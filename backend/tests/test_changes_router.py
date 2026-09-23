"""Drives the /changes fan-out handler directly (no TestClient — cleaner with
the in-memory DB) with an injected engine and a tenant-aware fake Xero transport
that feeds each entity a different chart of accounts.
"""

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.models import Entity
from app.routers.changes import ChangeRequest, create_change
from app.xero.client import XeroApi
from tests.test_mapping import ITEM_SOURCE, item_model


class TenantAwareTransport(httpx.AsyncBaseTransport):
    """Returns different snapshot data per Xero-Tenant-Id so B and C differ."""

    def __init__(self, by_tenant: dict[str, dict[str, dict]]):
        self.by_tenant = by_tenant

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        tenant = request.headers.get("Xero-Tenant-Id", "")
        path = request.url.path
        for suffix, body in self.by_tenant.get(tenant, {}).items():
            if path.endswith(suffix):
                return httpx.Response(200, json=body)
        return httpx.Response(200, json={})  # unmatched list endpoints → empty


@pytest.mark.asyncio
async def test_create_change_fans_out_and_persists(db, token):
    b = Entity(tenant_id="tenant-b", name="Org B")
    c = Entity(tenant_id="tenant-c", name="Org C")
    db.add_all([b, c])
    db.commit()

    transport = TenantAwareTransport(
        {
            "tenant-b": {
                "/Accounts": {
                    "Accounts": [
                        {"Code": "201", "Name": "Trading Income", "Type": "REVENUE", "Status": "ACTIVE"}
                    ]
                }
            },
            "tenant-c": {
                "/Accounts": {
                    "Accounts": [
                        {"Code": "400", "Name": "Advertising", "Type": "EXPENSE", "Status": "ACTIVE"}
                    ]
                }
            },
        }
    )
    api = XeroApi(transport=transport)
    body = ChangeRequest(change_type="item", payload=ITEM_SOURCE, target_entity_ids=[b.id, c.id])

    result = await create_change(body=body, db=db, complete=item_model(), api=api)

    assert result["kind"] == "propagation"
    assert result["change_type"] == "item"
    assert len(result["proposals"]) == 2
    by_entity = {p["entity_name"]: p for p in result["proposals"]}
    assert by_entity["Org B"]["needs_human"] is False
    assert by_entity["Org B"]["mapped_payload"]["SalesDetails"]["AccountCode"] == "201"
    assert by_entity["Org C"]["needs_human"] is True


@pytest.mark.asyncio
async def test_create_change_rejects_unknown_entity(db, token):
    api = XeroApi(transport=TenantAwareTransport({}))
    body = ChangeRequest(change_type="item", payload=ITEM_SOURCE, target_entity_ids=[999])
    with pytest.raises(Exception) as exc:
        await create_change(body=body, db=db, complete=item_model(), api=api)
    assert "999" in str(exc.value)


@pytest.mark.asyncio
async def test_one_entity_failing_keeps_the_others(db, token):
    # An LLM error for one org must not 500 the request and discard the proposals
    # already produced for every other org.
    b = Entity(tenant_id="tenant-b", name="Org B")
    c = Entity(tenant_id="tenant-c", name="Org C")
    db.add_all([b, c])
    db.commit()
    good = item_model()

    async def flaky(system, user, schema):
        if "Org C" in user:
            raise TimeoutError("LLM endpoint timed out")
        return await good(system, user, schema)

    transport = TenantAwareTransport(
        {"tenant-b": {"/Accounts": {"Accounts": [{"Code": "201", "Name": "Trading Income", "Status": "ACTIVE"}]}}}
    )
    body = ChangeRequest(change_type="item", payload=ITEM_SOURCE, target_entity_ids=[b.id, c.id])
    result = await create_change(body=body, db=db, complete=flaky, api=XeroApi(transport=transport))

    by_entity = {p["entity_name"]: p for p in result["proposals"]}
    assert by_entity["Org B"]["needs_human"] is False
    failed = by_entity["Org C"]
    assert failed["needs_human"] is True
    assert failed["confidence"] == 0.0
    assert failed["action"] == "create-item"
    assert "timed out" in failed["reasoning"]


@pytest.mark.asyncio
async def test_entities_are_mapped_concurrently(db, token):
    # Each mapping call waits until BOTH are in flight; sequential fan-out would
    # never get there and time out.
    b = Entity(tenant_id="tenant-b", name="Org B")
    c = Entity(tenant_id="tenant-c", name="Org C")
    db.add_all([b, c])
    db.commit()
    in_flight = 0
    both = asyncio.Event()
    inner = item_model()

    async def barrier(system, user, schema):
        nonlocal in_flight
        in_flight += 1
        if in_flight == 2:
            both.set()
        await asyncio.wait_for(both.wait(), timeout=2)
        return await inner(system, user, schema)

    body = ChangeRequest(change_type="item", payload=ITEM_SOURCE, target_entity_ids=[b.id, c.id])
    result = await create_change(
        body=body, db=db, complete=barrier, api=XeroApi(transport=TenantAwareTransport({}))
    )
    assert len(result["proposals"]) == 2


@pytest.mark.asyncio
async def test_non_propagatable_change_type_is_a_400(db, token, entity):
    body = ChangeRequest(change_type="bill", payload={}, target_entity_ids=[entity.id])
    with pytest.raises(HTTPException) as exc:
        await create_change(
            body=body, db=db, complete=item_model(), api=XeroApi(transport=TenantAwareTransport({}))
        )
    assert exc.value.status_code == 400
