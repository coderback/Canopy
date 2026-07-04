import pytest

from app.execution import execute_run
from app.models import Proposal, Run
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
