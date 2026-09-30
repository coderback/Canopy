"""Workspace settings and change control (Milestone 2).

Handlers are thin: permissions and state rules live in changes/service.py.
Jobs are enqueued with BackgroundTasks, i.e. after this request's transaction
has committed, so a worker never runs an approval that isn't saved yet."""

import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import func, select

from ..audit import service as audit
from ..auth.models import User
from ..changes import service
from ..changes.models import ChangeItem, ChangeSet
from ..core.config import get_settings
from ..core.errors import Forbidden, NotFound
from ..jobs.app import enqueue_change_items
from ..standard.models import GroupAccount
from ..sync.models import EntityAccount
from ..tenancy.models import Role
from ..tenancy.models import Workspace as WorkspaceRow
from ..xero.models import Entity
from . import schemas as S
from .deps import Workspace, WorkspaceContext

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["changes"])


# ---- settings -----------------------------------------------------------------


def _settings(ws: WorkspaceRow) -> dict:
    return {"changes_enabled": ws.changes_enabled, "allow_self_approval": ws.allow_self_approval,
            "writes_enabled_on_server": get_settings().writes_enabled}


@router.get("/settings", response_model=S.SettingsOut)
async def get_settings_(ctx: WorkspaceContext = Workspace):
    return _settings(await ctx.session.get(WorkspaceRow, ctx.workspace_id))


class SettingsChange(BaseModel):
    changes_enabled: bool | None = None
    allow_self_approval: bool | None = None


@router.patch("/settings", response_model=S.SettingsOut)
async def update_settings(body: SettingsChange, ctx: WorkspaceContext = Workspace):
    if ctx.role != Role.OWNER:
        raise Forbidden("Only the workspace owner can change these settings.")
    ws = await ctx.session.get(WorkspaceRow, ctx.workspace_id)
    before = _settings(ws)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(ws, field, value)
    await audit.record(ctx.session, "workspace.settings_changed", workspace_id=ctx.workspace_id,
                       actor_user_id=ctx.user_id, target_type="workspace", target_id=ws.id,
                       before=before, after=_settings(ws))
    return _settings(ws)


# ---- serialisation -------------------------------------------------------------


async def _users(s, ids) -> dict:
    ids = [i for i in ids if i]
    rows = await s.scalars(select(User).where(User.id.in_(ids))) if ids else []
    return {u.id: {"id": str(u.id), "email": u.email, "name": u.name} for u in rows}


def _iso(dt):
    return dt.isoformat() if dt else None


async def _item_out(s, item: ChangeItem) -> dict:
    entity = await s.get(Entity, item.entity_id)
    acct = await s.get(EntityAccount, item.entity_account_id) if item.entity_account_id else None
    group = await s.get(GroupAccount, item.group_account_id) if item.group_account_id else None
    return {
        "id": str(item.id), "entity_id": str(item.entity_id), "entity_name": entity.name if entity else "",
        "operation": item.operation,
        "account": {"id": str(acct.id), "code": acct.code, "name": acct.name, "type": acct.type} if acct else None,
        "group_account": {"id": str(group.id), "code": group.code, "name": group.name} if group else None,
        "payload": item.payload, "preflight_status": item.preflight_status,
        "preflight_messages": item.preflight_messages, "status": item.status, "attempt": item.attempt,
        "before": item.before, "after": item.after, "error": item.error, "executed_at": _iso(item.executed_at),
    }


async def _set_out(s, cs: ChangeSet, with_items: bool) -> dict:
    users = await _users(s, [cs.author_id, cs.decided_by])
    counts = dict((await s.execute(
        select(ChangeItem.status, func.count()).where(ChangeItem.change_set_id == cs.id).group_by(ChangeItem.status)
    )).all())
    out = {
        "id": str(cs.id), "title": cs.title, "reason": cs.reason, "status": cs.status,
        "author": users[cs.author_id], "decided_by": users.get(cs.decided_by),
        "decision_note": cs.decision_note, "self_approved": cs.self_approved,
        "created_at": _iso(cs.created_at), "submitted_at": _iso(cs.submitted_at), "decided_at": _iso(cs.decided_at),
        "item_counts": counts,
    }
    if with_items:
        out["items"] = [await _item_out(s, i) for i in await service.items(s, cs.id)]
    return out


async def _get(ctx: WorkspaceContext, set_id: uuid.UUID) -> ChangeSet:
    cs = await ctx.session.get(ChangeSet, set_id)
    if cs is None:
        raise NotFound("Change not found.")
    return cs


