"""
Milestone 3 (Document Upload & Ingestion) tests.

Exercises the real pipeline end to end -- upload, PyMuPDF extraction,
chunking, embedding (LocalHashEmbeddingProvider, no API key needed), and
vector storage (InMemoryVectorRepository, since conftest.py points
QDRANT_URL at an unreachable port on purpose -- see get_vector_repository's
fallback). No mocks of the ingestion logic itself: TestClient runs
BackgroundTasks synchronously, so by the time an upload response comes
back, ingestion has already finished.
"""

from tests.pdf_helpers import make_sample_pdf

POLICY_TEXT = "The expense approval threshold for department managers is five thousand dollars."


def test_upload_valid_pdf_is_extracted_chunked_and_ready(registered_client, tmp_path):
    client, _ = registered_client
    pdf_path = tmp_path / "policy.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT, "Second page with additional filler content for chunking."])

    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents",
            files={"file": ("policy.pdf", f, "application/pdf")},
        )
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["id"]
    assert resp.json()["status"] in ("QUEUED", "PROCESSING", "READY")

    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["document"]["status"] == "READY", detail
    assert detail["document"]["pageCount"] == 2
    assert detail["processingJob"]["step"] == "DONE"


def test_ingestion_writes_chunks_and_vectors(registered_client, tmp_path):
    """
    The write path (chunking + embedding + Qdrant/in-memory upsert) is the
    actual Milestone 3 deliverable Milestone 4 will read from -- assert it
    actually happened, not just that the document's status flipped to READY.
    """
    from app.db.session import SessionLocal
    from app.models.resource import ResourceChunk
    from app.services.vector_repo import get_vector_repository

    client, _ = registered_client
    pdf_path = tmp_path / "policy.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT])

    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("policy.pdf", f, "application/pdf")})
    document_id = resp.json()["id"]

    db = SessionLocal()
    try:
        chunks = db.query(ResourceChunk).filter(ResourceChunk.resource_id == document_id).all()
        assert len(chunks) >= 1
        point_ids = {c.vector_point_id for c in chunks}
    finally:
        db.close()

    repo = get_vector_repository()
    any_point = repo._points[next(iter(point_ids))]
    results = repo.search([0.0] * 384, workspace_id=any_point.workspace_id, top_k=10)
    stored_ids = {r.point.id for r in results}
    assert point_ids.issubset(stored_ids), "chunk vector_point_ids were not found in the vector store"


def test_scanned_pdf_with_no_text_fails_with_clear_error(registered_client, tmp_path):
    """A PDF with no extractable text (e.g. a scanned image) must fail
    fast and honestly (ADR-0006), not silently index empty content."""
    import fitz

    client, _ = registered_client
    pdf_path = tmp_path / "scanned.pdf"
    doc = fitz.open()
    doc.new_page()  # blank page, zero extractable characters
    doc.save(str(pdf_path))
    doc.close()

    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("scanned.pdf", f, "application/pdf")})
    document_id = resp.json()["id"]

    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["document"]["status"] == "FAILED"
    assert detail["document"]["errorMessage"]
    assert detail["processingJob"]["errorCode"] == "SCANNED_PDF_UNSUPPORTED"


def test_non_pdf_upload_is_rejected(registered_client, tmp_path):
    client, _ = registered_client
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("not a pdf")
    with open(txt_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents",
            files={"file": ("notes.txt", f, "text/plain")},
        )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_empty_file_upload_is_rejected(registered_client):
    client, _ = registered_client
    resp = client.post("/api/v1/documents", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EMPTY_FILE"


def test_oversized_upload_is_rejected(registered_client):
    """Size is checked before any PDF parsing, so garbage bytes past the
    MAX_UPLOAD_MB limit are enough -- no need for a valid multi-megabyte PDF."""
    from app.core.config import get_settings

    client, _ = registered_client
    max_bytes = get_settings().MAX_UPLOAD_MB * 1024 * 1024
    oversized = b"0" * (max_bytes + 1024)
    resp = client.post("/api/v1/documents", files={"file": ("big.pdf", oversized, "application/pdf")})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_duplicate_pdf_upload_is_rejected(registered_client, tmp_path):
    client, _ = registered_client
    pdf_path = tmp_path / "dup.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT])

    with open(pdf_path, "rb") as f:
        first = client.post("/api/v1/documents", files={"file": ("dup.pdf", f, "application/pdf")})
    assert first.status_code == 201

    with open(pdf_path, "rb") as f:
        second = client.post("/api/v1/documents", files={"file": ("dup.pdf", f, "application/pdf")})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE_DOCUMENT"


def test_delete_document_removes_it_from_library(registered_client, tmp_path):
    client, _ = registered_client
    pdf_path = tmp_path / "delete-me.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT])
    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("delete-me.pdf", f, "application/pdf")})
    document_id = resp.json()["id"]

    delete_resp = client.delete(f"/api/v1/documents/{document_id}")
    assert delete_resp.status_code == 204

    listing = client.get("/api/v1/documents").json()
    assert all(d["id"] != document_id for d in listing["items"])


