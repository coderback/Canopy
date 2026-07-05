"""Universal ingest engine (Bounty 02 — the "universal translator").

Two LLM passes, both through the injected `Complete` seam so tests run without
credentials:

  Pass 1 — classify_ingest: given the raw file grid, infer *what the file is* and
    normalise it into per-site financial `intents`. No per-source connector — the
    model reads the messy export directly. This is the visible "what is this?" beat.

  Pass 2 — map_ingest_to_journal: for ONE target entity and the intents that belong
    to it, build a balanced double-entry manual journal coded to accounts that
    actually exist in THAT entity's chart. Same EngineProposal contract, same
    deterministic guards and refuse-don't-guess rule as the propagation engine.

The LLM proposes; the balance check (ManualJournalPayload) and the account-code
guard (mapping._guard_referenced_codes) verify; a human approves; code writes.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, Field

from .contracts import EngineProposal
from .mapping import _guard_referenced_codes
from ..models import Entity

Complete = Callable[[str, str, dict], Awaitable[dict]]


# ---- Pass 1: classification contract ---------------------------------------


class IngestIntent(BaseModel):
    """One normalised financial fact extracted from a file row/group."""

    site: str | None = None          # the location/venue the row belongs to
    description: str
    amount: float | None = None
    direction: Literal["revenue", "expense", "cost", "asset", "liability", "other"] = "other"
    suggested_treatment: str | None = None
    needs_review: bool = False       # a required value was missing/ambiguous
    review_reason: str | None = None


class IngestClassification(BaseModel):
    doc_type: str
    human_description: str
    target_action: str = "create-manual-journal"
    intents: list[IngestIntent] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


CLASSIFY_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "doc_type": {
            "type": "string",
            "description": "A short label for what this file is, e.g. 'POS daily revenue settlement' or 'inventory stock count'.",
        },
        "human_description": {
            "type": "string",
            "description": "One sentence a finance user can read: what this file is and what it should become in Xero.",
        },
        "target_action": {
            "type": "string",
            "enum": ["create-manual-journal"],
            "description": "The Xero write this file normalises to (manual journal).",
        },
        "intents": {
            "type": "array",
            "description": "One normalised entry per site/row-group. Group rows by site and sum where sensible.",
            "items": {
                "type": "object",
                "properties": {
                    "site": {"type": "string", "description": "Location/venue name from the file (e.g. Bristol)."},
                    "description": {"type": "string"},
                    "amount": {"type": ["number", "null"], "description": "The monetary amount; null if missing in the file."},
                    "direction": {
                        "type": "string",
                        "enum": ["revenue", "expense", "cost", "asset", "liability", "other"],
                    },
                    "suggested_treatment": {"type": "string", "description": "How this should be booked, in plain words."},
                    "needs_review": {"type": "boolean", "description": "True if a required value was missing/ambiguous in the file."},
                    "review_reason": {"type": ["string", "null"]},
                },
                "required": ["description", "direction", "needs_review"],
                "additionalProperties": False,
            },
        },
        "caveats": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Anything imperfect about the file a human should know (missing values, unclear columns).",
        },
    },
    "required": ["doc_type", "human_description", "target_action", "intents", "caveats"],
    "additionalProperties": False,
}

_CLASSIFY_SYSTEM = (
    "You are Canopy's universal ingest engine. You are given the RAW grid of an "
    "arbitrary business file exported from some other tool (a POS, a stock system, "
    "a spreadsheet). There is no connector and no fixed schema: you must infer what "
    "the file is and normalise it yourself. Rules:\n"
    "1. Work out what the file represents and give it a short doc_type and a plain "
    "one-line human_description.\n"
    "2. The header may not be the first row; there may be title rows, totals rows, "
    "blank trailing columns, and inconsistent spelling/casing. Ignore title/total "
    "rows; do not treat a TOTALS line as a site.\n"
    "3. Produce one intent per site (group and sum rows for the same site where that "
    "is the sensible accounting treatment, e.g. a day's card+cash takings for one "
    "venue). Put the location in `site`.\n"
    "4. If a required number is missing or ambiguous for a row (e.g. a blank unit "
    "cost), set that intent's needs_review=true with a review_reason, and add a "
    "caveat — never invent the number.\n"
    "5. Emit exactly one classification via the tool. You only classify here; you do "
    "not choose Xero account codes yet."
)


async def classify_ingest(complete: Complete, filename: str, grid: str) -> IngestClassification:
    user = (
        f"FILE NAME: {filename}\n\n"
        f"RAW FILE GRID (row-indexed; interpret it yourself):\n{grid}"
    )
    raw = await complete(_CLASSIFY_SYSTEM, user, CLASSIFY_TOOL_SCHEMA)
    return IngestClassification.model_validate(raw)


# ---- Pass 2: per-entity manual-journal mapping -----------------------------


JOURNAL_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["create-manual-journal"]},
        "mapped_payload": {
            "type": "object",
            "description": (
                "A Xero ManualJournal for THIS entity. Must contain Narration and "
                "JournalLines (each with LineAmount, AccountCode, Description). Debits "
                "are positive LineAmount, credits negative; the lines MUST sum to zero."
            ),
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string", "description": "One or two sentences a human can audit."},
        "needs_human": {"type": "boolean", "description": "True if no valid account pairing exists here; never guess a code."},
    },
    "required": ["action", "mapped_payload", "confidence", "reasoning", "needs_human"],
    "additionalProperties": False,
}

_JOURNAL_SYSTEM = (
    "You are Canopy's ingest-to-journal engine. Turn normalised financial intents "
    "for ONE Xero organisation into ONE balanced manual journal, using only account "
    "codes that already exist in that organisation's chart. Rules you must never break:\n"
    "1. Never invent an account code. Use codes exactly as they appear in the "
    "provided snapshot. If no sensible account exists for a side of the entry, set "
    "needs_human=true and explain — do not guess.\n"
    "2. Double entry: debits are POSITIVE LineAmount, credits are NEGATIVE, and all "
    "JournalLines MUST sum to exactly zero.\n"
    "3. Book revenue as a credit to a revenue/sales account and a matching debit to a "
    "receivable/debtors or clearing account. Book a cost/stock consumption as a debit "
    "to a cost/expense account and a matching credit. Choose the closest existing "
    "accounts in THIS entity's snapshot.\n"
    "4. Do NOT post to bank accounts (AccountType BANK) — Xero rejects manual journals "
    "against bank accounts. Prefer receivable/clearing/GL accounts.\n"
    "5. If any intent is flagged needs_review (a missing/ambiguous value), exclude that "
    "line and set needs_human=true so a person decides, rather than booking a guess.\n"
    "6. Set confidence honestly. Emit exactly one proposal via the tool. You propose; a "
    "human approves; deterministic code writes."
)


def _build_journal_user_message(
    classification: IngestClassification, intents: list[IngestIntent], entity: Entity, snapshot: dict
) -> str:
    return (
        f"FILE: {classification.doc_type} — {classification.human_description}\n\n"
        f"TARGET ENTITY: {entity.name} (tenant {entity.tenant_id}).\n\n"
        f"INTENTS FOR THIS ENTITY (already grouped to its site):\n"
        f"{json.dumps([i.model_dump() for i in intents], indent=2, default=str)}\n\n"
        f"TARGET ENTITY SNAPSHOT (only these codes/ids exist here):\n"
        f"{json.dumps(snapshot, indent=2, default=str)}"
    )


async def map_ingest_to_journal(
    complete: Complete,
    classification: IngestClassification,
    intents: list[IngestIntent],
    entity: Entity,
    snapshot: dict,
) -> EngineProposal:
    """Build one balanced manual-journal proposal for one entity. Raises if the
    model's answer fails the EngineProposal contract."""
    user = _build_journal_user_message(classification, intents, entity, snapshot)
    raw = await complete(_JOURNAL_SYSTEM, user, JOURNAL_TOOL_SCHEMA)
    proposal = EngineProposal.model_validate(raw)
    # Any intent that couldn't be resolved cleanly must block approval.
    if any(i.needs_review for i in intents) and not proposal.needs_human:
        proposal.needs_human = True
        proposal.confidence = min(proposal.confidence, 0.4)
        reasons = "; ".join(i.review_reason or i.description for i in intents if i.needs_review)
        proposal.reasoning += (
            f" [Canopy guard: source rows need review ({reasons}) — flagged for a human "
            f"rather than booking a guessed amount.]"
        )
    # Reuse the propagation backstop: every referenced code must exist in the target.
    _guard_referenced_codes(proposal, entity, snapshot)
    return proposal
