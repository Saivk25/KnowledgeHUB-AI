from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, get_current_workspace
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.models.workspace import Workspace

router = APIRouter(tags=["workspace"])


class UpdateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateUserRequest(BaseModel):
    displayName: str = Field(min_length=1, max_length=255)


@router.get("/workspace")
def get_workspace(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    ready = (
        db.query(Document)
        .filter(Document.workspace_id == workspace.id, Document.status == DocumentStatus.READY)
        .count()
    )
    processing = (
        db.query(Document)
        .filter(
            Document.workspace_id == workspace.id,
            Document.status.in_([DocumentStatus.QUEUED, DocumentStatus.PROCESSING]),
        )
        .count()
    )
    failed = (
        db.query(Document)
        .filter(Document.workspace_id == workspace.id, Document.status == DocumentStatus.FAILED)
        .count()
    )
    return {
        "workspace": {"id": workspace.id, "name": workspace.name},
        "stats": {"readyDocuments": ready, "processingDocuments": processing, "failedDocuments": failed},
    }


@router.patch("/workspace")
def update_workspace(
    payload: UpdateWorkspaceRequest,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    workspace.name = payload.name
    db.commit()
    return {"workspace": {"id": workspace.id, "name": workspace.name}}


@router.patch("/users/me")
def update_user(
    payload: UpdateUserRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.display_name = payload.displayName
    db.commit()
    return {"user": {"id": user.id, "email": user.email, "displayName": user.display_name}}
