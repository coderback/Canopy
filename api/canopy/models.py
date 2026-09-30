"""Import every model so SQLAlchemy metadata (and Alembic) sees the full schema."""

from .audit.models import AuditEvent  # noqa: F401
from .auth.models import OAuthState, Session, User  # noqa: F401
from .changes.models import ChangeItem, ChangeSet  # noqa: F401
from .mapping.models import AccountMapping  # noqa: F401
from .standard.models import GroupAccount  # noqa: F401
from .sync.models import EntityAccount, EntityTaxRate, SyncRun  # noqa: F401
from .tenancy.models import Invitation, Membership, Role, Workspace  # noqa: F401
from .xero.models import Entity, XeroConnection, XeroQuota  # noqa: F401

# Tables whose rows belong to exactly one workspace: RLS policy
# `workspace_id = current workspace`. Tables with special policies
# (users, workspaces, memberships, audit_events) are handled individually.
WORKSPACE_TABLES = (
    "invitations",
    "xero_connections",
    "entities",
    "entity_accounts",
    "sync_runs",
    "group_accounts",
    "account_mappings",
    "entity_tax_rates",
    "change_sets",
    "change_items",
)
