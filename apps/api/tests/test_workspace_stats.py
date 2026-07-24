"""
Milestone 12 (Section 13 addendum) regression tests: `GET /workspace`'s
`stats` field.

Discovered live, during Item 4 (screenshot capture), that `stats` was
never populated -- `apps/web/app/chat/page.tsx` reads
`ws.stats?.readyDocuments ?? 0` to decide whether to show its compose UI
or a blocking "you need a Ready document" screen, so the missing field
left chat permanently unusable for every workspace regardless of actual
Ready document count. See docs/milestones/MILESTONE_12.md Section 13 for
the full discovery and Section 13.1 for this fix's design.

These tests create `Resource` rows directly against the test database
(same short-lived-session pattern `test_concept_resolution_concurrency.py`
uses) rather than through the real upload/ingestion pipeline, since only
each row's `status` matters here -- not real extraction/classification
behavior, which is already covered elsewhere.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.models.resource import Resource, ResourceStatus


def _make_resource(db, workspace_id: str, filename: str, status: str) -> None:
    db.add(
        Resource(
            workspace_id=workspace_id,
            filename=filename,
            storage_key=f"k-{filename}",
            mime_type="application/pdf",
            size_bytes=10,
            checksum=f"c-{filename}",
            status=status,
        )
    )


def test_workspace_stats_zero_resources(registered_client):
    """A brand-new workspace with no resources at all must report all
    three counts as zero -- this is exactly the state that should still
    show the chat page's "you need a Ready document" blocker."""
    client, _ = registered_client
    resp = client.get("/api/v1/workspace")
    assert resp.status_code == 200
    body = resp.json()
    assert "stats" in body
    assert body["stats"] == {"readyDocuments": 0, "processingDocuments": 0, "failedDocuments": 0}


def test_workspace_stats_counts_by_status(registered_client):
    """A workspace with a deliberate mix of every `ResourceStatus` value
    must report accurate per-bucket counts: two READY, one QUEUED and one
    PROCESSING both folding into processingDocuments (see
    WorkspaceStatsOut's docstring for why), and one FAILED."""
    client, body = registered_client
    workspace_id = body["workspace"]["id"]

    db = SessionLocal()
    try:
        _make_resource(db, workspace_id, "ready-1.pdf", ResourceStatus.READY)
        _make_resource(db, workspace_id, "ready-2.pdf", ResourceStatus.READY)
        _make_resource(db, workspace_id, "queued.pdf", ResourceStatus.QUEUED)
        _make_resource(db, workspace_id, "processing.pdf", ResourceStatus.PROCESSING)
        _make_resource(db, workspace_id, "failed.pdf", ResourceStatus.FAILED)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/v1/workspace")
    assert resp.status_code == 200
    assert resp.json()["stats"] == {
        "readyDocuments": 2,
        "processingDocuments": 2,
        "failedDocuments": 1,
    }


def test_workspace_stats_scoped_to_calling_workspace(registered_client):
    """Resources belonging to a different workspace must never be counted
    -- the same tenant-isolation guarantee every other query in this
    codebase enforces, exercised here for the new stats query specifically."""
    client, body = registered_client
    workspace_id = body["workspace"]["id"]

    from fastapi.testclient import TestClient

    from app.main import app

    other_client = TestClient(app)
    other_resp = other_client.post(
        "/api/v1/auth/register",
        json={"email": "other-workspace@example.com", "password": "password123", "displayName": "Other"},
    )
    other_workspace_id = other_resp.json()["workspace"]["id"]

    db = SessionLocal()
    try:
        _make_resource(db, workspace_id, "mine.pdf", ResourceStatus.READY)
        _make_resource(db, other_workspace_id, "theirs-1.pdf", ResourceStatus.READY)
        _make_resource(db, other_workspace_id, "theirs-2.pdf", ResourceStatus.READY)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/v1/workspace")
    assert resp.json()["stats"]["readyDocuments"] == 1

    other_stats_resp = other_client.get("/api/v1/workspace")
    assert other_stats_resp.json()["stats"]["readyDocuments"] == 2
