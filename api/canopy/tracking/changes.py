"""Tracking-category change items: building them, checking them, and deciding
whether one only brings an org into line with the group standard (the test for
self-approval). Execution lives in changes/tracking_executor.py.
"""

from sqlalchemy import select

from ..core.errors import AppError, NotFound
from ..xero.models import Entity, XeroConnection
from ..xero.scopes import can_write
from . import preflight as tp
from .models import (
    EntityTrackingCategory,
    EntityTrackingOption,
    GroupTrackingCategory,
    GroupTrackingOption,
    TrackingCategoryMapping,
    TrackingOptionMapping,
)
from .service import CONFIRMED, active_option_names


async def org_tracking(s, entity: Entity) -> tp.OrgTracking:
    """The org's tracking as the checks see it: every category that still exists
    in Xero (archived included), with its options."""
    categories = list(await s.scalars(select(EntityTrackingCategory).where(
        EntityTrackingCategory.entity_id == entity.id, EntityTrackingCategory.deleted_at.is_(None))))
    out = []
    for c in categories:
        options = await s.scalars(select(EntityTrackingOption).where(
            EntityTrackingOption.category_id == c.id, EntityTrackingOption.deleted_at.is_(None)))
        out.append(tp.OrgCategory(c.xero_category_id, c.name, c.status,
                                  tuple(tp.OrgOption(o.xero_option_id, o.name, o.status) for o in options)))
    conn = await s.get(XeroConnection, entity.connection_id)
    return tp.OrgTracking(entity.name, out, bool(conn and conn.status == "active" and can_write(conn.scopes)))


def _find_category(org: tp.OrgTracking, xero_id: str | None) -> tp.OrgCategory | None:
    return next((c for c in org.categories if c.xero_category_id == xero_id), None) if xero_id else None


async def targets(s, item, org: tp.OrgTracking) -> tuple[tp.OrgCategory | None, tp.OrgOption | None]:
    """The item's target category/option in `org` (None when gone from Xero)."""
    if item.operation == tp.CREATE_CATEGORY:
        return _find_category(org, item.created_xero_id), None
    category = option = None
    if item.entity_tracking_category_id:
        row = await s.get(EntityTrackingCategory, item.entity_tracking_category_id)
        category = _find_category(org, row.xero_category_id) if row and row.deleted_at is None else None
    if item.entity_tracking_option_id:
        row = await s.get(EntityTrackingOption, item.entity_tracking_option_id)
        if row and row.deleted_at is None and category:
            option = next((o for o in category.options if o.xero_option_id == row.xero_option_id), None)
    return category, option


async def run_preflight(s, item, entity: Entity) -> list[str]:
    org = await org_tracking(s, entity)
    category, option = await targets(s, item, org)
    return tp.check(item.operation, item.payload, org, category=category, option=option)


async def prepare(s, entity: Entity, operation: str, spec: dict) -> dict:
    """Column values (including payload) for a new tracking item. Creates from a
    group category or option take their payload from the standard."""
    payload = dict(spec.get("payload") or {})
    out = {"payload": payload}
    if operation == tp.CREATE_CATEGORY:
        if spec.get("group_tracking_category_id"):
            g = await s.get(GroupTrackingCategory, spec["group_tracking_category_id"])
            if g is None:
                raise NotFound("Group tracking category not found.")
            out["group_tracking_category_id"] = g.id
            out["payload"] = {"name": g.name, "options": await active_option_names(s, g.id), **payload}
        return out

    if operation in (tp.UPDATE_OPTION, tp.ARCHIVE_OPTION):
        option = await s.get(EntityTrackingOption, spec.get("entity_tracking_option_id")) \
            if spec.get("entity_tracking_option_id") else None
        if option is None or option.entity_id != entity.id:
            raise NotFound("Tracking option not found in that organisation.")
        out["entity_tracking_option_id"] = option.id
        out["entity_tracking_category_id"] = option.category_id
    else:
        category = await s.get(EntityTrackingCategory, spec.get("entity_tracking_category_id")) \
            if spec.get("entity_tracking_category_id") else None
        if category is None or category.entity_id != entity.id:
            raise NotFound("Tracking category not found in that organisation.")
        out["entity_tracking_category_id"] = category.id

    if operation == tp.CREATE_OPTION and spec.get("group_tracking_option_id"):
        g = await s.get(GroupTrackingOption, spec["group_tracking_option_id"])
        if g is None:
            raise NotFound("Group tracking option not found.")
        out["group_tracking_option_id"] = g.id
        out["payload"] = {"name": g.name, **payload}
    if operation in (tp.ARCHIVE_CATEGORY, tp.ARCHIVE_OPTION):
        out["payload"] = {}
    if operation not in tp.OPERATIONS:
        raise AppError(f"Unknown operation {operation!r}.")
    return out


async def _confirmed_category(s, entity_category_id) -> GroupTrackingCategory | None:
    m = await s.scalar(select(TrackingCategoryMapping).where(
        TrackingCategoryMapping.entity_category_id == entity_category_id))
    if m is None or m.status != CONFIRMED or m.group_category_id is None:
        return None
    g = await s.get(GroupTrackingCategory, m.group_category_id)
    return g if g and g.status == "active" else None


async def not_standard(s, item) -> str | None:
    """Why this item does more than bring its org into line with the group's
    tracking standard, or None when that's all it does:
    - create a category: a group category, with exactly its name and options;
    - create an option: a group option, in the org category confirmed against
      that option's group category, with exactly its name;
    - rename: to the name of the confirmed group category/option;
    - never an archive."""
    op = item.operation
    if op in (tp.ARCHIVE_CATEGORY, tp.ARCHIVE_OPTION):
        return "archives a tracking " + ("category" if op == tp.ARCHIVE_CATEGORY else "option")

    if op == tp.CREATE_CATEGORY:
        g = await s.get(GroupTrackingCategory, item.group_tracking_category_id) \
            if item.group_tracking_category_id else None
        if g is None or g.status != "active":
            return "creates a tracking category that isn't in the group standard"
        if item.payload != {"name": g.name, "options": await active_option_names(s, g.id)}:
            return "creates a tracking category that differs from the group standard"
        return None

    if op == tp.CREATE_OPTION:
        g = await s.get(GroupTrackingOption, item.group_tracking_option_id) if item.group_tracking_option_id else None
        if g is None or g.status != "active":
            return "adds a tracking option that isn't in the group standard"
        category = await _confirmed_category(s, item.entity_tracking_category_id)
        if category is None or category.id != g.category_id:
            return "adds a tracking option to a category that isn't confirmed against its group category"
        if item.payload != {"name": g.name}:
            return "adds a tracking option named differently from the group standard"
        return None

    if op == tp.UPDATE_CATEGORY:
        g = await _confirmed_category(s, item.entity_tracking_category_id)
        if g is None:
            return "renames a tracking category that isn't confirmed against a group category"
        return None if item.payload == {"name": g.name} else \
            "renames a tracking category to something other than its group name"

    if op == tp.UPDATE_OPTION:
        m = await s.scalar(select(TrackingOptionMapping).where(
            TrackingOptionMapping.entity_option_id == item.entity_tracking_option_id))
        g = await s.get(GroupTrackingOption, m.group_option_id) \
            if m and m.status == CONFIRMED and m.group_option_id else None
        if g is None or g.status != "active":
            return "renames a tracking option that isn't confirmed against a group option"
        return None if item.payload == {"name": g.name} else \
            "renames a tracking option to something other than its group name"

    return f"does something unrecognised ({op})"
