"""Dev-only demo support so the approval UI is clickable without live Xero.

`seed_demo` inserts three entities and one ready-made propagation run (an item
change fanned across them: clean in A, the 200->201 mapping in B, a refusal in
C). `DemoXeroApi` stands in for real Xero on approval so writes "succeed" with
fake ids — the results-fill-in-place beat works end-to-end offline. None of this
runs when demo_mode is off or a real Xero token is connected.
"""

import uuid

from sqlalchemy.orm import Session

from .models import Entity, Proposal, Run
from .xero.client import XeroApi

DEMO_ITEM_SOURCE = {
    "Code": "TRAMP-SOCK",
    "Name": "Trampoline Grip Socks",
    "IsSold": True,
    "SalesDetails": {"UnitPrice": 3.5, "AccountCode": "200", "TaxType": "OUTPUT2"},
}

_DEMO_ENTITIES = [
    ("demo-tenant-a", "Acme Trampolines (Bristol) Ltd"),
    ("demo-tenant-b", "Acme Trampolines (Guildford) Ltd"),
    ("demo-tenant-c", "Acme Trampolines (Cardiff) Ltd"),
]


class DemoXeroApi(XeroApi):
    """Returns canned successful writes so approval works with no live Xero."""

    def _ok(self, payload: dict, id_field: str) -> dict:
        return {**payload, id_field: f"demo-{uuid.uuid4().hex[:12]}"}

    async def create_or_update_contact(self, db, tenant_id, contact):
        return self._ok(contact, "ContactID")

    async def create_or_update_item(self, db, tenant_id, item):
        return self._ok(item, "ItemID")

    async def create_account(self, db, tenant_id, account):
        return self._ok(account, "AccountID")

    async def create_tracking_category(self, db, tenant_id, category):
        return self._ok(category, "TrackingCategoryID")

    async def add_tracking_option(self, db, tenant_id, category_id, option):
        return self._ok(option, "TrackingOptionID")

    async def create_manual_journal(self, db, tenant_id, journal):
        return self._ok(journal, "ManualJournalID")

    async def create_draft_bill(self, db, tenant_id, bill):
        return self._ok({**bill, "Type": "ACCPAY", "Status": "DRAFT"}, "InvoiceID")


demo_api = DemoXeroApi()


def ensure_demo_entities(db: Session) -> list[Entity]:
    entities = []
    for tenant_id, name in _DEMO_ENTITIES:
        entity = db.query(Entity).filter_by(tenant_id=tenant_id).one_or_none()
        if entity is None:
            entity = Entity(tenant_id=tenant_id, name=name)
            db.add(entity)
        entities.append(entity)
    db.commit()
    return entities


def seed_demo_run(db: Session) -> Run:
    """One propagation run with the three flagship proposal states."""
    a, b, c = ensure_demo_entities(db)
    run = Run(
        kind="propagation",
        change_type="item",
        source_payload=DEMO_ITEM_SOURCE,
        status="proposed",
    )
    db.add(run)
    db.flush()

    proposals = [
        Proposal(
            run_id=run.id,
            entity_id=a.id,
            action="create-item",
            mapped_payload=DEMO_ITEM_SOURCE,
            confidence=0.99,
            reasoning="Account 200 Sales exists here and the OUTPUT2 tax type matches — a direct copy.",
            needs_human=False,
            status="proposed",
        ),
        Proposal(
            run_id=run.id,
            entity_id=b.id,
            action="create-item",
            mapped_payload={
                "Code": "TRAMP-SOCK",
                "Name": "Trampoline Grip Socks",
                "IsSold": True,
                "SalesDetails": {"UnitPrice": 3.5, "AccountCode": "201", "TaxType": "OUTPUT2"},
            },
            confidence=0.98,
            reasoning="This entity has no active 200; mapped sales to 201 Trading Income, the equivalent revenue account. OUTPUT2 exists and is preserved.",
            needs_human=False,
            status="proposed",
        ),
        Proposal(
            run_id=run.id,
            entity_id=c.id,
            action="create-item",
            mapped_payload={"Code": "TRAMP-SOCK", "Name": "Trampoline Grip Socks", "IsSold": True},
            confidence=0.2,
            reasoning="No active revenue account exists in this entity to map the item's sales to. Refusing rather than guessing a code — a human must decide.",
            needs_human=True,
            status="proposed",
        ),
    ]
    db.add_all(proposals)
    db.commit()
    db.refresh(run)
    return run


