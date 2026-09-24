"""Tenant isolation is enforced by Postgres, not by application convention.

Every query here runs as `canopy_app`, the role the API and worker use."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from canopy.core.db import unit_of_work
from canopy.standard.models import GroupAccount
from canopy.xero.models import Entity
from migrations.policies import NO_RLS_TABLES

from .helpers import auth, make_entity, make_user, owner_scalar


async def _two_workspaces():
    alice = await make_user("xa", "alice@a.com")
    bob = await make_user("xb", "bob@b.com")
    ws_a = await auth.create_workspace(alice, "Group A")
    ws_b = await auth.create_workspace(bob, "Group B")
    await make_entity(ws_a, alice, "tenant-a", "Org A")
    await make_entity(ws_b, bob, "tenant-b", "Org B")
    return (alice, ws_a), (bob, ws_b)


async def test_a_workspace_only_sees_its_own_rows_even_without_a_where_clause():
    (alice, ws_a), (bob, ws_b) = await _two_workspaces()
    async with unit_of_work(workspace_id=ws_a, user_id=alice) as s:
        names = list(await s.scalars(select(Entity.name)))  # deliberately unfiltered
    assert names == ["Org A"]


async def test_no_context_sees_nothing():
    await _two_workspaces()
    async with unit_of_work() as s:
        assert list(await s.scalars(select(Entity))) == []


async def test_cannot_write_a_row_into_another_workspace():
    (alice, ws_a), (bob, ws_b) = await _two_workspaces()
    with pytest.raises(DBAPIError, match="row-level security"):
        async with unit_of_work(workspace_id=ws_a, user_id=alice) as s:
            s.add(GroupAccount(workspace_id=ws_b, code="100", name="x", type="EXPENSE", account_class="EXPENSE"))


async def test_users_are_only_visible_within_a_shared_workspace():
    (alice, ws_a), (bob, ws_b) = await _two_workspaces()
    async with unit_of_work(workspace_id=ws_a, user_id=alice) as s:
        emails = list(await s.scalars(text("select email from users")))
    assert emails == ["alice@a.com"]


async def test_audit_log_is_append_only_for_the_app():
    (alice, ws_a), _ = await _two_workspaces()
    for stmt in ("update audit_events set action = 'x'", "delete from audit_events"):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with unit_of_work(workspace_id=ws_a, user_id=alice) as s:
                await s.execute(text(stmt))


async def test_app_cannot_create_users_except_through_login():
    with pytest.raises(DBAPIError, match="permission denied"):
        async with unit_of_work() as s:
            await s.execute(text(
                "insert into users (id, xero_user_id, email, name, created_at) "
                "values (gen_random_uuid(), 'x', 'x@x.com', 'x', now())"
            ))


def test_every_table_is_either_row_level_secured_or_explicitly_exempt():
    """Guards future migrations: a new table without RLS fails here."""
    unsecured = owner_scalar(
        "select coalesce(string_agg(tablename, ','), '') from pg_tables "
        "where schemaname = 'public' and not rowsecurity"
    )
    exempt = set(NO_RLS_TABLES)
    offenders = [t for t in unsecured.split(",") if t and t not in exempt and not t.startswith("procrastinate")]
    assert offenders == []
