"""Change control end to end: settings, separation of duties, preflight, and
execution against a stateful fake Xero that behaves like the real one on writes
(unique code AND name incl. archived, status-only archive, idempotency keys)."""

import json
import uuid

import httpx
import pytest
from sqlalchemy import delete, update

from canopy.changes.executor import execute_item
from canopy.changes.models import ChangeItem
from canopy.core.config import get_settings
from canopy.core.db import unit_of_work
from canopy.mapping.models import AccountMapping
from canopy.sync.service import FULL, sync_entity_accounts
from canopy.tenancy.models import Membership, Role

from .helpers import client_for, make_entity, make_user, owner_scalar, sign_in
from .test_connect_and_sync import StaticToken

WRITE = "openid profile email offline_access accounting.settings"
ACCOUNTS_URL = "/api.xro/2.0/Accounts"


def acct(aid, code, name, type_="OVERHEADS", cls="EXPENSE", tax="INPUT2", status="ACTIVE", system=None):
    a = {"AccountID": aid, "Code": code, "Name": name, "Type": type_, "Class": cls, "TaxType": tax,
         "Status": status, "UpdatedDateUTC": "/Date(1700000000000+0000)/"}
    if system:
        a["SystemAccount"] = system
    return a


TAX_RATES = [
    {"TaxType": "INPUT2", "Name": "20% (VAT on Expenses)", "Status": "ACTIVE", "CanApplyToExpenses": True,
     "CanApplyToRevenue": False},
    {"TaxType": "OUTPUT2", "Name": "20% (VAT on Income)", "Status": "ACTIVE", "CanApplyToRevenue": True,
     "CanApplyToExpenses": False},
]


TRACKING_URL = "/api.xro/2.0/TrackingCategories"


