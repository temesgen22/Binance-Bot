"""add_fixed_amount_to_walk_forward_analyses

Revision ID: ed0664149df0
Revises: 209a456fd280
Create Date: 2025-12-30 21:03:53.765906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ed0664149df0'
down_revision: Union[str, None] = '209a456fd280'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add fixed_amount column to walk_forward_analyses table
    op.add_column('walk_forward_analyses',
        sa.Column('fixed_amount', sa.Numeric(precision=20, scale=8), nullable=True)
    )


def downgrade() -> None:
    # Remove fixed_amount column from walk_forward_analyses table
    op.drop_column('walk_forward_analyses', 'fixed_amount')

