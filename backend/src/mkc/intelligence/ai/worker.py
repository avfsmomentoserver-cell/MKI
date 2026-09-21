"""Background worker for processing AI tasks."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from mkc.intelligence.ai.queue import get_queue, Task, TaskStatus
from mkc.intelligence.ai.metrics import get_tracker
from mkc.intelligence.ai.providers import get_provider, AIMessage

logger = logging.getLogger("mkc.ai.worker")


class AIWorker:
    """Background worker that processes AI tasks from the queue."""

    def __init__(self, provider_type: str = "entrim", **provider_kwargs: Any):
        self.provider = get_provider(provider_type, **provider_kwargs)
        self.queue = get_queue()
        self.tracker = get_tracker()
        self._running = False

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        logger.info("AI worker started")
        
        while self._running:
            task = self.queue.dequeue()
            if task:
                await self._process_task(task)
            else:
                await asyncio.sleep(1)  # Poll interval

    async def stop(self) -> None:
        """Stop the worker loop."""
        self._running = False
        logger.info("AI worker stopped")

    async def _process_task(self, task: Task) -> None:
        """Process a single task."""
        logger.info(f"Processing task: {task.id} ({task.task_type})")
        
        try:
            if task.task_type == "generate_documentation":
                result = await self._generate_documentation(task.payload)
            elif task.task_type == "run_research":
                result = await self._run_research(task.payload)
            elif task.task_type == "synthesis":
                result = await self._synthesis(task.payload)
            elif task.task_type == "review":
                result = await self._review(task.payload)
            else:
                raise ValueError(f"Unknown task type: {task.task_type}")
            
            self.queue.complete(task.id, result)
            
            # Record usage
            if hasattr(self.provider, 'get_total_usage'):
                usage = self.provider.get_total_usage()
                # Simplified usage tracking (would need more context in real implementation)
            
        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}")
            self.queue.fail(task.id, str(e))

    async def _generate_documentation(self, payload: dict[str, Any]) -> str:
        """Generate documentation from knowledge objects."""
        prompt = payload.get("prompt", "")
        knowledge_objects = payload.get("knowledge_objects", [])
        
        # Build prompt from KOs
        ko_text = "\n\n".join([
            f"- {ko.get('title', '')}: {ko.get('content_summary', '')}"
            for ko in knowledge_objects[:20]  # Limit to first 20 for context
        ])
        
        full_prompt = f"""Generate documentation based on the following knowledge objects:

{ko_text}

Task: {prompt}

Generate clear, well-structured documentation in Markdown format.
"""
        
        response = await self.provider.generate(full_prompt)
        
        # Record usage
        self.tracker.record_usage(
            provider=self.provider.__class__.__name__,
            model=self.provider.model,
            task_type="generate_documentation",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_estimate_usd=response.usage.cost_estimate_usd,
            success=True
        )
        
        return response.content

    async def _run_research(self, payload: dict[str, Any]) -> str:
        """Run research analysis."""
        query = payload.get("query", "")
        context = payload.get("context", "")
        
        prompt = f"""Research query: {query}

Context: {context}

Analyze the context and provide:
1. Key findings
2. Potential contradictions
3. Research gaps
4. Recommendations
"""
        
        response = await self.provider.generate(prompt)
        
        self.tracker.record_usage(
            provider=self.provider.__class__.__name__,
            model=self.provider.model,
            task_type="run_research",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_estimate_usd=response.usage.cost_estimate_usd,
            success=True
        )
        
        return response.content

    async def _synthesis(self, payload: dict[str, Any]) -> str:
        """Synthesize information from multiple sources."""
        sources = payload.get("sources", [])
        topic = payload.get("topic", "")
        
        prompt = f"""Synthesize information on: {topic}

Sources:
{chr(10).join(f"- {s}" for s in sources[:10])}

Provide a comprehensive synthesis that:
1. Identifies common themes
2. Highlights differences
3. Proposes new insights
"""
        
        response = await self.provider.generate(prompt)
        
        self.tracker.record_usage(
            provider=self.provider.__class__.__name__,
            model=self.provider.model,
            task_type="synthesis",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_estimate_usd=response.usage.cost_estimate_usd,
            success=True
        )
        
        return response.content

    async def _review(self, payload: dict[str, Any]) -> str:
        """Review content for quality and completeness."""
        content = payload.get("content", "")
        criteria = payload.get("criteria", [])
        
        prompt = f"""Review the following content:

{content}

Criteria:
{chr(10).join(f"- {c}" for c in criteria)}

Provide:
1. Quality assessment
2. Completeness check
3. Suggestions for improvement
"""
        
        response = await self.provider.generate(prompt)
        
        self.tracker.record_usage(
            provider=self.provider.__class__.__name__,
            model=self.provider.model,
            task_type="review",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_estimate_usd=response.usage.cost_estimate_usd,
            success=True
        )
        
        return response.content
