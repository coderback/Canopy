"""Executes one approved tracking-category item (after executor.py's gates:
runnable, changes on, writes allowed).

1. refresh the org's mirror (its tracking is always read in full);
2. preflight again on that fresh state -> any problem fails WITHOUT writing;
   `before` is the target as Xero has it now;
3. write with the item's Idempotency-Key. Creating a category is several writes
   (the category, then each option): each has its own key derived from the item's,
   and the category's Xero id is saved as soon as it exists, so a retry adds only
   what's still missing instead of creating the category twice;
4. update the mirror and, for creates from the standard, confirm the mapping so
   the gap closes; then finish (audit + roll-up).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..core.db import unit_of_work
from ..core.models_base import utcnow
from ..mapping.matcher import normalise
from ..sync.service import INCREMENTAL, sync_entity_accounts
from ..tracking import changes as tc
from ..tracking import preflight as tp
from ..tracking.models import (
    EntityTrackingOption,
    GroupTrackingOption,
    TrackingCategoryMapping,
    TrackingOptionMapping,
)
from ..tracking.sync import upsert_category, upsert_option
from ..xero.client import QuotaExhausted, XeroApiError, XeroClient
from ..xero.models import Entity
from .models import ChangeItem
from .outcome import finish, reset


def _snapshot(category: tp.OrgCategory | None, option: tp.OrgOption | None) -> dict | None:
    if option is not None:
        return {"TrackingOptionID": option.xero_option_id, "Name": option.name, "Status": option.status}
    if category is not None:
        return {"TrackingCategoryID": category.xero_category_id, "Name": category.name, "Status": category.status,
                "Options": [{"TrackingOptionID": o.xero_option_id, "Name": o.name, "Status": o.status}
                            for o in category.options]}
    return None


async def _record_created(workspace_id, item_id, xero_id: str) -> None:
    async with unit_of_work(workspace_id=workspace_id) as s:
        (await s.get(ChangeItem, item_id)).created_xero_id = xero_id


async def _confirm(s, model, key_column: str, local_id, target_column: str, target_id, workspace_id, entity_id,
                   actor) -> None:
    now = utcnow()
    values = {"workspace_id": workspace_id, "entity_id": entity_id, key_column: local_id, target_column: target_id,
              "status": "confirmed", "source": "created", "confidence": 1.0,
              "reasoning": "Created in Xero by an approved Canopy change.", "decided_by": actor, "decided_at": now,
              "updated_at": now}
    stmt = insert(model).values(**values)
    await s.execute(stmt.on_conflict_do_update(
        index_elements=[getattr(model, key_column)],
        set_={k: stmt.excluded[k] for k in values if k not in ("workspace_id", "entity_id", key_column)},
    ))


async def execute_tracking(workspace_id: uuid.UUID, item_id: uuid.UUID, *, transport, tokens, actor,
                           replay: bool) -> str:
    async with unit_of_work(workspace_id=workspace_id) as s:
        item = await s.get(ChangeItem, item_id)
        entity = await s.get(Entity, item.entity_id)
        op, payload, key = item.operation, dict(item.payload), item.idempotency_key
        entity_id, tenant_id = entity.id, entity.tenant_id
        local_category_id = item.entity_tracking_category_id
        group_category_id, group_option_id = item.group_tracking_category_id, item.group_tracking_option_id

    client = XeroClient(tokens.access_token, transport)
    try:
        await sync_entity_accounts(workspace_id, entity_id, INCREMENTAL, transport=transport, tokens=tokens)
    except QuotaExhausted:
        await reset(workspace_id, item_id)
        raise
    except Exception as exc:  # noqa: BLE001 — recorded on the item, never silent
        await finish(workspace_id, item_id, status="failed", actor=actor,
                     error=f"Couldn't read the organisation before writing: {exc}")
        return "failed"

    async with unit_of_work(workspace_id=workspace_id) as s:
        item = await s.get(ChangeItem, item_id)
        entity = await s.get(Entity, entity_id)
        org = await tc.org_tracking(s, entity)
        category, option = await tc.targets(s, item, org)
        problems = tp.check(op, payload, org, category=category, option=option)
    before = None if op == tp.CREATE_CATEGORY else _snapshot(category, option)
    if problems and not replay:
        await finish(workspace_id, item_id, status="failed", before=before, actor=actor,
                     error="Not written — " + " ".join(problems))
        return "failed"

    category_xero_id = category.xero_category_id if category else None
    if (op != tp.CREATE_CATEGORY and category is None) or (op in tp.OPTION_TARGET and option is None):
        # Only reachable on a replay (preflight would have caught it otherwise).
        await finish(workspace_id, item_id, status="failed", before=before, actor=actor,
                     error="Not written — the tracking category or option no longer exists in Xero.")
        return "failed"
    try:
        if op == tp.CREATE_CATEGORY:
            if category_xero_id is None:
                created = await client.create_tracking_category(tenant_id, payload["name"].strip(), f"{key}-category")
                category_xero_id = created["TrackingCategoryID"]
                await _record_created(workspace_id, item_id, category_xero_id)
            have = {normalise(o.name) for o in category.options} if category else set()
            for n, name in enumerate(payload.get("options") or []):
                if normalise(name) not in have:
                    await client.create_tracking_option(tenant_id, category_xero_id, name.strip(), f"{key}-option-{n}")
            after = await client.get_tracking_category(tenant_id, category_xero_id) or {
                "TrackingCategoryID": category_xero_id, "Name": payload["name"].strip(), "Status": "ACTIVE"}
        elif op == tp.CREATE_OPTION:
            after = await client.create_tracking_option(tenant_id, category_xero_id, payload["name"].strip(), key)
        elif op in (tp.UPDATE_CATEGORY, tp.ARCHIVE_CATEGORY):
            fields = {"Name": payload["name"].strip()} if op == tp.UPDATE_CATEGORY else {"Status": "ARCHIVED"}
            after = await client.update_tracking_category(tenant_id, category_xero_id, fields, key)
        else:
            fields = {"Name": payload["name"].strip()} if op == tp.UPDATE_OPTION else {"Status": "ARCHIVED"}
            after = await client.update_tracking_option(tenant_id, category_xero_id, option.xero_option_id,
                                                        fields, key)
    except QuotaExhausted:
        await reset(workspace_id, item_id)
        raise
    except XeroApiError as exc:
        reason = "; ".join(exc.messages) if exc.messages else str(exc)
        await finish(workspace_id, item_id, status="failed", before=before, actor=actor,
                     error=f"Xero rejected the change: {reason}")
        return "failed"

    async with unit_of_work(workspace_id=workspace_id) as s:
        if op in (tp.CREATE_CATEGORY, tp.UPDATE_CATEGORY, tp.ARCHIVE_CATEGORY):
            local = await upsert_category(s, workspace_id, entity_id, after)
            if op == tp.CREATE_CATEGORY and group_category_id:
                # The new category IS the group category here: confirm it and its
                # options by name, so the gaps close.
                await _confirm(s, TrackingCategoryMapping, "entity_category_id", local, "group_category_id",
                               group_category_id, workspace_id, entity_id, actor)
                group_options = {normalise(g.name): g.id for g in await s.scalars(
                    select(GroupTrackingOption).where(GroupTrackingOption.category_id == group_category_id))}
                for o in await s.scalars(select(EntityTrackingOption).where(EntityTrackingOption.category_id == local)):
                    if normalise(o.name) in group_options:
                        await _confirm(s, TrackingOptionMapping, "entity_option_id", o.id, "group_option_id",
                                       group_options[normalise(o.name)], workspace_id, entity_id, actor)
        else:
            local = await upsert_option(s, workspace_id, entity_id, local_category_id, after)
            if op == tp.CREATE_OPTION and group_option_id:
                await _confirm(s, TrackingOptionMapping, "entity_option_id", local, "group_option_id",
                               group_option_id, workspace_id, entity_id, actor)
    await finish(workspace_id, item_id, status="succeeded", before=before, after=after, actor=actor)
    return "succeeded"
