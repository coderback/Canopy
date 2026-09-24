import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models_base import created_at, uuid_pk


class User(Base):
    """A person, identified by their Xero user id (Sign Up with Xero).

    RLS: a user sees themselves and people who share a workspace with them.
    Login creates users through the SECURITY DEFINER function
    `canopy_upsert_user`, because before login there is no user context."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    xero_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = created_at()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Session(Base):
    """Server-side session. The cookie holds a random token; only its SHA-256
    hash is stored, so a database leak does not yield usable sessions. Not
    workspace-scoped (looked up before any context exists) and holds no PII."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    active_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OAuthState(Base):
    """Pending OAuth round-trip (login or org connection). Holds the state,
    OIDC nonce and PKCE verifier; single-use and short-lived."""

    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)  # login | connect
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    redirect_to: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
