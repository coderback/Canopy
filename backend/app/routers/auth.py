from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..xero import auth as xero_auth

router = APIRouter(prefix="/auth/xero", tags=["auth"])


@router.get("/connect")
def connect():
    """Redirect the browser to Xero's consent screen. Repeat once per org."""
    return RedirectResponse(xero_auth.build_consent_url())


@router.get("/callback")
async def callback(code: str, state: str, db: Session = Depends(get_db)):
    if not xero_auth.consume_state(state):
        raise HTTPException(status_code=400, detail="Unknown OAuth state")
    await xero_auth.exchange_code(db, code)
    entities = await xero_auth.sync_connections(db)
    names = ", ".join(e.name for e in entities)
    return {
        "connected_entities": [
            {"id": e.id, "tenant_id": e.tenant_id, "name": e.name} for e in entities
        ],
        "message": f"Connected: {names}. Visit /auth/xero/connect again to add another organisation.",
    }
