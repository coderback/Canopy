"""Sign Up with Xero, org connection, sessions, invitations.

Two OAuth purposes share one callback, told apart by the stored state row:
- login:   OIDC scopes only -> verify id_token -> upsert user -> session.
- connect: accounting scopes, started by a workspace admin -> store the
  encrypted token set as a workspace connection -> discover the tenants this
  consent granted (filtered by authEventId) -> entities -> queue first sync.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from ..audit import service as audit
from ..core.config import get_settings
from ..core.db import unit_of_work
from ..core.errors import AppError, Forbidden, NotFound
from ..core.models_base import utcnow
from ..core.security import encrypt_json, hash_token, new_token, pkce_pair
from ..tenancy.models import Membership, Role, Workspace
from ..xero import oauth
from ..xero.models import Entity, XeroConnection
from ..xero.tokens import token_record
from .models import OAuthState, Session

STATE_TTL = timedelta(minutes=10)
LOGIN, CONNECT = "login", "connect"


@dataclass(frozen=True)
class CallbackResult:
    purpose: str
    redirect_to: str
    session_token: str | None = None  # set for login
    workspace_id: uuid.UUID | None = None
    new_entities: tuple = ()  # (entity_id, tenant_id) pairs to sync, for connect


def _safe_redirect(path: str | None) -> str:
    """Only same-site relative paths: never an open redirect."""
    if path and path.startswith("/") and not path.startswith("//"):
        return path
    return "/"


async def start_oauth(
    purpose: str, *, redirect_to: str | None = None,
    user_id: uuid.UUID | None = None, workspace_id: uuid.UUID | None = None,
    scopes: str | None = None,
) -> str:
    """Create a single-use state row and return Xero's authorize URL."""
    state, nonce = new_token(24), new_token(24)
    verifier, challenge = pkce_pair()
    async with unit_of_work() as s:
        s.add(OAuthState(
            state=state, purpose=purpose, nonce=nonce, code_verifier=verifier, user_id=user_id,
            workspace_id=workspace_id, redirect_to=_safe_redirect(redirect_to), expires_at=utcnow() + STATE_TTL,
        ))
    scopes = scopes or (oauth.LOGIN_SCOPES if purpose == LOGIN else get_settings().xero_connect_scopes)
    return oauth.authorize_url(scopes=scopes, state=state, nonce=nonce, code_challenge=challenge)


async def _consume_state(state: str) -> OAuthState:
    async with unit_of_work() as s:
        row = await s.get(OAuthState, state)
        if row is not None:
            await s.execute(delete(OAuthState).where(OAuthState.state == state))
    if row is None or row.expires_at <= utcnow():
        raise AppError("This sign-in link has expired. Please try again.", code="oauth_state_invalid")
    return row


async def create_session(user_id: uuid.UUID) -> str:
    token = new_token()
    async with unit_of_work(user_id=user_id) as s:
        s.add(Session(
            token_hash=hash_token(token), user_id=user_id, csrf_token=new_token(24),
            expires_at=utcnow() + timedelta(hours=get_settings().session_ttl_hours),
        ))
        await audit.record(s, "auth.login", workspace_id=None, actor_user_id=user_id)
    return token


async def end_session(token_hash: str) -> None:
    async with unit_of_work() as s:
        await s.execute(delete(Session).where(Session.token_hash == token_hash))


