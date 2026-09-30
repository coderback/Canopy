"""change control and tax rates

Revision ID: 79b69070b26d
Revises: 19627eb25682
Create Date: 2026-09-24 12:37:01.539249
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations import policies

revision = '79b69070b26d'
down_revision = '19627eb25682'
branch_labels = None
depends_on = None

NEW_WORKSPACE_TABLES = ("entity_tax_rates", "change_sets", "change_items")


def upgrade() -> None:
    op.add_column('workspaces', sa.Column('changes_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('workspaces', sa.Column('allow_self_approval', sa.Boolean(), server_default='false', nullable=False))

    op.create_table('entity_tax_rates',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('tax_type', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('effective_rate', sa.Float(), nullable=True),
    sa.Column('can_apply_to_revenue', sa.Boolean(), nullable=True),
    sa.Column('can_apply_to_expenses', sa.Boolean(), nullable=True),
    sa.Column('can_apply_to_assets', sa.Boolean(), nullable=True),
    sa.Column('can_apply_to_liabilities', sa.Boolean(), nullable=True),
    sa.Column('can_apply_to_equity', sa.Boolean(), nullable=True),
    sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], name=op.f('fk_entity_tax_rates_entity_id_entities'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_entity_tax_rates_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_entity_tax_rates')),
    sa.UniqueConstraint('entity_id', 'tax_type', name=op.f('uq_entity_tax_rates_entity_id_tax_type'))
    )
    op.create_index(op.f('ix_entity_tax_rates_entity_id'), 'entity_tax_rates', ['entity_id'], unique=False)
    op.create_index(op.f('ix_entity_tax_rates_workspace_id'), 'entity_tax_rates', ['workspace_id'], unique=False)

    op.create_table('change_sets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_by', sa.Uuid(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('self_approved', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status in ('draft', 'submitted', 'approved', 'rejected', 'executing', 'completed', 'partial', 'failed', 'cancelled')", name=op.f('ck_change_sets_status_valid')),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_change_sets_author_id_users')),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name=op.f('fk_change_sets_decided_by_users')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_change_sets_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_change_sets'))
    )
    op.create_index(op.f('ix_change_sets_workspace_id'), 'change_sets', ['workspace_id'], unique=False)

    op.create_table('change_items',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('change_set_id', sa.Uuid(), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('operation', sa.String(length=32), nullable=False),
    sa.Column('entity_account_id', sa.Uuid(), nullable=True),
    sa.Column('group_account_id', sa.Uuid(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('preflight_status', sa.String(length=16), nullable=False),
    sa.Column('preflight_messages', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('xero_account_id', sa.String(length=64), nullable=True),
    sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("operation in ('create_account', 'update_account', 'archive_account')", name=op.f('ck_change_items_operation_valid')),
    sa.CheckConstraint("preflight_status in ('ok', 'blocked')", name=op.f('ck_change_items_preflight_valid')),
    sa.CheckConstraint("status in ('pending', 'running', 'succeeded', 'failed', 'skipped')", name=op.f('ck_change_items_status_valid')),
    sa.ForeignKeyConstraint(['change_set_id'], ['change_sets.id'], name=op.f('fk_change_items_change_set_id_change_sets'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['entity_account_id'], ['entity_accounts.id'], name=op.f('fk_change_items_entity_account_id_entity_accounts'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], name=op.f('fk_change_items_entity_id_entities'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['group_account_id'], ['group_accounts.id'], name=op.f('fk_change_items_group_account_id_group_accounts'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_change_items_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_change_items'))
    )
    op.create_index(op.f('ix_change_items_change_set_id'), 'change_items', ['change_set_id'], unique=False)
    op.create_index(op.f('ix_change_items_entity_id'), 'change_items', ['entity_id'], unique=False)
    op.create_index(op.f('ix_change_items_workspace_id'), 'change_items', ['workspace_id'], unique=False)

    # Same isolation as every other workspace table (see migrations/policies.py).
    op.execute(policies.workspace_isolation_sql(NEW_WORKSPACE_TABLES))


def downgrade() -> None:
    for table in NEW_WORKSPACE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS workspace_isolation ON {table}")
    op.drop_index(op.f('ix_change_items_workspace_id'), table_name='change_items')
    op.drop_index(op.f('ix_change_items_entity_id'), table_name='change_items')
    op.drop_index(op.f('ix_change_items_change_set_id'), table_name='change_items')
    op.drop_table('change_items')
    op.drop_index(op.f('ix_change_sets_workspace_id'), table_name='change_sets')
    op.drop_table('change_sets')
    op.drop_index(op.f('ix_entity_tax_rates_workspace_id'), table_name='entity_tax_rates')
    op.drop_index(op.f('ix_entity_tax_rates_entity_id'), table_name='entity_tax_rates')
    op.drop_table('entity_tax_rates')
    op.drop_column('workspaces', 'allow_self_approval')
    op.drop_column('workspaces', 'changes_enabled')
