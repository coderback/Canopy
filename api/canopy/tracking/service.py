"""Tracking categories: the group standard, mapping each org onto it, and gaps.

Rules (same spirit as accounts):
- the standard holds at most two ACTIVE categories (Xero's per-org maximum);
- names are unique case-insensitively: categories within the standard, options
  within their category;
- suggestions never overwrite a human decision;
- an option maps only to an option of the group category its own category maps
  to, and can only be confirmed once that category mapping is confirmed;
- every decision and every edit to the standard is audited.
No AI here: suggestions are exact name matches, computed in one transaction.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from ..audit import service as audit
from ..core.errors import AppError, Conflict, NotFound
from ..core.models_base import utcnow
from ..mapping.matcher import EXACT, MANUAL, Match
from ..xero.models import Entity
from ..xero.status import SHOWN
from .matcher import Named, match_categories, match_options
from .models import (
    MAX_ACTIVE_CATEGORIES,
    MAX_NAME,
    EntityTrackingCategory,
    EntityTrackingOption,
    GroupTrackingCategory,
    GroupTrackingOption,
    TrackingCategoryMapping,
    TrackingOptionMapping,
)

SUGGESTED, CONFIRMED, REJECTED = "suggested", "confirmed", "rejected"


def _norm(s: str) -> str:
    return s.strip().lower()


def _clean_name(name: str | None, what: str) -> str:
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > MAX_NAME:
        raise AppError(f"A {what} name must be 1–{MAX_NAME} characters.")
    return name.strip()


# ---- the standard ------------------------------------------------------------------------


def option_dict(o: GroupTrackingOption) -> dict:
    return {"id": str(o.id), "name": o.name, "status": o.status}


def category_dict(c: GroupTrackingCategory, options: list[GroupTrackingOption]) -> dict:
    return {"id": str(c.id), "name": c.name, "status": c.status, "options": [option_dict(o) for o in options]}


async def _categories(s, workspace_id) -> list[GroupTrackingCategory]:
    return list(await s.scalars(
        select(GroupTrackingCategory).where(GroupTrackingCategory.workspace_id == workspace_id)
        .order_by(GroupTrackingCategory.created_at, GroupTrackingCategory.name)
    ))


async def _options(s, category_id) -> list[GroupTrackingOption]:
    return list(await s.scalars(
        select(GroupTrackingOption).where(GroupTrackingOption.category_id == category_id)
        .order_by(GroupTrackingOption.created_at, GroupTrackingOption.name)
    ))


async def list_standard(s, workspace_id) -> list[dict]:
    return [category_dict(c, await _options(s, c.id)) for c in await _categories(s, workspace_id)]


async def active_option_names(s, category_id) -> list[str]:
    return [o.name for o in await _options(s, category_id) if o.status == "active"]


async def _check_active_room(s, workspace_id, ignore: uuid.UUID | None = None) -> None:
    active = [c for c in await _categories(s, workspace_id) if c.status == "active" and c.id != ignore]
    if len(active) >= MAX_ACTIVE_CATEGORIES:
        raise Conflict(f"The group standard already has {len(active)} active tracking categories "
                       f"({', '.join(c.name for c in active)}). Xero allows two per organisation, so archive "
                       "one first.")


async def _check_category_name(s, workspace_id, name: str, ignore: uuid.UUID | None = None) -> None:
    for c in await _categories(s, workspace_id):
        if c.id != ignore and _norm(c.name) == _norm(name):
            raise Conflict(f"The group standard already has a tracking category named '{c.name}'.")


async def _check_option_name(s, category_id, name: str, ignore: uuid.UUID | None = None) -> None:
    for o in await _options(s, category_id):
        if o.id != ignore and _norm(o.name) == _norm(name):
            raise Conflict(f"That category already has an option named '{o.name}'.")


async def seed_from_entity(s, workspace_id, entity_id, actor) -> int:
    """Copy an org's ACTIVE categories and options into an EMPTY tracking standard."""
    if await _categories(s, workspace_id):
        raise Conflict("The group standard already has tracking categories; edit them instead of re-seeding.")
    entity = await s.get(Entity, entity_id)
    if entity is None:
        raise NotFound("Organisation not found.")
    categories = list(await s.scalars(
        select(EntityTrackingCategory).where(
            EntityTrackingCategory.entity_id == entity_id, EntityTrackingCategory.deleted_at.is_(None),
            EntityTrackingCategory.status == "ACTIVE",
        ).order_by(EntityTrackingCategory.name)
    ))
    if not categories:
        raise AppError(f"{entity.name} has no active tracking categories to copy.")
    options = 0
    for c in categories[:MAX_ACTIVE_CATEGORIES]:
        g = GroupTrackingCategory(workspace_id=workspace_id, name=c.name[:MAX_NAME], source_entity_id=entity_id)
        s.add(g)
        await s.flush()
        for o in await s.scalars(
            select(EntityTrackingOption).where(
                EntityTrackingOption.category_id == c.id, EntityTrackingOption.deleted_at.is_(None),
                EntityTrackingOption.status == "ACTIVE",
            ).order_by(EntityTrackingOption.name)
        ):
            s.add(GroupTrackingOption(workspace_id=workspace_id, category_id=g.id, name=o.name[:MAX_NAME]))
            options += 1
    await audit.record(s, "standard.tracking_seeded", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="entity", target_id=entity_id,
                       after={"categories": len(categories), "options": options, "entity": entity.name})
    return len(categories)


