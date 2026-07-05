"""Golden tests for the mapping engine — no network, injected LLM responses.

Each `complete` stand-in simulates what a correct model would return given the
snapshot the engine put in the prompt, so these assert the real intelligence
beats deterministically: the 200->201 translation, the refusal in an org with
no revenue account, and contact dedup against a name variant.
"""

import pytest

from app.engines.mapping import map_change
from app.models import Entity

ITEM_SOURCE = {
    "Code": "TRAMP-SOCK",
    "Name": "Trampoline Grip Socks",
    "IsSold": True,
    "SalesDetails": {"UnitPrice": 3.5, "AccountCode": "200", "TaxType": "OUTPUT2"},
}


def _entity(name: str, tenant_id: str) -> Entity:
    return Entity(tenant_id=tenant_id, name=name)


def snap(accounts=None, tax_rates=None, contacts=None, items=None, tracking=None) -> dict:
    return {
        "accounts": accounts or [],
        "tax_rates": tax_rates or [],
        "contacts": contacts or [],
        "items": items or [],
        "tracking_categories": tracking or [],
    }


def item_model():
    """Stand-in: map the item's revenue account to whatever active revenue code
    the snapshot actually contains; refuse if there is none."""

    async def complete(system, user, schema):
        if '"Code": "201"' in user:
            return {
                "action": "create-item",
                "mapped_payload": {
                    "Code": "TRAMP-SOCK",
                    "Name": "Trampoline Grip Socks",
                    "IsSold": True,
                    "SalesDetails": {"UnitPrice": 3.5, "AccountCode": "201", "TaxType": "OUTPUT2"},
                },
                "confidence": 0.95,
                "reasoning": "Org has no 200; mapped to 201 Trading Income.",
                "needs_human": False,
            }
        return {
            "action": "create-item",
            "mapped_payload": {"Code": "TRAMP-SOCK", "Name": "Trampoline Grip Socks"},
            "confidence": 0.2,
            "reasoning": "No active revenue account exists to map this item to.",
            "needs_human": True,
        }

    return complete


@pytest.mark.asyncio
async def test_item_maps_200_to_201_in_org_b():
    b = _entity("Org B", "tenant-b")
    snapshot = snap(
        accounts=[{"Code": "201", "Name": "Trading Income", "Type": "REVENUE", "Status": "ACTIVE"}],
        tax_rates=[{"TaxType": "OUTPUT2", "Name": "20% VAT"}],
    )
    prop = await map_change(item_model(), "item", ITEM_SOURCE, b, snapshot)
    assert prop.action == "create-item"
    assert prop.needs_human is False
    assert prop.mapped_payload["SalesDetails"]["AccountCode"] == "201"


@pytest.mark.asyncio
async def test_item_refuses_when_no_revenue_account():
    c = _entity("Org C", "tenant-c")
    snapshot = snap(accounts=[{"Code": "400", "Name": "Advertising", "Type": "EXPENSE", "Status": "ACTIVE"}])
    prop = await map_change(item_model(), "item", ITEM_SOURCE, c, snapshot)
    assert prop.needs_human is True
    # never invents a code
    assert prop.mapped_payload.get("SalesDetails", {}).get("AccountCode") is None


def contact_model():
    async def complete(system, user, schema):
        if "Acme Corporation Ltd" in user:
            return {
                "action": "create-contact",
                "mapped_payload": {"Name": "Acme Corporation Ltd", "ContactID": "c-b-1"},
                "confidence": 0.9,
                "reasoning": "Matches existing 'Acme Corporation Ltd' — linking, not duplicating.",
                "needs_human": False,
            }
        return {
            "action": "create-contact",
            "mapped_payload": {"Name": "Acme Corp"},
            "confidence": 0.8,
            "reasoning": "No existing match; creating new contact.",
            "needs_human": False,
        }

    return complete


@pytest.mark.asyncio
async def test_contact_dedup_links_to_existing_variant():
    b = _entity("Org B", "tenant-b")
    snapshot = snap(contacts=[{"ContactID": "c-b-1", "Name": "Acme Corporation Ltd"}])
    prop = await map_change(contact_model(), "contact", {"Name": "Acme Corp"}, b, snapshot)
    assert prop.mapped_payload.get("ContactID") == "c-b-1"


@pytest.mark.asyncio
async def test_guard_flags_payload_referencing_missing_account_code():
    """The model reasons a remap (300 -> 310) but leaves 300 in the payload — the
    deterministic guard must catch it and force needs_human so it can't be written."""

    async def inconsistent(system, user, schema):
        return {
            "action": "create-item",
            "mapped_payload": {
                "Code": "SAFETY-NET",
                "Name": "Safety Net",
                "SalesDetails": {"AccountCode": "200", "TaxType": "OUTPUT2"},
                "PurchaseDetails": {"AccountCode": "300", "TaxType": "INPUT2"},  # 300 not in snapshot
            },
            "confidence": 0.98,
            "reasoning": "Mapped purchases to 310 Cost of Goods Sold.",  # says 310, payload says 300
            "needs_human": False,
        }

    entity = _entity("Org D", "tenant-d")
    snapshot = snap(
        accounts=[
            {"Code": "200", "Name": "Sales", "Type": "REVENUE", "Status": "ACTIVE"},
            {"Code": "310", "Name": "Cost of Goods Sold", "Type": "DIRECTCOSTS", "Status": "ACTIVE"},
        ]
    )
    prop = await map_change(inconsistent, "item", ITEM_SOURCE, entity, snapshot)
    assert prop.needs_human is True
    assert prop.confidence <= 0.4
    assert "300" in prop.reasoning


