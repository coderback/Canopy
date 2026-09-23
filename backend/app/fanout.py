"""Concurrent per-entity fan-out shared by the propagation and ingest routers.

Xero's limits are per tenant, so snapshotting + mapping N entities runs
concurrently (bounded by `fanout_concurrency`, which mostly protects the LLM
endpoint). One entity failing — an LLM timeout, a malformed answer, a Xero read
error — must not sink the whole run: the failure becomes a zero-confidence
`needs_human` proposal for that entity, and every other entity's proposal is kept.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .config import get_settings
from .engines.contracts import EngineProposal
from .models import Entity

log = logging.getLogger(__name__)


def failed_proposal(action: str, entity: Entity, exc: Exception) -> EngineProposal:
    return EngineProposal(
        action=action,
        mapped_payload={},
        confidence=0.0,
        reasoning=(
            f"Canopy could not produce a proposal for {entity.name}: "
            f"{type(exc).__name__}: {str(exc)[:300]}. Nothing will be written here "
            f"unless a human supplies the payload."
        ),
        needs_human=True,
    )


async def fan_out(
    entities: list[Entity],
    work: Callable[[Entity], Awaitable[EngineProposal]],
    action: str,
) -> dict[int, EngineProposal]:
    """Run `work` for every entity concurrently; returns entity.id -> proposal,
    substituting `failed_proposal` for any entity whose work raised."""
    semaphore = asyncio.Semaphore(get_settings().fanout_concurrency)

    async def one(entity: Entity) -> tuple[int, EngineProposal]:
        async with semaphore:
            try:
                return entity.id, await work(entity)
            except Exception as exc:  # noqa: BLE001 — isolate per-entity failures
                log.exception("fan-out failed for entity %s", entity.id)
                return entity.id, failed_proposal(action, entity, exc)

    return dict(await asyncio.gather(*(one(e) for e in entities)))
