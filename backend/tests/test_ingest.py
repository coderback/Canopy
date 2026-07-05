"""Tests for the universal ingest adapter (Bounty 02).

No network, no LLM: parsing is deterministic and the engines take an injected
`complete` stand-in that returns what a correct model would, so we assert the
real behaviour — messy-file tolerance, balanced journals on real codes, the code
guard, and the refuse-don't-guess beat on a missing value.
"""

from pathlib import Path

import httpx
import pytest

from app.engines.contracts import validate_payload
from app.engines.ingest import (
    IngestClassification,
    IngestIntent,
    classify_ingest,
    map_ingest_to_journal,
)
from app.ingest_parse import UnsupportedFileError, parse_upload
from app.models import Entity
from app.routers.ingest import ingest_file, match_site_to_entity
from app.xero.client import XeroApi

FIXTURES = Path(__file__).resolve().parents[2] / "seed" / "fixtures"


def snap(accounts=None, tax_rates=None):
    return {
        "accounts": accounts or [],
        "tax_rates": tax_rates or [],
        "contacts": [],
        "items": [],
        "tracking_categories": [],
    }


REVENUE_ACCOUNTS = [
    {"Code": "200", "Name": "Sales", "Type": "REVENUE", "Status": "ACTIVE"},
    {"Code": "610", "Name": "Accounts Receivable", "Type": "CURRENT", "Status": "ACTIVE"},
]


# ---- parsing ---------------------------------------------------------------


def test_parse_messy_sortly_csv_keeps_raw_grid():
    data = (FIXTURES / "sortly_stock_count.csv").read_bytes()
    parsed = parse_upload("sortly_stock_count.csv", data)
    assert parsed["kind"] == "csv"
    # Title row, header-not-first, TOTALS row and blank trailing columns all survive
    # verbatim in the grid — interpreting them is the model's job.
    assert "Sortly Export" in parsed["grid"]
    assert "Party Balloons" in parsed["grid"]
    assert "TOTALS" in parsed["grid"]
    assert isinstance(parsed["rows"], list) and isinstance(parsed["rows"][0], list)


def test_parse_json_supplier_invoice():
    data = (FIXTURES / "supplier_invoice.json").read_bytes()
    parsed = parse_upload("supplier_invoice.json", data)
    assert parsed["kind"] == "json"
    assert parsed["rows"]["invoice_number"] == "BCS-2026-0714"


def test_parse_rejects_unknown_type():
    with pytest.raises(UnsupportedFileError):
        parse_upload("notes.txt", b"hello")


# ---- site matching ---------------------------------------------------------


def test_site_matches_entity_by_distinguishing_token():
    orgs = [Entity(tenant_id="t1", name="Demo Bristol Ltd"), Entity(tenant_id="t2", name="Demo London Ltd")]
    assert match_site_to_entity("Bristol ", orgs).name == "Demo Bristol Ltd"
    assert match_site_to_entity("london", orgs).name == "Demo London Ltd"
    assert match_site_to_entity("Cardiff", orgs) is None
    assert match_site_to_entity("Demo", orgs) is None  # stop-token only → no match


# ---- classification (pass 1) -----------------------------------------------


def classify_stub():
    async def complete(system, user, schema):
        return {
            "doc_type": "POS daily revenue settlement",
            "human_description": "A daily takings export from a POS; book takings as revenue per venue.",
            "target_action": "create-manual-journal",
            "intents": [
                {
                    "site": "Bristol",
                    "description": "Daily takings (card + cash)",
                    "amount": 2735.50,
                    "direction": "revenue",
                    "suggested_treatment": "Credit sales, debit receivable",
                    "needs_review": False,
                    "review_reason": None,
                }
            ],
            "caveats": [],
        }

    return complete


@pytest.mark.asyncio
async def test_classify_returns_validated_classification():
    result = await classify_ingest(classify_stub(), "roller.csv", "0: ...\n1: Bristol,CARD,2735.50")
    assert isinstance(result, IngestClassification)
    assert result.doc_type
    assert result.intents[0].site == "Bristol"
    assert result.intents[0].direction == "revenue"


# ---- per-entity journal (pass 2) -------------------------------------------


def journal_stub(lines):
    async def complete(system, user, schema):
        return {
            "action": "create-manual-journal",
            "mapped_payload": {"Narration": "POS revenue - Bristol", "JournalLines": lines},
            "confidence": 0.9,
            "reasoning": "Credited 200 Sales and debited 610 Accounts Receivable for the day's takings.",
            "needs_human": False,
        }

    return complete


BRISTOL_INTENT = IngestIntent(site="Bristol", description="Daily takings", amount=2735.50, direction="revenue")


