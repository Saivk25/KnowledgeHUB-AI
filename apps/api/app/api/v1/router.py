"""
v1 API router.

Milestone 3 (Document Upload & Ingestion) scope: auth, workspace, and
documents are mounted. `chat` is intentionally NOT imported here yet --
it transitively imports app.services.llm, which needs an AI-provider
client not wired until Milestone 4 (RAG Chat). Importing this router with
chat included now would pull in code with no defined behavior yet, ahead
of its milestone review. Add it back in Milestone 4.
"""

from fastapi import APIRouter

from app.api.v1.routes import auth, documents, workspace

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(workspace.router)
api_router.include_router(documents.router)
