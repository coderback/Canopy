"""Dev-only endpoint that seeds a clickable demo run (no live Xero required)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..demo import seed_demo_run
from ..serializers import run_dict

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed")
def seed(db: Session = Depends(get_db)):
    if not get_settings().demo_mode:
        raise HTTPException(status_code=404, detail="demo mode is disabled")
    run = seed_demo_run(db)
    return run_dict(run)