async def _own_item(ctx: WorkspaceContext, set_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """The item must belong to the change in the URL, not just to the workspace."""
    item = await ctx.session.get(ChangeItem, item_id)
    if item is None or item.change_set_id != set_id:
        raise NotFound("Item not found in this change.")


# ---- change sets ----------------------------------------------------------------


class ItemSpec(BaseModel):
    operation: Literal["create_account", "update_account", "archive_account"]
    entity_id: uuid.UUID
    entity_account_id: uuid.UUID | None = None
    group_account_id: uuid.UUID | None = None
    payload: dict | None = None


class NewChange(BaseModel):
    title: str
    reason: str = ""
    items: list[ItemSpec] = []


@router.get("/changes", response_model=list[S.ChangeSetOut])
async def list_changes(ctx: WorkspaceContext = Workspace):
    rows = await ctx.session.scalars(
        select(ChangeSet).where(ChangeSet.workspace_id == ctx.workspace_id).order_by(ChangeSet.created_at.desc())
    )
    return [await _set_out(ctx.session, cs, False) for cs in rows]


@router.post("/changes", status_code=201, response_model=S.ChangeSetOut)
async def create_change(body: NewChange, ctx: WorkspaceContext = Workspace):
    cs = await service.create_set(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, body.title, body.reason)
    for spec in body.items:
        await service.add_item(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, cs.id, spec.model_dump())
    return await _set_out(ctx.session, cs, True)


@router.get("/changes/{set_id}", response_model=S.ChangeSetOut)
async def get_change(set_id: uuid.UUID, ctx: WorkspaceContext = Workspace):
    return await _set_out(ctx.session, await _get(ctx, set_id), True)


@router.post("/changes/{set_id}/items", status_code=201, response_model=S.ChangeSetOut)
async def add_item(set_id: uuid.UUID, body: ItemSpec, ctx: WorkspaceContext = Workspace):
    await service.add_item(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, set_id, body.model_dump())
    return await _set_out(ctx.session, await _get(ctx, set_id), True)


class ItemEdit(BaseModel):
    payload: dict


@router.patch("/changes/{set_id}/items/{item_id}", response_model=S.ChangeSetOut)
async def edit_item(set_id: uuid.UUID, item_id: uuid.UUID, body: ItemEdit, ctx: WorkspaceContext = Workspace):
    await _own_item(ctx, set_id, item_id)
    await service.edit_item(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, item_id, body.payload)
    return await _set_out(ctx.session, await _get(ctx, set_id), True)


@router.delete("/changes/{set_id}/items/{item_id}", response_model=S.ChangeSetOut)
async def remove_item(set_id: uuid.UUID, item_id: uuid.UUID, ctx: WorkspaceContext = Workspace):
    await _own_item(ctx, set_id, item_id)
    await service.remove_item(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, item_id)
    return await _set_out(ctx.session, await _get(ctx, set_id), True)


@router.post("/changes/{set_id}/submit", response_model=S.ChangeSetOut)
async def submit(set_id: uuid.UUID, ctx: WorkspaceContext = Workspace):
    cs = await service.submit(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, set_id)
    return await _set_out(ctx.session, cs, True)


class ChangeDecision(BaseModel):
    note: str | None = None


@router.post("/changes/{set_id}/approve", response_model=S.ChangeSetOut)
async def approve(set_id: uuid.UUID, body: ChangeDecision, tasks: BackgroundTasks, ctx: WorkspaceContext = Workspace):
    cs, runnable = await service.decide(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, set_id, True, body.note)
    tasks.add_task(enqueue_change_items, ctx.workspace_id, runnable)
    return await _set_out(ctx.session, cs, True)


@router.post("/changes/{set_id}/reject", response_model=S.ChangeSetOut)
async def reject(set_id: uuid.UUID, body: ChangeDecision, ctx: WorkspaceContext = Workspace):
    cs, _ = await service.decide(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, set_id, False, body.note)
    return await _set_out(ctx.session, cs, True)


@router.post("/changes/{set_id}/cancel", response_model=S.ChangeSetOut)
async def cancel(set_id: uuid.UUID, ctx: WorkspaceContext = Workspace):
    cs = await service.cancel(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, set_id)
    return await _set_out(ctx.session, cs, True)


@router.post("/changes/{set_id}/retry", response_model=S.ChangeSetOut)
async def retry(set_id: uuid.UUID, tasks: BackgroundTasks, ctx: WorkspaceContext = Workspace):
    runnable = await service.retry_failed(ctx.session, ctx.workspace_id, ctx.user_id, ctx.role, set_id)
    tasks.add_task(enqueue_change_items, ctx.workspace_id, runnable)
    return await _set_out(ctx.session, await _get(ctx, set_id), True)