class FakeXero(httpx.AsyncBaseTransport):
    """One org's chart and tracking categories, mutated by writes. `script` queues
    canned responses per (method, path-prefix) to inject 429s or validation errors.
    Tracking writes behave like Xero's: two active categories at most, names
    unique (archived included), and a repeated Idempotency-Key replays the first
    response instead of writing again."""

    def __init__(self, accounts, tracking=None):
        self.accounts = {a["AccountID"]: dict(a) for a in accounts}
        self.tracking = [json.loads(json.dumps(c)) for c in tracking or []]
        self.requests: list[tuple[str, str, dict, str | None]] = []  # method, path, body, idempotency key
        self.script: dict[tuple[str, str], list[httpx.Response]] = {}
        self.replies: dict[str, httpx.Response] = {}  # Idempotency-Key -> first tracking response
        self.reject_options: dict[str, str] = {}  # option name -> validation message, used once

    def _headers(self):
        return {"X-MinLimit-Remaining": "55", "X-DayLimit-Remaining": "900", "X-AppMinLimit-Remaining": "9000"}

    def _ok(self, body):
        return httpx.Response(200, headers=self._headers(), json=body)

    def _invalid(self, message):
        return httpx.Response(400, headers=self._headers(), json={
            "ErrorNumber": 10, "Type": "ValidationException", "Message": "A validation exception occurred",
            "Elements": [{"ValidationErrors": [{"Message": message}]}]})

    async def handle_async_request(self, request):
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request.method, path, body, request.headers.get("Idempotency-Key")))
        for (method, prefix), queue in self.script.items():
            if request.method == method and path.startswith(prefix) and queue:
                return queue.pop(0)
        if path.endswith("/TaxRates"):
            return self._ok({"TaxRates": TAX_RATES})
        if request.method == "GET" and path == ACCOUNTS_URL:
            return self._ok({"Accounts": list(self.accounts.values())})
        if request.method == "GET" and path.startswith(ACCOUNTS_URL + "/"):
            a = self.accounts.get(path.rsplit("/", 1)[1])
            return self._ok({"Accounts": [a]}) if a else httpx.Response(404, headers=self._headers(), json={})
        if request.method == "PUT" and path == ACCOUNTS_URL:
            for a in self.accounts.values():
                if a["Code"] == body.get("Code"):
                    return self._invalid("Please enter a unique Code.")
                if a["Name"].lower() == body.get("Name", "").lower():
                    return self._invalid("Please enter a unique Name.")
            new = {"AccountID": str(uuid.uuid4()), "Status": "ACTIVE", "Class": "EXPENSE",
                   "UpdatedDateUTC": "/Date(1800000000000+0000)/", **body}
            self.accounts[new["AccountID"]] = new
            return self._ok({"Accounts": [new]})
        if request.method == "POST" and path.startswith(ACCOUNTS_URL + "/"):
            a = self.accounts[path.rsplit("/", 1)[1]]
            if "Status" in body and len(body) > 1:
                return self._invalid("You cannot archive an account and update other fields at the same time.")
            a.update(body)
            a["UpdatedDateUTC"] = "/Date(1800000000000+0000)/"
            return self._ok({"Accounts": [a]})
        if path.startswith(TRACKING_URL):
            key = request.headers.get("Idempotency-Key")
            if key and key in self.replies:
                return self.replies[key]
            response = self._tracking(request.method, path[len(TRACKING_URL):].strip("/").split("/"), body)
            if key and request.method in ("PUT", "POST"):
                self.replies[key] = response
            return response
        return httpx.Response(404, headers=self._headers(), json={})

    def _tracking(self, method, parts, body):
        parts = [p for p in parts if p]
        if method == "GET" and not parts:
            return self._ok({"TrackingCategories": json.loads(json.dumps(self.tracking))})
        category = next((c for c in self.tracking if parts and c["TrackingCategoryID"] == parts[0]), None)
        if parts and category is None:
            return httpx.Response(404, headers=self._headers(), json={})
        if method == "GET":
            return self._ok({"TrackingCategories": [category]})
        if method == "PUT" and not parts:
            if sum(c["Status"] == "ACTIVE" for c in self.tracking) >= 2:
                return self._invalid("You can only have 2 active tracking categories.")
            if any(c["Name"].lower() == body["Name"].lower() for c in self.tracking):
                return self._invalid("The tracking category name must be unique.")
            new = {"TrackingCategoryID": str(uuid.uuid4()), "Name": body["Name"], "Status": "ACTIVE", "Options": []}
            self.tracking.append(new)
            return self._ok({"TrackingCategories": [new]})
        if method == "POST" and len(parts) == 1:
            category.update(body)
            return self._ok({"TrackingCategories": [category]})
        if method == "PUT" and parts[1:] == ["Options"]:
            if body["Name"] in self.reject_options:
                return self._invalid(self.reject_options.pop(body["Name"]))
            if any(o["Name"].lower() == body["Name"].lower() for o in category["Options"]):
                return self._invalid("The tracking option name must be unique.")
            new = {"TrackingOptionID": str(uuid.uuid4()), "Name": body["Name"], "Status": "ACTIVE"}
            category["Options"].append(new)
            return self._ok({"Options": [new]})
        if method == "POST" and len(parts) == 3:
            option = next(o for o in category["Options"] if o["TrackingOptionID"] == parts[2])
            option.update(body)
            return self._ok({"Options": [option]})
        return httpx.Response(404, headers=self._headers(), json={})

    def writes(self):
        return [r for r in self.requests if r[0] in ("PUT", "POST")]


ORG_A = [acct("a-200", "200", "Sales", "REVENUE", "REVENUE", "OUTPUT2"), acct("a-489", "489", "Telephone"),
         acct("a-400", "400", "Advertising")]
ORG_B = [acct("b-200", "200", "Sales", "REVENUE", "REVENUE", "OUTPUT2"), acct("b-400", "400", "Adverts"),
         acct("b-610", "610", "Accounts Receivable", "CURRENT", "ASSET", None, system="DEBTORS")]


async def _group(c, xero_identity, *, write_b=True, enable=True):
    me = await sign_in(c, xero_identity)
    uid = me["user"]["id"]
    ws = (await c.post("/workspaces", json={"name": "Group"})).json()["id"]
    a = await make_entity(ws, uid, "tenant-a", "Org A", scopes=WRITE)
    b = await make_entity(ws, uid, "tenant-b", "Org B", scopes=WRITE if write_b else "accounting.settings.read")
    fake_a, fake_b = FakeXero(ORG_A), FakeXero(ORG_B)
    await sync_entity_accounts(ws, a, FULL, transport=fake_a, tokens=StaticToken())
    await sync_entity_accounts(ws, b, FULL, transport=fake_b, tokens=StaticToken())
    await c.post(f"/workspaces/{ws}/standard/seed", json={"entity_id": str(a)})
    if enable:
        await c.patch(f"/workspaces/{ws}/settings", json={"changes_enabled": True})
    return ws, uid, a, b, fake_b


