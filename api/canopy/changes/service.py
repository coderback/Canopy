"""Change sets: authoring, preflight, approval with separation of duties.

Permissions are enforced here, not in the UI:
- authors: owner, admin, preparer;  deciders: owner, admin, approver.
- nobody decides a set they authored. The one exception is self-approval, for a
  group with a single approver, and it is narrow (see `self_approval_blocker`):
  the workspace allows it, nobody else can approve, every item only brings an org
  into line with the group standard, and the author says why. Such a set is
  recorded as `self_approved` and waits in a review queue until someone else
  reviews it.
- nothing is authored or approved while the workspace has changes switched off.
Every transition writes an audit event in the same transaction.
"""

import uuid

from sqlalchemy import func, select

from ..audit import service as audit
from ..core.errors import AppError, Conflict, Forbidden, NotFound
from ..core.models_base import utcnow
from ..mapping.models import AccountMapping
from ..standard.models import GroupAccount
from ..sync.models import EntityAccount, EntityTaxRate
from ..tenancy.models import Membership, Role, Workspace
from ..xero.models import Entity, XeroConnection
from ..xero.scopes import can_write
from . import preflight as pf
from .models import ChangeItem, ChangeSet

AUTHORS = (Role.OWNER, Role.ADMIN, Role.PREPARER)
DECIDERS = (Role.OWNER, Role.ADMIN, Role.APPROVER)
EDITABLE = ("draft",)
TERMINAL_ITEM = ("succeeded", "failed", "skipped")


# ---- reading org state for preflight -----------------------------------------


def org_account(a: EntityAccount) -> pf.OrgAccount:
    return pf.OrgAccount(a.xero_account_id, a.code, a.name, a.type, a.account_class, a.status,
                         a.system_account, a.tax_type, a.description)


async def org_state(s, entity: Entity) -> pf.OrgState:
    accounts = await s.scalars(
        select(EntityAccount).where(EntityAccount.entity_id == entity.id, EntityAccount.deleted_at.is_(None))
    )
    rates = await s.scalars(select(EntityTaxRate).where(EntityTaxRate.entity_id == entity.id))
    conn = await s.get(XeroConnection, entity.connection_id)
    return pf.OrgState(
        name=entity.name,
        accounts=[org_account(a) for a in accounts],
        tax_rates=[
            pf.OrgTaxRate(t.tax_type, t.status, {
                "revenue": t.can_apply_to_revenue, "expenses": t.can_apply_to_expenses,
                "assets": t.can_apply_to_assets, "liabilities": t.can_apply_to_liabilities,
                "equity": t.can_apply_to_equity,
            })
            for t in rates
        ],
        can_write=bool(conn and conn.status == "active" and can_write(conn.scopes)),
    )


async def run_preflight(s, item: ChangeItem) -> list[str]:
    entity = await s.get(Entity, item.entity_id)
    if entity is None or entity.status != "active":
        return ["That organisation is no longer connected."]
    target = await s.get(EntityAccount, item.entity_account_id) if item.entity_account_id else None
    if target is not None and target.deleted_at is not None:
        target = None
    return pf.check(item.operation, item.payload, org_account(target) if target else None, await org_state(s, entity))


# ---- guards ----------------------------------------------------------------------


async def _workspace(s, workspace_id: uuid.UUID) -> Workspace:
    ws = await s.get(Workspace, workspace_id)
    if not ws.changes_enabled:
        raise Conflict("Changes to Xero are switched off for this workspace.", code="changes_disabled")
    return ws


def _require(role: Role, allowed: tuple, what: str) -> None:
    if role not in allowed:
        raise Forbidden(f"Your role can't {what}.")


async def _set(s, set_id: uuid.UUID) -> ChangeSet:
    cs = await s.get(ChangeSet, set_id)
    if cs is None:
        raise NotFound("Change not found.")
    return cs


def _editable(cs: ChangeSet, actor: uuid.UUID, role: Role) -> None:
    if cs.status not in EDITABLE:
        raise Conflict(f"This change is {cs.status} and can no longer be edited.")
    if cs.author_id != actor and role not in (Role.OWNER, Role.ADMIN):
        raise Forbidden("Only the author (or an admin) can edit a draft.")


