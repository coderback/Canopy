"""Tracking categories: the group standard, mapping review and gaps.

Viewers read; owners/admins edit the standard and decide mappings, as for
accounts. Suggestions are exact-name matches, cheap enough to recompute inside
the request whenever the standard changes, so there's no job to wait for.
"""

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from ..core.errors import NotFound
from ..tracking import service as tracking
from ..tracking.models import GroupTrackingCategory
from ..xero.models import Entity
from . import schemas as S
from .deps import ADMINS, Workspace, WorkspaceContext, require_role

router = APIRouter(prefix="/workspaces/{workspace_id}/tracking", tags=["tracking"])
Admin = require_role(*ADMINS)


async def _resuggest_everywhere(ctx: WorkspaceContext) -> None:
    """The standard changed: re-suggest every org's still-undecided mappings."""
    for eid in await ctx.session.scalars(
        select(Entity.id).where(Entity.workspace_id == ctx.workspace_id, Entity.status == "active")
    ):
        await tracking.generate_suggestions(ctx.session, ctx.workspace_id, eid, refresh=True)


async def _category_out(ctx: WorkspaceContext, g: GroupTrackingCategory) -> dict:
    await ctx.session.flush()
    return next(c for c in await tracking.list_standard(ctx.session, ctx.workspace_id) if c["id"] == str(g.id))


# ---- the standard -------------------------------------------------------------


@router.get("/standard", response_model=list[S.TrackingCategoryOut])
async def get_standard(ctx: WorkspaceContext = Workspace):
    return await tracking.list_standard(ctx.session, ctx.workspace_id)


class TrackingSeed(BaseModel):
    entity_id: uuid.UUID


@router.post("/standard/seed", status_code=201, response_model=S.TrackingSeeded)
async def seed(body: TrackingSeed, ctx: WorkspaceContext = Admin):
    n = await tracking.seed_from_entity(ctx.session, ctx.workspace_id, body.entity_id, ctx.user_id)
    await ctx.session.flush()
    await _resuggest_everywhere(ctx)
    return {"categories": n}


class NewCategory(BaseModel):
    name: str
    options: list[str] = []


@router.post("/standard/categories", status_code=201, response_model=S.TrackingCategoryOut)
async def add_category(body: NewCategory, ctx: WorkspaceContext = Admin):
    g = await tracking.create_category(ctx.session, ctx.workspace_id, body.name, ctx.user_id, body.options)
    await _resuggest_everywhere(ctx)
    return await _category_out(ctx, g)


class StandardChange(BaseModel):
    name: str | None = None
    status: Literal["active", "archived"] | None = None


@router.patch("/standard/categories/{category_id}", response_model=S.TrackingCategoryOut)
async def edit_category(category_id: uuid.UUID, body: StandardChange, ctx: WorkspaceContext = Admin):
    g = await tracking.update_category(ctx.session, ctx.workspace_id, category_id,
                                       body.model_dump(exclude_unset=True), ctx.user_id)
    await ctx.session.flush()
    await _resuggest_everywhere(ctx)
    return await _category_out(ctx, g)


class NewOption(BaseModel):
    name: str


@router.post("/standard/categories/{category_id}/options", status_code=201, response_model=S.TrackingCategoryOut)
async def add_option(category_id: uuid.UUID, body: NewOption, ctx: WorkspaceContext = Admin):
    o = await tracking.create_option(ctx.session, ctx.workspace_id, category_id, body.name, ctx.user_id)
    await _resuggest_everywhere(ctx)
    return await _category_out(ctx, await ctx.session.get(GroupTrackingCategory, o.category_id))


@router.patch("/standard/options/{option_id}", response_model=S.TrackingCategoryOut)
async def edit_option(option_id: uuid.UUID, body: StandardChange, ctx: WorkspaceContext = Admin):
    o = await tracking.update_option(ctx.session, ctx.workspace_id, option_id,
                                     body.model_dump(exclude_unset=True), ctx.user_id)
    await ctx.session.flush()
    await _resuggest_everywhere(ctx)
    return await _category_out(ctx, await ctx.session.get(GroupTrackingCategory, o.category_id))


# ---- mapping review --------------------------------------------------------------


async def _entity(ctx: WorkspaceContext, entity_id: uuid.UUID) -> Entity:
    e = await ctx.session.get(Entity, entity_id)
    if e is None:
        raise NotFound("Organisation not found.")
    return e


@router.get("/entities/{entity_id}", response_model=list[S.TrackingCategoryRow])
async def entity_tracking(entity_id: uuid.UUID, ctx: WorkspaceContext = Workspace):
    await _entity(ctx, entity_id)
    return await tracking.entity_view(ctx.session, entity_id)


@router.post("/entities/{entity_id}/suggest", response_model=list[S.TrackingCategoryRow])
async def resuggest(entity_id: uuid.UUID, ctx: WorkspaceContext = Admin):
    await _entity(ctx, entity_id)
    await tracking.generate_suggestions(ctx.session, ctx.workspace_id, entity_id, refresh=True)
    await ctx.session.flush()
    return await tracking.entity_view(ctx.session, entity_id)


@router.post("/entities/{entity_id}/confirm-exact", response_model=S.ConfirmedOut)
async def confirm_exact(entity_id: uuid.UUID, ctx: WorkspaceContext = Admin):
    await _entity(ctx, entity_id)
    return {"confirmed": await tracking.confirm_exact(ctx.session, ctx.workspace_id, entity_id, ctx.user_id)}


class TrackingDecision(BaseModel):
    action: Literal["confirm", "reject", "assign"]
    group_id: uuid.UUID | None = None


@router.post("/mappings/categories/{mapping_id}/decision", response_model=S.DecisionOut)
async def decide_category(mapping_id: uuid.UUID, body: TrackingDecision, ctx: WorkspaceContext = Admin):
    m = await tracking.decide_category(ctx.session, ctx.workspace_id, mapping_id, body.action, ctx.user_id,
                                       body.group_id)
    return {"id": str(m.id), "status": m.status}


@router.post("/mappings/options/{mapping_id}/decision", response_model=S.DecisionOut)
async def decide_option(mapping_id: uuid.UUID, body: TrackingDecision, ctx: WorkspaceContext = Admin):
    m = await tracking.decide_option(ctx.session, ctx.workspace_id, mapping_id, body.action, ctx.user_id,
                                     body.group_id)
    return {"id": str(m.id), "status": m.status}


@router.get("/gaps", response_model=S.TrackingGapMatrix)
async def gaps(ctx: WorkspaceContext = Workspace):
    return await tracking.gaps(ctx.session, ctx.workspace_id)
