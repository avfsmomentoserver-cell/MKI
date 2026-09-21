"""Knowledge graph visualization and analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from mkc.models import KnowledgeObject, Entity, EntityRelation

logger = logging.getLogger("mkc.intelligence.graph")


@dataclass
class GraphNode:
    """A node in the knowledge graph."""
    id: str = field(default_factory=lambda: str(uuid4()))
    label: str = ""
    type: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    source_ko_id: Optional[str] = None


@dataclass
class GraphEdge:
    """An edge in the knowledge graph."""
    id: str = field(default_factory=lambda: str(uuid4()))
    source: str = ""
    target: str = ""
    label: str = ""
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGraph:
    """A knowledge graph with nodes and edges."""
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeGraphBuilder:
    """Build knowledge graphs from database data."""

    def __init__(self):
        pass

    def build_graph(self, session: Session, limit: int = 100) -> KnowledgeGraph:
        """Build a knowledge graph from knowledge objects and relationships."""
        logger.info(f"Building knowledge graph with limit {limit}")
        
        graph = KnowledgeGraph()
        
        # Get knowledge objects as nodes
        knowledge_objects = session.query(KnowledgeObject).filter(
            KnowledgeObject.status == "active"
        ).limit(limit).all()
        
        # Create nodes from knowledge objects
        ko_id_to_node_id = {}
        for ko in knowledge_objects:
            node = GraphNode(
                label=ko.title or ko.type,
                type=ko.type,
                properties={
                    "confidence": ko.confidence,
                    "lifecycle_state": ko.lifecycle_state,
                    "created_at": ko.created_at.isoformat() if ko.created_at else None,
                },
                source_ko_id=str(ko.id)
            )
            graph.nodes.append(node)
            ko_id_to_node_id[str(ko.id)] = node.id
        
        # Add edges from entity relations
        relations = session.query(EntityRelation).limit(limit * 2).all()
        
        for relation in relations:
            source_id = relation.from_id
            target_id = relation.to_id
            
            # Only add edges if both nodes exist in our graph
            if source_id in ko_id_to_node_id and target_id in ko_id_to_node_id:
                edge = GraphEdge(
                    source=ko_id_to_node_id[source_id],
                    target=ko_id_to_node_id[target_id],
                    label=relation.rel_type,
                    weight=relation.confidence,
                    properties={
                        "reason": relation.reason,
                    }
                )
                graph.edges.append(edge)
        
        # Add edges from entities to their related knowledge objects
        entities = session.query(Entity).limit(limit).all()
        
        for entity in entities:
            # Create entity node
            entity_node = GraphNode(
                label=entity.name,
                type="entity",
                properties={
                    "kind": entity.kind,
                    "attributes": entity.attributes_json or {},
                }
            )
            graph.nodes.append(entity_node)
            
            # Connect entity to knowledge objects that mention it
            # This is a simplified approach - in production, use text analysis
            for ko in knowledge_objects:
                content = (ko.content_summary + " " + ko.body).lower()
                if entity.name.lower() in content:
                    edge = GraphEdge(
                        source=entity_node.id,
                        target=ko_id_to_node_id.get(str(ko.id), ""),
                        label="mentions",
                        weight=0.8,
                        properties={"reason": "Entity mentioned in content"}
                    )
                    if edge.target:  # Only add if target exists
                        graph.edges.append(edge)
        
        graph.metadata = {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "knowledge_object_count": len(knowledge_objects),
            "entity_count": len(entities),
        }
        
        logger.info(f"Built graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        return graph

    def build_subgraph(self, session: Session, central_ko_id: str, depth: int = 2) -> KnowledgeGraph:
        """Build a subgraph centered on a specific knowledge object."""
        logger.info(f"Building subgraph centered on {central_ko_id} with depth {depth}")
        
        graph = KnowledgeGraph()
        
        # Get the central knowledge object
        central_ko = session.query(KnowledgeObject).filter(
            KnowledgeObject.id == central_ko_id
        ).first()
        
        if not central_ko:
            logger.warning(f"Knowledge object {central_ko_id} not found")
            return graph
        
        # Add central node
        central_node = GraphNode(
            label=central_ko.title or central_ko.type,
            type=central_ko.type,
            properties={
                "confidence": central_ko.confidence,
                "lifecycle_state": central_ko.lifecycle_state,
                "is_central": True,
            },
            source_ko_id=str(central_ko.id)
        )
        graph.nodes.append(central_node)
        
        # Get related knowledge objects via entity relations
        # This is a simplified approach - could be enhanced with more sophisticated relation detection
        related_kos = session.query(KnowledgeObject).filter(
            KnowledgeObject.status == "active",
            KnowledgeObject.id != central_ko_id
        ).limit(20).all()
        
        ko_id_to_node_id = {str(central_ko.id): central_node.id}
        
        for ko in related_kos:
            node = GraphNode(
                label=ko.title or ko.type,
                type=ko.type,
                properties={
                    "confidence": ko.confidence,
                    "lifecycle_state": ko.lifecycle_state,
                },
                source_ko_id=str(ko.id)
            )
            graph.nodes.append(node)
            ko_id_to_node_id[str(ko.id)] = node.id
            
            # Add edge from central node (simplified - just connecting for now)
            edge = GraphEdge(
                source=central_node.id,
                target=node.id,
                label="related",
                weight=0.5,
                properties={"reason": "Related knowledge object"}
            )
            graph.edges.append(edge)
        
        graph.metadata = {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "central_ko_id": central_ko_id,
            "depth": depth,
        }
        
        return graph

    def analyze_graph(self, graph: KnowledgeGraph) -> dict[str, Any]:
        """Analyze the knowledge graph and return metrics."""
        node_types = {}
        edge_types = {}
        
        for node in graph.nodes:
            node_types[node.type] = node_types.get(node.type, 0) + 1
        
        for edge in graph.edges:
            edge_types[edge.label] = edge_types.get(edge.label, 0) + 1
        
        # Calculate graph density
        max_edges = len(graph.nodes) * (len(graph.nodes) - 1) / 2
        density = len(graph.edges) / max_edges if max_edges > 0 else 0
        
        # Find most connected nodes
        node_connections = {}
        for edge in graph.edges:
            node_connections[edge.source] = node_connections.get(edge.source, 0) + 1
            node_connections[edge.target] = node_connections.get(edge.target, 0) + 1
        
        top_nodes = sorted(node_connections.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "density": density,
            "node_types": node_types,
            "edge_types": edge_types,
            "most_connected_nodes": [
                {"node_id": node_id, "connections": count}
                for node_id, count in top_nodes
            ],
        }
