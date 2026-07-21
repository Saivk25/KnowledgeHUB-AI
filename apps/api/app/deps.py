from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import Workspace


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


def get_current_user(
    access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "UNAUTHENTICATED", "Authentication required.")

    payload = decode_access_token(token)
    if not payload:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN", "Session is invalid or expired.")

    user = db.get(User, payload.get("sub"))
    if not user:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN", "Session is invalid or expired.")
    return user


def get_current_workspace(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.owner_user_id == user.id).first()
    if not workspace:
        raise AppError(status.HTTP_404_NOT_FOUND, "WORKSPACE_NOT_FOUND", "No workspace found for this user.")
    return workspace
