"""Mirror an org's chart of accounts into `entity_accounts`.

- incremental: `If-Modified-Since` = the newest UpdatedDateUTC we've seen
  (Xero's own clock, so no skew). Cheap; runs whenever we need fresh data.
- full: fetch everything and mark accounts we no longer see as deleted, which
  If-Modified-Since can never report. Runs on connect and nightly.
The Xero call happens outside any open transaction; the DB work is two short
transactions (mark running, then write results), all under the workspace's RLS.
"""

import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from ..core.db import unit_of_work
from ..core.models_base import utcnow
from ..xero.client import XeroClient, parse_xero_date
from ..xero.models import Entity
from ..xero.tokens import ConnectionTokens
from .models import EntityAccount, SyncRun

FULL, INCREMENTAL = "full", "incremental"


@dataclass(frozen=True)
class SyncResult:
    entity_id: uuid.UUID
    kind: str
    records_seen: int
    deleted: int


def _row(workspace_id: uuid.UUID, entity_id: uuid.UUID, a: dict) -> dict:
    return {
        "workspace_id": workspace_id,
        "entity_id": entity_id,
        "xero_account_id": a["AccountID"],
        "code": a.get("Code") or None,
        "name": a.get("Name") or "",
        "type": a.get("Type") or "",
        "account_class": a.get("Class") or None,
        "tax_type": a.get("TaxType") or None,
        "status": a.get("Status") or "ACTIVE",
        "system_account": a.get("SystemAccount") or None,
        "reporting_code": a.get("ReportingCode") or None,
        "description": a.get("Description") or None,
        "xero_updated_at": parse_xero_date(a.get("UpdatedDateUTC")),
        "deleted_at": None,
        "synced_at": utcnow(),
    }


async def sync_entity_accounts(
    workspace_id: uuid.UUID,
    entity_id: uuid.UUID,
    kind: str = INCREMENTAL,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    tokens: ConnectionTokens | None = None,
) -> SyncResult:
    async with unit_of_work(workspace_id=workspace_id) as s:
        entity = await s.get(Entity, entity_id)
        if entity is None or entity.status != "active":
            raise LookupError(f"entity {entity_id} is not an active entity in this workspace")
        tenant_id, connection_id = entity.tenant_id, entity.connection_id
        since = entity.accounts_modified_since if kind == INCREMENTAL else None
        if kind == INCREMENTAL and since is None:
            kind = FULL  # nothing to be incremental against yet
        run = SyncRun(workspace_id=workspace_id, entity_id=entity_id, kind=kind, status="running")
        s.add(run)
        entity.sync_status, entity.sync_error = "running", None
        await s.flush()
        run_id = run.id

    try:
        client = XeroClient(
            (tokens or ConnectionTokens(workspace_id, connection_id)).access_token, transport
        )
        accounts = await client.list_accounts(tenant_id, modified_since=since)
    except Exception as exc:
        await _mark_failed(workspace_id, entity_id, run_id, exc)
        raise

    now = utcnow()
    async with unit_of_work(workspace_id=workspace_id) as s:
        rows = [_row(workspace_id, entity_id, a) for a in accounts if a.get("AccountID")]
        if rows:
            stmt = insert(EntityAccount).values(rows)
            await s.execute(
                stmt.on_conflict_do_update(
                    index_elements=[EntityAccount.entity_id, EntityAccount.xero_account_id],
                    set_={
                        c: stmt.excluded[c]
                        for c in rows[0]
                        if c not in ("workspace_id", "entity_id", "xero_account_id")
                    },
                )
            )
        deleted = 0
        # A Xero org always has accounts; an empty full response means something
        # went wrong upstream, and must never wipe the mirror.
        if kind == FULL and rows:
            seen = [r["xero_account_id"] for r in rows]
            result = await s.execute(
                update(EntityAccount)
                .where(
                    EntityAccount.entity_id == entity_id,
                    EntityAccount.deleted_at.is_(None),
                    EntityAccount.xero_account_id.not_in(seen),
                )
                .values(deleted_at=now)
            )
            deleted = result.rowcount or 0
        entity = await s.get(Entity, entity_id)
        newest = max((r["xero_updated_at"] for r in rows if r["xero_updated_at"]), default=None)
        if newest and (entity.accounts_modified_since is None or newest > entity.accounts_modified_since):
            entity.accounts_modified_since = newest
        entity.sync_status, entity.sync_error, entity.last_synced_at = "ok", None, now
        run = await s.get(SyncRun, run_id)
        run.status, run.records_seen, run.finished_at = "ok", len(rows), now
    return SyncResult(entity_id, kind, len(rows), deleted)


async def _mark_failed(workspace_id: uuid.UUID, entity_id: uuid.UUID, run_id: uuid.UUID, exc: Exception) -> None:
    message = f"{type(exc).__name__}: {str(exc)[:500]}"
    async with unit_of_work(workspace_id=workspace_id) as s:
        await s.execute(
            update(Entity).where(Entity.id == entity_id).values(sync_status="error", sync_error=message)
        )
        await s.execute(
            update(SyncRun)
            .where(SyncRun.id == run_id)
            .values(status="error", error=message, finished_at=utcnow())
        )


async def live_accounts(s, entity_id: uuid.UUID) -> list[EntityAccount]:
    """Accounts that currently exist and are active in the org."""
    result = await s.scalars(
        select(EntityAccount).where(
            EntityAccount.entity_id == entity_id,
            EntityAccount.deleted_at.is_(None),
            EntityAccount.status == "ACTIVE",
        )
    )
    return list(result)
