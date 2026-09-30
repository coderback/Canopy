"""Alembic runs as the schema OWNER (migrations_database_url), never as the app role."""

from alembic import context
from sqlalchemy import create_engine

from canopy import models  # noqa: F401  (registers every table)
from canopy.core.config import get_settings
from canopy.core.db import Base

target_metadata = Base.metadata


def _url() -> str:
    # psycopg 3 serves both sync (here) and async (the app) under one URL scheme.
    return context.config.get_main_option("sqlalchemy.url") or get_settings().migrations_database_url


def include_object(obj, name, type_, reflected, compare_to):
    """The job queue owns its tables (procrastinate_*); they aren't in our models,
    so without this autogenerate proposes DROPPING them."""
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", "")
    return not (table or "").startswith("procrastinate")


def run_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
