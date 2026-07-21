"""
Milestone 6 -- end-to-end classification tests: ingestion populates
category/subject, the correction API works, and a confirmed value survives
a later automatic reclassification pass (the approved "auto_* always
updates, authoritative fields only follow until confirmed" design -- see
docs/adr/0013-classification-confidence.md).
"""

from app.services.classification import Classification


def test_ingestion_populates_category_and_auto_fields(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "hw2.txt"
    path.write_text("Assignment 2\nSubmit by Friday. This homework covers the due date policy.")

    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("hw2.txt", f, "text/plain")})
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["id"]

    detail = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert detail["status"] == "READY"
    assert detail["contentCategory"] == "ASSIGNMENT"
    assert detail["contentCategoryConfidence"] is not None
    assert detail["contentCategoryConfirmed"] is False
    assert detail["extractionConfidence"] == 1.0

    from app.db.session import SessionLocal
    from app.models.resource import Resource

    db = SessionLocal()
    try:
        resource = db.get(Resource, document_id)
        assert resource.auto_content_category == "ASSIGNMENT"
        assert resource.auto_content_category_confidence is not None
    finally:
        db.close()


def test_classification_correction_confirms_and_updates(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "notes.txt"
    path.write_text("Some fairly generic study notes with no strong category signal at all.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("notes.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/documents/{document_id}/classification",
        json={"contentCategory": "RESEARCH_PAPER", "subject": "Distributed Systems"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body = patch_resp.json()
    assert body["contentCategory"] == "RESEARCH_PAPER"
    assert body["contentCategoryConfirmed"] is True
    assert body["contentCategoryConfidence"] == 1.0
    assert body["subject"] == "Distributed Systems"
    assert body["subjectConfirmed"] is True

    # persisted, not just echoed back
    detail = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert detail["contentCategory"] == "RESEARCH_PAPER"
    assert detail["subject"] == "Distributed Systems"


def test_confirmed_classification_survives_automatic_reclassification(
    registered_client, tmp_path, monkeypatch
):
    client, _ = registered_client
    path = tmp_path / "hw3.txt"
    path.write_text("Assignment 3\nSubmit by Monday. Homework due date is strict.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("hw3.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    confirm_resp = client.patch(
        f"/api/v1/documents/{document_id}/classification",
        json={"contentCategory": "RESEARCH_PAPER", "subject": "Custom Subject"},
    )
    assert confirm_resp.status_code == 200

    # Simulate a later automatic reclassification pass (e.g. a future
    # reprocessing run) returning a DIFFERENT category/subject, to prove the
    # confirmed value is not silently overwritten -- only the auto_* fields
    # should move.
    import app.services.ingestion_service as ingestion_module

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
    from app.models.resource import Resource

    db = SessionLocal()
    try:
        ingestion_module.process_document(db, document_id)
    finally:
        db.close()

    detail = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert detail["contentCategory"] == "RESEARCH_PAPER"  # unchanged -- confirmed
    assert detail["subject"] == "Custom Subject"  # unchanged -- confirmed

    db = SessionLocal()
    try:
        resource = db.get(Resource, document_id)
        assert resource.auto_content_category == "LECTURE"  # updated
        assert resource.auto_subject == "Auto Detected Subject"  # updated
    finally:
        db.close()


def test_classification_failure_degrades_gracefully_without_failing_resource(
    registered_client, tmp_path, monkeypatch
):
    import app.services.ingestion_service as ingestion_module

    class _BrokenClassifier:
        def classify(self, text, filename):
            raise RuntimeError("simulated classifier outage")

    monkeypatch.setattr(ingestion_module, "get_classifier", lambda: _BrokenClassifier())

    client, _ = registered_client
    path = tmp_path / "plain.txt"
    path.write_text("Some plain content for ingestion.")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("plain.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    detail = client.get(f"/api/v1/documents/{document_id}").json()["document"]
    assert detail["status"] == "READY"  # never fails solely due to classification
    assert detail["contentCategory"] == "OTHER"
    assert detail["contentCategoryConfidence"] == 0.0
    assert detail["subject"] is None


def test_classification_update_requires_at_least_one_field(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "x.txt"
    path.write_text("content")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("x.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    patch_resp = client.patch(f"/api/v1/documents/{document_id}/classification", json={})
    assert patch_resp.status_code == 422
    assert patch_resp.json()["error"]["code"] == "EMPTY_UPDATE"


def test_classification_update_rejects_invalid_category(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "y.txt"
    path.write_text("content")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("y.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/documents/{document_id}/classification",
        json={"contentCategory": "NOT_A_REAL_CATEGORY"},
    )
    assert patch_resp.status_code == 422
    assert patch_resp.json()["error"]["code"] == "INVALID_CATEGORY"


def test_classification_update_requires_auth(client):
    resp = client.patch("/api/v1/documents/does-not-exist/classification", json={"subject": "x"})
    assert resp.status_code == 401


def test_classification_update_respects_workspace_isolation(registered_client, tmp_path):
    client, _ = registered_client
    path = tmp_path / "private.txt"
    path.write_text("private content")
    with open(path, "rb") as f:
        resp = client.post("/api/v1/documents", files={"file": ("private.txt", f, "text/plain")})
    document_id = resp.json()["id"]

    from fastapi.testclient import TestClient

    from app.main import app

    other = TestClient(app)
    other.post(
        "/api/v1/auth/register",
        json={"email": "other-classify@test.com", "password": "longenough123", "displayName": "Other"},
    )
    patch_resp = other.patch(f"/api/v1/documents/{document_id}/classification", json={"subject": "hijack"})
    assert patch_resp.status_code == 404
