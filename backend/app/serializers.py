"""Shared JSON serializers for runs and proposals.

Both the changes fan-out router and the runs/approval router return the same
run shape so the approval UI consumes exactly one schema.
"""

from .models import Proposal, Run


def proposal_dict(p: Proposal) -> dict:
    return {
        "id": p.id,
        "entity_id": p.entity_id,
        "entity_name": p.entity.name if p.entity else None,
        "action": p.action,
        "mapped_payload": p.mapped_payload,
        "edited_payload": p.edited_payload,
        "confidence": p.confidence,
        "reasoning": p.reasoning,
        "needs_human": p.needs_human,
        "status": p.status,
        "results": [
            {
                "attempt": r.attempt,
                "success": r.success,
                "error": r.error,
                "xero_id": r.xero_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in p.write_results
        ],
    }


def run_dict(run: Run, include_proposals: bool = True) -> dict:
    data = {
        "id": run.id,
        "kind": run.kind,
        "change_type": run.change_type,
        "status": run.status,
        "source_payload": run.source_payload,
        "created_at": run.created_at.isoformat(),
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if include_proposals:
        data["proposals"] = [proposal_dict(p) for p in run.proposals]
    return data
