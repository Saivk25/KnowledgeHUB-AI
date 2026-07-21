"""
Milestone 7 -- concepts API route tests: list/detail/related/merge,
workspace isolation, and auth. Mirrors the exact conventions already
established for documents.py's own route tests (AppError codes,
workspace-scoped 404s, a genuinely separate TestClient for cross-workspace
isolation checks).
"""

from app.models.concept import ConceptRelationship, RelationshipType

ASSIGNMENT_TEXT = "Assignment 2\nSubmit by Friday. This homework covers the due date policy."


def _upload(client, tmp_path, filename, text):
    path = tmp_path / filename
    path.write_text(text)
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": (filename, f, "text/plain")})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_list_concepts_requires_auth(client):
    resp = client.get("/api/v1/concepts")
    assert resp.status_code == 401


def test_list_concepts_returns_created_concepts(registered_client, tmp_path):
    client, _ = registered_client
    document_id = _upload(client, tmp_path, "hw2.txt", ASSIGNMENT_TEXT)
    concepts = client.get(f"/api/v1/documents/{document_id}").json()["concepts"]
    concept_id = concepts[0]["conceptId"]

    resp = client.get("/api/v1/concepts")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(item["id"] == concept_id for item in items)
    matched = next(item for item in items if item["id"] == concept_id)
    assert matched["status"] == "ACTIVE"
    assert matched["evidenceCount"] == 1


def test_get_concept_detail_includes_evidence_and_related(registered_client, tmp_path):
    from app.db.session import SessionLocal

    client, _ = registered_client
    document_id = _upload(client, tmp_path, "hw2.txt", ASSIGNMENT_TEXT)
    concepts = client.get(f"/api/v1/documents/{document_id}").json()["concepts"]
    concept_id = concepts[0]["conceptId"]

    resp = client.get(f"/api/v1/concepts/{concept_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["concept"]["id"] == concept_id
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["resourceId"] == document_id
    assert body["evidence"][0]["contributionType"] == "APPLIES"
    assert body["evidence"][0]["excerpt"]  # non-empty, a real chunk excerpt
    assert body["related"] == []  # no relationships created by the local linker

    db = SessionLocal()
    try:
        assert db.query(ConceptRelationship).count() == 0
    finally:
        db.close()


def test_get_concept_detail_404_for_unknown_id(registered_client):
    client, _ = registered_client
    resp = client.get("/api/v1/concepts/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CONCEPT_NOT_FOUND"


def test_related_concepts_endpoint_traverses_manually_created_relationship(registered_client, tmp_path):
    from app.db.session import SessionLocal
    from app.models.concept import Concept
    from app.models.resource import ResourceChunk

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]
    document_id = _upload(client, tmp_path, "notes.txt", "some content")

    db = SessionLocal()
    try:
        chunk = db.query(ResourceChunk).filter(ResourceChunk.resource_id == document_id).first()
        a = Concept(workspace_id=workspace_id, name="A", normalized_name="a")
        b = Concept(workspace_id=workspace_id, name="B", normalized_name="b")
        db.add_all([a, b])
        db.flush()
        db.add(
            ConceptRelationship(
                workspace_id=workspace_id,
                from_concept_id=a.id,
                to_concept_id=b.id,
                relationship_type=RelationshipType.RELATED_TO,
                strength=0.7,
                evidence_chunk_id=chunk.id,
            )
        )
        db.commit()
        a_id, b_id = a.id, b.id
    finally:
        db.close()

    resp = client.get(f"/api/v1/concepts/{a_id}/related")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["conceptId"] == b_id
    assert items[0]["relationshipType"] == "RELATED_TO"
    assert items[0]["depth"] == 1


def test_merge_endpoint_success(registered_client, tmp_path):
    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    from app.db.session import SessionLocal
    from app.services import concept_graph

    db = SessionLocal()
    try:
        source = concept_graph.resolve_concept(db, workspace_id, "Merge Source").concept
        target = concept_graph.resolve_concept(db, workspace_id, "Merge Target").concept
        db.commit()
        source_id, target_id = source.id, target.id
    finally:
        db.close()

    resp = client.post(f"/api/v1/concepts/{source_id}/merge", json={"intoConceptId": target_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == target_id

    resp = client.get(f"/api/v1/concepts/{source_id}")
    assert resp.status_code == 200
    assert resp.json()["concept"]["status"] == "MERGED"


def test_merge_endpoint_rejects_self_merge(registered_client):
    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    from app.db.session import SessionLocal
    from app.services import concept_graph

    db = SessionLocal()
    try:
        concept = concept_graph.resolve_concept(db, workspace_id, "Solo").concept
        db.commit()
        concept_id = concept.id
    finally:
        db.close()

    resp = client.post(f"/api/v1/concepts/{concept_id}/merge", json={"intoConceptId": concept_id})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "MERGE_FAILED"


def test_concepts_are_workspace_isolated(registered_client, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app

    client, _ = registered_client
    document_id = _upload(client, tmp_path, "hw2.txt", ASSIGNMENT_TEXT)
    concept_id = client.get(f"/api/v1/documents/{document_id}").json()["concepts"][0]["conceptId"]

    other = TestClient(app)
    other.post(
        "/api/v1/auth/register",
        json={"email": "other-concepts@test.com", "password": "password123", "displayName": "Other"},
    )

    resp = other.get(f"/api/v1/concepts/{concept_id}")
    assert resp.status_code == 404

    resp = other.get("/api/v1/concepts")
    assert resp.status_code == 200
    assert all(item["id"] != concept_id for item in resp.json()["items"])
