"""Connecting orgs, token handling, account sync and Xero quota behaviour."""

import asyncio
import time

import httpx
import pytest

from canopy.core.db import unit_of_work
from canopy.core.security import encrypt_json
from canopy.sync.service import FULL, INCREMENTAL, sync_entity_accounts
from canopy.xero.client import QuotaExhausted
from canopy.xero.models import XeroConnection
from canopy.xero.oauth import XeroIdentityClient
from canopy.xero.tokens import ConnectionRevoked, ConnectionTokens

from .helpers import auth, client_for, connect_orgs, make_entity, make_user, owner_scalar, sign_in


def account(aid, code, name, type_="EXPENSE", cls="EXPENSE", status="ACTIVE", updated="/Date(1700000000000+0000)/"):
    return {"AccountID": aid, "Code": code, "Name": name, "Type": type_, "Class": cls,
            "Status": status, "UpdatedDateUTC": updated}


class FakeAccounting(httpx.AsyncBaseTransport):
    """Accounting API /Accounts with Xero's quota headers; records requests."""

    def __init__(self, accounts, *, status=200, retry_after=None, min_remaining="55", day_remaining="4900"):
        self.accounts, self.status, self.retry_after = accounts, status, retry_after
        self.min_remaining, self.day_remaining = min_remaining, day_remaining
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        headers = {"X-MinLimit-Remaining": self.min_remaining, "X-DayLimit-Remaining": self.day_remaining,
                   "X-AppMinLimit-Remaining": "9000"}
        if self.status == 429:
            headers |= {"Retry-After": str(self.retry_after), "X-Rate-Limit-Problem": "day"}
            return httpx.Response(429, headers=headers, json={})
        return httpx.Response(200, headers=headers, json={"Accounts": self.accounts})


class StaticToken:
    async def access_token(self):
        return "token"


async def _entity():
    user = await make_user()
    ws = await auth.create_workspace(user, "G")
    return ws, user, await make_entity(ws, user, "tenant-a", "Org A")


async def test_connect_flow_stores_encrypted_tokens_creates_entities_and_queues_sync(xero_identity, jobs_in_memory):
    xero_identity.tenants.append({"id": "conn-2", "tenantId": "tenant-b", "tenantName": "Org B", "tenantType": "ORGANISATION"})
    async with client_for(xero_identity) as c:
        await sign_in(c, xero_identity)
        ws = (await c.post("/workspaces", json={"name": "G"})).json()["id"]
        start = await c.get(f"/workspaces/{ws}/xero/connect")
        assert "accounting.settings.read" in start.headers["location"]
        assert "accounting.transactions" not in start.headers["location"]  # read-only milestone
        await connect_orgs(c, xero_identity, ws)
        entities = (await c.get(f"/workspaces/{ws}/entities")).json()
    assert sorted(e["name"] for e in entities) == ["Org A", "Org B"]
    stored = owner_scalar("select token_encrypted from xero_connections")
    assert "r-1" not in stored and "access_token" not in stored  # encrypted at rest
    queued = [j for j in jobs_in_memory.jobs.values() if j["task_name"] == "sync_accounts"]
    assert len(queued) == 2 and all(j["args"]["kind"] == FULL for j in queued)
    assert {j["lock"] for j in queued} == {"tenant:tenant-a", "tenant:tenant-b"}


async def test_full_sync_mirrors_accounts_and_records_quota():
    ws, _, eid = await _entity()
    fake = FakeAccounting([account("a1", "400", "Advertising"), account("a2", "200", "Sales", "REVENUE", "REVENUE")])
    result = await sync_entity_accounts(ws, eid, FULL, transport=fake, tokens=StaticToken())
    assert result.records_seen == 2 and result.kind == FULL
    assert owner_scalar("select count(*) from entity_accounts where entity_id = :e", e=eid) == 2
    assert owner_scalar("select day_remaining from xero_quota where tenant_id = 'tenant-a'") == 4900
    assert owner_scalar("select sync_status from entities where id = :e", e=eid) == "ok"


