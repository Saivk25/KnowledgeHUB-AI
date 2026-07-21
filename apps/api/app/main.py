"""
KnowledgeHub AI -- API entrypoint.

Milestone 3 (Document Upload & Ingestion) scope: mounts health, auth,
workspace, and documents routers. The chat router remains dormant -- see
app/api/v1/router.py and app/README.md for why, and the frozen SRS /
milestone plan for when it arrives.
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
from app.db.base import Base
from app.db.session import engine

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


@app.on_event("startup")
def on_startup() -> None:
    # Milestone 3 adds documents/document_pages/document_chunks/
    # ingestion_jobs (imported transitively via app.api.v1.router, which
    # registers them on Base.metadata through the documents router).
    # create_all is the frozen MVP decision (see
    # docs/adr/0008-schema-create-all-not-alembic.md) -- Alembic migrations
    # arrive only once there is real data to migrate around.
    Base.metadata.create_all(bind=engine)


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
