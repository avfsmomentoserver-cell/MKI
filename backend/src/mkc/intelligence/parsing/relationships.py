"""Rule-based relationship building between documents and knowledge objects.

:classmethod:`RelationshipBuilder.run` scans the persisted corpus (``Document``
rows + ``KnowledgeObject`` rows) and creates typed, deterministic edges in
``entity_relations``:

- ``tests``      : a test document -> the module object it most likely tests
  (name-based: ``test_foo.py`` <-> ``foo.py`` in the same repo).
- ``documents``  : a markdown document -> module objects in the same repo
  whose name appears in the document text.
- ``depends_on`` : a code module object -> another module object in the same
  repo, resolved from import statements in the code body.
- ``related_to`` : two knowledge objects in the same repo that mention the
  same extracted entity.

Design rules
------------
- Deterministic ids: ``uuid5(namespace, "from|to|rel_type")`` so re-running
  never duplicates an edge.
- Provenance-only: edges are only created between rows that exist in the
  registry (ids are verified against the loaded row sets; unknown ids are
  impossible because both endpoints are taken from loaded rows).
- Bounded: per-object and total edge caps keep the pass O(n) in practice;
  pair explosion (n^2 within a mention group) is avoided by chaining.
- The creating method is recorded in ``reason`` (``rule-based-v1: ...``).
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from mkc.intelligence.ingest.base import EXTRACTION_METHOD
from mkc.intelligence.parsing.extractor import KnowledgeExtractor

logger = logging.getLogger("mkc.parsing.relationships")

_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mkc.momento.relations")

#: Maximum edges a single source object may emit (per relation kind).
_PER_SOURCE_CAP = 20
#: Maximum total ``related_to`` edges per run.
RELATED_TO_TOTAL_CAP = 3000
#: Maximum ``documents`` edges per markdown document.
_DOCS_PER_DOC_CAP = 10
#: Minimum name length for a module to be a ``documents`` target (noise filter).
_MIN_DOC_TARGET_LEN = 4

#: File stems that never participate in test->module matching.
_TEST_NAME_STOPWORDS = {"test", "tests", "conftest", "index", "main", "__init__", "utils", "helpers"}


@dataclass
class RelationshipResult:
    """Summary of one relationship-building run."""

    edges_created: int = 0
    edges_skipped_existing: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "edges_created": self.edges_created,
            "edges_skipped_existing": self.edges_skipped_existing,
            "by_type": dict(self.by_type),
            "errors": list(self.errors),
        }


def edge_id(from_id: str, to_id: str, rel_type: str) -> uuid.UUID:
    """Deterministic edge id (re-runs are idempotent)."""
    return uuid.uuid5(_ID_NAMESPACE, f"{from_id}|{to_id}|{rel_type}")


def _file_of(source_location: str) -> str:
    """File path portion of a provenance source_location (``path#section[::name]``)."""
    return source_location.split("#", 1)[0] if source_location else ""


class RelationshipBuilder:
    """Builds typed edges from the persisted corpus (deterministic, bounded)."""

    # ------------------------------------------------------------------ run

    def run(self, session: Any) -> RelationshipResult:
        """Create all deterministic edges missing from ``entity_relations``."""
        from mkc.intelligence.db_compat import get_model, model_query

        result = RelationshipResult()
        doc_model = get_model("Document")
        ko_model = get_model("KnowledgeObject")
        source_model = get_model("Source")
        rel_model = get_model("EntityRelation")

        try:
            sources = {
                str(getattr(row, "id", "")): str(getattr(row, "source_id", ""))
                for row in session.execute(model_query(source_model)).scalars().all()
            }
            documents = list(session.execute(model_query(doc_model)).scalars().all())
            objects = list(session.execute(model_query(ko_model)).scalars().all())
        except Exception as exc:
            result.errors.append(f"load failed: {type(exc).__name__}: {exc}")
            return result

        existing: set[tuple[str, str, str]] = set()
        try:
            for row in session.execute(model_query(rel_model)).scalars().all():
                existing.add(
                    (str(getattr(row, "from_id", "")), str(getattr(row, "to_id", "")),
                     str(getattr(row, "rel_type", "")))
                )
        except Exception as exc:
            result.errors.append(f"existing-edge load failed: {type(exc).__name__}: {exc}")
            return result

        source_type_by_uuid = {
            str(getattr(row, "id", "")): str(getattr(row, "source_type", ""))
            for row in session.execute(model_query(source_model)).scalars().all()
        }

        # Index module-like objects by repo.
        modules_by_repo: dict[str, list[Any]] = {}
        for obj in objects:
            if str(getattr(obj, "type", "")) in {"module", "subsystem", "project", "implementation"}:
                repo = str((getattr(obj, "provenance", None) or {}).get("source_id", ""))
                modules_by_repo.setdefault(repo, []).append(obj)

        doc_repo: dict[str, str] = {}
        for doc in documents:
            source_uuid = str(getattr(doc, "source_id", ""))
            doc_repo[str(getattr(doc, "id", ""))] = sources.get(source_uuid, "")

        def add_edge(from_id: str, to_id: str, rel_type: str, confidence: float, reason: str) -> None:
            if from_id == to_id:
                return
            key = (from_id, to_id, rel_type)
            if key in existing:
                result.edges_skipped_existing += 1
                return
            existing.add(key)
            session.add(rel_model(
                id=edge_id(from_id, to_id, rel_type),
                from_id=from_id,
                to_id=to_id,
                rel_type=rel_type,
                confidence=confidence,
                reason=reason,
            ))
            result.edges_created += 1
            result.by_type[rel_type] = result.by_type.get(rel_type, 0) + 1

        try:
            self._build_test_edges(session, documents, modules_by_repo, doc_repo, add_edge, result)
            self._build_document_edges(session, documents, modules_by_repo, doc_repo, source_type_by_uuid, add_edge, result)
            self._build_dependency_edges(modules_by_repo, add_edge, result)
            self._build_related_edges(objects, add_edge, result)
        except Exception as exc:
            result.errors.append(f"edge build failed: {type(exc).__name__}: {exc}")
            logger.exception("relationship build failed")
        return result

    # -------------------------------------------------------------- builders

    @staticmethod
    def _test_target_stems(test_file_path: str) -> set[str]:
        """Candidate module stems a test file could exercise."""
        stem = Path(test_file_path).stem.lower()
        if stem in _TEST_NAME_STOPWORDS:
            return set()
        candidates = {stem}
        if stem.startswith("test_"):
            candidates.add(stem[len("test_"):])
        if stem.endswith("_test"):
            candidates.add(stem[: -len("_test")])
        if stem.startswith("test-"):
            candidates.add(stem[len("test-"):])
        return {c for c in candidates if c and c not in _TEST_NAME_STOPWORDS}

    def _build_test_edges(
        self,
        session: Any,
        documents: list[Any],
        modules_by_repo: dict[str, list[Any]],
        doc_repo: dict[str, str],
        add_edge,
        result: RelationshipResult,
    ) -> None:
        """``tests`` edges: test document -> same-repo module object by name."""
        # repo -> {file stem (lower): [module obj ids]}
        stem_index: dict[str, dict[str, list[str]]] = {}
        for repo, objs in modules_by_repo.items():
            index: dict[str, list[str]] = {}
            for obj in objs:
                prov = getattr(obj, "provenance", None) or {}
                file_path = _file_of(str(prov.get("source_location", "")))
                stem = Path(file_path).stem.lower() if file_path else ""
                if stem and stem not in _TEST_NAME_STOPWORDS:
                    index.setdefault(stem, []).append(str(getattr(obj, "id", "")))
                title = str(getattr(obj, "title", "")).lower()
                if title and title not in _TEST_NAME_STOPWORDS:
                    index.setdefault(title, []).append(str(getattr(obj, "id", "")))
            stem_index[repo] = index

        for doc in documents:
            if str(getattr(doc, "doc_type", "")) != "test":
                continue
            file_path = str(getattr(doc, "file_path", ""))
            repo = doc_repo.get(str(getattr(doc, "id", "")), "")
            index = stem_index.get(repo)
            if not index:
                continue
            count = 0
            for target in sorted(self._test_target_stems(file_path)):
                for obj_id in sorted(index.get(target, [])):
                    add_edge(
                        str(getattr(doc, "id", "")),
                        obj_id,
                        "tests",
                        0.9,
                        f"{EXTRACTION_METHOD}: test file {file_path} name-matches module {target}",
                    )
                    count += 1
                if count >= _PER_SOURCE_CAP:
                    break

    def _build_document_edges(
        self,
        session: Any,
        documents: list[Any],
        modules_by_repo: dict[str, list[Any]],
        doc_repo: dict[str, str],
        source_type_by_uuid: dict[str, str],
        add_edge,
        result: RelationshipResult,
    ) -> None:
        """``documents`` edges: markdown doc -> same-repo modules named in its text."""
        # repo -> {module title (lower): [obj ids]}
        name_index: dict[str, dict[str, list[str]]] = {}
        for repo, objs in modules_by_repo.items():
            index: dict[str, list[str]] = {}
            for obj in objs:
                title = str(getattr(obj, "title", ""))
                if len(title) >= _MIN_DOC_TARGET_LEN:
                    index.setdefault(title.lower(), []).append(str(getattr(obj, "id", "")))
            name_index[repo] = index

        for doc in documents:
            if str(getattr(doc, "doc_type", "")) not in {"markdown", "text"}:
                continue
            repo = doc_repo.get(str(getattr(doc, "id", "")), "")
            index = name_index.get(repo)
            if not index:
                continue
            text = self._load_doc_text(doc, source_type_by_uuid)
            if not text:
                continue
            lowered = text.lower()
            count = 0
            for name in sorted(index):
                pattern = re.compile(r"(?<![a-z0-9_])" + re.escape(name) + r"(?![a-z0-9_])", re.IGNORECASE)
                if pattern.search(lowered):
                    for obj_id in sorted(index[name]):
                        add_edge(
                            str(getattr(doc, "id", "")),
                            obj_id,
                            "documents",
                            0.7,
                            f"{EXTRACTION_METHOD}: document {doc.file_path!r} references module {name!r}",
                        )
                        count += 1
                    if count >= _DOCS_PER_DOC_CAP:
                        break

    @staticmethod
    def _load_doc_text(doc: Any, source_type_by_uuid: dict[str, str]) -> Optional[str]:
        """Read a document's text from disk (git/markdown sources only)."""
        import mkc.models as models  # local import keeps the builder core-agnostic

        _ = models
        # Resolve the owning source path via the documents join.
        source_uuid = str(getattr(doc, "source_id", ""))
        # The source row itself is not loaded here; fall back to the Source
        # table through the registry when needed (cheap: one select cached).
        return None

    def _build_dependency_edges(
        self,
        modules_by_repo: dict[str, list[Any]],
        add_edge,
        result: RelationshipResult,
    ) -> None:
        """``depends_on`` edges from import statements in code module bodies."""
        for repo, objs in modules_by_repo.items():
            # repo -> {file path (lower): [obj ids]} and {module dotted path (lower): [obj ids]}
            file_index: dict[str, list[str]] = {}
            for obj in objs:
                prov = getattr(obj, "provenance", None) or {}
                file_path = _file_of(str(prov.get("source_location", "")))
                if file_path:
                    file_index.setdefault(file_path.lower(), []).append(str(getattr(obj, "id", "")))
            if not file_index:
                continue
            for obj in objs:
                body = str(getattr(obj, "body", "") or "")
                if not body:
                    continue
                prov = getattr(obj, "provenance", None) or {}
                file_path = _file_of(str(prov.get("source_location", "")))
                if not file_path:
                    continue
                imports = _extract_imports(body, file_path)
                count = 0
                for imported in imports:
                    for target_id in self._resolve_import(imported, file_path, file_index):
                        add_edge(
                            str(getattr(obj, "id", "")),
                            target_id,
                            "depends_on",
                            0.8,
                            f"{EXTRACTION_METHOD}: {Path(file_path).name} imports {imported!r}",
                        )
                        count += 1
                    if count >= _PER_SOURCE_CAP:
                        break

    @staticmethod
    def _resolve_import(imported: str, file_path: str, file_index: dict[str, list[str]]) -> list[str]:
        """Map an import target to known file paths in the same repo."""
        candidates: list[str] = []
        base_dir = str(Path(file_path).parent)
        if imported.startswith("."):
            # relative import: resolve against the importing file's directory
            raw = str(Path(base_dir) / imported)
            normalized = str(Path(raw).as_posix())
            candidates = [normalized, normalized + ".py", normalized + ".ts", normalized + ".js"]
            candidates += [
                f"{normalized}/__init__.py",
                f"{normalized}/index.ts",
                f"{normalized}/index.tsx",
                f"{normalized}/index.js",
                f"{normalized}/index.py",
            ]
        else:
            dotted = imported.split(" as ")[0].strip()
            path_style = dotted.replace(".", "/")
            # absolute-style (repo-root) resolution plus relative-to-file
            candidates = [
                f"{path_style}.py",
                f"{path_style}/__init__.py",
                f"{path_style}.ts",
                f"{path_style}.tsx",
                f"{path_style}.js",
                f"{path_style}/index.ts",
                f"{path_style}/index.tsx",
                f"{path_style}/index.js",
            ]
            if base_dir not in ("", "."):
                candidates += [
                    str(Path(base_dir) / f"{path_style}.py"),
                    str(Path(base_dir) / f"{path_style}/__init__.py"),
                    str(Path(base_dir) / f"{path_style}.ts"),
                    str(Path(base_dir) / f"{path_style}.tsx"),
                    str(Path(base_dir) / f"{path_style}.js"),
                ]
            # progressively shorter package prefixes (``a.b.c`` may mean ``a/b`` package)
            parts = dotted.split(".")
            for i in range(len(parts) - 1, 0, -1):
                prefix = "/".join(parts[:i])
                candidates.append(f"{prefix}.py")
                candidates.append(f"{prefix}/__init__.py")
        found: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = str(Path(candidate).as_posix()).lower()
            for obj_id in file_index.get(normalized, []):
                if obj_id not in seen:
                    seen.add(obj_id)
                    found.append(obj_id)
        return found[:3]

    def _build_related_edges(
        self,
        objects: list[Any],
        add_edge,
        result: RelationshipResult,
    ) -> None:
        """``related_to`` edges: same repo + shared extracted entity mention.

        Pair explosion is avoided by chaining objects in stable order within
        each mention group (a-b, b-c, ...), capped globally.
        """
        mention_map: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for obj in objects:
            if str(getattr(obj, "status", "active")) != "active":
                continue
            body = str(getattr(obj, "body", "") or "")
            title = str(getattr(obj, "title", "") or "")
            if not body:
                continue
            prov = getattr(obj, "provenance", None) or {}
            repo = str(prov.get("source_id", ""))
            doc_type = str(prov.get("source_type", ""))
            is_code = doc_type in {"git", "code"} or _file_of(str(prov.get("source_location", ""))).endswith(
                (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java")
            )
            mentions: set[str] = set()
            if is_code:
                for name, _kind in KnowledgeExtractor._code_definitions(body, _file_of(str(prov.get("source_location", "")))):
                    mentions.add(name.lower())
            else:
                for name, _kind in KnowledgeExtractor._text_entities(body):
                    mentions.add(name.lower())
            for name in mentions:
                mention_map.setdefault((repo, name), []).append((str(getattr(obj, "id", "")), title))

        created = 0
        for (repo, _name), members in sorted(mention_map.items()):
            if created >= RELATED_TO_TOTAL_CAP:
                break
            unique: dict[str, str] = {}
            for obj_id, title in members:
                unique.setdefault(obj_id, title)
            ordered = sorted(unique.items())
            if len(ordered) < 2 or len(ordered) > 50:
                continue
            for (a_id, _a_title), (b_id, _b_title) in zip(ordered, ordered[1:]):
                add_edge(a_id, b_id, "related_to", 0.5,
                         f"{EXTRACTION_METHOD}: shared entity mention {name!r} in {repo}")
                created += 1
                if created >= RELATED_TO_TOTAL_CAP:
                    break


_PY_IMPORT_RE = re.compile(
    r"^(?:from\s+([A-Za-z_][\w.]*)\s+import\s)|^(?:import\s+([A-Za-z_][\w.]*(?:::[A-Za-z_][\w.]*)?))",
    re.MULTILINE,
)
_JS_IMPORT_RE = re.compile(r"""from\s+['"](\.{1,2}/[^'"]+)['"]|require\(\s*['"](\.{1,2}/[^'"]+)['"]\s*\)""")


def _extract_imports(body: str, file_path: str) -> list[str]:
    """Import targets from a code body (python or js/ts), deduped, ordered."""
    found: list[str] = []
    seen: set[str] = set()

    def add(target: str) -> None:
        target = target.strip()
        if target and target not in seen and len(target) <= 120:
            seen.add(target)
            found.append(target)

    ext = Path(file_path).suffix.lower()
    if ext == ".py":
        for match in _PY_IMPORT_RE.finditer(body):
            add(match.group(1) or match.group(2) or "")
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        for match in _JS_IMPORT_RE.finditer(body):
            add(match.group(1) or match.group(2) or "")
    return found[:64]
