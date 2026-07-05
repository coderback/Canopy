from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Entity, Snapshot
from ..snapshots import snapshot_health
from ..xero.client import xero_api

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("")
def list_entities(db: Session = Depends(get_db)):
    entities = db.query(Entity).filter_by(active=True).all()
    health = snapshot_health(db, entities)
    out = []
    for e in entities:
        latest = (
            db.query(Snapshot)
            .filter_by(entity_id=e.id)
            .order_by(Snapshot.fetched_at.desc())
            .first()
        )
        out.append(
            {
                "id": e.id,
                "tenant_id": e.tenant_id,
                "name": e.name,
                "connected_at": e.connected_at.isoformat() if e.connected_at else None,
                "snapshot_age": latest.fetched_at.isoformat() if latest else None,
                "health": health[e.id],
            }
        )
    return out


@router.get("/{entity_id}/organisation")
async def organisation(entity_id: int, db: Session = Depends(get_db)):
    """Live read — proves the connection for this tenant end-to-end."""
    entity = db.get(Entity, entity_id)
    if entity is None:
        return {"error": "unknown entity"}
    org = await xero_api.get_organisation(db, entity.tenant_id)
    return {
        "Name": org.get("Name"),
        "LegalName": org.get("LegalName"),
        "OrganisationID": org.get("OrganisationID"),
        "BaseCurrency": org.get("BaseCurrency"),
        "CountryCode": org.get("CountryCode"),
        "IsDemoCompany": org.get("IsDemoCompany"),
    }
