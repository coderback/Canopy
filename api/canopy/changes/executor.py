"""Executes ONE approved change item against Xero.

Order matters, and every step is a gate:
1. the item and its set must still be runnable (approved/executing, not already done);
2. the workspace must still have changes on, and the global kill switch must allow writes;
3. the org's mirror is refreshed (incremental sync, incl. tax rates and tracking);
4. for edits/archives the live object is read from Xero -> `before`;
5. preflight runs again against that fresh data -> any problem fails the item
   WITHOUT writing;
6. the write carries the item's Idempotency-Key (stable across automatic retries,
   and replayed as-is if an earlier run died mid-write);
7. the mirror, the mapping (a created account is confirmed against its group
   account, closing the gap) and the audit log are updated, and the set's status is
   rolled up under a row lock so parallel items across tenants can't race.
The Xero calls happen outside any open transaction. Tracking items share steps
1-2 here and run the rest in tracking_executor.py.
"""

import uuid

import httpx
from sqlalchemy.dialects.postgresql import insert

from ..core.config import get_settings
from ..core.db import unit_of_work
from ..core.models_base import utcnow
from ..mapping.models import AccountMapping
from ..sync.models import EntityAccount
from ..sync.service import INCREMENTAL, sync_entity_accounts, upsert_account
from ..tenancy.models import Workspace
from ..tracking import preflight as tp
from ..xero.client import QuotaExhausted, XeroApiError, XeroClient
from ..xero.models import Entity
from ..xero.tokens import ConnectionTokens
from . import preflight as pf
from .models import ChangeItem, ChangeSet
from .outcome import finish as _finish
from .outcome import reset as _reset
from .service import org_state

RUNNABLE_SETS = ("approved", "executing")


def _live(account: dict) -> pf.OrgAccount:
    return pf.OrgAccount(
        account["AccountID"], account.get("Code"), account.get("Name") or "", account.get("Type") or "",
        account.get("Class"), account.get("Status") or "ACTIVE", account.get("SystemAccount"),
        account.get("TaxType"), account.get("Description"),
    )


async def execute_item(
    workspace_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    tokens=None,
) -> str:
    """Returns the item's final status. Raises QuotaExhausted (item reset to pending)
    so the job can be rescheduled."""
    async with unit_of_work(workspace_id=workspace_id) as s:
        item = await s.get(ChangeItem, item_id)
        if item is None or item.status in ("succeeded", "skipped"):
            return item.status if item else "missing"
        cs = await s.get(ChangeSet, item.change_set_id)
        if cs.status not in RUNNABLE_SETS:
            item.status = "skipped"
            return "skipped"
        entity = await s.get(Entity, item.entity_id)
        workspace = await s.get(Workspace, workspace_id)
        target = await s.get(EntityAccount, item.entity_account_id) if item.entity_account_id else None
        # Picked up while still 'running' = an earlier run died mid-flight, possibly
        # after Xero applied the write. Replay with the same Idempotency-Key (Xero
        # returns its cached result) instead of re-validating against our own write.
        replay = item.status == "running"
        cs.status, item.status = "executing", "running"
        op, payload, key, group_id = item.operation, dict(item.payload), item.idempotency_key, item.group_account_id
        tenant_id, connection_id, actor = entity.tenant_id, entity.connection_id, cs.decided_by
        target_xero_id = target.xero_account_id if target else None
        changes_on = workspace.changes_enabled

    # The owner can switch changes off at any time, including after an approval:
    # nothing already queued may write once they have.
    if not changes_on:
        await _finish(workspace_id, item_id, status="failed", actor=actor,
                      error="Changes to Xero were switched off for this workspace before this ran.")
        return "failed"
    if not get_settings().writes_enabled:
        await _finish(workspace_id, item_id, status="failed", actor=actor,
                      error="Writes to Xero are switched off on this server (XERO_WRITES_ENABLED).")
        return "failed"

    tokens = tokens or ConnectionTokens(workspace_id, connection_id)
    if op in tp.OPERATIONS:
        from .tracking_executor import execute_tracking

        return await execute_tracking(workspace_id, item_id, transport=transport, tokens=tokens, actor=actor,
                                      replay=replay)

    client = XeroClient(tokens.access_token, transport)
    try:
        # Fresh mirror first, so the second preflight sees what Xero sees now.
        await sync_entity_accounts(workspace_id, item.entity_id, INCREMENTAL, transport=transport, tokens=tokens)
        before = await client.get_account(tenant_id, target_xero_id) if target_xero_id else None
    except QuotaExhausted:
        await _reset(workspace_id, item_id)
        raise
    except Exception as exc:  # noqa: BLE001 — recorded on the item, never silent
        await _finish(workspace_id, item_id, status="failed", actor=actor,
                      error=f"Couldn't read the organisation before writing: {exc}")
        return "failed"

    async with unit_of_work(workspace_id=workspace_id) as s:
        entity = await s.get(Entity, item.entity_id)
        problems = pf.check(op, payload, _live(before) if before else None, await org_state(s, entity))
    if problems and not replay:
        await _finish(workspace_id, item_id, status="failed", before=before, actor=actor,
                      error="Not written — " + " ".join(problems))
        return "failed"

    fields = pf.xero_fields(op, payload)
    try:
        if op == pf.CREATE:
            after = await client.create_account(tenant_id, fields, key)
        elif op == pf.UPDATE:
            after = await client.update_account(tenant_id, target_xero_id, fields, key)
        else:
            after = await client.archive_account(tenant_id, target_xero_id, key)
    except QuotaExhausted:
        await _reset(workspace_id, item_id)
        raise
    except XeroApiError as exc:
        reason = "; ".join(exc.messages) if exc.messages else str(exc)
        await _finish(workspace_id, item_id, status="failed", before=before, actor=actor,
                      error=f"Xero rejected the change: {reason}")
        return "failed"

    async with unit_of_work(workspace_id=workspace_id) as s:
        local_id = await upsert_account(s, workspace_id, item.entity_id, after)
        if op == pf.CREATE and group_id:
            # The new account IS the group account in this org: confirm it, closing the gap.
            now = utcnow()
            values = {"workspace_id": workspace_id, "entity_id": item.entity_id, "entity_account_id": local_id,
                      "group_account_id": group_id, "status": "confirmed", "source": "created",
                      "confidence": 1.0, "reasoning": "Created in Xero by an approved Canopy change.",
                      "decided_by": actor, "decided_at": now, "updated_at": now}
            stmt = insert(AccountMapping).values(**values)
            await s.execute(stmt.on_conflict_do_update(
                index_elements=[AccountMapping.entity_account_id],
                set_={
                    k: stmt.excluded[k] for k in values
                    if k not in ("workspace_id", "entity_id", "entity_account_id")
                },
            ))
    await _finish(workspace_id, item_id, status="succeeded", before=before, after=after,
                  xero_account_id=after.get("AccountID"), actor=actor)
    return "succeeded"