async def handle_callback(
    code: str, state: str, identity: oauth.XeroIdentityClient, *, signing_key=None
) -> CallbackResult:
    st = await _consume_state(state)
    tokens = await identity.exchange_code(code, st.code_verifier)
    person = oauth.verify_id_token(tokens["id_token"], nonce=st.nonce, signing_key=signing_key)

    if st.purpose == LOGIN:
        async with unit_of_work() as s:
            user_id = await s.scalar(
                text("select canopy_upsert_user(:x, :e, :n)"),
                {"x": person.xero_user_id, "e": person.email, "n": person.name},
            )
        return CallbackResult(LOGIN, st.redirect_to or "/", session_token=await create_session(user_id))

    # connect: the state row pins who started it and for which workspace.
    if st.user_id is None or st.workspace_id is None:
        raise AppError("Invalid connection request.", code="oauth_state_invalid")
    ws, actor = st.workspace_id, st.user_id
    auth_event = oauth.unverified_claims(tokens["access_token"]).get("authentication_event_id")
    tenants = [
        c for c in await identity.list_connections(tokens["access_token"], auth_event)
        if c.get("tenantType") == "ORGANISATION"
    ]
    new_entities = []
    async with unit_of_work(workspace_id=ws, user_id=actor) as s:
        # Filter on the workspace too: RLS also shows the user's memberships elsewhere.
        role = await s.scalar(
            select(Membership.role).where(Membership.workspace_id == ws, Membership.user_id == actor)
        )
        if role not in (Role.OWNER, Role.ADMIN):
            raise Forbidden("Only workspace owners and admins can connect organisations.")
        stmt = insert(XeroConnection).values(
            workspace_id=ws, xero_user_id=person.xero_user_id, connected_by=actor,
            token_encrypted=encrypt_json(token_record(tokens)), scopes=tokens.get("scope", ""),
            status="active", last_refreshed_at=utcnow(),
        )
        connection_id = await s.scalar(
            stmt.on_conflict_do_update(
                index_elements=[XeroConnection.workspace_id, XeroConnection.xero_user_id],
                set_={
                    k: stmt.excluded[k]
                    for k in ("token_encrypted", "scopes", "status", "last_refreshed_at", "connected_by")
                },
            ).returning(XeroConnection.id)
        )
        for t in tenants:
            existing = await s.scalar(select(Entity).where(Entity.tenant_id == t["tenantId"]))
            if existing:
                existing.connection_id, existing.status = connection_id, "active"
                existing.xero_connection_ref, existing.name = t.get("id"), t.get("tenantName") or existing.name
                new_entities.append((existing.id, existing.tenant_id))
                continue
            e = Entity(workspace_id=ws, connection_id=connection_id, tenant_id=t["tenantId"],
                       xero_connection_ref=t.get("id"), name=t.get("tenantName") or t["tenantId"],
                       sync_status="queued")
            s.add(e)
            await s.flush()
            new_entities.append((e.id, e.tenant_id))
        await audit.record(s, "xero.connected", workspace_id=ws, actor_user_id=actor,
                           target_type="xero_connection", target_id=connection_id,
                           after={"orgs": [t.get("tenantName") for t in tenants], "scopes": tokens.get("scope")})
    return CallbackResult(CONNECT, st.redirect_to or f"/w/{ws}", workspace_id=ws, new_entities=tuple(new_entities))


async def create_workspace(user_id: uuid.UUID, name: str) -> uuid.UUID:
    ws = uuid.uuid4()
    # Bind the new id first so the RLS WITH CHECK clauses accept the inserts.
    async with unit_of_work(workspace_id=ws, user_id=user_id) as s:
        s.add(Workspace(id=ws, name=name.strip() or "My group", created_by=user_id))
        await s.flush()
        s.add(Membership(workspace_id=ws, user_id=user_id, role=Role.OWNER))
        await audit.record(s, "workspace.created", workspace_id=ws, actor_user_id=user_id, after={"name": name})
    return ws


async def accept_invitation(token: str, user_id: uuid.UUID) -> uuid.UUID:
    async with unit_of_work(user_id=user_id) as s:
        row = (await s.execute(
            text("select workspace_id from canopy_accept_invitation(:h)"), {"h": hash_token(token)}
        )).first()
    if row is None:
        raise NotFound("This invitation is invalid, expired, or for a different email address.")
    ws = row[0]
    async with unit_of_work(workspace_id=ws, user_id=user_id) as s:
        await audit.record(s, "member.joined", workspace_id=ws, actor_user_id=user_id)
    return ws
