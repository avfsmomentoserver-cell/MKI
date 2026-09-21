"""Knowledge object CRUD tests against the live ``mkc_test`` database.

Pins the API contract in ``src/mkc/api/routers/knowledge.py``:

- POST  -> 201, envelope ``{"object": ...}``; 400 on enum/provenance violations.
- GET   -> PagedResponse with type / lifecycle_state / status / q filters and
  page / page_size; detail view includes provenance + source chain; 404
  envelope for unknown/malformed ids (no oracle).
- PATCH -> lifecycle-validated; 409 + ``allowed_next_states`` on violation;
  provenance is immutable by API policy and stays unchanged.

Every row created through the API is deleted by the ``creator`` fixture.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import delete, select

from mkc.core.database import get_session_factory
from mkc.core.lifecycle import allowed_next_states
from mkc.models import AuditLog, KnowledgeObject, Source


@pytest.fixture
def creator(client, auth_headers):
    """POST helper that auto-deletes every knowledge object it creates."""
    created: list[str] = []

    def post(payload: dict[str, Any]) -> Any:
        response = client.post("/api/v1/knowledge", headers=auth_headers, json=payload)
        if response.status_code == 201:
            created.append(response.json()["object"]["id"])
        return response

    yield post

    if created:
        session = get_session_factory()()
        try:
            session.execute(
                delete(KnowledgeObject).where(KnowledgeObject.id.in_([uuid.UUID(i) for i in created]))
            )
            session.commit()
        finally:
            session.close()


def _payload(title: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "hypothesis",
        "title": title,
        "provenance": {"source_location": "tests/test_crud_knowledge.py"},
    }
    payload.update(overrides)
    return payload


def test_create_returns_201_with_defaults_and_shows_in_list(creator, client, auth_headers) -> None:
    title = f"crud-{uuid.uuid4().hex[:10]}"
    response = creator(_payload(title))
    assert response.status_code == 201
    obj = response.json()["object"]
    assert obj["id"]
    assert obj["type"] == "hypothesis"
    assert obj["title"] == title
    assert obj["lifecycle_state"] == "unknown"  # default when omitted
    assert obj["confidence"] == 0.5
    assert obj["status"] == "active"
    assert obj["provenance"] == {"source_location": "tests/test_crud_knowledge.py"}
    assert isinstance(obj["created_at"], str)
    assert isinstance(obj["updated_at"], str)

    listed = client.get("/api/v1/knowledge", headers=auth_headers, params={"q": title})
    assert listed.status_code == 200
    body = listed.json()
    assert [item["id"] for item in body["items"]] == [obj["id"]]
    assert body["total"] == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"provenance": {}},  # source_location missing
        {"provenance": {"source_location": ""}},  # empty location
        {"type": "not-a-type"},
        {"lifecycle_state": "not-a-state"},
        {"status": "retired"},
    ],
)
def test_create_rejects_invalid_payloads(creator, overrides: dict[str, Any]) -> None:
    response = creator(_payload(f"bad-{uuid.uuid4().hex[:8]}", **overrides))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},  # min_length=1
        {"confidence": 1.5},  # le=1.0
    ],
)
def test_create_rejects_schema_violations_with_422(creator, overrides: dict[str, Any]) -> None:
    payload = _payload(f"schema-{uuid.uuid4().hex[:8]}")
    payload.update(overrides)
    response = creator(payload)
    assert response.status_code == 422


def test_create_with_source_id_round_trips(creator, client, auth_headers) -> None:
    session = get_session_factory()()
    src = Source(source_type="git", source_id=f"crud-src-{uuid.uuid4().hex[:8]}", path="/tmp/repo")
    session.add(src)
    session.commit()
    try:
        title = f"src-{uuid.uuid4().hex[:8]}"
        response = creator(_payload(title, source_id=str(src.id)))
        assert response.status_code == 201
        assert response.json()["object"]["source_id"] == str(src.id)
    finally:
        session.execute(delete(Source).where(Source.id == src.id))
        session.commit()
        session.close()


def test_create_with_bad_source_id_is_400(creator) -> None:
    response = creator(_payload(f"src-{uuid.uuid4().hex[:8]}", source_id="not-a-uuid"))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_source_id"

    response = creator(_payload(f"src-{uuid.uuid4().hex[:8]}", source_id=str(uuid.uuid4())))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_source"


def test_list_filters_by_type_lifecycle_state_and_status(creator, client, auth_headers) -> None:
    marker = uuid.uuid4().hex[:10]
    a = creator(_payload(f"filt-{marker}-a", type="hypothesis")).json()["object"]
    b = creator(_payload(f"filt-{marker}-b", type="hypothesis", lifecycle_state="idea")).json()["object"]
    c = creator(
        _payload(f"filt-{marker}-c", type="fact", lifecycle_state="idea", status="archived")
    ).json()["object"]

    base = {"q": f"filt-{marker}"}
    by_type = client.get(
        "/api/v1/knowledge", headers=auth_headers, params={**base, "type": "hypothesis"}
    ).json()
    assert {item["id"] for item in by_type["items"]} == {a["id"], b["id"]}
    assert by_type["total"] == 2

    by_state = client.get(
        "/api/v1/knowledge", headers=auth_headers, params={**base, "lifecycle_state": "idea"}
    ).json()
    assert {item["id"] for item in by_state["items"]} == {b["id"], c["id"]}
    assert by_state["total"] == 2

    by_status = client.get(
        "/api/v1/knowledge", headers=auth_headers, params={**base, "status": "archived"}
    ).json()
    assert {item["id"] for item in by_status["items"]} == {c["id"]}
    assert by_status["total"] == 1

    combined = client.get(
        "/api/v1/knowledge",
        headers=auth_headers,
        params={**base, "type": "hypothesis", "lifecycle_state": "idea", "status": "active"},
    ).json()
    assert {item["id"] for item in combined["items"]} == {b["id"]}


def test_list_pagination_envelope(creator, client, auth_headers) -> None:
    marker = uuid.uuid4().hex[:10]
    ids = {
        creator(_payload(f"page-{marker}-{i}")).json()["object"]["id"]
        for i in range(3)
    }

    first = client.get(
        "/api/v1/knowledge", headers=auth_headers, params={"q": f"page-{marker}", "page": 1, "page_size": 2}
    ).json()
    assert first["total"] == 3
    assert first["page"] == 1
    assert first["page_size"] == 2
    assert len(first["items"]) == 2

    second = client.get(
        "/api/v1/knowledge", headers=auth_headers, params={"q": f"page-{marker}", "page": 2, "page_size": 2}
    ).json()
    assert second["page"] == 2
    assert len(second["items"]) == 1
    assert {item["id"] for item in first["items"]} | {item["id"] for item in second["items"]} == ids

    beyond = client.get(
        "/api/v1/knowledge", headers=auth_headers, params={"q": f"page-{marker}", "page": 3, "page_size": 2}
    ).json()
    assert beyond["items"] == []
    assert beyond["total"] == 3


def test_get_by_id_includes_provenance_and_source_chain(creator, client, auth_headers) -> None:
    provenance = {
        "original_text": "the engine scales",
        "extraction_method": "manual",
        "source_type": "markdown",
        "source_location": "docs/NOTE.md#L3",
        "author": "qa-bot",
    }
    obj = creator(_payload(f"get-{uuid.uuid4().hex[:8]}", provenance=provenance)).json()["object"]

    response = client.get(f"/api/v1/knowledge/{obj['id']}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["object"]
    assert body["provenance"] == provenance
    assert body["source"] is None
    assert body["provenance_chain"] == {"object": provenance, "source": None}


def test_get_unknown_and_malformed_ids_are_404(client, auth_headers) -> None:
    for identifier in (str(uuid.uuid4()), "not-a-uuid", "123"):
        response = client.get(f"/api/v1/knowledge/{identifier}", headers=auth_headers)
        assert response.status_code == 404, identifier
        assert response.json()["detail"]["code"] == "not_found"


def test_patch_valid_transition_updates_state_and_audits(creator, client, auth_headers) -> None:
    obj = creator(_payload(f"patch-{uuid.uuid4().hex[:8]}", lifecycle_state="idea")).json()["object"]
    assert obj["lifecycle_state"] == "idea"

    response = client.patch(
        f"/api/v1/knowledge/{obj['id']}",
        headers=auth_headers,
        json={"lifecycle_state": "question", "actor": "auto"},
    )
    assert response.status_code == 200
    assert response.json()["object"]["lifecycle_state"] == "question"

    # Persisted + audited with the from-state recorded.
    session = get_session_factory()()
    try:
        assert session.get(KnowledgeObject, uuid.UUID(obj["id"])).lifecycle_state == "question"
        row = session.execute(
            select(AuditLog).where(
                AuditLog.action == "knowledge.lifecycle_transition", AuditLog.object_id == obj["id"]
            )
        ).scalar_one()
        assert row.details["from_state"] == "idea"
        assert row.details["lifecycle_state"] == "question"
    finally:
        session.close()


def test_patch_invalid_transition_returns_409_with_allowed_next_states(creator, client, auth_headers) -> None:
    obj = creator(_payload(f"conflict-{uuid.uuid4().hex[:8]}", lifecycle_state="hypothesis")).json()["object"]

    response = client.patch(
        f"/api/v1/knowledge/{obj['id']}",
        headers=auth_headers,
        json={"lifecycle_state": "production", "actor": "auto"},
    )
    assert response.status_code == 409
    error = response.json()["detail"]
    assert error["code"] == "invalid_transition"
    assert error["from_state"] == "hypothesis"
    assert error["to_state"] == "production"
    assert error["allowed_next_states"] == allowed_next_states("hypothesis")

    # State unchanged after the rejected attempt.
    fetched = client.get(f"/api/v1/knowledge/{obj['id']}", headers=auth_headers).json()["object"]
    assert fetched["lifecycle_state"] == "hypothesis"


def test_patch_self_transition_returns_409(creator, client, auth_headers) -> None:
    obj = creator(_payload(f"self-{uuid.uuid4().hex[:8]}", lifecycle_state="idea")).json()["object"]
    response = client.patch(
        f"/api/v1/knowledge/{obj['id']}",
        headers=auth_headers,
        json={"lifecycle_state": "idea", "actor": "auto"},
    )
    assert response.status_code == 409
    assert "state unchanged" in response.json()["detail"]["detail"]


def test_patch_human_required_state_rejects_automated_actor(creator, client, auth_headers) -> None:
    obj = creator(_payload(f"human-{uuid.uuid4().hex[:8]}", lifecycle_state="validated")).json()["object"]

    rejected = client.patch(
        f"/api/v1/knowledge/{obj['id']}",
        headers=auth_headers,
        json={"lifecycle_state": "implemented", "actor": "auto"},
    )
    assert rejected.status_code == 409
    assert "human" in rejected.json()["detail"]["detail"]

    accepted = client.patch(
        f"/api/v1/knowledge/{obj['id']}",
        headers=auth_headers,
        json={"lifecycle_state": "implemented", "actor": "qa-human"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["object"]["lifecycle_state"] == "implemented"


def test_patch_unknown_lifecycle_state_is_400(creator, client, auth_headers) -> None:
    obj = creator(_payload(f"badstate-{uuid.uuid4().hex[:8]}", lifecycle_state="idea")).json()["object"]
    response = client.patch(
        f"/api/v1/knowledge/{obj['id']}", headers=auth_headers, json={"lifecycle_state": "not-a-state"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "validation_error"


def test_patch_cannot_alter_provenance(creator, client, auth_headers) -> None:
    provenance = {"source_location": "tests/test_crud_knowledge.py", "author": "qa-bot"}
    obj = creator(_payload(f"immut-{uuid.uuid4().hex[:8]}", provenance=provenance)).json()["object"]

    # The schema has no provenance field; the client sends one anyway.
    response = client.patch(
        f"/api/v1/knowledge/{obj['id']}",
        headers=auth_headers,
        json={"title": "retitled", "provenance": {"source_location": "TAMPERED", "author": "attacker"}},
    )
    assert response.status_code == 200
    assert response.json()["object"]["title"] == "retitled"

    # The tamper is ignored: provenance is byte-identical.
    fetched = client.get(f"/api/v1/knowledge/{obj['id']}", headers=auth_headers).json()["object"]
    assert fetched["provenance"] == provenance
    assert fetched["provenance_chain"]["object"] == provenance


def test_patch_updates_mutable_fields_and_audits(creator, client, auth_headers) -> None:
    obj = creator(_payload(f"mut-{uuid.uuid4().hex[:8]}")).json()["object"]
    response = client.patch(
        f"/api/v1/knowledge/{obj['id']}",
        headers=auth_headers,
        json={"title": "mutated", "confidence": 0.9, "status": "archived", "actor": "qa-bot"},
    )
    assert response.status_code == 200
    body = response.json()["object"]
    assert body["title"] == "mutated"
    assert body["confidence"] == 0.9
    assert body["status"] == "archived"

    session = get_session_factory()()
    try:
        row = session.execute(
            select(AuditLog).where(AuditLog.action == "knowledge.update", AuditLog.object_id == obj["id"])
        ).scalar_one()
        assert row.details["title"] == "mutated"
        assert row.actor == "qa-bot"
    finally:
        session.close()


def test_patch_unknown_id_is_404(client, auth_headers) -> None:
    response = client.patch(f"/api/v1/knowledge/{uuid.uuid4()}", headers=auth_headers, json={"title": "x"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"
