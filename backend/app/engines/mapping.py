"""Per-entity mapping engine (Bounty 01 propagation core).

For one source change and one target entity's live reference data, ask the LLM
to produce exactly one `EngineProposal`: the action to take, a Xero-ready
payload mapped to *that entity's* chart of accounts / tax rates / contacts, a
confidence, human-readable reasoning, and a `needs_human` flag.

Hard rule enforced by the prompt AND by validation: the model proposes, it may
never invent an account/tax code. If nothing in the target snapshot fits, it
must refuse (`needs_human=true`) rather than guess. The returned JSON is parsed
through `EngineProposal` (contracts.py) so a malformed answer fails loudly
before anything is persisted or written.
"""

import json
from collections.abc import Awaitable, Callable

from .contracts import EngineProposal
from ..models import Entity

Complete = Callable[[str, str, dict], Awaitable[dict]]

# JSON-schema mirror of EngineProposal — the single tool the model may call.
PROPOSAL_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "create-contact",
                "create-item",
                "create-account",
                "create-tracking-category",
            ],
            "description": "The Xero write this proposal represents.",
        },
        "mapped_payload": {
            "type": "object",
            "description": "Xero-ready payload using codes/ids that exist in THIS entity.",
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {
            "type": "string",
            "description": "One or two sentences a human can audit.",
        },
        "needs_human": {
            "type": "boolean",
            "description": "True if the mapping is ambiguous or impossible; never guess a code.",
        },
    },
    "required": ["action", "mapped_payload", "confidence", "reasoning", "needs_human"],
    "additionalProperties": False,
}

_ACTION_BY_TYPE = {
    "contact": "create-contact",
    "item": "create-item",
    "account": "create-account",
    "tracking": "create-tracking-category",
}

_BASE_SYSTEM = (
    "You are Canopy's mapping engine. You translate ONE change so it applies "
    "correctly to ONE specific Xero organisation, using only reference data that "
    "already exists in that organisation. Rules you must never break:\n"
    "1. Never invent an account code, tax type, or tracking id. If no existing "
    "target fits, set needs_human=true and explain what is missing — do not guess.\n"
    "2. Return codes/ids exactly as they appear in the provided snapshot.\n"
    "3. Emit exactly one proposal via the emit_proposal tool. You propose; a human "
    "approves; deterministic code writes. You never write to Xero yourself.\n"
    "4. Set confidence honestly: high only when an exact, unambiguous target exists.\n"
    "5. Self-consistency check before you answer: EVERY account code and tax type in "
    "mapped_payload must appear verbatim in this entity's snapshot. If your reasoning "
    "says you remapped a code (e.g. 300 -> 310), the payload MUST contain the remapped "
    "code (310), never the original source code."
)

_TYPE_GUIDANCE = {
    "item": (
        "Change type: ITEM (action create-item). Map BOTH SalesDetails and "
        "PurchaseDetails the same way: their AccountCode and TaxType must be codes that "
        "exist in this entity's accounts/tax_rates. If the source sells to '200 Sales' "
        "but this entity has no active 200, map to the equivalent active revenue account "
        "(e.g. '201 Trading Income'). If the source purchases to '300' and no active 300 "
        "exists, map to the equivalent active direct-cost/expense account (e.g. '310 Cost "
        "of Goods Sold') AND put that remapped code in PurchaseDetails.AccountCode. If an "
        "entity has NO suitable active account for a side, refuse (needs_human=true). Keep "
        "the item Code and Name identical to the source."
    ),
    "account": (
        "Change type: ACCOUNT (action create-account). Propagate the new account. "
        "Keep Code and Name; map Type to a valid Xero AccountType and TaxType to one "
        "present in this entity's tax_rates. If the Code already exists here, refuse "
        "(needs_human=true) so a human decides."
    ),
    "contact": (
        "Change type: CONTACT (action create-contact). Deduplicate against this "
        "entity's contacts snapshot: if a clearly-the-same contact already exists "
        "(name variants like 'Acme Corp' vs 'Acme Corporation Ltd'), put its exact "
        "ContactID in mapped_payload so this links/updates instead of creating a "
        "duplicate, and say so in reasoning. Otherwise create new (no ContactID)."
    ),
    "tracking": (
        "Change type: TRACKING (action create-tracking-category). If a category with "
        "this Name already exists here, refuse (needs_human=true). Otherwise propose "
        "the category with its Options."
    ),
}


def _referenced_account_codes(action: str, payload: dict) -> list[str]:
    """Account codes the payload will write against — must exist in the target."""
    codes: list[str] = []
    if action == "create-item":
        for side in ("SalesDetails", "PurchaseDetails"):
            details = payload.get(side)
            if isinstance(details, dict) and details.get("AccountCode") is not None:
                codes.append(str(details["AccountCode"]))
    return codes


def _snapshot_account_codes(snapshot: dict) -> set[str]:
    return {
        str(a["Code"])
        for a in snapshot.get("accounts", [])
        if isinstance(a, dict) and a.get("Code") is not None
    }


def _guard_referenced_codes(proposal: EngineProposal, entity: Entity, snapshot: dict) -> None:
    """Deterministic backstop: the LLM may reason correctly but emit a payload that
    references a code not in the target (observed with gpt-5.4-mini leaving a source
    code in PurchaseDetails despite remapping it in prose). Any such code can't be
    written — force needs_human so it blocks approval instead of failing at write time.
    """
    known = _snapshot_account_codes(snapshot)
    missing = [c for c in _referenced_account_codes(proposal.action, proposal.mapped_payload) if c not in known]
    if missing and not proposal.needs_human:
        proposal.needs_human = True
        proposal.confidence = min(proposal.confidence, 0.4)
        proposal.reasoning += (
            f" [Canopy guard: account code(s) {sorted(set(missing))} in the mapped payload "
            f"do not exist in {entity.name}'s chart — flagged for human review rather than "
            f"a guaranteed write failure.]"
        )


def _build_user_message(change_type: str, source_payload: dict, entity: Entity, snapshot: dict) -> str:
    return (
        f"{_TYPE_GUIDANCE[change_type]}\n\n"
        f"TARGET ENTITY: {entity.name} (tenant {entity.tenant_id}).\n\n"
        f"SOURCE CHANGE:\n{json.dumps(source_payload, indent=2)}\n\n"
        f"TARGET ENTITY SNAPSHOT (only these codes/ids exist here):\n"
        f"{json.dumps(snapshot, indent=2, default=str)}"
    )


async def map_change(
    complete: Complete,
    change_type: str,
    source_payload: dict,
    entity: Entity,
    snapshot: dict,
) -> EngineProposal:
    """Map one source change onto one entity. Raises if `change_type` is unknown
    or the model's answer fails the EngineProposal contract."""
    if change_type not in _ACTION_BY_TYPE:
        raise ValueError(f"unknown change_type {change_type!r}")
    system = f"{_BASE_SYSTEM}\n\n{_TYPE_GUIDANCE[change_type]}"
    user = _build_user_message(change_type, source_payload, entity, snapshot)
    raw = await complete(system, user, PROPOSAL_TOOL_SCHEMA)
    proposal = EngineProposal.model_validate(raw)
    _guard_referenced_codes(proposal, entity, snapshot)
    return proposal
