"""Async database access with Postgres row-level security.

Every unit of work runs in ONE transaction that first sets two transaction-local
settings, `app.workspace_id` and `app.user_id`. RLS policies (see migrations)
filter tenant tables on them, so a query that forgets a `WHERE workspace_id = …`
still cannot see another workspace's rows. `set_config(..., true)` is the
function form of `SET LOCAL`: the values vanish at commit/rollback, so a pooled
connection never carries one tenant's context into the next request.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

# Deterministic constraint names so Alembic migrations are stable.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def set_context(
    session: AsyncSession,
    workspace_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """(Re)bind the RLS context for the rest of the current transaction."""
    await session.execute(
        text(
            "select set_config('app.workspace_id', :w, true),"
            " set_config('app.user_id', :u, true)"
        ),
        {"w": str(workspace_id) if workspace_id else "", "u": str(user_id) if user_id else ""},
    )


@asynccontextmanager
async def unit_of_work(
    workspace_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AsyncIterator[AsyncSession]:
    """One transaction with the RLS context set. Commits on success."""
    async with get_sessionmaker()() as session:
        async with session.begin():
            await set_context(session, workspace_id, user_id)
            yield session
