"""Rule-based knowledge extraction (deterministic, offline, no LLM calls).

:class:`KnowledgeExtractor` turns raw document text into
``KnowledgeObject`` rows with **immutable provenance**:

- documents are chunked on section boundaries (max ~2000 chars per chunk);
- each chunk is classified by weighted keyword rules into one of:
  ``decision`` | ``hypothesis`` | ``experiment`` | ``question`` |
  ``observation`` | ``module`` (code files) | ``fact`` (default);
- the ``lifecycle_state`` follows the classification with a hard
  extraction cap: raw text never produces states above ``hypothesis``
  (hypothesis/decision/experiment/observation markers all cap at
  ``hypothesis``; questions at ``question``; facts at ``idea``).  Only
  code files (existence of the code is itself the evidence) are created
  as ``implemented`` modules;
- every object carries a provenance dict
  ``{source_type, source_id, source_location, original_text,
  extraction_method, author, file_hash}``;
- ``confidence`` is 0.3-0.8 based on how many rule signals matched.

Objects are stored with a **deterministic id** derived from
``(source_id, file_path, section, chunk_hash, type)`` so re-running the
extractor never duplicates rows.  When a source file changes (hash
differs), only the extractor's own previously auto-generated rows for
that file are replaced.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from mkc.intelligence.ingest.base import EXTRACTION_METHOD, slugify_text

logger = logging.getLogger("mkc.parsing.extractor")

# T-D1: Simple secret pattern detection (not exhaustive, basic safety net)
_SECRET_PATTERNS = [
    r'(?i)(?:api[_-]?key|apikey|secret|token|password|passwd|pwd)[\s=:]+[\'"]?[a-zA-Z0-9_\-]{20,}[\'"]?',
    r'(?i)ghp_[a-zA-Z0-9]{36}',  # GitHub PAT
    r'(?i)gho_[a-zA-Z0-9]{36}',  # GitHub OAuth
    r'(?i)ghu_[a-zA-Z0-9]{36}',  # GitHub user token
    r'(?i)ghs_[a-zA-Z0-9]{36}',  # GitHub server token
    r'(?i)ghr_[a-zA-Z0-9]{36}',  # GitHub refresh token
    r'(?i)sk_[a-zA-Z0-9]{32,}',  # Stripe secret key
    r'(?i)pk_[a-zA-Z0-9]{32,}',  # Stripe publishable key
    r'(?i)AKIA[0-9A-Z]{16}',  # AWS access key
]

def _mask_secrets(text: str) -> str:
    """Replace detected secret patterns with placeholders (T-D1)."""
    masked = text
    for pattern in _SECRET_PATTERNS:
        if re.search(pattern, masked):
            masked = re.sub(pattern, '[SECRET_REDACTED]', masked, flags=re.IGNORECASE)
            logger.warning("Secret pattern detected and masked in extracted text")
    return masked

CHUNK_MAX_CHARS = 2000
MIN_CHUNK_CHARS = 40
CONFIDENCE_BASE = 0.30
CONFIDENCE_PER_SIGNAL = 0.10
CONFIDENCE_MAX = 0.80

_DECISION_MARKERS = (
    "decided to", "we will use", "we're going to use", "we are going to use",
    "decision:", "chosen solution", "final decision", "we have decided",
    "going forward, we", "the decision is", "we decided",
)
_HYPOTHESIS_MARKERS = (
    "hypothesis", "hypothesize", "i think", "maybe ", "possibly",
    "conjecture", "i believe", "it seems that", "speculation",
    "could it be", "we suspect",
)
_EXPERIMENT_MARKERS = (
    "experiment", "we tested", "tested on", "baseline", "sample size",
    "statistical", "a/b test", "ab-test", "control group",
    "measured against", "benchmark run", "trial run",
)
_OBSERVATION_MARKERS = (
    "observed", "measured", "result shows", "results show", "in practice",
    "empirically", "profiling shows", "we saw that", "the data shows",
)

_CODE_LANGUAGES = {"code", "test"}


@dataclass
class ExtractedObject:
    """An in-memory knowledge object ready for persistence."""

    obj_type: str
    title: str
    content_summary: str
    body: str
    lifecycle_state: str
    confidence: float
    provenance: dict[str, Any] = field(default_factory=dict)
    entities: list[tuple[str, str]] = field(default_factory=list)

    def stable_id(self) -> str:
        """Deterministic 32-hex id from provenance + classification.

        The id is scoped to the source (via source_id UUID) to prevent
        cross-source collisions when different repos have identical content
        at the same path. Includes a source-specific salt to ensure
        deterministic uniqueness per source.
        
        Returns a UUID-formatted string (32 hex chars with hyphens) for database compatibility.
        """
        # Use source_id as a salt to ensure cross-source uniqueness
        source_id = str(self.provenance.get("source_id", ""))
        basis = "|".join([
            source_id,  # Source UUID as salt
            str(self.provenance.get("source_location", "")),
            self.obj_type,
            str(self.provenance.get("chunk_hash", "")),
        ])
        hex_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]
        # Convert to UUID format: 8-4-4-4-12
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"


@dataclass
class ExtractionResult:
    """Summary of one extractor run."""

    documents_processed: int = 0
    chunks_analyzed: int = 0
    objects_created: int = 0
    objects_replaced: int = 0
    entities_created: int = 0
    errors: list[str] = field(default_factory=list)


def chunk_text(text: str) -> list[tuple[str, str]]:
    """Split text into ``(section, chunk)`` pairs of at most ~2000 chars.

    Section boundaries are markdown headings; within a section long
    paragraphs are cut at the 2000 char budget (sentence/newline aware).
    """
    sections: list[tuple[str, list[str]]] = []
    current_name = "introduction"
    current_lines: list[str] = []
    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            if current_lines:
                sections.append((current_name, current_lines))
            current_name = heading.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_name, current_lines))

    chunks: list[tuple[str, str]] = []
    for name, lines in sections:
        buffer = ""
        for line in lines:
            candidate = f"{buffer}\n{line}" if buffer else line
            if len(candidate) > CHUNK_MAX_CHARS and buffer:
                chunks.append((name, buffer.strip()))
                buffer = line
            else:
                buffer = candidate
        if buffer.strip():
            chunks.append((name, buffer.strip()))
    return [(name, chunk) for name, chunk in chunks if len(chunk) >= MIN_CHUNK_CHARS]


def _match_count(text: str, markers: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for marker in markers if marker in lowered)


def classify_chunk(chunk: str, doc_type: str,
                   file_path: str = "") -> tuple[str, str, int]:
    """Classify a chunk -> (type, lifecycle_state, signal_count).

    Priority: question (terminal ``?``) wins when the chunk is short;
    otherwise the marker family with the most hits wins.  Code files
    classify as ``module`` (one object per definition, handled by the
    caller which picks the dominant definition).

    Lifecycle cap (KNOWLEDGE_MODEL human-gate): auto-extracted prose
    never enters a human-only state (``validated`` / ``implemented`` /
    ``production``). Decision-marker chunks therefore cap at
    ``hypothesis`` — a textual "we decided" is an unverified claim, not a
    validated fact; promotion happens via the audited state machine. The
    sole documented exception is code: an existing ``module`` definition
    is itself the evidence, so code chunks are created as
    ``implemented``.
    """
    if doc_type in _CODE_LANGUAGES:
        return "module", "implemented", 2
    stripped = chunk.strip()
    if stripped.endswith("?") and len(stripped) <= 400:
        return "question", "question", 1
    decision = _match_count(chunk, _DECISION_MARKERS)
    experiment = _match_count(chunk, _EXPERIMENT_MARKERS)
    observation = _match_count(chunk, _OBSERVATION_MARKERS)
    hypothesis = _match_count(chunk, _HYPOTHESIS_MARKERS)
    scored = sorted(
        (("decision", decision, "hypothesis"),
         ("experiment", experiment, "experiment"),
         ("observation", observation, "observed"),
         ("hypothesis", hypothesis, "hypothesis")),
        key=lambda item: item[1], reverse=True,
    )
    winner_type, winner_score, winner_state = scored[0]
    if winner_score > 0:
        return winner_type, winner_state, winner_score
    return "fact", "idea", 0


class KnowledgeExtractor:
    """Rule-based extractor over Documents (pure rules; no network/LLM)."""

    # ------------------------------------------------------------- pure API

    @staticmethod
    def _code_definitions(chunk: str, file_path: str) -> list[tuple[str, str]]:
        """(name, kind) for classes/functions/consts in a code chunk."""
        found: list[tuple[str, str]] = []
        seen: set[str] = set()
        for pattern, kind in (
            (r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", "module"),
            (r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)", "module"),
            (r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", "module"),
            (r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", "module"),
        ):
            for match in re.finditer(pattern, chunk, re.MULTILINE):
                name = match.group(1)
                if name not in seen:
                    seen.add(name)
                    found.append((name, kind))
        if not found:
            stem = Path(file_path).stem
            if stem and stem not in {"__init__", "index", "main"}:
                found.append((stem, "module"))
        return found[:8]

    @staticmethod
    def _text_entities(chunk: str) -> list[tuple[str, str]]:
        """Conservative entity mention extraction from prose.

        - ``<Name> engine`` / ``<name> engine`` -> engine
        - ``<name> metric`` / ``<x> rate|accuracy|precision|recall`` -> metric
        - ``theory of <name>`` / ``<name> theory`` -> theory
        - Capitalized multi-word phrases (2-6 words) -> concept
        """
        entities: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add(name: str, kind: str) -> None:
            clean = re.sub(r"\s+", " ", name).strip()
            if 2 <= len(clean) <= 80 and (clean.lower(), kind) not in seen:
                seen.add((clean.lower(), kind))
                entities.append((clean, kind))

        for match in re.finditer(r"\b([A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,5})\s+engine\b", chunk):
            add(match.group(1), "engine")
        for match in re.finditer(r"\b([A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,4})\s+(?:metric|rate|score)\b", chunk):
            add(match.group(1), "metric")
        for match in re.finditer(r"\btheory\s+of\s+([a-z][\w\-]*(?:\s+[a-z][\w\-]*){0,4})\b", chunk):
            add(match.group(1), "theory")
        for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5})\b", chunk):
            phrase = match.group(1)
            words = phrase.split()
            if 2 <= len(words) <= 6:
                add(phrase, "concept")
        return entities[:8]

    @staticmethod
    def _title_for(obj_type: str, chunk: str, file_path: str) -> str:
        first_line = next(
            (line.strip() for line in chunk.splitlines() if line.strip()),
            chunk.strip(),
        )
        first_line = re.sub(r"^#+\s*", "", first_line)
        return first_line[:120]

    @staticmethod
    def _summary_for(chunk: str) -> str:
        text = re.sub(r"\s+", " ", chunk.strip())
        return text[:400]

    def extract_text(self, text: str, *, source_type: str, source_id: str,
                     file_path: str, doc_type: str, author: str = "unknown",
                     file_hash: str = "") -> list[ExtractedObject]:
        """Classify and extract from raw text (pure; no database access)."""
        objects: list[ExtractedObject] = []
        # Ensure source_id is a string for consistent handling
        source_id_str = str(source_id)
        # T-D1: Mask secrets in the raw text before processing
        masked_text = _mask_secrets(text)
        for section, chunk in chunk_text(masked_text):
            obj_type, lifecycle, signals = classify_chunk(chunk, doc_type, file_path)
            confidence = min(CONFIDENCE_MAX,
                             CONFIDENCE_BASE + CONFIDENCE_PER_SIGNAL * max(signals, 1))
            if obj_type == "module" and doc_type in _CODE_LANGUAGES:
                definitions = self._code_definitions(chunk, file_path)
                for name, kind in definitions:
                    chunk_hash = hashlib.sha256(
                        f"{file_path}|{section}|{name}|{chunk[:200]}".encode("utf-8")
                    ).hexdigest()[:16]
                    objects.append(ExtractedObject(
                        obj_type="module",
                        title=name,
                        content_summary=(
                            f"{doc_type} definition {name!r} in {file_path} "
                            f"(section: {section})."
                        ),
                        body=chunk[:2000],
                        lifecycle_state="implemented",
                        confidence=0.7,
                        provenance={
                            "source_type": source_type,
                            "source_id": source_id_str,
                            "source_location": f"{file_path}#{section}::{name}",
                            "original_text": chunk[:2000],
                            "extraction_method": EXTRACTION_METHOD,
                            "author": author,
                            "file_hash": file_hash,
                            "chunk_hash": chunk_hash,
                        },
                        entities=[(name, "module")],
                    ))
                continue
            chunk_hash = hashlib.sha256(
                f"{file_path}|{section}|{chunk[:500]}".encode("utf-8")
            ).hexdigest()[:16]
            entities = (self._code_definitions(chunk, file_path)
                        if doc_type in _CODE_LANGUAGES
                        else self._text_entities(chunk))
            objects.append(ExtractedObject(
                obj_type=obj_type,
                title=self._title_for(obj_type, chunk, file_path),
                content_summary=self._summary_for(chunk),
                body=chunk[:2000],
                lifecycle_state=lifecycle,
                confidence=confidence,
                provenance={
                    "source_type": source_type,
                    "source_id": source_id_str,
                    "source_location": f"{file_path}#{section}",
                    "original_text": chunk[:2000],
                    "extraction_method": EXTRACTION_METHOD,
                    "author": author,
                    "file_hash": file_hash,
                    "chunk_hash": chunk_hash,
                },
                entities=entities,
            ))
        return objects

    # ------------------------------------------------------------- DB API

    def _author_map(self, session: Any) -> dict[str, str]:
        """repo name -> git author of the last commit (from Source rows)."""
        from mkc.intelligence.db_compat import get_model, model_query
        try:
            source_model = get_model("Source")
            rows = session.execute(model_query(source_model)).scalars().all()
        except Exception:
            return {}
        authors: dict[str, str] = {}
        for row in rows:
            if getattr(row, "source_type", None) != "git":
                continue
            metadata = getattr(row, "metadata_json", None) or {}
            last_commit = metadata.get("last_commit") or {}
            author = last_commit.get("author") if isinstance(last_commit, dict) else None
            if author:
                # Documents carry the Source PK (UUID) in their source_id
                # column, so the lookup must be keyed by the row id.
                authors[str(getattr(row, "id", ""))] = str(author)
        return authors

    def _source_path_map(self, session: Any) -> dict[str, tuple[str, str]]:
        """source_id -> (path, source_type) for on-disk content resolution."""
        from mkc.intelligence.db_compat import get_model, model_query
        try:
            source_model = get_model("Source")
            rows = session.execute(model_query(source_model)).scalars().all()
        except Exception:
            return {}
        # Documents carry the Source PK (UUID) in their source_id column,
        # so the lookup must be keyed by the row id.
        return {
            str(getattr(row, "id", "")): (
                str(getattr(row, "path", "") or ""),
                str(getattr(row, "source_type", "") or ""),
            )
            for row in rows
        }

    @staticmethod
    def _load_document_text(document: Any, paths: dict[str, tuple[str, str]]) -> Optional[str]:
        """Read a document's text from disk when it was not inlined."""
        source_id = str(getattr(document, "source_id", ""))
        file_path = str(getattr(document, "file_path", ""))
        entry = paths.get(source_id)
        if entry is None:
            return None
        base, source_type = entry
        if not base:
            return None
        if source_type == "chatgpt":
            # conversation docs: file_path = "<file.json>#<conv_id>";
            # content is inlined at import time, so there is nothing on disk.
            return None
        candidate = Path(base) / file_path
        if not candidate.is_file():
            return None
        try:
            return candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def run(self, session: Any, limit: Optional[int] = None, source_id: Optional[str] = None) -> ExtractionResult:
        """Extract knowledge from all eligible Documents in *session*.

        Idempotent: objects carry deterministic ids; superseded
        auto-generated rows (same file, stale hash) are replaced.
        
        Args:
            session: Database session
            limit: Optional limit on number of documents to process
            source_id: Optional source UUID to filter documents (prevents cross-source extraction)
        """
        from mkc.intelligence.db_compat import get_model, model_query

        result = ExtractionResult()
        doc_model = get_model("Document")
        ko_model = get_model("KnowledgeObject")
        entity_model = get_model("Entity")

        docs = session.execute(model_query(doc_model)).scalars().all()
        docs = [d for d in docs
                if str(getattr(d, "doc_type", "")) in
                {"markdown", "code", "test", "chatgpt", "text"}]
        
        # Filter by source_id if provided to prevent cross-source extraction
        if source_id is not None:
            docs = [d for d in docs if str(getattr(d, "source_id", "")) == str(source_id)]
        
        if limit is not None:
            docs = docs[:limit]

        authors = self._author_map(session)
        paths = self._source_path_map(session)

        existing_by_location: dict[tuple[str, str], list[Any]] = {}
        for row in session.execute(model_query(ko_model)).scalars().all():
            prov = getattr(row, "provenance", None) or {}
            if prov.get("extraction_method") != EXTRACTION_METHOD:
                continue
            location = str(prov.get("source_location", ""))
            # Key by (source_id, location) to prevent cross-source collisions
            row_source_id = str(prov.get("source_id", ""))
            existing_by_location.setdefault((row_source_id, location), []).append(row)

        entities_seen: set[tuple[str, str]] = set()
        for row in session.execute(model_query(entity_model)).scalars().all():
            entities_seen.add(
                (str(getattr(row, "name", "")).lower(), str(getattr(row, "kind", "")))
            )

        for document in docs:
            file_path = str(getattr(document, "file_path", ""))
            file_hash = str(getattr(document, "file_hash", ""))
            doc_type = str(getattr(document, "doc_type", ""))
            source_id = str(getattr(document, "source_id", ""))
            existing_ids: set[str] = set()  # Initialize before try block to avoid NameError
            try:
                text = getattr(document, "content", None) or self._load_document_text(
                    document, paths
                )
                if text is None or not text.strip():
                    continue
                result.documents_processed += 1
                source_type = paths.get(source_id, ("", "unknown"))[1] or "unknown"
                author = authors.get(source_id, "unknown")

                stale: list[Any] = []
                fresh: list[Any] = []
                for (existing_source_id, location), rows in existing_by_location.items():
                    # Only consider KOs from the same source
                    if existing_source_id != str(source_id):
                        continue
                    if location.startswith(file_path + "#"):
                        for row in rows:
                            prov = getattr(row, "provenance", None) or {}
                            (fresh if prov.get("file_hash") == file_hash else stale).append(row)
                for row in stale:
                    session.delete(row)
                    result.objects_replaced += 1

                existing_ids = {
                    str(getattr(r, "id", "")) for r in fresh
                }
                author_for_doc = author
                objects = self.extract_text(
                    text,
                    source_type=source_type,
                    source_id=str(source_id),
                    file_path=file_path,
                    doc_type=doc_type,
                    author=author_for_doc,
                    file_hash=file_hash,
                )
                for extracted in objects:
                    result.chunks_analyzed += 1
                    if extracted.stable_id() in existing_ids:
                        continue
                    values = {
                        "id": extracted.stable_id(),
                        "type": extracted.obj_type,
                        "title": extracted.title,
                        "content_summary": extracted.content_summary,
                        "body": extracted.body,
                        "lifecycle_state": extracted.lifecycle_state,
                        "confidence": extracted.confidence,
                        "source_id": source_id,
                        "provenance": extracted.provenance,
                        "status": "active",
                    }
                    row = ko_model(**values)  # type: ignore[call-arg]
                    session.add(row)
                    result.objects_created += 1
                    for name, kind in extracted.entities:
                        key = (name.lower(), kind)
                        if key in entities_seen:
                            continue
                        entities_seen.add(key)
                        session.add(entity_model(
                            id=hashlib.sha256(
                                f"{name.lower()}|{kind}".encode("utf-8")
                            ).hexdigest()[:32],
                            name=name,
                            kind=kind,
                            attributes_json={"origin": "rule-based-v1"},
                        ))
                        result.entities_created += 1
                    existing_ids.add(extracted.stable_id())
            except Exception as exc:
                result.errors.append(f"{file_path}: {type(exc).__name__}: {exc}")
        return result
