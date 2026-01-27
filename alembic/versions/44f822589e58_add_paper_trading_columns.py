"""add_paper_trading_columns

Revision ID: 44f822589e58
Revises: 6d66c529e2e7
Create Date: 2026-01-27 00:49:44.095371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '44f822589e58'
down_revision: Union[str, None] = '6d66c529e2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add paper_trading columns to accounts, trades, and completed_trades tables.
    
    This migration adds:
    - paper_trading (Boolean) and paper_balance (Numeric) to accounts table
    - paper_trading (Boolean) to trades table
    - paper_trading (Boolean) to completed_trades table
    
    All columns default to False/NULL for backward compatibility.
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
    
    # 1. Add paper_trading and paper_balance to accounts table
    if 'accounts' in existing_tables:
        if not column_exists('accounts', 'paper_trading'):
            op.add_column(
                'accounts',
                sa.Column('paper_trading', sa.Boolean(), nullable=False, server_default='false')
            )
            # Create index for paper_trading
            op.create_index('ix_accounts_paper_trading', 'accounts', ['paper_trading'])
        
        if not column_exists('accounts', 'paper_balance'):
            op.add_column(
                'accounts',
                sa.Column('paper_balance', sa.Numeric(20, 8), nullable=True)
            )
    
    # 2. Add paper_trading to trades table
    if 'trades' in existing_tables:
        if not column_exists('trades', 'paper_trading'):
            op.add_column(
                'trades',
                sa.Column('paper_trading', sa.Boolean(), nullable=False, server_default='false')
            )
            # Create partial index for filtering (only index false values for performance)
            if not index_exists('trades', 'idx_trades_paper_trading'):
                op.execute(text("""
                    CREATE INDEX idx_trades_paper_trading 
                    ON trades(paper_trading)
                    WHERE paper_trading = false
                """))
    
    # 3. Add paper_trading to completed_trades table
    if 'completed_trades' in existing_tables:
        if not column_exists('completed_trades', 'paper_trading'):
            op.add_column(
                'completed_trades',
                sa.Column('paper_trading', sa.Boolean(), nullable=False, server_default='false')
            )
            # Create partial index for filtering (only index false values for performance)
            if not index_exists('completed_trades', 'idx_completed_trades_paper_trading'):
                op.execute(text("""
                    CREATE INDEX idx_completed_trades_paper_trading 
                    ON completed_trades(paper_trading)
                    WHERE paper_trading = false
                """))


def downgrade() -> None:
    """Remove paper_trading columns and indexes."""
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
    
    # 1. Drop indexes and columns from completed_trades
    if 'completed_trades' in existing_tables:
        if index_exists('completed_trades', 'idx_completed_trades_paper_trading'):
            op.execute(text("DROP INDEX IF EXISTS idx_completed_trades_paper_trading"))
        try:
            op.drop_column('completed_trades', 'paper_trading')
        except Exception:
            pass  # Column might not exist
    
    # 2. Drop indexes and columns from trades
    if 'trades' in existing_tables:
        if index_exists('trades', 'idx_trades_paper_trading'):
            op.execute(text("DROP INDEX IF EXISTS idx_trades_paper_trading"))
        try:
            op.drop_column('trades', 'paper_trading')
        except Exception:
            pass  # Column might not exist
    
    # 3. Drop indexes and columns from accounts
    if 'accounts' in existing_tables:
        if index_exists('accounts', 'ix_accounts_paper_trading'):
            op.drop_index('ix_accounts_paper_trading', table_name='accounts')
        try:
            op.drop_column('accounts', 'paper_balance')
        except Exception:
            pass  # Column might not exist
        try:
            op.drop_column('accounts', 'paper_trading')
        except Exception:
            pass  # Column might not exist
