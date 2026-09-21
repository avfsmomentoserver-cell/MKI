"""Git repository collector (strictly read-only).

Indexes a local git repository into MKC:

- one ``Source`` row (``source_type="git"``) with commit count, last
  commit, detected languages and current branch;
- one ``Source`` row per recent commit (``source_type="commit"``,
  upserted by commit hash) with author, date, subject and the list of
  files changed;
- one ``Document`` row per tracked text file (upserted by
  ``(source_id, file_path, file_hash)``).

The collector never writes into the repository: it only uses read-only
``git`` commands (``ls-files``, ``log``, ``rev-list``, ``rev-parse``,
``branch``).  Binaries, lock files, ``node_modules``/``.git``/``dist``/
``build`` trees and files larger than 2 MB are skipped.

``git log``/``rev-list`` output is parsed as untrusted data; a repository
with a hostile history can only produce junk metadata, never code
execution.  Re-running the collector is idempotent.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mkc.intelligence.ingest.base import (
    COMMIT_LOG_LIMIT,
    MAX_FILE_BYTES,
    CollectionRunner,
    RawArtifact,
    doc_type_for_path,
    language_for_path,
    looks_binary,
    should_skip_path,
    utcnow,
)

logger = logging.getLogger("mkc.ingest.git")

#: Files at or below this size keep their text inline in the artifact;
#: larger files store only a hash (the parser re-reads them from disk).
INLINE_CONTENT_LIMIT = 256 * 1024

_LOG_MARKER = "@@@COMMIT@@@"
_FIELD_SEP = "\x1f"


def _is_safe_path(repo_root: Path, candidate: Path) -> bool:
    """Check if a candidate path is safe to read (T-N1: symlink containment).

    Returns False if:
    - The resolved path is outside the resolved repo root
    - The candidate path is a symlink (even if it points inside the repo)

    This prevents directory traversal via symlinks that could escape the repo.
    """
    try:
        resolved_repo = repo_root.resolve()
        resolved_candidate = candidate.resolve()
    except (OSError, RuntimeError):
        return False
    
    # Check if the resolved path is inside the resolved repo
    try:
        resolved_candidate.relative_to(resolved_repo)
    except ValueError:
        return False
    
    # Reject symlinks even if they point inside the repo
    if candidate.is_symlink():
        return False
    
    return True


def _read_text_bounded(path: Path, limit: int) -> Optional[str]:
    """Read up to *limit* bytes as UTF-8 text; ``None`` when unreadable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return None


