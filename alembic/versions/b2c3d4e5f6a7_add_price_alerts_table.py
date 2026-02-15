"""add_price_alerts_table

Revision ID: b2c3d4e5f6a7
Revises: a2b3c4d5e6f7
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add price_alerts table for Binance-style price alert push notifications."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    def get_table_indexes(table_name):
        if table_name not in existing_tables:
            return []
        try:
            return [idx["name"] for idx in inspector.get_indexes(table_name)]
        except Exception:
            return []

    if "price_alerts" not in existing_tables:
        op.create_table(
            "price_alerts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("symbol", sa.String(20), nullable=False),
            sa.Column("alert_type", sa.String(32), nullable=False),
            sa.Column("target_price", sa.Numeric(20, 8), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("last_price", sa.Numeric(20, 8), nullable=True),
            sa.Column("trigger_once", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )

        indexes = get_table_indexes("price_alerts")
        if "ix_price_alerts_user_id" not in indexes:
            op.create_index("ix_price_alerts_user_id", "price_alerts", ["user_id"])
        if "ix_price_alerts_symbol" not in indexes:
            op.create_index("ix_price_alerts_symbol", "price_alerts", ["symbol"])
        if "idx_price_alerts_enabled" not in indexes:
            op.create_index("idx_price_alerts_enabled", "price_alerts", ["enabled"])
        if "idx_price_alerts_enabled_symbol" not in indexes:
            op.create_index("idx_price_alerts_enabled_symbol", "price_alerts", ["enabled", "symbol"])


def downgrade() -> None:
    """Drop price_alerts table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    if "price_alerts" in existing_tables:
        op.drop_index("idx_price_alerts_enabled_symbol", table_name="price_alerts")
        op.drop_index("idx_price_alerts_enabled", table_name="price_alerts")
        op.drop_index("ix_price_alerts_symbol", table_name="price_alerts")
        op.drop_index("ix_price_alerts_user_id", table_name="price_alerts")
        op.drop_table("price_alerts")
