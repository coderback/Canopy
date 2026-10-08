"""Tracking categories: the pure matcher and pre-write checks."""

import uuid

import pytest

from canopy.tracking import preflight as tp
from canopy.tracking.matcher import Named, match_categories, match_options


def _named(*names):
    return [Named(uuid.uuid4(), n) for n in names]


def org(*categories, can_write=True):
    return tp.OrgTracking("Org B", list(categories), can_write)


def cat(name, status="ACTIVE", options=()):
    return tp.OrgCategory(f"x-{name}", name, status,
                          tuple(tp.OrgOption(f"x-{name}-{o}", o.lstrip("~"),
                                             "ARCHIVED" if o.startswith("~") else "ACTIVE") for o in options))


# ---- matcher ----------------------------------------------------------------------------


def test_categories_match_on_normalised_name_only():
    region, dept = _named("Region", "Sales & Marketing")
    local = _named("region ", "Sales and Marketing", "Dept")
    matches = match_categories(local, [region, dept])
    assert [(m.group_id, m.source) for m in matches] == [
        (region.id, "exact"), (dept.id, "exact"), (None, "unmatched")]


def test_options_match_only_within_the_mapped_group_category():
    london, bristol = _named("London", "Bristol")
    local = _named("London", "Leeds")
    matches = match_options(local, [london, bristol], "Region")
    assert [(m.group_id, m.source) for m in matches] == [(london.id, "exact"), (None, "unmatched")]
    assert "'Region'" in matches[1].reasoning


def test_options_of_an_unmapped_category_wait_for_their_category():
    (m,) = match_options(_named("London"), [], None)
    assert m.group_id is None and "isn't mapped" in m.reasoning


# ---- preflight --------------------------------------------------------------------------


def test_a_new_category_with_its_options_passes():
    assert tp.check(tp.CREATE_CATEGORY, {"name": "Region", "options": ["London", "Bristol"]}, org()) == []


def test_xeros_two_active_category_limit_blocks_a_third():
    problems = tp.check(tp.CREATE_CATEGORY, {"name": "Project", "options": []},
                        org(cat("Region"), cat("Department")))
    assert "already has 2 active tracking categories (Region, Department)" in problems[0]


def test_four_categories_including_archived_is_the_ceiling():
    problems = tp.check(tp.CREATE_CATEGORY, {"name": "Project"},
                        org(cat("A"), cat("B", "ARCHIVED"), cat("C", "ARCHIVED"), cat("D", "ARCHIVED")))
    assert "4 tracking categories including archived" in problems[0]


def test_an_archived_category_still_blocks_its_name():
    problems = tp.check(tp.CREATE_CATEGORY, {"name": "region"}, org(cat("Region", "ARCHIVED")))
    assert problems == ["A tracking category named 'Region' already exists in Org B (archived)."]


@pytest.mark.parametrize("payload, problem", [
    ({"name": ""}, "1–100 characters"),
    ({"name": "x" * 101}, "1–100 characters"),
    ({"name": "Region", "options": ["London", "london "]}, "listed twice"),
    ({"name": "Region", "options": "London"}, "list of names"),
])
def test_names_and_options_are_validated(payload, problem):
    assert any(problem in p for p in tp.check(tp.CREATE_CATEGORY, payload, org()))


def test_resuming_our_own_half_created_category_skips_the_clash_and_limit_checks():
    ours = cat("Region", options=["London"])
    assert tp.check(tp.CREATE_CATEGORY, {"name": "Region", "options": ["London", "Bristol"]},
                    org(ours, cat("Department")), category=ours) == []


def test_options_are_unique_within_their_category_archived_included():
    region = cat("Region", options=["London", "~Leeds"])
    assert "already has an option named 'Leeds' (archived)" in \
        tp.check(tp.CREATE_OPTION, {"name": "leeds"}, org(region), category=region)[0]
    assert tp.check(tp.CREATE_OPTION, {"name": "Bristol"}, org(region), category=region) == []


def test_no_options_can_be_added_to_an_archived_category():
    region = cat("Region", "ARCHIVED")
    assert "unarchive it in Xero first" in tp.check(tp.CREATE_OPTION, {"name": "X"}, org(region), category=region)[0]


def test_renames_change_only_the_name_and_must_change_it():
    region = cat("Region", options=["London", "Bristol"])
    london = region.options[0]
    assert tp.check(tp.UPDATE_CATEGORY, {"name": "Region"}, org(region), category=region) == ["Nothing would change."]
    assert "Only the name" in tp.check(tp.UPDATE_CATEGORY, {"status": "ARCHIVED"}, org(region), category=region)[0]
    assert "already has an option named 'Bristol'" in \
        tp.check(tp.UPDATE_OPTION, {"name": "bristol"}, org(region), category=region, option=london)[0]
    assert tp.check(tp.UPDATE_OPTION, {"name": "London City"}, org(region), category=region, option=london) == []


def test_targets_that_vanished_or_are_already_archived_are_blocked():
    region = cat("Region", options=["~London"])
    assert "no longer exists" in tp.check(tp.ARCHIVE_CATEGORY, {}, org())[0]
    assert "no longer exists" in tp.check(tp.ARCHIVE_OPTION, {}, org(region), category=region)[0]
    assert "already archived" in tp.check(tp.ARCHIVE_OPTION, {}, org(region), category=region,
                                          option=region.options[0])[0]


def test_write_access_is_required():
    problems = tp.check(tp.CREATE_CATEGORY, {"name": "Region"}, org(can_write=False))
    assert problems == ["Canopy doesn't have write access to Org B. Reconnect it with write access."]
