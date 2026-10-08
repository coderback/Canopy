"""Tracking categories end to end: sync, the group standard, mapping, gaps, and
approved changes executed against the stateful fake Xero from test_changes."""

import uuid

import pytest

from canopy.sync.service import FULL, sync_entity_accounts
from canopy.tenancy.models import Role

from .helpers import client_for, make_entity, owner_scalar, sign_in
from .test_changes import ORG_A, ORG_B, TRACKING_URL, WRITE, FakeXero, _approved, _other_approver, _run
from .test_connect_and_sync import StaticToken


def category(name, *options, status="ACTIVE"):
    return {"TrackingCategoryID": f"tc-{name}-{uuid.uuid4().hex[:6]}", "Name": name, "Status": status,
            "Options": [{"TrackingOptionID": f"to-{o.lstrip('~')}-{uuid.uuid4().hex[:6]}", "Name": o.lstrip("~"),
                         "Status": "ARCHIVED" if o.startswith("~") else "ACTIVE"} for o in options]}


TRACKING_A = [category("Region", "London", "Bristol", "Guildford"), category("Department", "Ops", "Marketing")]
TRACKING_B = [category("Region", "London", "Leeds")]


async def _group(c, xero_identity, tracking_b=None):
    me = await sign_in(c, xero_identity)
    ws = (await c.post("/workspaces", json={"name": "Group"})).json()["id"]
    a = await make_entity(ws, me["user"]["id"], "tenant-a", "Org A", scopes=WRITE)
    b = await make_entity(ws, me["user"]["id"], "tenant-b", "Org B", scopes=WRITE)
    fake_a, fake_b = FakeXero(ORG_A, TRACKING_A), FakeXero(ORG_B, TRACKING_B if tracking_b is None else tracking_b)
    await sync_entity_accounts(ws, a, FULL, transport=fake_a, tokens=StaticToken())
    await sync_entity_accounts(ws, b, FULL, transport=fake_b, tokens=StaticToken())
    assert (await c.post(f"/workspaces/{ws}/tracking/standard/seed", json={"entity_id": str(a)})).status_code == 201
    await c.patch(f"/workspaces/{ws}/settings", json={"changes_enabled": True})
    return ws, a, b, fake_b


def _find(rows, name):
    return next(r for r in rows if r["name"] == name)


def _standard_option(std, category_name, option_name):
    return next(o["id"] for c in std if c["name"] == category_name for o in c["options"] if o["name"] == option_name)


# ---- sync and the standard ---------------------------------------------------------------


