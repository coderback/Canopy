"""Organisation connection lifecycle: disconnect, purge, and the nightly check.

Rules (Xero's certification checkpoints and commercial terms, plus our own):
- disconnecting an org tells Xero to drop that connection (DELETE /connections),
  rather than waiting for tokens to expire; it frees the slot towards the plan's
  connection limit and fees;
- once none of a grant's orgs is connected, the grant itself is revoked and its
  tokens deleted: no secrets are kept for orgs we no longer serve;
- a disconnected org's data is kept for a grace period, so an accidental
  disconnect can be undone by reconnecting, then purged. The organisation row,
  its change history and the audit log are kept;
- nightly, each grant's connection list is compared with ours: orgs that vanished
  from Xero need reconnecting, and connections we don't use (orphans, or
  non-organisation tenants) are removed, since they'd count towards the limit.
Xero calls happen outside any open transaction.
"""

import logging
import uuid
from datetime import timedelta

import httpx
from sqlalchemy import delete, func, select

from ..audit import service as audit
from ..core.db import unit_of_work
from ..core.errors import AppError, Conflict, NotFound
from ..core.models_base import utcnow
from ..core.security import decrypt_json
from ..sync.models import EntityAccount, EntityTaxRate, SyncRun
from ..tracking.models import EntityTrackingCategory, EntityTrackingOption
from .models import Entity, XeroConnection
from .oauth import XeroIdentityClient
from .status import DISCONNECTED, REMOVED_REASON, SHOWN, mark_needs_reconnect
from .tokens import ConnectionRevoked, ConnectionTokens

log = logging.getLogger(__name__)

GRACE_PERIOD = timedelta(days=30)


async def disconnect(workspace_id: uuid.UUID, entity_id: uuid.UUID, actor: uuid.UUID, *,
                     remove_now: bool = False, identity: XeroIdentityClient | None = None) -> None:
    async with unit_of_work(workspace_id=workspace_id, user_id=actor) as s:
        e = await s.get(Entity, entity_id)
        if e is None:
            raise NotFound("Organisation not found.")
        if e.status == DISCONNECTED:
            raise Conflict(f"{e.name} is already disconnected.")
        conn = await s.get(XeroConnection, e.connection_id)
        connected = conn is not None and conn.status == "active"
        ref, connection_id = e.xero_connection_ref, e.connection_id
        last_on_grant = not await s.scalar(
            select(func.count()).select_from(Entity).where(
                Entity.connection_id == connection_id, Entity.id != entity_id, Entity.status.in_(SHOWN)))

    identity = identity or XeroIdentityClient()
    if connected and ref:
        try:
            await identity.delete_connection(
                await ConnectionTokens(workspace_id, connection_id, identity).access_token(), ref)
        except ConnectionRevoked:
            pass  # the grant is already gone, and its connections with it
        except httpx.HTTPError as exc:
            raise AppError("Couldn't reach Xero to disconnect it. Nothing was changed; try again.",
                           code="xero_unavailable") from exc

    refresh_token = None
    async with unit_of_work(workspace_id=workspace_id, user_id=actor) as s:
        e = await s.get(Entity, entity_id)
        now = utcnow()
        e.status, e.status_reason, e.status_changed_at = DISCONNECTED, "Disconnected in Canopy.", now
        e.purge_after = now if remove_now else now + GRACE_PERIOD
        await audit.record(s, "xero.org_disconnected", workspace_id=workspace_id, actor_user_id=actor,
                           target_type="entity", target_id=e.id,
                           after={"org": e.name, "data_removed_after": e.purge_after.isoformat()})
        conn = await s.get(XeroConnection, connection_id)
        if last_on_grant and conn is not None and conn.token_encrypted:
            refresh_token = decrypt_json(conn.token_encrypted).get("refresh_token")
            conn.token_encrypted, conn.status = None, "revoked"
            await audit.record(s, "xero.grant_revoked", workspace_id=workspace_id, actor_user_id=actor,
                               target_type="xero_connection", target_id=conn.id,
                               after={"reason": "none of its organisations is connected any more"})
    if refresh_token:
        try:
            await identity.revoke(refresh_token)
        except httpx.HTTPError:
            # The secret is already deleted here; Xero expires an unused grant anyway.
            log.warning("revoking grant %s at Xero failed", connection_id)
    if remove_now:
        await purge(workspace_id, entity_id, actor)


async def purge(workspace_id: uuid.UUID, entity_id: uuid.UUID, actor: uuid.UUID | None = None) -> None:
    """Delete a disconnected org's mirrored Xero data and its mappings. Keeps the
    organisation row, its change history and the audit log."""
    async with unit_of_work(workspace_id=workspace_id, user_id=actor) as s:
        e = await s.get(Entity, entity_id)
        if e is None:
            raise NotFound("Organisation not found.")
        if e.status != DISCONNECTED:
            raise Conflict("Only a disconnected organisation's data can be removed.")
        if e.purged_at is not None:
            return
        # Mappings go with the mirror rows they hang off (ON DELETE CASCADE).
        for model in (EntityTrackingOption, EntityTrackingCategory, EntityAccount, EntityTaxRate, SyncRun):
            await s.execute(delete(model).where(model.entity_id == entity_id))
        e.purged_at = utcnow()
        await audit.record(s, "xero.org_data_removed", workspace_id=workspace_id, actor_user_id=actor,
                           target_type="entity", target_id=e.id, after={"org": e.name})


async def check_grant(workspace_id: uuid.UUID, connection_id: uuid.UUID,
                      identity: XeroIdentityClient | None = None) -> None:
    """Compare what this grant reaches in Xero with what Canopy uses."""
    identity = identity or XeroIdentityClient()
    try:
        token = await ConnectionTokens(workspace_id, connection_id, identity).access_token()
    except ConnectionRevoked:
        return  # its organisations were flagged when the refresh was refused
    listed = await identity.list_connections(token)
    async with unit_of_work(workspace_id=workspace_id) as s:
        shown = list(await s.scalars(select(Entity).where(Entity.status.in_(SHOWN))))
        reached = {c.get("tenantId") for c in listed}
        await mark_needs_reconnect(
            s, [e for e in shown if e.connection_id == connection_id and e.tenant_id not in reached], REMOVED_REASON)
        in_use = {e.tenant_id for e in shown}
    orphans = [c for c in listed if c.get("tenantType") != "ORGANISATION" or c.get("tenantId") not in in_use]
    for c in orphans:
        await identity.delete_connection(token, c["id"])
    if orphans:
        async with unit_of_work(workspace_id=workspace_id) as s:
            await audit.record(s, "xero.unused_connections_removed", workspace_id=workspace_id, actor_user_id=None,
                               target_type="xero_connection", target_id=connection_id,
                               after={"tenants": [c.get("tenantName") or c.get("tenantId") for c in orphans]})