# ---- authoring -------------------------------------------------------------------


async def create_set(s, workspace_id, actor, role, title: str, reason: str = "") -> ChangeSet:
    await _workspace(s, workspace_id)
    _require(role, AUTHORS, "propose changes")
    cs = ChangeSet(workspace_id=workspace_id, title=title.strip() or "Untitled change", reason=reason,
                   author_id=actor)
    s.add(cs)
    await s.flush()
    await audit.record(s, "change.created", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="change_set", target_id=cs.id, after={"title": cs.title})
    return cs


async def _default_tax_type(s, group: GroupAccount, entity_id: uuid.UUID) -> str | None:
    """The tax type the group account carries in the org it was seeded from, if that
    tax type also exists, is active, and fits the class in the target org."""
    if not group.source_entity_id:
        return None
    source = await s.scalar(select(EntityAccount).where(
        EntityAccount.entity_id == group.source_entity_id, EntityAccount.code == group.code,
        EntityAccount.deleted_at.is_(None),
    ))
    if source is None or not source.tax_type:
        return None
    rate = await s.scalar(select(EntityTaxRate).where(
        EntityTaxRate.entity_id == entity_id, EntityTaxRate.tax_type == source.tax_type,
    ))
    if rate is None or rate.status != "ACTIVE":
        return None
    flag = pf.CLASS_TAX_FLAG.get(group.account_class or "")
    applies = getattr(rate, f"can_apply_to_{flag}", None) if flag else None
    return None if applies is False else source.tax_type


async def _create_defaults(s, group: GroupAccount, entity_id: uuid.UUID) -> dict:
    """The payload that creates `group` in an org exactly as the standard defines it."""
    defaults = {"code": group.code, "name": group.name, "type": group.type, "description": group.description,
                "tax_type": await _default_tax_type(s, group, entity_id)}
    return {k: v for k, v in defaults.items() if v is not None}


async def add_item(s, workspace_id, actor, role, set_id, spec: dict) -> ChangeItem:
    """spec: {operation, entity_id, entity_account_id?, group_account_id?, payload?}.
    For a create from a group account, the payload defaults to the group account's
    code/name/type/description and the source org's tax type where valid."""
    await _workspace(s, workspace_id)
    cs = await _set(s, set_id)
    _editable(cs, actor, role)
    op = spec["operation"]
    if op not in (pf.CREATE, pf.UPDATE, pf.ARCHIVE):
        raise AppError(f"Unknown operation {op!r}.")
    entity = await s.get(Entity, spec["entity_id"])
    if entity is None:
        raise NotFound("Organisation not found.")
    payload = dict(spec.get("payload") or {})
    group_id = spec.get("group_account_id")
    account_id = spec.get("entity_account_id")

    if op == pf.CREATE and group_id:
        group = await s.get(GroupAccount, group_id)
        if group is None:
            raise NotFound("Group account not found.")
        payload = {**await _create_defaults(s, group, entity.id), **payload}
    if op in (pf.UPDATE, pf.ARCHIVE):
        acct = await s.get(EntityAccount, account_id) if account_id else None
        if acct is None or acct.entity_id != entity.id:
            raise NotFound("Account not found in that organisation.")
    if op == pf.ARCHIVE:
        payload = {}

    item = ChangeItem(workspace_id=workspace_id, change_set_id=cs.id, entity_id=entity.id, operation=op,
                      entity_account_id=account_id, group_account_id=group_id, payload=payload)
    s.add(item)
    await s.flush()
    problems = await run_preflight(s, item)
    item.preflight_status, item.preflight_messages = ("blocked" if problems else "ok"), problems
    return item


async def edit_item(s, workspace_id, actor, role, item_id, payload: dict) -> ChangeItem:
    await _workspace(s, workspace_id)
    item = await s.get(ChangeItem, item_id)
    if item is None:
        raise NotFound("Item not found.")
    _editable(await _set(s, item.change_set_id), actor, role)
    if item.operation == pf.ARCHIVE:
        raise AppError("An archive has nothing to edit.")
    item.payload = {**item.payload, **payload}
    problems = await run_preflight(s, item)
    item.preflight_status, item.preflight_messages = ("blocked" if problems else "ok"), problems
    return item


