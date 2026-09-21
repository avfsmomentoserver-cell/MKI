"""MKC intelligence layer.

Turns raw artifacts (git repositories, markdown documents, chat exports)
into structured knowledge objects with immutable provenance.

Sub-packages
------------
ingest      Collectors that read sources and persist Source/Document rows.
parsing     Rule-based knowledge extraction and relationship building.
analysis    Search, contradiction detection and insight generation.
reports     Deterministic markdown report generation.
context     Context API used by AI agents (FastAPI router + service).
"""

__version__ = "1.0.0"

EXTRACTION_METHOD = "rule-based-v1"
