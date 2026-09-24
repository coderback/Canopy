"""Group standard -> suggestions -> human decisions -> gaps -> export, over HTTP."""

import csv
import io

from canopy.mapping.service import generate_suggestions
from canopy.sync.service import FULL, sync_entity_accounts

from .helpers import client_for, make_entity, owner_scalar, sign_in
from .test_connect_and_sync import FakeAccounting, StaticToken, account

ORG_A = [  # becomes the group standard
    account("a1", "200", "Sales", "REVENUE", "REVENUE"),
    account("a2", "400", "Advertising"),
    account("a3", "897", "Software Subscriptions"),
    account("a4", "410", "Insurance"),
]
ORG_B = [  # an acquired org with its own coding scheme
    account("b1", "200", "Sales", "REVENUE", "REVENUE"),        # exact
    account("b2", "8100", "Software Subscriptions"),            # same name, different code
    account("b3", "400", "Marketing & PR"),                     # same code, different name
    account("b4", "650", "Trampoline Park Cover"),              # AI: insurance
    account("b5", "660", "Site Charity Fund"),                  # AI: no equivalent
]


async def fake_ai(system, user, schema):
    answers = {"Trampoline Park Cover": ("410", 0.8), "Site Charity Fund": (None, 0.7)}
    out = []
    for line in user.splitlines():
        if line.startswith("L"):
            ref, _code, name, *_ = [p.strip() for p in line.split("|")]
            code, conf = answers.get(name, (None, 0.1))
            out.append({"local_ref": ref, "group_code": code, "confidence": conf, "reasoning": f"about {name}"})
    return {"suggestions": out}


async def _setup(c, xero_identity):
    me = await sign_in(c, xero_identity)
    ws = (await c.post("/workspaces", json={"name": "Group"})).json()["id"]
    a = await make_entity(ws, me["user"]["id"], "tenant-a", "Org A")
    b = await make_entity(ws, me["user"]["id"], "tenant-b", "Org B")
    await sync_entity_accounts(ws, a, FULL, transport=FakeAccounting(ORG_A), tokens=StaticToken())
    await sync_entity_accounts(ws, b, FULL, transport=FakeAccounting(ORG_B), tokens=StaticToken())
    return ws, a, b


async def test_seed_suggest_decide_gaps_and_export(xero_identity, jobs_in_memory):
    async with client_for(xero_identity) as c:
        ws, a, b = await _setup(c, xero_identity)

        seeded = await c.post(f"/workspaces/{ws}/standard/seed", json={"entity_id": str(a)})
        assert seeded.status_code == 201 and seeded.json() == {"accounts": 4}
        # Suggestion jobs are queued for every org, after the seed committed.
        assert sum(j["task_name"] == "suggest_mappings" for j in jobs_in_memory.jobs.values()) == 2

        # Run what the worker would run (with a fake model).
        await generate_suggestions(ws, a, fake_ai)
        await generate_suggestions(ws, b, fake_ai)

        rows = {r["account"]["name"]: r for r in (await c.get(f"/workspaces/{ws}/entities/{b}/mappings")).json()}
        src = {n: (r["mapping"]["source"], r["group_account"]["code"] if r["group_account"] else None)
               for n, r in rows.items()}
        assert src == {
            "Sales": ("exact", "200"),
            "Software Subscriptions": ("name", "897"),
            "Marketing & PR": ("code_conflict", "400"),
            "Trampoline Park Cover": ("ai", "410"),
            "Site Charity Fund": ("ai", None),
        }

        # Nothing is confirmed yet: every group account is pending or a gap in B.
        gaps = (await c.get(f"/workspaces/{ws}/gaps")).json()
        assert all(r["cells"][str(b)]["state"] != "mapped" for r in gaps["rows"])

        assert (await c.post(f"/workspaces/{ws}/entities/{b}/mappings/confirm-exact")).json() == {"confirmed": 1}
        decide = lambda name, **body: c.post(f"/workspaces/{ws}/mappings/{rows[name]['mapping']['id']}/decision", json=body)  # noqa: E731
        assert (await decide("Software Subscriptions", action="confirm")).status_code == 200
        assert (await decide("Marketing & PR", action="reject")).status_code == 200
        assert (await decide("Trampoline Park Cover", action="confirm")).status_code == 200
        assert (await decide("Site Charity Fund", action="assign", group_account_id=None)).status_code == 200

        gaps = (await c.get(f"/workspaces/{ws}/gaps")).json()
        state_b = {r["group_account"]["code"]: r["cells"][str(b)]["state"] for r in gaps["rows"]}
        assert state_b == {"200": "mapped", "400": "gap", "410": "mapped", "897": "mapped"}

        export = (await c.get(f"/workspaces/{ws}/export.csv")).text
    lines = list(csv.DictReader(io.StringIO(export)))
    b_lines = {r["local_name"]: r["group_code"] for r in lines if r["organisation"] == "Org B"}
    assert b_lines == {"Sales": "200", "Software Subscriptions": "897", "Trampoline Park Cover": "410", "Site Charity Fund": ""}
    assert owner_scalar("select count(*) from audit_events where action like 'mapping.%'") == 5


