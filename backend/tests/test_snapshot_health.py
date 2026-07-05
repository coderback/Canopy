from app.models import Entity, Snapshot
from app.snapshots import snapshot_health


def _entity(db, tenant_id, name):
    e = Entity(tenant_id=tenant_id, name=name)
    db.add(e)
    db.commit()
    return e


def _accounts(db, entity, records):
    db.add(Snapshot(entity_id=entity.id, kind="accounts", data=records))
    db.commit()


def test_health_reports_snapshot_coverage(db):
    a = _entity(db, "tenant-a", "Org A")
    _accounts(db, a, [{"Code": "200", "Name": "Sales"}])
    db.add(Snapshot(entity_id=a.id, kind="contacts", data=[{"Name": "Acme"}]))
    db.commit()

    health = snapshot_health(db, [a])[a.id]
    assert health["kinds_cached"] == 2
    assert health["kinds_total"] == 5
    assert health["snapshots"]["accounts"]["count"] == 1
    assert health["snapshots"]["contacts"]["fetched_at"]


def test_drift_flags_majority_codes_missing_here(db):
    a = _entity(db, "tenant-a", "Org A")
    b = _entity(db, "tenant-b", "Org B")
    c = _entity(db, "tenant-c", "Org C")
    _accounts(db, a, [{"Code": "200", "Name": "Sales"}, {"Code": "400", "Name": "Rent"}])
    _accounts(db, b, [{"Code": "201", "Name": "Trading Income"}, {"Code": "400", "Name": "Rent"}])
    _accounts(db, c, [{"Code": "200", "Name": "Sales"}, {"Code": "400", "Name": "Rent"}])

    health = snapshot_health(db, [a, b, c])

    # 200 exists in A and C (2 of 3) but not B → drift on B, nowhere else
    assert health[b.id]["drift"] == [
        {"code": "200", "name": "Sales", "present_in": 2, "of": 3}
    ]
    assert health[a.id]["drift"] == []
    assert health[c.id]["drift"] == []
    # 201 exists only in B (1 of 3) — a minority code is nobody's drift
    assert all("201" not in [d["code"] for d in h["drift"]] for h in health.values())


def test_drift_ignores_archived_codes_and_needs_two_orgs(db):
    a = _entity(db, "tenant-a", "Org A")
    b = _entity(db, "tenant-b", "Org B")
    _accounts(db, a, [{"Code": "200", "Name": "Sales", "Status": "ARCHIVED"}])
    _accounts(db, b, [{"Code": "400", "Name": "Rent"}])

    health = snapshot_health(db, [a, b])
    # archived 200 doesn't count as present in A, so it can't be drift for B;
    # 400 is only in 1 of 2 orgs (not a strict majority) so no drift for A
    assert health[a.id]["drift"] == []
    assert health[b.id]["drift"] == []


def test_no_snapshots_means_empty_health_not_error(db):
    a = _entity(db, "tenant-a", "Org A")
    health = snapshot_health(db, [a])[a.id]
    assert health["snapshots"] == {}
    assert health["kinds_cached"] == 0
    assert health["drift"] == []
