"""add_sensitivity_analysis_tables

Revision ID: 7195ae0c7657
Revises: ed0664149df0
Create Date: 2025-01-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7195ae0c7657'
down_revision: Union[str, None] = 'ed0664149df0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sensitivity_analyses table
    op.create_table(
        'sensitivity_analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('strategy_type', sa.String(50), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('base_params', postgresql.JSONB, nullable=False),
        sa.Column('analyze_params', postgresql.JSONB, nullable=False),
        sa.Column('metric', sa.String(50), nullable=False),
        sa.Column('kline_interval', sa.String(10), nullable=False),
        sa.Column('leverage', sa.Integer, nullable=False),
        sa.Column('risk_per_trade', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column('fixed_amount', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('initial_balance', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('most_sensitive_param', sa.String(100), nullable=True),
        sa.Column('least_sensitive_param', sa.String(100), nullable=True),
        sa.Column('recommended_params', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for sensitivity_analyses
    op.create_index('idx_sensitivity_analyses_user_id', 'sensitivity_analyses', ['user_id'])
    op.create_index('idx_sensitivity_analyses_symbol', 'sensitivity_analyses', ['symbol'])
    op.create_index('idx_sensitivity_analyses_strategy_type', 'sensitivity_analyses', ['strategy_type'])
    op.create_index('idx_sensitivity_analyses_created_at', 'sensitivity_analyses', ['created_at'])
    
    # Create sensitivity_parameter_results table
    op.create_table(
        'sensitivity_parameter_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('analysis_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parameter_name', sa.String(100), nullable=False),
        sa.Column('base_value', postgresql.JSONB, nullable=True),
        sa.Column('tested_values', postgresql.JSONB, nullable=False),
        sa.Column('sensitivity_score', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('optimal_value', postgresql.JSONB, nullable=True),
        sa.Column('worst_value', postgresql.JSONB, nullable=True),
        sa.Column('impact_range', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('impact_range_display', sa.String(255), nullable=True),
        sa.Column('results', postgresql.JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['analysis_id'], ['sensitivity_analyses.id'], ondelete='CASCADE'),
    )
    
    # Create index for sensitivity_parameter_results
    op.create_index('idx_sensitivity_param_results_analysis_id', 'sensitivity_parameter_results', ['analysis_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_sensitivity_param_results_analysis_id', table_name='sensitivity_parameter_results')
    op.drop_index('idx_sensitivity_analyses_created_at', table_name='sensitivity_analyses')
    op.drop_index('idx_sensitivity_analyses_strategy_type', table_name='sensitivity_analyses')
    op.drop_index('idx_sensitivity_analyses_symbol', table_name='sensitivity_analyses')
    op.drop_index('idx_sensitivity_analyses_user_id', table_name='sensitivity_analyses')
    
    # Drop tables
    op.drop_table('sensitivity_parameter_results')
    op.drop_table('sensitivity_analyses')
