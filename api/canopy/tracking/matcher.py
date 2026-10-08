"""Deterministic mapping of an org's tracking categories and options onto the
group standard. Pure functions over plain data (no DB), like mapping/matcher.py.

Names only, normalised the same way as account names ("Sales & Marketing" ==
"Sales and Marketing"). Anything without an exact name match is left for a
person to assign: tracking lists are short, so no AI pass.

Options are matched only within the group category their own category maps to,
so "London" under Region never lands on "London" under some other category.
"""

import uuid
from dataclasses import dataclass

from ..mapping.matcher import EXACT, UNMATCHED, Match, normalise


@dataclass(frozen=True)
class Named:
    id: uuid.UUID
    name: str


def _by_name(items: list[Named]) -> dict[str, Named]:
    out: dict[str, Named] = {}
    for item in items:
        out.setdefault(normalise(item.name), item)
    return out


def match_categories(local: list[Named], standard: list[Named]) -> list[Match]:
    by_name = _by_name(standard)
    out = []
    for c in local:
        g = by_name.get(normalise(c.name))
        if g:
            out.append(Match(c.id, g.id, EXACT, 1.0, "Same name as the group category."))
        else:
            out.append(Match(c.id, None, UNMATCHED, 0.0,
                             "No group category with this name. Choose one, or mark it local-only."))
    return out


def match_options(local: list[Named], group_options: list[Named], group_category_name: str | None) -> list[Match]:
    """`local` are the options of ONE org category; `group_options` those of the
    group category it maps to (empty when it maps to none)."""
    by_name = _by_name(group_options)
    out = []
    for o in local:
        g = by_name.get(normalise(o.name))
        if g:
            out.append(Match(o.id, g.id, EXACT, 1.0, "Same name as the group option."))
        elif group_category_name is None:
            out.append(Match(o.id, None, UNMATCHED, 0.0,
                             "Its category isn't mapped to a group category yet."))
        else:
            out.append(Match(o.id, None, UNMATCHED, 0.0,
                             f"No option with this name in the group's '{group_category_name}'. "
                             "Choose one, or mark it local-only."))
    return out
