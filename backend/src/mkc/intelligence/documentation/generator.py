"""AI-orchestrated documentation generation from knowledge objects."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from mkc.intelligence.ai.providers import get_provider, AIProvider

logger = logging.getLogger("mkc.intelligence.documentation")


class DocType(Enum):
    """Documentation types."""
    OVERVIEW = "overview"
    API_REFERENCE = "api_reference"
    ARCHITECTURE = "architecture"
    GUIDE = "guide"
    TUTORIAL = "tutorial"
    TROUBLESHOOTING = "troubleshooting"
    FAQ = "faq"
    CHANGELOG = "changelog"


@dataclass
class Document:
    """A generated document."""
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    doc_type: DocType = DocType.GUIDE
    content: str = ""
    source_ko_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1
    author: str = "ai"


class DocumentGenerator:
    """Generate documentation from knowledge objects using AI."""

    def __init__(self, provider: Optional[AIProvider] = None):
        self.provider = provider or get_provider("entrim")

    async def generate_overview(self, knowledge_objects: list[dict[str, Any]]) -> Document:
        """Generate an overview document from knowledge objects."""
        logger.info(f"Generating overview from {len(knowledge_objects)} knowledge objects")
        
        # Build context from KOs
        ko_summaries = "\n\n".join([
            f"## {ko.get('title', 'Untitled')}\n{ko.get('content_summary', ko.get('content', '')[:200])}"
            for ko in knowledge_objects[:50]  # Limit to 50 for context
        ])
        
        prompt = f"""Generate a comprehensive overview document based on the following knowledge objects:

{ko_summaries}

Create a well-structured overview that includes:
1. Executive Summary
2. Key Components
3. Architecture Overview
4. Main Features
5. Usage Patterns

Use Markdown formatting with proper headings, lists, and code blocks where appropriate.
Be concise but informative. Focus on the most important information from the knowledge objects.
"""
        
        response = await self.provider.generate(prompt)
        
        return Document(
            title="System Overview",
            doc_type=DocType.OVERVIEW,
            content=response.content,
            source_ko_ids=[ko.get('id') for ko in knowledge_objects],
            author="ai"
        )

    async def generate_api_reference(self, knowledge_objects: list[dict[str, Any]]) -> Document:
        """Generate API reference documentation."""
        logger.info(f"Generating API reference from {len(knowledge_objects)} knowledge objects")
        
        # Filter for API-related KOs
        api_kos = [ko for ko in knowledge_objects if any(
            keyword in ko.get('title', '').lower() or keyword in ko.get('content', '').lower()
            for keyword in ['api', 'endpoint', 'route', 'function', 'method']
        )]
        
        ko_summaries = "\n\n".join([
            f"## {ko.get('title', 'Untitled')}\n{ko.get('content', '')}"
            for ko in api_kos[:30]
        ])
        
        prompt = f"""Generate API reference documentation based on the following knowledge objects:

{ko_summaries}

Create a comprehensive API reference that includes:
1. Introduction
2. Authentication
3. Endpoints (grouped by resource)
4. Request/Response formats
5. Error codes
6. Examples

Use Markdown with code blocks for examples. Include tables for parameters where appropriate.
"""
        
        response = await self.provider.generate(prompt)
        
        return Document(
            title="API Reference",
            doc_type=DocType.API_REFERENCE,
            content=response.content,
            source_ko_ids=[ko.get('id') for ko in api_kos],
            author="ai"
        )

    async def generate_architecture_doc(self, knowledge_objects: list[dict[str, Any]]) -> Document:
        """Generate architecture documentation."""
        logger.info(f"Generating architecture doc from {len(knowledge_objects)} knowledge objects")
        
        # Filter for architecture-related KOs
        arch_kos = [ko for ko in knowledge_objects if any(
            keyword in ko.get('title', '').lower() or keyword in ko.get('content', '').lower()
            for keyword in ['architecture', 'design', 'component', 'module', 'structure']
        )]
        
        ko_summaries = "\n\n".join([
            f"## {ko.get('title', 'Untitled')}\n{ko.get('content', '')}"
            for ko in arch_kos[:30]
        ])
        
        prompt = f"""Generate architecture documentation based on the following knowledge objects:

{ko_summaries}

Create comprehensive architecture documentation that includes:
1. System Overview
2. High-Level Architecture
3. Component Diagram (described in text)
4. Data Flow
5. Technology Stack
6. Design Patterns
7. Deployment Considerations

Use Markdown with mermaid diagrams where appropriate. Use code blocks for configuration examples.
"""
        
        response = await self.provider.generate(prompt)
        
        return Document(
            title="Architecture Documentation",
            doc_type=DocType.ARCHITECTURE,
            content=response.content,
            source_ko_ids=[ko.get('id') for ko in arch_kos],
            author="ai"
        )

    async def generate_guide(self, knowledge_objects: list[dict[str, Any]], topic: str) -> Document:
        """Generate a guide on a specific topic."""
        logger.info(f"Generating guide on '{topic}' from {len(knowledge_objects)} knowledge objects")
        
        # Filter for topic-relevant KOs
        relevant_kos = [ko for ko in knowledge_objects if topic.lower() in 
                       ko.get('title', '').lower() or topic.lower() in ko.get('content', '').lower()]
        
        ko_summaries = "\n\n".join([
            f"## {ko.get('title', 'Untitled')}\n{ko.get('content', '')}"
            for ko in relevant_kos[:40]
        ])
        
        prompt = f"""Generate a comprehensive guide on '{topic}' based on the following knowledge objects:

{ko_summaries}

Create a practical guide that includes:
1. Introduction
2. Prerequisites
3. Step-by-step instructions
4. Examples
5. Common pitfalls
6. Best practices
7. Troubleshooting

Use Markdown with code blocks for examples. Include numbered steps for procedures.
Make it actionable and easy to follow.
"""
        
        response = await self.provider.generate(prompt)
        
        return Document(
            title=f"{topic.title()} Guide",
            doc_type=DocType.GUIDE,
            content=response.content,
            source_ko_ids=[ko.get('id') for ko in relevant_kos],
            author="ai"
        )

    async def generate_changelog(self, knowledge_objects: list[dict[str, Any]]) -> Document:
        """Generate changelog from recent changes."""
        logger.info(f"Generating changelog from {len(knowledge_objects)} knowledge objects")
        
        # Filter for change-related KOs
        change_kos = [ko for ko in knowledge_objects if any(
            keyword in ko.get('title', '').lower() or keyword in ko.get('content', '').lower()
            for keyword in ['change', 'fix', 'feature', 'update', 'bug', 'release']
        )]
        
        ko_summaries = "\n\n".join([
            f"## {ko.get('title', 'Untitled')}\n{ko.get('content', '')}"
            for ko in change_kos[:50]
        ])
        
        prompt = f"""Generate a changelog based on the following knowledge objects:

{ko_summaries}

Create a structured changelog that includes:
1. Recent Changes (grouped by type: Added, Changed, Fixed, Removed)
2. Version information
3. Migration notes if applicable
4. Known issues

Use standard changelog format with proper Markdown formatting.
"""
        
        response = await self.provider.generate(prompt)
        
        return Document(
            title="Changelog",
            doc_type=DocType.CHANGELOG,
            content=response.content,
            source_ko_ids=[ko.get('id') for ko in change_kos],
            author="ai"
        )
