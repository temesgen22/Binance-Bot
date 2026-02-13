"""Service to record trailing-stop level updates in the database."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from loguru import logger
from sqlalchemy import func

from app.models.db_models import Strategy, Trade, TrailingStopUpdate

if TYPE_CHECKING:
    from app.services.database_service import DatabaseService


class TrailingStopUpdateService:
    """Records each trailing-stop TP/SL level update for a position (for tracing/analytics)."""

    def __init__(self, db_service: "DatabaseService", user_id: UUID) -> None:
        self.db_service = db_service
        self.user_id = user_id

    def record_trail_update(
        self,
        strategy_id: str,
        symbol: str,
        position_side: str,
        best_price: float,
        tp_price: float,
        sl_price: float,
    ) -> None:
        """
        Insert one row into trailing_stop_updates for this level update.
        Uses strategy_id (string) to look up strategy; stores strategy.id (UUID) and position_instance_id.
        Skips insert if position_instance_id is None. Assigns update_sequence in a concurrency-safe way.
        """
        db = self.db_service.db
        strategy = db.query(Strategy).filter(
            Strategy.user_id == self.user_id,
            Strategy.strategy_id == strategy_id,
        ).with_for_update().first()

        if not strategy:
            logger.debug(
                f"TrailingStopUpdateService: strategy not found for strategy_id={strategy_id}, skipping record"
            )
            return

        position_instance_id = strategy.position_instance_id
        if position_instance_id is None:
            logger.debug(
                f"TrailingStopUpdateService: position_instance_id is None for strategy_id={strategy_id}, skipping record"
            )
            return

        next_seq = db.query(func.coalesce(func.max(TrailingStopUpdate.update_sequence), 0)).filter(
            TrailingStopUpdate.position_instance_id == position_instance_id
        ).scalar()
        next_seq = (next_seq or 0) + 1

        entry_order_id = None
        entry_side = "BUY" if position_side == "LONG" else "SELL"
        entry_trade = (
            db.query(Trade)
            .filter(
                Trade.strategy_id == strategy.id,
                Trade.position_instance_id == position_instance_id,
                Trade.side == entry_side,
                Trade.status.in_(["FILLED", "PARTIALLY_FILLED"]),
            )
            .order_by(Trade.created_at.asc())
            .first()
        )
        if entry_trade:
            entry_order_id = entry_trade.order_id

        row = TrailingStopUpdate(
            strategy_id=strategy.id,
            position_instance_id=position_instance_id,
            entry_order_id=entry_order_id,
            symbol=symbol,
            position_side=position_side,
            update_sequence=next_seq,
            best_price=best_price,
            tp_price=tp_price,
            sl_price=sl_price,
        )
        db.add(row)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"TrailingStopUpdateService: failed to insert trail update: {e}")
