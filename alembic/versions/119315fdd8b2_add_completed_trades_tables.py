"""add_completed_trades_tables

Revision ID: 119315fdd8b2
Revises: c9d8e7f6a5b4
Create Date: 2026-01-08 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '119315fdd8b2'
down_revision: Union[str, None] = 'c9d8e7f6a5b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add completed_trades and completed_trade_orders tables."""
    from sqlalchemy import inspect
    
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    def get_table_indexes(table_name: str) -> list[str]:
        try:
            return [idx['name'] for idx in inspector.get_indexes(table_name)]
        except Exception:
            return []
    
    # Create completed_trades table
    if 'completed_trades' not in existing_tables:
        op.create_table(
            'completed_trades',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('close_event_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('entry_order_id', sa.BigInteger(), nullable=False),
            sa.Column('exit_order_id', sa.BigInteger(), nullable=False),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('side', sa.String(length=10), nullable=False),
            sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
            sa.Column('exit_time', sa.DateTime(timezone=True), nullable=False),
            sa.Column('entry_price', sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column('exit_price', sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column('quantity', sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column('pnl_usd', sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column('pnl_pct', sa.Numeric(precision=10, scale=4), nullable=False),
            sa.Column('fee_paid', sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column('funding_fee', sa.Numeric(precision=20, scale=8), nullable=False, server_default='0.0'),
            sa.Column('leverage', sa.Integer(), nullable=True),
            sa.Column('exit_reason', sa.String(length=50), nullable=True),
            sa.Column('initial_margin', sa.Numeric(precision=20, scale=8), nullable=True),
            sa.Column('margin_type', sa.String(length=20), nullable=True),
            sa.Column('notional_value', sa.Numeric(precision=20, scale=8), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
            sa.CheckConstraint("side IN ('LONG', 'SHORT')", name='completed_trades_side_check'),
            sa.UniqueConstraint('user_id', 'strategy_id', 'close_event_id', name='uq_completed_trade_idempotency'),
        )
    
    # Create indexes for completed_trades
    completed_trades_indexes = get_table_indexes('completed_trades')
    if 'idx_completed_trades_strategy_id' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_strategy_id', 'completed_trades', ['strategy_id'])
    if 'idx_completed_trades_user_id' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_user_id', 'completed_trades', ['user_id'])
    if 'idx_completed_trades_account_id' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_account', 'completed_trades', ['account_id'])
    if 'idx_completed_trades_close_event_id' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_close_event_id', 'completed_trades', ['close_event_id'], unique=True)
    if 'idx_completed_trades_entry_order_id' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_entry_order_id', 'completed_trades', ['entry_order_id'])
    if 'idx_completed_trades_exit_order_id' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_exit_order_id', 'completed_trades', ['exit_order_id'])
    if 'idx_completed_trades_symbol' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_symbol', 'completed_trades', ['symbol'])
    if 'idx_completed_trades_entry_time' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_entry_time', 'completed_trades', ['entry_time'])
    if 'idx_completed_trades_exit_time' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_exit_time', 'completed_trades', ['exit_time'])
    if 'idx_completed_trades_user_strategy' not in completed_trades_indexes:
        op.create_index('idx_completed_trades_user_strategy', 'completed_trades', ['user_id', 'strategy_id'])
    
    # Create completed_trade_orders table
    if 'completed_trade_orders' not in existing_tables:
        op.create_table(
            'completed_trade_orders',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('completed_trade_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('trade_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('order_id', sa.BigInteger(), nullable=False),
            sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('order_role', sa.String(length=10), nullable=False),
            sa.Column('quantity', sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column('price', sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['completed_trade_id'], ['completed_trades.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['trade_id'], ['trades.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
            sa.CheckConstraint("order_role IN ('ENTRY', 'EXIT')", name='completed_trade_orders_role_check'),
            sa.UniqueConstraint('completed_trade_id', 'trade_id', 'order_role', name='uq_completed_trade_order'),
        )
    
    # Create indexes for completed_trade_orders
    completed_trade_orders_indexes = get_table_indexes('completed_trade_orders')
    if 'idx_completed_trade_orders_completed_trade_id' not in completed_trade_orders_indexes:
        op.create_index('idx_completed_trade_orders_completed_trade', 'completed_trade_orders', ['completed_trade_id'])
    if 'idx_completed_trade_orders_trade_id' not in completed_trade_orders_indexes:
        op.create_index('idx_completed_trade_orders_trade', 'completed_trade_orders', ['trade_id'])
    if 'idx_completed_trade_orders_order_id' not in completed_trade_orders_indexes:
        op.create_index('idx_completed_trade_orders_order', 'completed_trade_orders', ['order_id'])
    if 'idx_completed_trade_orders_account_id' not in completed_trade_orders_indexes:
        op.create_index('idx_completed_trade_orders_account', 'completed_trade_orders', ['account_id'])


def downgrade() -> None:
    """Remove completed_trades and completed_trade_orders tables."""
    from sqlalchemy import inspect
    
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    if 'completed_trade_orders' in existing_tables:
        op.drop_table('completed_trade_orders')
    
    if 'completed_trades' in existing_tables:
        op.drop_table('completed_trades')
