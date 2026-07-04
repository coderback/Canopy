import pytest

from app.xero.client import XeroApi, XeroApiError


@pytest.mark.asyncio
async def test_tenant_header_is_explicit_per_request(db, token, fake_transport):
    fake_transport.on("GET", "/Organisation", {"Organisations": [{"Name": "Org A"}]})
    api = XeroApi(transport=fake_transport)

    await api.get_organisation(db, "tenant-a")
    await api.get_organisation(db, "tenant-b")

    headers = [r.headers["Xero-Tenant-Id"] for r in fake_transport.requests]
    assert headers == ["tenant-a", "tenant-b"]


@pytest.mark.asyncio
async def test_retry_on_429_then_success(db, token, fake_transport):
    fake_transport.fail_next = [429, 429]
    fake_transport.on("GET", "/Accounts", {"Accounts": [{"Code": "200"}]})
    api = XeroApi(transport=fake_transport)

    accounts = await api.list_accounts(db, "tenant-a")
    assert accounts == [{"Code": "200"}]
    assert len(fake_transport.requests) == 3


@pytest.mark.asyncio
async def test_4xx_raises_with_body(db, token, fake_transport):
    fake_transport.on("PUT", "/Accounts", {"Message": "Code already exists"}, status=400)
    api = XeroApi(transport=fake_transport)

    with pytest.raises(XeroApiError) as err:
        await api.create_account(db, "tenant-a", {"Code": "200", "Name": "X", "Type": "EXPENSE"})
    assert err.value.status_code == 400


@pytest.mark.asyncio
async def test_draft_bill_is_forced_accpay_draft(db, token, fake_transport):
    import json

    fake_transport.on("PUT", "/Invoices", {"Invoices": [{"InvoiceID": "abc", "Status": "DRAFT"}]})
    api = XeroApi(transport=fake_transport)

    await api.create_draft_bill(
        db, "tenant-a", {"Contact": {"Name": "S"}, "LineItems": [], "Status": "AUTHORISED"}
    )
    sent = json.loads(fake_transport.requests[-1].content)["Invoices"][0]
    assert sent["Status"] == "DRAFT" and sent["Type"] == "ACCPAY"
