"""
Milestone 8 (Local-First Retrieval & Provenance): exercises the
`/api/v1/conversations` router and the real retrieval pipeline end to end,
now that `chat.router` is mounted (see app/api/v1/router.py). Previously
deferred and unconditionally skipped since Milestone 4 -- see this
module's git history for that skip's own docstring.

DRR Section 10's adversarial test ("a query with zero relevant local
content must never receive a Local label") is
test_query_with_zero_relevant_content_is_never_labeled_local below -- the
one hard release gate FR-10 requires before this milestone can freeze.
"""

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.workspace import Workspace
from tests.pdf_helpers import make_sample_pdf

settings = get_settings()

POLICY_TEXT = "The expense approval threshold for department managers is five thousand dollars per request."
UNRELATED_QUESTION = (
    "What is the boiling point of liquid nitrogen in kelvin at standard atmospheric pressure?"
)


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
    assert body["answer"]["provenance"] == "LOCAL"
    assert body["answer"]["canOfferExternalFallback"] is False
    assert 0.0 <= body["answer"]["retrievalConfidence"] <= 1.0
    assert body["answer"]["citations"], "expected at least one citation"

    first_citation = body["answer"]["citations"][0]
    assert first_citation["documentId"] == document_id
    assert first_citation["pageNumber"] == 1
    assert "expense approval threshold" in first_citation["excerpt"]
    assert f"[{first_citation['order']}]" in body["answer"]["content"]


def test_local_answer_retrieval_latency_is_under_the_documented_target(registered_client, tmp_path):
    """DRR Section 5's first concrete, testable retrieval latency target
    (RETRIEVAL_LATENCY_TARGET_MS, config.py) is a P95 target -- a single
    request in a test suite cannot prove a percentile, so this is a floor
    sanity check only: the local, zero-config golden path (in-memory
    vector fallback, LocalHashEmbeddingProvider, no network calls) must
    stay comfortably under the target on one representative request, not
    a statistical guarantee. A real P95 measurement needs a load-testing
    harness, which is out of this milestone's approved scope."""
    client, _ = registered_client
    _upload_ready_document(client, tmp_path)

    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "What is the expense approval threshold for department managers?"},
    )
    assert resp.status_code == 201, resp.text
    # retrievalLatencyMs isn't in the API response (only stored on Answer),
    # so this reads it back from the persisted row -- the same value the
    # response's retrievalConfidence/citations were built alongside.
    from app.models.answer import Answer
    from app.models.conversation import Message

    db = SessionLocal()
    try:
        assistant_message = (
            db.query(Message)
            .filter(Message.conversation_id == conv["id"], Message.role == "assistant")
            .first()
        )
        answer_row = db.query(Answer).filter(Answer.message_id == assistant_message.id).first()
        assert answer_row.retrieval_latency_ms <= settings.RETRIEVAL_LATENCY_TARGET_MS, (
            f"retrieval took {answer_row.retrieval_latency_ms}ms, "
            f"target is {settings.RETRIEVAL_LATENCY_TARGET_MS}ms"
        )
    finally:
        db.close()


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


def test_query_with_zero_relevant_content_is_never_labeled_local(registered_client, tmp_path):
    """DRR Section 10's hard adversarial case (FR-10): a workspace with a
    real, ready document that has nothing to do with the question must
    still be answered INSUFFICIENT, never LOCAL -- sufficiency must never
    be assumed just because *some* document exists in the workspace."""
    client, _ = registered_client
    _upload_ready_document(client, tmp_path, text=POLICY_TEXT)

    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": UNRELATED_QUESTION},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["answer"]["status"] == "INSUFFICIENT"
    assert body["answer"]["provenance"] is None
    assert body["answer"]["canOfferExternalFallback"] is True
    assert body["answer"]["citations"] == []


def test_external_fallback_requires_explicit_consent(registered_client, tmp_path):
    """Insufficient evidence + no consent -> honest INSUFFICIENT, never a
    silent external call. The identical question, resent with explicit
    per-request consent, is answered from general knowledge instead and
    labeled EXTERNAL."""
    client, _ = registered_client
    _upload_ready_document(client, tmp_path, text=POLICY_TEXT)
    conv = client.post("/api/v1/conversations", json={}).json()

    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": UNRELATED_QUESTION},
    )
    assert resp.json()["answer"]["status"] == "INSUFFICIENT"

    resp2 = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": UNRELATED_QUESTION, "useExternalFallback": True},
    )
    assert resp2.status_code == 201, resp2.text
    body2 = resp2.json()
    assert body2["answer"]["status"] == "OK"
    assert body2["answer"]["provenance"] == "EXTERNAL"
    assert body2["answer"]["citations"] == []
    # Zero-config golden path (no OPENAI_API_KEY set in tests): an honest
    # degraded message, never a fabricated general-knowledge answer
    # (ADR-0004) -- ExtractiveFallbackProvider.answer_general_knowledge().
    assert "require a configured AI provider" in body2["answer"]["content"]


def test_workspace_allow_external_fallback_grants_consent_without_per_request_confirmation(
    registered_client, tmp_path
):
    """The workspace-level setting is an alternative consent path to the
    per-request flag, not a replacement for consent altogether."""
    client, reg = registered_client
    _upload_ready_document(client, tmp_path, text=POLICY_TEXT)

    db = SessionLocal()
    try:
        workspace = db.get(Workspace, reg["workspace"]["id"])
        workspace.allow_external_fallback = True
        db.commit()
    finally:
        db.close()

    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": UNRELATED_QUESTION},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["answer"]["status"] == "OK"
    assert body["answer"]["provenance"] == "EXTERNAL"


def test_hybrid_provenance_only_when_explicitly_requested_on_a_sufficient_answer(registered_client, tmp_path):
    """HYBRID must never be a silent blend of local evidence and general
    knowledge -- it only exists when the caller explicitly asks to
    supplement an already-sufficient local answer."""
    client, _ = registered_client
    _upload_ready_document(client, tmp_path)

    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={
            "content": "What is the expense approval threshold for department managers?",
            "useExternalFallback": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["answer"]["status"] == "OK"
    assert body["answer"]["provenance"] == "HYBRID"
    assert body["answer"]["citations"], "HYBRID must still carry the local citations"
    assert "not sourced from your documents" in body["answer"]["content"]
