"""Fixtures for tests that need Postgres (docker compose up -d db)."""

import time
import uuid

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from procrastinate.testing import InMemoryConnector
from sqlalchemy import create_engine, text

from canopy.core.config import get_settings
from canopy.xero import oauth

API_DIR = __file__.rsplit("tests", 1)[0]


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Fresh schema per test session, built by the real migration."""
    cfg = Config(f"{API_DIR}alembic.ini")
    cfg.set_main_option("script_location", f"{API_DIR}migrations")
    cfg.set_main_option("sqlalchemy.url", get_settings().migrations_database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean(schema):
    """Wipe data (as the owner, which bypasses RLS) before each test."""
    engine = create_engine(get_settings().migrations_database_url)
    with engine.begin() as conn:
        tables = conn.execute(text(
            "select string_agg(format('%I', tablename), ', ') from pg_tables "
            "where schemaname = 'public' and tablename <> 'alembic_version'"
        )).scalar()
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    engine.dispose()
    yield


@pytest.fixture(autouse=True)
def jobs_in_memory():
    """Deferred jobs land in memory; tests assert on them without a worker."""
    from canopy.jobs.app import app

    connector = InMemoryConnector()
    with app.replace_connector(connector):
        yield connector


# ---- a fake Xero identity service --------------------------------------------

SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def id_token(xero_user_id: str, email: str, nonce: str, name: str = "Test User", skew: int = 0) -> str:
    now = int(time.time()) + skew  # skew: how far Xero's clock runs ahead of ours
    return jwt.encode(
        {"iss": oauth.ISSUER, "aud": get_settings().xero_client_id, "iat": now, "exp": now + 300,
         "nonce": nonce, "xero_userid": xero_user_id, "email": email, "name": name},
        SIGNING_KEY, algorithm="RS256",
    )


def access_token(auth_event_id: str = "evt-1") -> str:
    return jwt.encode({"authentication_event_id": auth_event_id, "exp": int(time.time()) + 1800},
                      "test-only-hmac-key-not-a-secret-000000", algorithm="HS256")


class FakeXeroIdentity(httpx.AsyncBaseTransport):
    """Token + connections endpoints. `person` decides who signs in; the
    nonce is read back from the pending state so the id_token validates."""

    def __init__(self):
        self.person = ("xero-user-1", "owner@example.com")
        self.tenants = [{"id": "conn-1", "tenantId": "tenant-a", "tenantName": "Org A", "tenantType": "ORGANISATION"}]
        self.refresh_calls = 0
        self.refresh_fails_with: str | None = None
        self.nonce = ""
        self.clock_skew = 0  # seconds Xero's clock is ahead of ours

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == oauth.TOKEN_URL:
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if form["grant_type"] == "refresh_token":
                self.refresh_calls += 1
                if self.refresh_fails_with:
                    return httpx.Response(400, json={"error": self.refresh_fails_with})
                return httpx.Response(200, json={"access_token": access_token(), "refresh_token": f"r-{self.refresh_calls + 1}",
                                                 "expires_in": 1800, "scope": "accounting.settings.read"})
            xero_id, email = self.person
            return httpx.Response(200, json={
                "access_token": access_token(), "refresh_token": "r-1", "expires_in": 1800,
                "id_token": id_token(xero_id, email, self.nonce, skew=self.clock_skew),
                "scope": "openid profile email offline_access accounting.settings.read",
            })
        if url.startswith(oauth.CONNECTIONS_URL):
            return httpx.Response(200, json=self.tenants)
        return httpx.Response(404)


@pytest.fixture
def xero_identity(monkeypatch):
    fake = FakeXeroIdentity()

    class _Key:
        key = SIGNING_KEY.public_key()

    class _Jwks:
        def get_signing_key_from_jwt(self, token):
            return _Key()

    monkeypatch.setattr(oauth, "_jwks_client", lambda: _Jwks())
    return fake


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
