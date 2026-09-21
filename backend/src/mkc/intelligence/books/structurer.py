"""Book structurer for organizing knowledge objects into books."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from mkc.intelligence.ai.providers import get_provider

logger = logging.getLogger("mkc.intelligence.books")


class BookFormat(Enum):
    """Book export formats."""
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    EPUB = "epub"


@dataclass
class Chapter:
    """A book chapter."""
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    content: str = ""
    order: int = 0
    source_ko_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Book:
    """A structured book from knowledge objects."""
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    subtitle: str = ""
    author: str = ""
    description: str = ""
    chapters: list[Chapter] = field(default_factory=list)
    toc: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class BookStructurer:
    """Structure knowledge objects into books."""

    def __init__(self, provider_type: str = "entrim"):
        self.provider = get_provider(provider_type)

    async def structure_book(self, knowledge_objects: list[dict[str, Any]], 
                           book_title: str = "Knowledge Base",
                           structure_type: str = "topic_based") -> Book:
        """Structure knowledge objects into a book.
        
        Args:
            knowledge_objects: List of knowledge object dicts
            book_title: Title for the book
            structure_type: How to organize chapters (topic_based, chronological, type_based)
        """
        logger.info(f"Structuring book: {book_title} with {len(knowledge_objects)} KOs")
        
        if structure_type == "topic_based":
            book = await self._structure_by_topic(knowledge_objects, book_title)
        elif structure_type == "chronological":
            book = await self._structure_chronologically(knowledge_objects, book_title)
        elif structure_type == "type_based":
            book = await self._structure_by_type(knowledge_objects, book_title)
        else:
            raise ValueError(f"Unknown structure type: {structure_type}")
        
        # Generate table of contents
        book.toc = self._generate_toc(book)
        
        book.updated_at = datetime.utcnow()
        logger.info(f"Book structured: {book.title} with {len(book.chapters)} chapters")
        
        return book

    async def _structure_by_topic(self, knowledge_objects: list[dict[str, Any]], 
                                 book_title: str) -> Book:
        """Structure book by topic using AI to group related content."""
        # Group KOs by type first as a starting point
        from collections import defaultdict
        by_type = defaultdict(list)
        for ko in knowledge_objects:
            by_type[ko.get('type', 'unknown')].append(ko)
        
        chapters = []
        chapter_order = 0
        
        # Create chapters for each major type
        for ko_type, k_objects in sorted(by_type.items()):
            if len(k_objects) < 3:
                continue  # Skip small groups
            
            # Use AI to generate chapter content
            ko_summaries = "\n\n".join([
                f"## {ko.get('title', 'Untitled')}\n{ko.get('content_summary', ko.get('content', '')[:300])}"
                for ko in k_objects[:15]  # Limit for context
            ])
            
            prompt = f"""Create a comprehensive chapter about {ko_type} based on the following knowledge objects:

{ko_summaries}

Generate a well-structured chapter that includes:
1. Introduction to the topic
2. Key concepts
3. Detailed explanations
4. Examples and applications
5. Summary

Use Markdown formatting with proper headings, lists, and code blocks where appropriate.
"""
            
            response = await self.provider.generate(prompt)
            
            chapter = Chapter(
                title=ko_type.replace('_', ' ').title(),
                content=response.content,
                order=chapter_order,
                source_ko_ids=[ko.get('id') for ko in k_objects],
                metadata={"ko_type": ko_type, "ko_count": len(k_objects)}
            )
            chapters.append(chapter)
            chapter_order += 1
        
        # Sort chapters by order
        chapters.sort(key=lambda c: c.order)
        
        return Book(
            title=book_title,
            subtitle="AI-Structured Knowledge Base",
            author="MKC System",
            description=f"A comprehensive book organized by topic from {len(knowledge_objects)} knowledge objects",
            chapters=chapters,
            metadata={"structure_type": "topic_based", "total_kos": len(knowledge_objects)}
        )

    async def _structure_chronologically(self, knowledge_objects: list[dict[str, Any]], 
                                        book_title: str) -> Book:
        """Structure book chronologically by creation date."""
        # Sort by created_at
        sorted_kos = sorted(knowledge_objects, key=lambda ko: ko.get('created_at', ''))
        
        # Group by date ranges (e.g., by month)
        from collections import defaultdict
        by_month = defaultdict(list)
        for ko in sorted_kos:
            created_at = ko.get('created_at', '')
            if created_at:
                month_key = created_at[:7]  # YYYY-MM
                by_month[month_key].append(ko)
        
        chapters = []
        chapter_order = 0
        
        for month, k_objects in sorted(by_month.items()):
            if len(k_objects) < 2:
                continue
            
            ko_summaries = "\n\n".join([
                f"## {ko.get('title', 'Untitled')}\n{ko.get('content_summary', '')[:200]}"
                for ko in k_objects[:10]
            ])
            
            prompt = f"""Create a chapter covering knowledge from {month} based on:

