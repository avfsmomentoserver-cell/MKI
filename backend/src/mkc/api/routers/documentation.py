"""API router for generated documentation."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mkc.core.auth import require_token
from mkc.core.database import get_session
from mkc.intelligence.documentation.generator import DocumentGenerator, DocType
from mkc.models import GeneratedDocument, DocumentUpdateTrigger, KnowledgeObject

logger = logging.getLogger("mkc.api.documentation")

router = APIRouter(prefix="/documentation", tags=["documentation"])


@router.get("/documents")
async def list_documents(doc_type: Optional[str] = None, 
                        limit: int = 50,
                        session: Session = Depends(get_session)):
    """List generated documents."""
    query = session.query(GeneratedDocument)
    
    if doc_type:
        query = query.filter(GeneratedDocument.doc_type == doc_type)
    
    documents = query.order_by(GeneratedDocument.updated_at.desc()).limit(limit).all()
    return [doc.to_dict() for doc in documents]


@router.get("/documents/{document_id}")
async def get_document(document_id: str, session: Session = Depends(get_session)):
    """Get a specific document by ID."""
    document = session.query(GeneratedDocument).filter(
        GeneratedDocument.id == document_id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document.to_dict()


@router.get("/documents/{document_id}/versions")
async def get_document_versions(document_id: str, session: Session = Depends(get_session)):
    """Get version history for a document."""
    document = session.query(GeneratedDocument).filter(
        GeneratedDocument.id == document_id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Collect all versions by following previous_version chain
    versions = []
    current = document
    while current:
        versions.append(current.to_dict())
        current = current.previous_version
    
    return versions


@router.post("/generate")
async def generate_document(doc_type: str, 
                           topic: Optional[str] = None,
                           session: Session = Depends(get_session)):
    """Generate a new document using AI."""
    # Get all knowledge objects
    knowledge_objects = session.query(KnowledgeObject).filter(
        KnowledgeObject.status == "active"
    ).all()
    
    ko_dicts = [ko.to_dict() for ko in knowledge_objects]
    
    generator = DocumentGenerator()
    
    try:
        if doc_type == "overview":
            doc = await generator.generate_overview(ko_dicts)
        elif doc_type == "api_reference":
            doc = await generator.generate_api_reference(ko_dicts)
        elif doc_type == "architecture":
            doc = await generator.generate_architecture_doc(ko_dicts)
        elif doc_type == "guide":
            if not topic:
                raise HTTPException(status_code=400, detail="Topic required for guide type")
            doc = await generator.generate_guide(ko_dicts, topic)
        elif doc_type == "changelog":
            doc = await generator.generate_changelog(ko_dicts)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown document type: {doc_type}")
        
        # Save to database
        db_doc = GeneratedDocument(
            title=doc.title,
            doc_type=doc.doc_type.value,
            content=doc.content,
            source_ko_ids=doc.source_ko_ids,
            version=doc.version,
            author=doc.author
        )
        session.add(db_doc)
        session.commit()
        session.refresh(db_doc)
        
        logger.info(f"Generated document: {db_doc.id} ({doc_type})")
        return db_doc.to_dict()
        
    except Exception as e:
        logger.error(f"Document generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{document_id}/regenerate")
async def regenerate_document(document_id: str, session: Session = Depends(get_session)):
    """Regenerate an existing document (creates new version)."""
    document = session.query(GeneratedDocument).filter(
        GeneratedDocument.id == document_id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get all knowledge objects
    knowledge_objects = session.query(KnowledgeObject).filter(
        KnowledgeObject.status == "active"
    ).all()
    
    ko_dicts = [ko.to_dict() for ko in knowledge_objects]
    
    generator = DocumentGenerator()
    
    try:
        # Regenerate based on doc_type
        if document.doc_type == "overview":
            doc = await generator.generate_overview(ko_dicts)
        elif document.doc_type == "api_reference":
            doc = await generator.generate_api_reference(ko_dicts)
        elif document.doc_type == "architecture":
            doc = await generator.generate_architecture_doc(ko_dicts)
        elif document.doc_type == "guide":
            # Extract topic from title
            topic = document.title.replace(" Guide", "").lower()
            doc = await generator.generate_guide(ko_dicts, topic)
        elif document.doc_type == "changelog":
            doc = await generator.generate_changelog(ko_dicts)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown document type: {document.doc_type}")
        
        # Save as new version
        new_doc = GeneratedDocument(
            title=doc.title,
            doc_type=doc.doc_type.value,
            content=doc.content,
            source_ko_ids=doc.source_ko_ids,
            version=document.version + 1,
            author="ai",
            previous_version_id=document.id
        )
        session.add(new_doc)
        session.commit()
        session.refresh(new_doc)
        
        logger.info(f"Regenerated document: {new_doc.id} (version {new_doc.version})")
        return new_doc.to_dict()
        
    except Exception as e:
        logger.error(f"Document regeneration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/triggers/pending")
async def get_pending_triggers(session: Session = Depends(get_session)):
    """Get pending document update triggers."""
    triggers = session.query(DocumentUpdateTrigger).filter(
        DocumentUpdateTrigger.processed == 0
    ).order_by(DocumentUpdateTrigger.triggered_at).all()
    
    return [trigger.to_dict() for trigger in triggers]


@router.post("/triggers/{trigger_id}/process")
async def process_trigger(trigger_id: str, session: Session = Depends(get_session)):
    """Process a document update trigger."""
    trigger = session.query(DocumentUpdateTrigger).filter(
        DocumentUpdateTrigger.id == trigger_id
    ).first()
    
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    
    if trigger.processed != 0:
        raise HTTPException(status_code=400, detail="Trigger already processed")
    
    # Mark as processing
    trigger.processed = 1
    session.commit()
    
    try:
        # Regenerate the associated document
        document = session.query(GeneratedDocument).filter(
            GeneratedDocument.id == trigger.document_id
        ).first()
        
        if document:
            # Call regenerate (simplified - in production would be async)
            # For now, just mark as completed
            trigger.processed = 2
            session.commit()
            
            return {"status": "completed", "trigger_id": trigger_id}
        else:
            trigger.processed = 2
            session.commit()
            return {"status": "completed", "trigger_id": trigger_id, "note": "Document not found"}
            
    except Exception as e:
        logger.error(f"Trigger processing failed: {e}")
        trigger.processed = 0  # Reset to pending
        session.commit()
        raise HTTPException(status_code=500, detail=str(e))