def _group_id(c_std, code):
    return next(g["id"] for g in c_std if g["code"] == code)


async def _fill_gap(c, ws, b, code="489"):
    std = (await c.get(f"/workspaces/{ws}/standard")).json()
    return await c.post(f"/workspaces/{ws}/changes", json={
        "title": f"Add {code} to Org B", "reason": "close the gap",
        "items": [{"operation": "create_account", "entity_id": str(b), "group_account_id": _group_id(std, code)}]})


async def _second_user(ws, role: Role, xero_id="xero-user-2", email="second@example.com"):
    uid = await make_user(xero_id, email)
    async with unit_of_work(workspace_id=ws, user_id=uid) as s:
        s.add(Membership(workspace_id=uuid.UUID(ws), user_id=uid, role=role))
    return xero_id, email


async def _as(xero_identity, xero_id, email):
    xero_identity.person = (xero_id, email)
    c = client_for(xero_identity)
    await c.__aenter__()
    await sign_in(c, xero_identity)
    return c


async def _other_approver(xero_identity, ws, role=Role.APPROVER):
    """Signs in a new member who can decide; the caller closes the client."""
    tag = uuid.uuid4().hex[:8]
    return await _as(xero_identity, *await _second_user(ws, role, f"x-{tag}", f"{tag}@example.com"))


async def _map(ws, entity_id, code, group_code, status="confirmed"):
    """Maps org account `code` to group account `group_code`."""
    account = owner_scalar("select id from entity_accounts where entity_id = :e and code = :c", e=entity_id, c=code)
    group = owner_scalar("select id from group_accounts where workspace_id = :w and code = :c", w=ws, c=group_code)
    async with unit_of_work(workspace_id=uuid.UUID(ws)) as s:
        await s.execute(delete(AccountMapping).where(AccountMapping.entity_account_id == account))
        s.add(AccountMapping(workspace_id=uuid.UUID(ws), entity_id=entity_id, entity_account_id=account,
                             group_account_id=group, status=status, source="manual", confidence=1.0))
    return account


