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
    pass


def downgrade() -> None:
    pass

