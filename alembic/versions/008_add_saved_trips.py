"""Add saved_trips table for user trip bookmarks.

Revision ID: 008_add_saved_trips
Revises: 007_add_city_photo_reference
Create Date: 2026-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '008_add_saved_trips'
down_revision: Union[str, None] = '007_add_city_photo_reference'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create saved_trips table."""
    op.create_table(
        'saved_trips',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('trip_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('trips.id', ondelete='CASCADE'), nullable=False),
        sa.Column('city_name', sa.String(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('hero_image_url', sa.String(), nullable=True),
        sa.Column('route_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Index for efficient user queries sorted by date
    op.create_index('ix_saved_trips_user_id_start_date', 'saved_trips', ['user_id', 'start_date'])

    # Unique constraint: user can save a trip only once
    op.create_unique_constraint('uq_saved_trips_user_trip', 'saved_trips', ['user_id', 'trip_id'])


def downgrade() -> None:
    """Drop saved_trips table."""
    op.drop_constraint('uq_saved_trips_user_trip', 'saved_trips', type_='unique')
    op.drop_index('ix_saved_trips_user_id_start_date', table_name='saved_trips')
    op.drop_table('saved_trips')
