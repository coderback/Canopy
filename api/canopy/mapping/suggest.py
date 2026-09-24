"""AI suggestions for accounts the deterministic matcher couldn't place.

One batched call per org: the group standard plus that org's unmatched
accounts. Only account metadata is sent (codes, names, types) — no contacts,
no amounts, no personal data. The model may answer "no group equivalent".
Every answer then passes deterministic guards, and every result is only a
*suggestion* until a person confirms it.
"""

from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from .matcher import AI, LocalAccount, Match, StandardAccount, account_class

Complete = Callable[[str, str, dict], Awaitable[dict]]

MAX_BATCH = 150  # keep prompts small; larger charts are split into batches

SUGGEST_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "local_ref": {"type": "string", "description": "The L-reference of the org account."},
                    "group_code": {
                        "type": ["string", "null"],
                        "description": "Group account code it corresponds to, or null if none fits.",
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reasoning": {"type": "string", "description": "One sentence a finance person can check."},
                },
                "required": ["local_ref", "group_code", "confidence", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}

SYSTEM = (
    "You map one organisation's chart of accounts onto a group's standard chart of accounts. "
    "For each org account, pick the single group account that represents the same thing for "
    "consolidated reporting, or null if none does. Rules:\n"
    "1. Use only group codes from the list given. Never invent a code.\n"
    "2. Never map across account classes (revenue, expense, asset, liability, equity).\n"
    "3. Prefer null over a weak guess: an org-specific account with no group equivalent is normal.\n"
    "4. Confidence is honest: high only when the meaning is unambiguous.\n"
    "5. Answer every L-reference exactly once via the tool. A human reviews every suggestion."
)


class _Suggestion(BaseModel):
    local_ref: str
    group_code: str | None
    confidence: float = Field(ge=0, le=1)
    reasoning: str


class _Answer(BaseModel):
    suggestions: list[_Suggestion]


def _prompt(local: list[LocalAccount], standard: list[StandardAccount]) -> tuple[str, dict[str, LocalAccount]]:
    refs = {f"L{i}": a for i, a in enumerate(local, start=1)}
    group_lines = "\n".join(f"{g.code} | {g.name} | {g.type} | {g.account_class}" for g in standard)
    local_lines = "\n".join(
        f"{ref} | {a.code or '-'} | {a.name} | {a.type} | {account_class(a.type, a.account_class) or '?'}"
        for ref, a in refs.items()
    )
    user = (
        "GROUP STANDARD (code | name | type | class):\n"
        f"{group_lines}\n\n"
        "ORG ACCOUNTS TO MAP (ref | code | name | type | class):\n"
        f"{local_lines}"
    )
    return user, refs


def _guarded(s: _Suggestion, acct: LocalAccount, by_code: dict[str, StandardAccount]) -> Match:
    """Deterministic backstops on the model's answer."""
    if s.group_code is None:
        return Match(acct.id, None, AI, s.confidence, f"No group equivalent: {s.reasoning}")
    group = by_code.get(s.group_code.strip())
    if group is None:
        return Match(acct.id, None, AI, 0.0,
                     f"[Canopy guard: suggested group code {s.group_code!r} doesn't exist; discarded.] {s.reasoning}")
    local_class = account_class(acct.type, acct.account_class)
    if local_class and local_class != group.account_class:
        return Match(acct.id, None, AI, 0.0,
                     f"[Canopy guard: {local_class} account can't map to {group.account_class} group "
                     f"account {group.code}; discarded.] {s.reasoning}")
    return Match(acct.id, group.id, AI, s.confidence, s.reasoning)


async def suggest(
    complete: Complete, local: list[LocalAccount], standard: list[StandardAccount]
) -> list[Match]:
    """AI-backed suggestions for `local`. Accounts the model skips come back as
    unmatched (group None, confidence 0) so every account gets a row to review."""
    if not local or not standard:
        return [Match(a.id, None, AI, 0.0, "No group standard to compare against.") for a in local]
    by_code = {g.code.strip(): g for g in standard}
    results: dict = {}
    for start in range(0, len(local), MAX_BATCH):
        batch = local[start : start + MAX_BATCH]
        user, refs = _prompt(batch, standard)
        answer = _Answer.model_validate(await complete(SYSTEM, user, SUGGEST_TOOL_SCHEMA))
        for s in answer.suggestions:
            acct = refs.get(s.local_ref)
            if acct is not None and acct.id not in results:
                results[acct.id] = _guarded(s, acct, by_code)
    return [
        results.get(a.id) or Match(a.id, None, AI, 0.0, "The model gave no answer for this account.")
        for a in local
    ]
