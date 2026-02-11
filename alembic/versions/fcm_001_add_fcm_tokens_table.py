"""add_fcm_tokens_table

Revision ID: fcm_001
Revises: 44f822589e58
Create Date: 2026-02-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fcm_001'
down_revision: Union[str, None] = '44f822589e58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add fcm_tokens table for Firebase Cloud Messaging push notifications."""
    # Make migration idempotent: check for existing objects BEFORE creating them
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    # Helper to get indexes for a table (returns empty list if table doesn't exist)
    def get_table_indexes(table_name):
        if table_name not in existing_tables:
            return []
        try:
            return [idx['name'] for idx in inspector.get_indexes(table_name)]
        except Exception:
            return []
    
    # Create fcm_tokens table if it doesn't exist
    if 'fcm_tokens' not in existing_tables:
        op.create_table(
            'fcm_tokens',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('token', sa.String(500), nullable=False),
            sa.Column('device_id', sa.String(255), nullable=False),
            sa.Column('device_type', sa.String(50), nullable=False, server_default='android'),
            sa.Column('client_type', sa.String(50), nullable=False, server_default='android_app'),
            sa.Column('device_name', sa.String(100), nullable=True),
            sa.Column('app_version', sa.String(50), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        )
        
        # Create indexes
        fcm_indexes = get_table_indexes('fcm_tokens')
        
        if 'ix_fcm_tokens_user_id' not in fcm_indexes:
            op.create_index('ix_fcm_tokens_user_id', 'fcm_tokens', ['user_id'])
        
        if 'ix_fcm_tokens_token' not in fcm_indexes:
            op.create_index('ix_fcm_tokens_token', 'fcm_tokens', ['token'], unique=True)
        
        if 'ix_fcm_tokens_device_id' not in fcm_indexes:
            op.create_index('ix_fcm_tokens_device_id', 'fcm_tokens', ['device_id'])
        
        if 'idx_fcm_tokens_user_device' not in fcm_indexes:
            op.create_index('idx_fcm_tokens_user_device', 'fcm_tokens', ['user_id', 'device_id'], unique=True)
        
        if 'idx_fcm_tokens_active' not in fcm_indexes:
            op.create_index('idx_fcm_tokens_active', 'fcm_tokens', ['is_active'])
        
        if 'ix_fcm_tokens_created_at' not in fcm_indexes:
            op.create_index('ix_fcm_tokens_created_at', 'fcm_tokens', ['created_at'])
        
        if 'idx_fcm_tokens_client_type' not in fcm_indexes:
            op.create_index('idx_fcm_tokens_client_type', 'fcm_tokens', ['client_type'])


def downgrade() -> None:
    """Drop fcm_tokens table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    if 'fcm_tokens' in existing_tables:
        # Drop indexes first (in reverse order of creation)
        op.drop_index('idx_fcm_tokens_client_type', table_name='fcm_tokens')
        op.drop_index('ix_fcm_tokens_created_at', table_name='fcm_tokens')
        op.drop_index('idx_fcm_tokens_active', table_name='fcm_tokens')
        op.drop_index('idx_fcm_tokens_user_device', table_name='fcm_tokens')
        op.drop_index('ix_fcm_tokens_device_id', table_name='fcm_tokens')
        op.drop_index('ix_fcm_tokens_token', table_name='fcm_tokens')
        op.drop_index('ix_fcm_tokens_user_id', table_name='fcm_tokens')
        
        # Drop table
        op.drop_table('fcm_tokens')
