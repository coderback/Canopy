"""Request dependencies: who is calling, which workspace, and the transaction.

- Authentication is a server-side session looked up from an HTTP-only cookie.
- Mutating requests must echo the session's CSRF token in `X-CSRF-Token`
  (cookies are sent cross-site on some navigations; the header isn't).
- Workspace routes carry the workspace in the path. The per-request
  transaction binds that workspace and the user into the RLS context, then the
  caller's membership is checked; non-members get 404, so workspace ids don't
  leak.
- The DB dependency uses scope="function": FastAPI closes it (committing)
  BEFORE the response is sent, so a failed commit can't masquerade as success.
"""

import hmac
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.models import Session as SessionRow
from ..core.config import get_settings
from ..core.db import unit_of_work
from ..core.errors import Forbidden, NotFound, Unauthenticated
from ..core.security import hash_token
from ..tenancy.models import Membership, Role

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    token_hash: str
    csrf_token: str


@dataclass
class WorkspaceContext:
    session: AsyncSession
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: Role


async def get_principal(request: Request) -> Principal:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise Unauthenticated("Sign in required.")
    token_hash = hash_token(token)
    async with unit_of_work() as s:
        row = await s.get(SessionRow, token_hash)
    if row is None or row.expires_at <= datetime.now(UTC):
        raise Unauthenticated("Session expired. Sign in again.")
    principal = Principal(user_id=row.user_id, token_hash=token_hash, csrf_token=row.csrf_token)
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(sent, principal.csrf_token):
            raise Forbidden("Missing or invalid CSRF token.", code="csrf_failed")
    return principal


async def user_db(principal: Principal = Depends(get_principal)) -> AsyncIterator[AsyncSession]:
    """Transaction bound to the user only (no workspace): for /me and creating workspaces."""
    async with unit_of_work(user_id=principal.user_id) as s:
        yield s


async def _workspace_ctx(
    workspace_id: uuid.UUID, principal: Principal = Depends(get_principal)
) -> AsyncIterator[WorkspaceContext]:
    async with unit_of_work(workspace_id=workspace_id, user_id=principal.user_id) as s:
        role = await s.scalar(
            select(Membership.role).where(
                Membership.workspace_id == workspace_id, Membership.user_id == principal.user_id
            )
        )
        if role is None:
            raise NotFound("Workspace not found.")
        yield WorkspaceContext(s, workspace_id, principal.user_id, role)


# Use these in routes. scope="function" => commit happens before the response.
UserDb = Depends(user_db, scope="function")
Workspace = Depends(_workspace_ctx, scope="function")


def require_role(*allowed: Role):
    """Dependency factory: the caller's role in the path workspace must be allowed."""

    async def check(ctx: WorkspaceContext = Workspace) -> WorkspaceContext:
        if ctx.role not in allowed:
            raise Forbidden("Your role can't do this.")
        return ctx

    return Depends(check, scope="function")


ADMINS = (Role.OWNER, Role.ADMIN)
