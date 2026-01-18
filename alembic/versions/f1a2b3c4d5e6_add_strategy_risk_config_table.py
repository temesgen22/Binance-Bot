"""add_strategy_risk_config_table

Revision ID: f1a2b3c4d5e6
Revises: ed0664149df0
Create Date: 2026-01-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '119315fdd8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create strategy_risk_config table
    op.create_table(
        'strategy_risk_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Strategy-Level Limits
        sa.Column('max_daily_loss_usdt', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('max_daily_loss_pct', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('max_weekly_loss_usdt', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('max_weekly_loss_pct', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('max_drawdown_pct', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('max_exposure_usdt', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('max_exposure_pct', sa.Numeric(precision=10, scale=6), nullable=True),
        
        # Behavior Settings
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('override_account_limits', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('use_more_restrictive', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        
        # Loss Reset Configuration
        sa.Column('daily_loss_reset_time', sa.DateTime(timezone=False), nullable=True),
        sa.Column('weekly_loss_reset_day', sa.Integer(), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='UTC'),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('strategy_id', name='strategy_risk_config_strategy_id_unique'),
    )
    
    # Create indexes
    op.create_index('idx_strategy_risk_config_strategy_id', 'strategy_risk_config', ['strategy_id'], unique=True)
    op.create_index('idx_strategy_risk_config_user_id', 'strategy_risk_config', ['user_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_strategy_risk_config_user_id', table_name='strategy_risk_config')
    op.drop_index('idx_strategy_risk_config_strategy_id', table_name='strategy_risk_config')
    
    # Drop table
    op.drop_table('strategy_risk_config')

