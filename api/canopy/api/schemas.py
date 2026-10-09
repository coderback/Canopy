"""Response shapes. These drive the OpenAPI schema the web app's TypeScript
types are generated from, so the frontend can't drift from the API."""

from typing import Literal

from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class WorkspaceRef(BaseModel):
    id: str
    name: str
    role: str


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str
    workspaces: list[WorkspaceRef]


class IdOut(BaseModel):
    id: str


class WorkspaceIdOut(BaseModel):
    workspace_id: str


class QueuedOut(BaseModel):
    queued: bool


class CountOut(BaseModel):
    accounts: int


class ConfirmedOut(BaseModel):
    confirmed: int


class MemberOut(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str


class RoleOut(BaseModel):
    id: str
    role: str


class InvitationOut(BaseModel):
    id: str
    email: str
    role: str
    expires_at: str


class InvitationCreated(BaseModel):
    id: str
    token: str
    expires_at: str


class EntityOut(BaseModel):
    id: str
    name: str
    tenant_id: str
    status: Literal["active", "needs_reconnect", "disconnected"]
    sync_status: str
    sync_error: str | None
    last_synced_at: str | None
    can_write: bool
    status_reason: str | None
    status_changed_at: str | None
    # A disconnected org's data is removed after this date (None once removed).
    purge_after: str | None
    purged_at: str | None


class GroupAccountOut(BaseModel):
    id: str
    code: str
    name: str
    type: str
    account_class: str
    description: str | None
    status: str


class LocalAccountOut(BaseModel):
    id: str
    code: str | None
    name: str
    type: str


class MappingOut(BaseModel):
    id: str
    status: Literal["suggested", "confirmed", "rejected"]
    source: Literal["exact", "name", "code_conflict", "ai", "manual", "unmatched", "created"]
    group_account_id: str | None
    confidence: float
    reasoning: str


class GroupRef(BaseModel):
    id: str
    code: str
    name: str


class MappingRow(BaseModel):
    account: LocalAccountOut
    mapping: MappingOut | None
    group_account: GroupRef | None


class DecisionOut(BaseModel):
    id: str
    status: str


class EntityRef(BaseModel):
    id: str
    name: str
    # Gap matrices also show orgs that need reconnecting, flagged as stale.
    status: Literal["active", "needs_reconnect", "disconnected"] = "active"


class GapCell(BaseModel):
    state: Literal["mapped", "pending", "gap"]
    confirmed: int
    suggested: int


class GapRow(BaseModel):
    group_account: GroupRef
    cells: dict[str, GapCell]
    gaps: int


class GapMatrix(BaseModel):
    entities: list[EntityRef]
    rows: list[GapRow]


class TrackingOptionOut(BaseModel):
    id: str
    name: str
    status: Literal["active", "archived"]


class TrackingCategoryOut(BaseModel):
    id: str
    name: str
    status: Literal["active", "archived"]
    options: list[TrackingOptionOut]


class TrackingSeeded(BaseModel):
    categories: int


class TrackingMappingOut(BaseModel):
    id: str
    status: Literal["suggested", "confirmed", "rejected"]
    source: Literal["exact", "manual", "unmatched", "created"]
    group_id: str | None
    confidence: float
    reasoning: str


class NamedRef(BaseModel):
    id: str
    name: str


class TrackingOptionRow(BaseModel):
    id: str
    name: str
    mapping: TrackingMappingOut | None
    group_option: NamedRef | None


class TrackingCategoryRow(BaseModel):
    id: str
    name: str
    mapping: TrackingMappingOut | None
    group_category: NamedRef | None
    options: list[TrackingOptionRow]


class TrackingGapCell(BaseModel):
    # no_category: the org lacks the category itself, so the option can't be added yet.
    state: Literal["mapped", "pending", "gap", "no_category"]
    # Where a missing option would be added (the org category confirmed against the group's).
    entity_category_id: str | None


class TrackingGapOption(BaseModel):
    group_option: NamedRef
    cells: dict[str, TrackingGapCell]
    gaps: int


class TrackingGapCategory(BaseModel):
    group_category: NamedRef
    cells: dict[str, TrackingGapCell]
    gaps: int
    options: list[TrackingGapOption]


class TrackingGapMatrix(BaseModel):
    entities: list[EntityRef]
    categories: list[TrackingGapCategory]


class AuditEventOut(BaseModel):
    id: int
    action: str
    actor_user_id: str | None
    target_type: str | None
    target_id: str | None
    before: dict | None
    after: dict | None
    at: str


class SettingsOut(BaseModel):
    changes_enabled: bool
    allow_self_approval: bool
    writes_enabled_on_server: bool
    # Members who can approve changes. Self-approval only applies while this is 1.
    approvers: int


class ChangeItemOut(BaseModel):
    id: str
    entity_id: str
    entity_name: str
    operation: Literal[
        "create_account", "update_account", "archive_account", "create_tracking_category",
        "create_tracking_option", "update_tracking_category", "update_tracking_option",
        "archive_tracking_category", "archive_tracking_option",
    ]
    account: LocalAccountOut | None
    group_account: GroupRef | None
    # Tracking items: the org's category/option and the group's they align with.
    tracking_category: NamedRef | None = None
    tracking_option: NamedRef | None = None
    group_tracking_category: NamedRef | None = None
    group_tracking_option: NamedRef | None = None
    payload: dict
    preflight_status: Literal["ok", "blocked"]
    preflight_messages: list[str]
    status: Literal["pending", "running", "succeeded", "failed", "skipped"]
    attempt: int
    before: dict | None
    after: dict | None
    error: str | None
    executed_at: str | None


class ChangeSetOut(BaseModel):
    id: str
    title: str
    reason: str
    status: Literal["draft", "submitted", "approved", "rejected", "executing", "completed", "partial", "failed",
                    "cancelled"]
    author: UserOut
    decided_by: UserOut | None
    decision_note: str | None
    self_approved: bool
    # Self-approved and not yet reviewed by someone else.
    needs_review: bool
    reviewed_by: UserOut | None
    reviewed_at: str | None
    review_note: str | None
    created_at: str
    submitted_at: str | None
    decided_at: str | None
    item_counts: dict[str, int]
    items: list[ChangeItemOut] | None = None
    # Only for the author of a submitted change: why they can't approve it
    # themselves (None = they can, with a note).
    self_approval_blocker: str | None = None
