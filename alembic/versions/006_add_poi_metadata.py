"""Add POI metadata fields

Revision ID: 006_add_poi_metadata
Revises: 005_add_trip_legacy_public
Create Date: 2026-01-04 15:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_add_poi_metadata'
down_revision = '005_add_trip_legacy_public'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('pois', sa.Column('user_ratings_total', sa.Integer(), nullable=True))
    op.add_column('pois', sa.Column('business_status', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('pois', 'business_status')
    op.drop_column('pois', 'user_ratings_total')
