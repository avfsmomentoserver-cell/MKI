"""API router for book production."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mkc.core.auth import require_token
from mkc.core.database import get_session
from mkc.intelligence.books.structurer import BookStructurer, BookFormat
from mkc.models import GeneratedBook, BookChapter, KnowledgeObject

logger = logging.getLogger("mkc.api.books")

router = APIRouter(prefix="/books", tags=["books"])


@router.get("/")
async def list_books(structure_type: Optional[str] = None, 
                    limit: int = 50,
                    session: Session = Depends(get_session)):
    """List generated books."""
    query = session.query(GeneratedBook)
    
    if structure_type:
        query = query.filter(GeneratedBook.structure_type == structure_type)
    
    books = query.order_by(GeneratedBook.created_at.desc()).limit(limit).all()
    return [book.to_dict() for book in books]


@router.get("/{book_id}")
async def get_book(book_id: str, session: Session = Depends(get_session)):
    """Get a specific book by ID."""
    book = session.query(GeneratedBook).filter(
        GeneratedBook.id == book_id
    ).first()
    
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    return book.to_dict()


@router.get("/{book_id}/chapters")
async def get_book_chapters(book_id: str, session: Session = Depends(get_session)):
    """Get chapters for a specific book."""
    book = session.query(GeneratedBook).filter(
        GeneratedBook.id == book_id
    ).first()
    
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    chapters = session.query(BookChapter).filter(
        BookChapter.book_id == book_id
    ).order_by(BookChapter.order).all()
    
    return [chapter.to_dict() for chapter in chapters]


@router.post("/generate")
async def generate_book(title: str, 
                        structure_type: str = "topic_based",
                        session: Session = Depends(get_session)):
    """Generate a new book from knowledge objects."""
    # Get all knowledge objects
    knowledge_objects = session.query(KnowledgeObject).filter(
        KnowledgeObject.status == "active"
    ).all()
    
    ko_dicts = [ko.to_dict() for ko in knowledge_objects]
    
    structurer = BookStructurer()
    
    try:
        book = await structurer.structure_book(ko_dicts, title, structure_type)
        
        # Save book to database
        db_book = GeneratedBook(
            title=book.title,
            subtitle=book.subtitle,
            author=book.author,
            description=book.description,
            structure_type=structure_type,
            content_markdown=structurer.render_markdown(book),
            content_html=structurer.render_html(book),
            table_of_contents=book.toc,
            source_ko_ids=book.metadata.get("total_kos", []),
            chapter_count=len(book.chapters),
            metadata_json=book.metadata
        )
        session.add(db_book)
        session.commit()
        session.refresh(db_book)
        
        # Save chapters
        for chapter in book.chapters:
            db_chapter = BookChapter(
                book_id=db_book.id,
                title=chapter.title,
                content=chapter.content,
                order=chapter.order,
                source_ko_ids=chapter.source_ko_ids,
                metadata_json=chapter.metadata
            )
            session.add(db_chapter)
        
        session.commit()
        
        logger.info(f"Generated book: {db_book.id} ({title}) with {len(book.chapters)} chapters")
        return db_book.to_dict()
        
    except Exception as e:
        logger.error(f"Book generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{book_id}/export/{format}")
async def export_book(book_id: str, format: str, session: Session = Depends(get_session)):
    """Export a book in the specified format."""
    book = session.query(GeneratedBook).filter(
        GeneratedBook.id == book_id
    ).first()
    
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if format == "markdown":
        return {
            "format": "markdown",
            "content": book.content_markdown,
            "filename": f"{book.title.replace(' ', '_')}.md"
        }
    elif format == "html":
        return {
            "format": "html",
            "content": book.content_html,
            "filename": f"{book.title.replace(' ', '_')}.html"
        }
    elif format == "pdf":
        # PDF generation would require additional libraries (weasyprint, reportlab)
        # For now, return the HTML which can be converted to PDF
        return {
            "format": "html",  # Fallback to HTML
            "content": book.content_html,
            "filename": f"{book.title.replace(' ', '_')}.html",
            "note": "PDF export not yet implemented - use HTML and convert manually"
        }
    elif format == "epub":
        # EPUB generation would require additional libraries (ebooklib)
        # For now, return the markdown which can be converted to EPUB
        return {
            "format": "markdown",  # Fallback to markdown
            "content": book.content_markdown,
            "filename": f"{book.title.replace(' ', '_')}.md",
            "note": "EPUB export not yet implemented - use Markdown and convert manually"
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@router.delete("/{book_id}")
async def delete_book(book_id: str, session: Session = Depends(get_session)):
    """Delete a book."""
    book = session.query(GeneratedBook).filter(
        GeneratedBook.id == book_id
    ).first()
    
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Delete chapters first
    session.query(BookChapter).filter(BookChapter.book_id == book_id).delete()
    
    # Delete book
    session.delete(book)
    session.commit()
    
    return {"status": "deleted", "book_id": book_id}
