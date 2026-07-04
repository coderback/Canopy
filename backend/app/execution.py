"""Deterministic execution layer.

Runs ONLY after human approval. For each approved proposal: validate the
payload against its action schema, write via the Xero client with an explicit
tenant id, and record a full request/response audit row. Partial failures are
recorded per-row and retriable — one bad entity never blocks the rest.
"""

from sqlalchemy.orm import Session

from .engines.contracts import validate_payload
from .models import Proposal, Run, WriteResult, utcnow
from .xero.client import XeroApi, XeroApiError

_ID_FIELDS = {
    "create-contact": "ContactID",
    "create-item": "ItemID",
    "create-account": "AccountID",
    "create-tracking-category": "TrackingCategoryID",
    "create-manual-journal": "ManualJournalID",
    "create-bill": "InvoiceID",
}


async def _write(api: XeroApi, db: Session, tenant_id: str, action: str, payload: dict) -> dict:
    if action == "create-contact":
        return await api.create_or_update_contact(db, tenant_id, payload)
    if action == "create-item":
        return await api.create_or_update_item(db, tenant_id, payload)
    if action == "create-account":
        return await api.create_account(db, tenant_id, payload)
    if action == "create-tracking-category":
        options = payload.pop("Options", [])
        category = await api.create_tracking_category(db, tenant_id, payload)
        for name in options:
            await api.add_tracking_option(
                db, tenant_id, category["TrackingCategoryID"], {"Name": name}
            )
        return category
    if action == "create-manual-journal":
        return await api.create_manual_journal(db, tenant_id, payload)
    if action == "create-bill":
        return await api.create_draft_bill(db, tenant_id, payload)
    raise ValueError(f"unknown action {action!r}")


async def execute_proposal(db: Session, api: XeroApi, proposal: Proposal) -> WriteResult:
    payload = proposal.edited_payload or proposal.mapped_payload
    attempt = len(proposal.write_results) + 1
    try:
        payload = validate_payload(proposal.action, payload)
        response = await _write(api, db, proposal.entity.tenant_id, proposal.action, dict(payload))
        result = WriteResult(
            proposal_id=proposal.id,
            attempt=attempt,
            success=True,
            request_json=payload,
            response_json=response,
            xero_id=response.get(_ID_FIELDS.get(proposal.action, ""), None),
        )
        proposal.status = "executed"
    except (XeroApiError, ValueError, KeyError) as exc:
        result = WriteResult(
            proposal_id=proposal.id,
            attempt=attempt,
            success=False,
            request_json=payload if isinstance(payload, dict) else {},
            error=str(exc),
        )
        proposal.status = "failed"
    db.add(result)
    db.commit()
    return result


async def execute_run(db: Session, api: XeroApi, run: Run) -> Run:
    run.status = "executing"
    db.commit()
    outcomes: list[bool] = []
    for proposal in run.proposals:
        if proposal.status != "approved":
            continue
        result = await execute_proposal(db, api, proposal)
        outcomes.append(result.success)
    if not outcomes:
        run.status = "completed"
    elif all(outcomes):
        run.status = "completed"
    elif any(outcomes):
        run.status = "partial"
    else:
        run.status = "failed"
    run.completed_at = utcnow()
    db.commit()
    return run
