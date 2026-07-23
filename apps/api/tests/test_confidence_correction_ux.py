"""
Milestone 11 (Confidence & Correction UX) tests.

Grounded in the implementation audit that produced
docs/milestones/MILESTONE_11.md: every field/route this milestone adds
already existed at the model layer (Resource.auto_*, Answer.sufficiency_reason)
or is a wholly new, additive table/route (resource_corrections,
GET .../corrections, POST .../reextract). These tests cover exactly the
Section 10 testing strategy: the new correction-history log (insert-on-PATCH,
workspace-scoped read), the four newly-exposed auto_* DocumentOut fields,
sufficiencyReason on AnswerOut/IntentResponse, and the new reextract route
(success/rejection cases) -- plus a regression check that /retry's existing
behavior is completely unaffected.
"""

from tests.pdf_helpers import make_sample_pdf

POLICY_TEXT = "The expense approval threshold for department managers is five thousand dollars per request."


def _upload_ready_document(client, tmp_path, filename="policy.pdf", text=POLICY_TEXT):
    pdf_path = tmp_path / filename
    make_sample_pdf(str(pdf_path), [text])
    with open(pdf_path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": (filename, f, "application/pdf")})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# -- 4.2: auto_* fields on DocumentOut ---------------------------------------


def test_document_out_exposes_auto_classification_fields(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "hw2.txt"
    path.write_text("Assignment 2\nSubmit by Friday. This homework covers the due date policy.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("hw2.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    detail = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert detail["autoContentCategory"] == "ASSIGNMENT"
    assert detail["autoContentCategoryConfidence"] is not None
    # never confirmed -- authoritative and auto_* fields still agree here
    assert detail["contentCategoryConfirmed"] is False


def test_auto_fields_keep_tracking_latest_run_after_confirmation(registered_client, tmp_path, monkeypatch):
    """The key behavior the audit flagged as missing from the API: auto_*
    keeps reflecting the latest automatic run independent of _confirmed
    state, distinct from the authoritative (now user-corrected) fields."""
    client, _ = registered_client
    path = tmp_path / "hw3.txt"
    path.write_text("Assignment 3\nSubmit by Monday. Homework due date is strict.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("hw3.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    client.patch(
        f"/api/v1/documents/{document_id}/classification",
        json={"contentCategory": "RESEARCH_PAPER", "subject": "Custom Subject"},
    )

    import app.services.ingestion_service as ingestion_module
    from app.services.classification import Classification

    class _FixedClassifier:
        def classify(self, text, filename):
            return Classification(
                category="LECTURE",
                category_confidence=0.9,
                subject="Auto Detected Subject",
                subject_confidence=0.8,
            )

    monkeypatch.setattr(ingestion_module, "get_classifier", lambda: _FixedClassifier())

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        ingestion_module.process_document(db, document_id)
    finally:
        db.close()

    detail = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert detail["contentCategory"] == "RESEARCH_PAPER"  # confirmed, unchanged
    assert detail["subject"] == "Custom Subject"  # confirmed, unchanged
    assert detail["autoContentCategory"] == "LECTURE"  # latest run, always updates
    assert detail["autoSubject"] == "Auto Detected Subject"


# -- 4.1: resource_corrections -----------------------------------------------


def test_classification_update_logs_one_correction_per_changed_field(registered_client, tmp_path):
    client, _ = registered_client
    document_id = _upload_ready_document(client, tmp_path)

    client.patch(
        f"/api/v1/documents/{document_id}/classification",
        json={"contentCategory": "RESEARCH_PAPER"},
    )

    corrections = client.get(f"/api/v1/documents/{document_id}/corrections").json()["items"]
    assert len(corrections) == 1
    assert corrections[0]["field"] == "CONTENT_CATEGORY"
    assert corrections[0]["newValue"] == "RESEARCH_PAPER"
    # previous_value/confidence captured as they stood *before* the overwrite
    assert corrections[0]["correctedAt"]


def test_correction_row_captures_pre_overwrite_value_and_confidence(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "hw2.txt"
    path.write_text("Assignment 2\nSubmit by Friday. This homework covers the due date policy.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("hw2.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    before = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert before["contentCategory"] == "ASSIGNMENT"
    prior_confidence = before["contentCategoryConfidence"]

    client.patch(
        f"/api/v1/documents/{document_id}/classification",
        json={"contentCategory": "RESEARCH_PAPER"},
    )

    corrections = client.get(f"/api/v1/documents/{document_id}/corrections").json()["items"]
    assert corrections[0]["previousValue"] == "ASSIGNMENT"
    assert corrections[0]["previousConfidence"] == prior_confidence
    assert corrections[0]["newValue"] == "RESEARCH_PAPER"


def test_changing_both_fields_in_one_request_inserts_two_corrections(registered_client, tmp_path):
    client, _ = registered_client
    document_id = _upload_ready_document(client, tmp_path)

    client.patch(
        f"/api/v1/documents/{document_id}/classification",
        json={"contentCategory": "RESEARCH_PAPER", "subject": "Distributed Systems"},
    )

    corrections = client.get(f"/api/v1/documents/{document_id}/corrections").json()["items"]
    assert len(corrections) == 2
    fields = {c["field"] for c in corrections}
    assert fields == {"CONTENT_CATEGORY", "SUBJECT"}


def test_corrections_are_returned_newest_first(registered_client, tmp_path):
    client, _ = registered_client
    document_id = _upload_ready_document(client, tmp_path)

    client.patch(f"/api/v1/documents/{document_id}/classification", json={"contentCategory": "LECTURE"})
    client.patch(f"/api/v1/documents/{document_id}/classification", json={"contentCategory": "ASSIGNMENT"})

    corrections = client.get(f"/api/v1/documents/{document_id}/corrections").json()["items"]
    assert len(corrections) == 2
    assert corrections[0]["newValue"] == "ASSIGNMENT"  # most recent first
    assert corrections[1]["newValue"] == "LECTURE"


def test_corrections_route_requires_auth(client):
    resp = client.get("/api/v1/documents/does-not-exist/corrections")
    assert resp.status_code == 401


def test_corrections_route_404s_on_unknown_document(registered_client):
    client, _ = registered_client
    resp = client.get("/api/v1/documents/does-not-exist/corrections")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_corrections_route_respects_workspace_isolation(registered_client, tmp_path):
    client, _ = registered_client
    document_id = _upload_ready_document(client, tmp_path, filename="private.pdf")
    client.patch(f"/api/v1/documents/{document_id}/classification", json={"contentCategory": "LECTURE"})

    from fastapi.testclient import TestClient

    from app.main import app

    other = TestClient(app)
    other.post(
        "/api/v1/auth/register",
        json={"email": "other-corrections@test.com", "password": "longenough123", "displayName": "Other"},
    )
    resp = other.get(f"/api/v1/documents/{document_id}/corrections")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


# -- 4.6: POST /documents/{id}/reextract -------------------------------------


def test_reextract_reprocesses_a_ready_document(registered_client, tmp_path):
    client, _ = registered_client
    document_id = _upload_ready_document(client, tmp_path)
    assert client.get(f"/api/v1/documents/{document_id}").json()["document"]["status"] == "READY"

    resp = client.post(f"/api/v1/documents/{document_id}/reextract")
    assert resp.status_code == 200, resp.text

    detail = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert detail["status"] == "READY"  # reprocessed the identical, still-extractable PDF


def test_reextract_rejects_a_failed_document(registered_client, tmp_path):
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

    reextract_resp = client.post(f"/api/v1/documents/{document_id}/reextract")
    assert reextract_resp.status_code == 409
    assert reextract_resp.json()["error"]["code"] == "DOCUMENT_NOT_READY"


def test_reextract_rejects_a_queued_document(registered_client, tmp_path):
    client, _ = registered_client
    document_id = _upload_ready_document(client, tmp_path)

    from app.db.session import SessionLocal
    from app.models.resource import Resource, ResourceStatus

    db = SessionLocal()
    try:
        resource = db.get(Resource, document_id)
        resource.status = ResourceStatus.QUEUED
        db.commit()
    finally:
        db.close()

    resp = client.post(f"/api/v1/documents/{document_id}/reextract")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "DOCUMENT_NOT_READY"


def test_reextract_route_requires_auth(client):
    resp = client.post("/api/v1/documents/does-not-exist/reextract")
    assert resp.status_code == 401


def test_reextract_route_404s_on_unknown_document(registered_client):
    client, _ = registered_client
    resp = client.post("/api/v1/documents/does-not-exist/reextract")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


# -- Regression: /retry must show zero behavior change -----------------------


def test_retry_still_rejects_ready_documents_unchanged(registered_client, tmp_path):
    """The exact scenario /reextract now serves for READY documents must
    still be rejected by the untouched /retry route -- proves the two
    routes are genuinely separate, not a re-implementation of one via the
    other."""
    client, _ = registered_client
    document_id = _upload_ready_document(client, tmp_path)

    retry_resp = client.post(f"/api/v1/documents/{document_id}/retry")
    assert retry_resp.status_code == 409
    assert retry_resp.json()["error"]["code"] == "DOCUMENT_NOT_FAILED"


def test_retry_still_reprocesses_failed_documents_unchanged(registered_client, tmp_path):
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

    retry_resp = client.post(f"/api/v1/documents/{document_id}/retry")
    assert retry_resp.status_code == 200
    detail = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert detail["status"] == "FAILED"  # same scanned PDF fails again, deterministically


# -- 4.3: sufficiencyReason on AnswerOut / IntentResponse --------------------


def test_answer_out_includes_sufficiency_reason(registered_client, tmp_path):
    client, _ = registered_client
    _upload_ready_document(client, tmp_path)

    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "What is the expense approval threshold for department managers?"},
    )
    assert resp.status_code == 201, resp.text
    answer = resp.json()["answer"]
    assert answer["sufficiencyReason"] in (
        "no_candidates",
        "strong_single_hit",
        "insufficient_supporting_hits",
        "below_min_score",
        "top_score",
    )


def test_intent_response_includes_sufficiency_reason_key(registered_client, tmp_path):
    """IntentResponse gains the field as an optional, additive addition --
    every existing intent handler continues to construct its response
    unchanged (Pydantic default), so the key must be present in the
    envelope even though this milestone does not modify any handler."""
    client, _ = registered_client
    _upload_ready_document(client, tmp_path)

    conv = client.post("/api/v1/conversations", json={}).json()
    resp = client.post(
        f"/api/v1/conversations/{conv['id']}/intents",
        json={"intent": "EXPLAIN", "question": "What is the expense approval threshold?"},
    )
    assert resp.status_code == 201, resp.text
    assert "sufficiencyReason" in resp.json()