async def remove_item(s, workspace_id, actor, role, item_id) -> None:
    item = await s.get(ChangeItem, item_id)
    if item is None:
        raise NotFound("Item not found.")
    _editable(await _set(s, item.change_set_id), actor, role)
    await s.delete(item)


async def items(s, set_id) -> list[ChangeItem]:
    return list(await s.scalars(
        select(ChangeItem).where(ChangeItem.change_set_id == set_id).order_by(ChangeItem.created_at)
    ))


# ---- lifecycle ---------------------------------------------------------------------


async def submit(s, workspace_id, actor, role, set_id) -> ChangeSet:
    await _workspace(s, workspace_id)
    cs = await _set(s, set_id)
    _editable(cs, actor, role)
    its = await items(s, cs.id)
    if not its:
        raise AppError("Add at least one change before submitting.")
    blocked = []
    for item in its:
        problems = await run_preflight(s, item)
        item.preflight_status, item.preflight_messages = ("blocked" if problems else "ok"), problems
        if problems:
            blocked.append(item)
    if blocked:
        raise AppError(f"{len(blocked)} item(s) can't be made as they stand; fix or remove them first.",
                       code="preflight_blocked")
    cs.status, cs.submitted_at = "submitted", utcnow()
    await audit.record(s, "change.submitted", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="change_set", target_id=cs.id, after={"items": len(its)})
    return cs


async def approvers(s, workspace_id, excluding: uuid.UUID | None = None) -> int:
    """How many members can approve changes, optionally not counting one of them."""
    query = select(func.count()).select_from(Membership).where(
        Membership.workspace_id == workspace_id, Membership.role.in_(DECIDERS)
    )
    if excluding is not None:
        query = query.where(Membership.user_id != excluding)
    return await s.scalar(query)


async def _not_standard(s, item: ChangeItem) -> str | None:
    """Why this item does more than bring its org into line with the group standard,
    or None when that's all it does. Only such items can be self-approved:
    - create: a group account, with exactly the details the standard gives it;
    - update: a rename to the name of the group account it's confirmed against;
    - never an archive, and never any other edit (codes included)."""
    if item.operation == pf.ARCHIVE:
        return "archives an account"
    if item.operation == pf.CREATE:
        group = await s.get(GroupAccount, item.group_account_id) if item.group_account_id else None
        if group is None or group.status != "active":
            return "creates an account that isn't in the group standard"
        if item.payload != await _create_defaults(s, group, item.entity_id):
            return "creates an account with details changed from the group standard"
        return None
    mapping = await s.scalar(select(AccountMapping).where(AccountMapping.entity_account_id == item.entity_account_id))
    group = (
        await s.get(GroupAccount, mapping.group_account_id)
        if mapping and mapping.status == "confirmed" and mapping.group_account_id else None
    )
    if group is None or group.status != "active":
        return "edits an account that isn't confirmed against a group account"
    if item.payload != {"name": group.name}:
        return "makes an edit other than renaming to the group account's name"
    return None


async def self_approval_blocker(s, ws: Workspace, cs: ChangeSet, role: Role) -> str | None:
    """Why the author of `cs` can't approve it themselves, or None if they can."""
    if role not in DECIDERS:
        return "Your role can't approve changes."
    if not ws.allow_self_approval:
        return "Self-approval is off for this workspace."
    others = await approvers(s, ws.id, excluding=cs.author_id)
    if others:
        return f"{others} other {'person' if others == 1 else 'people'} can approve changes here."
    for item in await items(s, cs.id):
        reason = await _not_standard(s, item)
        if reason:
            entity = await s.get(Entity, item.entity_id)
            return (f"The change in {entity.name} {reason}; only changes that bring an org into line with "
                    "the group standard can be self-approved.")
    return None


