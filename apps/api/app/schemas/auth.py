from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    displayName: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    displayName: str


class WorkspaceOut(BaseModel):
    id: str
    name: str


class WorkspaceStatsOut(BaseModel):
    """Milestone 12 (Section 13 addendum): per-status `Resource` counts for
    the calling workspace. Mirrors `apps/web/lib/api.ts`'s existing
    `WorkspaceStatsOut` TypeScript interface field-for-field so no frontend
    type change is required -- that interface predates this schema (it was
    declared, unpopulated, back when Milestone 4's now-promoted chat screen
    was still dormant in `app/_future/`; see workspace.py's route docstring
    for the full history of why it was never wired up until now).

    Three fields, not four: `Resource.status` has four values (`QUEUED`,
    `PROCESSING`, `READY`, `FAILED`), but the frontend contract this mirrors
    only distinguishes three buckets. `QUEUED` (not yet started) and
    `PROCESSING` (actively running) are both still-in-flight from a caller's
    perspective -- neither is done and neither has failed -- so both count
    toward `processingDocuments`. See `get_workspace`'s implementation.
    """

    readyDocuments: int
    processingDocuments: int
    failedDocuments: int


class AuthResponse(BaseModel):
    user: UserOut
    workspace: WorkspaceOut
    accessToken: str


class MeResponse(BaseModel):
    user: UserOut
    workspace: WorkspaceOut | None
