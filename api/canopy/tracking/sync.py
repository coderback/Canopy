"""Mirror an org's tracking categories and options.

Always a full read (`includeArchived=true`): an org has at most four categories,
so it's one small call, and archived ones matter (they count towards Xero's
limit and block reusing their name). Unlike accounts, an org may legitimately
have no tracking categories, so an empty response does mark the mirror deleted.
Deletion is soft (`deleted_at`), so mappings and history survive.
"""

import uuid

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from ..core.models_base import utcnow
from .models import EntityTrackingCategory, EntityTrackingOption

DELETED = "DELETED"


def _status(x: dict) -> str:
    return (x.get("Status") or "ACTIVE").upper()


async def upsert_option(s, workspace_id: uuid.UUID, entity_id: uuid.UUID, category_id: uuid.UUID, o: dict,
                        now=None) -> uuid.UUID:
    row = {"workspace_id": workspace_id, "entity_id": entity_id, "category_id": category_id,
           "xero_option_id": o["TrackingOptionID"], "name": o.get("Name") or "", "status": _status(o),
           "deleted_at": (now or utcnow()) if _status(o) == DELETED else None, "synced_at": now or utcnow()}
    stmt = insert(EntityTrackingOption).values(**row)
    return await s.scalar(stmt.on_conflict_do_update(
        index_elements=[EntityTrackingOption.entity_id, EntityTrackingOption.xero_option_id],
        set_={k: stmt.excluded[k] for k in ("category_id", "name", "status", "deleted_at", "synced_at")},
    ).returning(EntityTrackingOption.id))


async def upsert_category(s, workspace_id: uuid.UUID, entity_id: uuid.UUID, c: dict, now=None) -> uuid.UUID:
    """Writes the category and any options in the payload; returns its local id.
    Also used after a change, with Xero's response."""
    now = now or utcnow()
    row = {"workspace_id": workspace_id, "entity_id": entity_id, "xero_category_id": c["TrackingCategoryID"],
           "name": c.get("Name") or "", "status": _status(c),
           "deleted_at": now if _status(c) == DELETED else None, "synced_at": now}
    stmt = insert(EntityTrackingCategory).values(**row)
    category_id = await s.scalar(stmt.on_conflict_do_update(
        index_elements=[EntityTrackingCategory.entity_id, EntityTrackingCategory.xero_category_id],
        set_={k: stmt.excluded[k] for k in ("name", "status", "deleted_at", "synced_at")},
    ).returning(EntityTrackingCategory.id))
    for o in c.get("Options") or []:
        if o.get("TrackingOptionID"):
            await upsert_option(s, workspace_id, entity_id, category_id, o, now)
    return category_id


async def write_tracking(s, workspace_id: uuid.UUID, entity_id: uuid.UUID, categories: list[dict], now) -> int:
    """Full mirror of the org's tracking. Returns how many categories were seen."""
    seen_categories, seen_options = [], []
    for c in categories:
        if not c.get("TrackingCategoryID"):
            continue
        await upsert_category(s, workspace_id, entity_id, c, now)
        seen_categories.append(c["TrackingCategoryID"])
        seen_options += [o["TrackingOptionID"] for o in c.get("Options") or [] if o.get("TrackingOptionID")]
    await s.execute(
        update(EntityTrackingCategory)
        .where(EntityTrackingCategory.entity_id == entity_id, EntityTrackingCategory.deleted_at.is_(None),
               EntityTrackingCategory.xero_category_id.not_in(seen_categories))
        .values(deleted_at=now)
    )
    await s.execute(
        update(EntityTrackingOption)
        .where(EntityTrackingOption.entity_id == entity_id, EntityTrackingOption.deleted_at.is_(None),
               EntityTrackingOption.xero_option_id.not_in(seen_options))
        .values(deleted_at=now)
    )
    return len(seen_categories)
