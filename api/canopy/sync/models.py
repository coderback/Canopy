import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models_base import WorkspaceScoped, created_at, uuid_pk


class EntityAccount(WorkspaceScoped, Base):
    """Mirror of one account in one org's chart. Only the fields mapping needs:
    bank account numbers and similar are deliberately not stored."""

    __tablename__ = "entity_accounts"
    __table_args__ = (UniqueConstraint("entity_id", "xero_account_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    xero_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str | None] = mapped_column(String(32))  # bank accounts may have none
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    account_class: Mapped[str | None] = mapped_column(String(16))
    # ASSET | EQUITY | EXPENSE | LIABILITY | REVENUE (Xero "Class")
    tax_type: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ACTIVE | ARCHIVED
    system_account: Mapped[str | None] = mapped_column(String(64))
    reporting_code: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    xero_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when a full sync no longer sees the account (deleted in Xero).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = created_at()


class SyncRun(WorkspaceScoped, Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # full | incremental
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # running | ok | error
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EntityTaxRate(WorkspaceScoped, Base):
    """Mirror of one org's tax rates: creating or editing an account needs a tax
    type that exists, is active, and applies to the account's class in THAT org."""

    __tablename__ = "entity_tax_rates"
    __table_args__ = (UniqueConstraint("entity_id", "tax_type"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tax_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ACTIVE | DELETED | ARCHIVED
    effective_rate: Mapped[float | None] = mapped_column(Float)
    # Which account classes Xero allows this tax type on (None = not reported).
    can_apply_to_revenue: Mapped[bool | None] = mapped_column(Boolean)
    can_apply_to_expenses: Mapped[bool | None] = mapped_column(Boolean)
    can_apply_to_assets: Mapped[bool | None] = mapped_column(Boolean)
    can_apply_to_liabilities: Mapped[bool | None] = mapped_column(Boolean)
    can_apply_to_equity: Mapped[bool | None] = mapped_column(Boolean)
    synced_at: Mapped[datetime] = created_at()
