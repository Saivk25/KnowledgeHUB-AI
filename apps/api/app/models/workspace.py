from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPK, TimestampMixin


class Workspace(Base, UUIDPK, TimestampMixin):
    """
    MVP: one personal workspace per user. This is the tenant boundary used
    to filter every document, chunk, and citation query. The schema does not
    prevent multi-member workspaces later (Phase 2 adds a memberships table).
    """

    __tablename__ = "workspaces"

    owner_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="My Workspace")

    owner = relationship("User", back_populates="workspaces")
