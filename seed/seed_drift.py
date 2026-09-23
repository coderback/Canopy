"""Bake in (or undo) a deliberate account drift for the resolve-later demo.

Plants a distinctive account in every active org EXCEPT one target, so the target
shows a red drift dot you can resolve live (click the dot -> pre-filled propose ->
approve -> Xero create -> dot turns green). Run AFTER connecting the orgs, from
the backend dir:

    cd backend && python ..\\seed\\seed_drift.py --target "Demo Manchester Ltd"
    cd backend && python ..\\seed\\seed_drift.py --target "Demo Manchester Ltd" --undo

Why a *fresh* account (not archiving an existing one): archiving keeps the code
and name reserved in Xero, so the later resolve (a create) would fail on a
duplicate. Drift is also name-aware — the target must lack the name entirely — so
the planted name must not exist anywhere yet. Defaults satisfy both.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Entity, Snapshot  # noqa: E402
from app.snapshots import get_snapshot, snapshot_health  # noqa: E402
from app.xero.client import XeroApi, XeroApiError, xero_api  # noqa: E402


def _latest_accounts(db, entity) -> list[dict]:
    row = (
        db.query(Snapshot)
        .filter_by(entity_id=entity.id, kind="accounts")
        .order_by(Snapshot.fetched_at.desc())
        .first()
    )
    return row.data if row else []


async def bake(api: XeroApi, db, entities, target, code, name, type_) -> None:
    # A clean gap needs the code AND name free in every org (name-aware drift).
    for e in entities:
        clash = [
            r for r in _latest_accounts(db, e)
            if str(r.get("Code")) == code or (r.get("Name", "").lower() == name.lower())
        ]
        if clash:
            sys.exit(f"ABORT: {e.name} already has {clash} — pick a free --code/--name.")
    for e in entities:
        if e.id == target.id:
            print(f"  skip {e.name} (left as the gap to solve later)")
            continue
        await api.create_account(db, e.tenant_id, {"Code": code, "Name": name, "Type": type_})
        print(f"  created {code} {name} in {e.name}")
        await get_snapshot(db, api, e, "accounts", force=True)


async def undo(api: XeroApi, db, entities, target, code, name) -> None:
    for e in entities:
        if e.id == target.id:
            continue
        match = next(
            (r for r in _latest_accounts(db, e) if str(r.get("Code")) == code and r.get("AccountID")),
            None,
        )
        if not match:
            print(f"  {e.name}: nothing to undo")
            continue
        try:
            await api.request(db, e.tenant_id, "POST", f"/Accounts/{match['AccountID']}", json={"Status": "ARCHIVED"})
            print(f"  archived {code} in {e.name}")
        except XeroApiError as exc:
            print(f"  {e.name}: could not archive {code}: {exc.status_code}")
        await get_snapshot(db, api, e, "accounts", force=True)


async def main(args) -> None:
    init_db()
    db = SessionLocal()
    entities = db.query(Entity).filter_by(active=True).order_by(Entity.id).all()
    target = next((e for e in entities if e.name == args.target), None)
    if target is None:
        sys.exit(f"Unknown target {args.target!r}. Active orgs: {[e.name for e in entities]}")

    # Ensure every org's accounts snapshot is current before we reason about gaps.
    for e in entities:
        await get_snapshot(db, xero_api, e, "accounts")

    if args.undo:
        await undo(xero_api, db, entities, target, args.code, args.name)
    else:
        await bake(xero_api, db, entities, target, args.code, args.name, args.type)

    print("\nhealth:")
    health = snapshot_health(db, entities)
    for e in entities:
        h = health[e.id]
        dot = "RED" if h["drift_total"] else "green"
        print(f"  {e.name:<22} {dot:<5} drift={[x['code'] for x in h['drift']]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bake in / undo a deliberate account drift for the demo.")
    ap.add_argument("--target", required=True, help="org name to leave WITHOUT the account (the drift to solve later)")
    ap.add_argument("--code", default="990", help="account code to plant (default 990)")
    ap.add_argument("--name", default="Gift Card Liability", help="account name to plant")
    ap.add_argument("--type", default="CURRLIAB", help="Xero AccountType (default CURRLIAB)")
    ap.add_argument("--undo", action="store_true", help="archive the planted account back out of the non-target orgs")
    asyncio.run(main(ap.parse_args()))
