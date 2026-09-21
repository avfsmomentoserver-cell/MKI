"""Research task runner for scheduled research workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from mkc.intelligence.ai.providers import get_provider
from mkc.models import KnowledgeObject, Insight, Contradiction

logger = logging.getLogger("mkc.intelligence.research")


class ResearchTaskType(Enum):
    """Types of research tasks."""
    ANALYZE_GAPS = "analyze_gaps"
    GENERATE_HYPOTHESES = "generate_hypotheses"
    SYNTHESIS = "synthesis"
    CONTRADICTION_DEEP_DIVE = "contradiction_deep_dive"
    CROSS_SOURCE_ANALYSIS = "cross_source_analysis"


@dataclass
class ResearchTaskResult:
    """Result of a research task."""
    task_id: str = field(default_factory=lambda: str(uuid4()))
    task_type: ResearchTaskType = ResearchTaskType.ANALYZE_GAPS
    status: str = "completed"
    findings: list[str] = field(default_factory=list)
    insights_generated: int = 0
    contradictions_found: int = 0
    hypotheses_generated: int = 0
    error: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class ResearchTaskRunner:
    """Runner for scheduled research tasks."""

    def __init__(self, provider_type: str = "entrim"):
        self.provider = get_provider(provider_type)

    async def run_task(self, task_type: ResearchTaskType, session: Session) -> ResearchTaskResult:
        """Run a research task."""
        result = ResearchTaskResult(task_type=task_type)
        logger.info(f"Starting research task: {task_type.value}")

        try:
            if task_type == ResearchTaskType.ANALYZE_GAPS:
                await self._analyze_gaps(session, result)
            elif task_type == ResearchTaskType.GENERATE_HYPOTHESES:
                await self._generate_hypotheses(session, result)
            elif task_type == ResearchTaskType.SYNTHESIS:
                await self._synthesis(session, result)
            elif task_type == ResearchTaskType.CONTRADICTION_DEEP_DIVE:
                await self._contradiction_deep_dive(session, result)
            elif task_type == ResearchTaskType.CROSS_SOURCE_ANALYSIS:
                await self._cross_source_analysis(session, result)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

            result.completed_at = datetime.utcnow()
            result.status = "completed"
            logger.info(f"Research task completed: {task_type.value}")

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            result.completed_at = datetime.utcnow()
            logger.error(f"Research task failed: {task_type.value} - {e}")

        return result

    async def _analyze_gaps(self, session: Session, result: ResearchTaskResult) -> None:
        """Analyze research gaps in knowledge objects."""
        # Get knowledge objects with low confidence or unknown lifecycle state
        k_objects = session.query(KnowledgeObject).filter(
            (KnowledgeObject.confidence < 0.5) | 
            (KnowledgeObject.lifecycle_state == "unknown")
        ).limit(50).all()

        if not k_objects:
            result.findings.append("No low-confidence or unknown knowledge objects found")
            return

        ko_summaries = "\n\n".join([
            f"- {ko.title} (confidence: {ko.confidence}, state: {ko.lifecycle_state})"
            for ko in k_objects[:20]
        ])

        prompt = f"""Analyze the following knowledge objects for research gaps:

{ko_summaries}

Identify:
1. Knowledge gaps (missing information)
2. Uncertain claims (low confidence)
3. Areas needing validation
4. Suggested research directions

Provide specific, actionable recommendations for each gap identified.
"""

        response = await self.provider.generate(prompt)
        result.findings.append(response.content)
        result.findings.append(f"Analyzed {len(k_objects)} knowledge objects")

    async def _generate_hypotheses(self, session: Session, result: ResearchTaskResult) -> None:
        """Generate new research hypotheses from existing knowledge."""
        # Get recent insights to base hypotheses on
        insights = session.query(Insight).filter(
            Insight.status == "needs_review"
        ).limit(20).all()

        if not insights:
            result.findings.append("No insights found to generate hypotheses from")
            return

        insight_summaries = "\n\n".join([
            f"- {insight.insight_type}: {insight.summary[:200]}"
            for insight in insights
        ])

        prompt = f"""Based on the following insights, generate testable research hypotheses:

