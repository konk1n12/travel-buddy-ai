"""Add hotel location coordinate fields to trips table.

Revision ID: 003_add_hotel_location_coords
Revises: 002_add_trip_city_location
Create Date: 2024-12-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_add_hotel_location_coords'
down_revision: Union[str, None] = '002_add_trip_city_location'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add hotel location coordinate columns to trips table."""
    op.add_column('trips', sa.Column('hotel_lat', sa.Float(), nullable=True))
    op.add_column('trips', sa.Column('hotel_lon', sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove hotel location coordinate columns from trips table."""
    op.drop_column('trips', 'hotel_lon')
    op.drop_column('trips', 'hotel_lat')
