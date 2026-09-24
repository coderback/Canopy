"""Background jobs on a Postgres-backed queue (procrastinate): no Redis.

- All Xero work for one tenant runs serially: jobs take `lock="tenant:<id>"`,
  so API calls for a tenant never race each other against its rate limit,
  whichever worker process picks them up.
- `queueing_lock` de-duplicates: at most one pending sync per entity.
- QuotaExhausted re-schedules the job for when Xero says it may retry, instead
  of blocking a worker.
- Jobs run as the app role, so RLS applies: each job binds its workspace.
"""

import logging
import uuid

import procrastinate
from sqlalchemy import text

# Register EVERY model: the worker imports only a few services, and SQLAlchemy
# can't resolve a foreign key (e.g. sync_runs.workspace_id -> workspaces) to a
# table whose model was never imported.
from .. import models  # noqa: F401
from ..core.config import get_settings
from ..core.db import unit_of_work
from ..llm import complete_structured
from ..mapping.service import generate_suggestions
from ..sync.service import FULL, INCREMENTAL, mark_entity_failed, sync_entity_accounts
from ..xero.client import QuotaExhausted
from ..xero.tokens import ConnectionRevoked

log = logging.getLogger(__name__)


def _conninfo() -> str:
    # SQLAlchemy URL -> libpq conninfo for psycopg.
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://", 1)


app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=_conninfo()),
    import_paths=["canopy.jobs.app"],
)


def llm_configured() -> bool:
    s = get_settings()
    return bool(s.azure_openai_endpoint or s.openai_api_key)


async def enqueue_sync(workspace_id: uuid.UUID, entity_id: uuid.UUID, tenant_id: str, kind: str = INCREMENTAL) -> None:
    try:
        await sync_accounts.configure(
            lock=f"tenant:{tenant_id}", queueing_lock=f"sync:{entity_id}"
        ).defer_async(workspace_id=str(workspace_id), entity_id=str(entity_id), tenant_id=tenant_id, kind=kind)
    except procrastinate.exceptions.AlreadyEnqueued:
        pass  # a sync for this entity is already waiting; it will pick up the latest data


async def enqueue_suggest(workspace_id: uuid.UUID, entity_id: uuid.UUID, refresh: bool = False) -> None:
    try:
        await suggest_mappings.configure(queueing_lock=f"suggest:{entity_id}").defer_async(
            workspace_id=str(workspace_id), entity_id=str(entity_id), refresh=refresh
        )
    except procrastinate.exceptions.AlreadyEnqueued:
        pass


@app.task(name="sync_accounts", queue="xero")
async def sync_accounts(workspace_id: str, entity_id: str, tenant_id: str, kind: str) -> None:
    ws, ent = uuid.UUID(workspace_id), uuid.UUID(entity_id)
    try:
        await sync_entity_accounts(ws, ent, kind)
    except QuotaExhausted as exc:
        log.info("sync deferred: %s", exc)
        await sync_accounts.configure(lock=f"tenant:{tenant_id}", schedule_at=exc.retry_at).defer_async(
            workspace_id=workspace_id, entity_id=entity_id, tenant_id=tenant_id, kind=kind
        )
        return
    except ConnectionRevoked as exc:
        log.warning("sync skipped: connection revoked for entity %s", entity_id)
        await mark_entity_failed(ws, ent, exc)
        return
    except Exception as exc:
        await mark_entity_failed(ws, ent, exc)
        raise
    # New or changed accounts get suggestions straight away.
    await enqueue_suggest(ws, ent)


@app.task(name="suggest_mappings", queue="mapping")
async def suggest_mappings(workspace_id: str, entity_id: str, refresh: bool = False) -> None:
    complete = complete_structured if llm_configured() else None
    await generate_suggestions(uuid.UUID(workspace_id), uuid.UUID(entity_id), complete, refresh=refresh)


@app.periodic(cron="0 2 * * *")
@app.task(name="nightly_full_sync", queue="xero")
async def nightly_full_sync(timestamp: int) -> None:
    """Full sync every active entity (catches deletions incremental can't see).
    Listing entities across workspaces goes through a SECURITY DEFINER function
    that returns only ids: the job itself has no workspace context."""
    async with unit_of_work() as s:
        rows = (await s.execute(text("select workspace_id, entity_id, tenant_id from canopy_active_entities()"))).all()
    for workspace_id, entity_id, tenant_id in rows:
        await enqueue_sync(workspace_id, entity_id, tenant_id, FULL)
