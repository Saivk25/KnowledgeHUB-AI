"""
Stale ingestion-job reconciliation.

Milestone 12 (Production Hardening & Portfolio Polish), Section 4.1 of
docs/milestones/MILESTONE_12.md: ADR-0005's own accepted limitation
("BackgroundTask crash loses the in-flight job") was scoped against a
single, four-stage pipeline; the pipeline has since grown to six stages
(extract -> classify -> chunk -> embed -> index -> concept-link -- see
app/models/ingestion_job.py's IngestionStep). A crash between any two
stages leaves the IngestionJob row `status == "RUNNING"` forever, with no
detection or resumption mechanism -- the resource is silently stuck,
indistinguishable from a job that's just taking a long time.

Design decision (MILESTONE_12.md Section 4.1, approved): retain
BackgroundTask (ADR-0005 reconfirmed, no task-queue migration); close
this specific, narrow gap with a bounded, indexed reconciliation query
that marks orphaned `RUNNING` jobs `FAILED` with a distinct error code,
so the existing, unchanged retry/reextract endpoints (Milestone 3/11)
become the recovery path. This module adds no new pipeline stage, and
does not touch `process_document`'s stage logic in
app/services/ingestion_service.py.

Mirrors `process_document`'s own `_fail()` closure (ingestion_service.py)
for how a resource/job pair is marked failed, rather than inventing a
second convention for the same state transition.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ingestion_job import IngestionJob, IngestionStep
from app.models.resource import Resource, ResourceStatus

logger = logging.getLogger(__name__)

# Distinct from every error_code process_document() itself ever sets
# (UNSUPPORTED_FILE_TYPE, SCANNED_PDF_UNSUPPORTED, NO_EXTRACTABLE_TEXT,
# INGESTION_ERROR, or an ExtractionError subclass's own code) so a
# reconciled job is always distinguishable in the UI/logs from one that
# actually ran to a real failure.
INTERRUPTED_ERROR_CODE = "INTERRUPTED"


def reconcile_stale_jobs(db: Session, *, now: datetime | None = None) -> int:
    """Finds every IngestionJob still `status == "RUNNING"` whose
    `started_at` is older than `settings.STALE_JOB_THRESHOLD_MINUTES`, and
    marks it (and its Resource) FAILED with `INTERRUPTED_ERROR_CODE`.

    Bounded, single query (`status == "RUNNING" AND started_at < cutoff`)
    -- not a full-table scan -- safe to call on every API startup per the
    approved design. `now` is an injectable seam for tests; production
    callers should never pass it.

    Returns the number of jobs reconciled, for logging.
    """
    settings = get_settings()
    reference_time = now or datetime.now(timezone.utc)
    cutoff = reference_time - timedelta(minutes=settings.STALE_JOB_THRESHOLD_MINUTES)

    stale_jobs = (
        db.query(IngestionJob)
        .filter(IngestionJob.status == "RUNNING", IngestionJob.started_at < cutoff)
        .all()
    )

    for job in stale_jobs:
        job.status = "FAILED"
        job.step = IngestionStep.FAILED
        job.error_code = INTERRUPTED_ERROR_CODE
        job.completed_at = reference_time

        resource = db.get(Resource, job.resource_id)
        if resource is not None:
            resource.status = ResourceStatus.FAILED
            resource.error_message = (
                "Processing was interrupted (the server restarted mid-job). "
                "Use retry or re-run extraction to resume."
            )

    if stale_jobs:
        db.commit()
        logger.warning(
            "stale_jobs_reconciled count=%s cutoff_minutes=%s",
            len(stale_jobs),
            settings.STALE_JOB_THRESHOLD_MINUTES,
        )

    return len(stale_jobs)
