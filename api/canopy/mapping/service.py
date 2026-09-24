"""Mapping lifecycle: generate suggestions, record human decisions, compute gaps.

Human decisions are never overwritten: regenerating suggestions only touches
accounts with no mapping row or a still-`suggested` one. The LLM call happens
between two short transactions, never inside one.
"""

import csv
import io
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert

from ..audit import service as audit
from ..core.db import unit_of_work
from ..core.errors import AppError, NotFound
from ..core.models_base import utcnow
from ..standard.models import GroupAccount
from ..sync.models import EntityAccount
from ..sync.service import live_accounts
from ..xero.models import Entity
from .matcher import EXACT, MANUAL, UNMATCHED, LocalAccount, Match, StandardAccount, match_accounts
from .models import AccountMapping
from .suggest import Complete, suggest

SUGGESTED, CONFIRMED, REJECTED = "suggested", "confirmed", "rejected"


@dataclass(frozen=True)
class SuggestResult:
    entity_id: uuid.UUID
    deterministic: int
    ai: int


async def generate_suggestions(
    workspace_id: uuid.UUID,
    entity_id: uuid.UUID,
    complete: Complete | None,
    *,
    refresh: bool = False,
) -> SuggestResult:
    """Suggest mappings for this org's unmapped accounts (and, with refresh=True,
    re-suggest ones still awaiting review). `complete=None` skips the AI pass."""
    async with unit_of_work(workspace_id=workspace_id) as s:
        standard = [
            StandardAccount(g.id, g.code, g.name, g.type, g.account_class)
            for g in await s.scalars(
                select(GroupAccount).where(GroupAccount.workspace_id == workspace_id, GroupAccount.status == "active")
            )
        ]
        existing = {
            m.entity_account_id: m.status
            for m in await s.scalars(select(AccountMapping).where(AccountMapping.entity_id == entity_id))
        }
        todo = [
            LocalAccount(a.id, a.code, a.name, a.type, a.account_class)
            for a in await live_accounts(s, entity_id)
            if a.id not in existing or (refresh and existing[a.id] == SUGGESTED)
        ]
    if not standard or not todo:
        return SuggestResult(entity_id, 0, 0)

    matches, remaining = match_accounts(todo, standard)
    if complete and remaining:
        ai_matches = await suggest(complete, remaining, standard)
    else:
        # Every live account must reach the review queue, even with AI switched off;
        # otherwise it silently drops out of the workflow and can never be decided.
        reason = "No deterministic match found. Choose the group account, or mark it local-only."
        ai_matches = [Match(a.id, None, UNMATCHED, 0.0, reason) for a in remaining]

    async with unit_of_work(workspace_id=workspace_id) as s:
        for m in [*matches, *ai_matches]:
            values = {
                "workspace_id": workspace_id, "entity_id": entity_id, "entity_account_id": m.local_id,
                "group_account_id": m.group_id, "status": SUGGESTED, "source": m.source,
                "confidence": m.confidence, "reasoning": m.reasoning, "updated_at": utcnow(),
            }
            stmt = insert(AccountMapping).values(**values)
            # Only replace rows that are still awaiting review; decisions stand.
            await s.execute(
                stmt.on_conflict_do_update(
                    index_elements=[AccountMapping.entity_account_id],
                    set_={
                        k: stmt.excluded[k]
                        for k in ("group_account_id", "source", "confidence", "reasoning", "updated_at")
                    },
                    where=AccountMapping.status == SUGGESTED,
                )
            )
    return SuggestResult(entity_id, len(matches), len(ai_matches))


def _as_dict(m: AccountMapping) -> dict:
    return {
        "id": str(m.id), "status": m.status, "source": m.source,
        "group_account_id": str(m.group_account_id) if m.group_account_id else None,
        "confidence": m.confidence, "reasoning": m.reasoning,
    }


async def decide(
    s, workspace_id: uuid.UUID, mapping_id: uuid.UUID, action: str, actor: uuid.UUID,
    group_account_id: uuid.UUID | None = None,
) -> AccountMapping:
    """confirm (as suggested) | reject | assign (to a chosen group account, or
    None = deliberately local-only). Every decision is audited."""
    m = await s.get(AccountMapping, mapping_id)
    if m is None:
        raise NotFound("Mapping not found.")
    before = _as_dict(m)
    if action == "confirm":
        m.status = CONFIRMED
    elif action == "reject":
        m.status = REJECTED
    elif action == "assign":
        if group_account_id is not None and await s.get(GroupAccount, group_account_id) is None:
            raise NotFound("Group account not found.")
        m.group_account_id, m.status, m.source, m.confidence = group_account_id, CONFIRMED, MANUAL, 1.0
        m.reasoning = "Assigned by a person." if group_account_id else "Marked local-only by a person."
    else:
        raise AppError(f"Unknown action {action!r}.")
    m.decided_by, m.decided_at = actor, utcnow()
    await audit.record(s, f"mapping.{action}", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="account_mapping", target_id=m.id, before=before, after=_as_dict(m))
    return m


