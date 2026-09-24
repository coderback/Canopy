"""Shared setup for integration tests: users, workspaces, entities, sign-in."""

import uuid
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import create_engine, text

from canopy.api.routes_auth import get_identity_client
from canopy.app import create_app
from canopy.auth import service as auth
from canopy.core.config import get_settings
from canopy.core.db import unit_of_work
from canopy.core.security import encrypt_json
from canopy.xero.models import Entity, XeroConnection
from canopy.xero.oauth import XeroIdentityClient
from canopy.xero.tokens import token_record


async def make_user(xero_id: str = "xero-user-1", email: str = "owner@example.com") -> uuid.UUID:
    async with unit_of_work() as s:
        return await s.scalar(text("select canopy_upsert_user(:x, :e, 'Test')"), {"x": xero_id, "e": email})


async def make_entity(ws: uuid.UUID, user: uuid.UUID, tenant_id: str, name: str, token: dict | None = None) -> uuid.UUID:
    async with unit_of_work(workspace_id=ws, user_id=user) as s:
        conn = XeroConnection(
            workspace_id=ws, xero_user_id=f"xu-{tenant_id}", connected_by=user, scopes="accounting.settings.read",
            token_encrypted=encrypt_json(token or token_record({"access_token": "a", "refresh_token": "r", "expires_in": 1800})),
        )
        s.add(conn)
        await s.flush()
        e = Entity(workspace_id=ws, connection_id=conn.id, tenant_id=tenant_id, name=name)
        s.add(e)
        await s.flush()
        return e.id


def owner_scalar(sql: str, **params):
    """Read as the schema owner (bypasses RLS) to inspect what's really stored."""
    engine = create_engine(get_settings().migrations_database_url)
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql), params).scalar()
    finally:
        engine.dispose()


def client_for(identity_transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    app = create_app(with_jobs=False)
    if identity_transport is not None:
        app.dependency_overrides[get_identity_client] = lambda: XeroIdentityClient(identity_transport)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api.test")


async def sign_in(client: httpx.AsyncClient, fake) -> dict:
    """Drive the real login flow against the fake Xero; returns /me."""
    start = await client.get("/auth/login", params={"redirect_to": "/dashboard"})
    assert start.status_code == 303
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    fake.nonce = owner_scalar("select nonce from oauth_states where state = :s", s=state)
    cb = await client.get("/auth/xero/callback", params={"code": "c", "state": state})
    assert cb.status_code == 303, cb.text
    assert cb.headers["location"] == "http://web.test/dashboard"
    me = await client.get("/me")
    assert me.status_code == 200, me.text
    client.headers["X-CSRF-Token"] = me.json()["csrf_token"]
    return me.json()


async def connect_orgs(client: httpx.AsyncClient, fake, workspace_id: str) -> None:
    start = await client.get(f"/workspaces/{workspace_id}/xero/connect")
    assert start.status_code == 303, start.text
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    fake.nonce = owner_scalar("select nonce from oauth_states where state = :s", s=state)
    cb = await client.get("/auth/xero/callback", params={"code": "c", "state": state})
    assert cb.status_code == 303, cb.text


__all__ = ["auth", "make_user", "make_entity", "owner_scalar", "client_for", "sign_in", "connect_orgs"]
