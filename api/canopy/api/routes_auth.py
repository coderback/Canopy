"""Sign-in, org connection callback, session, and /me."""

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import service
from ..auth.models import User
from ..core.config import get_settings
from ..jobs.app import enqueue_sync
from ..sync.service import FULL
from ..tenancy.models import Membership, Workspace
from ..xero.oauth import XeroIdentityClient
from . import schemas as S
from .deps import Principal, UserDb, get_principal

router = APIRouter(tags=["auth"])


def get_identity_client() -> XeroIdentityClient:
    """Overridden in tests with a fake transport."""
    return XeroIdentityClient()


def _set_session_cookie(response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name, token, httponly=True, secure=s.cookie_secure, samesite="lax",
        max_age=s.session_ttl_hours * 3600, path="/",
    )


@router.get("/auth/login")
async def login(redirect_to: str | None = None):
    """Sign Up / Sign In with Xero. Also the App Store 'connect request URL'."""
    return RedirectResponse(await service.start_oauth(service.LOGIN, redirect_to=redirect_to), status_code=303)


@router.get("/auth/xero/callback")
async def xero_callback(
    code: str, state: str, identity: XeroIdentityClient = Depends(get_identity_client)
):
    result = await service.handle_callback(code, state, identity)
    web = get_settings().web_base_url
    response = RedirectResponse(f"{web}{result.redirect_to}", status_code=303)
    if result.session_token:
        _set_session_cookie(response, result.session_token)
    for entity_id, tenant_id in result.new_entities:
        await enqueue_sync(result.workspace_id, entity_id, tenant_id, FULL)
    return response


@router.post("/auth/logout", status_code=204)
async def logout(principal: Principal = Depends(get_principal)):
    await service.end_session(principal.token_hash)
    response = Response(status_code=204)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return response


@router.get("/me", response_model=S.MeOut)
async def me(principal: Principal = Depends(get_principal), s: AsyncSession = UserDb):
    user = await s.get(User, principal.user_id)
    rows = (await s.execute(
        select(Workspace.id, Workspace.name, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == principal.user_id)
        .order_by(Workspace.name)
    )).all()
    return {
        "user": {"id": str(user.id), "email": user.email, "name": user.name},
        "csrf_token": principal.csrf_token,
        "workspaces": [{"id": str(w), "name": n, "role": r.value} for w, n, r in rows],
    }


class NewWorkspace(BaseModel):
    name: str


@router.post("/workspaces", status_code=201, response_model=S.IdOut)
async def create_workspace(body: NewWorkspace, principal: Principal = Depends(get_principal)):
    ws = await service.create_workspace(principal.user_id, body.name)
    return {"id": str(ws)}


class AcceptInvitation(BaseModel):
    token: str


@router.post("/invitations/accept", response_model=S.WorkspaceIdOut)
async def accept_invitation(body: AcceptInvitation, principal: Principal = Depends(get_principal)):
    ws = await service.accept_invitation(body.token, principal.user_id)
    return {"workspace_id": str(ws)}
