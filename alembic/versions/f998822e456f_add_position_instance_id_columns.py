"""add_position_instance_id_columns

Revision ID: f998822e456f
Revises: f1a2b3c4d5e6
Create Date: 2026-01-26 12:24:35.753515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f998822e456f'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add position_instance_id columns to strategies, trades, and completed_trades tables.
    
    This migration adds position_instance_id to track position cycles and prevent
    old unmatched entry quantities from being incorrectly matched with new position exits.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    # Helper function to check if column exists
    def column_exists(table_name: str, column_name: str) -> bool:
        if table_name not in existing_tables:
            return False
        existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in existing_columns
    
    # Helper function to check if index exists
    def index_exists(table_name: str, index_name: str) -> bool:
        if table_name not in existing_tables:
            return False
        indexes = inspector.get_indexes(table_name)
        return any(idx['name'] == index_name for idx in indexes)
    
    # 1. Add position_instance_id to strategies table
    if 'strategies' in existing_tables:
        if not column_exists('strategies', 'position_instance_id'):
            op.add_column(
                'strategies',
                sa.Column('position_instance_id', postgresql.UUID(as_uuid=True), nullable=True)
            )
        
        # Create index for strategies
        if not index_exists('strategies', 'idx_strategies_pos_instance'):
            op.create_index(
                'idx_strategies_pos_instance',
                'strategies',
                ['position_instance_id']
            )
    
    # 2. Add position_instance_id to trades table
    if 'trades' in existing_tables:
        if not column_exists('trades', 'position_instance_id'):
            op.add_column(
                'trades',
                sa.Column('position_instance_id', postgresql.UUID(as_uuid=True), nullable=True)
            )
        
        # Create main index for trades (with position_side)
        if not index_exists('trades', 'idx_trades_pos_instance'):
            op.create_index(
                'idx_trades_pos_instance',
                'trades',
                ['strategy_id', 'symbol', 'position_side', 'position_instance_id', 'timestamp']
            )
        
        # Create separate index for NULL position_side (better performance for old trades)
        if not index_exists('trades', 'idx_trades_pos_instance_null'):
            # Use raw SQL for partial index (WHERE clause)
            op.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_trades_pos_instance_null 
                ON trades(strategy_id, symbol, position_instance_id, timestamp)
                WHERE position_side IS NULL
            """))
    
    # 3. Add position_instance_id to completed_trades table
    if 'completed_trades' in existing_tables:
        if not column_exists('completed_trades', 'position_instance_id'):
            op.add_column(
                'completed_trades',
                sa.Column('position_instance_id', postgresql.UUID(as_uuid=True), nullable=True)
            )
        
        # Create index for completed_trades
        if not index_exists('completed_trades', 'idx_completed_trades_pos_instance'):
            op.create_index(
                'idx_completed_trades_pos_instance',
                'completed_trades',
                ['strategy_id', 'symbol', 'position_instance_id', 'exit_time']
            )


def downgrade() -> None:
    """Remove position_instance_id columns and indexes."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    # Helper function to check if index exists
    def index_exists(table_name: str, index_name: str) -> bool:
        if table_name not in existing_tables:
            return False
        indexes = inspector.get_indexes(table_name)
        return any(idx['name'] == index_name for idx in indexes)
    
    # Drop indexes first, then columns
    
    # 1. Drop indexes and column from completed_trades
    if 'completed_trades' in existing_tables:
        if index_exists('completed_trades', 'idx_completed_trades_pos_instance'):
            op.drop_index('idx_completed_trades_pos_instance', table_name='completed_trades')
        try:
            op.drop_column('completed_trades', 'position_instance_id')
        except Exception:
            pass  # Column might not exist
    
    # 2. Drop indexes and column from trades
    if 'trades' in existing_tables:
        if index_exists('trades', 'idx_trades_pos_instance_null'):
            op.execute(text("DROP INDEX IF EXISTS idx_trades_pos_instance_null"))
        if index_exists('trades', 'idx_trades_pos_instance'):
            op.drop_index('idx_trades_pos_instance', table_name='trades')
        try:
            op.drop_column('trades', 'position_instance_id')
        except Exception:
            pass  # Column might not exist
    
    # 3. Drop indexes and column from strategies
    if 'strategies' in existing_tables:
        if index_exists('strategies', 'idx_strategies_pos_instance'):
            op.drop_index('idx_strategies_pos_instance', table_name='strategies')
        try:
            op.drop_column('strategies', 'position_instance_id')
        except Exception:
            pass  # Column might not exist

