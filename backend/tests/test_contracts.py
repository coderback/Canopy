import pytest
from pydantic import ValidationError

from app.engines.contracts import EngineProposal, validate_payload


def test_valid_contact_payload():
    payload = validate_payload("create-contact", {"Name": "Acme Corp", "EmailAddress": "x@acme.com"})
    assert payload == {"Name": "Acme Corp", "EmailAddress": "x@acme.com"}


def test_contact_requires_name():
    with pytest.raises(ValidationError):
        validate_payload("create-contact", {"EmailAddress": "x@acme.com"})


def test_account_requires_code_name_type():
    payload = validate_payload("create-account", {"Code": "492", "Name": "Site Repairs", "Type": "EXPENSE"})
    assert payload["Type"] == "EXPENSE"
    with pytest.raises(ValidationError):
        validate_payload("create-account", {"Code": "492", "Name": "Site Repairs"})


def test_tracking_options_coerced_from_dict_form():
    # The model sometimes emits Xero's native [{"Name": "Sales"}] shape; both that
    # and the plain-string form must normalise to ["Sales", ...] rather than fail.
    dict_form = validate_payload(
        "create-tracking-category",
        {"Name": "Department", "Options": [{"Name": "Sales"}, {"Name": "Ops"}]},
    )
    assert dict_form["Options"] == ["Sales", "Ops"]
    str_form = validate_payload(
        "create-tracking-category", {"Name": "Department", "Options": ["Sales", "Ops"]}
    )
    assert str_form["Options"] == ["Sales", "Ops"]


def test_manual_journal_must_balance():
    lines_ok = [
        {"LineAmount": 120.5, "AccountCode": "300"},
        {"LineAmount": -120.5, "AccountCode": "630"},
    ]
    payload = validate_payload(
        "create-manual-journal", {"Narration": "Stock adj", "JournalLines": lines_ok}
    )
    assert payload["Status"] == "DRAFT"

    lines_bad = [
        {"LineAmount": 120.5, "AccountCode": "300"},
        {"LineAmount": -100.0, "AccountCode": "630"},
    ]
    with pytest.raises(ValidationError):
        validate_payload("create-manual-journal", {"Narration": "x", "JournalLines": lines_bad})


def test_bill_payload_cannot_set_status():
    # Type/Status are forced by the client (ACCPAY/DRAFT); schema drops extras.
    payload = validate_payload(
        "create-bill",
        {
            "Contact": {"Name": "Supplies Ltd"},
            "LineItems": [
                {"Description": "Widgets", "Quantity": 2, "UnitAmount": 10.0, "AccountCode": "300"}
            ],
        },
    )
    assert "Status" not in payload and "Type" not in payload


def test_engine_proposal_contract():
    p = EngineProposal(
        action="create-item",
        mapped_payload={"Code": "TRAMP-SOCK"},
        confidence=0.92,
        reasoning="Mapped 200 Sales -> 201 Trading Income",
    )
    assert not p.needs_human
    with pytest.raises(ValidationError):
        EngineProposal(action="delete-everything", mapped_payload={}, confidence=0.5, reasoning="no")
    with pytest.raises(ValidationError):
        EngineProposal(action="create-item", mapped_payload={}, confidence=1.5, reasoning="no")
