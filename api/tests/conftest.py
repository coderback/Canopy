"""Test configuration. Runs before `canopy` is imported, so settings see it.

Integration tests use the `canopy_test` database from docker-compose:
the app connects as `canopy_app` (RLS applies, exactly as in production) and
the harness uses the owner role only for schema setup and cleanup.
"""

import os

from cryptography.fernet import Fernet

TEST_DB_HOST = os.environ.get("TEST_DB_HOST", "localhost:5432")
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"postgresql+psycopg://canopy_app:canopy_app@{TEST_DB_HOST}/canopy_test",
        "MIGRATIONS_DATABASE_URL": f"postgresql+psycopg://canopy:canopy@{TEST_DB_HOST}/canopy_test",
        "TOKEN_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
        "XERO_CLIENT_ID": "test-client-id",
        "XERO_CLIENT_SECRET": "test-client-secret",
        "API_BASE_URL": "http://api.test",
        "WEB_BASE_URL": "http://web.test",
        # Never reach a real model from tests.
        "AZURE_OPENAI_ENDPOINT": "",
        "OPENAI_API_KEY": "",
        "XERO_WRITES_ENABLED": "true",
    }
)

from canopy.core.loop import configure_event_loop  # noqa: E402

configure_event_loop()
