"""
Deferred to Milestone 3 (Document Ingestion Pipeline).

These tests exercise PDF upload, extraction, and chunking against the
`/api/v1/documents` router, which is not mounted in Milestone 1
(Project Foundation). `pytest.importorskip` also means this module cleanly
skips in the Milestone 1 environment, which does not install PyMuPDF (see
requirements.txt). Re-enable by removing this guard once the ingestion
router is wired into app/main.py and PyMuPDF is back in requirements.txt.
"""

import pytest

pytest.importorskip("fitz", reason="PyMuPDF is a Milestone 3 dependency, not installed in Milestone 1")

from tests.pdf_helpers import make_sample_pdf  # noqa: E402

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

    # TestClient runs BackgroundTasks synchronously, so ingestion has already
    # completed by the time this GET runs.
    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["document"]["status"] == "READY", detail
    assert detail["document"]["pageCount"] == 2
    assert detail["processingJob"]["step"] == "DONE"


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