async def decide(s, workspace_id, actor, role, set_id, approve: bool, note: str | None) -> tuple[ChangeSet, list]:
    """Returns the set and, when approved, the (item, tenant) pairs to execute; the
    caller enqueues them after this transaction commits."""
    ws = await _workspace(s, workspace_id)
    _require(role, DECIDERS, "approve or reject changes")
    cs = await _set(s, set_id)
    if cs.status != "submitted":
        raise Conflict(f"This change is {cs.status}; only submitted changes can be decided.")
    note = (note or "").strip() or None
    self_decision = cs.author_id == actor
    if self_decision and not approve:
        raise Conflict("You proposed this change; cancel it instead of rejecting it.", code="separation_of_duties")
    if self_decision:
        blocker = await self_approval_blocker(s, ws, cs, role)
        if blocker:
            raise Forbidden(f"You can't approve a change you proposed. {blocker}", code="separation_of_duties")
        if not note:
            raise AppError("Say why you're approving your own change; it's kept for review.", code="note_required")
    if not approve and not note:
        raise AppError("Say why you're rejecting it.", code="note_required")
    cs.status = "approved" if approve else "rejected"
    cs.decided_by, cs.decided_at, cs.decision_note = actor, utcnow(), note
    cs.self_approved = bool(approve and self_decision)
    await audit.record(s, "change.approved" if approve else "change.rejected", workspace_id=workspace_id,
                       actor_user_id=actor, target_type="change_set", target_id=cs.id,
                       after={"note": note, "self_approved": cs.self_approved})
    return cs, (await runnable(s, cs.id) if approve else [])


async def review(s, workspace_id, actor, role, set_id, note: str | None) -> ChangeSet:
    """Clears a self-approved set from the review queue. Deliberately not gated on
    `changes_enabled`: looking back at what was written is always allowed."""
    _require(role, DECIDERS, "review changes")
    cs = await _set(s, set_id)
    if not cs.self_approved:
        raise Conflict("Only self-approved changes go to review.")
    if cs.reviewed_at is not None:
        raise Conflict("This change has already been reviewed.")
    if cs.author_id == actor:
        raise Forbidden("Someone other than the author has to review a self-approved change.",
                        code="separation_of_duties")
    cs.reviewed_by, cs.reviewed_at, cs.review_note = actor, utcnow(), (note or "").strip() or None
    await audit.record(s, "change.reviewed", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="change_set", target_id=cs.id, after={"note": cs.review_note})
    return cs


async def cancel(s, workspace_id, actor, role, set_id) -> ChangeSet:
    cs = await _set(s, set_id)
    if cs.status not in ("draft", "submitted"):
        raise Conflict(f"A {cs.status} change can't be cancelled.")
    if cs.author_id != actor and role not in (Role.OWNER, Role.ADMIN):
        raise Forbidden("Only the author (or an admin) can cancel a change.")
    cs.status = "cancelled"
    await audit.record(s, "change.cancelled", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="change_set", target_id=cs.id)
    return cs


async def retry_failed(s, workspace_id, actor, role, set_id) -> list:
    """Re-run failed items as a NEW attempt (new idempotency key), so Xero's cached
    failure isn't simply replayed. The original approval stands."""
    await _workspace(s, workspace_id)
    _require(role, DECIDERS, "retry changes")
    cs = await _set(s, set_id)
    if cs.status not in ("partial", "failed"):
        raise Conflict("Only a partially failed or failed change can be retried.")
    retried = 0
    for item in await items(s, cs.id):
        if item.status == "failed":
            item.status, item.error, item.attempt = "pending", None, item.attempt + 1
            retried += 1
    cs.status = "executing"
    await audit.record(s, "change.retried", workspace_id=workspace_id, actor_user_id=actor,
                       target_type="change_set", target_id=cs.id, after={"items": retried})
    await s.flush()
    return await runnable(s, cs.id)


async def runnable(s, set_id) -> list[tuple[uuid.UUID, str]]:
    """(item id, tenant id) for every item waiting to run, for the job queue."""
    rows = await s.execute(
        select(ChangeItem.id, Entity.tenant_id)
        .join(Entity, Entity.id == ChangeItem.entity_id)
        .where(ChangeItem.change_set_id == set_id, ChangeItem.status == "pending")
    )
    return [(i, t) for i, t in rows.all()]


def roll_up(item_statuses: list[str]) -> str | None:
    """The set's status once every item has finished, else None."""
    if not item_statuses or any(st not in TERMINAL_ITEM for st in item_statuses):
        return None
    ok = [st for st in item_statuses if st == "succeeded"]
    if len(ok) == len(item_statuses):
        return "completed"
    return "partial" if ok else "failed"

