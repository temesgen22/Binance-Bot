"""add_exchange_platform_to_accounts

Revision ID: 9087ba9df11b
Revises: af03ee2f45dc
Create Date: 2025-12-16 01:05:02.650568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9087ba9df11b'
down_revision: Union[str, None] = 'af03ee2f45dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add exchange_platform column to accounts table
    op.add_column('accounts', sa.Column('exchange_platform', sa.String(length=50), nullable=False, server_default='binance'))
    # Create index for faster queries
    op.create_index(op.f('ix_accounts_exchange_platform'), 'accounts', ['exchange_platform'], unique=False)


def downgrade() -> None:
    # Remove index
    op.drop_index(op.f('ix_accounts_exchange_platform'), table_name='accounts')
    # Remove column
    op.drop_column('accounts', 'exchange_platform')

