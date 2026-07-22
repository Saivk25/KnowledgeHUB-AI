"""
v1 API router.

Milestone 8 (Local-First Retrieval & Provenance) mounts `chat` for the
first time -- its retrieval pipeline (app/services/retrieval_service.py,
app/services/llm.py) is no longer dormant scaffolding once this milestone
reviews and extends it (sufficiency scoring, provenance, hybrid
vector+concept retrieval). See docs/adr/0003-retrieval-pipeline-scope.md
and docs/adr/0004-ai-provider-strategy.md for the governing decisions this
router now activates.
"""

from fastapi import APIRouter

from app.api.v1.routes import auth, chat, concepts, documents, workspace

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(workspace.router)
api_router.include_router(documents.router)
# Milestone 7 (Concept Graph): concepts are only ever created by the
# ingestion pipeline (documents.router already mounted above); this
# router is read/merge only.
api_router.include_router(concepts.router)
# Milestone 8 (Local-First Retrieval & Provenance).
api_router.include_router(chat.router)
