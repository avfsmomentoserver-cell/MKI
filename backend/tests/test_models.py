"""Model-level persistence tests on the ``mkc_test`` database.

Covers the Source -> Document -> KnowledgeObject chain, JSONB provenance
round-trips, ``to_dict()`` JSON-safe serialization (UUIDs/datetimes as
strings), and the ``Entity`` (name, kind) unique constraint.

Each test writes real rows and deletes them on teardown; all names/ids are
fresh per test, so nothing is shared across tests.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from mkc.models import Document, Entity, KnowledgeObject, Source


def _delete_chain(session, obj: KnowledgeObject, doc: Document | None, src: Source | None) -> None:
    """Remove knowledge object, then document, then source (FK-safe order)."""
    session.execute(delete(KnowledgeObject).where(KnowledgeObject.id == obj.id))
    if doc is not None:
        session.execute(delete(Document).where(Document.id == doc.id))
    if src is not None:
        session.execute(delete(Source).where(Source.id == src.id))
    session.commit()


def test_source_document_knowledge_chain_inserts_and_links(test_db) -> None:
    """A source, a document on it, and a knowledge object on that source persist and link."""
    session = test_db()
    try:
        src = Source(source_type="git", source_id=f"chain-{uuid.uuid4().hex[:8]}", path="/tmp/repo")
        session.add(src)
        session.flush()

        doc = Document(
            source_id=src.id,
            file_path="engine.py",
            file_hash="0" * 64,
            size_bytes=1024,
            doc_type="code",
            title="Chain doc",
        )
        session.add(doc)
        session.flush()

        obj = KnowledgeObject(
            type="hypothesis",
            title=f"chain-{uuid.uuid4().hex[:8]}",
            source_id=src.id,
            provenance={"source_location": "tests/test_models.py#chain"},
        )
        session.add(obj)
        session.commit()

        assert src.id is not None and doc.id is not None and obj.id is not None
        assert doc.source_id == src.id
        assert obj.source_id == src.id

        # Re-fetch in the same session to prove the rows are queryable.
        loaded = session.execute(
            select(KnowledgeObject).where(KnowledgeObject.id == obj.id)
        ).scalar_one()
        assert loaded.title == obj.title
        assert loaded.source_id == src.id
    finally:
        _delete_chain(session, obj, doc, src)
        session.close()


def test_provenance_jsonb_round_trips_through_a_new_session(test_db) -> None:
    """Nested JSONB provenance (unicode included) survives commit + a fresh session."""
    session = test_db()
    try:
        provenance = {
            "original_text": "vérité naïve — 知識",
            "extraction_method": "llm:gpt-4o",
            "source_type": "markdown",
            "source_location": "docs/KNOWLEDGE_MODEL.md#L12-L40",
            "author": "qa-bot",
            "nested": {"depth": 2, "counts": [1, 2, 3], "flag": True, "nil": None},
        }
        obj = KnowledgeObject(
            type="claim",
            title=f"prov-{uuid.uuid4().hex[:8]}",
            lifecycle_state="unknown",
            provenance=provenance,
        )
        session.add(obj)
        session.commit()
        obj_id = obj.id
    finally:
        session.close()

    # New session: the value comes back from Postgres JSONB, not the ORM cache.
    session2 = test_db()
    try:
        loaded = session2.get(KnowledgeObject, obj_id)
        assert loaded is not None
        assert loaded.provenance == provenance
        assert loaded.provenance["nested"]["counts"] == [1, 2, 3]
        assert loaded.provenance["author"] == "qa-bot"
    finally:
        session2.execute(delete(KnowledgeObject).where(KnowledgeObject.id == obj_id))
        session2.commit()
        session2.close()


def test_to_dict_serializes_uuids_and_datetimes_to_strings(test_db) -> None:
    """to_dict() is JSON-safe: UUIDs and datetimes become strings; json.dumps works."""
    session = test_db()
    try:
        src = Source(source_type="markdown", source_id=f"ser-{uuid.uuid4().hex[:8]}")
        session.add(src)
        session.flush()
        obj = KnowledgeObject(
            type="fact",
            title=f"ser-{uuid.uuid4().hex[:8]}",
            content_summary="summary",
            body="body",
            source_id=src.id,
            provenance={"source_location": "tests/test_models.py#ser"},
        )
        session.add(obj)
        session.commit()
        session.refresh(obj)

        data = obj.to_dict()
        assert isinstance(data["id"], str)
        assert uuid.UUID(data["id"]) == obj.id
        assert data["source_id"] == str(src.id)
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)
        assert datetime.fromisoformat(data["created_at"]).tzinfo is not None
        assert datetime.fromisoformat(data["updated_at"]).tzinfo is not None
        # Whole payload is JSON-serializable without custom encoders.
        json.dumps(data)

        src_data = src.to_dict()
        assert isinstance(src_data["id"], str)
        assert isinstance(src_data["indexed_at"], str)
        json.dumps(src_data)
    finally:
        _delete_chain(session, obj, None, src)
        session.close()


def test_knowledge_object_without_source_serializes_source_id_as_none(test_db) -> None:
    session = test_db()
    try:
        obj = KnowledgeObject(
            type="question",
            title=f"nosrc-{uuid.uuid4().hex[:8]}",
            provenance={"source_location": "tests/test_models.py#nosrc"},
        )
        session.add(obj)
        session.commit()
        session.refresh(obj)
        assert obj.source_id is None
        assert obj.to_dict()["source_id"] is None
    finally:
        _delete_chain(session, obj, None, None)
        session.close()


def test_entity_unique_constraint_name_plus_kind_is_enforced(test_db) -> None:
    """(name, kind) is unique: duplicate pair -> IntegrityError, other kind -> OK."""
    name = f"engine-{uuid.uuid4().hex[:8]}"
    session = test_db()
    created: list[Entity] = []
    try:
        first = Entity(name=name, kind="module")
        session.add(first)
        session.commit()
        created.append(first)

        duplicate = Entity(name=name, kind="module")
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Same name, different kind: allowed.
        other = Entity(name=name, kind="person")
        session.add(other)
        session.commit()
        created.append(other)

        rows = session.execute(select(Entity.id).where(Entity.name == name)).all()
        assert len(rows) == 2
    finally:
        for entity in created:
            session.execute(delete(Entity).where(Entity.id == entity.id))
        session.commit()
        session.close()


def test_document_requires_existing_source(test_db) -> None:
    """A Document pointing at a missing source violates the FK (no orphans)."""
    session = test_db()
    try:
        doc = Document(
            source_id=uuid.uuid4(),
            file_path="orphan.py",
            file_hash="1" * 64,
        )
        session.add(doc)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()
