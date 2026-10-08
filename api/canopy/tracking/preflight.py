"""Deterministic checks for tracking-category changes, run at submit and again
just before writing (see changes/preflight.py for accounts). Pure functions over
plain data; an empty list means the item may run.

Xero's rules this encodes: at most two ACTIVE categories per org and four in
total (archived count); names 1-100 characters; names unique among an org's
categories, and among a category's options, archived ones included.
"""

from dataclasses import dataclass, field

from .models import MAX_ACTIVE_CATEGORIES, MAX_CATEGORIES, MAX_NAME

CREATE_CATEGORY, CREATE_OPTION = "create_tracking_category", "create_tracking_option"
UPDATE_CATEGORY, UPDATE_OPTION = "update_tracking_category", "update_tracking_option"
ARCHIVE_CATEGORY, ARCHIVE_OPTION = "archive_tracking_category", "archive_tracking_option"
OPERATIONS = (CREATE_CATEGORY, CREATE_OPTION, UPDATE_CATEGORY, UPDATE_OPTION, ARCHIVE_CATEGORY, ARCHIVE_OPTION)
CATEGORY_TARGET = (UPDATE_CATEGORY, ARCHIVE_CATEGORY, CREATE_OPTION)
OPTION_TARGET = (UPDATE_OPTION, ARCHIVE_OPTION)


@dataclass(frozen=True)
class OrgOption:
    xero_option_id: str
    name: str
    status: str  # ACTIVE | ARCHIVED


@dataclass(frozen=True)
class OrgCategory:
    xero_category_id: str
    name: str
    status: str  # ACTIVE | ARCHIVED
    options: tuple[OrgOption, ...] = ()


@dataclass(frozen=True)
class OrgTracking:
    name: str  # the organisation's name, for messages
    categories: list[OrgCategory] = field(default_factory=list)
    can_write: bool = True


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _archived(status: str) -> str:
    return " (archived)" if status == "ARCHIVED" else ""


def _name(value, what: str) -> list[str]:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_NAME:
        return [f"A {what} name must be 1–{MAX_NAME} characters."]
    return []


def _category_clash(org: OrgTracking, name: str, ignore: str | None = None) -> list[str]:
    for c in org.categories:
        if c.xero_category_id != ignore and _norm(c.name) == _norm(name):
            return [f"A tracking category named '{c.name}' already exists in {org.name}{_archived(c.status)}."]
    return []


def _option_clash(category: OrgCategory, org: OrgTracking, name: str, ignore: str | None = None) -> list[str]:
    for o in category.options:
        if o.xero_option_id != ignore and _norm(o.name) == _norm(name):
            return [f"'{category.name}' in {org.name} already has an option named '{o.name}'{_archived(o.status)}."]
    return []


def _limits(org: OrgTracking) -> list[str]:
    active = [c.name for c in org.categories if c.status == "ACTIVE"]
    if len(active) >= MAX_ACTIVE_CATEGORIES:
        return [f"{org.name} already has {len(active)} active tracking categories ({', '.join(active)}), "
                "Xero's maximum. Archive one first."]
    if len(org.categories) >= MAX_CATEGORIES:
        return [f"{org.name} already has {len(org.categories)} tracking categories including archived ones, "
                "Xero's maximum."]
    return []


def _options(payload: dict) -> tuple[list[str], list[str]]:
    """(option names, problems) for a create-category payload."""
    options = payload.get("options") or []
    if not isinstance(options, list):
        return [], ["Options must be a list of names."]
    problems, seen = [], set()
    for o in options:
        problems += _name(o, "option")
        if isinstance(o, str):
            if _norm(o) in seen:
                problems.append(f"Option '{o.strip()}' is listed twice.")
            seen.add(_norm(o))
    return [o for o in options if isinstance(o, str)], problems


def check(
    operation: str,
    payload: dict,
    org: OrgTracking,
    *,
    category: OrgCategory | None = None,
    option: OrgOption | None = None,
) -> list[str]:
    """`category` is the target category (and, for a create that already wrote
    its category on an earlier attempt, that category: the run resumes by adding
    only the missing options). `option` is the target option."""
    problems: list[str] = []
    if not org.can_write:
        problems.append(f"Canopy doesn't have write access to {org.name}. Reconnect it with write access.")

    if operation == CREATE_CATEGORY:
        problems += _name(payload.get("name"), "tracking category")
        _, option_problems = _options(payload)
        problems += option_problems
        if category is not None:  # resuming our own half-finished create
            return problems
        if isinstance(payload.get("name"), str):
            problems += _category_clash(org, payload["name"])
        return problems + _limits(org)

    if operation in CATEGORY_TARGET:
        if category is None:
            return problems + [f"That tracking category no longer exists in {org.name}."]
        if category.status == "ARCHIVED":
            verb = "archived" if operation == ARCHIVE_CATEGORY else "archived; unarchive it in Xero first"
            return problems + [f"'{category.name}' is already {verb} ({org.name})."]
        if operation == ARCHIVE_CATEGORY:
            return problems
        if operation == CREATE_OPTION:
            problems += _name(payload.get("name"), "option")
            if isinstance(payload.get("name"), str):
                problems += _option_clash(category, org, payload["name"])
            return problems
        return problems + _rename(payload, category.name, "tracking category",
                                  lambda n: _category_clash(org, n, ignore=category.xero_category_id))

    if operation in OPTION_TARGET:
        if option is None or category is None:
            return problems + [f"That tracking option no longer exists in {org.name}."]
        if option.status == "ARCHIVED":
            verb = "archived" if operation == ARCHIVE_OPTION else "archived; unarchive it in Xero first"
            return problems + [f"'{option.name}' is already {verb} ({org.name})."]
        if operation == ARCHIVE_OPTION:
            return problems
        return problems + _rename(payload, option.name, "option",
                                  lambda n: _option_clash(category, org, n, ignore=option.xero_option_id))

    return problems + [f"Unknown operation {operation!r}."]


def _rename(payload: dict, current: str, what: str, clash) -> list[str]:
    unknown = set(payload) - {"name"}
    if unknown:
        return [f"Only the name of a {what} can be changed here."]
    name = payload.get("name")
    problems = _name(name, what)
    if problems:
        return problems
    if name.strip() == current:
        return ["Nothing would change."]
    return clash(name)
