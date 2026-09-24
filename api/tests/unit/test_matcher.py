import uuid

from canopy.mapping.matcher import (
    CODE_CONFLICT,
    EXACT,
    NAME,
    LocalAccount,
    StandardAccount,
    match_accounts,
)


def g(code, name, type_="EXPENSE", cls="EXPENSE"):
    return StandardAccount(uuid.uuid4(), code, name, type_, cls)


def loc(code, name, type_="EXPENSE", cls=None):
    return LocalAccount(uuid.uuid4(), code, name, type_, cls)


STANDARD = [
    g("200", "Sales", "REVENUE", "REVENUE"),
    g("400", "Advertising"),
    g("897", "Software Subscriptions"),
]


def test_exact_code_and_name_matches_with_full_confidence():
    a = loc("400", "advertising ")  # case/space-insensitive
    matches, remaining = match_accounts([a], STANDARD)
    assert remaining == []
    (m,) = matches
    assert (m.source, m.confidence, m.group_id) == (EXACT, 1.0, STANDARD[1].id)


def test_same_name_different_code_is_a_coding_scheme_difference():
    a = loc("8100", "Software Subscriptions")
    (m,), _ = match_accounts([a], STANDARD)
    assert m.source == NAME and m.group_id == STANDARD[2].id and m.confidence == 0.9


def test_same_code_different_name_is_flagged_not_trusted():
    a = loc("400", "Marketing & PR")
    (m,), _ = match_accounts([a], STANDARD)
    assert m.source == CODE_CONFLICT and m.confidence < 0.5 and m.group_id == STANDARD[1].id


def test_never_matches_across_account_classes():
    # Same code and name as group REVENUE "Sales" but it's an expense account here.
    a = loc("200", "Sales", type_="EXPENSE")
    matches, remaining = match_accounts([a], STANDARD)
    assert matches == [] and remaining == [a]


def test_unrecognised_accounts_are_left_for_the_ai():
    a = loc("650", "Trampoline Park Insurance")
    matches, remaining = match_accounts([a], STANDARD)
    assert matches == [] and remaining == [a]


def test_ambiguous_name_across_two_group_codes_is_not_guessed():
    standard = STANDARD + [g("401", "Advertising")]
    a = loc("999", "Advertising")
    matches, remaining = match_accounts([a], standard)
    assert matches == [] and remaining == [a]
