"""ChatGPT history importer (JSON exports).

Accepts a directory of JSON conversation exports in the two common
shapes:

- **flat**: ``[{"conversation_id"|"id"|"uuid": ..., "title"?, "messages":
  [{"role", "content", "timestamp"?}, ...]}, ...]``
- **nested**: ``[{"id": ..., "title"?, "created_at"?, "conversation":
  {"message"|"messages"|"items": [...]}, ...}, ...]``

Behavior guarantees
-------------------
- One ``Source`` row per export file (``source_type="chatgpt"``) and one
  ``Document`` row per conversation (title = exported title, else the
  first user message truncated to 120 chars).
- Assistant messages with substantial content are flagged for the
  knowledge extractor via ``metadata["extractable"]`` (see
  :class:`~mkc.intelligence.parsing.extractor.KnowledgeExtractor`); the
  importer itself stays deterministic and content-agnostic.
- Malformed files are skipped with the error recorded in
  ``IngestionResult.errors`` — the importer never crashes the run.
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
    utcnow,
)

logger = logging.getLogger("mkc.ingest.chatgpt")

#: Minimum characters of assistant message content to be considered
#: "substantial" by the extractor.
SUBSTANTIAL_MIN_CHARS = 160

_TITLE_MAX_LEN = 120
_CONVERSATION_ID_FIELDS = ("conversation_id", "id", "uuid", "chat_id")
_TITLE_FIELDS = ("title", "name", "subject")
_MESSAGES_FIELDS = ("messages", "message", "items")


def _first_present(record: dict[str, Any], fields: tuple[str, ...],
                    default: Any = None) -> Any:
    for field in fields:
        value = record.get(field)
        if value not in (None, ""):
            return value
    return default


def _extract_messages(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a conversation entry to a message list.

    Handles the flat layout (``entry["messages"]``) and the nested layout
    (``entry["conversation"]["messages"|"message"|"items"]``).
    """
    messages = entry.get("messages")
    if isinstance(messages, list):
        return messages
    conversation = entry.get("conversation")
    if isinstance(conversation, dict):
        for field in _MESSAGES_FIELDS:
            candidate = conversation.get(field)
            if isinstance(candidate, list):
                return candidate
    return []


def detect_export_format(payload: Any) -> str:
    """Detect the export shape: ``flat``, ``nested`` or ``unknown``."""
    if not isinstance(payload, list):
        return "unknown"
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if any(field in entry for field in _CONVERSATION_ID_FIELDS):
            if isinstance(entry.get("conversation"), dict):
                return "nested"
            if isinstance(entry.get("messages"), list):
                return "flat"
    return "unknown"


def conversation_title(entry: dict[str, Any]) -> str:
    """Exported title, else first user message truncated, else id."""
    title = _first_present(entry, _TITLE_FIELDS)
    if isinstance(title, str) and title.strip():
        return title.strip()[:_TITLE_MAX_LEN]
    for message in _extract_messages(entry):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).lower()
        if role != "user":
            continue
        content = message.get("content")
        text = _message_text(content)
        if text:
            return re.sub(r"\s+", " ", text).strip()[:_TITLE_MAX_LEN]
    conv_id = _first_present(entry, _CONVERSATION_ID_FIELDS, "")
    return str(conv_id)[:_TITLE_MAX_LEN] or "untitled-conversation"