{ko_summaries}

Generate a chapter that:
1. Summarizes the key developments from this period
2. Highlights important concepts and discoveries
3. Shows progression over time
4. Connects to broader themes

Use Markdown formatting.
"""
            
            response = await self.provider.generate(prompt)
            
            chapter = Chapter(
                title=f"{month}: Knowledge Evolution",
                content=response.content,
                order=chapter_order,
                source_ko_ids=[ko.get('id') for ko in k_objects],
                metadata={"month": month, "ko_count": len(k_objects)}
            )
            chapters.append(chapter)
            chapter_order += 1
        
        return Book(
            title=book_title,
            subtitle="Chronological Knowledge Evolution",
            author="MKC System",
            description=f"A chronological book tracing knowledge development over time",
            chapters=chapters,
            metadata={"structure_type": "chronological", "total_kos": len(knowledge_objects)}
        )

    async def _structure_by_type(self, knowledge_objects: list[dict[str, Any]], 
                                book_title: str) -> Book:
        """Structure book by knowledge object type."""
        from collections import defaultdict
        by_type = defaultdict(list)
        for ko in knowledge_objects:
            by_type[ko.get('type', 'unknown')].append(ko)
        
        chapters = []
        chapter_order = 0
        
        # Standard chapter order for technical books
        type_order = ['concept', 'architecture', 'api', 'implementation', 'testing', 'deployment']
        
        for ko_type in type_order:
            if ko_type not in by_type or len(by_type[ko_type]) < 2:
                continue
            
            k_objects = by_type[ko_type]
            ko_summaries = "\n\n".join([
                f"## {ko.get('title', 'Untitled')}\n{ko.get('content_summary', '')[:200]}"
                for ko in k_objects[:15]
            ])
            
            prompt = f"""Create a comprehensive chapter about {ko_type} based on:

{ko_summaries}

Generate a technical chapter that:
1. Explains fundamental concepts
2. Provides implementation details
3. Includes examples and best practices
4. Addresses common issues

Use Markdown formatting with code blocks and technical precision.
"""
            
            response = await self.provider.generate(prompt)
            
            chapter = Chapter(
                title=ko_type.replace('_', ' ').title(),
                content=response.content,
                order=chapter_order,
                source_ko_ids=[ko.get('id') for ko in k_objects],
                metadata={"ko_type": ko_type, "ko_count": len(k_objects)}
            )
            chapters.append(chapter)
            chapter_order += 1
        
        return Book(
            title=book_title,
            subtitle="Technical Knowledge Base",
            author="MKC System",
            description=f"A technical book organized by knowledge type",
            chapters=chapters,
            metadata={"structure_type": "type_based", "total_kos": len(knowledge_objects)}
        )

    def _generate_toc(self, book: Book) -> str:
        """Generate table of contents for the book."""
        toc_lines = ["# Table of Contents\n"]
        
        for chapter in book.chapters:
            toc_lines.append(f"## {chapter.order + 1}. {chapter.title}")
            # Add section headers from chapter content
            lines = chapter.content.split('\n')
            for line in lines:
                if line.startswith('### '):
                    toc_lines.append(f"   - {line[4:]}")
        
        return '\n'.join(toc_lines)

    def render_markdown(self, book: Book) -> str:
        """Render book as Markdown."""
        lines = [
            f"# {book.title}",
            f"## {book.subtitle}",
            f"**Author:** {book.author}",
            f"**Description:** {book.description}",
            "",
            "---",
            "",
            book.toc,
            "",
            "---",
            ""
        ]
        
        for chapter in book.chapters:
            lines.append(f"# Chapter {chapter.order + 1}: {chapter.title}")
            lines.append("")
            lines.append(chapter.content)
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return '\n'.join(lines)

    def render_html(self, book: Book) -> str:
        """Render book as HTML."""
        markdown = self.render_markdown(book)
        
        # Simple markdown to HTML conversion
        html = markdown
        html = html.replace('# ', '<h1>').replace('\n', '</h1>\n')
        html = html.replace('## ', '<h2>').replace('\n', '</h2>\n')
        html = html.replace('### ', '<h3>').replace('\n', '</h3>\n')
        html = html.replace('**', '<strong>').replace('**', '</strong>')
        html = html.replace('*', '<em>').replace('*', '</em>')
        html = html.replace('`', '<code>').replace('`', '</code>')
        html = html.replace('---', '<hr>')
        
        # Wrap in HTML template
        html_template = f"""<!DOCTYPE html>
<html>
<head>
    <title>{book.title}</title>
    <style>
        body {{ font-family: Georgia, serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }}
        h1 {{ color: #333; border-bottom: 2px solid #333; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        h3 {{ color: #777; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
        hr {{ border: none; border-top: 1px solid #ddd; margin: 30px 0; }}
    </style>
</head>
<body>
{html}
</body>
</html>"""
        
        return html_template
