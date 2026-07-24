"""
Milestone 12, Section 4.2: embedding-version tagging + re-embed tooling.

Uses the real ingestion/concept-linking pipeline (no mocks -- same
discipline as tests/test_ingestion.py and
tests/test_concept_linking_ingestion.py) against InMemoryVectorRepository
(conftest.py deliberately points QDRANT_URL at an unreachable port, so
get_vector_repository()/get_concept_vector_repository() fall back to it).
reembed.py's selective ("only re-embed stale points") behavior is
Qdrant-specific (see its own docstring); against the in-memory double
every point is always treated as needing re-embedding, which is exactly
what these tests rely on to prove point-count preservation and
workspace isolation deterministically.
"""

from app.models.concept import Concept

ASSIGNMENT_TEXT = "Assignment 2\nSubmit by Friday. This homework covers the due date policy."


def test_freshly_ingested_chunk_points_carry_embedding_model_version(registered_client, tmp_path):
    from app.services.embeddings import get_embedding_provider
    from app.services.vector_repo import get_vector_repository

    client, _ = registered_client
    path = tmp_path / "policy.txt"
    path.write_text("The expense approval threshold for department managers is five thousand dollars.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("policy.txt", f, "text/plain")})
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["id"]

    repo = get_vector_repository()
    points = [p for p in repo._points.values() if p.document_id == document_id]
    assert points, "expected at least one chunk vector point"
    expected_version = get_embedding_provider().version
    assert all(p.embedding_model_version == expected_version for p in points)


def test_freshly_linked_concept_point_carries_embedding_model_version(registered_client, tmp_path):
    from app.db.session import SessionLocal
    from app.services.embeddings import get_embedding_provider
    from app.services.vector_repo import get_concept_vector_repository

    client, _ = registered_client
    path = tmp_path / "embedding_version_concept.txt"
    path.write_text(ASSIGNMENT_TEXT)
    with open(path, "rb") as f:
        resp = client.post(
            "/api/v1/documents", files={"file": ("embedding_version_concept.txt", f, "text/plain")}
        )
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["id"]

    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert len(detail["concepts"]) == 1
    concept_id = detail["concepts"][0]["conceptId"]

    db = SessionLocal()
    try:
        concept = db.get(Concept, concept_id)
        assert concept is not None
    finally:
        db.close()

    concept_repo = get_concept_vector_repository()
    points = [p for p in concept_repo._points.values() if p.concept_id == concept_id]
    assert len(points) == 1
    assert points[0].embedding_model_version == get_embedding_provider().version


def test_reembed_chunks_preserves_point_count_and_fixes_stale_version(registered_client, tmp_path):
    from app.services.embeddings import get_embedding_provider
    from app.services.reembed import reembed_chunks
    from app.services.vector_repo import get_vector_repository

    client, payload = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    path = tmp_path / "reembed_chunks.txt"
    path.write_text("Some content about the reimbursement policy for this workspace.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("reembed_chunks.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    repo = get_vector_repository()
    before_ids = {p.id for p in repo._points.values() if p.document_id == document_id}
    assert before_ids

    # Simulate a stale corpus (as if these points were written by a prior,
    # different EmbeddingProvider) without touching the provider itself.
    for point_id in before_ids:
        repo._points[point_id].embedding_model_version = "old-fake-version"

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        count = reembed_chunks(db, workspace_id)
    finally:
        db.close()
    assert count == len(before_ids)

    after_ids = {p.id for p in repo._points.values() if p.document_id == document_id}
    assert after_ids == before_ids, "re-embedding must not change point count or point identity"
    expected_version = get_embedding_provider().version
    for point_id in after_ids:
        assert repo._points[point_id].embedding_model_version == expected_version


def test_reembed_concepts_preserves_point_count_and_fixes_stale_version(registered_client, tmp_path):
    from app.db.session import SessionLocal
    from app.services.embeddings import get_embedding_provider
    from app.services.reembed import reembed_concepts
    from app.services.vector_repo import get_concept_vector_repository

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    path = tmp_path / "reembed_concept_source.txt"
    path.write_text(ASSIGNMENT_TEXT)
    with open(path, "rb") as f:
        resp = client.post(
            "/api/v1/documents", files={"file": ("reembed_concept_source.txt", f, "text/plain")}
        )
    document_id = resp.json()["id"]
    concept_id = client.get(f"/api/v1/documents/{document_id}").json()["concepts"][0]["conceptId"]

    concept_repo = get_concept_vector_repository()
    before = {p.id for p in concept_repo._points.values() if p.concept_id == concept_id}
    assert len(before) == 1
    for point_id in before:
        concept_repo._points[point_id].embedding_model_version = "old-fake-version"

    db = SessionLocal()
    try:
        count = reembed_concepts(db, workspace_id)
    finally:
        db.close()
    assert count == 1

    after = [p for p in concept_repo._points.values() if p.concept_id == concept_id]
    assert len(after) == 1, "re-embedding a concept must net to the same point count"
    assert after[0].embedding_model_version == get_embedding_provider().version


def test_reembed_respects_workspace_isolation(client, tmp_path):
    from app.db.session import SessionLocal
    from app.services.reembed import reembed_chunks
    from app.services.vector_repo import get_vector_repository

    def _register_and_upload(email, filename, text):
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123", "displayName": "User"},
        )
        assert resp.status_code == 201, resp.text
        workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]
        path = tmp_path / filename
        path.write_text(text)
        with open(path, "rb") as f:
            upload = client.post("/api/v1/documents", files={"file": (filename, f, "text/plain")})
        assert upload.status_code == 201, upload.text
        client.post("/api/v1/auth/logout")
        return workspace_id, upload.json()["id"]

    ws_a, doc_a = _register_and_upload("reembed-iso-a@example.com", "a.txt", "Workspace A content.")
    ws_b, doc_b = _register_and_upload("reembed-iso-b@example.com", "b.txt", "Workspace B content.")

    repo = get_vector_repository()
    ids_a = {p.id for p in repo._points.values() if p.document_id == doc_a}
    ids_b = {p.id for p in repo._points.values() if p.document_id == doc_b}
    for point_id in ids_a | ids_b:
        repo._points[point_id].embedding_model_version = "old-fake-version"

    db = SessionLocal()
    try:
        count = reembed_chunks(db, ws_a)
    finally:
        db.close()
    assert count == len(ids_a)

    # Workspace A's points were fixed; workspace B's must be untouched.
    assert all(repo._points[pid].embedding_model_version != "old-fake-version" for pid in ids_a)
    assert all(repo._points[pid].embedding_model_version == "old-fake-version" for pid in ids_b)


def test_existing_vector_repository_behavior_is_unchanged(registered_client, tmp_path):
    """General regression: search()/upsert()/delete_by_document() still
    work exactly as before -- the new field is additive, not a behavior
    change to any existing VectorRepository method."""
    from app.services.vector_repo import get_vector_repository

    client, _ = registered_client
    path = tmp_path / "unchanged_behavior.txt"
    path.write_text("Some content for regression coverage.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("unchanged_behavior.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    repo = get_vector_repository()
    any_point = next(p for p in repo._points.values() if p.document_id == document_id)
    results = repo.search([0.0] * 384, workspace_id=any_point.workspace_id, top_k=10)
    assert any(r.point.document_id == document_id for r in results)

    repo.delete_by_document(document_id)
    assert not any(p.document_id == document_id for p in repo._points.values())