def _message_text(content: Any) -> str:
    """Flatten a message content field to plain text.

    Content may be a plain string or a list of content parts
    (``[{"type": "text", "text": ...}]``), depending on export tooling.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(p for p in parts if p)
    if isinstance(content, dict):
        return str(content.get("text", ""))
    return str(content)


class ChatGPTImporter(CollectionRunner):
    """Import JSON ChatGPT conversation exports from a directory.

    Parameters
    ----------
    dir_path:
        Directory containing ``.json`` export files (scanned recursively).
    db_session_factory:
        Optional session factory (see :class:`GitRepoCollector`).
    """

    def __init__(self, dir_path: str | Path,
                 db_session_factory: Optional[Any] = None) -> None:
        self.dir_path = Path(dir_path).expanduser().resolve()
        super().__init__(
            repo_name=self.dir_path.name,
            path=str(self.dir_path),
            db_session_factory=db_session_factory,
        )

    def iter_export_files(self) -> list[Path]:
        """All JSON files under ``dir_path`` (sorted, size-bounded)."""
        if not self.dir_path.is_dir():
            return []
        files: list[Path] = []
        for path in sorted(self.dir_path.rglob("*.json")):
            if not path.is_file():
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(path)
        return files

    def parse_file(self, path: Path) -> tuple[list[dict[str, Any]], str]:
        """Parse one export file into normalized conversation entries.

        Returns ``(entries, format)`` where format is ``flat``,
        ``nested`` or ``unknown``.  Raises ``ValueError`` for files that
        are not valid JSON lists of conversations.
        """
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        if isinstance(payload, dict):
            # Some exports wrap the list: {"conversations": [...]}.
            for value in payload.values():
                if isinstance(value, list):
                    payload = value
                    break
        if not isinstance(payload, list):
            raise ValueError("expected a JSON array of conversations")
        entries = [entry for entry in payload if isinstance(entry, dict)]
        if not entries:
            raise ValueError("no conversation entries found")
        return entries, detect_export_format(payload)

    def collect(self) -> list[RawArtifact]:
        """Emit one artifact per conversation across all export files.

        Malformed files raise nothing: they are recorded via
        :meth:`collect_with_errors` instead.  This method is the
        Protocol entry point and collects only well-formed files,
        stashing per-file errors on ``self.errors``.
        """
        self.errors = []
        artifacts: list[RawArtifact] = []
        for path in self.iter_export_files():
            try:
                entries, _format = self.parse_file(path)
            except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError) as exc:
                self.errors.append(f"{path.name}: skipped ({type(exc).__name__}: {exc})")
                logger.warning("skipping chatgpt export %s: %s", path.name, exc)
                continue
            for entry in entries:
                artifacts.append(self._artifact_for(path, entry))
        return artifacts

    # ``collect`` is the Protocol method; expose errors on the result.
    errors: list[str]

    def _artifact_for(self, export_path: Path,
                      entry: dict[str, Any]) -> RawArtifact:
        conv_id = str(_first_present(entry, _CONVERSATION_ID_FIELDS,
                                     "")) or export_path.stem
        messages = _extract_messages(entry)
        normalized: list[dict[str, Any]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "unknown")).lower()
            text = _message_text(message.get("content"))
            normalized.append({
                "role": role,
                "content": text,
                "timestamp": message.get("timestamp") or message.get("created_at")
                or entry.get("created_at") or None,
                "substantial": role == "assistant"
                and len(text.strip()) >= SUBSTANTIAL_MIN_CHARS,
            })
        content_body = json.dumps(
            {"title": conversation_title(entry), "messages": normalized},
            ensure_ascii=False,
        )
        digest = hashlib.sha256(content_body.encode("utf-8")).hexdigest()
        return RawArtifact(
            source_type="chatgpt",
            source_id=conv_id,
            path=f"{export_path.name}#{conv_id}",
            content=content_body,
            metadata={
                "doc_type": "chatgpt",
                "sha256": digest,
                "size_bytes": len(content_body.encode("utf-8")),
                "title": conversation_title(entry),
                "export_file": export_path.name,
                "message_count": len(normalized),
                "created_at": entry.get("created_at") or None,
            },
        )

    # -- persistence ---------------------------------------------------------

    def _persist_source(self, session: Any, result: Any) -> None:
        files = self.iter_export_files()
        self._ensure_source(
            session,
            source_type="chatgpt",
            source_id=self.repo_name,
            path=str(self.dir_path),
            metadata={
                "file_count": len(files),
                "indexed_at": utcnow().isoformat(),
            },
        )
        for error in getattr(self, "errors", []):
            result.errors.append(f"chatgpt export: {error}")

    def _persist_artifact(self, session: Any, artifact: RawArtifact,
                          result: Any) -> None:
        meta = artifact.metadata
        self._ensure_document(
            session,
            source_id=artifact.source_id,
            file_path=artifact.path,
            file_hash=str(meta.get("sha256", "")),
            size_bytes=int(meta.get("size_bytes", 0)),
            doc_type="chatgpt",
            title=str(meta.get("title", "untitled-conversation")),
            section_tree=None,
        )
        result.documents_created += 1
