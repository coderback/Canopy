"""self-approval review

Revision ID: 4c1d8e2a9f37
Revises: 79b69070b26d
Create Date: 2026-09-30 14:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = '4c1d8e2a9f37'
down_revision = '79b69070b26d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('change_sets', sa.Column('reviewed_by', sa.Uuid(), nullable=True))
    op.add_column('change_sets', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('change_sets', sa.Column('review_note', sa.Text(), nullable=True))
    op.create_foreign_key(op.f('fk_change_sets_reviewed_by_users'), 'change_sets', 'users', ['reviewed_by'], ['id'])
    # A review is only ever of a self-approved set, by someone other than its author.
    op.create_check_constraint(
        op.f('ck_change_sets_review_needs_self_approval'), 'change_sets',
        'reviewed_at IS NULL OR (self_approved AND reviewed_by IS NOT NULL AND reviewed_by <> author_id)',
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_change_sets_review_needs_self_approval'), 'change_sets', type_='check')
    op.drop_constraint(op.f('fk_change_sets_reviewed_by_users'), 'change_sets', type_='foreignkey')
    op.drop_column('change_sets', 'review_note')
    op.drop_column('change_sets', 'reviewed_at')
    op.drop_column('change_sets', 'reviewed_by')
