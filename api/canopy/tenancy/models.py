import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models_base import WorkspaceScoped, created_at, uuid_pk


class Role(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    PREPARER = "preparer"  # proposes changes (Milestone 2)
    APPROVER = "approver"  # approves changes (Milestone 2)
    VIEWER = "viewer"


role_enum = Enum(Role, name="role", values_callable=lambda e: [m.value for m in e])


class Workspace(Base):
    """One customer group. RLS: visible to its members."""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created_at()
    # Milestone 2: writing to Xero is opt-in per workspace (owner), and the author of a
    # change may approve it only if the owner explicitly allows self-approval.
    changes_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    allow_self_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class Membership(WorkspaceScoped, Base):
    """RLS: visible within its workspace, and to the member themself (so a user
    can list the workspaces they belong to before choosing one)."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[Role] = mapped_column(role_enum, nullable=False)
    created_at: Mapped[datetime] = created_at()


class Invitation(WorkspaceScoped, Base):
    """Invite by email. Accepted through the SECURITY DEFINER function
    `canopy_accept_invitation`, since the invitee isn't a member yet."""

    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[Role] = mapped_column(role_enum, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
