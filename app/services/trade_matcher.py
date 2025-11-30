"""Shared utility for matching trades to completed positions.

This module provides a unified trade matching function used across multiple endpoints
to ensure consistent PnL calculations, fee handling, and trade pairing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple, Any

from app.models.order import OrderResponse
from loguru import logger


class CompletedTradeMatch:
    """Represents a matched completed trade with all details."""
    
    def __init__(
        self,
        entry_price: float,
        exit_price: float,
        quantity: float,
        side: str,
        entry_time: Optional[datetime] = None,
        exit_time: Optional[datetime] = None,
        entry_order_id: Optional[int] = None,
        exit_order_id: Optional[int] = None,
        gross_pnl: float = 0.0,
        fee_paid: float = 0.0,
        net_pnl: float = 0.0,
        exit_reason: Optional[str] = None,
    ):
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.quantity = quantity
        self.side = side
        self.entry_time = entry_time
        self.exit_time = exit_time
        self.entry_order_id = entry_order_id
        self.exit_order_id = exit_order_id
        self.gross_pnl = gross_pnl
        self.fee_paid = fee_paid
        self.net_pnl = net_pnl
        self.exit_reason = exit_reason


def match_trades_to_completed_positions(
    trades: List[OrderResponse],
    include_fees: bool = True,
    include_timestamps: bool = True,
    fee_rate: float = 0.0004,  # 0.04% default Binance Futures fee
) -> List[CompletedTradeMatch]:
    """Match trades to form completed positions using FIFO matching.
    
    Args:
        trades: List of OrderResponse objects in chronological order
        include_fees: Whether to calculate and include fees in PnL
        include_timestamps: Whether to extract and include timestamps
        fee_rate: Fee rate per trade (default 0.04% for Binance Futures)
    
    Returns:
        List of CompletedTradeMatch objects representing completed trades
    """
    if not trades:
        return []
    
    # Sort trades by order_id (Binance order IDs are sequential)
    # Higher order_id = more recent
    sorted_trades = sorted(trades, key=lambda t: t.order_id)
    
    completed_trades = []
    position_queue: List[Tuple[float, float, Optional[datetime], Optional[int], str, Optional[str]]] = []
    # Queue format: (quantity, entry_price, entry_time, entry_order_id, side, exit_reason)
    
    # Build timestamp map if needed
    order_id_to_timestamp: Dict[int, datetime] = {}
    if include_timestamps:
        for trade in sorted_trades:
            timestamp = datetime.now(timezone.utc)  # Fallback
            if hasattr(trade, 'timestamp') and trade.timestamp:
                timestamp = trade.timestamp
            elif hasattr(trade, 'time') and trade.time:
                timestamp = datetime.fromtimestamp(trade.time / 1000, tz=timezone.utc)
            order_id_to_timestamp[trade.order_id] = timestamp
    
    for trade in sorted_trades:
        entry_price = trade.avg_price or trade.price
        quantity = trade.executed_qty
        side = trade.side
        trade_time = order_id_to_timestamp.get(trade.order_id, datetime.now(timezone.utc)) if include_timestamps else None
        
        if side == "BUY":
            if position_queue and position_queue[0][4] == "SHORT":
                # Closing or reducing SHORT position
                remaining_qty = quantity
                
                while remaining_qty > 0 and position_queue and position_queue[0][4] == "SHORT":
                    short_entry = position_queue[0]
                    short_qty = short_entry[0]
                    short_price = short_entry[1]
                    short_entry_time = short_entry[2]
                    short_entry_order_id = short_entry[3]
                    short_exit_reason = short_entry[5]
                    
                    if short_qty <= remaining_qty:
                        close_qty = short_qty
                        close_fee_ratio = 1.0
                        position_queue.pop(0)
                    else:
                        close_qty = remaining_qty
                        close_fee_ratio = remaining_qty / short_qty
                        position_queue[0] = (short_qty - remaining_qty, short_price, short_entry_time,
                                            short_entry_order_id, "SHORT", short_exit_reason)
                    
                    # PnL for SHORT: (entry_price - exit_price) * quantity
                    gross_pnl = (short_price - entry_price) * close_qty
                    
                    # Calculate fees if requested
                    fee_paid = 0.0
                    if include_fees:
                        entry_fee = short_price * close_qty * fee_rate * close_fee_ratio
                        exit_fee = entry_price * close_qty * fee_rate * close_fee_ratio
                        fee_paid = entry_fee + exit_fee
                    
                    net_pnl = gross_pnl - fee_paid
                    
                    completed_trades.append(CompletedTradeMatch(
                        entry_price=short_price,
                        exit_price=entry_price,
                        quantity=close_qty,
                        side="SHORT",
                        entry_time=short_entry_time if include_timestamps else None,
                        exit_time=trade_time if include_timestamps else None,
                        entry_order_id=short_entry_order_id,
                        exit_order_id=trade.order_id,
                        gross_pnl=gross_pnl,
                        fee_paid=fee_paid,
                        net_pnl=net_pnl,
                        exit_reason=short_exit_reason or "MANUAL",
                    ))
                    remaining_qty -= close_qty
                
                # If remaining quantity after closing SHORT, open LONG
                if remaining_qty > 0:
                    position_queue.append((remaining_qty, entry_price, trade_time, trade.order_id, "LONG", None))
            else:
                # Opening or adding to LONG position
                position_queue.append((quantity, entry_price, trade_time, trade.order_id, "LONG", None))
        
        elif side == "SELL":
            if position_queue and position_queue[0][4] == "LONG":
                # Closing or reducing LONG position
                remaining_qty = quantity
                
                while remaining_qty > 0 and position_queue and position_queue[0][4] == "LONG":
                    long_entry = position_queue[0]
                    long_qty = long_entry[0]
                    long_price = long_entry[1]
                    long_entry_time = long_entry[2]
                    long_entry_order_id = long_entry[3]
                    long_exit_reason = long_entry[5]
                    
                    if long_qty <= remaining_qty:
                        close_qty = long_qty
                        close_fee_ratio = 1.0
                        position_queue.pop(0)
                    else:
                        close_qty = remaining_qty
                        close_fee_ratio = remaining_qty / long_qty
                        position_queue[0] = (long_qty - remaining_qty, long_price, long_entry_time,
                                            long_entry_order_id, "LONG", long_exit_reason)
                    
                    # PnL for LONG: (exit_price - entry_price) * quantity
                    gross_pnl = (entry_price - long_price) * close_qty
                    
                    # Calculate fees if requested
                    fee_paid = 0.0
                    if include_fees:
                        entry_fee = long_price * close_qty * fee_rate * close_fee_ratio
                        exit_fee = entry_price * close_qty * fee_rate * close_fee_ratio
                        fee_paid = entry_fee + exit_fee
                    
                    net_pnl = gross_pnl - fee_paid
                    
                    completed_trades.append(CompletedTradeMatch(
                        entry_price=long_price,
                        exit_price=entry_price,
                        quantity=close_qty,
                        side="LONG",
                        entry_time=long_entry_time if include_timestamps else None,
                        exit_time=trade_time if include_timestamps else None,
                        entry_order_id=long_entry_order_id,
                        exit_order_id=trade.order_id,
                        gross_pnl=gross_pnl,
                        fee_paid=fee_paid,
                        net_pnl=net_pnl,
                        exit_reason=long_exit_reason or "MANUAL",
                    ))
                    remaining_qty -= close_qty
                
                # If remaining quantity after closing LONG, open SHORT
                if remaining_qty > 0:
                    position_queue.append((remaining_qty, entry_price, trade_time, trade.order_id, "SHORT", None))
            else:
                # Opening or adding to SHORT position
                position_queue.append((quantity, entry_price, trade_time, trade.order_id, "SHORT", None))
    
    return completed_trades

