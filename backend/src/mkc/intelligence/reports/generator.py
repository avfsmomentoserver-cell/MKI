"""Deterministic markdown report generation for the MKC registry.

:func:`generate_report` reads the registry (``Source`` / ``Document`` /
``KnowledgeObject`` / ``Entity`` / ``EntityRelation`` / ``Decision`` /
``Experiment`` / ``ResearchItem`` / ``Contradiction`` rows), renders one of
the three report types as markdown, writes it to
``<output_dir>/<type>-<YYYY-MM-DD>.md`` (same-day re-runs overwrite the
file) and upserts the matching ``Report`` row (keyed by file path, so a
same-day regeneration updates the row instead of duplicating it).

Report types
------------
- ``project-knowledge``: what the registry knows, per source / doc /
  object / entity, plus recent decisions and experiments.
- ``research-gaps``: heavily mentioned entities with no research thread,
  pre-validation claims, contradictions, documentation gaps and stale
  (unknown-state) items.
- ``implementation-plan``: current state per repo, blockers, and
  prioritized next steps each justified by a ``reason:`` line.

Every report carries ``generated_at``, ``generated_by: mkc-reports-v1``,
source DB counts, and the footer
``Auto-generated from MKC registry; verify before acting.``
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from typing import get_args

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mkc.core.config import REPO_ROOT
from mkc.models import (
    Contradiction,
    Decision,
    Document,
    Entity,
    EntityRelation,
    Experiment,
    KnowledgeObject,
    Report,
    ResearchItem,
    Source,
)

logger = logging.getLogger("mkc.reports")

#: Generator version marker written into every report (and the Report row).
GENERATOR_VERSION = "mkc-reports-v1"

#: Default report output directory (workspace ``reports/``).
DEFAULT_REPORT_DIR: Path = REPO_ROOT / "reports"

#: Report kinds this generator knows how to build.
SUPPORTED_REPORT_TYPES: tuple[str, ...] = ("project-knowledge", "research-gaps", "implementation-plan")

ReportType = Literal["project-knowledge", "research-gaps", "implementation-plan"]

#: Knowledge objects in these states count as "pre-validation" for gap reports.
PRE_VALIDATION_STATES: tuple[str, ...] = ("idea", "question", "hypothesis", "researching", "unknown")

#: Knowledge object types that carry an explicit claim for gap analysis.
CLAIM_TYPES: frozenset[str] = frozenset(
    {"hypothesis", "claim", "decision", "observation", "experiment", "question"}
)

#: Cap for list sections so a large registry cannot produce unbounded reports.
_MAX_LIST = 25

#: Capitalized multi-word mentions (the conservative entity-mention signal).
_MENTION_RE = re.compile(r"[A-Z][A-Za-z0-9_\-]*(?: [A-Z][A-Za-z0-9_\-]*){0,3}")

#: Sentence-initial stop words that never count as entity mentions.
_MENTION_STOPWORDS = frozenset({
    "The", "A", "An", "This", "That", "These", "Those", "For", "With", "From",
    "To", "In", "On", "If", "When", "While", "And", "Or", "But", "Not", "No",
    "Yes", "It", "We", "You", "They", "My", "Your", "Our", "Their", "True",
    "False", "None", "Null", "Use", "Used", "Using", "Must", "Should", "Can",
    "Will", "Is", "Are", "Was", "Were", "Be", "By", "At", "As",
})


# --------------------------------------------------------------------------
# query helpers (small tables: one pass each, in Python)
# --------------------------------------------------------------------------


def _count_by(session: Session, model: Any, column: Any) -> dict[str, int]:
    """Group-count a column of *model* into ``{value: count}`` (None -> "unknown")."""
    rows = session.execute(select(column, func.count()).group_by(column)).all()
    return {str(key if key is not None else "unknown"): int(value) for key, value in rows}


def _total(session: Session, model: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _sources_by_type(session: Session) -> dict[str, list[Any]]:
    rows = session.execute(select(Source).order_by(Source.source_type, Source.source_id)).scalars().all()
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(str(row.source_type), []).append(row)
    return grouped


def _db_counts(session: Session) -> dict[str, int]:
    """Registry-wide row counts for the report header."""
    return {
        "sources": _total(session, Source),
        "documents": _total(session, Document),
        "knowledge_objects": _total(session, KnowledgeObject),
        "entities": _total(session, Entity),
        "entity_relations": _total(session, EntityRelation),
        "research_items": _total(session, ResearchItem),
        "decisions": _total(session, Decision),
        "experiments": _total(session, Experiment),
        "contradictions": _total(session, Contradiction),
        "reports": _total(session, Report),
    }


def _counts_section(title: str, counts: dict[str, int]) -> list[str]:
    """Render ``key: count`` lines sorted by count desc, then name."""
    lines = [f"### {title}"]
    if not counts:
        lines.append("_none_")
        return lines
    for key, value in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {key}: {value}")
    return lines


def _mentions_in_object(obj: Any) -> set[str]:
    """Capitalized multi-word mentions from an object's title + body (conservative)."""
    text = f"{getattr(obj, 'title', '') or ''}\n{getattr(obj, 'body', '') or ''}"
    found: set[str] = set()
    for match in _MENTION_RE.finditer(text):
        name = match.group(0).strip(" .,;:()[]{}\"'")
        if 3 <= len(name) <= 60 and name.split()[0] not in _MENTION_STOPWORDS:
            found.add(name)
    return found


