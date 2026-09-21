"""Rule-based insight generation (deterministic, bounded, evidence-backed).

Four generators:

- (a) **pattern**: recurring theme across objects sharing an entity
  (mention count >= :data:`PATTERN_MIN_COUNT`); one insight per entity.
- (b) **gap**: high-mention entity with no linked research item;
  one insight per entity.
- (c) **unvalidated**: high-confidence objects stuck in pre-validation
  states; one insight summarising the stuck set (bucket-level identity).
- (d) **contradiction-summary**: open ``flagged`` contradictions grouped
  by area; one insight per area.

Invariants (knowledge-integrity rule):
- every insight carries non-empty ``supporting_evidence`` (object IDs) —
  generators that cannot produce evidence emit nothing (no evidenceless
  insights);
- every insight is created ``status="needs_review"`` — auto-generated
  insights never reach validated/implemented/production (human-only gate);
- idempotent: the insight id is a deterministic
  ``uuid5(MKC_INSIGHT_NAMESPACE, "<insight_type>|<semantic_key>")`` where the
  semantic key is the entity name (pattern/gap), ``"bucket"`` (unvalidated)
  or the area (contradiction-summary). Re-running the same corpus updates
  the existing row in place instead of duplicating it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from mkc.intelligence.parsing.extractor import KnowledgeExtractor
from mkc.intelligence.parsing.relationships import _file_of

logger = logging.getLogger("mkc.analysis.insights")

#: UUID namespace for deterministic insight ids.
MKC_INSIGHT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mkc.momento.insights")

#: Minimum objects mentioning an entity to call it a recurring pattern.
PATTERN_MIN_COUNT = 3
#: Minimum objects mentioning an entity to call it "high-mention" (gap).
GAP_MIN_MENTIONS = 3
#: Minimum confidence for an object to count as "stuck" (unvalidated).
UNVALIDATED_MIN_CONFIDENCE = 0.60
#: Cap on evidence ids stored per insight (keeps JSONB rows bounded).
MAX_EVIDENCE_IDS = 64
#: Cap on objects considered per entity mention group (noise filter).
_MAX_GROUP_SIZE = 50


def insight_id(insight_type: str, semantic_key: str) -> uuid.UUID:
    """Deterministic insight id: re-runs of the same corpus are idempotent."""
    return uuid.uuid5(MKC_INSIGHT_NAMESPACE, f"{insight_type}|{semantic_key}")


def _mention_keys(obj: Any) -> set[str]:
    """Entity mentions of one object, consistent with the relationship builder.

    Code objects contribute their definitions; prose objects contribute the
    rule-based text entities (same extraction rules as ``related_to`` edges).
    """
    body = str(getattr(obj, "body", "") or "")
    if not body:
        return set()
    prov = getattr(obj, "provenance", None) or {}
    doc_type = str(prov.get("source_type", ""))
    file_path = _file_of(str(prov.get("source_location", "")))
    is_code = doc_type in {"git", "code"} or file_path.endswith(
        (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java")
    )
    if is_code:
        return {name.lower() for name, _kind in KnowledgeExtractor._code_definitions(body, file_path)}
    return {name.lower() for name, _kind in KnowledgeExtractor._text_entities(body)}


def _evidence_ids(objs: list[Any]) -> list[str]:
    """Sorted, de-duplicated knowledge object ids (bounded)."""
    return sorted({str(getattr(o, "id", "")) for o in objs})[:MAX_EVIDENCE_IDS]


@dataclass
class InsightResult:
    """Summary of one insight-generation run."""

    objects_scanned: int = 0
    created: int = 0
    updated: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "objects_scanned": self.objects_scanned,
            "created": self.created,
            "updated": self.updated,
            "by_type": dict(self.by_type),
            "errors": list(self.errors),
        }


class InsightGenerator:
    """Generates the four insight families (deterministic, bounded)."""

    # ------------------------------------------------------------------ run

    def run(self, session: Any) -> InsightResult:
        """Run all four generators; upsert ``needs_review`` insights.

        Does not commit (the caller owns the transaction boundary).
        """
        from mkc.models import Contradiction, Insight, KnowledgeObject, ResearchItem

        result = InsightResult()
        try:
            objects = list(session.execute(KnowledgeObject.select()).scalars().all())
            open_contradictions = list(
                session.execute(Contradiction.select().where(Contradiction.status == "flagged"))
                .scalars()
                .all()
            )
            research_rows = list(session.execute(ResearchItem.select()).scalars().all())
        except Exception as exc:
            result.errors.append(f"load failed: {type(exc).__name__}: {exc}")
            logger.exception("insight generation load failed")
            return result

        result.objects_scanned = len(objects)
        if not objects:
            return result

        active = [o for o in objects if str(getattr(o, "status", "active")) == "active"]
        objects_by_id = {str(getattr(o, "id", "")): o for o in objects}

        existing_by_id: dict[str, Any] = {}
        for row in session.execute(Insight.select()).scalars().all():
            existing_by_id[str(row.id)] = row

        def upsert(insight_type: str, semantic_key: str, summary: str,
                   evidence: list[str], confidence: float) -> None:
            if not evidence:
                return  # no evidenceless insights
            target_id = insight_id(insight_type, semantic_key)
            row = existing_by_id.get(str(target_id))
            if row is not None:
                row.summary = summary  # type: ignore[attr-defined]
                row.supporting_evidence = evidence  # type: ignore[attr-defined]
                row.knowledge_ids = evidence  # type: ignore[attr-defined]
                row.confidence = confidence  # type: ignore[attr-defined]
                row.status = "needs_review"  # type: ignore[attr-defined]
                result.updated += 1
            else:
                session.add(Insight(
                    id=target_id,
                    knowledge_ids=evidence,
                    insight_type=insight_type,
                    summary=summary,
                    supporting_evidence=evidence,
                    confidence=confidence,
                    status="needs_review",
                ))
                existing_by_id[str(target_id)] = None
                result.created += 1
            result.by_type[insight_type] = result.by_type.get(insight_type, 0) + 1

        # ---------------- (a) pattern + (b) gap: shared-entity mentions -----
        mention_map: dict[str, list[str]] = {}
        for obj in active:
            for name in _mention_keys(obj):
                if 2 <= len(name) <= 80:
                    mention_map.setdefault(name, []).append(str(getattr(obj, "id", "")))

        research_topics_by_object: dict[str, list[str]] = {}
        for item in research_rows:
            k = str(getattr(item, "knowledge_id", ""))
            topic = str(getattr(item, "topic", "") or "").lower()
            title = str(getattr(item, "title", "") or "").lower()
            research_topics_by_object.setdefault(k, []).extend(t for t in (topic, title) if t)

        for name in sorted(mention_map):
            member_ids = sorted({mid for mid in mention_map[name] if mid in objects_by_id})
            if len(member_ids) < PATTERN_MIN_COUNT or len(member_ids) > _MAX_GROUP_SIZE:
                continue
            members = [objects_by_id[mid] for mid in member_ids]
            upsert(
                "pattern",
                name,
                f"Recurring theme: {len(members)} objects reference {name.title()!r} "
                f"(mention count >= {PATTERN_MIN_COUNT}).",
                _evidence_ids(members),
                min(0.4 + 0.05 * len(members), 0.85),
            )

        for name in sorted(mention_map):
            member_ids = sorted({mid for mid in mention_map[name] if mid in objects_by_id})
            if len(member_ids) < GAP_MIN_MENTIONS or len(member_ids) > _MAX_GROUP_SIZE:
                continue
            # gap: no research item linked to a member object mentions the entity
            linked = any(
                any(name in t for t in research_topics_by_object.get(mid, []))
                for mid in member_ids
            )
            if linked:
                continue
            members = [objects_by_id[mid] for mid in member_ids]
            upsert(
                "gap",
                name,
                f"Research gap: {len(members)} objects reference {name.title()!r} but no "
                f"research item covers it (open a research thread or link one).",
                _evidence_ids(members),
                min(0.4 + 0.05 * len(members), 0.8),
            )

        # ---------------- (c) unvalidated: confident objects, pre-validation -
        stuck = sorted(
            (
                obj for obj in active
                if float(getattr(obj, "confidence", 0.0) or 0.0) >= UNVALIDATED_MIN_CONFIDENCE
                and str(getattr(obj, "lifecycle_state", ""))
                in {"idea", "question", "hypothesis", "researching", "experiment", "observed", "validating", "unknown"}
            ),
            key=lambda o: (-float(getattr(o, "confidence", 0.0)), str(getattr(o, "id", ""))),
        )
        if stuck:
            top = stuck[:5]
            upsert(
                "unvalidated",
                "bucket",
                f"{len(stuck)} high-confidence objects (confidence >= {UNVALIDATED_MIN_CONFIDENCE:.2f}) are "
                f"still in pre-validation states: "
                + ", ".join(
                    f"{str(getattr(o, 'title', ''))[:40]} ({getattr(o, 'lifecycle_state', '')})"
                    for o in top
                )
                + ("..." if len(stuck) > 5 else "")
                + ". Push them through validation (human sign-off required).",
                _evidence_ids(stuck),
                min(0.5 + 0.02 * len(stuck), 0.9),
            )

        # ---------------- (d) contradiction-summary: open flags by area -----
        area_map: dict[str, list[Any]] = {}
        for contradiction in open_contradictions:
            a_id = str(getattr(contradiction, "claim_a_id", ""))
            b_id = str(getattr(contradiction, "claim_b_id", ""))
            area_obj = objects_by_id.get(a_id) or objects_by_id.get(b_id)
            area = str(getattr(area_obj, "type", "unknown")) if area_obj is not None else "unknown"
            area_map.setdefault(area, []).append(contradiction)

        for area in sorted(area_map):
            rows = area_map[area]
            evidence = sorted(
                {
                    cid
                    for row in rows
                    for cid in (str(getattr(row, "claim_a_id", "")), str(getattr(row, "claim_b_id", "")))
                    if cid in objects_by_id
                }
            )
            sample = rows[0]
            upsert(
                "contradiction",
                area,
                f"{len(rows)} open flagged contradiction(s) in area '{area}'. "
                f"Sample: {str(getattr(sample, 'claim_a_id', ''))[:8]} vs "
                f"{str(getattr(sample, 'claim_b_id', ''))[:8]}. "
                f"Review required; auto-resolution is disabled.",
                _evidence_ids([objects_by_id[c] for c in evidence]),
                min(0.5 + 0.05 * len(rows), 0.9),
            )
        return result

    def generate(self, session: Any) -> InsightResult:
        """Alias for :meth:`run` (compat with the package-level name)."""
        return self.run(session)
