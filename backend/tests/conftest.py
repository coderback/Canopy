import os
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault(
    "CANOPY_FERNET_KEY", "zH8leVeMk9wZ0S0R4CfQxDdD5c-p0PUKPU0hbEcxrl0="
)  # test-only key
os.environ.setdefault("XERO_CLIENT_ID", "test-client-id")
os.environ.setdefault("XERO_CLIENT_SECRET", "test-client-secret")

import httpx
import pytest

from app.db import Base, SessionLocal, engine
from app.models import Entity
from app.xero import auth as xero_auth


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def token(db):
    xero_auth.save_token(
        db,
        {
            "access_token": "fake-access",
            "refresh_token": "fake-refresh",
            "expires_in": 1800,
            "obtained_at": time.time(),
        },
    )


@pytest.fixture()
def entity(db):
    e = Entity(tenant_id="tenant-a", name="Org A")
    db.add(e)
    db.commit()
    return e


class FakeXeroTransport(httpx.AsyncBaseTransport):
    """Programmable fake for api.xero.com — records every request."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.handlers: list[tuple[str, str, object]] = []  # (method, path-suffix, response)
        self.fail_next: list[int] = []  # status codes to emit before succeeding

    def on(self, method: str, path_suffix: str, response: dict, status: int = 200):
        self.handlers.append((method.upper(), path_suffix, (status, response)))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_next:
            status = self.fail_next.pop(0)
            return httpx.Response(status, json={"error": "injected"}, headers={"Retry-After": "0"})
        for method, suffix, (status, body) in self.handlers:
            if request.method == method and request.url.path.endswith(suffix):
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": f"no handler for {request.method} {request.url.path}"})


@pytest.fixture()
def fake_transport():
    return FakeXeroTransport()
