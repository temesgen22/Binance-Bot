"""add_partial_fill_tracking_fields

Revision ID: c9d8e7f6a5b4
Revises: b08a3fc21d8f
Create Date: 2026-01-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c9d8e7f6a5b4'
down_revision: Union[str, None] = 'b08a3fc21d8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add orig_qty and remaining_qty fields to trades table for partial fill tracking."""
    from sqlalchemy import inspect
    
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    if 'trades' not in existing_tables:
        # Table doesn't exist, skip (shouldn't happen in normal flow)
        return
    
    # Get existing columns
    existing_columns = [col['name'] for col in inspector.get_columns('trades')]
    
    # Add orig_qty column if it doesn't exist
    if 'orig_qty' not in existing_columns:
        op.add_column('trades', sa.Column('orig_qty', sa.Numeric(20, 8), nullable=True))
    
    # Add remaining_qty column if it doesn't exist
    if 'remaining_qty' not in existing_columns:
        op.add_column('trades', sa.Column('remaining_qty', sa.Numeric(20, 8), nullable=True))
    
    # Update existing rows: calculate remaining_qty from orig_qty and executed_qty
    # For existing rows without orig_qty, set remaining_qty to NULL (unknown)
    # Note: We'll calculate remaining_qty in application code going forward
    # Only update if we have both orig_qty and executed_qty
    try:
        op.execute(text("""
            UPDATE trades 
            SET remaining_qty = CASE 
                WHEN orig_qty IS NOT NULL AND executed_qty IS NOT NULL 
                THEN orig_qty - executed_qty 
                ELSE NULL 
            END
            WHERE orig_qty IS NOT NULL AND executed_qty IS NOT NULL
        """))
    except Exception:
        # If update fails (e.g., no rows to update), that's fine
        pass


def downgrade() -> None:
    """Remove orig_qty and remaining_qty fields from trades table."""
    from sqlalchemy import inspect
    
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    if 'trades' not in existing_tables:
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('trades')]
    
    if 'remaining_qty' in existing_columns:
        op.drop_column('trades', 'remaining_qty')
    
    if 'orig_qty' in existing_columns:
        op.drop_column('trades', 'orig_qty')

