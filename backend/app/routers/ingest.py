"""Universal ingest router (Bounty 02).

POST /ingest takes an uploaded file (CSV/JSON/xlsx) and a list of target
entities, infers what the file is, and normalises it into one balanced manual
journal per entity — routed into the SAME Run/Proposal/approval flow as
propagation, so the frontend approval table consumes one schema for both bounties.

`ingest_file` holds the orchestration and is callable directly (tests pass raw
bytes + a canned completer); the endpoint is a thin multipart wrapper.
"""

import json
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..engines.ingest import classify_ingest, map_ingest_to_journal
from ..engines.mapping import Complete
from ..fanout import fan_out
from ..ingest_parse import UnsupportedFileError, parse_upload
from ..models import Entity, Proposal, Run
from ..serializers import run_dict
from ..snapshots import get_entity_context
from ..xero.client import XeroApi
from .changes import get_completer, get_xero_api

router = APIRouter(prefix="/ingest", tags=["ingest"])

# Tokens that don't help distinguish a site from an org name.
_STOP_TOKENS = {"ltd", "limited", "llp", "plc", "inc", "co", "company", "uk", "demo", "the", "org"}


def _tokens(name: str | None) -> set[str]:
    if not name:
        return set()
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t and t not in _STOP_TOKENS}


def match_site_to_entity(site: str | None, entities: list[Entity]) -> Entity | None:
    """Deterministic: the site shares a distinguishing token with the entity name
    (e.g. 'Bristol' ∈ 'Demo Bristol Ltd'). No fuzzy guessing — an unmatched site is
    surfaced to a human, never silently attributed to the wrong org."""
    site_tokens = _tokens(site)
    if not site_tokens:
        return None
    for entity in entities:
        if site_tokens & _tokens(entity.name):
            return entity
    return None


async def ingest_file(
    db: Session,
    complete: Complete,
    api: XeroApi,
    filename: str,
    data: bytes,
    target_entity_ids: list[int],
) -> dict:
    """Parse → classify → per-entity journal → persist a Run. Returns run_dict."""
    parsed = parse_upload(filename, data)  # raises UnsupportedFileError on bad input

    entities = (
        db.query(Entity)
        .filter(Entity.id.in_(target_entity_ids), Entity.active.is_(True))
        .all()
    )
    found = {e.id for e in entities}
    missing = [eid for eid in target_entity_ids if eid not in found]
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown/inactive entities: {missing}")
    if not entities:
        raise HTTPException(status_code=400, detail="pick at least one target entity")

    classification = await classify_ingest(complete, filename, parsed["grid"])

    run = Run(
        kind="ingest",
        change_type="manual_journal",
        source_payload={
            "filename": filename,
            "doc_type": classification.doc_type,
            "human_description": classification.human_description,
            "intents": [i.model_dump() for i in classification.intents],
            "caveats": classification.caveats,
        },
        status="proposed",
    )
    db.add(run)
    db.flush()

    intents_by_entity = {
        entity.id: [i for i in classification.intents if match_site_to_entity(i.site, [entity])]
        for entity in entities
    }

    async def propose(entity: Entity):
        snapshot = await get_entity_context(db, api, entity)
        return await map_ingest_to_journal(
            complete, classification, intents_by_entity[entity.id], entity, snapshot
        )

    proposals = await fan_out(
        [e for e in entities if intents_by_entity[e.id]], propose, "create-manual-journal"
    )

    for entity in entities:
        if not intents_by_entity[entity.id]:
            db.add(
                Proposal(
                    run_id=run.id,
                    entity_id=entity.id,
                    action="create-manual-journal",
                    mapped_payload={},
                    confidence=0.0,
                    reasoning=(
                        f"No rows in {filename} matched {entity.name}. Refusing to book a "
                        f"journal here rather than attributing another site's figures to it."
                    ),
                    needs_human=True,
                    status="proposed",
                )
            )
            continue
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


@router.post("")
async def ingest_endpoint(
    file: UploadFile = File(...),
    target_entity_ids: str = Form(...),
    db: Session = Depends(get_db),
    complete: Complete = Depends(get_completer),
    api: XeroApi = Depends(get_xero_api),
):
    try:
        ids = json.loads(target_entity_ids)
        if not isinstance(ids, list):
            raise ValueError
        ids = [int(i) for i in ids]
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="target_entity_ids must be a JSON array of entity ids")

    data = await file.read()
    try:
        return await ingest_file(db, complete, api, file.filename or "upload", data, ids)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
