from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.deps import AppError, get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut, WorkspaceOut

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "access_token"


def _issue_response(user: User, workspace: Workspace, response: Response) -> AuthResponse:
    token = create_access_token(subject=user.id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,
    )
    return AuthResponse(
        user=UserOut(id=user.id, email=user.email, displayName=user.display_name),
        workspace=WorkspaceOut(id=workspace.id, name=workspace.name),
        accessToken=token,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
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


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS", "Invalid email or password.")

    workspace = db.query(Workspace).filter(Workspace.owner_user_id == user.id).first()
    return _issue_response(user, workspace, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return None


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workspace = db.query(Workspace).filter(Workspace.owner_user_id == user.id).first()
    return {
        "user": UserOut(id=user.id, email=user.email, displayName=user.display_name),
        "workspace": WorkspaceOut(id=workspace.id, name=workspace.name) if workspace else None,
    }
