"""Organisation connections: disconnect, the 30-day grace period, purge, reconnect,
lost access, and the nightly connection check. Xero's identity service is the
fake from conftest, which records connection deletes and token revocations."""

import time
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from canopy.core.db import unit_of_work
from canopy.core.models_base import utcnow
from canopy.core.security import encrypt_json
from canopy.jobs.app import nightly_connection_check
from canopy.sync.service import FULL, sync_entity_accounts
from canopy.tenancy.models import Role
from canopy.xero import connections
from canopy.xero.models import XeroConnection
from canopy.xero.oauth import XeroIdentityClient
from canopy.xero.tokens import ConnectionRevoked, ConnectionTokens

from .helpers import client_for, connect_orgs, owner_scalar, sign_in
from .test_changes import _other_approver
from .test_connect_and_sync import FakeAccounting, StaticToken, account

ORG_B = {"id": "conn-2", "tenantId": "tenant-b", "tenantName": "Org B", "tenantType": "ORGANISATION"}


async def _group(c, xero_identity):
    """Org A and Org B connected through one Xero sign-in (one grant), both synced."""
    xero_identity.tenants.append(dict(ORG_B))
    await sign_in(c, xero_identity)
    ws = (await c.post("/workspaces", json={"name": "G"})).json()["id"]
    await connect_orgs(c, xero_identity, ws)
    orgs = {e["name"]: e["id"] for e in (await c.get(f"/workspaces/{ws}/entities")).json()}
    for eid in orgs.values():
        await sync_entity_accounts(ws, eid, FULL, transport=FakeAccounting([account("x1", "200", "Sales")]),
                                   tokens=StaticToken())
    return ws, orgs["Org A"], orgs["Org B"]


def _status(eid):
    return owner_scalar("select status from entities where id = :e", e=eid)


def _accounts(eid):
    return owner_scalar("select count(*) from entity_accounts where entity_id = :e", e=eid)


