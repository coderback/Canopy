"""Change control: a change set groups one intent's per-org items.

Lifecycle of a set:  draft -> submitted -> approved | rejected -> executing ->
completed | partial | failed   (cancelled from draft or submitted).
Each item is validated, executed and audited independently, so one org failing
never hides or blocks another.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models_base import WorkspaceScoped, created_at, utcnow, uuid_pk

SET_STATUSES = (
    "draft", "submitted", "approved", "rejected", "executing", "completed", "partial", "failed", "cancelled",
)
OPERATIONS = ("create_account", "update_account", "archive_account")
ITEM_STATUSES = ("pending", "running", "succeeded", "failed", "skipped")


def _in(column: str, values: tuple) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


class ChangeSet(WorkspaceScoped, Base):
    __tablename__ = "change_sets"
    __table_args__ = (CheckConstraint(_in("status", SET_STATUSES), name="status_valid"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    # True when the author approved their own set (only possible if the workspace allows it).
    self_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ChangeItem(WorkspaceScoped, Base):
    """One operation in one org.

    payload: desired fields — create: {code, name, type, tax_type?, description?};
    update: only the fields that change; archive: {}.
    before/after: the live Xero account read just before the write, and Xero's response."""

    __tablename__ = "change_items"
    __table_args__ = (
        CheckConstraint(_in("operation", OPERATIONS), name="operation_valid"),
        CheckConstraint(_in("status", ITEM_STATUSES), name="status_valid"),
        CheckConstraint("preflight_status in ('ok', 'blocked')", name="preflight_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    change_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("change_sets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entity_accounts.id", ondelete="SET NULL")
    )
    group_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("group_accounts.id", ondelete="SET NULL")
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    preflight_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    preflight_messages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Increments on each explicit retry; part of the Xero Idempotency-Key.
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    xero_account_id: Mapped[str | None] = mapped_column(String(64))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()

    @property
    def idempotency_key(self) -> str:
        """Stable within an attempt (automatic retries replay safely), new on an
        explicit retry (so a cached failure isn't replayed)."""
        return f"canopy-{self.id}-{self.attempt}"