async def create_category(s, workspace_id, name: str, actor, options: list[str] | None = None) -> GroupTrackingCategory:
    name = _clean_name(name, "tracking category")
    await _check_category_name(s, workspace_id, name)
    await _check_active_room(s, workspace_id)
    g = GroupTrackingCategory(workspace_id=workspace_id, name=name)
    s.add(g)
    await s.flush()
    seen = set()
    for raw in options or []:
        option = _clean_name(raw, "option")
        if _norm(option) in seen:
            raise AppError(f"Option '{option}' is listed twice.")
        seen.add(_norm(option))
        s.add(GroupTrackingOption(workspace_id=workspace_id, category_id=g.id, name=option))
    await s.flush()
    await audit.record(s, "standard.tracking_category_created", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="group_tracking_category", target_id=g.id,
                       after=category_dict(g, await _options(s, g.id)))
    return g


async def update_category(s, workspace_id, category_id, changes: dict, actor) -> GroupTrackingCategory:
    g = await s.get(GroupTrackingCategory, category_id)
    if g is None:
        raise NotFound("Tracking category not found.")
    before = category_dict(g, [])
    if changes.get("name") is not None:
        name = _clean_name(changes["name"], "tracking category")
        await _check_category_name(s, workspace_id, name, ignore=g.id)
        g.name = name
    if changes.get("status") in ("active", "archived") and changes["status"] != g.status:
        if changes["status"] == "active":
            await _check_active_room(s, workspace_id, ignore=g.id)
        g.status = changes["status"]
    await audit.record(s, "standard.tracking_category_updated", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="group_tracking_category", target_id=g.id, before=before,
                       after=category_dict(g, []))
    return g


async def create_option(s, workspace_id, category_id, name: str, actor) -> GroupTrackingOption:
    g = await s.get(GroupTrackingCategory, category_id)
    if g is None:
        raise NotFound("Tracking category not found.")
    name = _clean_name(name, "option")
    await _check_option_name(s, g.id, name)
    o = GroupTrackingOption(workspace_id=workspace_id, category_id=g.id, name=name)
    s.add(o)
    await s.flush()
    await audit.record(s, "standard.tracking_option_created", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="group_tracking_option", target_id=o.id,
                       after={**option_dict(o), "category": g.name})
    return o


async def update_option(s, workspace_id, option_id, changes: dict, actor) -> GroupTrackingOption:
    o = await s.get(GroupTrackingOption, option_id)
    if o is None:
        raise NotFound("Tracking option not found.")
    before = option_dict(o)
    if changes.get("name") is not None:
        name = _clean_name(changes["name"], "option")
        await _check_option_name(s, o.category_id, name, ignore=o.id)
        o.name = name
    if changes.get("status") in ("active", "archived"):
        o.status = changes["status"]
    await audit.record(s, "standard.tracking_option_updated", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="group_tracking_option", target_id=o.id, before=before, after=option_dict(o))
    return o


# ---- mapping -------------------------------------------------------------------------------


def _live_categories(entity_id):
    return select(EntityTrackingCategory).where(
        EntityTrackingCategory.entity_id == entity_id, EntityTrackingCategory.deleted_at.is_(None),
        EntityTrackingCategory.status == "ACTIVE",
    ).order_by(EntityTrackingCategory.name)


