"""
KnowledgeHub AI -- API entrypoint.

Milestone 1 (Project Foundation) scope: application wiring, CORS, structured
logging, generic error handling, and health checks only. No business
routers (auth, documents, chat) are mounted yet -- they are added in the
milestones that implement them, per the frozen SRS and the approved
milestone plan. See app/README.md for a full map of dormant modules and
docs/adr/ for the reasoning behind each dependency choice already locked
in (Postgres, Qdrant, etc.), which this foundation is built to support.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.health import router as health_router
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

# CORS: deliberately minimal for what actually exists right now -- GET-only
# health checks, called from the browser with no cookies/credentials
# involved. allow_credentials is left off (not True) because there is no
# session cookie to send yet; Milestone 2 turns it on alongside the auth
# router, at the same time it introduces something that actually needs it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.WEB_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET"],
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
