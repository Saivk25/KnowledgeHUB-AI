"""
Workspace + user profile routes.

Milestone note (original, Milestone 2): `GET /workspace` intentionally did
not report document counts. The original prototype queried the `Document`
model for ready/processing/failed counts, but that model/table didn't
exist until Milestone 3 (Document Ingestion) -- querying it here would
have raised `OperationalError: no such table` on a fresh Milestone 2
database. The `stats` field was meant to be "added back in Milestone 3
alongside the Document model it depends on," per this docstring's original
wording -- but that follow-up never actually happened: Milestone 3 shipped
a `listDocuments()`-based, client-computed count on the Documents page
instead, and `GET /workspace` was simply never revisited.

Milestone 8 ("Reactivate frontend chat UI") then promoted
`app/_future/chat/page.tsx` to the live `app/chat/page.tsx` route. That
screen reads `ws.stats?.readyDocuments` to decide whether to show its
compose UI at all or a "you need a Ready document" blocker -- a read that
was harmless while the screen was dormant (Milestone 4-7), but became a
real, unconditional bug the moment the screen went live: `stats` was
never populated, so `readyDocuments` was always `0` and the chat compose
UI was permanently hidden for every workspace, regardless of actual Ready
document count. See docs/milestones/MILESTONE_12.md Section 13 for the
full discovery (found live, during Milestone 12 Item 4's screenshot
capture) and Section 13.1 for this fix's design. `stats` is now populated
below, closing that gap -- no new endpoint, same response shape the
frontend has expected since Milestone 4.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, get_current_workspace
from app.models.resource import Resource, ResourceStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.auth import UserOut, WorkspaceOut, WorkspaceStatsOut

router = APIRouter(tags=["workspace"])


class UpdateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateUserRequest(BaseModel):
    displayName: str = Field(min_length=1, max_length=255)


class WorkspaceResponse(BaseModel):
    workspace: WorkspaceOut
    stats: WorkspaceStatsOut | None = None


class UserResponse(BaseModel):
    user: UserOut


def _workspace_stats(db: Session, workspace_id: str) -> WorkspaceStatsOut:
    """Per-status `Resource` counts for `workspace_id`. Same
    `.query(Resource).filter(...).count()` pattern
    `chat.py`'s `POST /{conversation_id}/messages` route already uses for
    its own `READY`-count gate (see that route for the original) --
    extended here to all three buckets `WorkspaceStatsOut` reports.
    `QUEUED` and `PROCESSING` are both counted under `processingDocuments`;
    see `WorkspaceStatsOut`'s own docstring for why."""
    base = db.query(Resource).filter(Resource.workspace_id == workspace_id)
    ready = base.filter(Resource.status == ResourceStatus.READY).count()
    processing = base.filter(Resource.status.in_([ResourceStatus.QUEUED, ResourceStatus.PROCESSING])).count()
    failed = base.filter(Resource.status == ResourceStatus.FAILED).count()
    return WorkspaceStatsOut(readyDocuments=ready, processingDocuments=processing, failedDocuments=failed)


@router.get(
    "/workspace",
    response_model=WorkspaceResponse,
    summary="Get the current user's workspace",
    description=(
        "Protected route. Returns the caller's own workspace only -- there "
        "is no lookup-by-id, so one account can never read another "
        "account's workspace. Includes per-status document counts in "
        "`stats` (Milestone 12 Section 13) -- see the module docstring "
        "above for why this was previously missing."
    ),
)
def get_workspace(
    workspace: Workspace = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    return WorkspaceResponse(
        workspace=WorkspaceOut(id=workspace.id, name=workspace.name),
        stats=_workspace_stats(db, workspace.id),
    )


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
