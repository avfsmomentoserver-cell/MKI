"""Common types and shared persistence logic for MKC ingestion collectors.

A collector reads a source (git repository, markdown directory, chat
exports) in a strictly **read-only** manner and produces
:class:`RawArtifact` records plus, when a SQLAlchemy session is available,
persistent ``Source`` and ``Document`` rows.

Design rules
------------
- Deterministic: re-running a collector never creates duplicate rows.
  ``Source`` rows are upserted by ``source_id``; ``Document`` rows by the
  natural key ``(source_id, file_path, file_hash)``.
- Resilient: per-file errors are recorded in :class:`IngestionResult`
  instead of aborting the run.
- Core-tolerant: the SQLAlchemy models live in the core package
  (``mkc.models``).  Importing is lazy; when the core is not present yet
  collectors still collect in-memory artifacts and log a warning.

Core contract (backend core package):
- ``Source.source_id`` is the natural string id; ``Document.source_id``
  and ``KnowledgeObject.source_id`` are UUID foreign keys into
  ``sources.id``.  Collectors therefore resolve the ``Source`` row first
  and pass the ORM row (or its ``id``) when creating documents.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Protocol

logger = logging.getLogger("mkc.ingest")

#: Directory names that are never indexed.
SKIP_DIRECTORIES: frozenset[str] = frozenset({
    "node_modules", ".git", "dist", "build", ".venv", "venv",
    "__pycache__", ".idea", ".vscode", ".pytest_cache",
})

#: File names that are never indexed.
SKIP_FILES: frozenset[str] = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
})

#: Maximum file size indexed as a document (bytes).
MAX_FILE_BYTES = 2 * 1024 * 1024

#: Number of recent commits recorded per repository.
COMMIT_LOG_LIMIT = 200

#: Provenance marker written on every extracted knowledge object.
EXTRACTION_METHOD = "rule-based-v1"

#: UUID namespace for deterministic (content-derived) primary keys.
_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mkc.momento")

#: Extensions treated as binary without content inspection.
BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".db", ".sqlite", ".sqlite3", ".parquet", ".feather", ".h5", ".pkl",
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".class", ".jar",
    ".war", ".o", ".a", ".bin", ".wasm",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac", ".ogg",
    ".pyd", ".node",
})

_DOC_TYPE_BY_EXTENSION: dict[str, str] = {
    ".md": "markdown", ".markdown": "markdown",
    ".py": "code", ".js": "code", ".jsx": "code", ".ts": "code",
    ".tsx": "code", ".go": "code", ".rs": "code", ".rb": "code",
    ".java": "code", ".c": "code", ".h": "code", ".cpp": "code",
    ".hpp": "code", ".cs": "code", ".php": "code", ".swift": "code",
    ".kt": "code", ".scala": "code", ".sh": "code", ".pl": "code",
    ".lua": "code", ".r": "code",
    ".json": "json",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "config", ".ini": "config", ".cfg": "config",
    ".conf": "config", ".env": "config",
    ".csv": "data", ".sql": "data",
    ".txt": "text", ".rst": "text",
    ".html": "html", ".css": "html",
}

_LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go",
    ".rs": "rust", ".rb": "ruby", ".java": "java", ".c": "c",
    ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp",
    ".php": "php", ".swift": "swift", ".kt": "kotlin",
    ".scala": "scala", ".sh": "shell", ".pl": "perl", ".lua": "lua",
    ".r": "r", ".md": "markdown", ".json": "json", ".yaml": "yaml",
    ".yml": "yaml", ".html": "html", ".css": "css", ".sql": "sql",
    ".toml": "toml", ".txt": "text",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def stable_uuid(basis: str) -> uuid.UUID:
    """Deterministic UUIDv5 derived from *basis* (re-runs are idempotent)."""
    return uuid.uuid5(_ID_NAMESPACE, basis)


def slugify_text(text: str, max_length: int = 120) -> str:
    """Lowercase ASCII slug with separators collapsed to single dashes.

    Prefers ``python-slugify`` when installed, otherwise pure Python.
    """
    try:
        from slugify import slugify
        return slugify(text or "", max_length=max_length) or "n/a"
    except Exception:  # pragma: no cover - slugify missing
        cleaned = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
        return cleaned[:max_length].strip("-") or "n/a"


def is_test_path(path: str) -> bool:
    """Return True when *path* looks like a test file or test directory."""
    name = path.rsplit("/", 1)[-1]
    lower = name.lower()
    if lower.startswith("test_") or lower == "test.py" or lower.endswith("_test.py"):
        return True
    if lower.startswith("test") and (lower.endswith(".js") or lower.endswith(".ts")):
        return True
    if lower in {"conftest.py", "jest.config.js", "jest.config.ts", "pytest.ini"}:
        return True
    for dirpart in path.split("/")[:-1]:
        if dirpart.lower() in {"tests", "test", "spec", "__tests__"}:
            return True
    return False


def doc_type_for_path(path: str) -> str:
    """Map a file path to a stable ``doc_type`` bucket.

    Buckets: code, test, markdown, json, yaml, config, data, text, html,
    other.  Test files win over their extension so relationship building
    can distinguish them from production modules.
    """
    name = path.rsplit("/", 1)[-1]
    if name == ".gitignore":
        return "config"
    if is_test_path(path):
        return "test"
    extension = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    return _DOC_TYPE_BY_EXTENSION.get(extension, "other")


def language_for_path(path: str) -> str:
    """Map a file path to a language name (empty string when unknown)."""
    name = path.rsplit("/", 1)[-1]
    extension = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    return _LANGUAGE_BY_EXTENSION.get(extension, "")


def looks_binary(path: str, first_bytes: bytes) -> bool:
    """Binary heuristic: known extension or a NUL byte in the first 4 KB."""
    name = path.rsplit("/", 1)[-1]
    extension = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    if extension in BINARY_EXTENSIONS:
        return True
    return b"\x00" in (first_bytes or b"")[:4096]


def should_skip_path(path: str) -> bool:
    """Return True when *path* must never be indexed."""
    parts = path.split("/")
    name = parts[-1]
    if name in SKIP_FILES:
        return True
    return any(part in SKIP_DIRECTORIES for part in parts)


def new_uuid() -> str:
    """New UUID4 string."""
    return str(uuid.uuid4())


def sha256_hex(data: bytes | str) -> str:
    """SHA-256 hex digest of text or bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


