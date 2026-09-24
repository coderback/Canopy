import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models_base import WorkspaceScoped, created_at, uuid_pk


class XeroConnection(WorkspaceScoped, Base):
    """One Xero user's OAuth grant inside a workspace. A token only reaches the
    tenants *that* user authorised, so a workspace may hold several."""

    __tablename__ = "xero_connections"
    __table_args__ = (UniqueConstraint("workspace_id", "xero_user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    xero_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connected_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # active | revoked (user disconnected / refresh token rejected) | error
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Entity(WorkspaceScoped, Base):
    """A connected Xero organisation within a workspace."""

    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("workspace_id", "tenant_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("xero_connections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Xero's id for this tenant connection; needed to DELETE /connections/{id}.
    xero_connection_ref: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_currency: Mapped[str | None] = mapped_column(String(3))
    country_code: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # active | disconnected
    sync_status: Mapped[str] = mapped_column(String(16), nullable=False, default="never")
    # never | queued | running | ok | error
    sync_error: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # High-water mark for incremental sync (max UpdatedDateUTC seen).
    accounts_modified_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class XeroQuota(Base):
    """Last-seen Xero rate-limit headers. Quotas belong to (app, tenant), not to
    a workspace, so this is keyed by tenant ('*app*' for the app-wide minute
    limit) and holds no customer data — no RLS."""

    __tablename__ = "xero_quota"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    min_remaining: Mapped[int | None] = mapped_column(Integer)
    day_remaining: Mapped[int | None] = mapped_column(Integer)
    retry_after_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = created_at()
