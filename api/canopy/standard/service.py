"""The group standard chart: seed from an org, import from CSV, edit."""

import csv
import io
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import service as audit
from ..core.errors import AppError, Conflict, NotFound
from ..mapping.matcher import TYPE_CLASS, account_class
from ..sync.service import live_accounts
from ..xero.models import Entity
from .models import GroupAccount

CLASSES = {"ASSET", "EQUITY", "EXPENSE", "LIABILITY", "REVENUE"}


def as_dict(g: GroupAccount) -> dict:
    return {
        "id": str(g.id), "code": g.code, "name": g.name, "type": g.type,
        "account_class": g.account_class, "description": g.description, "status": g.status,
    }


async def _count(s: AsyncSession, workspace_id: uuid.UUID) -> int:
    return await s.scalar(
        select(func.count()).select_from(GroupAccount).where(GroupAccount.workspace_id == workspace_id)
    ) or 0


async def seed_from_entity(
    s: AsyncSession, workspace_id: uuid.UUID, entity_id: uuid.UUID, actor: uuid.UUID
) -> int:
    """Copy an org's active, coded accounts into an EMPTY standard.
    Accounts with no code (typically bank accounts) are skipped: the standard is
    keyed by code. Refuses if a standard already exists, so it can't clobber edits."""
    if await _count(s, workspace_id):
        raise Conflict("The group standard already has accounts; edit it instead of re-seeding.")
    entity = await s.get(Entity, entity_id)
    if entity is None:
        raise NotFound("Entity not found.")
    accounts = [a for a in await live_accounts(s, entity_id) if a.code]
    if not accounts:
        raise AppError("That org has no synced accounts yet. Wait for its first sync to finish.")
    for a in accounts:
        s.add(
            GroupAccount(
                workspace_id=workspace_id, code=a.code, name=a.name, type=a.type,
                account_class=account_class(a.type, a.account_class) or "EXPENSE",
                description=a.description, source_entity_id=entity_id,
            )
        )
    await audit.record(
        s, "standard.seeded", workspace_id=workspace_id, actor_user_id=actor,
        target_type="entity", target_id=entity_id, after={"accounts": len(accounts), "entity": entity.name},
    )
    return len(accounts)


def parse_csv(content: bytes) -> list[dict]:
    """Rows of code,name,type[,description]. Errors name the row so they're fixable."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("CSV must be UTF-8.") from exc
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.strip().lower() for f in reader.fieldnames or []}
    missing = {"code", "name", "type"} - fields
    if missing:
        raise AppError(f"CSV is missing column(s): {', '.join(sorted(missing))}.")
    rows, seen = [], set()
    for n, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        code, name, type_ = row["code"], row["name"], row["type"].upper()
        if not (code and name and type_):
            raise AppError(f"Row {n}: code, name and type are all required.")
        if type_ not in TYPE_CLASS:
            raise AppError(f"Row {n}: unknown Xero account type {type_!r}.")
        if code in seen:
            raise AppError(f"Row {n}: duplicate code {code}.")
        seen.add(code)
        rows.append({"code": code, "name": name, "type": type_,
                     "account_class": TYPE_CLASS[type_], "description": row.get("description") or None})
    if not rows:
        raise AppError("CSV has no rows.")
    return rows


async def import_csv(s: AsyncSession, workspace_id: uuid.UUID, content: bytes, actor: uuid.UUID) -> int:
    if await _count(s, workspace_id):
        raise Conflict("The group standard already has accounts; edit it instead of re-importing.")
    rows = parse_csv(content)
    for r in rows:
        s.add(GroupAccount(workspace_id=workspace_id, **r))
    await audit.record(s, "standard.imported", workspace_id=workspace_id, actor_user_id=actor,
                       after={"accounts": len(rows)})
    return len(rows)


async def create_account(s: AsyncSession, workspace_id: uuid.UUID, data: dict, actor: uuid.UUID) -> GroupAccount:
    type_ = data["type"].upper()
    if type_ not in TYPE_CLASS:
        raise AppError(f"Unknown Xero account type {type_!r}.")
    exists = await s.scalar(
        select(GroupAccount.id).where(GroupAccount.workspace_id == workspace_id, GroupAccount.code == data["code"])
    )
    if exists:
        raise Conflict(f"Group code {data['code']} already exists.")
    g = GroupAccount(workspace_id=workspace_id, code=data["code"], name=data["name"], type=type_,
                     account_class=TYPE_CLASS[type_], description=data.get("description"))
    s.add(g)
    await s.flush()
    await audit.record(s, "standard.account_created", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="group_account", target_id=g.id, after=as_dict(g))
    return g


async def update_account(
    s: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID, changes: dict, actor: uuid.UUID
) -> GroupAccount:
    g = await s.get(GroupAccount, account_id)
    if g is None:
        raise NotFound("Group account not found.")
    before = as_dict(g)
    if "name" in changes and changes["name"]:
        g.name = changes["name"]
    if "description" in changes:
        g.description = changes["description"]
    if "status" in changes and changes["status"] in ("active", "archived"):
        g.status = changes["status"]
    if "type" in changes and changes["type"]:
        type_ = changes["type"].upper()
        if type_ not in TYPE_CLASS:
            raise AppError(f"Unknown Xero account type {type_!r}.")
        g.type, g.account_class = type_, TYPE_CLASS[type_]
    await audit.record(s, "standard.account_updated", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="group_account", target_id=g.id, before=before, after=as_dict(g))
    return g


async def list_accounts(s: AsyncSession, workspace_id: uuid.UUID) -> list[GroupAccount]:
    result = await s.scalars(
        select(GroupAccount).where(GroupAccount.workspace_id == workspace_id).order_by(GroupAccount.code)
    )
    return list(result)
