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
        return await _write_tracking_category(api, db, tenant_id, payload)
    if action == "create-manual-journal":
        return await api.create_manual_journal(db, tenant_id, payload)
    if action == "create-bill":
        return await api.create_draft_bill(db, tenant_id, payload)
    raise ValueError(f"unknown action {action!r}")


async def _write_tracking_category(api: XeroApi, db: Session, tenant_id: str, payload: dict) -> dict:
    """Category + options is several Xero calls, so a failure can leave the category
    created with only some options. Look the category up by name first and add only
    the missing options, so a retry completes the write instead of 400ing on a
    duplicate category name."""
    options = payload.pop("Options", [])
    name = str(payload.get("Name", "")).strip().lower()
    existing = next(
        (
            c for c in await api.list_tracking_categories(db, tenant_id)
            if str(c.get("Name", "")).strip().lower() == name
        ),
        None,
    )
    if existing is None:
        category = await api.create_tracking_category(db, tenant_id, payload)
        have: set[str] = set()
    else:
        category = existing
        have = {str(o.get("Name", "")).strip().lower() for o in existing.get("Options") or []}
    for option in options:
        if option.strip().lower() not in have:
            await api.add_tracking_option(
                db, tenant_id, category["TrackingCategoryID"], {"Name": option}
            )
    return category


async def execute_proposal(db: Session, api: XeroApi, proposal: Proposal) -> WriteResult:
    payload = proposal.edited_payload or proposal.mapped_payload
    attempt = len(proposal.write_results) + 1
    try:
        payload = validate_payload(proposal.action, payload)
        response = await _write(api, db, proposal.entity.tenant_id, proposal.action, dict(payload))
        result = WriteResult(
            attempt=attempt,
            success=True,
            request_json=payload,
            response_json=response,
            xero_id=response.get(_ID_FIELDS.get(proposal.action, ""), None),
        )
        proposal.status = "executed"
    except (XeroApiError, ValueError, KeyError) as exc:
        result = WriteResult(
            attempt=attempt,
            success=False,
            request_json=payload if isinstance(payload, dict) else {},
            error=str(exc),
        )
        proposal.status = "failed"
    # Attach via the relationship (not a bare FK) so the in-memory proposal's
    # write_results stays consistent — the approve response serializes it directly.
    proposal.write_results.append(result)
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