async def test_full_sync_marks_vanished_accounts_deleted_but_never_on_an_empty_response():
    ws, _, eid = await _entity()
    await sync_entity_accounts(ws, eid, FULL, transport=FakeAccounting([account("a1", "400", "Ads"), account("a2", "401", "PR")]), tokens=StaticToken())
    r = await sync_entity_accounts(ws, eid, FULL, transport=FakeAccounting([account("a1", "400", "Ads")]), tokens=StaticToken())
    assert r.deleted == 1
    empty = await sync_entity_accounts(ws, eid, FULL, transport=FakeAccounting([]), tokens=StaticToken())
    assert empty.deleted == 0
    assert owner_scalar("select count(*) from entity_accounts where deleted_at is null") == 1


async def test_incremental_sync_sends_if_modified_since_from_xeros_own_timestamps():
    ws, _, eid = await _entity()
    await sync_entity_accounts(ws, eid, FULL, transport=FakeAccounting([account("a1", "400", "Ads")]), tokens=StaticToken())
    fake = FakeAccounting([])
    r = await sync_entity_accounts(ws, eid, INCREMENTAL, transport=fake, tokens=StaticToken())
    assert r.kind == INCREMENTAL
    assert fake.requests[0].headers["If-Modified-Since"] == "2023-11-14T22:13:20"  # the /Date(1700000000000)/ above


async def test_a_long_retry_after_raises_quota_exhausted_instead_of_blocking():
    ws, _, eid = await _entity()
    fake = FakeAccounting([], status=429, retry_after=3600)
    with pytest.raises(QuotaExhausted):
        await sync_entity_accounts(ws, eid, FULL, transport=fake, tokens=StaticToken())
    assert owner_scalar("select sync_status from entities where id = :e", e=eid) == "error"
    assert owner_scalar("select retry_after_until is not null from xero_quota where tenant_id = 'tenant-a'")


async def _expiring_connection():
    ws, user, eid = await _entity()
    async with unit_of_work(workspace_id=ws) as s:
        conn = (await s.scalars(XeroConnection.__table__.select())).first()
    stale = {"access_token": "old", "refresh_token": "r-1", "expires_in": 1800, "obtained_at": time.time() - 3600}
    async with unit_of_work(workspace_id=ws) as s:
        c = await s.get(XeroConnection, conn)
        c.token_encrypted = encrypt_json(stale)
    return ws, conn


async def test_concurrent_refreshes_spend_the_refresh_token_once(xero_identity):
    ws, conn = await _expiring_connection()
    identity = XeroIdentityClient(xero_identity)
    tokens = [ConnectionTokens(ws, conn, identity) for _ in range(4)]
    results = await asyncio.gather(*(t.access_token() for t in tokens))
    assert xero_identity.refresh_calls == 1
    assert len(set(results)) == 1 and results[0] != "old"


async def test_a_revoked_grant_marks_the_connection_revoked(xero_identity):
    ws, conn = await _expiring_connection()
    xero_identity.refresh_fails_with = "invalid_grant"
    with pytest.raises(ConnectionRevoked):
        await ConnectionTokens(ws, conn, XeroIdentityClient(xero_identity)).access_token()
    assert owner_scalar("select status from xero_connections where id = :c", c=conn) == "revoked"


async def test_a_crashing_sync_job_never_leaves_the_org_stuck_on_queued(monkeypatch):
    from canopy.jobs import app as jobs

    ws, _, eid = await _entity()
    async with unit_of_work(workspace_id=ws) as s:
        from canopy.xero.models import Entity

        (await s.get(Entity, eid)).sync_status = "queued"

    async def boom(*args, **kwargs):
        raise RuntimeError("worker crashed before recording the run")

    monkeypatch.setattr(jobs, "sync_entity_accounts", boom)
    with pytest.raises(RuntimeError):
        await jobs.sync_accounts.func(workspace_id=str(ws), entity_id=str(eid), tenant_id="tenant-a", kind=FULL)
    assert owner_scalar("select sync_status from entities where id = :e", e=eid) == "error"
    assert "worker crashed" in owner_scalar("select sync_error from entities where id = :e", e=eid)