@dataclass
class IngestionResult:
    """Summary of a single collector run.

    Attributes
    ----------
    repo:
        Identifier of the source (repository name or directory name).
    path:
        Absolute path of the source on disk.
    files_indexed:
        Number of files examined for indexing.
    documents_created:
        Number of ``Document`` rows inserted or refreshed.
    commits_indexed:
        Number of commit ``Source`` rows recorded (0 for non-git sources).
    errors:
        Human-readable error lines for files or operations that failed.
    duration:
        Wall-clock seconds spent in :meth:`CollectionRunner.run`.
    """

    repo: str
    path: str
    files_indexed: int = 0
    documents_created: int = 0
    commits_indexed: int = 0
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0

    def merge(self, other: "IngestionResult") -> None:
        """Accumulate another result into this one."""
        self.files_indexed += other.files_indexed
        self.documents_created += other.documents_created
        self.commits_indexed += other.commits_indexed
        self.errors.extend(other.errors)

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe representation for logs and reports."""
        return {
            "repo": self.repo,
            "path": self.path,
            "files_indexed": self.files_indexed,
            "documents_created": self.documents_created,
            "commits_indexed": self.commits_indexed,
            "errors": list(self.errors),
            "duration": round(self.duration, 3),
        }


@dataclass
class RawArtifact:
    """A single piece of source material collected for downstream parsing.

    Attributes
    ----------
    source_type:
        ``git`` | ``commit`` | ``markdown`` | ``chatgpt``.
    source_id:
        Natural identifier of the owning source (repository name, commit
        hash, directory name or conversation id).
    path:
        File path within the source (relative for git repositories).
    content:
        File text, or ``None`` when the content is not (or could not be)
        materialized.
    metadata:
        Free-form metadata: ``doc_type``, ``sha256``, ``size_bytes``,
        ``author``, ``section_tree``, ...
    """

    source_type: str
    source_id: str
    path: str
    content: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseCollector(Protocol):
    """Protocol implemented by all MKC ingestion collectors."""

    def collect(self) -> list[RawArtifact]:
        """Collect artifacts from the source (read-only access)."""
        ...

    def run(self, session_factory: Optional[Callable[[], Any]] = None) -> IngestionResult:
        """Collect artifacts, persist Source/Document rows, return a summary."""
        ...


class CollectionRunner:
    """Shared lifecycle and persistence for collectors.

    Subclasses implement :meth:`collect` and (optionally)
    :meth:`_persist_source` / :meth:`_persist_artifact`.  :meth:`run`
    owns the transaction and never raises on per-file errors.
    """

    def __init__(self, repo_name: str, path: str,
                 db_session_factory: Optional[Callable[[], Any]] = None) -> None:
        self._repo_name = repo_name
        self._path = str(path)
        self._factory = db_session_factory
        self._core_models: Optional[Any] = None
        self._models_checked = False

    # -- core model access --------------------------------------------------

    def _models(self) -> Optional[Any]:
        """Import the core model namespace once; ``None`` when unavailable."""
        if not self._models_checked:
            self._models_checked = True
            try:
                import mkc.models as models  # type: ignore[attr-defined]
                self._core_models = models
            except Exception as exc:
                logger.warning(
                    "mkc.models unavailable (%s: %s); %s will collect "
                    "in-memory only until the backend core lands",
                    type(exc).__name__, exc, type(self).__name__,
                )
                self._core_models = False  # type: ignore[assignment]
        return self._core_models or None

    # -- session handling ----------------------------------------------------

    def _open_session(self) -> Any:
        """Open a session from the injected factory, else the core's.

        The factory may be a zero-arg callable returning either a raw
        session (closed by us) or a context manager (used via ``with``).
        """
        if self._factory is not None:
            return self._factory()
        from mkc.core.database import get_session_factory  # type: ignore[import-not-found]

        return get_session_factory()()

    # -- upsert helpers --------------------------------------------------------

    @staticmethod
    def _find_first(session: Any, model: Any, **filters: Any) -> Any:
        from sqlalchemy import select

        stmt = select(model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(model, key) == value)
        return session.execute(stmt).scalars().first()

    def _upsert(self, session: Any, model: Any, values: Mapping[str, Any],
                key_attrs: Mapping[str, Any]) -> tuple[Any, bool]:
        """Insert or update a row keyed by *key_attrs*; return (row, created)."""
        existing = self._find_first(session, model, **key_attrs)
        if existing is None:
            row = model(**{**values, **key_attrs})  # type: ignore[call-arg]
            session.add(row)
            session.flush()
            return row, True
        for key, value in values.items():
            setattr(existing, key, value)
        session.flush()
        return existing, False

    def _ensure_source(self, session: Any, source_type: str, source_id: str,
                       path: str, metadata: Mapping[str, Any]) -> Any:
        """Upsert a ``Source`` row keyed by ``source_id`` (idempotent)."""
        models = self._models()
        if models is None:
            return None
        row, _created = self._upsert(
            session,
            models.Source,
            {
                "source_type": source_type,
                "path": path,
                "metadata_json": dict(metadata),
                "indexed_at": utcnow(),
            },
            {"source_id": source_id},
        )
        return row

    def _ensure_document(self, session: Any, source_row: Any, file_path: str,
                         file_hash: str, size_bytes: int, doc_type: str,
                         title: str, section_tree: Any = None) -> Any:
        """Upsert a ``Document`` row keyed by (source, file_path, file_hash).

        ``source_row`` is the ORM ``Source`` row (its UUID ``id`` feeds the
        foreign key); a raw UUID is also accepted.
        """
        models = self._models()
        if models is None or source_row is None:
            return None
        source_uuid = getattr(source_row, "id", source_row)
        row, _created = self._upsert(
            session,
            models.Document,
            {
                "file_hash": file_hash,
                "size_bytes": int(size_bytes or 0),
                "doc_type": doc_type,
                "title": title,
                "section_tree": section_tree,
            },
            {"source_id": source_uuid, "file_path": file_path,
             "file_hash": file_hash},
        )
        return row

    # -- run lifecycle ---------------------------------------------------------

    def run(self, session_factory: Optional[Callable[[], Any]] = None) -> IngestionResult:
        """Collect artifacts, persist rows, and return a summary.

        Per-file failures are captured in ``result.errors``; a
        collection-level failure returns early with the error recorded.
        """
        started = time.perf_counter()
        if session_factory is not None:
            self._factory = session_factory
        result = IngestionResult(repo=self._repo_name, path=self._path)
        try:
            artifacts = self.collect()
        except Exception as exc:
            result.errors.append(f"collection failed: {type(exc).__name__}: {exc}")
            result.duration = time.perf_counter() - started
            return result

        try:
            with self._open_session() as session:
                try:
                    self._persist_source(session, result)
                except Exception as exc:
                    result.errors.append(
                        f"source row: {type(exc).__name__}: {exc}"
                    )
                for artifact in artifacts:
                    try:
                        result.files_indexed += 1
                        self._persist_artifact(session, artifact, result)
                    except Exception as exc:
                        result.errors.append(
                            f"{artifact.path}: {type(exc).__name__}: {exc}"
                        )
                session.commit()
        except Exception as exc:
            if self._models() is None and self._factory is None:
                logger.warning(
                    "%s: no session available (%s: %s); artifacts were "
                    "collected but not persisted",
                    type(self).__name__, type(exc).__name__, exc,
                )
            else:
                raise
        result.duration = time.perf_counter() - started
        return result

    # -- persistence hooks -------------------------------------------------------

    def _persist_source(self, session: Any, result: IngestionResult) -> None:
        """Persist the top-level ``Source`` row; override in subclasses."""

    def _persist_artifact(self, session: Any, artifact: RawArtifact,
                          result: IngestionResult) -> None:
        """Persist one artifact as a ``Document`` row (default layout).

        Default layout keys the document to the runner's top-level source
        (subclasses that need per-artifact sources override this).
        """
        meta = artifact.metadata
        self._ensure_document(
            session,
            source_row=getattr(self, "_source_row", None),
            file_path=artifact.path,
            file_hash=str(meta.get("sha256", "")),
            size_bytes=int(meta.get("size_bytes", 0)),
            doc_type=str(meta.get("doc_type", "other")),
            title=str(meta.get("title") or artifact.path.rsplit("/", 1)[-1]),
            section_tree=meta.get("section_tree"),
        )
        result.documents_created += 1
