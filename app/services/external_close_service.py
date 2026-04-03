"""
External close ingestion: when a position is closed outside the bot (e.g. manually on Binance),
detect the closing order(s), save as Trade with exit_reason=EXTERNAL_CLOSE, and create CompletedTrade(s).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Optional, List, Any, Tuple
from uuid import UUID

from loguru import logger

from app.models.db_models import Trade
from app.models.order import OrderResponse


# Quantity tolerance for matching closing order to position size (float comparison)
QTY_TOLERANCE = 1e-6


def _qty_match(position_size: float, total_qty: float) -> bool:
    """True if summed fill qty matches last known position size."""
    if position_size <= 0:
        return False
    if abs(total_qty - position_size) <= QTY_TOLERANCE:
        return True
    # Relative tolerance for small/high-precision contracts (exact float noise)
    rel = max(QTY_TOLERANCE, position_size * 1e-9)
    return abs(total_qty - position_size) <= rel


def find_closing_order_ids(
    client: Any,
    symbol: str,
    position_side: str,
    position_size: float,
) -> List[int]:
    """
    Find Binance order IDs that closed this position (by side and quantity).
    LONG close = SELL orders; SHORT close = BUY. Returns most recent matching order.

    IMPORTANT: futures_account_trades returns one row per *fill*. A single TP/SL order
    may split into multiple rows with the same orderId. We sum qty per orderId before
    comparing to position_size; matching only per-row used to miss native TP/SL closes.
    """
    if position_side.upper() not in ("LONG", "SHORT"):
        return []
    close_side = "SELL" if position_side.upper() == "LONG" else "BUY"
    try:
        trades = client.get_account_trades(symbol=symbol, limit=500)
    except Exception as e:
        logger.debug(f"get_account_trades failed for {symbol}: {e}")
        return []
    if not trades:
        return []
    # order_id -> list of (qty, time_ms)
    per_order: dict[int, List[Tuple[float, int]]] = defaultdict(list)
    for t in trades:
        if str(t.get("side", "")).upper() != close_side:
            continue
        qty = t.get("executedQty") or t.get("qty")
        if qty is None:
            continue
        try:
            q = float(qty)
        except (TypeError, ValueError):
            continue
        raw_oid = t.get("orderId")
        if raw_oid is None:
            continue
        try:
            oid = int(raw_oid)
        except (TypeError, ValueError):
            continue
        ts_raw = t.get("time")
        try:
            ts = int(ts_raw) if ts_raw is not None else 0
        except (TypeError, ValueError):
            ts = 0
        per_order[oid].append((q, ts))

    candidates: List[Tuple[int, int]] = []
    for oid, rows in per_order.items():
        total_qty = sum(r[0] for r in rows)
        if not _qty_match(position_size, total_qty):
            continue
        max_ts = max(r[1] for r in rows)
        candidates.append((oid, max_ts))

    if not candidates:
        return []
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [candidates[0][0]]


def build_order_response_for_external_close(
    client: Any,
    symbol: str,
    order_id: int,
    position_side: str,
) -> Optional[OrderResponse]:
    """Fetch order from Binance and return OrderResponse with exit_reason=EXTERNAL_CLOSE."""
    try:
        raw = client.get_order_status(symbol=symbol, order_id=order_id)
    except Exception as e:
        logger.debug(f"get_order_status failed for {order_id}: {e}")
        return None
    if not raw:
        return None
    if hasattr(client, "_parse_order_response"):
        order = client._parse_order_response(raw)
    else:
        # Minimal construction if no parser
        order = OrderResponse(
            symbol=raw.get("symbol", symbol),
            order_id=int(raw.get("orderId", order_id)),
            status=str(raw.get("status", "FILLED")),
            side=str(raw.get("side", "SELL")),
            price=float(raw.get("price") or 0),
            avg_price=float(raw.get("avgPrice") or raw.get("price") or 0),
            executed_qty=float(raw.get("executedQty") or raw.get("qty") or 0),
            exit_reason=None,
        )
    if hasattr(order, "model_copy"):
        return order.model_copy(update={"exit_reason": "EXTERNAL_CLOSE"})
    # Pydantic v1
    return order.copy(update={"exit_reason": "EXTERNAL_CLOSE"})


def _has_exit_trade_for_position(
    strategy_uuid: UUID,
    position_instance_id: UUID,
    exit_side: str,
) -> bool:
    """
    Idempotency guard: return True if a Trade already exists for this position with the given exit side (SELL/BUY).
    Uses sync session from get_session_factory; closes session when done.
    """
    from app.core.database import get_session_factory

    factory = get_session_factory()
    session = factory()
    try:
        existing = (
            session.query(Trade)
            .filter(
                Trade.strategy_id == strategy_uuid,
                Trade.position_instance_id == position_instance_id,
                Trade.side == exit_side,
                Trade.exit_reason.isnot(None),
            )
            .first()
        )
        return existing is not None
    finally:
        session.close()


async def handle_external_position_close(
    user_id: UUID,
    strategy_id_str: str,
    strategy_uuid: UUID,
    symbol: str,
    account_id: str,
    position_side: str,
    position_size: float,
    position_instance_id: Optional[UUID],
    entry_timestamp: Optional[Any],
    account_client: Any,
    trade_service: Any,
    paper_trading: bool,
    order_manager: Optional[Any] = None,
    entry_quantity: Optional[float] = None,
) -> None:
    """
    When a position was closed externally (e.g. on Binance app), find the closing order(s),
    save as Trade with exit_reason=EXTERNAL_CLOSE, and create CompletedTrade(s).
    Skips when position_instance_id is None, paper_trading is True, or position_side is invalid.
    """
    if position_instance_id is None:
        return
    if paper_trading:
        return
    if position_side.upper() not in ("LONG", "SHORT"):
        return

    exit_side = "SELL" if position_side.upper() == "LONG" else "BUY"

    # Idempotency: if we already have an exit trade for this position, skip
    if _has_exit_trade_for_position(strategy_uuid, position_instance_id, exit_side):
        return

    # Brief wait so strategy path can save first (TP/SL) and we avoid duplicate
    await asyncio.sleep(0.5)

    # Re-check after wait (strategy path may have saved)
    if _has_exit_trade_for_position(strategy_uuid, position_instance_id, exit_side):
        return

    order_ids = find_closing_order_ids(account_client, symbol, position_side, position_size)
    if not order_ids:
        logger.debug(f"No closing orders found for {symbol} {position_side} size={position_size}")
        return

    for order_id in order_ids:
        # Skip if strategy path already saved this order (e.g. TP/SL)
        existing = trade_service.get_trade_by_order_id(strategy_uuid, order_id)
        if existing is not None:
            exit_reason = getattr(existing, "exit_reason", None)
            if isinstance(exit_reason, str) and exit_reason.strip() and exit_reason not in ("EXTERNAL_CLOSE", "UNKNOWN"):
                continue

        order_response = build_order_response_for_external_close(
            account_client, symbol, order_id, position_side
        )
        if order_response is None:
            continue

        db_trade = trade_service.save_trade(
            user_id=user_id,
            strategy_id=strategy_uuid,
            order=order_response,
            position_instance_id=position_instance_id,
            commit=True,
        )

        # If save_trade returned an existing trade with strategy exit_reason (TP/SL), skip create_completed_trades
        if getattr(db_trade, "exit_reason", None) and db_trade.exit_reason not in ("EXTERNAL_CLOSE", "UNKNOWN", None):
            continue

        from app.services.completed_trade_helper import create_completed_trades_on_position_close

        create_completed_trades_on_position_close(
            user_id=user_id,
            strategy_id=strategy_id_str,
            exit_trade_id=db_trade.id,
            exit_order_id=int(order_response.order_id),
            exit_quantity=float(order_response.executed_qty),
            exit_price=float(order_response.avg_price or order_response.price or 0),
            position_side=position_side,
            exit_reason="EXTERNAL_CLOSE",
            db=None,
        )
        # Only create for first matching order (one exit per position)
        break