def _live_options(category_id):
    return select(EntityTrackingOption).where(
        EntityTrackingOption.category_id == category_id, EntityTrackingOption.deleted_at.is_(None),
        EntityTrackingOption.status == "ACTIVE",
    ).order_by(EntityTrackingOption.name)


async def _upsert(s, model, key_column: str, target_column: str, workspace_id, entity_id, m: Match) -> None:
    values = {"workspace_id": workspace_id, "entity_id": entity_id, key_column: m.local_id,
              target_column: m.group_id, "status": SUGGESTED, "source": m.source,
              "confidence": m.confidence, "reasoning": m.reasoning, "updated_at": utcnow()}
    stmt = insert(model).values(**values)
    # Only rows still awaiting review are replaced; decisions stand.
    await s.execute(stmt.on_conflict_do_update(
        index_elements=[getattr(model, key_column)],
        set_={k: stmt.excluded[k] for k in (target_column, "source", "confidence", "reasoning", "updated_at")},
        where=model.status == SUGGESTED,
    ))


async def _category_target(s, entity_category_id) -> GroupTrackingCategory | None:
    """The group category this org category maps to (suggested or confirmed)."""
    m = await s.scalar(select(TrackingCategoryMapping).where(
        TrackingCategoryMapping.entity_category_id == entity_category_id))
    if m is None or m.group_category_id is None or m.status == REJECTED:
        return None
    return await s.get(GroupTrackingCategory, m.group_category_id)


async def _suggest_options(s, workspace_id, entity_id, category: EntityTrackingCategory, refresh: bool) -> None:
    existing = {m.entity_option_id: m.status for m in await s.scalars(
        select(TrackingOptionMapping).join(EntityTrackingOption,
                                          EntityTrackingOption.id == TrackingOptionMapping.entity_option_id)
        .where(EntityTrackingOption.category_id == category.id))}
    todo = [Named(o.id, o.name) for o in await s.scalars(_live_options(category.id))
            if o.id not in existing or (refresh and existing[o.id] == SUGGESTED)]
    if not todo:
        return
    target = await _category_target(s, category.id)
    group_options = ([Named(o.id, o.name) for o in await _options(s, target.id) if o.status == "active"]
                     if target and target.status == "active" else [])
    for m in match_options(todo, group_options, target.name if target else None):
        await _upsert(s, TrackingOptionMapping, "entity_option_id", "group_option_id", workspace_id, entity_id, m)


async def generate_suggestions(s, workspace_id, entity_id, *, refresh: bool = False) -> None:
    """Suggest mappings for the org's unmapped categories and options (with
    refresh=True, also re-suggest ones still awaiting review)."""
    standard = [Named(c.id, c.name) for c in await _categories(s, workspace_id) if c.status == "active"]
    existing = {m.entity_category_id: m.status for m in await s.scalars(
        select(TrackingCategoryMapping).where(TrackingCategoryMapping.entity_id == entity_id))}
    categories = list(await s.scalars(_live_categories(entity_id)))
    todo = [Named(c.id, c.name) for c in categories
            if c.id not in existing or (refresh and existing[c.id] == SUGGESTED)]
    for m in match_categories(todo, standard):
        await _upsert(s, TrackingCategoryMapping, "entity_category_id", "group_category_id", workspace_id,
                      entity_id, m)
    for c in categories:
        await _suggest_options(s, workspace_id, entity_id, c, refresh)


def _mapping_dict(m) -> dict:
    target = m.group_category_id if isinstance(m, TrackingCategoryMapping) else m.group_option_id
    return {"id": str(m.id), "status": m.status, "source": m.source,
            "group_id": str(target) if target else None, "confidence": m.confidence, "reasoning": m.reasoning}


def _apply(m, action: str, target_column: str, target_id, actor) -> None:
    if action == "confirm":
        m.status = CONFIRMED
    elif action == "reject":
        m.status = REJECTED
    elif action == "assign":
        setattr(m, target_column, target_id)
        m.status, m.source, m.confidence = CONFIRMED, MANUAL, 1.0
        m.reasoning = "Assigned by a person." if target_id else "Marked local-only by a person."
    else:
        raise AppError(f"Unknown action {action!r}.")
    m.decided_by, m.decided_at = actor, utcnow()


