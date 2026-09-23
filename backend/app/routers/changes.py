"""Change fan-out router (Bounty 01 propagation core).

POST /changes takes one source change and a list of target entities, snapshots
each entity's live reference data, runs the mapping engine per entity
(concurrently, see fanout.py), and persists the resulting proposals into a new
Run. An entity whose mapping fails gets a needs_human row; the rest are kept. Nothing is written to Xero
here — the proposals wait in the batched approval table (POST /runs/{id}/approve).

The mapping-engine call and the Xero client are provided via dependencies so
tests can override them (app.dependency_overrides) with canned responses.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..engines import llm
from ..engines.contracts import ChangeType
from ..engines.mapping import _ACTION_BY_TYPE, Complete, map_change
from ..fanout import fan_out
from ..models import Entity, Proposal, Run
from ..serializers import run_dict
from ..snapshots import get_entity_context
from ..xero.client import XeroApi, xero_api

router = APIRouter(prefix="/changes", tags=["changes"])


def get_completer() -> Complete:
    """The structured-completion seam. Overridden in tests with a canned func."""
    return llm.complete_structured


def get_xero_api() -> XeroApi:
    return xero_api


class ChangeRequest(BaseModel):
    change_type: ChangeType
    payload: dict
    target_entity_ids: list[int]


@router.post("")
async def create_change(
    body: ChangeRequest,
    db: Session = Depends(get_db),
    complete: Complete = Depends(get_completer),
    api: XeroApi = Depends(get_xero_api),
):
    entities = (
        db.query(Entity)
        .filter(Entity.id.in_(body.target_entity_ids), Entity.active.is_(True))
        .all()
    )
    found = {e.id for e in entities}
    missing = [eid for eid in body.target_entity_ids if eid not in found]
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown/inactive entities: {missing}")
    action = _ACTION_BY_TYPE.get(body.change_type)
    if action is None:
        raise HTTPException(
            status_code=400,
            detail=f"change_type {body.change_type!r} is not propagated via /changes",
        )

    run = Run(
        kind="propagation",
        change_type=body.change_type,
        source_payload=body.payload,
        status="proposed",
    )
    db.add(run)
    db.flush()  # assign run.id before attaching proposals

    async def propose(entity: Entity):
        snapshot = await get_entity_context(db, api, entity)
        return await map_change(complete, body.change_type, body.payload, entity, snapshot)

    proposals = await fan_out(entities, propose, action)
    for entity in entities:
        proposal = proposals[entity.id]
        db.add(
            Proposal(
                run_id=run.id,
                entity_id=entity.id,
                action=proposal.action,
                mapped_payload=proposal.mapped_payload,
                confidence=proposal.confidence,
                reasoning=proposal.reasoning,
                needs_human=proposal.needs_human,
                status="proposed",
            )
        )

    db.commit()
    db.refresh(run)
    return run_dict(run)
