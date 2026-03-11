"""Add manual trading tables

Revision ID: m1n2o3p4q5r6
Revises: g2h3i4j5k6l7
Create Date: 2026-03-11

Creates tables for standalone manual trading feature:
- manual_positions: Track manually opened positions with TP/SL
- manual_trades: Individual trades within manual positions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'm1n2o3p4q5r6'
down_revision = 'g2h3i4j5k6l7'
branch_labels = None
depends_on = None


def upgrade():
    # Create manual_positions table
    op.create_table(
        'manual_positions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.String(50), nullable=False, server_default='default'),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('entry_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('leverage', sa.Integer, nullable=False, server_default='10'),
        sa.Column('margin_type', sa.String(10), server_default='CROSSED'),
        sa.Column('entry_order_id', sa.BigInteger, nullable=False, unique=True),
        sa.Column('tp_order_id', sa.BigInteger, nullable=True),
        sa.Column('sl_order_id', sa.BigInteger, nullable=True),
        sa.Column('take_profit_pct', sa.Numeric(10, 6), nullable=True),
        sa.Column('stop_loss_pct', sa.Numeric(10, 6), nullable=True),
        sa.Column('tp_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('sl_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('trailing_stop_enabled', sa.Boolean, server_default='false'),
        sa.Column('trailing_stop_callback_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('status', sa.String(20), server_default='OPEN'),
        sa.Column('remaining_quantity', sa.Numeric(20, 8), nullable=True),
        sa.Column('paper_trading', sa.Boolean, server_default='false'),
        sa.Column('exit_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('exit_order_id', sa.BigInteger, nullable=True),
        sa.Column('exit_reason', sa.String(20), nullable=True),
        sa.Column('realized_pnl', sa.Numeric(20, 8), nullable=True),
        sa.Column('fee_paid', sa.Numeric(20, 8), nullable=True),
        sa.Column('funding_fee', sa.Numeric(20, 8), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.CheckConstraint("side IN ('LONG', 'SHORT')", name='manual_positions_side_check'),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED', 'TP_HIT', 'SL_HIT', 'LIQUIDATED', 'PARTIAL_CLOSE')", name='manual_positions_status_check'),
    )
    
    # Create indexes for manual_positions
    op.create_index('ix_manual_positions_user_id', 'manual_positions', ['user_id'])
    op.create_index('ix_manual_positions_account_id', 'manual_positions', ['account_id'])
    op.create_index('ix_manual_positions_symbol', 'manual_positions', ['symbol'])
    op.create_index('ix_manual_positions_status', 'manual_positions', ['status'])
    op.create_index('ix_manual_positions_paper_trading', 'manual_positions', ['paper_trading'])
    op.create_index('ix_manual_positions_user_status', 'manual_positions', ['user_id', 'status'])
    op.create_index('ix_manual_positions_user_account', 'manual_positions', ['user_id', 'account_id'])
    op.create_index('ix_manual_positions_symbol_account', 'manual_positions', ['symbol', 'account_id'])
    
    # Create manual_trades table
    op.create_table(
        'manual_trades',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('position_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('manual_positions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.BigInteger, nullable=False, unique=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('order_type', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('price', sa.Numeric(20, 8), nullable=False),
        sa.Column('trade_type', sa.String(20), nullable=False),
        sa.Column('commission', sa.Numeric(20, 8), nullable=True),
        sa.Column('commission_asset', sa.String(10), nullable=True),
        sa.Column('realized_pnl', sa.Numeric(20, 8), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name='manual_trades_side_check'),
        sa.CheckConstraint("trade_type IN ('ENTRY', 'PARTIAL_CLOSE', 'EXIT', 'TP', 'SL')", name='manual_trades_type_check'),
    )
    
    # Create indexes for manual_trades
    op.create_index('ix_manual_trades_position_id', 'manual_trades', ['position_id'])
    op.create_index('ix_manual_trades_user_id', 'manual_trades', ['user_id'])
    op.create_index('ix_manual_trades_executed_at', 'manual_trades', ['executed_at'])


def downgrade():
    # Drop indexes first
    op.drop_index('ix_manual_trades_executed_at', table_name='manual_trades')
    op.drop_index('ix_manual_trades_user_id', table_name='manual_trades')
    op.drop_index('ix_manual_trades_position_id', table_name='manual_trades')
    
    op.drop_index('ix_manual_positions_symbol_account', table_name='manual_positions')
    op.drop_index('ix_manual_positions_user_account', table_name='manual_positions')
    op.drop_index('ix_manual_positions_user_status', table_name='manual_positions')
    op.drop_index('ix_manual_positions_paper_trading', table_name='manual_positions')
    op.drop_index('ix_manual_positions_status', table_name='manual_positions')
    op.drop_index('ix_manual_positions_symbol', table_name='manual_positions')
    op.drop_index('ix_manual_positions_account_id', table_name='manual_positions')
    op.drop_index('ix_manual_positions_user_id', table_name='manual_positions')
    
    # Drop tables
    op.drop_table('manual_trades')
    op.drop_table('manual_positions')