async def test_regenerating_suggestions_never_overwrites_human_decisions(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, b = await _setup(c, xero_identity)
        await c.post(f"/workspaces/{ws}/standard/seed", json={"entity_id": str(a)})
        await generate_suggestions(ws, b, fake_ai)
        rows = {r["account"]["name"]: r for r in (await c.get(f"/workspaces/{ws}/entities/{b}/mappings")).json()}
        mid = rows["Marketing & PR"]["mapping"]["id"]
        await c.post(f"/workspaces/{ws}/mappings/{mid}/decision", json={"action": "reject"})

        async def ai_now_says_insurance(system, user, schema):
            return await fake_ai(system, user.replace("Marketing & PR", "Trampoline Park Cover"), schema)

        await generate_suggestions(ws, b, ai_now_says_insurance, refresh=True)
        after = {r["account"]["name"]: r for r in (await c.get(f"/workspaces/{ws}/entities/{b}/mappings")).json()}
    assert after["Marketing & PR"]["mapping"]["status"] == "rejected"
    assert after["Marketing & PR"]["group_account"]["code"] == "400"


async def test_seeding_twice_is_refused(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, _ = await _setup(c, xero_identity)
        assert (await c.post(f"/workspaces/{ws}/standard/seed", json={"entity_id": str(a)})).status_code == 201
        again = await c.post(f"/workspaces/{ws}/standard/seed", json={"entity_id": str(a)})
    assert again.status_code == 409


async def test_csv_import_validates_rows(xero_identity):
    async with client_for(xero_identity) as c:
        await sign_in(c, xero_identity)
        ws = (await c.post("/workspaces", json={"name": "G"})).json()["id"]
        bad = await c.post(f"/workspaces/{ws}/standard/import",
                           files={"file": ("s.csv", b"code,name,type\n100,Cash,BANKK\n", "text/csv")})
        good = await c.post(f"/workspaces/{ws}/standard/import",
                            files={"file": ("s.csv", b"code,name,type\n100,Sales,REVENUE\n200,Rent,OVERHEADS\n", "text/csv")})
        std = (await c.get(f"/workspaces/{ws}/standard")).json()
    assert bad.status_code == 400 and "Row 2" in bad.json()["error"]["message"]
    assert good.json() == {"accounts": 2}
    assert {(g["code"], g["account_class"]) for g in std} == {("100", "REVENUE"), ("200", "EXPENSE")}


async def test_without_ai_every_unplaced_account_still_reaches_review(xero_identity):
    async with client_for(xero_identity) as c:
        ws, a, b = await _setup(c, xero_identity)
        await c.post(f"/workspaces/{ws}/standard/seed", json={"entity_id": str(a)})
        await generate_suggestions(ws, b, None)  # AI switched off
        rows = {r["account"]["name"]: r for r in (await c.get(f"/workspaces/{ws}/entities/{b}/mappings")).json()}
        assert all(r["mapping"] is not None for r in rows.values())  # nothing silently dropped
        unmatched = rows["Trampoline Park Cover"]["mapping"]
        assert unmatched["source"] == "unmatched" and unmatched["group_account_id"] is None
        # A person can still resolve it.
        insurance = next(g for g in (await c.get(f"/workspaces/{ws}/standard")).json() if g["code"] == "410")
        r = await c.post(f"/workspaces/{ws}/mappings/{unmatched['id']}/decision",
                         json={"action": "assign", "group_account_id": insurance["id"]})
    assert r.json()["status"] == "confirmed"
