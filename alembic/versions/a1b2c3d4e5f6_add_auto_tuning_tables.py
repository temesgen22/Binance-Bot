"""add_auto_tuning_tables

Revision ID: a1b2c3d4e5f6
Revises: 7195ae0c7657
Create Date: 2025-01-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7195ae0c7657'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add auto-tuning columns to strategies table
    op.add_column('strategies', sa.Column('auto_tuning_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('strategies', sa.Column('auto_tuning_config', postgresql.JSONB(), nullable=True))
    
    # Create index for auto_tuning_enabled
    op.create_index('idx_strategies_auto_tuning_enabled', 'strategies', ['auto_tuning_enabled'])
    
    # Create strategy_parameter_history table
    op.create_table(
        'strategy_parameter_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('strategy_uuid', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_label', sa.String(100), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('old_params', postgresql.JSONB(), nullable=False),
        sa.Column('new_params', postgresql.JSONB(), nullable=False),
        sa.Column('changed_params', postgresql.JSONB(), nullable=False),
        sa.Column('reason', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='applied'),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('performance_before', postgresql.JSONB(), nullable=True),
        sa.Column('performance_after', postgresql.JSONB(), nullable=True),
        sa.Column('performance_after_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tuning_run_id', sa.String(100), nullable=True),
        sa.Column('rollback_of_history_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['strategy_uuid'], ['strategies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rollback_of_history_id'], ['strategy_parameter_history.id'], ondelete='SET NULL'),
    )
    
    # Create indexes for strategy_parameter_history
    op.create_index('idx_param_history_user_strategy_created', 'strategy_parameter_history', 
                    ['user_id', 'strategy_uuid', 'created_at'])
    op.create_index('idx_param_history_strategy_uuid', 'strategy_parameter_history', ['strategy_uuid'])
    op.create_index('idx_param_history_status', 'strategy_parameter_history', ['status'])
    op.create_index('idx_param_history_reason', 'strategy_parameter_history', ['reason'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_param_history_reason', table_name='strategy_parameter_history')
    op.drop_index('idx_param_history_status', table_name='strategy_parameter_history')
    op.drop_index('idx_param_history_strategy_uuid', table_name='strategy_parameter_history')
    op.drop_index('idx_param_history_user_strategy_created', table_name='strategy_parameter_history')
    op.drop_index('idx_strategies_auto_tuning_enabled', table_name='strategies')
    
    # Drop table
    op.drop_table('strategy_parameter_history')
    
    # Drop columns from strategies
    op.drop_column('strategies', 'auto_tuning_config')
    op.drop_column('strategies', 'auto_tuning_enabled')









