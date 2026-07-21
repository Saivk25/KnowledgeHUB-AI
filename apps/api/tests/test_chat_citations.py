"""
Deferred to Milestone 4 (RAG Chat + Citations).

These tests exercise the `/api/v1/conversations` router and the retrieval
pipeline, neither of which exist in Milestone 1 (Project Foundation).
`pytest.importorskip` means this module cleanly skips in the Milestone 1
environment (no PyMuPDF installed). Re-enable once auth, ingestion, and
chat routers are wired into app/main.py.
"""

import pytest

pytest.importorskip("fitz", reason="PyMuPDF is a Milestone 3 dependency, not installed in Milestone 1")

from tests.pdf_helpers import make_sample_pdf  # noqa: E402

POLICY_TEXT = "The expense approval threshold for department managers is five thousand dollars per request."


def _upload_ready_document(client, tmp_path, filename="policy.pdf", text=POLICY_TEXT):
    pdf_path = tmp_path / filename
    make_sample_pdf(str(pdf_path), [text])
    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": (filename, f, "application/pdf")})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_question_with_no_ready_documents_is_rejected(registered_client):
    client, _ = registered_client
    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "What is the policy?"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_READY_DOCUMENTS"


def test_answer_includes_citation_to_correct_document_and_page(registered_client, tmp_path):
    client, _ = registered_client
    document_id = _upload_ready_document(client, tmp_path)

    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "What is the expense approval threshold for department managers?"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["answer"]["status"] == "OK"
    assert body["answer"]["citations"], "expected at least one citation"

    first_citation = body["answer"]["citations"][0]
    assert first_citation["documentId"] == document_id
    assert first_citation["pageNumber"] == 1
    assert "expense approval threshold" in first_citation["excerpt"]
    assert f"[{first_citation['order']}]" in body["answer"]["content"]


def test_citations_never_cross_workspace_boundary(client, tmp_path):
    # Workspace A uploads and indexes a document.
    client.post(
        "/api/v1/auth/register",
        json={"email": "a@w.com", "password": "password123", "displayName": "A"},
    )
    client_a = client
    _upload_ready_document(client_a, tmp_path, filename="a.pdf", text=POLICY_TEXT)

    # A fresh client/session for workspace B must not see workspace A's evidence.
    from fastapi.testclient import TestClient

    from app.main import app

    client_b = TestClient(app)
    client_b.post(
        "/api/v1/auth/register",
        json={"email": "b@w.com", "password": "password123", "displayName": "B"},
    )
    conv_b = client_b.post("/api/v1/conversations", json={}).json()
    resp_b = client_b.post(
        f"/api/v1/conversations/{conv_b['id']}/messages",
        json={"content": "What is the expense approval threshold for department managers?"},
    )
    # Workspace B has no ready documents of its own, so it must be rejected
    # rather than silently answering from workspace A's index.
    assert resp_b.status_code == 422
    assert resp_b.json()["error"]["code"] == "NO_READY_DOCUMENTS"
