"""add_trailing_stop_updates_table

Revision ID: a2b3c4d5e6f7
Revises: fcm_001
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'fcm_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trailing_stop_updates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('position_instance_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entry_order_id', sa.BigInteger(), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('position_side', sa.String(10), nullable=False),
        sa.Column('update_sequence', sa.Integer(), nullable=False),
        sa.Column('best_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('tp_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('sl_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('position_instance_id', 'update_sequence', name='uq_trailing_stop_updates_pos_seq'),
    )
    op.create_index('idx_trailing_stop_updates_strategy', 'trailing_stop_updates', ['strategy_id', 'created_at'])
    op.create_index('idx_trailing_stop_updates_position_instance_id', 'trailing_stop_updates', ['position_instance_id'])
    op.create_index('idx_trailing_stop_updates_created_at', 'trailing_stop_updates', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_trailing_stop_updates_created_at', table_name='trailing_stop_updates')
    op.drop_index('idx_trailing_stop_updates_position_instance_id', table_name='trailing_stop_updates')
    op.drop_index('idx_trailing_stop_updates_strategy', table_name='trailing_stop_updates')
    op.drop_table('trailing_stop_updates')
