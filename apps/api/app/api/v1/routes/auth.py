"""
Authentication routes (Milestone 2).

Sessions are carried both ways -- as an httpOnly cookie (used by the
browser-based Next.js frontend, see `_issue_response` below) and as the
same JWT in the response body (`accessToken`, for non-browser clients).
`app/deps.get_current_user` accepts either.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.deps import AppError, get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.auth import AuthResponse, LoginRequest, MeResponse, RegisterRequest, UserOut, WorkspaceOut

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "access_token"
settings = get_settings()


def _issue_response(user: User, workspace: Workspace, response: Response) -> AuthResponse:
    token = create_access_token(subject=user.id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        # Security audit fix (Milestone 2): Secure must be True whenever the
        # cookie could travel over plain HTTP, so it needs to be off for
        # local development (http://localhost) and on in any real
        # deployment. Driven by settings.ENV rather than hardcoded so it's
        # configurable per environment without a code change.
        secure=settings.ENV == "production",
        max_age=60 * 60 * 24,
    )
    return AuthResponse(
        user=UserOut(id=user.id, email=user.email, displayName=user.display_name),
        workspace=WorkspaceOut(id=workspace.id, name=workspace.name),
        accessToken=token,
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and a personal workspace",
    description=(
        "Creates a new user with a hashed password (bcrypt) and an "
        "auto-created personal workspace named \"{displayName}'s "
        'Workspace". Returns 409 EMAIL_TAKEN if the email is already '
        "registered. Sets the session cookie and also returns the JWT in "
        "the response body."
    ),
)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise AppError(status.HTTP_409_CONFLICT, "EMAIL_TAKEN", "An account with this email already exists.")

    user = User(
        id=str(uuid.uuid4()),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        display_name=payload.displayName,
    )
    db.add(user)
    db.flush()

    workspace = Workspace(owner_user_id=user.id, name=f"{payload.displayName}'s Workspace")
    db.add(workspace)
    db.commit()

    return _issue_response(user, workspace, response)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in with email and password",
    description=(
        "Returns 401 INVALID_CREDENTIALS for both an unknown email and a "
        "wrong password -- the message is deliberately identical for both "
        "so the endpoint never reveals whether an email is registered."
    ),
)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS", "Invalid email or password.")

    workspace = db.query(Workspace).filter(Workspace.owner_user_id == user.id).first()
    return _issue_response(user, workspace, response)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the session cookie",
    description=(
        "Clears the client's session cookie, ending the browser session "
        "immediately. Note (ADR-0001, accepted MVP trade-off): the JWT "
        "itself is stateless and is not server-side revoked, so a copy of "
        "the token obtained from the response body (non-browser clients) "
        "remains valid until its 24h expiry even after this call. "
        "Immediate server-side revocation requires a session store and is "
        "explicitly deferred -- see docs/adr/0001-jwt-cookie-auth.md."
    ),
)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return None


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get the current user and their workspace",
    description=(
        "Protected route -- requires the session cookie or a `Bearer` "
        "token. Returns 401 if neither is present or valid."
    ),
)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workspace = db.query(Workspace).filter(Workspace.owner_user_id == user.id).first()
    return MeResponse(
        user=UserOut(id=user.id, email=user.email, displayName=user.display_name),
        workspace=WorkspaceOut(id=workspace.id, name=workspace.name) if workspace else None,
    )