async def test_sync_mirrors_tracking_with_archived_ones_and_marks_vanished_ones_deleted(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, b, fake_b = await _group(c, xero_identity, [category("Region", "London", "~Leeds"),
                                                           category("Old", status="ARCHIVED")])
    count = "select count(*) from entity_tracking_{} where entity_id = :b and deleted_at is null"
    assert owner_scalar(count.format("categories"), b=b) == 2 and owner_scalar(count.format("options"), b=b) == 2
    fake_b.tracking = [c for c in fake_b.tracking if c["Name"] == "Region"]
    await sync_entity_accounts(ws, b, FULL, transport=fake_b, tokens=StaticToken())
    assert owner_scalar(count.format("categories"), b=b) == 1
    assert owner_scalar("select status from entity_tracking_options where name = 'Leeds'") == "ARCHIVED"


async def test_the_standard_holds_two_active_categories_with_unique_names(xero_identity):
    async with client_for(xero_identity) as c:
        ws, *_ = await _group(c, xero_identity)
        std = (await c.get(f"/workspaces/{ws}/tracking/standard")).json()
        assert [(s["name"], [o["name"] for o in s["options"]]) for s in std] == [
            ("Department", ["Marketing", "Ops"]), ("Region", ["Bristol", "Guildford", "London"])]
        third = await c.post(f"/workspaces/{ws}/tracking/standard/categories", json={"name": "Project"})
        assert third.status_code == 409 and "two per organisation" in third.json()["error"]["message"]
        region = _find(std, "Region")["id"]
        dupe = await c.post(f"/workspaces/{ws}/tracking/standard/categories/{region}/options", json={"name": "london"})
        assert dupe.status_code == 409
        reseed = await c.post(f"/workspaces/{ws}/tracking/standard/seed", json={"entity_id": str(uuid.uuid4())})
        assert reseed.status_code == 409
        await c.patch(f"/workspaces/{ws}/tracking/standard/categories/{_find(std, 'Department')['id']}",
                      json={"status": "archived"})
        added = await c.post(f"/workspaces/{ws}/tracking/standard/categories",
                             json={"name": "Project", "options": ["Alpha"]})
    assert added.status_code == 201 and added.json()["options"][0]["name"] == "Alpha"
    assert owner_scalar("select count(*) from audit_events where action like 'standard.tracking_%'") == 3


# ---- mapping and gaps ------------------------------------------------------------------------


async def test_suggestions_match_names_and_options_wait_for_their_category(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, b, _ = await _group(c, xero_identity)
        rows = (await c.get(f"/workspaces/{ws}/tracking/entities/{b}")).json()
        region = _find(rows, "Region")
        assert region["mapping"]["source"] == "exact" and region["group_category"]["name"] == "Region"
        london, leeds = _find(region["options"], "London"), _find(region["options"], "Leeds")
        assert london["mapping"]["source"] == "exact" and leeds["mapping"]["source"] == "unmatched"

        early = await c.post(f"/workspaces/{ws}/tracking/mappings/options/{london['mapping']['id']}/decision",
                             json={"action": "confirm"})
        assert early.status_code == 400 and "category maps first" in early.json()["error"]["message"]
        confirmed = (await c.post(f"/workspaces/{ws}/tracking/entities/{b}/confirm-exact")).json()
        assert confirmed == {"confirmed": 2}  # the category, then its matching option

        std = (await c.get(f"/workspaces/{ws}/tracking/standard")).json()
        wrong = await c.post(f"/workspaces/{ws}/tracking/mappings/options/{leeds['mapping']['id']}/decision",
                             json={"action": "assign", "group_id": _standard_option(std, "Department", "Ops")})
        assert wrong.status_code == 400 and "different group tracking category" in wrong.json()["error"]["message"]

        gaps = (await c.get(f"/workspaces/{ws}/tracking/gaps")).json()
    by_name = {g["group_category"]["name"]: g for g in gaps["categories"]}
    assert by_name["Region"]["cells"][str(b)]["state"] == "mapped"
    options = {o["group_option"]["name"]: o["cells"][str(b)] for o in by_name["Region"]["options"]}
    assert options["London"]["state"] == "mapped"
    assert options["Bristol"] == {"state": "gap", "entity_category_id": region["id"]}
    assert by_name["Department"]["cells"][str(b)]["state"] == "gap"
    assert {o["cells"][str(b)]["state"] for o in by_name["Department"]["options"]} == {"no_category"}


async def test_reassigning_a_category_drops_option_mappings_that_no_longer_fit(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, b, _ = await _group(c, xero_identity)
        await c.post(f"/workspaces/{ws}/tracking/entities/{b}/confirm-exact")
        region = _find((await c.get(f"/workspaces/{ws}/tracking/entities/{b}")).json(), "Region")
        std = (await c.get(f"/workspaces/{ws}/tracking/standard")).json()
        await c.post(f"/workspaces/{ws}/tracking/mappings/categories/{region['mapping']['id']}/decision",
                     json={"action": "assign", "group_id": _find(std, "Department")["id"]})
        after = _find((await c.get(f"/workspaces/{ws}/tracking/entities/{b}")).json(), "Region")
    london = _find(after["options"], "London")
    assert london["group_option"] is None and london["mapping"]["source"] == "unmatched"
    assert "'Department'" in london["mapping"]["reasoning"]


# ---- changes ------------------------------------------------------------------------------------


async def _propose(c, ws, *items, title="tracking"):
    return (await c.post(f"/workspaces/{ws}/changes", json={"title": title, "items": list(items)})).json()


async def test_creating_a_missing_category_writes_it_then_its_options_and_closes_the_gaps(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, b, fake = await _group(c, xero_identity)
        std = (await c.get(f"/workspaces/{ws}/tracking/standard")).json()
        cs = await _propose(c, ws, {"operation": "create_tracking_category", "entity_id": str(b),
                                    "group_tracking_category_id": _find(std, "Department")["id"]})
        (item,) = cs["items"]
        assert item["payload"] == {"name": "Department", "options": ["Marketing", "Ops"]}
        assert item["preflight_status"] == "ok"
        await _approved(c, xero_identity, ws, cs["id"])
        await _run(ws, cs, fake)
        done = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()
        gaps = (await c.get(f"/workspaces/{ws}/tracking/gaps")).json()
    assert done["status"] == "completed"
    writes = [(m, p.removeprefix(TRACKING_URL), body, k) for m, p, body, k in fake.writes()]
    key = f"canopy-{item['id']}-1"
    assert writes[0] == ("PUT", "", {"Name": "Department"}, f"{key}-category")
    assert [(w[2], w[3]) for w in writes[1:]] == [({"Name": "Marketing"}, f"{key}-option-0"),
                                                 ({"Name": "Ops"}, f"{key}-option-1")]
    department = next(g for g in gaps["categories"] if g["group_category"]["name"] == "Department")
    assert department["cells"][str(b)]["state"] == "mapped"
    assert {o["cells"][str(b)]["state"] for o in department["options"]} == {"mapped"}


async def test_a_failed_option_is_retried_without_creating_the_category_twice(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, b, fake = await _group(c, xero_identity)
        std = (await c.get(f"/workspaces/{ws}/tracking/standard")).json()
        cs = await _propose(c, ws, {"operation": "create_tracking_category", "entity_id": str(b),
                                    "group_tracking_category_id": _find(std, "Department")["id"]})
        await _approved(c, xero_identity, ws, cs["id"])
        # The category and its first option are written; the second option fails.
        fake.reject_options["Ops"] = "Option names can't contain '|'."
        await _run(ws, cs, fake)
        failed = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()
        assert failed["status"] == "failed" and "can't contain" in failed["items"][0]["error"]
        retried = (await c.post(f"/workspaces/{ws}/changes/{cs['id']}/retry")).json()
        await _run(ws, retried, fake)
        done = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()
    assert done["status"] == "completed"
    created = [w for w in fake.writes() if w[0] == "PUT" and w[1] == TRACKING_URL]
    assert len(created) == 1
    # The retry (attempt 2) wrote only the option that was still missing.
    retried_writes = [w[2] for w in fake.writes() if w[3] and w[3].startswith(f"canopy-{done['items'][0]['id']}-2")]
    assert retried_writes == [{"Name": "Ops"}]
    (department,) = [t for t in fake.tracking if t["Name"] == "Department"]
    assert [o["Name"] for o in department["Options"]] == ["Marketing", "Ops"]


async def test_xeros_two_active_category_limit_blocks_the_proposal(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, b, _ = await _group(c, xero_identity, [category("Region", "London"), category("Project", "Alpha")])
        std = (await c.get(f"/workspaces/{ws}/tracking/standard")).json()
        cs = await _propose(c, ws, {"operation": "create_tracking_category", "entity_id": str(b),
                                    "group_tracking_category_id": _find(std, "Department")["id"]})
    (item,) = cs["items"]
    assert item["preflight_status"] == "blocked"
    assert "already has 2 active tracking categories (Region, Project)" in item["preflight_messages"][0]


async def test_options_are_added_renamed_and_archived(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, b, fake = await _group(c, xero_identity)
        await c.post(f"/workspaces/{ws}/tracking/entities/{b}/confirm-exact")
        region = _find((await c.get(f"/workspaces/{ws}/tracking/entities/{b}")).json(), "Region")
        std = (await c.get(f"/workspaces/{ws}/tracking/standard")).json()
        leeds = _find(region["options"], "Leeds")
        cs = await _propose(
            c, ws,
            {"operation": "create_tracking_option", "entity_id": str(b), "entity_tracking_category_id": region["id"],
             "group_tracking_option_id": _standard_option(std, "Region", "Bristol")},
            {"operation": "update_tracking_option", "entity_id": str(b), "entity_tracking_option_id": leeds["id"],
             "payload": {"name": "Leeds North"}},
        )
        await _approved(c, xero_identity, ws, cs["id"])
        await _run(ws, cs, fake)
        cs2 = await _propose(c, ws, {"operation": "archive_tracking_option", "entity_id": str(b),
                                     "entity_tracking_option_id": leeds["id"], "payload": {"name": "ignored"}})
        await _approved(c, xero_identity, ws, cs2["id"])
        await _run(ws, cs2, fake)
        gaps = (await c.get(f"/workspaces/{ws}/tracking/gaps")).json()
        renamed = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["items"][1]
    assert renamed["before"]["Name"] == "Leeds" and renamed["after"]["Name"] == "Leeds North"
    assert fake.writes()[-1][2] == {"Status": "ARCHIVED"}
    assert owner_scalar("select status from entity_tracking_options where name = 'Leeds North'") == "ARCHIVED"
    region_gaps = next(g for g in gaps["categories"] if g["group_category"]["name"] == "Region")
    bristol = next(o for o in region_gaps["options"] if o["group_option"]["name"] == "Bristol")
    assert bristol["cells"][str(b)]["state"] == "mapped"


@pytest.mark.parametrize("case, allowed, reason", [
    ("create category from the standard", True, None),
    ("create category with other options", False, "differs from the group standard"),
    ("add option from the standard", True, None),
    ("rename option to its group name", True, None),
    ("archive option", False, "archives a tracking option"),
])
async def test_self_approval_covers_tracking_changes_that_only_align_to_the_standard(
    xero_identity, case, allowed, reason
):
    async with client_for(xero_identity) as c:
        ws, _, b, _ = await _group(c, xero_identity, [category("Region", "London", "Bristol City")])
        await c.patch(f"/workspaces/{ws}/settings", json={"allow_self_approval": True})
        await c.post(f"/workspaces/{ws}/tracking/entities/{b}/confirm-exact")
        std = (await c.get(f"/workspaces/{ws}/tracking/standard")).json()
        region = _find((await c.get(f"/workspaces/{ws}/tracking/entities/{b}")).json(), "Region")
        city = _find(region["options"], "Bristol City")
        if case == "rename option to its group name":
            await c.post(f"/workspaces/{ws}/tracking/mappings/options/{city['mapping']['id']}/decision",
                         json={"action": "assign", "group_id": _standard_option(std, "Region", "Bristol")})
        department = _find(std, "Department")["id"]
        item = {
            "create category from the standard": {"operation": "create_tracking_category",
                                                  "group_tracking_category_id": department},
            "create category with other options": {"operation": "create_tracking_category",
                                                   "group_tracking_category_id": department,
                                                   "payload": {"options": ["Ops"]}},
            "add option from the standard": {"operation": "create_tracking_option",
                                             "entity_tracking_category_id": region["id"],
                                             "group_tracking_option_id": _standard_option(std, "Region", "Guildford")},
            "rename option to its group name": {"operation": "update_tracking_option",
                                                "entity_tracking_option_id": city["id"],
                                                "payload": {"name": "Bristol"}},
            "archive option": {"operation": "archive_tracking_option", "entity_tracking_option_id": city["id"]},
        }[case]
        cs = await _propose(c, ws, {"entity_id": str(b), **item}, title=case)
        assert (await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")).status_code == 200, cs
        blocker = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["self_approval_blocker"]
        r = await c.post(f"/workspaces/{ws}/changes/{cs['id']}/approve", json={"note": "only approver"})
    if allowed:
        assert blocker is None and r.status_code == 200 and r.json()["self_approved"] is True
    else:
        assert reason in blocker and r.status_code == 403


async def test_viewers_read_tracking_but_cannot_edit_the_standard(xero_identity):
    async with client_for(xero_identity) as c:
        ws, *_ = await _group(c, xero_identity)
    viewer = await _other_approver(xero_identity, ws, Role.VIEWER)
    try:
        assert (await viewer.get(f"/workspaces/{ws}/tracking/standard")).status_code == 200
        r = await viewer.post(f"/workspaces/{ws}/tracking/standard/categories", json={"name": "Project"})
        assert r.status_code == 403
    finally:
        await viewer.__aexit__(None, None, None)
