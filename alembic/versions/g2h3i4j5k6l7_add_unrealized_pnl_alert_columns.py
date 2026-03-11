"""add_unrealized_pnl_alert_columns

Revision ID: g2h3i4j5k6l7
Revises: b2c3d4e5f6a7
Create Date: 2026-02-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g2h3i4j5k6l7'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unrealized PnL alert threshold columns to strategy_risk_config
    op.add_column(
        'strategy_risk_config',
        sa.Column('unrealized_profit_alert_usdt', sa.Numeric(precision=20, scale=8), nullable=True)
    )
    op.add_column(
        'strategy_risk_config',
        sa.Column('unrealized_loss_alert_usdt', sa.Numeric(precision=20, scale=8), nullable=True)
    )
    op.add_column(
        'strategy_risk_config',
        sa.Column('unrealized_pnl_alert_cooldown_minutes', sa.Integer(), nullable=False, server_default='30')
    )


def downgrade() -> None:
    op.drop_column('strategy_risk_config', 'unrealized_pnl_alert_cooldown_minutes')
    op.drop_column('strategy_risk_config', 'unrealized_loss_alert_usdt')
    op.drop_column('strategy_risk_config', 'unrealized_profit_alert_usdt')