def _unresolved_contradictions(session: Session) -> list[Any]:
    return list(
        session.execute(
            select(Contradiction).where(Contradiction.status != "resolved").order_by(Contradiction.id)
        ).scalars().all()
    )


def _active_objects(session: Session) -> list[Any]:
    return list(
        session.execute(select(KnowledgeObject).where(KnowledgeObject.status == "active")).scalars().all()
    )


def _researched_names(session: Session) -> set[str]:
    """Lower-cased names already tracked by a research item (title or topic)."""
    names: set[str] = set()
    for item in session.execute(select(ResearchItem)).scalars().all():
        if item.title:
            names.add(str(item.title).lower())
        if item.topic:
            names.add(str(item.topic).lower())
    return names


def _mention_counts(objects: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obj in objects:
        for name in _mentions_in_object(obj):
            counts[name] = counts.get(name, 0) + 1
    return counts


def _documentation_gap_ids(session: Session) -> set[str]:
    """Code/test Document ids with no incoming ``documents`` edge (no linked doc).

    Endpoints of entity_relations are id strings; a code file is "documented"
    when any markdown/text document has a ``documents`` relation targeting it.
    """
    code_ids: set[str] = set()
    for row in session.execute(
        select(Document).where(Document.doc_type.in_(["code", "test"]))
    ).scalars().all():
        code_ids.add(str(row.id))
    documented: set[str] = set()
    for rel in session.execute(
        select(EntityRelation).where(EntityRelation.rel_type == "documents")
    ).scalars().all():
        documented.add(str(rel.to_id))
    return code_ids - documented


def _top_mentioned_unresearched(
    session: Session, objects: list[Any], min_mentions: int = 1
) -> list[tuple[str, int]]:
    """Entities most often mentioned by active objects, minus researched names."""
    researched = _researched_names(session)
    ranked = sorted(_mention_counts(objects).items(), key=lambda kv: (-kv[1], kv[0]))
    return [(name, count) for name, count in ranked if name.lower() not in researched and count >= min_mentions]


# --------------------------------------------------------------------------
# report builders (each returns the markdown body lines)
# --------------------------------------------------------------------------


def _build_project_knowledge(session: Session, generated_at: datetime) -> list[str]:
    source_types = _sources_by_type(session)
    lines: list[str] = ["## 1. Sources indexed", ""]
    for source_type, rows in sorted(source_types.items()):
        lines.append(f"### {source_type} ({len(rows)})")
        for row in rows:
            indexed = row.indexed_at.isoformat() if row.indexed_at else "unknown"
            lines.append(f"- {row.source_id} — {row.path or '(no path)'} (indexed {indexed})")
        lines.append("")
    if not source_types:
        lines.append("_no sources registered_")
        lines.append("")

    lines += ["## 2. Documents by doc_type", ""]
    lines += _counts_section("doc_type", _count_by(session, Document, Document.doc_type))
    lines += ["", "## 3. Knowledge objects", ""]
    lines += _counts_section("by type", _count_by(session, KnowledgeObject, KnowledgeObject.type))
    lines += [""]
    lines += _counts_section("by lifecycle_state", _count_by(session, KnowledgeObject, KnowledgeObject.lifecycle_state))
    lines += ["", "## 4. Entities by kind", ""]
    lines += _counts_section("kind", _count_by(session, Entity, Entity.kind))
    lines += ["", "## 5. Relationships by type", ""]
    lines += _counts_section("rel_type", _count_by(session, EntityRelation, EntityRelation.rel_type))

    lines += ["", "## 6. Recent decisions (title / rationale)", ""]
    decisions = list(
        session.execute(
            select(Decision).order_by(Decision.decided_at.desc().nulls_last(), Decision.id).limit(_MAX_LIST)
        ).scalars().all()
    )
    if not decisions:
        lines.append("_none recorded_")
    for decision in decisions:
        rationale = (decision.reason or decision.decision_text or "").strip().replace("\n", " ")
        lines.append(f"- **{decision.title}** [{decision.status}] — {rationale[:240]}")

    lines += ["", "## 7. Recent experiments (title / status / conclusion)", ""]
    experiments = list(
        session.execute(select(Experiment).order_by(Experiment.id).limit(_MAX_LIST)).scalars().all()
    )
    if not experiments:
        lines.append("_none recorded_")
    for experiment in experiments:
        conclusion = (experiment.conclusion or experiment.result or "").strip().replace("\n", " ")
        lines.append(f"- **{experiment.title}** [{experiment.status}] — {conclusion[:240]}")
    return lines


def _build_research_gaps(session: Session, generated_at: datetime) -> list[str]:
    objects = _active_objects(session)
    lines: list[str] = []

    top = _top_mentioned_unresearched(session, objects, min_mentions=1)
    lines += ["## 1. Top-mentioned entities with no research object", ""]
    if not top:
        lines.append("_none — every mentioned entity has a research thread (or no entities were mentioned)_")
    for name, count in top[:_MAX_LIST]:
        lines.append(f"- {name} — mentioned in {count} knowledge object(s)")

    pre_by_state = _count_by(session, KnowledgeObject, KnowledgeObject.lifecycle_state)
    pre_validation = [
        obj for obj in objects
        if obj.lifecycle_state in PRE_VALIDATION_STATES and obj.type in CLAIM_TYPES
    ]
    lines += ["", "## 2. Claims/hypotheses in pre-validation states", ""]
    for state in PRE_VALIDATION_STATES:
        lines.append(f"- {state}: {pre_by_state.get(state, 0)} object(s)")
    lines += [""]
    for obj in pre_validation[:_MAX_LIST]:
        summary = (obj.content_summary or obj.body or "").strip().replace("\n", " ")
        lines.append(f"- [{obj.type} | {obj.lifecycle_state}] {obj.title} — {summary[:160]}")
    if len(pre_validation) > _MAX_LIST:
        lines.append(f"- …and {len(pre_validation) - _MAX_LIST} more")

    contradictions = _unresolved_contradictions(session)
    lines += ["", "## 3. Contradictions", ""]
    if not contradictions:
        lines.append("none")
    for contradiction in contradictions[:_MAX_LIST]:
        lines.append(
            f"- [{contradiction.severity} | {contradiction.status}] "
            f"{contradiction.claim_a_id} <-> {contradiction.claim_b_id}: "
            f"{(contradiction.explanation or '')[:160]}"
        )

    gaps = _documentation_gap_ids(session)
    lines += ["", "## 4. Documentation gaps (code files with no linked document)", ""]
    lines.append(
        f"{len(gaps)} code/test document(s) have no markdown document linked to them "
        "via a `documents` relationship."
    )
    for doc_id in sorted(gaps)[:_MAX_LIST]:
        lines.append(f"- {doc_id}")
    if len(gaps) > _MAX_LIST:
        lines.append(f"- …and {len(gaps) - _MAX_LIST} more")

    unknown_count = pre_by_state.get("unknown", 0)
    lines += ["", "## 5. Stale / unknown items", ""]
    lines.append(f"- knowledge objects in lifecycle state `unknown`: {unknown_count}")
    unknown_objs = [o for o in objects if o.lifecycle_state == "unknown"]
    for obj in unknown_objs[:_MAX_LIST]:
        lines.append(f"  - [{obj.type}] {obj.title}")
    return lines


def _build_implementation_plan(session: Session, generated_at: datetime) -> list[str]:
    lines: list[str] = ["## 1. Current state per source repo", ""]
    for row in _sources_by_type(session).get("git", []):
        docs = list(
            session.execute(select(Document).where(Document.source_id == row.id)).scalars().all()
        )
        objs = list(
            session.execute(select(KnowledgeObject).where(KnowledgeObject.source_id == row.id)).scalars().all()
        )
        doc_types: dict[str, int] = {}
        for doc in docs:
            doc_types[str(doc.doc_type)] = doc_types.get(str(doc.doc_type), 0) + 1
        by_type: dict[str, int] = {}
        by_state: dict[str, int] = {}
        for obj in objs:
            by_type[str(obj.type)] = by_type.get(str(obj.type), 0) + 1
            by_state[str(obj.lifecycle_state)] = by_state.get(str(obj.lifecycle_state), 0) + 1
        commit_count = (row.metadata_json or {}).get("commit_count", 0)
        branch = (row.metadata_json or {}).get("branch", "unknown")
        lines.append(f"### {row.source_id}")
        lines.append(f"- commits: {commit_count} (branch `{branch}`)")
        lines.append(
            f"- documents: {len(docs)} — " + (", ".join(f"{k}: {v}" for k, v in sorted(doc_types.items())) or "none")
        )
        lines.append(
            f"- knowledge objects: {len(objs)} — " + (", ".join(f"{k}: {v}" for k, v in sorted(by_type.items())) or "none")
        )
        lines.append(
            "- state distribution: " + (", ".join(f"{k}: {v}" for k, v in sorted(by_state.items())) or "n/a")
        )
        lines.append("")
    if not _sources_by_type(session).get("git"):
        lines.append("_no git sources registered_")
        lines.append("")

    objects = _active_objects(session)
    contradictions = _unresolved_contradictions(session)
    hot = _top_mentioned_unresearched(session, objects, min_mentions=3)

    lines += ["## 2. Blockers", ""]
    if not contradictions and not hot:
        lines.append("_none detected_")
    if contradictions:
        lines.append(f"### Unresolved contradictions ({len(contradictions)})")
        for contradiction in contradictions[:_MAX_LIST]:
            lines.append(
                f"- [{contradiction.severity}] {contradiction.claim_a_id} <-> "
                f"{contradiction.claim_b_id}: {(contradiction.explanation or '')[:160]}"
            )
    if hot:
        lines.append(f"### High-mention entities with no research or validation ({len(hot)})")
        for name, count in hot[:_MAX_LIST]:
            lines.append(f"- {name} — mentioned in {count} objects, not researched or validated")
    lines.append("")

    # prioritized next steps (each with a reason: line referencing evidence)
    steps: list[tuple[str, str]] = []
    if contradictions:
        steps.append((
            "Resolve the open contradictions before promoting related claims.",
            f"reason: {len(contradictions)} unresolved contradiction(s) block trust in the linked claims.",
        ))
    if hot:
        steps.append((
            "Open research threads for the most-mentioned unvalidated entities.",
            f"reason: {hot[0][0]!r} appears in {hot[0][1]} objects with no research item or validation.",
        ))
    unknown_count = sum(1 for o in objects if o.lifecycle_state == "unknown")
    if unknown_count:
        steps.append((
            "Classify unknown-state knowledge objects onto the lifecycle chain.",
            f"reason: {unknown_count} object(s) sit in state `unknown`, invisible to gap and plan analysis.",
        ))
    pre_validation = sum(1 for o in objects if o.lifecycle_state in PRE_VALIDATION_STATES)
    if objects and pre_validation / len(objects) > 0.5:
        steps.append((
            "Run validation passes (experiments) on the pre-validation claim pool.",
            f"reason: {pre_validation}/{len(objects)} active objects are still in pre-validation states.",
        ))
    gaps = _documentation_gap_ids(session)
    if gaps:
        steps.append((
            "Write markdown documentation for the most-depended code modules.",
            f"reason: {len(gaps)} code/test document(s) have no linked markdown document.",
        ))
    if not steps:
        steps.append((
            "Register more sources or re-run extraction; the registry has no actionable gaps yet.",
            "reason: no blockers, unvalidated hotspots, or documentation gaps were detected.",
        ))
    lines += ["## 3. Prioritized next steps", ""]
    for rank, (step, reason) in enumerate(steps, start=1):
        lines.append(f"{rank}. {step}")
        lines.append(f"   - {reason}")
    return lines


_BUILDERS = {
    "project-knowledge": _build_project_knowledge,
    "research-gaps": _build_research_gaps,
    "implementation-plan": _build_implementation_plan,
}


def _header(report_type: str, generated_at: datetime, db_counts: dict[str, int]) -> list[str]:
    counts_str = ", ".join(f"{key}: {value}" for key, value in sorted(db_counts.items()))
    return [
        f"# MKC {report_type} report",
        "",
        f"- generated_at: {generated_at.isoformat()}",
        f"- generated_by: {GENERATOR_VERSION}",
        f"- source DB counts — {counts_str}",
        "",
    ]


def _footer() -> list[str]:
    return ["", "---", "", "Auto-generated from MKC registry; verify before acting.", ""]


def generate_report(
    session: Session,
    report_type: ReportType | str,
    output_dir: Path | str | None = None,
) -> Report:
    """Build *report_type*, write the markdown file, and upsert the ``Report`` row.

    Idempotent per (type, day): the output file is ``<type>-<YYYY-MM-DD>.md``
    inside *output_dir* (default ``<workspace>/reports``) and same-day
    re-runs overwrite both the file and the existing ``Report`` row.
    Raises ``ValueError`` for an unsupported report type. The caller owns
    ``commit``.
    """
    if report_type not in get_args(ReportType):
        raise ValueError(
            f"unsupported report_type {report_type!r}; expected one of {SUPPORTED_REPORT_TYPES}"
        )

    generated_at = datetime.now(UTC)
    out_dir = Path(output_dir).expanduser().resolve() if output_dir else DEFAULT_REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{report_type}-{generated_at:%Y-%m-%d}.md"

    builder = _BUILDERS[report_type]
    db_counts = _db_counts(session)
    body_lines = builder(session, generated_at)
    markdown = "\n".join(_header(report_type, generated_at, db_counts) + body_lines + _footer())
    file_path.write_text(markdown, encoding="utf-8")

    summary = (
        f"{report_type}: "
        f"{db_counts['knowledge_objects']} knowledge objects, "
        f"{db_counts['documents']} documents, "
        f"{db_counts['sources']} sources, "
        f"{db_counts['entity_relations']} relationships "
        f"({GENERATOR_VERSION})"
    )

    # One Report row per (type, day): regenerate updates the row in place.
    existing = session.execute(
        select(Report).where(Report.path == str(file_path)).order_by(Report.generated_at.desc())
    ).scalars().first()
    if existing is None:
        row = Report(type=report_type, path=str(file_path), generated_at=generated_at, summary=summary)
        session.add(row)
    else:
        row = existing
        row.type = report_type
        row.generated_at = generated_at
        row.summary = summary
    session.flush()
    logger.info("report %s written to %s (id=%s)", report_type, file_path, row.id)
    return row
