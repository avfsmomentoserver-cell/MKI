"""In-process metrics registry rendered as Prometheus exposition text.

Kept deliberately dependency-free (the intelligence wave may swap this for
prometheus_client); the public entry points are the module-level
:data:`metrics` instance and its :meth:`_Metrics.render` method.
"""

from __future__ import annotations

import time
from collections import Counter


class _Metrics:
    """Minimal in-process metrics registry (counters + gauges)."""

    def __init__(self) -> None:
        self._search_queries_total: Counter[str] = Counter()
        self._ingestion_duration_seconds: dict[str, float] = {}
        self._started_at = time.monotonic()

    def inc_search_queries(self, route: str) -> None:
        """Count one search/query execution (called by search endpoints)."""
        self._search_queries_total[route] += 1

    def observe_ingestion(self, source_type: str, duration_seconds: float) -> None:
        """Record an ingestion run duration for a source type."""
        self._ingestion_duration_seconds[source_type] = duration_seconds

    def render(self, knowledge_count: int, document_count: int) -> str:
        """Render the current registry as Prometheus exposition text."""
        lines = [
            "# HELP mkc_knowledge_objects Number of knowledge objects in the registry.",
            "# TYPE mkc_knowledge_objects gauge",
            f"mkc_knowledge_objects {knowledge_count}",
            "# HELP mkc_documents_total Number of ingested documents.",
            "# TYPE mkc_documents_total gauge",
            f"mkc_documents_total {document_count}",
            "# HELP mkc_search_queries_total Total search queries executed, by route.",
            "# TYPE mkc_search_queries_total counter",
        ]
        if self._search_queries_total:
            for route, count in sorted(self._search_queries_total.items()):
                lines.append(f'mkc_search_queries_total{{route="{route}"}} {count}')
        else:
            lines.append("mkc_search_queries_total 0")
        lines += [
            "# HELP mkc_ingestion_duration_seconds Last ingestion duration per source type.",
            "# TYPE mkc_ingestion_duration_seconds gauge",
        ]
        for source_type, seconds in sorted(self._ingestion_duration_seconds.items()):
            lines.append(f'mkc_ingestion_duration_seconds{{source_type="{source_type}"}} {seconds:.4f}')
        lines += [
            "# HELP mkc_uptime_seconds Seconds since the API process started.",
            "# TYPE mkc_uptime_seconds gauge",
            f"mkc_uptime_seconds {time.monotonic() - self._started_at:.1f}",
        ]
        return "\n".join(lines) + "\n"


#: Process-level metrics, shared by every app instance in the process.
metrics = _Metrics()
