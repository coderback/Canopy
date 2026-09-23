import asyncio
import time

import pytest

from app.xero import auth as xero_auth


@pytest.mark.asyncio
async def test_concurrent_callers_refresh_the_token_once(db, monkeypatch):
    # Xero rotates the refresh token on every refresh, so concurrent fan-out calls
    # hitting an expired token must refresh once and share the result.
    xero_auth.save_token(
        db,
        {"access_token": "old", "refresh_token": "r-1", "expires_in": 0},  # save_token stamps now → already expired
    )
    used: list[str] = []

    async def fake_refresh(db_, token):
        used.append(token["refresh_token"])
        await asyncio.sleep(0.01)  # let the other callers pile up on the lock
        new = {"access_token": "new", "refresh_token": "r-2", "expires_in": 1800, "obtained_at": time.time()}
        xero_auth.save_token(db_, new)
        return new

    monkeypatch.setattr(xero_auth, "refresh_token", fake_refresh)
    tokens = await asyncio.gather(*(xero_auth.get_valid_access_token(db) for _ in range(5)))

    assert tokens == ["new"] * 5
    assert used == ["r-1"]
