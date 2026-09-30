"""Deterministic checks run before any write to Xero — at submit, and again at
execution against a fresh read — so nothing is written that Xero would reject or
that no longer makes sense. Pure functions over plain data; no DB, no network.

`check()` returns human-readable reasons; an empty list means the item may run.
"""

from dataclasses import dataclass, field

from ..mapping.matcher import TYPE_CLASS, account_class

CREATE, UPDATE, ARCHIVE = "create_account", "update_account", "archive_account"
EDITABLE_FIELDS = ("code", "name", "description", "tax_type")
MAX_CODE, MAX_NAME = 10, 150  # Xero's limits on account Code and Name

# Which tax-rate flag must be true for an account of each class.
CLASS_TAX_FLAG = {
    "REVENUE": "revenue", "EXPENSE": "expenses", "ASSET": "assets",
    "LIABILITY": "liabilities", "EQUITY": "equity",
}


@dataclass(frozen=True)
class OrgAccount:
    xero_account_id: str
    code: str | None
    name: str
    type: str
    account_class: str | None
    status: str  # ACTIVE | ARCHIVED
    system_account: str | None = None
    tax_type: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class OrgTaxRate:
    tax_type: str
    status: str
    applies: dict = field(default_factory=dict)  # class flag -> bool | None


@dataclass(frozen=True)
class OrgState:
    name: str
    accounts: list[OrgAccount]
    tax_rates: list[OrgTaxRate]
    can_write: bool


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _clash(org: OrgState, *, code: str | None, name: str | None, ignore: str | None) -> list[str]:
    """Xero requires code AND name to be unique across ALL accounts, archived included."""
    out = []
    for a in org.accounts:
        if a.xero_account_id == ignore:
            continue
        label = f"'{a.name}'" + (" (archived)" if a.status == "ARCHIVED" else "")
        if code and a.code and a.code.strip().upper() == code.strip().upper():
            out.append(f"Code {code} is already used by {label} in {org.name}.")
        if name and _norm(a.name) == _norm(name):
            out.append(f"An account named '{name}' already exists in {org.name}" +
                       (" (archived)." if a.status == "ARCHIVED" else "."))
    return out


def _tax(org: OrgState, tax_type: str | None, cls: str | None) -> list[str]:
    if not tax_type:
        return []
    rate = next((t for t in org.tax_rates if t.tax_type == tax_type), None)
    if rate is None:
        return [f"Tax type {tax_type} doesn't exist in {org.name}. Choose one of its tax rates."]
    if rate.status != "ACTIVE":
        return [f"Tax type {tax_type} is {rate.status.lower()} in {org.name}."]
    flag = CLASS_TAX_FLAG.get(cls or "")
    if flag and rate.applies.get(flag) is False:
        return [f"Tax type {tax_type} can't be used on {cls.lower()} accounts in {org.name}."]
    return []


def _fields(code: str | None, name: str | None) -> list[str]:
    out = []
    if code is not None and (not code.strip() or len(code.strip()) > MAX_CODE):
        out.append(f"Account code must be 1–{MAX_CODE} characters.")
    if name is not None and (not name.strip() or len(name.strip()) > MAX_NAME):
        out.append(f"Account name must be 1–{MAX_NAME} characters.")
    return out


def check(operation: str, payload: dict, target: OrgAccount | None, org: OrgState) -> list[str]:
    problems: list[str] = []
    if not org.can_write:
        problems.append(f"Canopy doesn't have write access to {org.name}. Reconnect it with write access.")

    if operation == CREATE:
        code, name, type_ = payload.get("code"), payload.get("name"), (payload.get("type") or "").upper()
        if code is None or name is None:
            problems.append("A new account needs a code and a name.")
        problems += _fields(code, name)
        if type_ not in TYPE_CLASS:
            problems.append(f"'{type_ or '(none)'}' isn't a Xero account type.")
        elif type_ == "BANK":
            problems.append("Bank accounts need bank details and must be created in Xero itself.")
        problems += _clash(org, code=code, name=name, ignore=None)
        problems += _tax(org, payload.get("tax_type"), account_class(type_, None))
        return problems

    if target is None:
        return problems + [f"The account no longer exists in {org.name}."]
    if target.system_account:
        return problems + [f"'{target.name}' is a Xero system account ({target.system_account}); "
                           "Xero doesn't allow it to be changed or archived."]
    if target.status == "ARCHIVED":
        return problems + [f"'{target.name}' is already archived in {org.name}."]

    if operation == ARCHIVE:
        if target.type == "BANK":
            problems.append("Bank accounts are archived from Xero's bank account settings, not the chart.")
        return problems

    if operation == UPDATE:
        changes = {k: v for k, v in payload.items() if k in EDITABLE_FIELDS}
        unknown = set(payload) - set(EDITABLE_FIELDS)
        if unknown:
            problems.append(f"Can't change {', '.join(sorted(unknown))} here.")
        current = {"code": target.code, "name": target.name, "tax_type": target.tax_type,
                   "description": target.description}
        if not any(v != current[k] for k, v in changes.items()):
            problems.append("Nothing would change.")
        problems += _fields(changes.get("code"), changes.get("name"))
        problems += _clash(org, code=changes.get("code"), name=changes.get("name"), ignore=target.xero_account_id)
        if "tax_type" in changes:
            problems += _tax(org, changes["tax_type"], account_class(target.type, target.account_class))
        return problems

    return problems + [f"Unknown operation {operation!r}."]


def xero_fields(operation: str, payload: dict) -> dict:
    """Translate an item payload into Xero's field names for the write."""
    names = {"code": "Code", "name": "Name", "type": "Type", "tax_type": "TaxType", "description": "Description"}
    if operation == ARCHIVE:
        return {"Status": "ARCHIVED"}
    out = {names[k]: v for k, v in payload.items() if k in names and v is not None}
    if operation == CREATE and "Type" in out:
        out["Type"] = out["Type"].upper()
    return out
