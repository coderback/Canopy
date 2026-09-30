from canopy.changes.preflight import (
    ARCHIVE,
    CREATE,
    UPDATE,
    OrgAccount,
    OrgState,
    OrgTaxRate,
    check,
    xero_fields,
)


def acct(aid, code, name, type_="OVERHEADS", status="ACTIVE", system=None, tax=None, cls="EXPENSE"):
    return OrgAccount(aid, code, name, type_, cls, status, system, tax)


RATES = [
    OrgTaxRate("INPUT2", "ACTIVE", {"expenses": True, "revenue": False}),
    OrgTaxRate("OUTPUT2", "ACTIVE", {"expenses": False, "revenue": True}),
    OrgTaxRate("OLDVAT", "DELETED", {"expenses": True}),
]


def org(accounts=(), can_write=True):
    return OrgState("Org B", list(accounts), RATES, can_write)


NEW = {"code": "489", "name": "Telephone", "type": "OVERHEADS", "tax_type": "INPUT2"}


def test_a_valid_create_passes():
    assert check(CREATE, NEW, None, org([acct("a1", "400", "Advertising")])) == []


def test_create_code_clash_includes_archived_accounts():
    problems = check(CREATE, NEW, None, org([acct("a1", "489", "Old phone", status="ARCHIVED")]))
    assert problems == ["Code 489 is already used by 'Old phone' (archived) in Org B."]


def test_create_name_clash_is_case_insensitive():
    (p,) = check(CREATE, NEW, None, org([acct("a1", "999", "TELEPHONE ")]))
    assert "already exists" in p


def test_create_bank_account_is_refused():
    assert any("Bank accounts" in p for p in check(CREATE, {**NEW, "type": "BANK", "tax_type": None}, None, org()))


def test_create_unknown_type_and_bad_lengths():
    problems = check(CREATE, {"code": "12345678901", "name": "x", "type": "NOPE"}, None, org())
    assert any("1–10 characters" in p for p in problems) and any("isn't a Xero account type" in p for p in problems)


def test_tax_type_must_exist_be_active_and_fit_the_class():
    assert "doesn't exist" in check(CREATE, {**NEW, "tax_type": "ZZZ"}, None, org())[0]
    assert "deleted" in check(CREATE, {**NEW, "tax_type": "OLDVAT"}, None, org())[0]
    assert "can't be used on expense" in check(CREATE, {**NEW, "tax_type": "OUTPUT2"}, None, org())[0]


def test_no_write_access_blocks_everything():
    assert any("write access" in p for p in check(CREATE, NEW, None, org(can_write=False)))


def test_system_accounts_cannot_be_changed_or_archived():
    ar = acct("a1", "610", "Accounts Receivable", "CURRENT", system="DEBTORS", cls="ASSET")
    for op, payload in ((UPDATE, {"name": "AR"}), (ARCHIVE, {})):
        (p,) = check(op, payload, ar, org([ar]))
        assert "system account" in p


def test_archived_or_missing_targets():
    old = acct("a1", "400", "Advertising", status="ARCHIVED")
    assert "already archived" in check(ARCHIVE, {}, old, org([old]))[0]
    assert "no longer exists" in check(ARCHIVE, {}, None, org())[0]


def test_update_rename_checks_clashes_but_ignores_itself():
    a, b = acct("a1", "400", "Advertising"), acct("a2", "401", "Marketing")
    assert check(UPDATE, {"name": "Advertising & Marketing"}, a, org([a, b])) == []
    assert "already exists" in check(UPDATE, {"name": "marketing"}, a, org([a, b]))[0]


def test_update_that_changes_nothing_is_refused():
    a = acct("a1", "400", "Advertising")
    assert check(UPDATE, {"name": "Advertising"}, a, org([a])) == ["Nothing would change."]


def test_update_rejects_fields_it_does_not_own():
    a = acct("a1", "400", "Advertising")
    assert any("Can't change" in p for p in check(UPDATE, {"type": "EXPENSE", "name": "Ads"}, a, org([a])))


def test_archive_request_is_status_only():
    assert xero_fields(ARCHIVE, {"name": "ignored"}) == {"Status": "ARCHIVED"}
    assert xero_fields(CREATE, {"code": "489", "name": "T", "type": "overheads", "tax_type": None}) == {
        "Code": "489", "Name": "T", "Type": "OVERHEADS"}
