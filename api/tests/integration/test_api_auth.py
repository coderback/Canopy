"""Sign Up with Xero, sessions, CSRF, workspace access and roles, over HTTP."""

from urllib.parse import parse_qs, urlparse

from canopy.core.db import unit_of_work
from canopy.tenancy.models import Membership, Role

from .helpers import client_for, owner_scalar, sign_in


async def test_login_creates_user_session_and_audits(xero_identity):
    async with client_for(xero_identity) as c:
        me = await sign_in(c, xero_identity)
    assert me["user"]["email"] == "owner@example.com" and me["workspaces"] == []
    # Only a hash of the session token is stored.
    token_hash = owner_scalar("select token_hash from sessions")
    assert len(token_hash) == 64
    assert owner_scalar("select count(*) from audit_events where action = 'auth.login'") == 1


async def test_login_requests_identity_scopes_only_and_uses_pkce(xero_identity):
    async with client_for(xero_identity) as c:
        start = await c.get("/auth/login")
    q = parse_qs(urlparse(start.headers["location"]).query)
    assert q["scope"] == ["openid profile email"]
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"][0]


async def test_state_is_single_use(xero_identity):
    async with client_for(xero_identity) as c:
        start = await c.get("/auth/login")
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        xero_identity.nonce = owner_scalar("select nonce from oauth_states where state = :s", s=state)
        assert (await c.get("/auth/xero/callback", params={"code": "c", "state": state})).status_code == 303
        replay = await c.get("/auth/xero/callback", params={"code": "c", "state": state})
    assert replay.status_code == 400 and replay.json()["error"]["code"] == "oauth_state_invalid"


async def test_open_redirects_are_refused(xero_identity):
    async with client_for(xero_identity) as c:
        start = await c.get("/auth/login", params={"redirect_to": "//evil.example/steal"})
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    assert owner_scalar("select redirect_to from oauth_states where state = :s", s=state) == "/"


async def test_unauthenticated_requests_get_401():
    async with client_for() as c:
        r = await c.get("/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


async def test_mutations_require_the_csrf_token(xero_identity):
    async with client_for(xero_identity) as c:
        await sign_in(c, xero_identity)
        csrf = c.headers.pop("X-CSRF-Token")
        blocked = await c.post("/workspaces", json={"name": "Group"})
        c.headers["X-CSRF-Token"] = csrf
        allowed = await c.post("/workspaces", json={"name": "Group"})
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "csrf_failed"
    assert allowed.status_code == 201


async def test_non_members_get_404_not_403(xero_identity):
    async with client_for(xero_identity) as c:
        await sign_in(c, xero_identity)
        ws = (await c.post("/workspaces", json={"name": "Mine"})).json()["id"]
    xero_identity.person = ("xero-user-2", "stranger@example.com")
    async with client_for(xero_identity) as c2:
        await sign_in(c2, xero_identity)
        r = await c2.get(f"/workspaces/{ws}/entities")
    assert r.status_code == 404


async def test_viewers_can_read_but_not_administer(xero_identity):
    async with client_for(xero_identity) as c:
        me = await sign_in(c, xero_identity)
        ws = (await c.post("/workspaces", json={"name": "G"})).json()["id"]
        async with unit_of_work(workspace_id=ws, user_id=me["user"]["id"]) as s:
            m = (await s.scalars(Membership.__table__.select().where(Membership.workspace_id == ws))).first()
            await s.execute(Membership.__table__.update().where(Membership.id == m).values(role=Role.VIEWER))
        assert (await c.get(f"/workspaces/{ws}/standard")).status_code == 200
        denied = await c.post(f"/workspaces/{ws}/standard/accounts", json={"code": "1", "name": "x", "type": "EXPENSE"})
    assert denied.status_code == 403


async def test_invitation_only_works_for_the_invited_email(xero_identity):
    async with client_for(xero_identity) as owner:
        await sign_in(owner, xero_identity)
        ws = (await owner.post("/workspaces", json={"name": "G"})).json()["id"]
        invite = await owner.post(f"/workspaces/{ws}/invitations", json={"email": "Accountant@Firm.com", "role": "admin"})
        token = invite.json()["token"]

    xero_identity.person = ("xero-user-3", "someone.else@firm.com")
    async with client_for(xero_identity) as wrong:
        await sign_in(wrong, xero_identity)
        assert (await wrong.post("/invitations/accept", json={"token": token})).status_code == 404

    xero_identity.person = ("xero-user-4", "accountant@firm.com")
    async with client_for(xero_identity) as right:
        await sign_in(right, xero_identity)
        ok = await right.post("/invitations/accept", json={"token": token})
        assert ok.status_code == 200 and ok.json()["workspace_id"] == ws
        me = (await right.get("/me")).json()
    assert me["workspaces"] == [{"id": ws, "name": "G", "role": "admin"}]
    assert owner_scalar("select count(*) from audit_events where action = 'member.joined'") == 1
