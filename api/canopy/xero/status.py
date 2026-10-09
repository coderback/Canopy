"""An organisation's connection status, in one place.

- active: connected; synced and changeable.
- needs_reconnect: access broke (the grant was revoked, Xero refused the org, or
  it vanished from Xero's connection list). Its data is kept and still shown,
  flagged as stale; no new changes until someone reconnects it.
- disconnected: deliberately disconnected in Canopy. Hidden from gaps; its data
  is purged after a grace period (or straight away on request).
"""

from ..audit import service as audit
from ..core.models_base import utcnow
from .models import Entity

ACTIVE, NEEDS_RECONNECT, DISCONNECTED = "active", "needs_reconnect", "disconnected"
# Organisations whose data is current or merely stale: shown in gaps and mapping.
SHOWN = (ACTIVE, NEEDS_RECONNECT)

REVOKED_REASON = ("The Xero sign-in Canopy uses for this organisation expired or was revoked. "
                  "Reconnect it to keep it in sync.")
REFUSED_REASON = ("Xero refused access to this organisation; it may have been disconnected in Xero. "
                  "Reconnect it to keep it in sync.")
REMOVED_REASON = "Canopy's connection to this organisation was removed in Xero. Reconnect it to keep it in sync."


async def mark_needs_reconnect(s, entities: list[Entity], reason: str) -> None:
    """Flag active organisations whose access broke; each change is audited once."""
    now = utcnow()
    for e in entities:
        if e.status != ACTIVE:
            continue
        e.status, e.status_reason, e.status_changed_at = NEEDS_RECONNECT, reason, now
        await audit.record(s, "xero.org_needs_reconnect", workspace_id=e.workspace_id, actor_user_id=None,
                           target_type="entity", target_id=e.id, after={"org": e.name, "reason": reason})


def reactivate(e: Entity) -> None:
    """Connected again (via the connect flow): clear every trace of the old state."""
    e.status, e.status_reason, e.status_changed_at = ACTIVE, None, utcnow()
    e.purge_after = e.purged_at = None
