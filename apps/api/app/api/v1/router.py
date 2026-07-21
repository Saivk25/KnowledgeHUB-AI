from fastapi import APIRouter

from app.api.v1.routes import auth, chat, documents, workspace

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(workspace.router)
