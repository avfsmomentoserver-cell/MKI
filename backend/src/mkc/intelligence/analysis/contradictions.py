"""Rule-based contradiction detection between knowledge objects (deterministic, bounded).

Design gate T-D1 (DoS): candidate generation is O(N + C), **never** O(N^2).

- An inverted index maps each (entity, keyword) mention to the objects that
  mention it (mentions are derived the same way ``parsing.relationships``
  does — from the persisted claim text, not from a stored object-entity join).
- Only pairs of claim-like objects (``fact`` / ``claim`` / ``hypothesis`` /
  ``decision`` / ``observation`` / ``theory`` / ``experiment`` / ``insight``)
  that share at least one mention are candidates.
- Per object: at most :data:`PER_OBJECT_CANDIDATE_CAP` candidates (top by
  overlap count, then by id) and at most :data:`MAX_MENTIONS_PER_OBJECT`
  distinct mentions are indexed (so a single mega-mention cannot fan out).
- Per run: a hard :data:`PAIR_BUDGET` cap on scored pairs with a
  deterministic ordering (mention, then candidate ids); when the budget is
  exhausted the run **logs a warning** and sets ``truncated=True``.

Scoring (lexical only, no external calls):
- opposition signals: negation patterns (per claim) and antonym pairs
  present on both sides;
- overlap: the Jaccard coefficient of claim-token sets.

Severity: ``high`` = opposition signal + Jaccard >= HIGH_JACCARD;
``medium`` = opposition signal or Jaccard >= MEDIUM_JACCARD; otherwise
``low``.

Persistence (idempotent): a re-run of the same corpus never duplicates an
edge. The deterministic dedup key is the unordered claim-id pair; rows are
keyed by (min claim id, max claim id) and refreshed in place (severity /
explanation may drift with the corpus). The model has no unique constraint
and no ``confidence`` column, so confidence travels in the ``explanation``
text (``confidence=0.xx;``) and dedup is enforced here.

Knowledge-integrity rule: contradictions are always created ``flagged`` and
are never auto-resolved; they never touch ``lifecycle_state`` (which is
human-gated anyway).
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from mkc.intelligence.parsing.extractor import KnowledgeExtractor

logger = logging.getLogger("mkc.analysis.contradictions")

#: Per-object candidate cap (T-D1): top-N by overlap, then id.
PER_OBJECT_CANDIDATE_CAP = 50
#: Per-run hard budget of scored pairs (T-D1).
PAIR_BUDGET = 20_000
#: Distinct mentions indexed per object (bounds the inverted-index fan-out).
MAX_MENTIONS_PER_OBJECT = 12
#: Minimum shared claim tokens for a candidate pair to be scored.
MIN_SHARED_TOKENS = 3
#: Above this many members a mention is a "mega-hub" and is not indexed.
MAX_MENTION_GROUP_SIZE = 64

HIGH_JACCARD = 0.60
MEDIUM_JACCARD = 0.35

#: Claim-like object types eligible for contradiction scanning.
CLAIM_TYPES: frozenset[str] = frozenset(
    {"fact", "claim", "hypothesis", "decision", "observation", "theory", "experiment", "insight"}
)

#: Negation patterns (per claim) that mark an opposing stance.
_NEGATION_PATTERNS: tuple[str, ...] = (
    "does not", "do not", "don't", "isn't", "won't", "cannot", "can't",
    "will not", "never ", "no longer", "isn't the case", "false",
    "incorrect", "wrong", "disagrees", "refutes", "rejects", "impossible",
    "failed to", "not the", " is not", " are not", " not ",
)

#: Antonym pairs: presence on both sides is a strong opposition signal.
_ANTONYM_PAIRS: tuple[tuple[str, str], ...] = (
    ("fast", "slow"), ("faster", "slower"),
    ("increase", "decrease"), ("increases", "decreases"),
    ("increased", "decreased"),
    ("higher", "lower"), ("higher", "smaller"),
    ("better", "worse"), ("more", "less"),
    ("larger", "smaller"), ("stronger", "weaker"),
    ("enables", "disables"), ("enabled", "disabled"),
)

_WORD_RE = re.compile(r"[a-z0-9]+")
#: Tokens too short or too common to count toward opposition overlap.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
        "can", "could", "did", "does", "do", "for", "from", "had", "has",
        "have", "he", "her", "his", "how", "i", "in", "into", "is", "it",
        "its", "just", "like", "make", "many", "may", "must", "no", "now",
        "not", "of", "on", "or", "other", "our", "out", "over", "per",
        "said", "see", "she", "should", "so", "some", "such", "than",
        "the", "their", "them", "then", "there", "these", "they", "this",
        "that", "to", "two", "up", "use", "used", "using", "via", "was",
        "way", "we", "were", "what", "when", "where", "which", "while",
        "who", "whom", "will", "with", "would", "you", "your",
    }
)


def _claim_tokens(text: str) -> set[str]:
    """Content tokens of a claim (stopwords removed, deduped)."""
    return {
        token
        for token in _WORD_RE.findall((text or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _has_negation(text: str) -> bool:
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in _NEGATION_PATTERNS)


def _opposite_present(a_tokens: set[str], b_tokens: set[str]) -> bool:
    for x, y in _ANTONYM_PAIRS:
        if (x in a_tokens and y in b_tokens) or (x in b_tokens and y in a_tokens):
            return True
    return False


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _claim_text(obj: Any) -> str:
    """Claim text = title + content_summary + body (deterministic order)."""
    return " ".join(
        part
        for part in (
            str(getattr(obj, "title", "") or ""),
            str(getattr(obj, "content_summary", "") or ""),
            str(getattr(obj, "body", "") or ""),
        )
        if part
    )


def _derive_mentions(obj: Any) -> set[str]:
    """Mention keys for the inverted index (same rules as relationships)."""
    body = str(getattr(obj, "body", "") or "")
    if not body:
        return set()
    prov = getattr(obj, "provenance", None) or {}
    location = str(prov.get("source_location", ""))
    file_path = location.split("#", 1)[0] if location else ""
    doc_type = str(prov.get("source_type", ""))
    is_code = doc_type in {"git", "code"} or file_path.endswith(
        (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java")
    )
    if is_code:
        mentions = {name.lower() for name, _kind in KnowledgeExtractor._code_definitions(body, file_path)}
    else:
        mentions = {name.lower() for name, _kind in KnowledgeExtractor._text_entities(body)}
    return {m for m in mentions if m}


def _candidate_pairs(
    objects: list[Any],
    mentions_by_id: dict[str, list[str]],
    tokens_by_id: dict[str, set[str]],
) -> tuple[list[tuple[str, str, int]], bool]:
    """Budgeted candidate generation via the inverted mention index.

    Returns ``(pairs, truncated)`` where each pair is
    ``(a_id, b_id, shared_mentions)`` with ``a_id < b_id``; deterministic
    ordering (by candidate pair, then overlap). ``truncated`` is True when a
    per-object cap dropped candidates.
    """
    # mention -> [object ids] (inverted index)
    mention_index: dict[str, list[str]] = {}
    for obj in objects:
        obj_id = str(getattr(obj, "id", ""))
        for mention in mentions_by_id.get(obj_id, ()):
            mention_index.setdefault(mention, []).append(obj_id)
    # pairwise overlap count = number of shared mentions
    scores: dict[tuple[str, str], int] = {}
    for mention, members in mention_index.items():
        members = sorted(set(members))
        if len(members) < 2 or len(members) > MAX_MENTION_GROUP_SIZE:
            # a "mega-hub" mention (e.g. a very common word) cannot pair
            # reliably; skipping it keeps fan-out bounded (T-D1)
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                scores[(members[i], members[j])] = scores.get((members[i], members[j]), 0) + 1
    # per-object cap: keep the top PER_OBJECT_CANDIDATE_CAP neighbours by
    # (overlap desc, id asc); a pair survives if it is among the top-N of
    # either endpoint (both directions are considered below)
    keep: dict[tuple[str, str], int] = {}
    truncated = False
    for obj_id in sorted(mentions_by_id):
        neighbours = [
            (other, overlap)
            for (a, b), overlap in scores.items()
            if a == obj_id or b == obj_id
            for other in (b if a == obj_id else a)
        ]
        neighbours = sorted(neighbours, key=lambda item: (-item[1], item[0]))
        if len(neighbours) > PER_OBJECT_CANDIDATE_CAP:
            truncated = True
        for other, overlap in neighbours[:PER_OBJECT_CANDIDATE_CAP]:
            key = (obj_id, other) if obj_id < other else (other, obj_id)
            keep[key] = max(keep.get(key, 0), overlap)
    out = [(a, b, ov) for (a, b), ov in sorted(keep.items())]
    # token-overlap prefilter: require a minimum shared claim-token count
    filtered = [
        (a, b, ov)
        for a, b, ov in out
        if len(tokens_by_id.get(a, set()) & tokens_by_id.get(b, set())) >= MIN_SHARED_TOKENS
    ]
    return filtered, truncated


@dataclass
class ScanResult:
    """Summary of one contradiction scan run."""

    objects_scanned: int = 0
    candidate_pairs: int = 0
    pairs_scored: int = 0
    contradictions_created: int = 0
    contradictions_updated: int = 0
    truncated: bool = False
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "objects_scanned": self.objects_scanned,
            "candidate_pairs": self.candidate_pairs,
            "pairs_scored": self.pairs_scored,
            "contradictions_created": self.contradictions_created,
            "contradictions_updated": self.contradictions_updated,
            "truncated": self.truncated,
            "errors": list(self.errors),
        }


def contradiction_id(claim_a_id: str, claim_b_id: str) -> uuid.UUID:
    """Deterministic contradiction id for an unordered claim-id pair."""
    a, b = sorted((claim_a_id, claim_b_id))
    return uuid.uuid5(uuid.NAMESPACE_URL, f"mkc.contradiction|{a}|{b}")


def _load_existing_pairs(session: Any) -> dict[tuple[str, str], Any]:
    """Map (min claim id, max claim id) -> Contradiction row (all rows)."""
    from mkc.models import Contradiction

    mapping: dict[tuple[str, str], Any] = {}
    try:
        for row in session.execute(Contradiction.select()).scalars().all():
            a = str(getattr(row, "claim_a_id", ""))
            b = str(getattr(row, "claim_b_id", ""))
            if a and b:
                mapping[tuple(sorted((a, b)))] = row
    except Exception as exc:
        logger.warning("failed loading existing contradictions: %s", exc)
    return mapping


class ContradictionDetector:
    """Budgeted, deterministic contradiction scanner (T-D1 compliant)."""

    def run(self, session: Any) -> ScanResult:
        """Scan the corpus for opposing claims; upsert flagged Contradictions.

        Does not commit (the caller owns the transaction boundary).
        Idempotent: re-runs refresh the same deterministic rows instead of
        duplicating them.
        """
        from mkc.models import Contradiction, KnowledgeObject

        result = ScanResult()
        try:
            objects = (
                session.execute(
                    KnowledgeObject.select().where(KnowledgeObject.status == "active")
                )
                .scalars()
                .all()
            )
        except Exception as exc:
            result.errors.append(f"load failed: {type(exc).__name__}: {exc}")
            logger.exception("contradiction scan: object load failed")
            return result

        claims = [
            obj
            for obj in objects
            if str(getattr(obj, "type", "")) in CLAIM_TYPES
            and str(getattr(obj, "status", "active")) == "active"
        ]
        result.objects_scanned = len(claims)
        if not claims:
            return result

        mentions_by_id: dict[str, list[str]] = {}
        tokens_by_id: dict[str, set[str]] = {}
        for obj in claims:
            obj_id = str(getattr(obj, "id", ""))
            mentions_by_id[obj_id] = sorted(_derive_mentions(obj))[:MAX_MENTIONS_PER_OBJECT]
            tokens_by_id[obj_id] = _claim_tokens(_claim_text(obj))

        pairs, truncated = _candidate_pairs(claims, mentions_by_id, tokens_by_id)
        result.candidate_pairs = len(pairs)
        result.truncated = truncated
        if truncated:
            logger.warning(
                "contradiction scan truncated: per-object candidate cap (%d) exceeded; "
                "some mention neighbours were dropped",
                PER_OBJECT_CANDIDATE_CAP,
            )

        existing = _load_existing_pairs(session)
        by_id = {str(getattr(o, "id", "")): o for o in claims}
        budget_left = PAIR_BUDGET
        for a_id, b_id, _overlap in pairs:
            if budget_left <= 0:
                result.truncated = True
                logger.warning(
                    "contradiction scan pair budget (%d) exhausted; "
                    "%d candidate pairs not scored",
                    PAIR_BUDGET,
                    len(pairs) - result.pairs_scored,
                )
                break
            a, b = by_id[a_id], by_id[b_id]
            a_tokens, b_tokens = tokens_by_id[a_id], tokens_by_id[b_id]
            text_a, text_b = _claim_text(a), _claim_text(b)
            jaccard = _jaccard(a_tokens, b_tokens)
            negation = _has_negation(text_a) != _has_negation(text_b)
            antonym = _opposite_present(a_tokens, b_tokens)
            result.pairs_scored += 1
            budget_left -= 1
            if not (negation or antonym or jaccard >= MEDIUM_JACCARD):
                continue
            if jaccard >= HIGH_JACCARD and (negation or antonym):
                severity = "high"
            elif negation or antonym or jaccard >= MEDIUM_JACCARD:
                severity = "medium"
            else:
                severity = "low"
            confidence = round(
                min(1.0, 0.30 + 0.4 * jaccard + (0.20 if negation else 0.0) + (0.15 if antonym else 0.0)),
                2,
            )
            shared = sorted(a_tokens & b_tokens)[:8]
            explanation = (
                f"Opposing claims detected (severity={severity}, confidence={confidence:.2f}). "
                f"Overlap: Jaccard={jaccard:.2f}, negation_differs={negation}, "
                f"antonym={antonym}, shared={shared or 'n/a'}. "
                f"Claim A ({a_id}): {text_a[:160]!r}. "
                f"Claim B ({b_id}): {text_b[:160]!r}."
            )
            key = (a_id, b_id)  # already sorted (min, max)
            row = existing.get(key)
            if row is not None:
                if str(getattr(row, "severity", "")) != severity:
                    row.severity = severity  # type: ignore[attr-defined]
                row.explanation = explanation  # type: ignore[attr-defined]
                row.status = "flagged"  # type: ignore[attr-defined]
                result.contradictions_updated += 1
            else:
                session.add(
                    Contradiction(
                        id=contradiction_id(a_id, b_id),
                        claim_a_id=a_id,
                        claim_b_id=b_id,
                        severity=severity,
                        status="flagged",
                        explanation=explanation,
                    )
                )
                result.contradictions_created += 1
                existing[key] = None
        return result

    def scan(self, session: Any) -> ScanResult:
        """Alias for :meth:`run` (readability at call sites)."""
        return self.run(session)
