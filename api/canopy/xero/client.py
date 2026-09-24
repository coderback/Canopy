"""Xero Accounting API client (ported from the hackathon build).

Rules:
- Every call names its tenant explicitly (Xero-Tenant-Id); nothing is cached globally.
- Quota comes from Xero's own response headers (X-MinLimit-Remaining,
  X-DayLimit-Remaining, X-AppMinLimit-Remaining), persisted per tenant so every
  process sees them. Daily limits differ by API pricing tier, so nothing here
  assumes 5,000/day.
- A 429 with a short Retry-After (minute limit) is waited out in-process; a long
  one (daily limit) raises QuotaExhausted so the job is rescheduled rather than
  holding a worker for hours.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert

from ..core.config import get_settings
from ..core.db import unit_of_work
from ..core.models_base import utcnow
from .models import XeroQuota

BASE_URL = "https://api.xero.com/api.xro/2.0"
APP_QUOTA_KEY = "*app*"
MAX_ATTEMPTS = 4
MAX_INLINE_WAIT_SECONDS = 65.0

AccessToken = Callable[[], Awaitable[str]]


class XeroApiError(Exception):
    def __init__(self, status_code: int, body: str, path: str):
        self.status_code = status_code
        self.body = body
        self.path = path
        super().__init__(f"Xero API {status_code} on {path}: {body[:500]}")


class QuotaExhausted(Exception):
    """Too close to (or over) a Xero limit to proceed now; retry at `retry_at`."""

    def __init__(self, tenant_id: str, retry_at: datetime, reason: str):
        super().__init__(f"Xero quota for {tenant_id}: {reason}; retry at {retry_at.isoformat()}")
        self.tenant_id = tenant_id
        self.retry_at = retry_at


_MS_DATE = re.compile(r"/Date\((-?\d+)([+-]\d{4})?\)/")


def parse_xero_date(value: str | None) -> datetime | None:
    """Xero JSON dates look like '/Date(1573755038314+0000)/' (ms since epoch)."""
    if not value:
        return None
    m = _MS_DATE.fullmatch(value)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Xero's un-suffixed ISO timestamps are UTC; never read them as local time.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _int_header(resp: httpx.Response, name: str) -> int | None:
    raw = resp.headers.get(name)
    return int(raw) if raw and raw.lstrip("-").isdigit() else None


async def _record_quota(tenant_id: str, resp: httpx.Response, retry_after: float | None) -> None:
    now = utcnow()
    rows = [
        {
            "tenant_id": tenant_id,
            "min_remaining": _int_header(resp, "X-MinLimit-Remaining"),
            "day_remaining": _int_header(resp, "X-DayLimit-Remaining"),
            "retry_after_until": now + timedelta(seconds=retry_after) if retry_after else None,
            "observed_at": now,
        }
    ]
    app_min = _int_header(resp, "X-AppMinLimit-Remaining")
    if app_min is not None:
        rows.append(
            {"tenant_id": APP_QUOTA_KEY, "min_remaining": app_min, "day_remaining": None,
             "retry_after_until": None, "observed_at": now}
        )
    async with unit_of_work() as s:
        for row in rows:
            stmt = insert(XeroQuota).values(**row)
            await s.execute(
                stmt.on_conflict_do_update(
                    index_elements=[XeroQuota.tenant_id],
                    set_={k: stmt.excluded[k] for k in row if k != "tenant_id"},
                )
            )


async def _preflight(tenant_id: str) -> None:
    """Wait out or refuse calls when the last-seen quota is at the floor."""
    s = get_settings()
    async with unit_of_work() as db:
        tenant = await db.get(XeroQuota, tenant_id)
        app = await db.get(XeroQuota, APP_QUOTA_KEY)
    now = utcnow()
    if tenant and tenant.retry_after_until and tenant.retry_after_until > now:
        wait = (tenant.retry_after_until - now).total_seconds()
        if wait > MAX_INLINE_WAIT_SECONDS:
            raise QuotaExhausted(tenant_id, tenant.retry_after_until, "Retry-After in effect")
        await asyncio.sleep(wait)
        return
    if tenant and tenant.day_remaining is not None and tenant.day_remaining <= s.xero_day_remaining_floor:
        raise QuotaExhausted(tenant_id, now + timedelta(hours=1), "daily limit nearly used")
    for q in (tenant, app):
        if q and q.min_remaining is not None and q.min_remaining <= s.xero_min_remaining_floor:
            elapsed = (now - q.observed_at).total_seconds()
            if elapsed < 60:
                await asyncio.sleep(60 - elapsed)
                return


class XeroClient:
    def __init__(self, access_token: AccessToken, transport: httpx.AsyncBaseTransport | None = None):
        self._access_token = access_token
        self._transport = transport  # injectable fake for tests

    async def request(
        self,
        tenant_id: str,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        modified_since: datetime | None = None,
    ) -> dict:
        last: XeroApiError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            await _preflight(tenant_id)
            headers = {
                "Authorization": f"Bearer {await self._access_token()}",
                "Xero-Tenant-Id": tenant_id,
                "Accept": "application/json",
            }
            if modified_since:
                headers["If-Modified-Since"] = modified_since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
                resp = await client.request(
                    method, f"{BASE_URL}{path}", headers=headers, params=params, json=json
                )
            retry_after = float(resp.headers["Retry-After"]) if "Retry-After" in resp.headers else None
            await _record_quota(tenant_id, resp, retry_after if resp.status_code == 429 else None)
            if resp.status_code == 429:
                wait = retry_after if retry_after is not None else 2**attempt
                problem = resp.headers.get("X-Rate-Limit-Problem", "unknown")
                if wait > MAX_INLINE_WAIT_SECONDS:
                    raise QuotaExhausted(tenant_id, utcnow() + timedelta(seconds=wait), f"{problem} limit")
                last = XeroApiError(429, resp.text, path)
                await asyncio.sleep(wait)
                continue
            if resp.status_code == 304:  # If-Modified-Since: nothing changed
                return {}
            if resp.status_code >= 400:
                raise XeroApiError(resp.status_code, resp.text, path)
            return resp.json() if resp.content else {}
        raise last or XeroApiError(429, "rate limited", path)

    async def list_accounts(self, tenant_id: str, modified_since: datetime | None = None) -> list[dict]:
        data = await self.request(tenant_id, "GET", "/Accounts", modified_since=modified_since)
        return data.get("Accounts", [])

    async def get_organisation(self, tenant_id: str) -> dict:
        data = await self.request(tenant_id, "GET", "/Organisation")
        return (data.get("Organisations") or [{}])[0]
