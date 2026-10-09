"""connection management

Revision ID: b3f1a6c2d8e4
Revises: 7e785c745bdc
Create Date: 2026-10-09 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

from migrations.policies import APP_ROLE

revision = 'b3f1a6c2d8e4'
down_revision = '7e785c745bdc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('entities', sa.Column('status_reason', sa.Text(), nullable=True))
    op.add_column('entities', sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('entities', sa.Column('purge_after', sa.DateTime(timezone=True), nullable=True))
    op.add_column('entities', sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f('ck_entities_status_valid'), 'entities',
                               "status in ('active', 'needs_reconnect', 'disconnected')")
    # A revoked grant's tokens are deleted, not kept.
    op.alter_column('xero_connections', 'token_encrypted', existing_type=sa.Text(), nullable=True)

    # The nightly connection check runs without a workspace context: these list
    # ids only, across workspaces, like canopy_active_entities().
    op.execute(f"""
CREATE FUNCTION canopy_active_connections()
  RETURNS TABLE (workspace_id uuid, connection_id uuid)
  LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT c.workspace_id, c.id FROM xero_connections c WHERE c.status = 'active'
$$;
CREATE FUNCTION canopy_entities_due_for_purge()
  RETURNS TABLE (workspace_id uuid, entity_id uuid)
  LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT e.workspace_id, e.id FROM entities e
    WHERE e.status = 'disconnected' AND e.purged_at IS NULL AND e.purge_after <= now()
$$;
REVOKE ALL ON FUNCTION canopy_active_connections() FROM PUBLIC;
REVOKE ALL ON FUNCTION canopy_entities_due_for_purge() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION canopy_active_connections() TO {APP_ROLE};
GRANT EXECUTE ON FUNCTION canopy_entities_due_for_purge() TO {APP_ROLE};
""")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS canopy_entities_due_for_purge()")
    op.execute("DROP FUNCTION IF EXISTS canopy_active_connections()")
    # Never delete rows here: entities cascade from connections. The old code
    # doesn't decrypt a revoked grant's token, so an empty one is safe.
    op.execute("UPDATE xero_connections SET token_encrypted = '' WHERE token_encrypted IS NULL")
    op.alter_column('xero_connections', 'token_encrypted', existing_type=sa.Text(), nullable=False)
    op.execute("UPDATE entities SET status = 'active' WHERE status = 'needs_reconnect'")
    op.drop_constraint(op.f('ck_entities_status_valid'), 'entities', type_='check')
    op.drop_column('entities', 'purged_at')
    op.drop_column('entities', 'purge_after')
    op.drop_column('entities', 'status_changed_at')
    op.drop_column('entities', 'status_reason')
