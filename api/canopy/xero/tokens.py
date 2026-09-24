"""Access tokens for a workspace's Xero connection, refreshed safely.

Xero rotates the refresh token on every refresh, so two processes refreshing
the same connection at once would leave one holding a dead token. The refresh
runs under a transaction-scoped Postgres advisory lock keyed on the connection:
whoever gets the lock second re-reads the row and finds a fresh token instead
of spending the stale refresh token. Works across API and worker processes,
unlike an in-process asyncio.Lock.
"""

import time
import uuid

from sqlalchemy import text

from ..core.db import unit_of_work
from ..core.models_base import utcnow
from ..core.security import decrypt_json, encrypt_json
from .models import XeroConnection
from .oauth import XeroAuthError, XeroIdentityClient

REFRESH_MARGIN_SECONDS = 120


class ConnectionRevoked(Exception):
    """The connection needs the user to reconnect (grant revoked or expired)."""


def token_record(token: dict) -> dict:
    """What we persist: the token set plus when it was obtained."""
    return {**token, "obtained_at": time.time()}


def _expiring(token: dict) -> bool:
    return time.time() > token.get("obtained_at", 0) + token.get("expires_in", 1800) - REFRESH_MARGIN_SECONDS


class ConnectionTokens:
    """Access-token provider for one connection. Every read and write opens its
    own short transaction bound to the connection's workspace (RLS)."""

    def __init__(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        identity: XeroIdentityClient | None = None,
    ):
        self.workspace_id = workspace_id
        self.connection_id = connection_id
        self.identity = identity or XeroIdentityClient()

    async def access_token(self) -> str:
        async with unit_of_work(workspace_id=self.workspace_id) as s:
            conn = await s.get(XeroConnection, self.connection_id)
            if conn is None or conn.status != "active":
                raise ConnectionRevoked("Xero connection is not active; reconnect required.")
            token = decrypt_json(conn.token_encrypted)
        if not _expiring(token):
            return token["access_token"]
        return await self._refresh()

    async def _refresh(self) -> str:
        revoked: XeroAuthError | None = None
        async with unit_of_work(workspace_id=self.workspace_id) as s:
            await s.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                {"k": f"xero-connection:{self.connection_id}"},
            )
            conn = await s.get(XeroConnection, self.connection_id, populate_existing=True)
            if conn is None or conn.status != "active":
                raise ConnectionRevoked("Xero connection is not active; reconnect required.")
            token = decrypt_json(conn.token_encrypted)
            if not _expiring(token):  # another process refreshed while we waited
                return token["access_token"]
            try:
                fresh = token_record(await self.identity.refresh(token["refresh_token"]))
            except XeroAuthError as exc:
                if not exc.revoked:
                    raise
                # Persist the revoked status (the block commits on normal exit), then raise.
                conn.status = "revoked"
                revoked = exc
            else:
                conn.token_encrypted = encrypt_json(fresh)
                conn.last_refreshed_at = utcnow()
                return fresh["access_token"]
        raise ConnectionRevoked(str(revoked)) from revoked
