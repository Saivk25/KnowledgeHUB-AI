# ADR-0005: FastAPI BackgroundTasks for ingestion, not Celery/Temporal

**Status:** Accepted (MVP)

**Decision:** Document ingestion (extract → chunk → embed → index) runs as
a FastAPI `BackgroundTask` kicked off from the upload endpoint. The upload
request returns immediately with `status: "QUEUED"`; the UI polls document
status until it reaches `READY` or `FAILED`.

**Alternatives considered:**
- **Celery + Redis broker:** the natural next step, giving retries, worker
  scaling, and a dead-letter queue.
- **Temporal:** the enterprise-grade choice (see the full SRS) for durable,
  observable workflows with built-in retry/backoff semantics.

**Why simpler wins for now:** both alternatives require running and
operating an additional service (broker + worker process) inside the
2-day build budget for a benefit — independent worker scaling, task
persistence across restarts — that a single-instance MVP doesn't need yet.
`app/services/ingestion_service.py` has no FastAPI-specific code in its
body; it takes a DB session and a document ID and returns nothing. That
makes it directly callable from a Celery task or a Temporal activity later
without rewriting ingestion logic.

**MVP impact:** ingestion is lost if the API process crashes mid-job (the
job row is left `RUNNING`); acceptable for local/demo use, called out
explicitly as a known limitation in the README.

**Revisit when:** the product needs multi-instance workers, ingestion
retries with backoff, or ingestion volume high enough to need independent
scaling from the API (Phase 2).
