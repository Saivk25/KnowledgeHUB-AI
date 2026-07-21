"""
v1 API router.

Milestone 2 (Authentication) scope: only auth and workspace are mounted.
`chat` and `documents` are intentionally NOT imported here yet -- both
transitively import modules with module-level imports of packages that
are not installed until their milestone (`app.services.extraction` does
`import fitz`; `app.services.embeddings` / `app.services.llm` do
`import httpx`). Importing this router with those two included would
raise ModuleNotFoundError before the app even starts. Add them back
(and their dependencies to requirements.txt) in Milestones 3 and 4.
"""

from fastapi import APIRouter

from app.api.v1.routes import auth, workspace

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(workspace.router)