@pytest.mark.asyncio
async def test_journal_is_balanced_and_uses_real_codes():
    entity = Entity(tenant_id="t-bristol", name="Demo Bristol Ltd")
    lines = [
        {"LineAmount": 2735.50, "AccountCode": "610", "Description": "Takings receivable"},
        {"LineAmount": -2735.50, "AccountCode": "200", "Description": "Sales"},
    ]
    classification = IngestClassification(doc_type="POS", human_description="x")
    prop = await map_ingest_to_journal(
        journal_stub(lines), classification, [BRISTOL_INTENT], entity, snap(accounts=REVENUE_ACCOUNTS)
    )
    assert prop.action == "create-manual-journal"
    assert prop.needs_human is False
    # The golden payload is write-valid: balances to zero on codes that exist here.
    normalised = validate_payload("create-manual-journal", prop.mapped_payload)
    assert {ln["AccountCode"] for ln in normalised["JournalLines"]} == {"200", "610"}


@pytest.mark.asyncio
async def test_journal_guard_flags_nonexistent_code():
    entity = Entity(tenant_id="t-x", name="Org X")
    lines = [
        {"LineAmount": 100.0, "AccountCode": "999", "Description": "Bad code"},  # not in snapshot
        {"LineAmount": -100.0, "AccountCode": "200", "Description": "Sales"},
    ]
    classification = IngestClassification(doc_type="POS", human_description="x")
    prop = await map_ingest_to_journal(
        journal_stub(lines), classification, [BRISTOL_INTENT], entity, snap(accounts=REVENUE_ACCOUNTS)
    )
    assert prop.needs_human is True
    assert prop.confidence <= 0.4
    assert "999" in prop.reasoning


@pytest.mark.asyncio
async def test_missing_value_intent_forces_needs_human():
    """The refuse-don't-guess beat: a source row with a missing amount must block
    approval even if the model's journal looked confident."""
    entity = Entity(tenant_id="t-y", name="Org Y")
    lines = [
        {"LineAmount": 50.0, "AccountCode": "610", "Description": "x"},
        {"LineAmount": -50.0, "AccountCode": "200", "Description": "y"},
    ]
    flagged = IngestIntent(
        site="Bristol", description="Party Balloons", amount=None, direction="cost",
        needs_review=True, review_reason="unit cost missing",
    )
    classification = IngestClassification(doc_type="stock count", human_description="x")
    prop = await map_ingest_to_journal(
        journal_stub(lines), classification, [flagged], entity, snap(accounts=REVENUE_ACCOUNTS)
    )
    assert prop.needs_human is True
    assert "unit cost missing" in prop.reasoning


# ---- end-to-end orchestration (ingest_file) --------------------------------


class _AccountsTransport(httpx.AsyncBaseTransport):
    """Every tenant returns the same revenue chart; other list endpoints empty."""

    async def handle_async_request(self, request):
        if request.url.path.endswith("/Accounts"):
            return httpx.Response(200, json={"Accounts": REVENUE_ACCOUNTS})
        return httpx.Response(200, json={})


def combined_stub():
    async def complete(system, user, schema):
        if "doc_type" in schema.get("properties", {}):
            return {
                "doc_type": "POS daily revenue settlement",
                "human_description": "Daily takings per venue.",
                "target_action": "create-manual-journal",
                "intents": [
                    {"site": "Bristol", "description": "Takings", "amount": 2735.5, "direction": "revenue", "needs_review": False, "review_reason": None},
                    {"site": "London", "description": "Takings", "amount": 4066.25, "direction": "revenue", "needs_review": False, "review_reason": None},
                ],
                "caveats": [],
            }
        return {
            "action": "create-manual-journal",
            "mapped_payload": {
                "Narration": "POS revenue",
                "JournalLines": [
                    {"LineAmount": 100.0, "AccountCode": "610", "Description": "Receivable"},
                    {"LineAmount": -100.0, "AccountCode": "200", "Description": "Sales"},
                ],
            },
            "confidence": 0.9,
            "reasoning": "Credited 200, debited 610.",
            "needs_human": False,
        }

    return complete


@pytest.mark.asyncio
async def test_ingest_file_fans_out_and_flags_unmatched_entity(db, token):
    bristol = Entity(tenant_id="t-bristol", name="Demo Bristol Ltd")
    london = Entity(tenant_id="t-london", name="Demo London Ltd")
    manchester = Entity(tenant_id="t-manch", name="Demo Manchester Ltd")  # no matching rows
    db.add_all([bristol, london, manchester])
    db.commit()

    api = XeroApi(transport=_AccountsTransport())
    data = (FIXTURES / "roller_revenue_live.csv").read_bytes()
    run = await ingest_file(
        db, combined_stub(), api, "roller_revenue_live.csv", data,
        [bristol.id, london.id, manchester.id],
    )

    assert run["kind"] == "ingest"
    assert run["change_type"] == "manual_journal"
    assert run["source_payload"]["doc_type"] == "POS daily revenue settlement"
    by_entity = {p["entity_name"]: p for p in run["proposals"]}
    assert by_entity["Demo Bristol Ltd"]["needs_human"] is False
    assert by_entity["Demo London Ltd"]["needs_human"] is False
    # Manchester had no matching rows → refused, not attributed another site's figures.
    assert by_entity["Demo Manchester Ltd"]["needs_human"] is True
    assert by_entity["Demo Manchester Ltd"]["mapped_payload"] == {}