{insight_summaries}

For each hypothesis:
1. State the hypothesis clearly
2. Define what would confirm it
3. Define what would refute it
4. Suggest a validation method

Focus on hypotheses that can be tested with available data or experiments.
"""

        response = await self.provider.generate(prompt)
        result.findings.append(response.content)
        result.hypotheses_generated = len([line for line in response.content.split('\n') if 'hypothesis' in line.lower()])

    async def _synthesis(self, session: Session, result: ResearchTaskResult) -> None:
        """Synthesize information across multiple sources."""
        # Get knowledge objects from different sources
        k_objects = session.query(KnowledgeObject).filter(
            KnowledgeObject.status == "active"
        ).limit(100).all()

        # Group by source
        from collections import defaultdict
        by_source = defaultdict(list)
        for ko in k_objects:
            source_id = str(ko.source_id) if ko.source_id else "unknown"
            by_source[source_id].append(ko)

        if len(by_source) < 2:
            result.findings.append("Need at least 2 sources for synthesis")
            return

        source_summary = "\n\n".join([
            f"Source {source_id}: {len(kos)} objects"
            for source_id, kos in by_source.items()
        ])

        prompt = f"""Synthesize information across multiple sources:

{source_summary}

Identify:
1. Common themes across sources
2. Contradictions between sources
3. Unique contributions of each source
4. Gaps where sources disagree or lack information

Provide a balanced synthesis that acknowledges source diversity.
"""

        response = await self.provider.generate(prompt)
        result.findings.append(response.content)
        result.findings.append(f"Synthesized across {len(by_source)} sources")

    async def _contradiction_deep_dive(self, session: Session, result: ResearchTaskResult) -> None:
        """Deep dive analysis of flagged contradictions."""
        # Get unresolved contradictions
        contradictions = session.query(Contradiction).filter(
            Contradiction.status == "flagged"
        ).limit(10).all()

        if not contradictions:
            result.findings.append("No unresolved contradictions found")
            return

        contradiction_summaries = "\n\n".join([
            f"- Severity: {c.severity}, Claim A: {c.claim_a_id}, Claim B: {c.claim_b_id}"
            for c in contradictions
        ])

        prompt = f"""Analyze the following flagged contradictions:

{contradiction_summaries}

For each contradiction:
1. Suggest resolution strategies
2. Identify which claim might be more credible
3. Propose validation experiments
4. Recommend next steps

Provide specific, actionable resolution paths.
"""

        response = await self.provider.generate(prompt)
        result.findings.append(response.content)
        result.contradictions_found = len(contradictions)

    async def _cross_source_analysis(self, session: Session, result: ResearchTaskResult) -> None:
        """Analyze knowledge objects across different sources."""
        # Get knowledge objects with source information
        k_objects = session.query(KnowledgeObject).filter(
            KnowledgeObject.source_id.isnot(None)
        ).limit(100).all()

        if not k_objects:
            result.findings.append("No knowledge objects with source information")
            return

        # Group by source
        from collections import defaultdict
        by_source = defaultdict(list)
        for ko in k_objects:
            source_id = str(ko.source_id)
            by_source[source_id].append(ko)

        source_analysis = "\n\n".join([
            f"Source {source_id}: {len(kos)} objects, types: {set(ko.type for ko in kos)}"
            for source_id, kos in by_source.items()
        ])

        prompt = f"""Analyze knowledge distribution across sources:

{source_analysis}

Identify:
1. Knowledge silos (information only in one source)
2. Redundant information across sources
3. Knowledge gaps by source
4. Recommendations for better cross-source integration

Provide actionable recommendations for improving knowledge sharing.
"""

        response = await self.provider.generate(prompt)
        result.findings.append(response.content)
        result.findings.append(f"Analyzed {len(by_source)} sources")
