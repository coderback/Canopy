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


def snapshot_health(db: Session, entities: list[Entity]) -> dict[int, dict]:
    """Per-entity snapshot coverage + cross-entity account-code drift.

    Reads only cached Snapshot rows (no Xero calls): for each entity, which
    kinds are cached and how fresh; plus which active account codes exist in a
    majority of snapshot-bearing orgs but are missing here — the "org B has no
    200" signal, surfaced without anyone running a propagation first.
    """
    ids = [e.id for e in entities]
    rows = db.query(Snapshot).filter(Snapshot.entity_id.in_(ids)).all() if ids else []
    by_entity: dict[int, dict[str, Snapshot]] = {}
    for row in rows:
        by_entity.setdefault(row.entity_id, {})[row.kind] = row

    codes: dict[int, dict[str, str]] = {}
    for eid, kinds in by_entity.items():
        acc = kinds.get("accounts")
        if acc is not None:
            codes[eid] = {
                r["Code"]: r.get("Name", "")
                for r in acc.data
                if r.get("Code") and r.get("Status", "ACTIVE") == "ACTIVE"
            }

    total = len(codes)
    presence: dict[str, set[int]] = {}
    names: dict[str, str] = {}
    for eid, cmap in codes.items():
        for code, name in cmap.items():
            presence.setdefault(code, set()).add(eid)
            names.setdefault(code, name)

    health: dict[int, dict] = {}
    for e in entities:
        kinds = by_entity.get(e.id, {})
        drift = []
        if e.id in codes and total >= 2:
            drift = [
                {
                    "code": code,
                    "name": names[code],
                    "present_in": len(present),
                    "of": total,
                }
                for code, present in presence.items()
                if e.id not in present and len(present) > total / 2
            ]
            drift.sort(key=lambda d: (-d["present_in"], d["code"]))
        health[e.id] = {
            "snapshots": {
                kind: {"count": len(row.data), "fetched_at": row.fetched_at.isoformat()}
                for kind, row in kinds.items()
            },
            "kinds_cached": len(kinds),
            "kinds_total": len(KINDS),
            "drift": drift[:5],
            "drift_total": len(drift),
        }
    return health
