"""Uniform Xero Accounting API client.

One httpx code path for every endpoint (the Accounting API is plain JSON),
which keeps tenant handling in exactly one place and makes tests trivial via
transport injection. Rules enforced here:

- EVERY call takes an explicit tenant_id — never cached globally (Xero guidance).
- Per-tenant rate limiting (60/min tenant limit) + 429 retry honouring Retry-After.
- Correct verbs per endpoint: PUT Accounts / ManualJournals / TrackingCategories /
  Invoices create; POST Contacts / Items create-or-update (idempotent by
  ContactID / item Code — our idempotency story for retries).
"""

import asyncio

import httpx
from sqlalchemy.orm import Session

from . import auth
from .ratelimit import limiter

BASE_URL = "https://api.xero.com/api.xro/2.0"
MAX_RETRIES = 4


class XeroApiError(Exception):
    def __init__(self, status_code: int, body: str, path: str):
        self.status_code = status_code
        self.body = body
        self.path = path
        super().__init__(f"Xero API {status_code} on {path}: {body[:500]}")


class XeroApi:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport  # injectable fake for tests

    async def request(
        self,
        db: Session,
        tenant_id: str,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        access_token = await auth.get_valid_access_token(db)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Xero-Tenant-Id": tenant_id,
            "Accept": "application/json",
        }
        last_error: XeroApiError | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            await limiter.acquire(tenant_id)
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
                resp = await client.request(
                    method, f"{BASE_URL}{path}", headers=headers, json=json, params=params
                )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                await asyncio.sleep(retry_after)
                last_error = XeroApiError(429, resp.text, path)
                continue
            if resp.status_code >= 400:
                raise XeroApiError(resp.status_code, resp.text, path)
            return resp.json() if resp.content else {}
        raise last_error or XeroApiError(429, "rate limited", path)

    # ---- reads -----------------------------------------------------------

    async def get_organisation(self, db, tenant_id: str) -> dict:
        data = await self.request(db, tenant_id, "GET", "/Organisation")
        return data["Organisations"][0]

    async def list_accounts(self, db, tenant_id: str) -> list[dict]:
        return (await self.request(db, tenant_id, "GET", "/Accounts")).get("Accounts", [])

    async def list_tax_rates(self, db, tenant_id: str) -> list[dict]:
        return (await self.request(db, tenant_id, "GET", "/TaxRates")).get("TaxRates", [])

    async def list_contacts(self, db, tenant_id: str) -> list[dict]:
        return (await self.request(db, tenant_id, "GET", "/Contacts")).get("Contacts", [])

    async def list_items(self, db, tenant_id: str) -> list[dict]:
        return (await self.request(db, tenant_id, "GET", "/Items")).get("Items", [])

    async def list_tracking_categories(self, db, tenant_id: str) -> list[dict]:
        return (await self.request(db, tenant_id, "GET", "/TrackingCategories")).get(
            "TrackingCategories", []
        )

    async def list_purchase_orders(self, db, tenant_id: str, status: str = "AUTHORISED") -> list[dict]:
        data = await self.request(
            db, tenant_id, "GET", "/PurchaseOrders", params={"Status": status}
        )
        return data.get("PurchaseOrders", [])

    # ---- writes (only called by the deterministic execution layer) -------

    async def create_or_update_contact(self, db, tenant_id: str, contact: dict) -> dict:
        data = await self.request(db, tenant_id, "POST", "/Contacts", json={"Contacts": [contact]})
        return data["Contacts"][0]

    async def create_or_update_item(self, db, tenant_id: str, item: dict) -> dict:
        data = await self.request(db, tenant_id, "POST", "/Items", json={"Items": [item]})
        return data["Items"][0]

    async def create_account(self, db, tenant_id: str, account: dict) -> dict:
        # No MCP tool exists for this — raw PUT Accounts (Code, Name, Type required).
        data = await self.request(db, tenant_id, "PUT", "/Accounts", json=account)
        return data["Accounts"][0]

    async def create_tracking_category(self, db, tenant_id: str, category: dict) -> dict:
        data = await self.request(
            db, tenant_id, "PUT", "/TrackingCategories", json=category
        )
        return data["TrackingCategories"][0]

    async def add_tracking_option(self, db, tenant_id: str, category_id: str, option: dict) -> dict:
        data = await self.request(
            db, tenant_id, "PUT", f"/TrackingCategories/{category_id}/Options", json=option
        )
        return data["Options"][0]

    async def create_manual_journal(self, db, tenant_id: str, journal: dict) -> dict:
        data = await self.request(
            db, tenant_id, "PUT", "/ManualJournals", json={"ManualJournals": [journal]}
        )
        return data["ManualJournals"][0]

    async def create_draft_bill(self, db, tenant_id: str, bill: dict) -> dict:
        # ApprovalMax-safe by construction: Type ACCPAY, Status DRAFT, and we
        # NEVER touch the source purchase order's status.
        bill = {**bill, "Type": "ACCPAY", "Status": "DRAFT"}
        data = await self.request(db, tenant_id, "PUT", "/Invoices", json={"Invoices": [bill]})
        return data["Invoices"][0]


xero_api = XeroApi()
