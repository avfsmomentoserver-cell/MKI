"""Deterministic markdown report generation.

Public entry point: :func:`mkc.intelligence.reports.generator.generate_report`
(upserts a ``Report`` row and writes ``<type>-<YYYY-MM-DD>.md``).
"""

from mkc.intelligence.reports.generator import (
    DEFAULT_REPORT_DIR,
    GENERATOR_VERSION,
    SUPPORTED_REPORT_TYPES,
    generate_report,
)

__all__ = [
    "DEFAULT_REPORT_DIR",
    "GENERATOR_VERSION",
    "SUPPORTED_REPORT_TYPES",
    "generate_report",
]
