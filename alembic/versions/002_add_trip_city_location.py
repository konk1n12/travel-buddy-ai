"""Add city center location fields to trips table.

Revision ID: 002_add_trip_city_location
Revises: 001_add_poi_external_fields
Create Date: 2024-12-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_add_trip_city_location'
down_revision: Union[str, None] = '001_add_poi_external_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add city center location columns to trips table."""
    op.add_column('trips', sa.Column('city_center_lat', sa.Float(), nullable=True))
    op.add_column('trips', sa.Column('city_center_lon', sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove city center location columns from trips table."""
    op.drop_column('trips', 'city_center_lon')
    op.drop_column('trips', 'city_center_lat')
