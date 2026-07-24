"""
KnowledgeHub AI -- API entrypoint.

Milestone 3 (Document Upload & Ingestion) scope: mounts health, auth,
workspace, and documents routers. The chat router remains dormant -- see
app/api/v1/router.py and app/README.md for why, and the frozen SRS /
milestone plan for when it arrives.

Milestone 4 change: schema creation no longer happens here. `Base.metadata.
create_all` (ADR-0008) is retired in favor of Alembic-managed migrations
(ADR-0010) -- run `alembic upgrade head` before starting the API in every
environment (local dev, CI, Docker; see apps/api/Dockerfile's CMD and
tests/conftest.py, both updated in this same milestone). Running migrations
inside the app process at startup is deliberately avoided: with more than
one API replica, concurrent `create_all`-style calls were harmless
(idempotent, checkfirst), but concurrent migration runs are not -- a
top-level `alembic upgrade head` is guarded by Alembic's own lock table
(alembic_version) but is still meant to be run once, out of band, not
racing N app instances on every restart.

Milestone 12 addition: a startup event reconciles stale IngestionJob rows
(see app/services/job_reconciliation.py and MILESTONE_12.md Section 4.1)
-- unlike the Alembic migration above, this is safe to run on every boot
of every replica: it is a single bounded, indexed query, not a schema
change, and marking an already-orphaned job FAILED twice is a no-op the
second time (the query only ever matches rows still `status ==
"RUNNING"`).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title=settings.APP_NAME, version="0.3.0")

# CORS: Milestone 3 adds document deletion (DELETE /api/v1/documents/{id}),
# so DELETE joins the allowed methods. allow_credentials stays True (the
# session cookie introduced in Milestone 2) and the origin stays a single,
# non-wildcard value -- still no wildcard anywhere in this configuration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.WEB_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = str(uuid.uuid4())
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        body = {"error": {**detail, "requestId": request_id}}
    else:
        body = {"error": {"code": "HTTP_ERROR", "message": str(detail), "requestId": request_id}}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Security fix (Milestone 2 audit, still in force): FastAPI's default
    # handler for this exception echoes back the raw submitted value for
    # every invalid field. This handler reuses the same {"error": ...}
    # envelope as every other error response and deliberately omits raw
    # field values, listing only the field path and the validation message.
    request_id = str(uuid.uuid4())
    field_errors = [
        {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "The request could not be validated.",
                "details": field_errors,
                "requestId": request_id,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = str(uuid.uuid4())
    logger.exception("unhandled_exception request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
                "requestId": request_id,
            }
        },
    )


app.include_router(health_router)
app.include_router(api_router)


@app.on_event("startup")
def _reconcile_stale_jobs_on_startup() -> None:
    """Milestone 12, Section 4.1: mark any IngestionJob left `RUNNING` by a
    crashed prior process as FAILED/INTERRUPTED, so it becomes resumable
    via the existing retry/reextract endpoints instead of stuck forever.
    Wrapped defensively -- a reconciliation failure must never prevent the
    API from starting, the same "auxiliary work never blocks the primary
    path" rule already applied to classification/concept-linking failures
    in app/services/ingestion_service.py."""
    from app.db.session import SessionLocal
    from app.services.job_reconciliation import reconcile_stale_jobs

    db = SessionLocal()
    try:
        count = reconcile_stale_jobs(db)
        if count:
            logger.warning("startup_reconciliation reconciled=%s", count)
    except Exception:  # noqa: BLE001
        logger.exception("startup_reconciliation_failed")
    finally:
        db.close()
