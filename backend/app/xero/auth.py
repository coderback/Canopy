"""OAuth 2.0 auth-code flow for ONE standard Xero app connected to N orgs.

Token set is stored encrypted (Fernet) in a singleton DB row and refreshed
automatically. Tenant IDs come from GET /connections and are upserted into
the entity registry — every API call downstream passes an explicit tenant id.
"""

import asyncio
import base64
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Entity, TokenRecord

AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
CONNECTIONS_URL = "https://api.xero.com/connections"

_pending_states: set[str] = set()
_refresh_lock = asyncio.Lock()


def _fernet() -> Fernet:
    key = get_settings().canopy_fernet_key
    if not key:
        raise RuntimeError("CANOPY_FERNET_KEY is not set — see .env.example")
    return Fernet(key.encode())


def build_consent_url() -> str:
    settings = get_settings()
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    params = {
        "response_type": "code",
        "client_id": settings.xero_client_id,
        "redirect_uri": settings.xero_redirect_uri,
        "scope": settings.xero_scopes,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def consume_state(state: str) -> bool:
    if state in _pending_states:
        _pending_states.discard(state)
        return True
    return False


def _basic_auth_header() -> str:
    settings = get_settings()
    raw = f"{settings.xero_client_id}:{settings.xero_client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def save_token(db: Session, token: dict) -> None:
    token = dict(token)
    token["obtained_at"] = time.time()
    blob = _fernet().encrypt(json.dumps(token).encode()).decode()
    record = db.get(TokenRecord, 1)
    if record is None:
        record = TokenRecord(id=1, token_encrypted=blob)
        db.add(record)
    else:
        record.token_encrypted = blob
    db.commit()


def load_token(db: Session) -> dict | None:
    record = db.get(TokenRecord, 1)
    if record is None:
        return None
    return json.loads(_fernet().decrypt(record.token_encrypted.encode()).decode())


async def exchange_code(db: Session, code: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            headers={"Authorization": _basic_auth_header()},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.xero_redirect_uri,
            },
        )
    resp.raise_for_status()
    token = resp.json()
    save_token(db, token)
    return token


async def refresh_token(db: Session, token: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            headers={"Authorization": _basic_auth_header()},
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
            },
        )
    resp.raise_for_status()
    new_token = resp.json()
    save_token(db, new_token)
    return new_token


def _expiring(token: dict) -> bool:
    obtained = token.get("obtained_at", 0)
    expires_in = token.get("expires_in", 1800)
    return time.time() > obtained + expires_in - 60  # refresh 60s early


async def get_valid_access_token(db: Session) -> str:
    token = load_token(db)
    if token is None:
        raise RuntimeError("No Xero token stored — connect an organisation first via /auth/xero/connect")
    if _expiring(token):
        # The fan-out calls Xero for several tenants concurrently. Xero rotates the
        # refresh token on every refresh, so only one coroutine may refresh; the
        # rest wait, then re-read the token it saved instead of spending a stale one.
        async with _refresh_lock:
            token = load_token(db) or token
            if _expiring(token):
                token = await refresh_token(db, token)
    return token["access_token"]


async def sync_connections(db: Session) -> list[Entity]:
    """GET /connections → upsert the tenant registry."""
    access_token = await get_valid_access_token(db)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            CONNECTIONS_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
    resp.raise_for_status()
    entities: list[Entity] = []
    for conn in resp.json():
        if conn.get("tenantType") != "ORGANISATION":
            continue
        tenant_id = conn["tenantId"]
        entity = db.query(Entity).filter_by(tenant_id=tenant_id).one_or_none()
        if entity is None:
            entity = Entity(tenant_id=tenant_id, name=conn.get("tenantName") or tenant_id)
            db.add(entity)
        else:
            entity.name = conn.get("tenantName") or entity.name
            entity.active = True
        entities.append(entity)
    db.commit()
    return entities
