"""Markdown directory collector.

Recursively scans a directory for ``.md`` / ``.markdown`` files and
persists one ``Document`` row per file, enriched with:

- ``title``: first H1 (or the file name when absent);
- ``section_tree``: JSON hierarchy of headings ``[{level, title,
  children: [...]}, ...]``;
- metadata: word count and code block count.

Parsing uses ``markdown-it-py`` when available, with a pure-Python
line-based heading parser as the offline fallback.  The ``section_tree``
algorithm is identical in both modes, so results are stable across
environments.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from mkc.intelligence.ingest.base import (
    MAX_FILE_BYTES,
    CollectionRunner,
    RawArtifact,
    should_skip_path,
    utcnow,
)

logger = logging.getLogger("mkc.ingest.markdown")

MARKDOWN_EXTENSIONS = {".md", ".markdown"}

_H1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```|~~~)")

INLINE_CONTENT_LIMIT = 256 * 1024


def parse_headings_fallback(text: str) -> list[dict[str, Any]]:
    """Pure-Python heading parser (outside fenced code blocks).

    Returns a flat list of ``{"level": int, "title": str}`` in document
    order.
    """
    headings: list[dict[str, Any]] = []
    in_fence = False
    for line in text.splitlines():
        fence = _FENCE_RE.match(line.lstrip())
        if fence:
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match:
            headings.append({
                "level": len(match.group(1)),
                "title": match.group(2).strip(),
            })
    return headings


def _parse_headings_markdownit(text: str) -> list[dict[str, Any]]:
    """Heading extraction via ``markdown-it-py`` (fence-aware).

    Pairs each ``heading_open`` token with the following ``inline`` token
    that carries the heading text.
    """
    from markdown_it import MarkdownIt  # type: ignore[import-not-found]

    headings: list[dict[str, Any]] = []
    pending: Optional[dict[str, Any]] = None
    for token in MarkdownIt("commonmark").parse(text):
        if token.type == "heading_open":
            pending = {"level": int(token.tag[1]), "title": ""}  # h1..h6
        elif token.type == "inline" and pending is not None:
            pending["title"] = (token.content or "").strip()
            headings.append(pending)
            pending = None
    return headings


def parse_headings(text: str) -> list[dict[str, Any]]:
    """Extract flat headings using markdown-it when available.

    Falls back to :func:`parse_headings_fallback` when ``markdown-it-py``
    is not installed or the parser fails; both produce the same shape.
    """
    try:
        return _parse_headings_markdownit(text)
    except ImportError:
        return parse_headings_fallback(text)
    except Exception as exc:  # pragma: no cover - parser regression guard
        logger.debug("markdown-it parsing failed (%s); using fallback", exc)
        return parse_headings_fallback(text)


def headings_to_tree(headings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nest a flat heading list into a section tree.

    ``[{level, title}, ...]`` -> ``[{level, title, children: [...]}, ...]``
    where children are the following headings of deeper level, up to the
    next heading of the same or shallower level.
    """
    root: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []
    for heading in headings:
        node = {"level": heading["level"], "title": heading["title"],
                "children": []}
        while stack and stack[-1][0] >= node["level"]:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            root.append(node)
        stack.append((node["level"], node))
    return root


def count_code_blocks(text: str) -> int:
    """Count fenced code blocks (opening fences)."""
    in_fence = False
    count = 0
    for line in text.splitlines():
        if _FENCE_RE.match(line.lstrip()):
            if in_fence:
                count += 1
            in_fence = not in_fence
    return count


def word_count(text: str) -> int:
    """Approximate word count (whitespace split)."""
    return len(text.split())


def extract_title(text: str, fallback: str) -> str:
    """First H1 in the document, else the fallback (file name)."""
    match = _H1_RE.search(text)
    if match:
        return match.group(1).strip()
    return fallback


class MarkdownCollector(CollectionRunner):
    """Index all markdown files under a directory.

    Parameters
    ----------
    dir_path:
        Directory to scan recursively.
    source_name:
        ``source_id`` used for the ``Source`` row; defaults to the
        directory's basename.
    db_session_factory:
        Optional session factory (see :class:`GitRepoCollector`).
    """

    def __init__(self, dir_path: str | Path,
                 source_name: Optional[str] = None,
                 db_session_factory: Optional[Any] = None) -> None:
        self.dir_path = Path(dir_path).expanduser().resolve()
        super().__init__(
            repo_name=source_name or self.dir_path.name,
            path=str(self.dir_path),
            db_session_factory=db_session_factory,
        )

    def iter_markdown_files(self) -> list[Path]:
        """All markdown files under ``dir_path`` (skip-listed dirs excluded)."""
        if not self.dir_path.is_dir():
            return []
        found: list[Path] = []
        for path in sorted(self.dir_path.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in MARKDOWN_EXTENSIONS:
                continue
            relative = path.relative_to(self.dir_path).as_posix()
            if should_skip_path(relative):
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            found.append(path)
        return found

    def _analyze(self, path: Path, text: str) -> dict[str, Any]:
        """Title, section tree, word count and code block count."""
        headings = parse_headings(text)
        return {
            "title": extract_title(text, path.stem),
            "section_tree": headings_to_tree(headings),
            "code_block_count": count_code_blocks(text),
            "word_count": word_count(text),
        }

    def collect(self) -> list[RawArtifact]:
        """Emit one artifact per markdown file (content inlined when small)."""
        artifacts: list[RawArtifact] = []
        for path in self.iter_markdown_files():
            relative = path.relative_to(self.dir_path).as_posix()
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise OSError(f"unreadable markdown file {path}: {exc}") from exc
            text = raw.decode("utf-8", errors="replace")
            size = len(raw)
            content = text if size <= INLINE_CONTENT_LIMIT else None
            analysis = self._analyze(path, text)
            artifacts.append(RawArtifact(
                source_type="markdown",
                source_id=self.repo_name,
                path=relative,
                content=content,
                metadata={
                    "doc_type": "markdown",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": size,
                    "title": analysis["title"],
                    "section_tree": analysis["section_tree"],
                    "code_block_count": analysis["code_block_count"],
                    "word_count": analysis["word_count"],
                },
            ))
        return artifacts

    # -- persistence ---------------------------------------------------------

    def _persist_source(self, session: Any, result: Any) -> None:
        files = self.iter_markdown_files()
        self._ensure_source(
            session,
            source_type="markdown",
            source_id=self.repo_name,
            path=str(self.dir_path),
            metadata={
                "file_count": len(files),
                "indexed_at": utcnow().isoformat(),
            },
        )

    def _persist_artifact(self, session: Any, artifact: RawArtifact,
                          result: Any) -> None:
        meta = artifact.metadata
        section_tree = meta.get("section_tree")
        self._ensure_document(
            session,
            source_id=self.repo_name,
            file_path=artifact.path,
            file_hash=str(meta.get("sha256", "")),
            size_bytes=int(meta.get("size_bytes", 0)),
            doc_type="markdown",
            title=str(meta.get("title") or artifact.path.rsplit("/", 1)[-1]),
            section_tree=json.dumps(section_tree, ensure_ascii=False)
            if section_tree is not None else None,
        )
        result.documents_created += 1
