"""Add legacy public flag and ownership constraint

Revision ID: 005_add_trip_legacy_public
Revises: 004_add_auth_tables
Create Date: 2025-01-04 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_add_trip_legacy_public'
down_revision = '004_add_auth_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'trips',
        sa.Column('is_legacy_public', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )

    # Preserve access to truly legacy trips that had no ownership before auth.
    op.execute(
        "UPDATE trips SET is_legacy_public = TRUE WHERE user_id IS NULL AND device_id IS NULL"
    )

    op.create_check_constraint(
        'ck_trips_owner_or_legacy_public',
        'trips',
        'user_id IS NOT NULL OR device_id IS NOT NULL OR is_legacy_public = TRUE',
    )


def downgrade() -> None:
    op.drop_constraint('ck_trips_owner_or_legacy_public', 'trips', type_='check')
    op.drop_column('trips', 'is_legacy_public')