def _sha256_file(path: Path) -> str:
    """SHA-256 of a file's full content (streamed)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_commit_log(raw: str) -> list[dict[str, Any]]:
    """Parse ``git log --name-only`` output into commit dictionaries.

    The pretty format is ``@@@COMMIT@@@<hash>\\x1f<author>\\x1f<date>\\x1f<subject>``
    followed by the changed file paths of that commit.  Field values are
    treated as opaque text (hostile history cannot inject markers because
    the separators are non-printable and the marker line is anchored).
    """
    commits: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    for line in raw.splitlines():
        if line.startswith(_LOG_MARKER):
            if current is not None:
                commits.append(current)
            payload = line[len(_LOG_MARKER):]
            fields = payload.split(_FIELD_SEP)
            commit: dict[str, Any] = {
                "hash": fields[0].strip() if fields else "",
                "author": fields[1].strip() if len(fields) > 1 else "",
                "date": fields[2].strip() if len(fields) > 2 else "",
                "subject": fields[3].strip() if len(fields) > 3 else "",
                "files": [],
            }
            current = commit
        elif current is not None and line.strip():
            current["files"].append(line.strip())
    if current is not None:
        commits.append(current)
    for commit in commits:
        commit["files_changed"] = len(commit["files"])
    return commits


class GitRepoCollector(CollectionRunner):
    """Index one local git repository (read-only).

    Parameters
    ----------
    repo_path:
        Path to the repository root (must contain ``.git``).
    db_session_factory:
        Optional zero-arg callable returning a SQLAlchemy session (or a
        session context manager).  When omitted the core's
        ``get_session`` is used.
    """

    def __init__(self, repo_path: str | Path,
                 db_session_factory: Optional[Any] = None) -> None:
        self.repo_path = Path(repo_path).expanduser().resolve()
        super().__init__(
            repo_name=self.repo_path.name,
            path=str(self.repo_path),
            db_session_factory=db_session_factory,
        )
        self._gitpy_repo: Optional[Any] = None
        self._gitpy_failed = False

    # ------------------------------------------------------------------ git

    def _run_git(self, *args: str, timeout: int = 120) -> Optional[str]:
        """Run a read-only ``git`` command; ``None`` on any failure."""
        command = ["git", "-C", str(self.repo_path), *args]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("git %s failed: %s", " ".join(args[:2]), exc)
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout

    def _is_git_repo(self) -> bool:
        if self._gitpy_repo is not None or self._gitpy_failed:
            return self._gitpy_repo is not None
        try:
            from git import Repo  # type: ignore[import-not-found]
            from git.exc import InvalidGitRepositoryError  # type: ignore[import-not-found]
            try:
                self._gitpy_repo = Repo(str(self.repo_path), search_parent_directories=False)
            except InvalidGitRepositoryError:
                self._gitpy_repo = None
        except ImportError:
            pass
        if self._gitpy_repo is None:
            probe = self._run_git("rev-parse", "--is-inside-work-tree")
            if probe is None or probe.strip() != "true":
                self._gitpy_failed = True
            elif self._gitpy_repo is None:
                # no GitPython but a real git repo: keep using subprocess
                self._gitpy_failed = False
        else:
            self._gitpy_failed = False
        return self._gitpy_repo is not None or not self._gitpy_failed

    def _ls_files(self) -> list[str]:
        """Tracked file paths (repo-relative, forward slashes)."""
        if self._gitpy_repo is not None:
            raw = self._gitpy_repo.git.ls_files("-z")
            return [p for p in raw.split("\0") if p]
        raw = self._run_git("ls-files")
        if raw is None:
            return []
        return [line for line in raw.splitlines() if line.strip()]

    def _branch_name(self) -> str:
        if self._gitpy_repo is not None:
            try:
                head = self._gitpy_repo.head
                if head.is_detached:
                    return "detached"
                return head.ref.name
            except Exception:
                return "unknown"
        raw = self._run_git("branch", "--show-current")
        branch = (raw or "").strip()
        return branch or "unknown"

    def _head_commit(self) -> Optional[dict[str, Any]]:
        if self._gitpy_repo is not None:
            try:
                commit = self._gitpy_repo.head.commit
                return {
                    "hash": commit.hexsha,
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat()
                    if commit.committed_datetime else "",
                    "subject": commit.summary,
                }
            except Exception as exc:  # empty repository
                logger.debug("no HEAD commit: %s", exc)
                return None
        raw = self._run_git("log", "-n", "1",
                            "--pretty=format:%H%x1f%an%x1f%aI%x1f%s")
        if not raw or not raw.strip():
            return None
        fields = raw.split(_FIELD_SEP)
        return {
            "hash": fields[0].strip(),
            "author": fields[1].strip() if len(fields) > 1 else "",
            "date": fields[2].strip() if len(fields) > 2 else "",
            "subject": fields[3].strip() if len(fields) > 3 else "",
        }

    def _commit_log(self) -> list[dict[str, Any]]:
        """Last up-to-200 commits, newest first, with changed file lists."""
        if self._gitpy_repo is not None:
            commits: list[dict[str, Any]] = []
            try:
                for commit in self._gitpy_repo.iter_commits(
                    max_count=COMMIT_LOG_LIMIT
                ):
                    files: list[str] = []
                    try:
                        stats = commit.stats
                        for stat_file in stats.files:
                            name = stat_file.b_path or stat_file.a_path
                            if name:
                                files.append(name)
                    except Exception:
                        files = []
                    committed = commit.committed_datetime
                    commits.append({
                        "hash": commit.hexsha,
                        "author": str(commit.author),
                        "date": committed.isoformat() if committed else "",
                        "subject": commit.summary,
                        "files": files,
                        "files_changed": len(files),
                    })
                return commits
            except Exception as exc:
                logger.warning("GitPython log failed (%s); falling back to "
                               "subprocess", exc)
        raw = self._run_git(
            "log", "-n", str(COMMIT_LOG_LIMIT), "--name-only",
            f"--pretty=format:{_LOG_MARKER}%H{_FIELD_SEP}%an"
            f"{_FIELD_SEP}%aI{_FIELD_SEP}%s",
        )
        if raw is None:
            return []
        return _parse_commit_log(raw)

    def _total_commit_count(self) -> int:
        if self._gitpy_repo is not None:
            try:
                return len(list(self._gitpy_repo.iter_commits()))
            except Exception:
                return 0
        raw = self._run_git("rev-list", "--count", "HEAD")
        try:
            return int((raw or "0").strip() or 0)
        except ValueError:
            return 0

    # --------------------------------------------------------------- collect

    def collect(self) -> list[RawArtifact]:
        """Enumerate tracked files and emit one artifact per indexable file."""
        if not self._is_git_repo():
            raise FileNotFoundError(
                f"{self.repo_path} is not a git repository"
            )
        artifacts: list[RawArtifact] = []
        for relative in self._ls_files():
            relative = relative.replace("\\", "/")
            if should_skip_path(relative):
                continue
            absolute = self.repo_path / relative
            # T-N1: Symlink containment check
            if not _is_safe_path(self.repo_path, absolute):
                logger.debug("Skipping unsafe path (symlink or outside repo): %s", relative)
                continue
            try:
                size = absolute.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            head_bytes = b""
            try:
                with open(absolute, "rb") as handle:
                    head_bytes = handle.read(4096)
            except OSError:
                continue
            if looks_binary(relative, head_bytes):
                continue
            content: Optional[str] = None
            if size <= INLINE_CONTENT_LIMIT:
                content = _read_text_bounded(absolute, INLINE_CONTENT_LIMIT)
            artifacts.append(RawArtifact(
                source_type="git",
                source_id=self.repo_path.name,
                path=relative,
                content=content,
                metadata={
                    "doc_type": doc_type_for_path(relative),
                    "sha256": _sha256_file(absolute),
                    "size_bytes": size,
                    "abs_path": str(absolute),
                },
            ))
        return artifacts

    # ------------------------------------------------------------- persistence

    def _collect_repo_summary(self) -> dict[str, Any]:
        """Gather commit/branch/language facts for the repo Source row."""
        commits = self._commit_log()
        head = self._head_commit()
        files = self._ls_files()
        languages = Counter(
            language_for_path(f) for f in files if language_for_path(f)
        )
        summary: dict[str, Any] = {
            "commit_count": self._total_commit_count(),
            "last_commit": head,
            "branch": self._branch_name(),
            "languages": sorted(languages.items()),
            "language_counts": dict(languages),
            "tracked_file_count": len(files),
            "indexed_at": utcnow().isoformat(),
        }
        return summary, commits, head

    def _persist_source(self, session: Any, result: Any) -> None:
        summary, commits, head = self._collect_repo_summary()
        self._repo_summary = summary
        self._repo_commits = commits
        if head is None:
            result.errors.append(
                "repository has no commits; file index only"
            )
        self._source_row = self._ensure_source(
            session,
            source_type="git",
            source_id=self.repo_path.name,
            path=str(self.repo_path),
            metadata=summary,
        )
        for commit in commits:
            self._ensure_source(
                session,
                source_type="commit",
                source_id=commit["hash"],
                path=str(self.repo_path),
                metadata={
                    "repo": self.repo_path.name,
                    "author": commit["author"],
                    "date": commit["date"],
                    "subject": commit["subject"],
                    "files_changed": list(commit["files"]),
                    "files_changed_count": commit["files_changed"],
                },
            )
            result.commits_indexed += 1

    def _persist_artifact(self, session: Any, artifact: RawArtifact,
                          result: Any) -> None:
        meta = artifact.metadata
        title = artifact.path.rsplit("/", 1)[-1]
        if meta.get("doc_type") == "markdown" and artifact.content:
            match = re.search(r"^#\s+(.+)$", artifact.content, re.MULTILINE)
            if match:
                title = match.group(1).strip()
        self._ensure_document(
            session,
            source_row=getattr(self, "_source_row", None),
            file_path=artifact.path,
            file_hash=str(meta.get("sha256", "")),
            size_bytes=int(meta.get("size_bytes", 0)),
            doc_type=str(meta.get("doc_type", "other")),
            title=title,
            section_tree=None,
        )
        result.documents_created += 1

    # -- run wrapper: attach repo summary to results -------------------------

    def run(self, session_factory: Optional[Any] = None) -> Any:
        from mkc.intelligence.ingest.base import IngestionResult

        result = super().run(session_factory)
        summary = getattr(self, "_repo_summary", None)
        if summary is not None:
            result.metadata = {  # type: ignore[attr-defined]
                "commit_count": summary["commit_count"],
                "branch": summary["branch"],
                "languages": summary["languages"],
            }
        return result
