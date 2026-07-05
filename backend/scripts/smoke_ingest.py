"""Live end-to-end smoke test for the universal ingest adapter (Bounty 02).

Runs the REAL pipeline in-process against the connected Xero orgs:
parse -> classify (LLM) -> per-entity manual-journal mapping (LLM, against each
org's live chart) -> guards -> [approve -> write -> read back].

Usage (from the backend/ dir, venv active):
    python scripts/smoke_ingest.py --dry-run   # reads + maps only, NO writes
    python scripts/smoke_ingest.py             # also writes DRAFT journals + reads back

--dry-run needs only the Phase-1 scopes (accounting.settings) and proves the
mapping/guards live. The real write needs `accounting.transactions` on the token:
enable it in the Xero app portal Configuration, then re-consent via
GET /auth/xero/connect. The script refuses to write if that scope is missing.
"""

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.db import SessionLocal, init_db  # noqa: E402
from app.engines.ingest import _nonpostable_accounts  # noqa: E402
from app.engines.llm import complete_structured  # noqa: E402
from app.execution import execute_run  # noqa: E402
from app.models import Entity, Run  # noqa: E402
from app.routers.ingest import ingest_file  # noqa: E402
from app.snapshots import get_entity_context  # noqa: E402
from app.xero import auth  # noqa: E402
from app.xero.client import xero_api  # noqa: E402

FIXTURE = REPO / "seed" / "fixtures" / "roller_revenue_live.csv"
TARGET_NAMES = ["Demo Bristol Ltd", "Demo London Ltd", "Demo Manchester Ltd"]


def _journal_lines(payload: dict) -> list[dict]:
    return payload.get("JournalLines", []) or []


async def main(dry_run: bool) -> int:
    init_db()
    db = SessionLocal()

    token = auth.load_token(db)
    if not token:
        print("FAIL: no Xero token stored — connect via GET /auth/xero/connect first.")
        return 2
    scopes = token.get("scope", "")
    has_txn = "accounting.transactions" in scopes
    print(f"token scopes: {scopes}")
    print(f"accounting.transactions present: {has_txn}")
    if not dry_run and not has_txn:
        print(
            "\nFAIL: writing manual journals needs `accounting.transactions`.\n"
            "  1) Xero app portal -> Configuration -> enable accounting.transactions\n"
            "  2) re-consent: open GET /auth/xero/connect and approve\n"
            "  3) re-run this script (or add --dry-run to test read+map only)."
        )
        return 3

    entities = (
        db.query(Entity)
        .filter(Entity.name.in_(TARGET_NAMES), Entity.active.is_(True))
        .all()
    )
    if not entities:
        print(f"FAIL: none of {TARGET_NAMES} are active in the registry.")
        return 4
    ids = [e.id for e in entities]
    print(f"targets: {[(e.id, e.name) for e in entities]}")
    print(f"fixture: {FIXTURE.name}\n")

    run = await ingest_file(db, complete_structured, xero_api, FIXTURE.name, FIXTURE.read_bytes(), ids)

    src = run["source_payload"]
    print(f"== classified: {src['doc_type']} ==")
    print(f"   {src['human_description']}")
    for c in src.get("caveats", []):
        print(f"   caveat: {c}")
    print()

    # Show each proposal + independently confirm every posted line is postable.
    all_postable = True
    for p in run["proposals"]:
        entity = db.get(Entity, p["entity_id"])
        snapshot = await get_entity_context(db, xero_api, entity)
        blocked = _nonpostable_accounts(snapshot)
        flag = "NEEDS-HUMAN" if p["needs_human"] else "ok"
        print(f"[{flag}] {p['entity_name']}  conf={p['confidence']:.2f}")
        print(f"   reasoning: {p['reasoning']}")
        for ln in _journal_lines(p["mapped_payload"]):
            code = str(ln.get("AccountCode"))
            bad = code in blocked
            all_postable = all_postable and (not bad or p["needs_human"])
            mark = f"  <-- NOT POSTABLE ({blocked[code]})" if bad else ""
            print(f"     {ln.get('LineAmount'):>10}  {code}  {ln.get('Description','')}{mark}")
        print()

    if dry_run:
        print("DRY RUN — no writes performed.")
        print("postable check:", "PASS" if all_postable else "FAIL (a writable row targets a blocked account)")
        return 0 if all_postable else 5

    # Approve the confident rows and write.
    run_obj = db.get(Run, run["id"])
    for p in run_obj.proposals:
        if not p.needs_human:
            p.status = "approved"
    run_obj.status = "approved"
    db.commit()
    await execute_run(db, xero_api, run_obj)
    db.refresh(run_obj)
    print(f"== run status: {run_obj.status} ==")

    # Read every written journal back from Xero to prove it landed.
    ok = True
    for p in run_obj.proposals:
        wr = p.write_results[-1] if p.write_results else None
        if wr is None:
            print(f"   {p.entity.name}: skipped (needs human / excluded)")
        elif wr.success:
            mj = await xero_api.request(db, p.entity.tenant_id, "GET", f"/ManualJournals/{wr.xero_id}")
            j = (mj.get("ManualJournals") or [{}])[0]
            print(f"   {p.entity.name}: WROTE {wr.xero_id}  status={j.get('Status')}  '{j.get('Narration')}'")
        else:
            ok = False
            print(f"   {p.entity.name}: WRITE FAILED — {wr.error}")
    return 0 if ok else 6


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="read + map only, no writes")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.dry_run)))
