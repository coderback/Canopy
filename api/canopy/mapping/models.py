import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models_base import WorkspaceScoped, created_at, utcnow, uuid_pk


class AccountMapping(WorkspaceScoped, Base):
    """Maps ONE org account to at most one group account (many-to-one).

    - status: suggested (from the matcher or AI) | confirmed | rejected
    - group_account_id NULL + confirmed = deliberately local-only (no group
      equivalent). NULL + suggested = the matcher found nothing.
    A group account is a *gap* in an org when none of the org's live accounts
    has a confirmed mapping to it."""

    __tablename__ = "account_mappings"
    __table_args__ = (
        CheckConstraint("status in ('suggested','confirmed','rejected')", name="status_valid"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="confidence_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity_accounts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    group_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("group_accounts.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # exact | name | code_conflict | ai | manual | unmatched
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
