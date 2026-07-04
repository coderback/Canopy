from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..execution import execute_run
from ..models import Run, utcnow
from ..serializers import run_dict
from ..xero.client import xero_api

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(Run).order_by(Run.created_at.desc()).limit(50).all()
    return [run_dict(r, include_proposals=False) for r in runs]


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return run_dict(run)


class RowDecision(BaseModel):
    proposal_id: int
    approved: bool
    edited_payload: dict | None = None


class ApproveRequest(BaseModel):
    decisions: list[RowDecision]


@router.post("/{run_id}/approve")
async def approve_run(run_id: int, body: ApproveRequest, db: Session = Depends(get_db)):
    """The single batched approval: per-row include/exclude/edit, then execute."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")
    if run.status not in ("proposed", "partial", "failed"):
        raise HTTPException(status_code=409, detail=f"run is {run.status}")

    by_id = {p.id: p for p in run.proposals}
    for decision in body.decisions:
        proposal = by_id.get(decision.proposal_id)
        if proposal is None:
            raise HTTPException(status_code=400, detail=f"proposal {decision.proposal_id} not in run")
        if decision.approved:
            proposal.status = "approved"
            if decision.edited_payload is not None:
                proposal.edited_payload = decision.edited_payload
        else:
            proposal.status = "excluded"

    # needs_human rows cannot slip through unreviewed: they must appear in the
    # decisions list explicitly (approved or excluded) or we refuse the batch.
    decided = {d.proposal_id for d in body.decisions}
    unreviewed = [
        p.id for p in run.proposals if p.needs_human and p.id not in decided and p.status == "proposed"
    ]
    if unreviewed:
        raise HTTPException(
            status_code=422,
            detail=f"proposals {unreviewed} are flagged needs_human and must be explicitly approved or excluded",
        )

    run.status = "approved"
    run.approved_at = utcnow()
    db.commit()

    await execute_run(db, xero_api, run)
    db.refresh(run)
    return run_dict(run)