async def decide_category(s, workspace_id, mapping_id, action: str, actor, group_category_id=None):
    m = await s.get(TrackingCategoryMapping, mapping_id)
    if m is None:
        raise NotFound("Mapping not found.")
    if action == "assign" and group_category_id is not None \
            and await s.get(GroupTrackingCategory, group_category_id) is None:
        raise NotFound("Group tracking category not found.")
    before = _mapping_dict(m)
    _apply(m, action, "group_category_id", group_category_id, actor)
    await audit.record(s, f"tracking_mapping.{action}", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="tracking_category_mapping", target_id=m.id, before=before,
                       after=_mapping_dict(m))
    await _reconcile_options(s, workspace_id, m)
    return m


async def _reconcile_options(s, workspace_id, m: TrackingCategoryMapping) -> None:
    """After a category decision, drop option mappings that now point outside the
    category's group category, then re-suggest the options."""
    target = m.group_category_id if m.status != REJECTED else None
    allowed = [o.id for o in await _options(s, target)] if target else []
    option_ids = select(EntityTrackingOption.id).where(EntityTrackingOption.category_id == m.entity_category_id)
    stale = delete(TrackingOptionMapping).where(
        TrackingOptionMapping.entity_option_id.in_(option_ids),
        TrackingOptionMapping.group_option_id.is_not(None),
    )
    if allowed:
        stale = stale.where(TrackingOptionMapping.group_option_id.not_in(allowed))
    await s.execute(stale)
    category = await s.get(EntityTrackingCategory, m.entity_category_id)
    await s.flush()
    await _suggest_options(s, workspace_id, m.entity_id, category, refresh=True)


async def decide_option(s, workspace_id, mapping_id, action: str, actor, group_option_id=None):
    m = await s.get(TrackingOptionMapping, mapping_id)
    if m is None:
        raise NotFound("Mapping not found.")
    option = await s.get(EntityTrackingOption, m.entity_option_id)
    if action in ("confirm", "assign"):
        cm = await s.scalar(select(TrackingCategoryMapping).where(
            TrackingCategoryMapping.entity_category_id == option.category_id))
        if cm is None or cm.status != CONFIRMED:
            raise AppError("Confirm how its tracking category maps first.")
        chosen = group_option_id if action == "assign" else m.group_option_id
        if chosen is not None:
            g = await s.get(GroupTrackingOption, chosen)
            if g is None:
                raise NotFound("Group tracking option not found.")
            if g.category_id != cm.group_category_id:
                raise AppError("That option belongs to a different group tracking category.")
    before = _mapping_dict(m)
    _apply(m, action, "group_option_id", group_option_id, actor)
    await audit.record(s, f"tracking_mapping.{action}", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="tracking_option_mapping", target_id=m.id, before=before, after=_mapping_dict(m))
    return m


async def confirm_exact(s, workspace_id, entity_id, actor) -> int:
    """Bulk-confirm exact-name suggestions: categories first, then the options of
    categories that are now confirmed."""
    now, n = utcnow(), 0
    for m in await s.scalars(select(TrackingCategoryMapping).where(
            TrackingCategoryMapping.entity_id == entity_id, TrackingCategoryMapping.status == SUGGESTED,
            TrackingCategoryMapping.source == EXACT)):
        m.status, m.decided_by, m.decided_at = CONFIRMED, actor, now
        n += 1
    await s.flush()
    confirmed_categories = select(TrackingCategoryMapping.entity_category_id).where(
        TrackingCategoryMapping.entity_id == entity_id, TrackingCategoryMapping.status == CONFIRMED)
    for m in await s.scalars(
        select(TrackingOptionMapping).join(EntityTrackingOption,
                                          EntityTrackingOption.id == TrackingOptionMapping.entity_option_id)
        .where(TrackingOptionMapping.entity_id == entity_id, TrackingOptionMapping.status == SUGGESTED,
               TrackingOptionMapping.source == EXACT,
               EntityTrackingOption.category_id.in_(confirmed_categories))
    ):
        m.status, m.decided_by, m.decided_at = CONFIRMED, actor, now
        n += 1
    if n:
        await audit.record(s, "tracking_mapping.bulk_confirm_exact", workspace_id=workspace_id,
                           actor_user_id=actor, target_type="entity", target_id=entity_id, after={"confirmed": n})
    return n


