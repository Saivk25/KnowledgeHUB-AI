"""
Milestone 12, Section 4.1: stale IngestionJob reconciliation.

Constructs Resource/IngestionJob rows directly (mirroring
tests/test_resource_model.py's pattern for schema-level behavior that the
API itself doesn't expose a route to trigger) rather than through the
upload route, since simulating a crashed-mid-job process means placing a
job in a state the real pipeline never leaves it in on its own.
"""

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings


def _make_running_job(db, workspace_id: str, *, started_minutes_ago: float):
    from app.models.ingestion_job import IngestionJob, IngestionStep
    from app.models.resource import Resource, ResourceContentSource, ResourceStatus

    resource = Resource(
        workspace_id=workspace_id,
        content_source=ResourceContentSource.FILE,
        status=ResourceStatus.PROCESSING,
        filename="stuck.pdf",
    )
    db.add(resource)
    db.flush()

    job = IngestionJob(
        resource_id=resource.id,
        status="RUNNING",
        step=IngestionStep.INDEXING,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago),
    )
    db.add(job)
    db.commit()
    db.refresh(resource)
    db.refresh(job)
    return resource, job


def test_stale_running_job_is_marked_failed_and_interrupted(registered_client):
    from app.db.session import SessionLocal
    from app.models.ingestion_job import IngestionStep
    from app.models.resource import ResourceStatus
    from app.services.job_reconciliation import INTERRUPTED_ERROR_CODE, reconcile_stale_jobs

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]
    threshold = get_settings().STALE_JOB_THRESHOLD_MINUTES

    db = SessionLocal()
    try:
        resource, job = _make_running_job(db, workspace_id, started_minutes_ago=threshold + 30)

        count = reconcile_stale_jobs(db)
        assert count == 1

        db.refresh(resource)
        db.refresh(job)
        assert resource.status == ResourceStatus.FAILED
        assert resource.error_message is not None
        assert job.status == "FAILED"
        assert job.step == IngestionStep.FAILED
        assert job.error_code == INTERRUPTED_ERROR_CODE
        assert job.completed_at is not None
    finally:
        db.close()


def test_recent_running_job_is_left_untouched(registered_client):
    from app.db.session import SessionLocal
    from app.models.resource import ResourceStatus
    from app.services.job_reconciliation import reconcile_stale_jobs

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]

    db = SessionLocal()
    try:
        resource, job = _make_running_job(db, workspace_id, started_minutes_ago=1)

        count = reconcile_stale_jobs(db)
        assert count == 0

        db.refresh(resource)
        db.refresh(job)
        assert resource.status == ResourceStatus.PROCESSING
        assert job.status == "RUNNING"
        assert job.error_code is None
    finally:
        db.close()


def test_reconciled_job_has_no_effect_on_a_second_pass(registered_client):
    """The reconciliation query only ever matches rows still `status ==
    "RUNNING"` -- running it twice in a row must not re-touch a job it
    already reconciled (idempotency of the check itself, independent of
    the Qdrant idempotency question this milestone separately resolved)."""
    from app.db.session import SessionLocal
    from app.services.job_reconciliation import reconcile_stale_jobs

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]
    threshold = get_settings().STALE_JOB_THRESHOLD_MINUTES

    db = SessionLocal()
    try:
        _make_running_job(db, workspace_id, started_minutes_ago=threshold + 30)

        first_pass = reconcile_stale_jobs(db)
        second_pass = reconcile_stale_jobs(db)
        assert first_pass == 1
        assert second_pass == 0
    finally:
        db.close()


def test_reconciled_resource_is_resumable_via_existing_retry_route(registered_client):
    """The recovery path is deliberately the existing, unchanged
    Milestone 3 retry endpoint -- confirms a reconciled resource is a
    completely ordinary FAILED resource from that route's point of view,
    not a new state it needs to special-case."""
    from app.db.session import SessionLocal
    from app.services.job_reconciliation import reconcile_stale_jobs

    client, _ = registered_client
    workspace_id = client.get("/api/v1/workspace").json()["workspace"]["id"]
    threshold = get_settings().STALE_JOB_THRESHOLD_MINUTES

    db = SessionLocal()
    try:
        resource, _job = _make_running_job(db, workspace_id, started_minutes_ago=threshold + 30)
        reconcile_stale_jobs(db)
        resource_id = resource.id
    finally:
        db.close()

    resp = client.post(f"/api/v1/documents/{resource_id}/retry")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "QUEUED"
