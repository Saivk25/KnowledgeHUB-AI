"""
Workspace + user profile routes.

Milestone note: `GET /workspace` intentionally does not report document
counts yet. The original prototype queried the `Document` model for
ready/processing/failed counts, but that model/table doesn't exist until
Milestone 3 (Document Ingestion) -- querying it here would raise
`OperationalError: no such table` on a fresh Milestone 2 database. This is
the smallest change that keeps the endpoint honest about what exists
right now; the `stats` field is added back in Milestone 3 alongside the
Document model it depends on.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, get_current_workspace
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.auth import UserOut, WorkspaceOut

router = APIRouter(tags=["workspace"])


class UpdateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateUserRequest(BaseModel):
    displayName: str = Field(min_length=1, max_length=255)


class WorkspaceResponse(BaseModel):
    workspace: WorkspaceOut


class UserResponse(BaseModel):
    user: UserOut


@router.get(
    "/workspace",
    response_model=WorkspaceResponse,
    summary="Get the current user's workspace",
    description=(
        "Protected route. Returns the caller's own workspace only -- there "
        "is no lookup-by-id, so one account can never read another "
        "account's workspace. Does not include document counts yet; see "
        "the module docstring above."
    ),
)
def get_workspace(
    workspace: Workspace = Depends(get_current_workspace),
):
    return WorkspaceResponse(workspace=WorkspaceOut(id=workspace.id, name=workspace.name))


@router.patch(
    "/workspace",
    response_model=WorkspaceResponse,
    summary="Rename the current user's workspace",
)
def update_workspace(
    payload: UpdateWorkspaceRequest,
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    workspace.name = payload.name
    db.commit()
    return WorkspaceResponse(workspace=WorkspaceOut(id=workspace.id, name=workspace.name))


@router.patch(
    "/users/me",
    response_model=UserResponse,
    summary="Update the current user's display name",
    description="Protected route. Email is not editable through this endpoint in Milestone 2.",
)
def update_user(
    payload: UpdateUserRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.display_name = payload.displayName
    db.commit()
    return UserResponse(user=UserOut(id=user.id, email=user.email, displayName=user.display_name))
