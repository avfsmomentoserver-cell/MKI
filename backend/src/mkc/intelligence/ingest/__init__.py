"""Ingestion collectors: git repositories, markdown directories, chat exports."""

from mkc.intelligence.ingest.base import (
    BaseCollector,
    CollectionRunner,
    IngestionResult,
    RawArtifact,
)
from mkc.intelligence.ingest.chatgpt_importer import ChatGPTImporter
from mkc.intelligence.ingest.git_collector import GitRepoCollector
from mkc.intelligence.ingest.markdown_collector import MarkdownCollector

__all__ = [
    "BaseCollector",
    "ChatGPTImporter",
    "CollectionRunner",
    "GitRepoCollector",
    "IngestionResult",
    "MarkdownCollector",
    "RawArtifact",
]
