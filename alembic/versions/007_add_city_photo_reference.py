"""Add city_photo_reference to trips table.

Revision ID: 007_add_city_photo_reference
Revises: ffec9c372e4b
Create Date: 2026-01-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007_add_city_photo_reference'
down_revision: Union[str, None] = '23e8c4b0eaed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add city_photo_reference column to trips table."""
    op.add_column('trips', sa.Column('city_photo_reference', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove city_photo_reference column from trips table."""
    op.drop_column('trips', 'city_photo_reference')
