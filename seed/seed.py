"""Seed the three connected demo orgs so the demo's intelligence moment is real.

Run AFTER connecting 3 orgs via /auth/xero/connect, from the backend dir:

    cd backend && python ..\\seed\\seed.py [--with-po]

What it sets up (entities are taken in connection order A, B, C):
- Org A (source): item TRAMP-SOCK selling to `200 Sales`; suppliers
  "Acme Corporation Ltd" and "Bounce Cleaning Services".
- Org B: `200 Sales` archived, `201 Trading Income` created → forces the
  mapping moment (200 -> 201); contact variant "Acme Corp" → forces dedup.
- Org C: ALL revenue accounts archived → forces the engine's refusal beat.
- (--with-po) an open purchase order in org A for the Phase 3 PO-to-Bill demo.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Entity  # noqa: E402
from app.xero.client import XeroApi, XeroApiError  # noqa: E402


async def archive_account(api: XeroApi, db, tenant_id: str, account: dict) -> bool:
    try:
        await api.request(
            db,
            tenant_id,
            "POST",
            f"/Accounts/{account['AccountID']}",
            json={"Status": "ARCHIVED"},
        )
        print(f"    archived {account['Code']} {account['Name']}")
        return True
    except XeroApiError as exc:
        print(f"    could not archive {account.get('Code')}: {exc.status_code} (system account?)")
        return False


async def seed_org_a(api: XeroApi, db, tenant_id: str) -> None:
    print("  Org A (source): contacts + demo item on 200 Sales")
    for name, email in [
        ("Acme Corporation Ltd", "accounts@acme.example"),
        ("Bounce Cleaning Services", "billing@bounceclean.example"),
    ]:
        await api.create_or_update_contact(
            db, tenant_id, {"Name": name, "EmailAddress": email, "IsSupplier": True}
        )
        print(f"    contact: {name}")
    await api.create_or_update_item(
        db,
        tenant_id,
        {
            "Code": "TRAMP-SOCK",
            "Name": "Trampoline Grip Socks",
            "Description": "Non-slip grip socks, all sizes",
            "IsSold": True,
            "SalesDetails": {"UnitPrice": 3.50, "AccountCode": "200", "TaxType": "OUTPUT2"},
        },
    )
    print("    item: TRAMP-SOCK -> 200 Sales")


async def seed_org_b(api: XeroApi, db, tenant_id: str) -> None:
    print("  Org B: archive 200 Sales, create 201 Trading Income, contact variant")
    accounts = await api.list_accounts(db, tenant_id)
    codes = {a.get("Code"): a for a in accounts}
    if "201" not in codes:
        await api.create_account(
            db, tenant_id, {"Code": "201", "Name": "Trading Income", "Type": "REVENUE"}
        )
        print("    created 201 Trading Income")
    if "200" in codes and codes["200"].get("Status") == "ACTIVE":
        await archive_account(api, db, tenant_id, codes["200"])
    await api.create_or_update_contact(
        db, tenant_id, {"Name": "Acme Corp", "EmailAddress": "ap@acme.example", "IsSupplier": True}
    )
    print("    contact variant: Acme Corp")


async def seed_org_c(api: XeroApi, db, tenant_id: str) -> None:
    print("  Org C: archive ALL revenue accounts (forces the refusal beat)")
    accounts = await api.list_accounts(db, tenant_id)
    for account in accounts:
        if account.get("Type") == "REVENUE" and account.get("Status") == "ACTIVE":
            await archive_account(api, db, tenant_id, account)


async def seed_po(api: XeroApi, db, tenant_id: str) -> None:
    print("  Org A: open purchase order for the PO-to-Bill demo")
    po = {
        "Contact": {"Name": "Bounce Cleaning Services"},
        "LineItems": [
            {"Description": "Deep clean - foam pits", "Quantity": 3, "UnitAmount": 250.0, "AccountCode": "408"},
            {"Description": "Trampoline bed sanitising", "Quantity": 10, "UnitAmount": 45.0, "AccountCode": "408"},
            {"Description": "Consumables (PPE, solution)", "Quantity": 1, "UnitAmount": 180.0, "AccountCode": "408"},
        ],
        "Status": "AUTHORISED",
    }
    data = await api.request(db, tenant_id, "PUT", "/PurchaseOrders", json={"PurchaseOrders": [po]})
    number = data["PurchaseOrders"][0].get("PurchaseOrderNumber")
    print(f"    created open PO {number} (3 lines, total 1,110.00)")


async def main(with_po: bool) -> None:
    init_db()
    db = SessionLocal()
    api = XeroApi()
    entities = db.query(Entity).filter_by(active=True).order_by(Entity.id).all()
    if len(entities) < 3:
        sys.exit(
            f"Need 3 connected orgs, found {len(entities)}. "
            "Connect them via http://localhost:8000/auth/xero/connect first."
        )
    a, b, c = entities[:3]
    print(f"Seeding: A={a.name} · B={b.name} · C={c.name}")
    await seed_org_a(api, db, a.tenant_id)
    await seed_org_b(api, db, b.tenant_id)
    await seed_org_c(api, db, c.tenant_id)
    if with_po:
        await seed_po(api, db, a.tenant_id)
    print("Done. Snapshots will refresh on next use (TTL) — or restart the backend.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-po", action="store_true", help="also create an open PO in org A")
    args = parser.parse_args()
    asyncio.run(main(args.with_po))