async def _submitted(c, ws, items, title="x"):
    cs = (await c.post(f"/workspaces/{ws}/changes", json={"title": title, "items": items})).json()
    assert (await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")).status_code == 200, cs
    return cs


# ---- settings and permissions ---------------------------------------------------------------


async def test_changes_are_off_until_the_owner_turns_them_on(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity, enable=False)
        r = await _fill_gap(c, ws, b)
        assert r.status_code == 409 and r.json()["error"]["code"] == "changes_disabled"
        assert (await c.get(f"/workspaces/{ws}/settings")).json()["changes_enabled"] is False
        on = await c.patch(f"/workspaces/{ws}/settings", json={"changes_enabled": True})
        assert on.json()["changes_enabled"] is True
    assert owner_scalar("select count(*) from audit_events where action = 'workspace.settings_changed'") == 1


async def test_only_the_owner_changes_settings(xero_identity):
    async with client_for(xero_identity) as c:
        ws, *_ = await _group(c, xero_identity)
    admin = await _as(xero_identity, *await _second_user(ws, Role.ADMIN))
    try:
        r = await admin.patch(f"/workspaces/{ws}/settings", json={"allow_self_approval": True})
        assert r.status_code == 403
    finally:
        await admin.__aexit__(None, None, None)


async def test_authors_cannot_approve_their_own_change_unless_the_owner_allows_it(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        assert (await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")).json()["status"] == "submitted"
        shown = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()
        assert shown["self_approval_blocker"] == "Self-approval is off for this workspace."
        denied = await c.post(f"/workspaces/{ws}/changes/{cs['id']}/approve", json={"note": "small team"})
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "separation_of_duties"

        await c.patch(f"/workspaces/{ws}/settings", json={"allow_self_approval": True})
        assert (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["self_approval_blocker"] is None
        silent = await c.post(f"/workspaces/{ws}/changes/{cs['id']}/approve", json={"note": "  "})
        assert silent.status_code == 400 and silent.json()["error"]["code"] == "note_required"
        ok = (await c.post(f"/workspaces/{ws}/changes/{cs['id']}/approve", json={"note": "small team"})).json()
    assert ok["status"] == "approved" and ok["self_approved"] is True and ok["needs_review"] is True
    assert owner_scalar("select after->>'self_approved' from audit_events where action = 'change.approved'") == "true"


async def test_self_approval_only_applies_while_nobody_else_can_approve(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        await c.patch(f"/workspaces/{ws}/settings", json={"allow_self_approval": True})
        cs = (await _fill_gap(c, ws, b)).json()
        await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")
        # Members who can't approve don't count.
        await _second_user(ws, Role.PREPARER, "xp", "prep@example.com")
        await _second_user(ws, Role.VIEWER, "xv", "view@example.com")
        assert (await c.get(f"/workspaces/{ws}/settings")).json()["approvers"] == 1
        assert (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["self_approval_blocker"] is None

        await _second_user(ws, Role.APPROVER, "xa", "appr@example.com")
        assert (await c.get(f"/workspaces/{ws}/settings")).json()["approvers"] == 2
        denied = await c.post(f"/workspaces/{ws}/changes/{cs['id']}/approve", json={"note": "quicker"})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "separation_of_duties"
    assert "1 other person can approve" in denied.json()["error"]["message"]


def _item(op, b, account=None, group=None, payload=None):
    return {"operation": op, "entity_id": str(b), "entity_account_id": account and str(account),
            "group_account_id": group, "payload": payload}


@pytest.mark.parametrize("case, allowed, reason", [
    ("create from the standard", True, None),
    ("create with a changed description", False, "details changed from the group standard"),
    ("create outside the standard", False, "isn't in the group standard"),
    ("rename to the group name", True, None),
    ("rename to another name", False, "other than renaming to the group account's name"),
    ("recode as well as rename", False, "other than renaming to the group account's name"),
    ("rename an unconfirmed account", False, "isn't confirmed against a group account"),
    ("archive", False, "archives an account"),
])
async def test_self_approval_is_only_for_bringing_an_org_into_line_with_the_standard(
    xero_identity, case, allowed, reason
):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        await c.patch(f"/workspaces/{ws}/settings", json={"allow_self_approval": True})
        std = (await c.get(f"/workspaces/{ws}/standard")).json()
        adverts = owner_scalar("select id from entity_accounts where code = '400' and entity_id = :b", b=b)
        # Org B's 'Adverts' is the group's 400 Advertising: confirmed, or only suggested.
        await _map(ws, b, "400", "400", "suggested" if case == "rename an unconfirmed account" else "confirmed")
        item = {
            "create from the standard": _item("create_account", b, group=_group_id(std, "489")),
            "create with a changed description":
                _item("create_account", b, group=_group_id(std, "489"), payload={"description": "mobiles"}),
            "create outside the standard": _item("create_account", b, payload={
                "code": "499", "name": "Sundries", "type": "OVERHEADS", "tax_type": "INPUT2"}),
            "rename to the group name": _item("update_account", b, adverts, payload={"name": "Advertising"}),
            "rename to another name": _item("update_account", b, adverts, payload={"name": "Marketing"}),
            "recode as well as rename":
                _item("update_account", b, adverts, payload={"name": "Advertising", "code": "401"}),
            "rename an unconfirmed account": _item("update_account", b, adverts, payload={"name": "Advertising"}),
            "archive": _item("archive_account", b, adverts),
        }[case]
        cs = await _submitted(c, ws, [item], title=case)
        blocker = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["self_approval_blocker"]
        r = await c.post(f"/workspaces/{ws}/changes/{cs['id']}/approve", json={"note": "only approver"})
    if allowed:
        assert blocker is None and r.status_code == 200 and r.json()["self_approved"] is True
    else:
        assert reason in blocker and blocker.startswith("The change in Org B")
        assert r.status_code == 403 and reason in r.json()["error"]["message"]


async def test_authors_cancel_rather_than_reject_their_own_change(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        await c.patch(f"/workspaces/{ws}/settings", json={"allow_self_approval": True})
        cs = (await _fill_gap(c, ws, b)).json()
        await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")
        r = await c.post(f"/workspaces/{ws}/changes/{cs['id']}/reject", json={"note": "changed my mind"})
    assert r.status_code == 409 and "cancel it instead" in r.json()["error"]["message"]


async def test_self_approved_changes_wait_for_someone_else_to_review_them(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        await c.patch(f"/workspaces/{ws}/settings", json={"allow_self_approval": True})
        mine = (await _fill_gap(c, ws, b)).json()
        await c.post(f"/workspaces/{ws}/changes/{mine['id']}/submit")
        await c.post(f"/workspaces/{ws}/changes/{mine['id']}/approve", json={"note": "only approver"})
        queue = (await c.get(f"/workspaces/{ws}/changes", params={"needs_review": True})).json()
        assert [q["id"] for q in queue] == [mine["id"]]
        own = await c.post(f"/workspaces/{ws}/changes/{mine['id']}/review", json={})
        assert own.status_code == 403 and own.json()["error"]["code"] == "separation_of_duties"
        other = (await _fill_gap(c, ws, b, code="200")).json()  # nobody self-approved this one

    preparer = await _other_approver(xero_identity, ws, Role.PREPARER)
    approver = await _other_approver(xero_identity, ws)
    try:
        assert (await preparer.post(f"/workspaces/{ws}/changes/{mine['id']}/review", json={})).status_code == 403
        assert (await approver.post(f"/workspaces/{ws}/changes/{other['id']}/review", json={})).status_code == 409
        done = (await approver.post(f"/workspaces/{ws}/changes/{mine['id']}/review",
                                    json={"note": "checked against the standard"})).json()
        again = await approver.post(f"/workspaces/{ws}/changes/{mine['id']}/review", json={})
        queue = (await approver.get(f"/workspaces/{ws}/changes", params={"needs_review": True})).json()
    finally:
        await preparer.__aexit__(None, None, None)
        await approver.__aexit__(None, None, None)
    assert done["needs_review"] is False and done["review_note"] == "checked against the standard"
    assert done["reviewed_by"]["email"] != done["author"]["email"]
    assert again.status_code == 409 and queue == []
    assert owner_scalar("select count(*) from audit_events where action = 'change.reviewed'") == 1


async def test_a_different_approver_can_approve_but_a_preparer_cannot(xero_identity, jobs_in_memory):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")
    preparer = await _as(xero_identity, *await _second_user(ws, Role.PREPARER, "xp", "prep@example.com"))
    approver = await _as(xero_identity, *await _second_user(ws, Role.APPROVER, "xa", "appr@example.com"))
    try:
        assert (await preparer.post(f"/workspaces/{ws}/changes/{cs['id']}/approve", json={})).status_code == 403
        ok = await approver.post(f"/workspaces/{ws}/changes/{cs['id']}/approve", json={})
        assert ok.json()["status"] == "approved" and ok.json()["self_approved"] is False
    finally:
        await preparer.__aexit__(None, None, None)
        await approver.__aexit__(None, None, None)
    queued = [j for j in jobs_in_memory.jobs.values() if j["task_name"] == "execute_change_item"]
    assert len(queued) == 1 and queued[0]["lock"] == "tenant:tenant-b"


async def test_viewers_cannot_propose_changes(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
    viewer = await _as(xero_identity, *await _second_user(ws, Role.VIEWER, "xv", "view@example.com"))
    try:
        assert (await _fill_gap(viewer, ws, b)).status_code == 403
    finally:
        await viewer.__aexit__(None, None, None)


async def test_rejecting_needs_a_reason(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")
    approver = await _other_approver(xero_identity, ws)
    try:
        assert (await approver.post(f"/workspaces/{ws}/changes/{cs['id']}/reject", json={})).status_code == 400
        r = await approver.post(f"/workspaces/{ws}/changes/{cs['id']}/reject", json={"note": "wrong code"})
    finally:
        await approver.__aexit__(None, None, None)
    assert r.json()["status"] == "rejected" and r.json()["decision_note"] == "wrong code"


# ---- preflight at authoring ---------------------------------------------------------------------


async def test_create_defaults_come_from_the_group_account_and_source_tax_type(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        (item,) = (await _fill_gap(c, ws, b)).json()["items"]
    assert item["payload"] == {"code": "489", "name": "Telephone", "type": "OVERHEADS", "tax_type": "INPUT2"}
    assert item["preflight_status"] == "ok"


async def test_blocked_items_stop_submission_until_fixed(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b, code="400")).json()  # Org B already uses code 400
        (item,) = cs["items"]
        assert item["preflight_status"] == "blocked" and "Code 400 is already used" in item["preflight_messages"][0]
        refused = await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")
        assert refused.status_code == 400 and refused.json()["error"]["code"] == "preflight_blocked"
        # Org B calls its account 'Adverts', so the name 'Advertising' is free: only the code clashed.
        fixed = await c.patch(f"/workspaces/{ws}/changes/{cs['id']}/items/{item['id']}", json={"payload": {"code": "401"}})
        assert fixed.json()["items"][0]["preflight_status"] == "ok"
        submitted = await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")
    assert submitted.status_code == 200 and submitted.json()["status"] == "submitted"


async def test_orgs_without_write_access_are_blocked(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity, write_b=False)
        (item,) = (await _fill_gap(c, ws, b)).json()["items"]
        entities = {e["name"]: e["can_write"] for e in (await c.get(f"/workspaces/{ws}/entities")).json()}
    assert item["preflight_status"] == "blocked" and "write access" in item["preflight_messages"][0]
    assert entities == {"Org A": True, "Org B": False}


async def test_system_accounts_cannot_be_archived(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, _ = await _group(c, xero_identity)
        ar = owner_scalar("select id from entity_accounts where code = '610'")
        cs = (await c.post(f"/workspaces/{ws}/changes", json={"title": "x", "items": [
            {"operation": "archive_account", "entity_id": str(b), "entity_account_id": str(ar)}]})).json()
    assert "system account" in cs["items"][0]["preflight_messages"][0]


# ---- execution ---------------------------------------------------------------------------------------


async def _approved(c, xero_identity, ws, cs_id):
    """Submitted by the author, approved by a second person."""
    assert (await c.post(f"/workspaces/{ws}/changes/{cs_id}/submit")).status_code == 200
    person = xero_identity.person
    approver = await _other_approver(xero_identity, ws)
    try:
        assert (await approver.post(f"/workspaces/{ws}/changes/{cs_id}/approve", json={})).status_code == 200
    finally:
        await approver.__aexit__(None, None, None)
        xero_identity.person = person


async def _run(ws, cs, fake):
    for item in cs["items"]:
        await execute_item(uuid.UUID(ws), uuid.UUID(item["id"]), transport=fake, tokens=StaticToken())


async def test_approved_create_writes_once_with_an_idempotency_key_and_closes_the_gap(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, fake = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        await _approved(c, xero_identity, ws, cs["id"])
        before_gaps = (await c.get(f"/workspaces/{ws}/gaps")).json()
        assert next(r for r in before_gaps["rows"] if r["group_account"]["code"] == "489")["cells"][str(b)]["state"] == "gap"

        await _run(ws, cs, fake)
        done = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()
        gaps = (await c.get(f"/workspaces/{ws}/gaps")).json()
    (item,) = done["items"]
    assert done["status"] == "completed" and item["status"] == "succeeded"
    (write,) = fake.writes()
    assert write[:2] == ("PUT", ACCOUNTS_URL) and write[3] == f"canopy-{item['id']}-1"
    assert write[2] == {"Code": "489", "Name": "Telephone", "Type": "OVERHEADS", "TaxType": "INPUT2"}
    assert item["after"]["Code"] == "489" and item["before"] is None
    assert next(r for r in gaps["rows"] if r["group_account"]["code"] == "489")["cells"][str(b)]["state"] == "mapped"
    assert owner_scalar("select source from account_mappings m join entity_accounts a on a.id = m.entity_account_id "
                        "where a.code = '489' and a.entity_id = :b", b=b) == "created"
    assert owner_scalar("select count(*) from audit_events where action = 'change.item_succeeded'") == 1


async def test_a_429_retry_reuses_the_key_and_an_explicit_retry_gets_a_new_one(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, fake = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        await _approved(c, xero_identity, ws, cs["id"])
        throttled = httpx.Response(429, headers={"Retry-After": "0", "X-Rate-Limit-Problem": "minute"}, json={})
        rejected = fake._invalid("Account code is too long for this organisation.")
        fake.script[("PUT", ACCOUNTS_URL)] = [throttled, rejected]
        await _run(ws, cs, fake)
        failed = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()
        assert failed["status"] == "failed"
        assert failed["items"][0]["error"] == "Xero rejected the change: Account code is too long for this organisation."

        retried = (await c.post(f"/workspaces/{ws}/changes/{cs['id']}/retry")).json()
        await _run(ws, retried, fake)
        done = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()
    keys = [w[3] for w in fake.writes()]
    item_id = done["items"][0]["id"]
    assert keys == [f"canopy-{item_id}-1", f"canopy-{item_id}-1", f"canopy-{item_id}-2"]
    assert done["status"] == "completed"


async def test_data_changed_after_approval_means_no_write(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, fake = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        await _approved(c, xero_identity, ws, cs["id"])
        # Someone creates 'Telephone' directly in Xero after the approval.
        fake.accounts["b-new"] = acct("b-new", "4890", "Telephone")
        await _run(ws, cs, fake)
        item = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["items"][0]
    assert item["status"] == "failed" and item["error"].startswith("Not written") and "already exists" in item["error"]
    assert fake.writes() == []


async def test_rename_then_archive_sends_status_only_and_records_before_after(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, fake = await _group(c, xero_identity)
        adverts = owner_scalar("select id from entity_accounts where code = '400' and entity_id = :b", b=b)
        cs = (await c.post(f"/workspaces/{ws}/changes", json={"title": "align", "items": [
            {"operation": "update_account", "entity_id": str(b), "entity_account_id": str(adverts),
             "payload": {"name": "Advertising"}}]})).json()
        await _approved(c, xero_identity, ws, cs["id"])
        await _run(ws, cs, fake)
        renamed = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["items"][0]
        assert renamed["status"] == "succeeded"
        assert renamed["before"]["Name"] == "Adverts" and renamed["after"]["Name"] == "Advertising"

        cs2 = (await c.post(f"/workspaces/{ws}/changes", json={"title": "archive", "items": [
            {"operation": "archive_account", "entity_id": str(b), "entity_account_id": str(adverts)}]})).json()
        await _approved(c, xero_identity, ws, cs2["id"])
        await _run(ws, cs2, fake)
    assert fake.writes()[-1][2] == {"Status": "ARCHIVED"}
    assert owner_scalar("select status from entity_accounts where id = :a", a=adverts) == "ARCHIVED"


async def test_the_kill_switch_stops_every_write(xero_identity, monkeypatch):
    async with client_for(xero_identity) as c:
        ws, _, _, b, fake = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        await _approved(c, xero_identity, ws, cs["id"])
        monkeypatch.setattr(get_settings(), "xero_writes_enabled", False)
        await _run(ws, cs, fake)
        item = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["items"][0]
    assert item["status"] == "failed" and "switched off" in item["error"] and fake.writes() == []


async def test_an_interrupted_write_is_replayed_with_the_same_key(xero_identity):
    """The worker died after Xero applied the create but before recording it."""
    async with client_for(xero_identity) as c:
        ws, _, _, b, fake = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        await _approved(c, xero_identity, ws, cs["id"])
        item_id = cs["items"][0]["id"]
        fake.accounts["b-489"] = acct("b-489", "489", "Telephone")  # Xero already has it
        replayed = httpx.Response(200, headers=fake._headers(), json={"Accounts": [fake.accounts["b-489"]]})
        fake.script[("PUT", ACCOUNTS_URL)] = [replayed]  # Xero's cached response for the same key
        async with unit_of_work(workspace_id=uuid.UUID(ws)) as s:
            await s.execute(update(ChangeItem).where(ChangeItem.id == uuid.UUID(item_id)).values(status="running"))
        await _run(ws, cs, fake)
        item = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["items"][0]
    assert item["status"] == "succeeded"
    assert [w[3] for w in fake.writes()] == [f"canopy-{item_id}-1"]


@pytest.mark.parametrize("status", ["draft", "submitted"])
async def test_cancelled_changes_never_run(xero_identity, status):
    async with client_for(xero_identity) as c:
        ws, _, _, b, fake = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        if status == "submitted":
            await c.post(f"/workspaces/{ws}/changes/{cs['id']}/submit")
        assert (await c.post(f"/workspaces/{ws}/changes/{cs['id']}/cancel")).json()["status"] == "cancelled"
        await _run(ws, cs, fake)
        item = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["items"][0]
    assert item["status"] == "skipped" and fake.writes() == []


async def test_switching_changes_off_after_approval_stops_queued_writes(xero_identity):
    async with client_for(xero_identity) as c:
        ws, _, _, b, fake = await _group(c, xero_identity)
        cs = (await _fill_gap(c, ws, b)).json()
        await _approved(c, xero_identity, ws, cs["id"])
        await c.patch(f"/workspaces/{ws}/settings", json={"changes_enabled": False})
        await _run(ws, cs, fake)
        item = (await c.get(f"/workspaces/{ws}/changes/{cs['id']}")).json()["items"][0]
    assert item["status"] == "failed" and "switched off" in item["error"] and fake.writes() == []
