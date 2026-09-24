import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import request_id_var
from .models import AuditEvent


async def record(
    session: AsyncSession,
    action: str,
    *,
    workspace_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: Any = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """Append an audit event in the caller's transaction, so the event and the
    change it describes commit (or roll back) together."""
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            before=before,
            after=after,
            request_id=request_id_var.get(),
        )
    )
