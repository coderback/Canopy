"""Everything under /workspaces/{workspace_id}. Role checks per route:
viewers read; owners/admins connect orgs, manage members, edit the standard
and decide mappings."""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select

from ..audit import service as audit
from ..audit.models import AuditEvent
from ..auth import service as auth_service
from ..auth.models import User
from ..core.config import get_settings
from ..core.errors import AppError, Conflict, NotFound
from ..core.models_base import utcnow
from ..core.security import hash_token, new_token
from ..jobs.app import enqueue_suggest, enqueue_sync
from ..mapping import service as mapping
from ..standard import service as standard
from ..sync.service import FULL, INCREMENTAL
from ..tenancy.models import Invitation, Membership, Role
from ..tenancy.models import Workspace as WorkspaceRow
from ..xero import connections
from ..xero.models import Entity, XeroConnection
from ..xero.oauth import XeroIdentityClient
from ..xero.scopes import can_write
from . import schemas as S
from .deps import ADMINS, Workspace, WorkspaceContext, require_role
from .routes_auth import get_identity_client

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["workspace"])

Admin = require_role(*ADMINS)
INVITE_TTL = timedelta(days=7)


# ---- members & invitations -------------------------------------------------


@router.get("/members", response_model=list[S.MemberOut])
async def members(ctx: WorkspaceContext = Workspace):
    rows = (await ctx.session.execute(
        select(Membership, User).join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == ctx.workspace_id).order_by(User.name)
    )).all()
    return [{"id": str(m.id), "user_id": str(u.id), "name": u.name, "email": u.email, "role": m.role.value}
            for m, u in rows]


class RoleChange(BaseModel):
    role: Role


@router.patch("/members/{membership_id}", response_model=S.RoleOut)
async def change_role(membership_id: uuid.UUID, body: RoleChange, ctx: WorkspaceContext = Admin):
    m = await ctx.session.get(Membership, membership_id)
    if m is None or m.workspace_id != ctx.workspace_id:
        raise NotFound("Member not found.")
    if m.role == Role.OWNER or body.role == Role.OWNER:
        raise AppError("Ownership can't be changed here.")
    before = m.role.value
    m.role = body.role
    await audit.record(ctx.session, "member.role_changed", workspace_id=ctx.workspace_id, actor_user_id=ctx.user_id,
                       target_type="membership", target_id=m.id, before={"role": before}, after={"role": m.role.value})
    return {"id": str(m.id), "role": m.role.value}


@router.delete("/members/{membership_id}", status_code=204)
async def remove_member(membership_id: uuid.UUID, ctx: WorkspaceContext = Admin):
    m = await ctx.session.get(Membership, membership_id)
    if m is None or m.workspace_id != ctx.workspace_id:
        raise NotFound("Member not found.")
    if m.role == Role.OWNER:
        raise AppError("The owner can't be removed.")
    await ctx.session.delete(m)
    await audit.record(ctx.session, "member.removed", workspace_id=ctx.workspace_id, actor_user_id=ctx.user_id,
                       target_type="membership", target_id=m.id, before={"user_id": str(m.user_id)})


class NewInvitation(BaseModel):
    email: EmailStr
    role: Role


@router.post("/invitations", status_code=201, response_model=S.InvitationCreated)
async def invite(body: NewInvitation, ctx: WorkspaceContext = Admin):
    if body.role == Role.OWNER:
        raise AppError("Invite as admin, then transfer ownership separately.")
    token = new_token()
    inv = Invitation(workspace_id=ctx.workspace_id, email=body.email.lower(), role=body.role,
                     token_hash=hash_token(token), invited_by=ctx.user_id, expires_at=utcnow() + INVITE_TTL)
    ctx.session.add(inv)
    await ctx.session.flush()
    await audit.record(ctx.session, "member.invited", workspace_id=ctx.workspace_id, actor_user_id=ctx.user_id,
                       target_type="invitation", target_id=inv.id, after={"email": inv.email, "role": inv.role.value})
    # The token is returned once for the admin to share; only its hash is stored.
    return {"id": str(inv.id), "token": token, "expires_at": inv.expires_at.isoformat()}


@router.get("/invitations", response_model=list[S.InvitationOut])
async def invitations(ctx: WorkspaceContext = Admin):
    rows = await ctx.session.scalars(
        select(Invitation).where(Invitation.workspace_id == ctx.workspace_id, Invitation.accepted_at.is_(None))
    )
    return [{"id": str(i.id), "email": i.email, "role": i.role.value, "expires_at": i.expires_at.isoformat()}
            for i in rows]


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(invitation_id: uuid.UUID, ctx: WorkspaceContext = Admin):
    await ctx.session.execute(
        delete(Invitation).where(Invitation.id == invitation_id, Invitation.workspace_id == ctx.workspace_id)
    )
    await audit.record(ctx.session, "member.invitation_revoked", workspace_id=ctx.workspace_id,
                       actor_user_id=ctx.user_id, target_type="invitation", target_id=invitation_id)


