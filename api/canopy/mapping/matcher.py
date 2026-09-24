"""Deterministic mapping of one org's accounts onto the group standard.

Pure functions over plain data (no DB, no LLM) so every rule is unit-testable.
Order of passes, each only considering what earlier passes left unmatched:

1. exact     — same code AND same name (case/space-insensitive)   → confidence 1.0
2. name      — same normalised name, different code               → 0.9
               (a coding-scheme difference: the hackathon's name-aware drift rule)
3. code_conflict — same code, different name                       → 0.4, flagged
               (maybe renamed, maybe a different account reusing the number;
                a human must decide, so it is never auto-confirmed)
4. whatever remains goes to the AI suggester (mapping/suggest.py).

Account class must be compatible for any match: an org's REVENUE account can
never map to a group EXPENSE account, whatever the names say.
"""

import re
import uuid
from dataclasses import dataclass

EXACT, NAME, CODE_CONFLICT, AI, MANUAL = "exact", "name", "code_conflict", "ai", "manual"

# Xero account Type -> Class, for accounts synced without a Class.
TYPE_CLASS = {
    "BANK": "ASSET", "CURRENT": "ASSET", "CURRLIAB": "LIABILITY", "DEPRECIATN": "EXPENSE",
    "DIRECTCOSTS": "EXPENSE", "EQUITY": "EQUITY", "EXPENSE": "EXPENSE", "FIXED": "ASSET",
    "INVENTORY": "ASSET", "LIABILITY": "LIABILITY", "NONCURRENT": "ASSET", "OTHERINCOME": "REVENUE",
    "OVERHEADS": "EXPENSE", "PREPAYMENT": "ASSET", "REVENUE": "REVENUE", "SALES": "REVENUE",
    "TERMLIAB": "LIABILITY", "PAYGLIABILITY": "LIABILITY", "SUPERANNUATIONEXPENSE": "EXPENSE",
    "SUPERANNUATIONLIABILITY": "LIABILITY", "WAGESEXPENSE": "EXPENSE",
}


@dataclass(frozen=True)
class LocalAccount:
    id: uuid.UUID
    code: str | None
    name: str
    type: str
    account_class: str | None


@dataclass(frozen=True)
class StandardAccount:
    id: uuid.UUID
    code: str
    name: str
    type: str
    account_class: str


@dataclass(frozen=True)
class Match:
    local_id: uuid.UUID
    group_id: uuid.UUID | None
    source: str
    confidence: float
    reasoning: str


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def account_class(type_: str, explicit: str | None) -> str | None:
    return explicit or TYPE_CLASS.get((type_ or "").upper())


def compatible(local: LocalAccount, group: StandardAccount) -> bool:
    lc = account_class(local.type, local.account_class)
    return lc is None or lc == group.account_class


def match_accounts(
    local: list[LocalAccount], standard: list[StandardAccount]
) -> tuple[list[Match], list[LocalAccount]]:
    """Return (deterministic matches, accounts left for the AI)."""
    by_code = {g.code.strip(): g for g in standard}
    by_name: dict[str, list[StandardAccount]] = {}
    for g in standard:
        by_name.setdefault(normalise(g.name), []).append(g)

    matches: list[Match] = []
    remaining: list[LocalAccount] = []
    for acct in local:
        code = (acct.code or "").strip()
        name_key = normalise(acct.name)
        same_code = by_code.get(code) if code else None
        if same_code and normalise(same_code.name) == name_key and compatible(acct, same_code):
            matches.append(Match(acct.id, same_code.id, EXACT, 1.0, "Same code and name as the group account."))
            continue
        named = [g for g in by_name.get(name_key, []) if compatible(acct, g)]
        if len(named) == 1:
            g = named[0]
            matches.append(
                Match(acct.id, g.id, NAME, 0.9,
                      f"Same name as group {g.code} under a different code ({code or 'no code'}): "
                      f"a coding-scheme difference.")
            )
            continue
        if same_code and compatible(acct, same_code):
            matches.append(
                Match(acct.id, same_code.id, CODE_CONFLICT, 0.4,
                      f"Code {code} matches group '{same_code.name}' but this org calls it "
                      f"'{acct.name}'. Renamed, or a different account reusing the code? Needs a human.")
            )
            continue
        remaining.append(acct)
    return matches, remaining