async def test_disconnecting_drops_the_xero_connection_and_keeps_data_for_30_days(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, b = await _group(c, xero_identity)
        r = await c.post(f"/workspaces/{ws}/entities/{a}/disconnect", json={})
        gaps = (await c.get(f"/workspaces/{ws}/gaps")).json()
    out = r.json()
    assert r.status_code == 200 and out["status"] == "disconnected"
    assert xero_identity.deleted == ["conn-1"] and xero_identity.revoked == []  # Org B still uses the grant
    days = (owner_scalar("select purge_after from entities where id = :e", e=a) - utcnow()) / timedelta(days=1)
    assert 29.9 < days <= 30 and out["purge_after"] and out["purged_at"] is None
    assert _accounts(a) == 1  # kept, so reconnecting within 30 days restores it
    assert [e["name"] for e in gaps["entities"]] == ["Org B"]
    assert owner_scalar("select count(*) from audit_events where action = 'xero.org_disconnected'") == 1


async def test_disconnecting_the_last_org_revokes_the_grant_and_deletes_its_tokens(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, b = await _group(c, xero_identity)
        await c.post(f"/workspaces/{ws}/entities/{a}/disconnect", json={})
        await c.post(f"/workspaces/{ws}/entities/{b}/disconnect", json={})
    assert xero_identity.revoked == ["r-1"]
    assert owner_scalar("select status from xero_connections") == "revoked"
    assert owner_scalar("select token_encrypted is null from xero_connections") is True
    assert owner_scalar("select count(*) from audit_events where action = 'xero.grant_revoked'") == 1


async def test_remove_now_purges_the_data_but_keeps_the_org_and_its_history(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, _ = await _group(c, xero_identity)
        r = await c.post(f"/workspaces/{ws}/entities/{a}/disconnect", json={"remove_now": True})
    assert r.json()["purged_at"] and _accounts(a) == 0
    assert owner_scalar("select count(*) from entities where id = :e", e=a) == 1
    assert owner_scalar("select count(*) from audit_events where action = 'xero.org_data_removed'") == 1


async def test_reconnecting_restores_the_org_and_cancels_the_purge(xero_identity, jobs_in_memory):
    async with client_for(xero_identity) as c:
        ws, a, _ = await _group(c, xero_identity)
        await c.post(f"/workspaces/{ws}/entities/{a}/disconnect", json={})
        xero_identity.tenants.append({"id": "conn-1b", "tenantId": "tenant-a", "tenantName": "Org A",
                                      "tenantType": "ORGANISATION"})
        await connect_orgs(c, xero_identity, ws)
        org = next(e for e in (await c.get(f"/workspaces/{ws}/entities")).json() if e["id"] == a)
    assert org["status"] == "active" and org["purge_after"] is None and org["status_reason"] is None
    assert _accounts(a) == 1
    assert any(j["args"].get("entity_id") == a for j in jobs_in_memory.jobs.values()
               if j["task_name"] == "sync_accounts")


async def test_the_nightly_job_removes_data_only_once_the_grace_period_is_over(xero_identity, monkeypatch):
    monkeypatch.setattr(connections, "XeroIdentityClient", lambda: XeroIdentityClient(xero_identity))
    async with client_for(xero_identity) as c:
        ws, a, b = await _group(c, xero_identity)
        await c.post(f"/workspaces/{ws}/entities/{a}/disconnect", json={})
        await c.post(f"/workspaces/{ws}/entities/{b}/disconnect", json={})
    async with unit_of_work(workspace_id=ws) as s:
        from canopy.xero.models import Entity
        (await s.get(Entity, a)).purge_after = utcnow() - timedelta(minutes=1)
    await nightly_connection_check(0)
    assert _accounts(a) == 0 and _accounts(b) == 1


async def test_a_refused_refresh_flags_every_org_on_the_grant_and_blocks_new_changes(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, b = await _group(c, xero_identity)
        async with unit_of_work(workspace_id=ws) as s:
            conn = (await s.scalars(XeroConnection.__table__.select())).first()
            row = await s.get(XeroConnection, conn)
            row.token_encrypted = encrypt_json({"access_token": "old", "refresh_token": "r-1", "expires_in": 1800,
                                                "obtained_at": time.time() - 3600})
        xero_identity.refresh_fails_with = "invalid_grant"
        try:
            await ConnectionTokens(ws, conn, XeroIdentityClient(xero_identity)).access_token()
        except ConnectionRevoked:
            pass
        orgs = {e["name"]: e for e in (await c.get(f"/workspaces/{ws}/entities")).json()}
        await c.patch(f"/workspaces/{ws}/settings", json={"changes_enabled": True})
        cs = (await c.post(f"/workspaces/{ws}/changes", json={"title": "x", "items": [
            {"operation": "create_account", "entity_id": a,
             "payload": {"code": "999", "name": "Test", "type": "EXPENSE"}}]})).json()
        gaps = (await c.get(f"/workspaces/{ws}/gaps")).json()
    assert {o["status"] for o in orgs.values()} == {"needs_reconnect"}
    assert "expired or was revoked" in orgs["Org A"]["status_reason"] and orgs["Org A"]["can_write"] is False
    assert cs["items"][0]["preflight_messages"] == ["Org A needs reconnecting before changes can be made to it."]
    # Still in the group view, flagged, so the picture isn't silently incomplete.
    assert {e["status"] for e in gaps["entities"]} == {"needs_reconnect"}


async def test_xero_refusing_one_org_flags_only_that_org(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, b = await _group(c, xero_identity)
    try:
        await sync_entity_accounts(ws, a, FULL, transport=FakeAccounting([], status=403), tokens=StaticToken())
    except Exception:  # noqa: BLE001 — the sync fails; what matters is how the org is flagged
        pass
    assert _status(a) == "needs_reconnect" and _status(b) == "active"
    assert "refused access" in owner_scalar("select status_reason from entities where id = :e", e=a)


async def test_the_nightly_check_flags_orgs_removed_in_xero_and_removes_unused_connections(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, b = await _group(c, xero_identity)
    conn = owner_scalar("select id from xero_connections")
    xero_identity.tenants = [t for t in xero_identity.tenants if t["tenantId"] != "tenant-b"] + [
        {"id": "conn-9", "tenantId": "tenant-old", "tenantName": "Sold Ltd", "tenantType": "ORGANISATION"},
        {"id": "conn-p", "tenantId": "practice-1", "tenantName": "A Practice", "tenantType": "PRACTICE"},
    ]
    await connections.check_grant(ws, conn, XeroIdentityClient(xero_identity))
    assert _status(a) == "active" and _status(b) == "needs_reconnect"
    assert "removed in Xero" in owner_scalar("select status_reason from entities where id = :e", e=b)
    assert sorted(xero_identity.deleted) == ["conn-9", "conn-p"]


async def test_connecting_drops_tenants_that_are_not_organisations(xero_identity):
    xero_identity.tenants.append({"id": "conn-p", "tenantId": "practice-1", "tenantName": "A Practice",
                                  "tenantType": "PRACTICE"})
    async with client_for(xero_identity) as c:
        await sign_in(c, xero_identity)
        ws = (await c.post("/workspaces", json={"name": "G"})).json()["id"]
        await connect_orgs(c, xero_identity, ws)
        names = [e["name"] for e in (await c.get(f"/workspaces/{ws}/entities")).json()]
    assert names == ["Org A"] and xero_identity.deleted == ["conn-p"]


async def test_a_failed_disconnect_at_xero_changes_nothing(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, _ = await _group(c, xero_identity)
        xero_identity.delete_fails = True
        r = await c.post(f"/workspaces/{ws}/entities/{a}/disconnect", json={})
    assert r.status_code >= 400 and r.json()["error"]["code"] == "xero_unavailable"
    assert _status(a) == "active"


async def test_only_admins_disconnect(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, _ = await _group(c, xero_identity)
    approver = await _other_approver(xero_identity, ws, Role.APPROVER)
    try:
        r = await approver.post(f"/workspaces/{ws}/entities/{a}/disconnect", json={})
    finally:
        await approver.__aexit__(None, None, None)
    assert r.status_code == 403 and _status(a) == "active"


async def test_reconnecting_keeps_write_access_once_changes_are_on(xero_identity):
    def scopes(location):
        return set(parse_qs(urlparse(location).query)["scope"][0].split())

    async with client_for(xero_identity) as c:
        ws, *_ = await _group(c, xero_identity)
        before = scopes((await c.get(f"/workspaces/{ws}/xero/connect")).headers["location"])
        await c.patch(f"/workspaces/{ws}/settings", json={"changes_enabled": True})
        after = scopes((await c.get(f"/workspaces/{ws}/xero/connect")).headers["location"])
    assert "accounting.settings.read" in before and "accounting.settings" not in before
    assert "accounting.settings" in after  # a reconnect never downgrades a write grant
