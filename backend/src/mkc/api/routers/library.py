"""API router for library analytics and graph visualization."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mkc.core.auth import require_token
from mkc.core.database import get_session
from mkc.intelligence.graph.builder import KnowledgeGraphBuilder
from mkc.intelligence.library.analytics import LibraryAnalytics

logger = logging.getLogger("mkc.api.library")

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/metrics")
async def get_library_metrics(session: Session = Depends(get_session)):
    """Get comprehensive library metrics."""
    analytics = LibraryAnalytics()
    metrics = analytics.compute_metrics(session)
    
    return metrics.__dict__


@router.get("/growth-trends")
async def get_growth_trends(days: int = 30, session: Session = Depends(get_session)):
    """Get growth trends over time."""
    analytics = LibraryAnalytics()
    trends = analytics.get_growth_trends(session, days)
    
    return trends


@router.get("/top-sources")
async def get_top_sources(limit: int = 10, session: Session = Depends(get_session)):
    """Get top sources by knowledge object count."""
    analytics = LibraryAnalytics()
    sources = analytics.get_top_sources(session, limit)
    
    return sources


@router.get("/graph")
async def get_knowledge_graph(limit: int = 100, session: Session = Depends(get_session)):
    """Get knowledge graph visualization data."""
    builder = KnowledgeGraphBuilder()
    graph = builder.build_graph(session, limit)
    
    return {
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "type": node.type,
                "properties": node.properties,
                "source_ko_id": node.source_ko_id,
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "label": edge.label,
                "weight": edge.weight,
                "properties": edge.properties,
            }
            for edge in graph.edges
        ],
        "metadata": graph.metadata,
    }


@router.get("/graph/analyze")
async def analyze_graph(limit: int = 100, session: Session = Depends(get_session)):
    """Analyze the knowledge graph and return metrics."""
    builder = KnowledgeGraphBuilder()
    graph = builder.build_graph(session, limit)
    analysis = builder.analyze_graph(graph)
    
    return analysis


@router.get("/graph/subgraph/{ko_id}")
async def get_subgraph(ko_id: str, depth: int = 2, session: Session = Depends(get_session)):
    """Get a subgraph centered on a specific knowledge object."""
    builder = KnowledgeGraphBuilder()
    graph = builder.build_subgraph(session, ko_id, depth)
    
    return {
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "type": node.type,
                "properties": node.properties,
                "source_ko_id": node.source_ko_id,
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "label": edge.label,
                "weight": edge.weight,
                "properties": edge.properties,
            }
            for edge in graph.edges
        ],
        "metadata": graph.metadata,
    }
