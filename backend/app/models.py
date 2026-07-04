from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Entity(Base):
    """One connected Xero organisation (tenant)."""

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    short_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="entity")


class TokenRecord(Base):
    """Singleton row holding the Fernet-encrypted OAuth token set for the ONE app."""

    __tablename__ = "token_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    token_encrypted: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Snapshot(Base):
    """Cached per-entity reference data (accounts, tax rates, contacts, items, tracking)."""

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entity: Mapped[Entity] = relationship(back_populates="snapshots")


class Run(Base):
    """One fan-out: a change (or ingest/matching) proposed across N entities."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # propagation | ingest | po_bill
    change_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    # proposed | approved | executing | completed | partial | failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    proposals: Mapped[list["Proposal"]] = relationship(back_populates="run")


class Proposal(Base):
    """One AI-mapped (entity × action) row awaiting human approval."""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    action: Mapped[str] = mapped_column(String(64))
    mapped_payload: Mapped[dict] = mapped_column(JSON)
    edited_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    needs_human: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    # proposed | approved | excluded | executed | failed

    run: Mapped[Run] = relationship(back_populates="proposals")
    entity: Mapped[Entity] = relationship()
    write_results: Mapped[list["WriteResult"]] = relationship(back_populates="proposal")


class WriteResult(Base):
    """Full request/response audit for every write attempt."""

    __tablename__ = "write_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    request_json: Mapped[dict] = mapped_column(JSON)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    xero_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    proposal: Mapped[Proposal] = relationship(back_populates="write_results")
