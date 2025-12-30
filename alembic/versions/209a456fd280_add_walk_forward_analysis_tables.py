"""add_walk_forward_analysis_tables

Revision ID: 209a456fd280
Revises: 9087ba9df11b
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '209a456fd280'
down_revision: Union[str, None] = '9087ba9df11b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create walk_forward_analyses table
    op.create_table('walk_forward_analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('strategy_type', sa.String(length=50), nullable=False),
        sa.Column('overall_start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('overall_end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('training_period_days', sa.Integer(), nullable=False),
        sa.Column('test_period_days', sa.Integer(), nullable=False),
        sa.Column('step_size_days', sa.Integer(), nullable=False),
        sa.Column('window_type', sa.String(length=20), nullable=False),
        sa.Column('total_windows', sa.Integer(), nullable=False),
        sa.Column('leverage', sa.Integer(), nullable=False),
        sa.Column('risk_per_trade', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column('initial_balance', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('optimization_enabled', sa.Boolean(), nullable=False),
        sa.Column('optimization_method', sa.String(length=50), nullable=True),
        sa.Column('optimization_metric', sa.String(length=50), nullable=True),
        sa.Column('optimize_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('min_trades_guardrail', sa.Integer(), nullable=True),
        sa.Column('max_drawdown_cap', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('lottery_trade_threshold', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('total_return_pct', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('avg_window_return_pct', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('consistency_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('sharpe_ratio', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('max_drawdown_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('total_trades', sa.Integer(), nullable=False),
        sa.Column('avg_win_rate', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('return_std_dev', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('best_window', sa.Integer(), nullable=True),
        sa.Column('worst_window', sa.Integer(), nullable=True),
        sa.Column('final_balance', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('candles_processed', sa.Integer(), nullable=True),
        sa.Column('keep_details', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("leverage >= 1 AND leverage <= 50", name='wf_analyses_leverage_check'),
        sa.CheckConstraint("risk_per_trade > 0 AND risk_per_trade < 1", name='wf_analyses_risk_check'),
        sa.CheckConstraint("window_type IN ('rolling', 'expanding')", name='wf_analyses_window_type_check')
    )
    op.create_index(op.f('ix_walk_forward_analyses_user_id'), 'walk_forward_analyses', ['user_id'], unique=False)
    op.create_index(op.f('ix_walk_forward_analyses_symbol'), 'walk_forward_analyses', ['symbol'], unique=False)
    op.create_index(op.f('ix_walk_forward_analyses_strategy_type'), 'walk_forward_analyses', ['strategy_type'], unique=False)
    op.create_index(op.f('ix_walk_forward_analyses_overall_start_time'), 'walk_forward_analyses', ['overall_start_time'], unique=False)
    op.create_index(op.f('ix_walk_forward_analyses_created_at'), 'walk_forward_analyses', ['created_at'], unique=False)
    op.create_index('idx_wf_analyses_params', 'walk_forward_analyses', ['params'], unique=False, postgresql_using='gin')
    op.create_index('idx_wf_analyses_created_at', 'walk_forward_analyses', ['created_at'], unique=False, postgresql_ops={'created_at': 'DESC'})
    
    # Create walk_forward_windows table
    op.create_table('walk_forward_windows',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('window_number', sa.Integer(), nullable=False),
        sa.Column('training_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('training_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('test_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('test_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('optimized_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('training_return_pct', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('training_sharpe', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('training_win_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('training_trades', sa.Integer(), nullable=True),
        sa.Column('test_return_pct', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('test_sharpe', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('test_win_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('test_trades', sa.Integer(), nullable=True),
        sa.Column('test_final_balance', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('optimization_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['walk_forward_analyses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("window_number > 0", name='wf_windows_window_number_check')
    )
    op.create_index(op.f('ix_walk_forward_windows_analysis_id'), 'walk_forward_windows', ['analysis_id'], unique=False)
    op.create_index('idx_wf_windows_analysis_window', 'walk_forward_windows', ['analysis_id', 'window_number'], unique=False)
    
    # Create walk_forward_equity_points table
    op.create_table('walk_forward_equity_points',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('balance', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('window_number', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['walk_forward_analyses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_walk_forward_equity_points_analysis_id'), 'walk_forward_equity_points', ['analysis_id'], unique=False)
    op.create_index(op.f('ix_walk_forward_equity_points_time'), 'walk_forward_equity_points', ['time'], unique=False)
    op.create_index('idx_wf_equity_analysis_time', 'walk_forward_equity_points', ['analysis_id', 'time'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_wf_equity_analysis_time', table_name='walk_forward_equity_points')
    op.drop_index(op.f('ix_walk_forward_equity_points_time'), table_name='walk_forward_equity_points')
    op.drop_index(op.f('ix_walk_forward_equity_points_analysis_id'), table_name='walk_forward_equity_points')
    op.drop_table('walk_forward_equity_points')
    
    op.drop_index('idx_wf_windows_analysis_window', table_name='walk_forward_windows')
    op.drop_index(op.f('ix_walk_forward_windows_analysis_id'), table_name='walk_forward_windows')
    op.drop_table('walk_forward_windows')
    
    op.drop_index('idx_wf_analyses_created_at', table_name='walk_forward_analyses')
    op.drop_index('idx_wf_analyses_params', table_name='walk_forward_analyses')
    op.drop_index(op.f('ix_walk_forward_analyses_created_at'), table_name='walk_forward_analyses')
    op.drop_index(op.f('ix_walk_forward_analyses_overall_start_time'), table_name='walk_forward_analyses')
    op.drop_index(op.f('ix_walk_forward_analyses_strategy_type'), table_name='walk_forward_analyses')
    op.drop_index(op.f('ix_walk_forward_analyses_symbol'), table_name='walk_forward_analyses')
    op.drop_index(op.f('ix_walk_forward_analyses_user_id'), table_name='walk_forward_analyses')
    op.drop_table('walk_forward_analyses')
