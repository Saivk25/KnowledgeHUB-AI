"""
Health check endpoints -- Milestone 1 (Project Foundation).

Decision: two endpoints with different purposes, both unversioned (health
checks are infrastructure concerns, not business API surface, so they are
deliberately not under /api/v1):

- GET /health       -- liveness. Always returns 200 if the process can
  handle a request at all. No dependency calls. This is what Docker's own
  HEALTHCHECK and a load balancer should poll.
- GET /health/ready -- readiness. Verifies the API can actually reach its
  two hard dependencies (PostgreSQL, Qdrant) and returns 503 with a
  component breakdown if either is unreachable. This is what you'd wire
  into a Kubernetes readinessProbe later, or use manually to confirm
  `docker compose up` brought up the full stack correctly.

Why separate them rather than one endpoint: a liveness check that
transitively pings the database conflates "the process is alive" with "the
process's dependencies are healthy" -- a slow/unreachable database would
then cause an orchestrator to kill and restart a perfectly healthy API
process in a loop, which is the opposite of what you want.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def liveness():
    return {"status": "ok", "app": settings.APP_NAME}


def _check_database() -> tuple[bool, str]:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return True, "reachable"
    except Exception as exc:  # noqa: BLE001
        logger.warning("health_check_database_failed error=%s", exc)
        return False, "unreachable"


def _check_qdrant() -> tuple[bool, str]:
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=settings.QDRANT_URL, timeout=3.0)
        client.get_collections()
        return True, "reachable"
    except Exception as exc:  # noqa: BLE001
        logger.warning("health_check_qdrant_failed error=%s", exc)
        return False, "unreachable"


@router.get("/health/ready")
def readiness():
    db_ok, db_detail = _check_database()
    qdrant_ok, qdrant_detail = _check_qdrant()

    components = {
        "database": {"status": "up" if db_ok else "down", "detail": db_detail},
        "vector_db": {"status": "up" if qdrant_ok else "down", "detail": qdrant_detail},
    }
    overall_ok = db_ok and qdrant_ok

    body = {"status": "ready" if overall_ok else "degraded", "components": components}
    return JSONResponse(status_code=200 if overall_ok else 503, content=body)
