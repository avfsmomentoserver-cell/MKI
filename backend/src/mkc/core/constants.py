"""Shared constants: lifecycle states, knowledge types, and public API version."""

from __future__ import annotations

#: Major API version served under /api/v1.
API_VERSION: str = "v1"

#: Every knowledge object lifecycle state recognized by the registry.
LIFECYCLE_STATES: frozenset[str] = frozenset(
    {
        "idea",
        "question",
        "hypothesis",
        "researching",
        "experiment",
        "observed",
        "validating",
        "validated",
        "implemented",
        "production",
        "contradicted",
        "rejected",
        "deprecated",
        "superseded",
        "unknown",
    }
)

#: Source types an ingestion job can register.
SOURCE_TYPES: frozenset[str] = frozenset({"git", "markdown", "chatgpt", "commit", "code", "research"})

#: Derived document classification values.
DOC_TYPES: frozenset[str] = frozenset({"code", "markdown", "json", "yaml", "config", "test", "other"})

#: Entity kinds tracked in the entity graph.
ENTITY_KINDS: frozenset[str] = frozenset({"module", "engine", "theory", "metric", "concept", "person"})

#: Relation types between documents and knowledge objects.
RELATION_TYPES: frozenset[str] = frozenset(
    {"depends_on", "uses", "implements", "tests", "documents", "related_to"}
)

#: Research item workflow states.
RESEARCH_STATUSES: frozenset[str] = frozenset(
    {"planned", "running", "paused", "failed", "succeeded", "validated", "archived"}
)

#: Experiment workflow states.
EXPERIMENT_STATUSES: frozenset[str] = RESEARCH_STATUSES

#: Decision statuses.
DECISION_STATUSES: frozenset[str] = frozenset({"proposed", "accepted", "implemented", "superseded"})

#: Insight categories.
INSIGHT_TYPES: frozenset[str] = frozenset({"pattern", "trend", "gap", "contradiction", "recommendation"})

INSIGHT_STATUSES: frozenset[str] = frozenset({"needs_review", "accepted", "rejected"})

#: Contradiction severities.
CONTRADICTION_SEVERITIES: frozenset[str] = frozenset({"high", "medium", "low"})

CONTRADICTION_STATUSES: frozenset[str] = frozenset({"flagged", "resolved", "false_positive"})

#: Generated report kinds.
REPORT_TYPES: frozenset[str] = frozenset(
    {"project-knowledge", "research-gaps", "implementation-plan", "architecture", "release-notes"}
)

#: Knowledge object type taxonomy (see models.KnowledgeObject.type).
KNOWLEDGE_TYPES: frozenset[str] = frozenset(
    {
        "document",
        "fact",
        "claim",
        "hypothesis",
        "question",
        "theory",
        "insight",
        "research",
        "paper",
        "experiment",
        "observation",
        "decision",
        "requirement",
        "module",
        "dependency",
        "implementation",
        "benchmark",
        "bug",
        "risk",
        "tech_debt",
        "plan",
        "task",
        "roadmap_item",
        "glossary_term",
        "metric",
        "dataset",
        "source",
        "person",
        "project",
        "subsystem",
    }
)

#: Knowledge object storage statuses.
KNOWLEDGE_STATUSES: frozenset[str] = frozenset({"active", "archived"})