def test_delete_document_removes_its_vectors(registered_client, tmp_path):
    from app.services.vector_repo import get_vector_repository

    client, _ = registered_client
    pdf_path = tmp_path / "delete-vectors.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT])
    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("delete-vectors.pdf", f, "application/pdf")})
    document_id = resp.json()["id"]

    repo = get_vector_repository()
    before = [p for p in repo._points.values() if p.document_id == document_id]
    assert len(before) >= 1

    client.delete(f"/api/v1/documents/{document_id}")
    after = [p for p in repo._points.values() if p.document_id == document_id]
    assert after == []


def test_retry_reprocesses_a_failed_document(registered_client, tmp_path):
    import fitz

    client, _ = registered_client
    pdf_path = tmp_path / "scanned.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("scanned.pdf", f, "application/pdf")})
    document_id = resp.json()["id"]
    assert client.get(f"/api/v1/documents/{document_id}").json()["document"]["status"] == "FAILED"

    retry_resp = client.post(f"/api/v1/documents/{document_id}/retry")
    assert retry_resp.status_code == 200

    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["document"]["status"] == "FAILED"  # same scanned PDF fails again, deterministically


def test_retry_rejects_a_document_that_is_not_failed(registered_client, tmp_path):
    client, _ = registered_client
    pdf_path = tmp_path / "ready.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT])
    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("ready.pdf", f, "application/pdf")})
    document_id = resp.json()["id"]
    assert client.get(f"/api/v1/documents/{document_id}").json()["document"]["status"] == "READY"

    retry_resp = client.post(f"/api/v1/documents/{document_id}/retry")
    assert retry_resp.status_code == 409
    assert retry_resp.json()["error"]["code"] == "DOCUMENT_NOT_FAILED"


def test_document_routes_require_auth(client):
    assert client.get("/api/v1/documents").status_code == 401
    assert client.get("/api/v1/documents/does-not-exist").status_code == 401
    assert client.delete("/api/v1/documents/does-not-exist").status_code == 401


def test_document_not_found_returns_404(registered_client):
    client, _ = registered_client
    resp = client.get("/api/v1/documents/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_workspace_isolation_for_documents(client, tmp_path):
    """One account can never see, download, or delete another account's
    document -- the same tenant boundary enforced for workspaces in
    Milestone 2, now proven for the documents that live inside them."""
    pdf_path = tmp_path / "private.pdf"
    make_sample_pdf(str(pdf_path), [POLICY_TEXT])

    owner = client
    owner.post(
        "/api/v1/auth/register",
        json={"email": "owner@test.com", "password": "longenough123", "displayName": "Owner"},
    )
    with open(pdf_path, "rb") as f:
        upload = owner.post("/api/v1/documents", files={"file": ("private.pdf", f, "application/pdf")})
    document_id = upload.json()["id"]

    from fastapi.testclient import TestClient

    from app.main import app

    other = TestClient(app)
    other.post(
        "/api/v1/auth/register",
        json={"email": "other@test.com", "password": "longenough123", "displayName": "Other"},
    )

    assert other.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert other.get(f"/api/v1/documents/{document_id}/file").status_code == 404
    assert other.delete(f"/api/v1/documents/{document_id}").status_code == 404
    assert all(d["id"] != document_id for d in other.get("/api/v1/documents").json()["items"])