# --- Universal ingest demo (Bounty 02), fully offline ----------------------

DEMO_INGEST_SOURCE = {
    "filename": "roller_revenue.csv",
    "doc_type": "POS daily revenue settlement",
    "human_description": (
        "A daily takings export from a ROLLER POS system — book each venue's card + "
        "cash takings for 2026-07-01 as revenue, one manual journal per entity."
    ),
    "intents": [
        {"site": "Bristol", "description": "Card + cash takings", "amount": 2735.50, "direction": "revenue", "needs_review": False, "review_reason": None},
        {"site": "Guildford", "description": "Card + cash takings", "amount": 2066.25, "direction": "revenue", "needs_review": False, "review_reason": None},
        {"site": "Cardiff", "description": "Card + voucher takings", "amount": 1629.00, "direction": "revenue", "needs_review": True, "review_reason": "no active revenue account in this entity to book against"},
    ],
    "caveats": ["Cardiff has no active revenue account to book takings against — flagged for review."],
}


def seed_demo_ingest_run(db: Session) -> Run:
    """One ingest run retelling the flagship states as manual journals: a clean
    booking, a revenue-account remap (no 200 → 201), and a refusal. No LLM, no
    Xero — approval still writes via DemoXeroApi with fake ids."""
    a, b, c = ensure_demo_entities(db)
    run = Run(
        kind="ingest",
        change_type="manual_journal",
        source_payload=DEMO_INGEST_SOURCE,
        status="proposed",
    )
    db.add(run)
    db.flush()

    proposals = [
        Proposal(
            run_id=run.id,
            entity_id=a.id,
            action="create-manual-journal",
            mapped_payload={
                "Narration": "ROLLER takings 2026-07-01 — Bristol",
                "JournalLines": [
                    {"LineAmount": 2735.50, "AccountCode": "610", "Description": "Takings receivable"},
                    {"LineAmount": -2735.50, "AccountCode": "200", "Description": "Sales"},
                ],
            },
            confidence=0.97,
            reasoning="Bristol has 200 Sales and 610 Accounts Receivable; booked the day's £2,735.50 takings as revenue.",
            needs_human=False,
            status="proposed",
        ),
        Proposal(
            run_id=run.id,
            entity_id=b.id,
            action="create-manual-journal",
            mapped_payload={
                "Narration": "ROLLER takings 2026-07-01 — Guildford",
                "JournalLines": [
                    {"LineAmount": 2066.25, "AccountCode": "610", "Description": "Takings receivable"},
                    {"LineAmount": -2066.25, "AccountCode": "201", "Description": "Trading Income"},
                ],
            },
            confidence=0.95,
            reasoning="Guildford has no active 200; mapped revenue to 201 Trading Income, its equivalent revenue account. Debited 610 Accounts Receivable.",
            needs_human=False,
            status="proposed",
        ),
        Proposal(
            run_id=run.id,
            entity_id=c.id,
            action="create-manual-journal",
            mapped_payload={"Narration": "ROLLER takings 2026-07-01 — Cardiff"},
            confidence=0.2,
            reasoning="Cardiff has no active revenue account to book the takings against. Refusing rather than guessing a code — a human must decide.",
            needs_human=True,
            status="proposed",
        ),
    ]
    db.add_all(proposals)
    db.commit()
    db.refresh(run)
    return run