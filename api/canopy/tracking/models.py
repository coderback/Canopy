"""Tracking categories: the group standard, each org's mirror, and the mapping
between them. Same shape as accounts (standard / mirror / many-to-one mapping),
one level deeper: a category holds options.

Xero allows at most two ACTIVE categories per org (four including archived), so
the group standard is capped at two active categories too: a standard with three
could never be met.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from ..core.db import Base
from ..core.models_base import WorkspaceScoped, created_at, utcnow, uuid_pk

MAX_ACTIVE_CATEGORIES = 2  # per org, and so per group standard
MAX_CATEGORIES = 4  # per org, active + archived
MAX_NAME = 100  # Xero's limit for category and option names

GROUP_STATUSES = "status in ('active', 'archived')"
MAPPING_STATUSES = "status in ('suggested', 'confirmed', 'rejected')"


def _updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class GroupTrackingCategory(WorkspaceScoped, Base):
    __tablename__ = "group_tracking_categories"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        CheckConstraint(GROUP_STATUSES, name="status_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(MAX_NAME), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("entities.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = _updated_at()


class GroupTrackingOption(WorkspaceScoped, Base):
    __tablename__ = "group_tracking_options"
    __table_args__ = (
        UniqueConstraint("category_id", "name"),
        CheckConstraint(GROUP_STATUSES, name="status_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("group_tracking_categories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(MAX_NAME), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = _updated_at()


class EntityTrackingCategory(WorkspaceScoped, Base):
    """Mirror of one org's tracking category (archived ones included: they count
    towards Xero's limit of four and block reusing their name)."""

    __tablename__ = "entity_tracking_categories"
    __table_args__ = (UniqueConstraint("entity_id", "xero_category_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    xero_category_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ACTIVE | ARCHIVED
    # Set when a sync no longer sees it (deleted in Xero).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = created_at()


class EntityTrackingOption(WorkspaceScoped, Base):
    __tablename__ = "entity_tracking_options"
    __table_args__ = (UniqueConstraint("entity_id", "xero_option_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity_tracking_categories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    xero_option_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ACTIVE | ARCHIVED
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = created_at()


class _Mapping:
    """Columns shared by both mapping tables (see AccountMapping for the rules:
    suggestions never overwrite a decision; NULL + confirmed = local-only)."""

    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # exact | manual | unmatched | created
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @declared_attr
    def decided_by(cls) -> Mapped[uuid.UUID | None]:
        # A foreign key on a mixin column has to be declared per table.
        return mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = _updated_at()


class TrackingCategoryMapping(_Mapping, WorkspaceScoped, Base):
    __tablename__ = "tracking_category_mappings"
    __table_args__ = (CheckConstraint(MAPPING_STATUSES, name="status_valid"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity_tracking_categories.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    group_category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("group_tracking_categories.id", ondelete="SET NULL"), index=True
    )


class TrackingOptionMapping(_Mapping, WorkspaceScoped, Base):
    """An option can only map to an option of the group category its own
    category is mapped to (enforced in the service)."""

    __tablename__ = "tracking_option_mappings"
    __table_args__ = (CheckConstraint(MAPPING_STATUSES, name="status_valid"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_option_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity_tracking_options.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    group_option_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("group_tracking_options.id", ondelete="SET NULL"), index=True
    )