# ---- Xero connection & entities -------------------------------------------


@router.get("/xero/connect")
async def connect_xero(write: bool = False, ctx: WorkspaceContext = Admin):
    """Connect (or reconnect) orgs. Read-only while changes are off; once they're
    on, every connect asks for write access too, because the grant is stored per
    Xero user: a read-only reconnect would otherwise drop write access for every
    org that user connected. Xero lets the user pick which orgs get the grant."""
    ws = await ctx.session.get(WorkspaceRow, ctx.workspace_id)
    if write and not ws.changes_enabled:
        raise Conflict("Turn on changes for this workspace before granting write access.", code="changes_disabled")
    scopes = get_settings().xero_write_scopes if ws.changes_enabled else None
    url = await auth_service.start_oauth(
        auth_service.CONNECT, user_id=ctx.user_id, workspace_id=ctx.workspace_id,
        redirect_to=f"/w/{ctx.workspace_id}" + ("/settings" if write else ""), scopes=scopes,
    )
    return RedirectResponse(url, status_code=303)


def _iso(dt):
    return dt.isoformat() if dt else None


def _entity(e: Entity, conn: XeroConnection | None) -> dict:
    return {
        "id": str(e.id), "name": e.name, "tenant_id": e.tenant_id, "status": e.status,
        "sync_status": e.sync_status, "sync_error": e.sync_error, "last_synced_at": _iso(e.last_synced_at),
        "can_write": bool(e.status == "active" and conn and conn.status == "active" and can_write(conn.scopes)),
        "status_reason": e.status_reason, "status_changed_at": _iso(e.status_changed_at),
        "purge_after": None if e.purged_at else _iso(e.purge_after), "purged_at": _iso(e.purged_at),
    }


async def _entity_out(ctx: WorkspaceContext, entity_id: uuid.UUID) -> dict:
    ctx.session.expire_all()  # the change was committed by another transaction
    e = await ctx.session.get(Entity, entity_id)
    return _entity(e, await ctx.session.get(XeroConnection, e.connection_id))


@router.get("/entities", response_model=list[S.EntityOut])
async def entities(ctx: WorkspaceContext = Workspace):
    rows = (await ctx.session.execute(
        select(Entity, XeroConnection).outerjoin(XeroConnection, XeroConnection.id == Entity.connection_id)
        .where(Entity.workspace_id == ctx.workspace_id).order_by(Entity.name)
    )).all()
    return [_entity(e, c) for e, c in rows]


class DisconnectRequest(BaseModel):
    # False: keep its data 30 days so reconnecting restores it; True: remove it now.
    remove_now: bool = False


@router.post("/entities/{entity_id}/disconnect", response_model=S.EntityOut)
async def disconnect_entity(entity_id: uuid.UUID, body: DisconnectRequest, ctx: WorkspaceContext = Admin,
                            identity: XeroIdentityClient = Depends(get_identity_client)):
    await connections.disconnect(ctx.workspace_id, entity_id, ctx.user_id, remove_now=body.remove_now,
                                 identity=identity)
    return await _entity_out(ctx, entity_id)


@router.post("/entities/{entity_id}/remove-data", response_model=S.EntityOut)
async def remove_entity_data(entity_id: uuid.UUID, ctx: WorkspaceContext = Admin):
    """Remove a disconnected org's data now instead of at the end of its grace period."""
    await connections.purge(ctx.workspace_id, entity_id, ctx.user_id)
    return await _entity_out(ctx, entity_id)


@router.post("/entities/{entity_id}/sync", status_code=202, response_model=S.QueuedOut)
async def sync_entity(
    entity_id: uuid.UUID, tasks: BackgroundTasks, full: bool = False, ctx: WorkspaceContext = Admin
):
    e = await ctx.session.get(Entity, entity_id)
    if e is None or e.status != "active":
        raise NotFound("Organisation not found.")
    tasks.add_task(enqueue_sync, ctx.workspace_id, e.id, e.tenant_id, FULL if full else INCREMENTAL)
    return {"queued": True}


# ---- group standard -------------------------------------------------------


@router.get("/standard", response_model=list[S.GroupAccountOut])
async def get_standard(ctx: WorkspaceContext = Workspace):
    return [standard.as_dict(g) for g in await standard.list_accounts(ctx.session, ctx.workspace_id)]


class SeedRequest(BaseModel):
    entity_id: uuid.UUID


async def _suggest_everywhere(ctx: WorkspaceContext, tasks: BackgroundTasks) -> None:
    """Queue re-suggestion for every org once THIS transaction has committed
    (BackgroundTasks run after the response, and the DB dependency commits
    before it), so no job can read the standard before it exists."""
    ids = list(await ctx.session.scalars(
        select(Entity.id).where(Entity.workspace_id == ctx.workspace_id, Entity.status == "active")
    ))
    for eid in ids:
        tasks.add_task(enqueue_suggest, ctx.workspace_id, eid, True)


