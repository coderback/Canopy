import pytest

from app.demo import demo_api, seed_demo_run
from app.execution import execute_run


def test_seed_demo_run_has_three_flagship_proposals(db):
    run = seed_demo_run(db)
    assert run.kind == "propagation"
    assert run.change_type == "item"
    assert len(run.proposals) == 3
    needs = sorted(p.needs_human for p in run.proposals)
    assert needs == [False, False, True]  # A + B clean, C refuses
    # the mapped org (B) carries the translated account code
    codes = {
        p.mapped_payload.get("SalesDetails", {}).get("AccountCode")
        for p in run.proposals
    }
    assert "201" in codes


@pytest.mark.asyncio
async def test_approving_demo_run_completes_with_fake_ids(db):
    run = seed_demo_run(db)
    for p in run.proposals:
        if not p.needs_human:
            p.status = "approved"
    db.commit()

    await execute_run(db, demo_api, run)

    db.refresh(run)
    assert run.status == "completed"
    executed = [p for p in run.proposals if p.status == "executed"]
    assert len(executed) == 2
    for p in executed:
        assert p.write_results[0].success is True
        assert p.write_results[0].xero_id and p.write_results[0].xero_id.startswith("demo-")
