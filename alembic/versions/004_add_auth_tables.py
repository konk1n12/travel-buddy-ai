"""Add authentication tables and trip ownership

Revision ID: 004_add_auth_tables
Revises: 003_add_hotel_location_coords
Create Date: 2025-01-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_auth_tables'
down_revision = '003_add_hotel_location_coords'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # Create auth_identities table
    op.create_table(
        'auth_identities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('provider_subject', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('provider_data', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_auth_identities_user_id', 'auth_identities', ['user_id'])
    op.create_index('ix_auth_identities_provider_subject', 'auth_identities', ['provider', 'provider_subject'], unique=True)

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('refresh_token_hash', sa.String(), nullable=False, unique=True),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('device_name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])
    op.create_index('ix_sessions_device_id', 'sessions', ['device_id'])

    # Create guest_devices table
    op.create_table(
        'guest_devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('device_id', sa.String(), nullable=False, unique=True),
        sa.Column('generated_trips_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_guest_devices_device_id', 'guest_devices', ['device_id'])

    # Create otp_challenges table
    op.create_table(
        'otp_challenges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('code_hash', sa.String(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_otp_challenges_email', 'otp_challenges', ['email'])

    # Add ownership columns to trips table
    op.add_column('trips', sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('trips', sa.Column('device_id', sa.String(), nullable=True))
    op.create_index('ix_trips_user_id', 'trips', ['user_id'])
    op.create_index('ix_trips_device_id', 'trips', ['device_id'])
    op.create_foreign_key(
        'fk_trips_user_id',
        'trips', 'users',
        ['user_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Remove ownership columns from trips
    op.drop_constraint('fk_trips_user_id', 'trips', type_='foreignkey')
    op.drop_index('ix_trips_device_id', table_name='trips')
    op.drop_index('ix_trips_user_id', table_name='trips')
    op.drop_column('trips', 'device_id')
    op.drop_column('trips', 'user_id')

    # Drop auth tables
    op.drop_table('otp_challenges')
    op.drop_table('guest_devices')
    op.drop_table('sessions')
    op.drop_table('auth_identities')
    op.drop_table('users')
