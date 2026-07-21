"""
Milestone 5 -- YouTube transcript ingestion tests.

`extract_video_id` is pure and network-free, tested directly against real
URL strings. `fetch_transcript` is the one deliberate mock boundary in this
milestone (see app/services/youtube.py's docstring): it calls a real
third-party service, so tests monkeypatch it rather than hitting the network
-- but everything downstream of that seam (the route, Resource creation,
extraction via TextExtractor, chunking, embedding, vector indexing) runs for
real, same as every other ingestion test in this suite.
"""

import pytest

from app.services.youtube import InvalidYoutubeUrlError, extract_video_id


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id_accepts_known_youtube_url_shapes(url, expected_id):
    assert extract_video_id(url) == expected_id


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",  # not a YouTube host at all -- the SSRF guard
        "https://vimeo.com/12345",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",  # non-http(s) scheme
        "not a url",
        "https://www.youtube.com/watch?v=short",  # not an 11-char id
        "https://www.youtube.com/",  # no video id at all
    ],
)
def test_extract_video_id_rejects_non_youtube_or_malformed_urls(url):
    with pytest.raises(InvalidYoutubeUrlError):
        extract_video_id(url)


def test_youtube_ingestion_end_to_end(registered_client, monkeypatch):
    # Patched where the name is looked up (documents.py imports the name
    # directly, matching this codebase's existing import style -- see
    # get_embedding_provider in services/embeddings.py), not on the
    # defining module, which a direct-name import wouldn't pick up.
    import app.api.v1.routes.documents as documents_module

    transcript_text = (
        "Gradient descent is an optimization algorithm used to minimize a "
        "function by iteratively moving in the direction of steepest descent."
    )
    monkeypatch.setattr(documents_module, "fetch_transcript", lambda video_id: transcript_text)

    client, _ = registered_client
    resp = client.post(
        "/api/v1/documents/youtube",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["id"]

    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["document"]["status"] == "READY", detail
    assert detail["document"]["filename"] == "youtube_dQw4w9WgXcQ.txt"

    from app.db.session import SessionLocal
    from app.models.resource import ResourceChunk

    db = SessionLocal()
    try:
        chunks = db.query(ResourceChunk).filter(ResourceChunk.resource_id == document_id).all()
        assert len(chunks) >= 1
    finally:
        db.close()


def test_youtube_ingestion_rejects_non_youtube_url(registered_client):
    client, _ = registered_client
    resp = client.post("/api/v1/documents/youtube", json={"url": "https://example.com/video"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_YOUTUBE_URL"


def test_youtube_ingestion_reports_unavailable_transcript(registered_client, monkeypatch):
    import app.api.v1.routes.documents as documents_module
    from app.services.youtube import TranscriptUnavailableError

    def _raise(video_id):
        raise TranscriptUnavailableError("No transcript is available for this video.")

    monkeypatch.setattr(documents_module, "fetch_transcript", _raise)

    client, _ = registered_client
    resp = client.post(
        "/api/v1/documents/youtube",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "TRANSCRIPT_UNAVAILABLE"


def test_youtube_route_requires_auth(client):
    resp = client.post(
        "/api/v1/documents/youtube",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert resp.status_code == 401
