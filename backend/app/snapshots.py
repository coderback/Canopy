"""Per-entity reference-data snapshots with a DB-backed TTL cache.

Mirrors the shared-cache pattern from AirHop's internal portal: mapping calls
and the approval UI read from here instead of hammering the API per row.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from .config import get_settings
from .models import Entity, Snapshot, utcnow
from .xero.client import XeroApi

KINDS = ("accounts", "tax_rates", "contacts", "items", "tracking_categories")

_FETCHERS = {
    "accounts": lambda api, db, tid: api.list_accounts(db, tid),
    "tax_rates": lambda api, db, tid: api.list_tax_rates(db, tid),
    "contacts": lambda api, db, tid: api.list_contacts(db, tid),
    "items": lambda api, db, tid: api.list_items(db, tid),
    "tracking_categories": lambda api, db, tid: api.list_tracking_categories(db, tid),
}


def _slim(kind: str, records: list[dict]) -> list[dict]:
    """Keep only the fields the mapping engine needs — snapshots go into prompts."""
    if kind == "accounts":
        # SystemAccount (DEBTORS/CREDITORS/GST/…) + Type=BANK mark accounts a
        # manual journal cannot post to — the ingest engine/guard needs to see them.
        keys = ("Code", "Name", "Type", "TaxType", "Status", "Description", "SystemAccount")
    elif kind == "tax_rates":
        keys = ("Name", "TaxType", "EffectiveRate", "Status", "CanApplyToExpenses", "CanApplyToRevenue")
    elif kind == "contacts":
        keys = ("ContactID", "Name", "EmailAddress", "IsSupplier", "IsCustomer", "ContactStatus")
    elif kind == "items":
        keys = ("Code", "Name", "Description", "SalesDetails", "PurchaseDetails", "IsSold", "IsPurchased")
    else:  # tracking_categories
        keys = ("TrackingCategoryID", "Name", "Status", "Options")
    return [{k: r.get(k) for k in keys if r.get(k) is not None} for r in records]


async def get_snapshot(
    db: Session, api: XeroApi, entity: Entity, kind: str, force: bool = False
) -> list[dict]:
    assert kind in KINDS, f"unknown snapshot kind {kind!r}"
    ttl = timedelta(seconds=get_settings().snapshot_ttl_seconds)
    row = (
        db.query(Snapshot)
        .filter_by(entity_id=entity.id, kind=kind)
        .order_by(Snapshot.fetched_at.desc())
        .first()
    )
    if row is not None and not force:
        fetched = row.fetched_at
        if fetched.tzinfo is None:  # SQLite drops tzinfo
            from datetime import timezone

            fetched = fetched.replace(tzinfo=timezone.utc)
        if utcnow() - fetched < ttl:
            return row.data

    records = _slim(kind, await _FETCHERS[kind](api, db, entity.tenant_id))
    if row is None:
        row = Snapshot(entity_id=entity.id, kind=kind, data=records)
        db.add(row)
    else:
        row.data = records
        row.fetched_at = utcnow()
    db.commit()
    return records


async def get_entity_context(db: Session, api: XeroApi, entity: Entity) -> dict[str, list[dict]]:
    """Everything the mapping engine needs to reason about one target entity."""
    return {kind: await get_snapshot(db, api, entity, kind) for kind in KINDS}
