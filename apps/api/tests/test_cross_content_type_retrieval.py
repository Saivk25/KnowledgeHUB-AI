"""
Milestone 8: DRR Section 14 ("Also Important") -- retrieval ranking across
heterogeneous chunk types (PDF page vs. code function vs.
video-transcript segment) had no evaluation plan prior to this milestone.
This test builds a corpus with one resource of each type (reusing
Milestone 5's real extractors -- PdfExtractor via make_sample_pdf,
CodeExtractor for a .py file, and the YouTube transcript path via
Milestone 5's fetch_transcript monkeypatch seam, same as
test_youtube_ingestion.py) and confirms retrieval draws citations across
more than one content type rather than only ever favoring one.
"""

from tests.pdf_helpers import make_sample_pdf

SHARED_TOPIC = "photosynthesis rate calculation for plant leaves"


def test_retrieval_draws_citations_across_pdf_code_and_video_transcript(
    registered_client, tmp_path, monkeypatch
):
    client, _ = registered_client

    # PDF page.
    pdf_path = tmp_path / "biology_notes.pdf"
    make_sample_pdf(
        str(pdf_path),
        ["Photosynthesis converts sunlight into chemical energy inside plant leaves."],
    )
    with open(pdf_path, "rb") as f:
        resp_pdf = client.post(
            "/api/v1/documents", files={"file": ("biology_notes.pdf", f, "application/pdf")}
        )
    assert resp_pdf.status_code == 201, resp_pdf.text

    # Code function.
    code_path = tmp_path / "photosynthesis.py"
    code_path.write_text(
        "def calculate_photosynthesis_rate(leaf_area, light_intensity):\n"
        '    """Estimate the photosynthesis rate for a plant leaf."""\n'
        "    return leaf_area * light_intensity * 0.05\n"
    )
    with open(code_path, "rb") as f:
        resp_code = client.post("/api/v1/documents", files={"file": ("photosynthesis.py", f, "text/plain")})
    assert resp_code.status_code == 201, resp_code.text

    # Video transcript segment.
    import app.api.v1.routes.documents as documents_module

    transcript_text = (
        "In this video we walk through how to calculate the photosynthesis rate "
        "for plant leaves given leaf area and light intensity."
    )
    monkeypatch.setattr(documents_module, "fetch_transcript", lambda video_id: transcript_text)
    resp_video = client.post(
        "/api/v1/documents/youtube",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert resp_video.status_code == 201, resp_video.text

    document_ids = {resp_pdf.json()["id"], resp_code.json()["id"], resp_video.json()["id"]}
    for doc_id in document_ids:
        detail = client.get(f"/api/v1/documents/{doc_id}").json()
        assert detail["document"]["status"] == "READY", detail

    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": f"How is the {SHARED_TOPIC} calculated?"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["answer"]["citations"], "expected at least one citation across the mixed-type corpus"
    cited_document_ids = {c["documentId"] for c in body["answer"]["citations"]}
    # The evaluation gap DRR Section 14 called out: retrieval must not be
    # structurally biased toward a single content type when more than one
    # is genuinely relevant -- at least two of the three types should be
    # represented among the citations for a query that matches all three.
    assert (
        len(cited_document_ids) >= 2
    ), f"expected citations from at least 2 of the 3 content types, got {cited_document_ids}"
    assert cited_document_ids <= document_ids