@router.post("/standard/seed", status_code=201, response_model=S.CountOut)
async def seed_standard(body: SeedRequest, tasks: BackgroundTasks, ctx: WorkspaceContext = Admin):
    n = await standard.seed_from_entity(ctx.session, ctx.workspace_id, body.entity_id, ctx.user_id)
    await _suggest_everywhere(ctx, tasks)
    return {"accounts": n}


@router.post("/standard/import", status_code=201, response_model=S.CountOut)
async def import_standard(
    tasks: BackgroundTasks, file: UploadFile = File(...), ctx: WorkspaceContext = Admin
):
    n = await standard.import_csv(ctx.session, ctx.workspace_id, await file.read(), ctx.user_id)
    await _suggest_everywhere(ctx, tasks)
    return {"accounts": n}


class NewGroupAccount(BaseModel):
    code: str
    name: str
    type: str
    description: str | None = None


@router.post("/standard/accounts", status_code=201, response_model=S.GroupAccountOut)
async def add_group_account(body: NewGroupAccount, ctx: WorkspaceContext = Admin):
    g = await standard.create_account(ctx.session, ctx.workspace_id, body.model_dump(), ctx.user_id)
    return standard.as_dict(g)


class GroupAccountChange(BaseModel):
    name: str | None = None
    type: str | None = None
    description: str | None = None
    status: Literal["active", "archived"] | None = None


@router.patch("/standard/accounts/{account_id}", response_model=S.GroupAccountOut)
async def edit_group_account(account_id: uuid.UUID, body: GroupAccountChange, ctx: WorkspaceContext = Admin):
    g = await standard.update_account(
        ctx.session, ctx.workspace_id, account_id, body.model_dump(exclude_unset=True), ctx.user_id
    )
    return standard.as_dict(g)


# ---- mappings, gaps, export ------------------------------------------------


@router.get("/entities/{entity_id}/mappings", response_model=list[S.MappingRow])
async def entity_mappings(entity_id: uuid.UUID, ctx: WorkspaceContext = Workspace):
    if await ctx.session.get(Entity, entity_id) is None:
        raise NotFound("Organisation not found.")
    return await mapping.entity_mappings(ctx.session, entity_id)


@router.post("/entities/{entity_id}/mappings/suggest", status_code=202, response_model=S.QueuedOut)
async def resuggest(entity_id: uuid.UUID, tasks: BackgroundTasks, ctx: WorkspaceContext = Admin):
    if await ctx.session.get(Entity, entity_id) is None:
        raise NotFound("Organisation not found.")
    tasks.add_task(enqueue_suggest, ctx.workspace_id, entity_id, True)
    return {"queued": True}


@router.post("/entities/{entity_id}/mappings/confirm-exact", response_model=S.ConfirmedOut)
async def confirm_exact(entity_id: uuid.UUID, ctx: WorkspaceContext = Admin):
    return {"confirmed": await mapping.confirm_exact(ctx.session, ctx.workspace_id, entity_id, ctx.user_id)}


class Decision(BaseModel):
    action: Literal["confirm", "reject", "assign"]
    group_account_id: uuid.UUID | None = None


@router.post("/mappings/{mapping_id}/decision", response_model=S.DecisionOut)
async def decide(mapping_id: uuid.UUID, body: Decision, ctx: WorkspaceContext = Admin):
    m = await mapping.decide(ctx.session, ctx.workspace_id, mapping_id, body.action, ctx.user_id,
                             body.group_account_id)
    return {"id": str(m.id), "status": m.status}


@router.get("/gaps", response_model=S.GapMatrix)
async def gap_matrix(ctx: WorkspaceContext = Workspace):
    return await mapping.gaps(ctx.session, ctx.workspace_id)


@router.get("/export.csv", response_class=PlainTextResponse)
async def export(ctx: WorkspaceContext = Workspace):
    body = await mapping.export_csv(ctx.session, ctx.workspace_id)
    return PlainTextResponse(body, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="canopy-mapping.csv"'})


# ---- audit -----------------------------------------------------------------


@router.get("/audit", response_model=list[S.AuditEventOut])
async def audit_log(limit: int = 100, ctx: WorkspaceContext = Admin):
    rows = await ctx.session.scalars(
        select(AuditEvent).where(AuditEvent.workspace_id == ctx.workspace_id)
        .order_by(AuditEvent.id.desc()).limit(min(max(limit, 1), 500))
    )
    return [{"id": e.id, "action": e.action, "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
             "target_type": e.target_type, "target_id": e.target_id, "before": e.before, "after": e.after,
             "at": e.created_at.isoformat()} for e in rows]

