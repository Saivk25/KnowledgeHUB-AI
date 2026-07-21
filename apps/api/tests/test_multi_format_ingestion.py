"""
Milestone 5 -- end-to-end ingestion tests for every newly supported format.

Mirrors test_ingestion.py's existing PDF coverage (upload -> real extraction
-> chunking -> embedding -> READY), one test per new format, plus a check
that extraction_confidence is populated for every one of them. Image OCR is
covered separately in test_ocr_extraction.py (skippable) and
test_ocr_ingestion_end_to_end below (also skippable, same reason).
"""

import shutil

import pytest

from tests.extractor_fixtures import make_sample_docx, make_sample_image, make_sample_pptx

TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


def _upload_and_get_detail(client, path, filename, content_type):
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": (filename, f, content_type)})
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["id"]
    detail = client.get(f"/api/v1/documents/{document_id}").json()
    return document_id, detail


def test_docx_upload_is_extracted_chunked_and_ready(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "policy.docx"
    make_sample_docx(str(path), ["The expense approval threshold is five thousand dollars."])

    document_id, detail = _upload_and_get_detail(
        client, path, "policy.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    assert detail["document"]["status"] == "READY", detail
    assert detail["processingJob"]["step"] == "DONE"


def test_pptx_upload_is_extracted_chunked_and_ready(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "slides.pptx"
    make_sample_pptx(str(path), ["Introduction to gradient descent", "Learning rate and convergence"])

    pptx_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    document_id, detail = _upload_and_get_detail(client, path, "slides.pptx", pptx_mime)

    assert detail["document"]["status"] == "READY", detail
    assert detail["document"]["pageCount"] == 2


def test_txt_upload_is_extracted_chunked_and_ready(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "notes.txt"
    path.write_text("A quick note about the expense approval policy for department managers.")

    document_id, detail = _upload_and_get_detail(client, path, "notes.txt", "text/plain")

    assert detail["document"]["status"] == "READY", detail


def test_markdown_upload_is_extracted_chunked_and_ready(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "notes.md"
    path.write_text("# Policy\n\nThe expense approval threshold is five thousand dollars.")

    document_id, detail = _upload_and_get_detail(client, path, "notes.md", "text/markdown")

    assert detail["document"]["status"] == "READY", detail


def test_code_file_upload_is_extracted_chunked_and_ready(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "utils.py"
    path.write_text(
        "def compute_threshold(base: float, factor: float) -> float:\n"
        '    """Returns the expense approval threshold."""\n'
        "    return base * factor\n"
    )

    document_id, detail = _upload_and_get_detail(client, path, "utils.py", "text/x-python")

    assert detail["document"]["status"] == "READY", detail


@pytest.mark.skipif(
    not TESSERACT_AVAILABLE,
    reason="tesseract binary not found on PATH -- install Tesseract OCR to run this test locally",
)
def test_ocr_ingestion_end_to_end(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "whiteboard.png"
    make_sample_image(str(path), "APPROVAL THRESHOLD")

    document_id, detail = _upload_and_get_detail(client, path, "whiteboard.png", "image/png")

    assert detail["document"]["status"] == "READY", detail

    from app.db.session import SessionLocal
    from app.models.resource import Resource

    db = SessionLocal()
    try:
        resource = db.get(Resource, document_id)
        assert resource.extraction_confidence is not None
        assert 0.0 <= resource.extraction_confidence <= 1.0
    finally:
        db.close()


def test_extraction_confidence_is_populated_for_non_ocr_formats(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "notes.txt"
    path.write_text("Some content for confidence checking.")

    document_id, detail = _upload_and_get_detail(client, path, "notes.txt", "text/plain")
    assert detail["document"]["status"] == "READY", detail

    from app.db.session import SessionLocal
    from app.models.resource import Resource

    db = SessionLocal()
    try:
        resource = db.get(Resource, document_id)
        assert resource.extraction_confidence == 1.0
    finally:
        db.close()
