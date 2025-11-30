"""API routes for trading reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api.deps import get_strategy_runner, get_binance_client
from app.models.report import StrategyReport, TradeReport, TradingReport
from app.models.order import OrderResponse
from app.services.strategy_runner import StrategyRunner
from app.core.my_binance_client import BinanceClient


router = APIRouter(prefix="/reports", tags=["reports"])


def _match_trades_to_completed_positions(
    trades: List[OrderResponse],
    strategy_id: str,
    strategy_name: str,
    symbol: str,
    leverage: int,
) -> List[TradeReport]:
    """Match trades to form completed positions with detailed information.
    
    Uses actual Binance trade data from orders including:
    - Real timestamps from Binance API
    - Actual commission/fees from Binance API
    - Actual leverage from Binance API (with fallback to strategy leverage)
    - Initial margin, margin type, notional value from Binance API
    """
    completed_trades = []
    # Position queue: (quantity, entry_price, entry_time, entry_order_id, side, exit_reason, 
    #                  entry_fee, entry_leverage, initial_margin, margin_type, notional_value)
    position_queue = []
    order_id_to_timestamp = {}  # Map order_id to timestamp
    order_id_to_order = {order.order_id: order for order in trades}  # Map order_id to full order object
    
    # Helper to get actual timestamp from order
    def get_trade_timestamp(order: OrderResponse) -> datetime:
        """Get actual timestamp from Binance order, with fallback."""
        if order.timestamp:
            return order.timestamp
        if order.update_time:
            return order.update_time
        # Fallback: use current time (shouldn't happen if order was placed recently)
        return datetime.now(timezone.utc)
    
    # Helper to get actual fee from order
    def get_order_fee(order: OrderResponse, notional: float) -> float:
        """Get actual commission from Binance order, with fallback estimate."""
        if order.commission is not None:
            # Convert commission to USDT if needed (assuming commission_asset is tracked)
            # For now, assume commission is already in USDT or main quote currency
            return float(order.commission)
        # Fallback: estimate 0.04% of notional (Binance Futures typical fee)
        return notional * 0.0004
    
    # Helper to get actual leverage from order
    def get_order_leverage(order: OrderResponse) -> int:
        """Get actual leverage from Binance order, with fallback to strategy leverage."""
        if order.leverage is not None and order.leverage > 0:
            return order.leverage
        return leverage  # Fallback to strategy leverage
    
    # Build timestamp map from trades using actual Binance data
    for trade in trades:
        order_id_to_timestamp[trade.order_id] = get_trade_timestamp(trade)
    
    for trade in sorted(trades, key=lambda t: order_id_to_timestamp.get(t.order_id, datetime.min.replace(tzinfo=timezone.utc))):
        entry_price = trade.avg_price or trade.price
        quantity = trade.executed_qty
        side = trade.side
        trade_time = order_id_to_timestamp.get(trade.order_id, datetime.now(timezone.utc))
        
        # Get actual fee from Binance order
        notional = entry_price * quantity
        actual_fee = get_order_fee(trade, notional)
        trade_leverage = get_order_leverage(trade)
        
        if side == "BUY":
            if position_queue and position_queue[0][4] == "SHORT":
                # Closing or reducing SHORT position
                remaining_qty = quantity
                remaining_fee = actual_fee
                
                while remaining_qty > 0 and position_queue and position_queue[0][4] == "SHORT":
                    short_entry = position_queue[0]
                    short_qty = short_entry[0]
                    short_price = short_entry[1]
                    short_entry_time = short_entry[2]
                    short_entry_order_id = short_entry[3]
                    short_exit_reason = short_entry[5] if len(short_entry) > 5 else None
                    short_entry_fee = short_entry[6] if len(short_entry) > 6 else (short_price * short_qty * 0.0004)
                    short_leverage = short_entry[7] if len(short_entry) > 7 else leverage
                    
                    if short_qty <= remaining_qty:
                        close_qty = short_qty
                        close_fee_ratio = 1.0
                        position_queue.pop(0)
                    else:
                        close_qty = remaining_qty
                        close_fee_ratio = remaining_qty / short_qty
                        position_queue[0] = (short_qty - remaining_qty, short_price, short_entry_time, 
                                            short_entry_order_id, "SHORT", short_exit_reason, short_entry_fee, short_leverage)
                    
                    # PnL for SHORT: (entry_price - exit_price) * quantity - fees
                    gross_pnl = (short_price - entry_price) * close_qty
                    # Use actual fees from orders (proportional to quantity)
                    entry_fee_portion = short_entry_fee * close_fee_ratio
                    exit_fee_portion = actual_fee * (close_qty / quantity) if quantity > 0 else 0
                    total_fee = entry_fee_portion + exit_fee_portion
                    net_pnl = gross_pnl - total_fee
                    
                    # Calculate PnL percentage
                    entry_notional = short_price * close_qty
                    pnl_pct = (net_pnl / entry_notional) * 100 if entry_notional > 0 else 0
                    
                    # Determine exit reason if not already set
                    exit_reason = short_exit_reason or "MANUAL"
                    # Could enhance this by checking if TP/SL orders were filled
                    
                    # Get additional Binance parameters from entry and exit orders
                    entry_order = order_id_to_order.get(short_entry_order_id)
                    exit_order = order_id_to_order.get(trade.order_id)
                    
                    # Extract initial margin and margin type from entry order (proportional to close_qty)
                    initial_margin = None
                    margin_type = None
                    notional_value_entry = None
                    if entry_order:
                        if entry_order.initial_margin is not None and short_qty > 0:
                            initial_margin = entry_order.initial_margin * (close_qty / short_qty)
                        margin_type = entry_order.margin_type
                        notional_value_entry = entry_order.notional_value
                        if not notional_value_entry and entry_order.avg_price:
                            notional_value_entry = entry_order.avg_price * close_qty
                    
                    completed_trades.append(TradeReport(
                        trade_id=str(short_entry_order_id),
                        strategy_id=strategy_id,
                        symbol=symbol,
                        side="SHORT",
                        entry_time=short_entry_time,
                        entry_price=short_price,
                        exit_time=trade_time,
                        exit_price=entry_price,
                        quantity=close_qty,
                        leverage=short_leverage,  # Use actual leverage from entry order
                        fee_paid=round(total_fee, 4),
                        pnl_usd=round(net_pnl, 4),
                        pnl_pct=round(pnl_pct, 4),
                        exit_reason=exit_reason,
                        initial_margin=initial_margin,
                        margin_type=margin_type,
                        notional_value=notional_value_entry,
                        entry_order_id=short_entry_order_id,
                        exit_order_id=trade.order_id,
                    ))
                    remaining_qty -= close_qty
                    remaining_fee -= exit_fee_portion
                
                # If remaining quantity after closing SHORT, open LONG
                if remaining_qty > 0:
                    remaining_fee_portion = actual_fee * (remaining_qty / quantity) if quantity > 0 else 0
                    position_queue.append((remaining_qty, entry_price, trade_time, trade.order_id, "LONG", None, remaining_fee_portion, trade_leverage))
            else:
                # Opening or adding to LONG position
                position_queue.append((quantity, entry_price, trade_time, trade.order_id, "LONG", None, actual_fee, trade_leverage))
        
        elif side == "SELL":
            if position_queue and position_queue[0][4] == "LONG":
                # Closing or reducing LONG position
                remaining_qty = quantity
                remaining_fee = actual_fee
                
                while remaining_qty > 0 and position_queue and position_queue[0][4] == "LONG":
                    long_entry = position_queue[0]
                    long_qty = long_entry[0]
                    long_price = long_entry[1]
                    long_entry_time = long_entry[2]
                    long_entry_order_id = long_entry[3]
                    long_exit_reason = long_entry[5] if len(long_entry) > 5 else None
                    long_entry_fee = long_entry[6] if len(long_entry) > 6 else (long_price * long_qty * 0.0004)
                    long_leverage = long_entry[7] if len(long_entry) > 7 else leverage
                    
                    if long_qty <= remaining_qty:
                        close_qty = long_qty
                        close_fee_ratio = 1.0
                        position_queue.pop(0)
                    else:
                        close_qty = remaining_qty
                        close_fee_ratio = remaining_qty / long_qty
                        position_queue[0] = (long_qty - remaining_qty, long_price, long_entry_time,
                                            long_entry_order_id, "LONG", long_exit_reason, long_entry_fee, long_leverage)
                    
                    # PnL for LONG: (exit_price - entry_price) * quantity - fees
                    gross_pnl = (entry_price - long_price) * close_qty
                    # Use actual fees from orders (proportional to quantity)
                    entry_fee_portion = long_entry_fee * close_fee_ratio
                    exit_fee_portion = actual_fee * (close_qty / quantity) if quantity > 0 else 0
                    total_fee = entry_fee_portion + exit_fee_portion
                    net_pnl = gross_pnl - total_fee
                    
                    # Calculate PnL percentage
                    entry_notional = long_price * close_qty
                    pnl_pct = (net_pnl / entry_notional) * 100 if entry_notional > 0 else 0
                    
                    # Determine exit reason if not already set
                    exit_reason = long_exit_reason or "MANUAL"
                    
                    # Get additional Binance parameters from entry and exit orders
                    entry_order = order_id_to_order.get(long_entry_order_id)
                    exit_order = order_id_to_order.get(trade.order_id)
                    
                    # Extract initial margin and margin type from entry order (proportional to close_qty)
                    initial_margin = None
                    margin_type = None
                    notional_value_entry = None
                    if entry_order:
                        if entry_order.initial_margin is not None and long_qty > 0:
                            initial_margin = entry_order.initial_margin * (close_qty / long_qty)
                        margin_type = entry_order.margin_type
                        notional_value_entry = entry_order.notional_value
                        if not notional_value_entry and entry_order.avg_price:
                            notional_value_entry = entry_order.avg_price * close_qty
                    
                    completed_trades.append(TradeReport(
                        trade_id=str(long_entry_order_id),
                        strategy_id=strategy_id,
                        symbol=symbol,
                        side="LONG",
                        entry_time=long_entry_time,
                        entry_price=long_price,
                        exit_time=trade_time,
                        exit_price=entry_price,
                        quantity=close_qty,
                        leverage=long_leverage,  # Use actual leverage from entry order
                        fee_paid=round(total_fee, 4),
                        pnl_usd=round(net_pnl, 4),
                        pnl_pct=round(pnl_pct, 4),
                        exit_reason=exit_reason,
                        initial_margin=initial_margin,
                        margin_type=margin_type,
                        notional_value=notional_value_entry,
                        entry_order_id=long_entry_order_id,
                        exit_order_id=trade.order_id,
                    ))
                    remaining_qty -= close_qty
                    remaining_fee -= exit_fee_portion
                
                # If remaining quantity after closing LONG, open SHORT
                if remaining_qty > 0:
                    remaining_fee_portion = actual_fee * (remaining_qty / quantity) if quantity > 0 else 0
                    position_queue.append((remaining_qty, entry_price, trade_time, trade.order_id, "SHORT", None, remaining_fee_portion, trade_leverage))
            else:
                # Opening or adding to SHORT position
                position_queue.append((quantity, entry_price, trade_time, trade.order_id, "SHORT", None, actual_fee, trade_leverage))
    
    return completed_trades


@router.get("/", response_model=TradingReport)
def get_trading_report(
    strategy_id: Optional[str] = Query(default=None, description="Filter by strategy ID"),
    strategy_name: Optional[str] = Query(default=None, description="Filter by strategy name (partial match)"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    start_date: Optional[str] = Query(default=None, description="Filter from date/time (ISO format)"),
    end_date: Optional[str] = Query(default=None, description="Filter to date/time (ISO format)"),
    runner: StrategyRunner = Depends(get_strategy_runner),
    client: BinanceClient = Depends(get_binance_client),
) -> TradingReport:
    """Generate comprehensive trading report with strategy summaries and trade details.
    
    Returns a two-level report:
    - Strategy-level summaries with aggregated statistics
    - Trade-level details for each completed trade within strategies
    """
    try:
        # Parse datetime filters
        start_datetime: Optional[datetime] = None
        end_datetime: Optional[datetime] = None
        
        if start_date:
            try:
                start_datetime = date_parser.parse(start_date)
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Invalid start_date format: {start_date}, error: {exc}")
                start_datetime = None
        
        if end_date:
            try:
                end_datetime = date_parser.parse(end_date)
                if end_datetime.tzinfo is None:
                    end_datetime = end_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Invalid end_date format: {end_date}, error: {exc}")
                end_datetime = None
        
        # Get all strategies
        all_strategies = runner.list_strategies()
        
        # Apply filters
        filtered_strategies = []
        for strategy in all_strategies:
            if strategy_id and strategy.id != strategy_id:
                continue
            if strategy_name and strategy_name.lower() not in strategy.name.lower():
                continue
            if symbol and strategy.symbol.upper() != symbol.upper():
                continue
            filtered_strategies.append(strategy)
        
        # Build strategy reports
        strategy_reports = []
        total_trades_count = 0  # Total ALL trades (not just completed)
        total_winning = 0
        total_losing = 0
        total_profit = 0.0
        total_loss = 0.0
        
        for strategy in filtered_strategies:
            try:
                # Get trades for this strategy
                trades = runner.get_trades(strategy.id)
                
                # Match trades to form completed positions
                completed_trades_list = _match_trades_to_completed_positions(
                    trades,
                    strategy.id,
                    strategy.name,
                    strategy.symbol,
                    strategy.leverage,
                )
                
                # Apply date filters to trades
                if start_datetime or end_datetime:
                    filtered_trades = []
                    for trade in completed_trades_list:
                        trade_time = trade.entry_time or trade.exit_time
                        if trade_time:
                            if start_datetime and trade_time < start_datetime:
                                continue
                            if end_datetime and trade_time > end_datetime:
                                continue
                        filtered_trades.append(trade)
                    completed_trades_list = filtered_trades
                
                # Calculate strategy statistics
                wins = len([t for t in completed_trades_list if t.pnl_usd > 0])
                losses = len([t for t in completed_trades_list if t.pnl_usd < 0])
                win_rate = (wins / len(completed_trades_list) * 100) if completed_trades_list else 0.0
                
                total_profit_usd = sum(t.pnl_usd for t in completed_trades_list if t.pnl_usd > 0)
                total_loss_usd = abs(sum(t.pnl_usd for t in completed_trades_list if t.pnl_usd < 0))
                net_pnl = sum(t.pnl_usd for t in completed_trades_list)
                
                # Determine stopped_at
                stopped_at = None
                if strategy.status.value != "running":
                    # If stopped, try to get last trade time or use current time
                    if completed_trades_list:
                        stopped_at = max((t.exit_time for t in completed_trades_list if t.exit_time), 
                                       default=strategy.created_at)
                    else:
                        stopped_at = strategy.created_at
                
                strategy_report = StrategyReport(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    symbol=strategy.symbol,
                    created_at=strategy.created_at,
                    stopped_at=stopped_at,
                    total_trades=len(trades),  # All trades (open + closed)
                    wins=wins,
                    losses=losses,
                    win_rate=round(win_rate, 2),
                    total_profit_usd=round(total_profit_usd, 4),
                    total_loss_usd=round(total_loss_usd, 4),
                    net_pnl=round(net_pnl, 4),
                    trades=completed_trades_list,
                )
                
                strategy_reports.append(strategy_report)
                # BUG FIX #1: Count ALL trades (not just completed) for total_trades consistency
                total_trades_count += len(trades)  # Fixed: was len(completed_trades_list)
                total_winning += wins
                total_losing += losses
                total_profit += total_profit_usd
                total_loss += total_loss_usd
                
            except Exception as exc:
                logger.error(f"Error generating report for strategy {strategy.id}: {exc}")
                continue
        
        # Calculate overall statistics
        # BUG FIX #2: Win rate should be based on completed trades (wins+losses), not all trades
        total_completed_trades = total_winning + total_losing
        overall_win_rate = (total_winning / total_completed_trades * 100) if total_completed_trades > 0 else 0.0
        overall_net_pnl = total_profit - total_loss
        
        # Build filters dict
        filters = {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
        }
        filters = {k: v for k, v in filters.items() if v is not None}
        
        return TradingReport(
            strategies=strategy_reports,
            total_strategies=len(strategy_reports),
            total_trades=total_trades_count,
            overall_win_rate=round(overall_win_rate, 2),
            overall_net_pnl=round(overall_net_pnl, 4),
            filters=filters if filters else None,
        )
    
    except Exception as exc:
        logger.exception(f"Error generating trading report: {exc}")
        raise