async def entity_view(s, entity_id) -> list[dict]:
    """The org's active categories and options, each with its mapping, for review."""
    out = []
    for c in await s.scalars(_live_categories(entity_id)):
        cm = await s.scalar(select(TrackingCategoryMapping).where(TrackingCategoryMapping.entity_category_id == c.id))
        gc = await s.get(GroupTrackingCategory, cm.group_category_id) if cm and cm.group_category_id else None
        options = []
        for o in await s.scalars(_live_options(c.id)):
            om = await s.scalar(select(TrackingOptionMapping).where(TrackingOptionMapping.entity_option_id == o.id))
            go = await s.get(GroupTrackingOption, om.group_option_id) if om and om.group_option_id else None
            options.append({"id": str(o.id), "name": o.name, "mapping": _mapping_dict(om) if om else None,
                            "group_option": {"id": str(go.id), "name": go.name} if go else None})
        out.append({"id": str(c.id), "name": c.name, "mapping": _mapping_dict(cm) if cm else None,
                    "group_category": {"id": str(gc.id), "name": gc.name} if gc else None, "options": options})
    return out


# ---- gaps -------------------------------------------------------------------------------------


async def gaps(s, workspace_id) -> dict:
    """Group categories and options × active orgs.

    Category cell: mapped (a live org category confirmed against it) | pending
    (only suggested) | gap. Option cell: mapped | pending | gap (the org has the
    category, so the option can be added to it: `entity_category_id` says where)
    | no_category (the org lacks the category itself)."""
    entities = list(await s.scalars(
        select(Entity).where(Entity.workspace_id == workspace_id, Entity.status.in_(SHOWN)).order_by(Entity.name)))
    cat_rows = (await s.execute(
        select(TrackingCategoryMapping.entity_id, TrackingCategoryMapping.group_category_id,
               TrackingCategoryMapping.status, TrackingCategoryMapping.entity_category_id)
        .join(EntityTrackingCategory, EntityTrackingCategory.id == TrackingCategoryMapping.entity_category_id)
        .where(TrackingCategoryMapping.group_category_id.is_not(None),
               EntityTrackingCategory.deleted_at.is_(None), EntityTrackingCategory.status == "ACTIVE")
    )).all()
    opt_rows = (await s.execute(
        select(TrackingOptionMapping.entity_id, TrackingOptionMapping.group_option_id, TrackingOptionMapping.status)
        .join(EntityTrackingOption, EntityTrackingOption.id == TrackingOptionMapping.entity_option_id)
        .where(TrackingOptionMapping.group_option_id.is_not(None),
               EntityTrackingOption.deleted_at.is_(None), EntityTrackingOption.status == "ACTIVE")
    )).all()
    cat_state: dict[tuple, tuple[str, uuid.UUID]] = {}
    for eid, gid, status, local in cat_rows:
        if status == CONFIRMED:
            cat_state[(gid, eid)] = ("mapped", local)
        elif status == SUGGESTED and (gid, eid) not in cat_state:
            cat_state[(gid, eid)] = ("pending", local)
    opt_state: dict[tuple, str] = {}
    for eid, gid, status in opt_rows:
        if status == CONFIRMED:
            opt_state[(gid, eid)] = "mapped"
        elif status == SUGGESTED:
            opt_state.setdefault((gid, eid), "pending")

    rows = []
    for c in await _categories(s, workspace_id):
        if c.status != "active":
            continue
        cells, missing = {}, 0
        for e in entities:
            state, local = cat_state.get((c.id, e.id), ("gap", None))
            cells[str(e.id)] = {"state": state, "entity_category_id": str(local) if local else None}
            missing += state == "gap"
        options = []
        for o in await _options(s, c.id):
            if o.status != "active":
                continue
            ocells = {}
            for e in entities:
                cstate, local = cat_state.get((c.id, e.id), ("gap", None))
                if cstate != "mapped":
                    ocells[str(e.id)] = {"state": "no_category", "entity_category_id": None}
                else:
                    ocells[str(e.id)] = {"state": opt_state.get((o.id, e.id), "gap"),
                                         "entity_category_id": str(local)}
            options.append({"group_option": {"id": str(o.id), "name": o.name}, "cells": ocells,
                            "gaps": sum(1 for v in ocells.values() if v["state"] == "gap")})
        rows.append({"group_category": {"id": str(c.id), "name": c.name}, "cells": cells, "gaps": missing,
                     "options": options})
    return {"entities": [{"id": str(e.id), "name": e.name, "status": e.status} for e in entities],
            "categories": rows}