@pytest.mark.asyncio
async def test_guard_passes_when_all_codes_exist():
    async def consistent(system, user, schema):
        return {
            "action": "create-item",
            "mapped_payload": {
                "Code": "SAFETY-NET",
                "Name": "Safety Net",
                "SalesDetails": {"AccountCode": "200", "TaxType": "OUTPUT2"},
                "PurchaseDetails": {"AccountCode": "310", "TaxType": "INPUT2"},
            },
            "confidence": 0.98,
            "reasoning": "Both sides map to codes that exist here.",
            "needs_human": False,
        }

    entity = _entity("Org E", "tenant-e")
    snapshot = snap(
        accounts=[
            {"Code": "200", "Name": "Sales", "Type": "REVENUE", "Status": "ACTIVE"},
            {"Code": "310", "Name": "Cost of Goods Sold", "Type": "DIRECTCOSTS", "Status": "ACTIVE"},
        ]
    )
    prop = await map_change(consistent, "item", ITEM_SOURCE, entity, snapshot)
    assert prop.needs_human is False
    assert prop.confidence == 0.98


@pytest.mark.asyncio
async def test_tracking_creates_new_category_with_options():
    """A tracking category not already present is propagated with its Options intact."""

    async def complete(system, user, schema):
        return {
            "action": "create-tracking-category",
            "mapped_payload": {"Name": "Department", "Options": ["Sales", "Ops"]},
            "confidence": 0.95,
            "reasoning": "No category named Department exists here; creating with its options.",
            "needs_human": False,
        }

    e = _entity("Org H", "tenant-h")
    snapshot = snap(tracking=[])
    prop = await map_change(complete, "tracking", {"Name": "Department", "Options": ["Sales", "Ops"]}, e, snapshot)
    assert prop.action == "create-tracking-category"
    assert prop.needs_human is False
    assert prop.mapped_payload["Options"] == ["Sales", "Ops"]


@pytest.mark.asyncio
async def test_tracking_refuses_when_category_name_exists():
    """Xero won't create a second category with the same Name — refuse rather than fail."""

    async def complete(system, user, schema):
        return {
            "action": "create-tracking-category",
            "mapped_payload": {"Name": "Region"},
            "confidence": 0.2,
            "reasoning": "A tracking category named Region already exists here; refusing.",
            "needs_human": True,
        }

    e = _entity("Org I", "tenant-i")
    snapshot = snap(tracking=[{"Name": "Region", "Options": [{"Name": "North"}]}])
    prop = await map_change(complete, "tracking", {"Name": "Region", "Options": ["North", "South"]}, e, snapshot)
    assert prop.needs_human is True


@pytest.mark.asyncio
async def test_account_guard_flags_duplicate_name():
    """Xero requires unique account Name (not just Code). If the model proposes a
    create whose Name already exists here, the guard must force needs_human so it
    can't fail at write time."""

    async def dup_name(system, user, schema):
        return {
            "action": "create-account",
            "mapped_payload": {"Code": "8100", "Name": "Software Subscriptions", "Type": "EXPENSE"},
            "confidence": 0.98,
            "reasoning": "Code 8100 is free, creating.",  # missed the name clash
            "needs_human": False,
        }

    entity = _entity("Org F", "tenant-f")
    snapshot = snap(
        accounts=[{"Code": "897", "Name": "Software Subscriptions", "Type": "EXPENSE", "Status": "ACTIVE"}]
    )
    prop = await map_change(dup_name, "account", {"Code": "8100", "Name": "Software Subscriptions", "Type": "EXPENSE"}, entity, snapshot)
    assert prop.needs_human is True
    assert prop.confidence <= 0.4
    assert "Software Subscriptions" in prop.reasoning


@pytest.mark.asyncio
async def test_account_guard_passes_when_code_and_name_free():
    async def fresh(system, user, schema):
        return {
            "action": "create-account",
            "mapped_payload": {"Code": "8200", "Name": "Cloud Software Licences", "Type": "EXPENSE"},
            "confidence": 0.98,
            "reasoning": "Both code and name are free here.",
            "needs_human": False,
        }

    entity = _entity("Org G", "tenant-g")
    snapshot = snap(accounts=[{"Code": "897", "Name": "Software Subscriptions", "Type": "EXPENSE", "Status": "ACTIVE"}])
    prop = await map_change(fresh, "account", {"Code": "8200", "Name": "Cloud Software Licences", "Type": "EXPENSE"}, entity, snapshot)
    assert prop.needs_human is False
    assert prop.confidence == 0.98


@pytest.mark.asyncio
async def test_malformed_llm_response_raises():
    async def bad(system, user, schema):
        return {  # confidence out of range → EngineProposal rejects it
            "action": "create-item",
            "mapped_payload": {},
            "confidence": 2.0,
            "reasoning": "x",
            "needs_human": False,
        }

    with pytest.raises(Exception):
        await map_change(bad, "item", ITEM_SOURCE, _entity("X", "t"), snap())


@pytest.mark.asyncio
async def test_unknown_change_type_raises():
    async def any_response(system, user, schema):
        return {}

    with pytest.raises(ValueError):
        await map_change(any_response, "invoice", {}, _entity("X", "t"), snap())
