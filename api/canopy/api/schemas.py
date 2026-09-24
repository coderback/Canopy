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
    status: str
    sync_status: str
    sync_error: str | None
    last_synced_at: str | None


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
    source: Literal["exact", "name", "code_conflict", "ai", "manual", "unmatched"]
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


class AuditEventOut(BaseModel):
    id: int
    action: str
    actor_user_id: str | None
    target_type: str | None
    target_id: str | None
    before: dict | None
    after: dict | None
    at: str
