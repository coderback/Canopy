"""Recording how a change item ended, shared by the account and tracking
executors: the item's status, before/after and the audit event, then the set's
status rolled up under a row lock (items for different tenants run in parallel).
"""

from sqlalchemy import select

from ..audit import service as audit
from ..core.db import unit_of_work
from ..core.models_base import utcnow
from .models import ChangeItem, ChangeSet
from .service import roll_up


async def finish(workspace_id, item_id, *, status: str, error: str | None = None, before=None, after=None,
                 xero_account_id: str | None = None, actor=None) -> None:
    async with unit_of_work(workspace_id=workspace_id) as s:
        item = await s.get(ChangeItem, item_id)
        item.status, item.error, item.executed_at = status, error, utcnow()
        if before is not None:
            item.before = before
        if after is not None:
            item.after, item.xero_account_id = after, xero_account_id
        await audit.record(
            s, f"change.item_{status}", workspace_id=workspace_id, actor_user_id=actor,
            target_type="change_item", target_id=item.id, before=before,
            after=after if status == "succeeded" else {"error": error},
        )
        cs = (await s.execute(
            select(ChangeSet).where(ChangeSet.id == item.change_set_id).with_for_update()
        )).scalar_one()
        statuses = list(await s.scalars(select(ChangeItem.status).where(ChangeItem.change_set_id == cs.id)))
        final = roll_up(statuses)
        if final and cs.status != final:
            cs.status = final
            await audit.record(s, f"change.{final}", workspace_id=workspace_id, actor_user_id=None,
                               target_type="change_set", target_id=cs.id)


async def reset(workspace_id, item_id) -> None:
    """Back to pending, for a job that will be rescheduled (quota exhausted)."""
    async with unit_of_work(workspace_id=workspace_id) as s:
        item = await s.get(ChangeItem, item_id)
        item.status = "pending"