async def confirm_exact(s, workspace_id: uuid.UUID, entity_id: uuid.UUID, actor: uuid.UUID) -> int:
    """Bulk-confirm the exact (same code and name) suggestions for one org."""
    rows = list(await s.scalars(
        select(AccountMapping).where(
            AccountMapping.entity_id == entity_id, AccountMapping.status == SUGGESTED,
            AccountMapping.source == EXACT,
        )
    ))
    now = utcnow()
    for m in rows:
        m.status, m.decided_by, m.decided_at = CONFIRMED, actor, now
    if rows:
        await audit.record(s, "mapping.bulk_confirm_exact", workspace_id=workspace_id, actor_user_id=actor,
                           target_type="entity", target_id=entity_id, after={"confirmed": len(rows)})
    return len(rows)


async def entity_mappings(s, entity_id: uuid.UUID) -> list[dict]:
    """Every live account in the org with its mapping (if any), for review."""
    stmt = (
        select(EntityAccount, AccountMapping, GroupAccount)
        .outerjoin(AccountMapping, AccountMapping.entity_account_id == EntityAccount.id)
        .outerjoin(GroupAccount, GroupAccount.id == AccountMapping.group_account_id)
        .where(EntityAccount.entity_id == entity_id, EntityAccount.deleted_at.is_(None),
               EntityAccount.status == "ACTIVE")
        .order_by(EntityAccount.code.nulls_last(), EntityAccount.name)
    )
    out = []
    for acct, m, g in (await s.execute(stmt)).all():
        out.append({
            "account": {"id": str(acct.id), "code": acct.code, "name": acct.name, "type": acct.type},
            "mapping": _as_dict(m) if m else None,
            "group_account": {"id": str(g.id), "code": g.code, "name": g.name} if g else None,
        })
    return out


async def gaps(s, workspace_id: uuid.UUID) -> dict:
    """Matrix of group accounts × active orgs: how many live org accounts are
    CONFIRMED against each group account. 0 = a gap; also reports pending review."""
    entities = list(await s.scalars(
        select(Entity).where(Entity.workspace_id == workspace_id, Entity.status == "active").order_by(Entity.name)
    ))
    standard = list(await s.scalars(
        select(GroupAccount).where(GroupAccount.workspace_id == workspace_id, GroupAccount.status == "active")
        .order_by(GroupAccount.code)
    ))
    counts = (
        await s.execute(
            select(AccountMapping.group_account_id, AccountMapping.entity_id, AccountMapping.status, func.count())
            .join(EntityAccount, and_(EntityAccount.id == AccountMapping.entity_account_id,
                                      EntityAccount.deleted_at.is_(None), EntityAccount.status == "ACTIVE"))
            .where(AccountMapping.group_account_id.is_not(None))
            .group_by(AccountMapping.group_account_id, AccountMapping.entity_id, AccountMapping.status)
        )
    ).all()
    cell: dict[tuple, dict] = {}
    for gid, eid, status, n in counts:
        cell.setdefault((gid, eid), {"confirmed": 0, "suggested": 0})
        if status in (CONFIRMED, SUGGESTED):
            cell[(gid, eid)][status] += n
    rows = []
    for g in standard:
        cells = {}
        for e in entities:
            c = cell.get((g.id, e.id), {"confirmed": 0, "suggested": 0})
            state = "mapped" if c["confirmed"] else ("pending" if c["suggested"] else "gap")
            cells[str(e.id)] = {"state": state, **c}
        rows.append({"group_account": {"id": str(g.id), "code": g.code, "name": g.name},
                     "cells": cells, "gaps": sum(1 for v in cells.values() if v["state"] == "gap")})
    return {
        "entities": [{"id": str(e.id), "name": e.name} for e in entities],
        "rows": rows,
    }


async def export_csv(s, workspace_id: uuid.UUID) -> str:
    """Confirmed mappings as CSV (org, local code/name, group code/name) — the
    shape consolidation tools import."""
    stmt = (
        select(Entity.name, EntityAccount.code, EntityAccount.name, GroupAccount.code, GroupAccount.name)
        .join(AccountMapping, AccountMapping.entity_id == Entity.id)
        .join(EntityAccount, EntityAccount.id == AccountMapping.entity_account_id)
        .outerjoin(GroupAccount, GroupAccount.id == AccountMapping.group_account_id)
        .where(AccountMapping.status == CONFIRMED, EntityAccount.deleted_at.is_(None))
        .order_by(Entity.name, EntityAccount.code)
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["organisation", "local_code", "local_name", "group_code", "group_name"])
    for row in (await s.execute(stmt)).all():
        w.writerow(["" if v is None else v for v in row])
    return buf.getvalue()
