"""Pydantic contracts.

The mapping/ingest/matching engines emit `EngineProposal` JSON. Nothing is
written to Xero unless the payload validates against the action's schema
below AND a human has approved the row. The LLM proposes; code writes.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ChangeType = Literal["contact", "item", "account", "tracking", "manual_journal", "bill"]

ACTIONS = (
    "create-contact",
    "create-item",
    "create-account",
    "create-tracking-category",
    "create-manual-journal",
    "create-bill",
)


class EngineProposal(BaseModel):
    """The JSON contract every engine (mapping / ingest / matching) must emit."""

    action: str
    mapped_payload: dict
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    needs_human: bool = False

    @field_validator("action")
    @classmethod
    def action_known(cls, v: str) -> str:
        if v not in ACTIONS:
            raise ValueError(f"unknown action {v!r}")
        return v


# ---- per-action write payload schemas (validated before ANY write) --------


class ContactPayload(BaseModel):
    Name: str
    EmailAddress: str | None = None
    ContactNumber: str | None = None
    ContactID: str | None = None  # present → update/link instead of create
    IsSupplier: bool | None = None
    IsCustomer: bool | None = None
    Phones: list[dict] | None = None
    Addresses: list[dict] | None = None


class ItemPayload(BaseModel):
    Code: str
    Name: str
    Description: str | None = None
    IsSold: bool | None = None
    IsPurchased: bool | None = None
    SalesDetails: dict | None = None  # {"UnitPrice":..., "AccountCode":..., "TaxType":...}
    PurchaseDetails: dict | None = None


class AccountPayload(BaseModel):
    Code: str
    Name: str
    Type: str  # e.g. EXPENSE, REVENUE — Xero AccountType enum
    Description: str | None = None
    TaxType: str | None = None


class TrackingCategoryPayload(BaseModel):
    Name: str
    Options: list[str] = []


class JournalLine(BaseModel):
    LineAmount: float
    AccountCode: str
    Description: str | None = None
    Tracking: list[dict] | None = None


class ManualJournalPayload(BaseModel):
    Narration: str
    JournalLines: list[JournalLine]
    Date: str | None = None
    Status: Literal["DRAFT", "POSTED"] = "DRAFT"

    @field_validator("JournalLines")
    @classmethod
    def must_balance(cls, lines: list[JournalLine]) -> list[JournalLine]:
        if len(lines) < 2:
            raise ValueError("a journal needs at least two lines")
        total = round(sum(line.LineAmount for line in lines), 2)
        if abs(total) > 0.005:
            raise ValueError(f"journal lines must sum to zero, got {total}")
        return lines


class BillLineItem(BaseModel):
    Description: str
    Quantity: float
    UnitAmount: float
    AccountCode: str
    TaxType: str | None = None


class BillPayload(BaseModel):
    Contact: dict  # {"ContactID": ...} or {"Name": ...}
    Date: str | None = None
    DueDate: str | None = None
    InvoiceNumber: str | None = None
    Reference: str | None = None
    LineItems: list[BillLineItem]
    # Type/Status are forced to ACCPAY/DRAFT by the client — not accepted here.


PAYLOAD_SCHEMAS: dict[str, type[BaseModel]] = {
    "create-contact": ContactPayload,
    "create-item": ItemPayload,
    "create-account": AccountPayload,
    "create-tracking-category": TrackingCategoryPayload,
    "create-manual-journal": ManualJournalPayload,
    "create-bill": BillPayload,
}


def validate_payload(action: str, payload: dict) -> dict:
    """Validate + normalise a payload for its action. Raises on failure."""
    schema = PAYLOAD_SCHEMAS[action]
    return schema.model_validate(payload).model_dump(exclude_none=True)
