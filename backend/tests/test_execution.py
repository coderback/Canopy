import pytest

from app.execution import execute_run
from app.models import Proposal, Run, Snapshot
from app.xero.client import XeroApi


def _make_run(db, entity, payload_a: dict, payload_b: dict) -> Run:
    run = Run(kind="propagation", change_type="contact", source_payload=payload_a)
    db.add(run)
    db.flush()
    for payload in (payload_a, payload_b):
        db.add(
            Proposal(
                run_id=run.id,
                entity_id=entity.id,
                action="create-contact",
                mapped_payload=payload,
                confidence=0.9,
                reasoning="test",
                status="approved",
            )
        )
    db.commit()
    return run


@pytest.mark.asyncio
async def test_partial_failure_is_recorded_and_run_marked_partial(db, token, entity, fake_transport):
    calls = {"n": 0}

    class CountingTransport(type(fake_transport)):
        pass

    # First contact write succeeds, second returns 400.
    import httpx

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json={"Contacts": [{"ContactID": "c-1", "Name": "A"}]})
            return httpx.Response(400, json={"Message": "boom"})

    run = _make_run(db, entity, {"Name": "Good Contact"}, {"Name": "Bad Contact"})
    await execute_run(db, XeroApi(transport=Transport()), run)

    db.refresh(run)
    assert run.status == "partial"
    statuses = sorted(p.status for p in run.proposals)
    assert statuses == ["executed", "failed"]
    failed = next(p for p in run.proposals if p.status == "failed")
    assert failed.write_results[0].error and "400" in failed.write_results[0].error


@pytest.mark.asyncio
async def test_invalid_payload_never_reaches_xero(db, token, entity, fake_transport):
    run = Run(kind="propagation", change_type="account", source_payload={})
    db.add(run)
    db.flush()
    db.add(
        Proposal(
            run_id=run.id,
            entity_id=entity.id,
            action="create-account",
            mapped_payload={"Code": "492"},  # missing Name + Type → schema failure
            confidence=0.9,
            reasoning="test",
            status="approved",
        )
    )
    db.commit()

    await execute_run(db, XeroApi(transport=fake_transport), run)
    assert fake_transport.requests == []  # zero API calls
    db.refresh(run)
    assert run.status == "failed"


@pytest.mark.asyncio
async def test_successful_write_refreshes_entity_snapshot(db, token, entity, fake_transport):
    # Resolving a drift must move the health bar immediately: after the write,
    # execute_run force-re-reads the entity's accounts so the new code is cached.
    acct = {"AccountID": "a-1", "Code": "990", "Name": "Gift Card Liability", "Type": "CURRLIAB", "Status": "ACTIVE"}
    fake_transport.on("PUT", "/Accounts", {"Accounts": [acct]})
    fake_transport.on("GET", "/Accounts", {"Accounts": [acct]})

    run = Run(kind="propagation", change_type="account", source_payload={})
    db.add(run)
    db.flush()
    db.add(
        Proposal(
            run_id=run.id,
            entity_id=entity.id,
            action="create-account",
            mapped_payload={"Code": "990", "Name": "Gift Card Liability", "Type": "CURRLIAB"},
            confidence=0.9,
            reasoning="test",
            status="approved",
        )
    )
    db.commit()

    await execute_run(db, XeroApi(transport=fake_transport), run)

    db.refresh(run)
    assert run.status == "completed"
    # the write (PUT) was followed by a forced re-read (GET /Accounts)
    assert any(r.method == "GET" and r.url.path.endswith("/Accounts") for r in fake_transport.requests)
    # and the fresh snapshot now carries the just-created account
    snap = db.query(Snapshot).filter_by(entity_id=entity.id, kind="accounts").first()
    assert snap is not None and any(a["Code"] == "990" for a in snap.data)


@pytest.mark.asyncio
async def test_tracking_category_retry_completes_partial_write(db, token, entity, fake_transport):
    # A previous attempt created the category and its first option, then died.
    # The retry must reuse it and add only the missing option — not re-PUT the
    # category (Xero 400s a duplicate name) nor duplicate "North".
    existing = {
        "TrackingCategoryID": "tc-1",
        "Name": "Region",
        "Options": [{"TrackingOptionID": "o-1", "Name": "North"}],
    }
    fake_transport.on("GET", "/TrackingCategories", {"TrackingCategories": [existing]})
    fake_transport.on("PUT", "/Options", {"Options": [{"TrackingOptionID": "o-2", "Name": "South"}]})

    run = Run(kind="propagation", change_type="tracking", source_payload={})
    db.add(run)
    db.flush()
    db.add(
        Proposal(
            run_id=run.id,
            entity_id=entity.id,
            action="create-tracking-category",
            mapped_payload={"Name": "Region", "Options": ["North", "South"]},
            confidence=0.9,
            reasoning="test",
            status="approved",
        )
    )
    db.commit()

    await execute_run(db, XeroApi(transport=fake_transport), run)

    db.refresh(run)
    assert run.status == "completed"
    puts = [r for r in fake_transport.requests if r.method == "PUT"]
    assert [r.url.path for r in puts] == ["/api.xro/2.0/TrackingCategories/tc-1/Options"]
    assert b"South" in puts[0].content
    assert run.proposals[0].write_results[0].xero_id == "tc-1"
