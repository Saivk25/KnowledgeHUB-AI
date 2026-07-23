"""
Milestone 9: end-to-end contract test proving the DRR Section 4 shared
envelope holds across all four intents via the real
POST /conversations/{id}/intents route, and that POST /messages
(Milestone 8, kept as a thin EXPLAIN-only wrapper) still works unchanged.
"""

from tests.pdf_helpers import make_sample_pdf

_ENVELOPE_KEYS = {
    "intent",
    "status",
    "provenance",
    "sufficiencyScore",
    "retrievalConfidence",
    "canOfferExternalFallback",
    "citations",
    "result",
}


def _upload_ready_pdf(
    client, tmp_path, filename="notes.pdf", text="Photosynthesis converts sunlight into chemical energy."
):
    pdf_path = tmp_path / filename
    make_sample_pdf(str(pdf_path), [text])
    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": (filename, f, "application/pdf")})
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]
    detail = client.get(f"/api/v1/documents/{doc_id}").json()
    assert detail["document"]["status"] == "READY", detail
    return doc_id


def test_explain_via_intents_matches_shared_envelope(registered_client, tmp_path):
    client, _ = registered_client
    _upload_ready_pdf(client, tmp_path)
    conv = client.post("/api/v1/conversations", json={}).json()

    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/intents",
        json={"intent": "EXPLAIN", "question": "What does photosynthesis convert?"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert _ENVELOPE_KEYS <= set(body.keys())
    assert body["intent"] == "EXPLAIN"
    assert body["result"]["kind"] == "explain"


def test_search_via_intents_returns_ranked_hits(registered_client, tmp_path):
    client, _ = registered_client
    _upload_ready_pdf(client, tmp_path)
    conv = client.post("/api/v1/conversations", json={}).json()

    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/intents",
        json={"intent": "SEARCH", "question": "photosynthesis sunlight energy"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert _ENVELOPE_KEYS <= set(body.keys())
    assert body["intent"] == "SEARCH"
    assert body["result"]["kind"] == "search"
    assert "hits" in body["result"]


def test_summarize_resource_via_intents(registered_client, tmp_path):
    client, _ = registered_client
    doc_id = _upload_ready_pdf(client, tmp_path)
    conv = client.post("/api/v1/conversations", json={}).json()

    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/intents",
        json={"intent": "SUMMARIZE", "resourceId": doc_id},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert _ENVELOPE_KEYS <= set(body.keys())
    assert body["result"]["kind"] == "summarize"
    assert body["provenance"] == "LOCAL"


def test_compare_two_resources_via_intents(registered_client, tmp_path):
    client, _ = registered_client
    doc_a = _upload_ready_pdf(client, tmp_path, "a.pdf", "Content about apples.")
    doc_b = _upload_ready_pdf(client, tmp_path, "b.pdf", "Content about oranges.")
    conv = client.post("/api/v1/conversations", json={}).json()

    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/intents",
        json={
            "intent": "COMPARE",
            "targets": [
                {"label": "Apples", "resourceId": doc_a},
                {"label": "Oranges", "resourceId": doc_b},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert _ENVELOPE_KEYS <= set(body.keys())
    assert body["result"]["kind"] == "compare"
    assert len(body["result"]["targets"]) == 2


def test_messages_endpoint_still_works_unchanged(registered_client, tmp_path):
    """POST /messages (Milestone 8) must still work exactly as before --
    a separate, full-fidelity EXPLAIN path, not replaced by /intents (see
    chat.py's create_intent docstring)."""
    client, _ = registered_client
    _upload_ready_pdf(client, tmp_path)
    conv = client.post("/api/v1/conversations", json={}).json()

    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "What does photosynthesis convert?"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "answer" in body
    assert body["answer"]["status"] in {"OK", "INSUFFICIENT"}
