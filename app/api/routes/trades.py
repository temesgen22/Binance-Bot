"""API routes for trade and position tracking."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api.deps import get_strategy_runner, get_binance_client
from app.models.trade import (
    TradeWithTimestamp,
    PositionSummary,
    TradeSummary,
    SymbolPnL,
    TradeFilterParams,
)
from app.models.order import OrderResponse
from app.services.strategy_runner import StrategyRunner
from app.core.my_binance_client import BinanceClient
from app.core.exceptions import StrategyNotFoundError


router = APIRouter(prefix="/trades", tags=["trades"])


def _convert_order_to_trade_with_timestamp(
    order: OrderResponse,
    strategy_id: Optional[str] = None,
    strategy_name: Optional[str] = None,
) -> TradeWithTimestamp:
    """Convert OrderResponse to TradeWithTimestamp."""
    return TradeWithTimestamp(
        symbol=order.symbol,
        order_id=order.order_id,
        status=order.status,
        side=order.side,
        price=order.price,
        avg_price=order.avg_price,
        executed_qty=order.executed_qty,
        timestamp=datetime.utcnow(),  # We'll need to track this better in the future
        strategy_id=strategy_id,
        strategy_name=strategy_name,
    )


@router.get("/", response_model=List[TradeWithTimestamp])
def list_all_trades(
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    start_date: Optional[datetime] = Query(default=None, description="Filter from date"),
    end_date: Optional[datetime] = Query(default=None, description="Filter until date"),
    side: Optional[str] = Query(default=None, description="Filter by side (BUY/SELL)"),
    strategy_id: Optional[str] = Query(default=None, description="Filter by strategy ID"),
    runner: StrategyRunner = Depends(get_strategy_runner),
) -> List[TradeWithTimestamp]:
    """Get all trades across all strategies with optional filtering."""
    all_trades = []
    
    # Get all strategies
    strategies = runner.list_strategies()
    strategy_map = {s.id: s for s in strategies}
    
    # Collect trades from all strategies
    for strategy in strategies:
        # Apply strategy_id filter
        if strategy_id and strategy.id != strategy_id:
            continue
        
        # Apply symbol filter
        if symbol and strategy.symbol.upper() != symbol.upper():
            continue
        
        # Get trades for this strategy
        strategy_trades = runner.get_trades(strategy.id)
        for trade in strategy_trades:
            trade_with_ts = _convert_order_to_trade_with_timestamp(
                trade,
                strategy_id=strategy.id,
                strategy_name=strategy.name,
            )
            
            # Apply side filter
            if side and trade_with_ts.side.upper() != side.upper():
                continue
            
            # Apply date filters (if we had timestamps)
            # For now, we'll include all trades
            
            all_trades.append(trade_with_ts)
    
    logger.info(f"Retrieved {len(all_trades)} trades with filters: symbol={symbol}, side={side}, strategy_id={strategy_id}")
    return all_trades


@router.get("/symbols", response_model=List[str])
def list_symbols(runner: StrategyRunner = Depends(get_strategy_runner)) -> List[str]:
    """Get list of all symbols that have trades."""
    symbols = set()
    
    strategies = runner.list_strategies()
    for strategy in strategies:
        trades = runner.get_trades(strategy.id)
        if trades:
            symbols.add(strategy.symbol)
    
    return sorted(list(symbols))


@router.get("/symbol/{symbol}/pnl", response_model=SymbolPnL)
def get_symbol_pnl(
    symbol: str,
    runner: StrategyRunner = Depends(get_strategy_runner),
    client: BinanceClient = Depends(get_binance_client),
) -> SymbolPnL:
    """Get profit and loss summary for a specific symbol."""
    symbol = symbol.upper()
    
    # Get all strategies for this symbol
    strategies = runner.list_strategies()
    symbol_strategies = [s for s in strategies if s.symbol.upper() == symbol]
    
    if not symbol_strategies:
        # Return empty PnL if no strategies found
        return SymbolPnL(symbol=symbol)
    
    # Collect all trades for this symbol
    all_trades: List[OrderResponse] = []
    for strategy in symbol_strategies:
        trades = runner.get_trades(strategy.id)
        all_trades.extend(trades)
    
    # Calculate completed trades and realized PnL
    completed_trades = []
    position_queue = []  # List of (quantity, entry_price, side, strategy_id, strategy_name) tuples
    
    # Build a map of order_id to strategy for faster lookup
    order_to_strategy = {}
    for strategy in symbol_strategies:
        strategy_trades = runner.get_trades(strategy.id)
        for t in strategy_trades:
            if t.order_id not in order_to_strategy:
                order_to_strategy[t.order_id] = (strategy.id, strategy.name)
    
    for trade in all_trades:
        entry_price = trade.avg_price or trade.price
        quantity = trade.executed_qty
        side = trade.side
        
        # Find strategy info from map
        strategy_id, strategy_name = order_to_strategy.get(trade.order_id, (None, None))
        
        if side == "BUY":
            if position_queue and position_queue[0][2] == "SHORT":
                # Closing or reducing SHORT position
                remaining_qty = quantity
                while remaining_qty > 0 and position_queue and position_queue[0][2] == "SHORT":
                    short_entry = position_queue[0]
                    short_qty = short_entry[0]
                    short_price = short_entry[1]
                    short_strategy_id = short_entry[3]
                    short_strategy_name = short_entry[4]
                    
                    if short_qty <= remaining_qty:
                        close_qty = short_qty
                        position_queue.pop(0)
                    else:
                        close_qty = remaining_qty
                        position_queue[0] = (short_qty - remaining_qty, short_price, "SHORT", short_strategy_id, short_strategy_name)
                    
                    # PnL for SHORT: entry_price - exit_price
                    pnl = (short_price - entry_price) * close_qty
                    completed_trades.append(TradeSummary(
                        symbol=symbol,
                        entry_price=short_price,
                        exit_price=entry_price,
                        quantity=close_qty,
                        side="SHORT",
                        realized_pnl=pnl,
                        strategy_id=short_strategy_id,
                        strategy_name=short_strategy_name,
                    ))
                    remaining_qty -= close_qty
                
                # If remaining quantity after closing SHORT, open LONG
                if remaining_qty > 0:
                    position_queue.append((remaining_qty, entry_price, "LONG", strategy_id, strategy_name))
            else:
                # Opening or adding to LONG position
                position_queue.append((quantity, entry_price, "LONG", strategy_id, strategy_name))
        
        elif side == "SELL":
            if position_queue and position_queue[0][2] == "LONG":
                # Closing or reducing LONG position
                remaining_qty = quantity
                while remaining_qty > 0 and position_queue and position_queue[0][2] == "LONG":
                    long_entry = position_queue[0]
                    long_qty = long_entry[0]
                    long_price = long_entry[1]
                    long_strategy_id = long_entry[3]
                    long_strategy_name = long_entry[4]
                    
                    if long_qty <= remaining_qty:
                        close_qty = long_qty
                        position_queue.pop(0)
                    else:
                        close_qty = remaining_qty
                        position_queue[0] = (long_qty - remaining_qty, long_price, "LONG", long_strategy_id, long_strategy_name)
                    
                    # PnL for LONG: exit_price - entry_price
                    pnl = (entry_price - long_price) * close_qty
                    completed_trades.append(TradeSummary(
                        symbol=symbol,
                        entry_price=long_price,
                        exit_price=entry_price,
                        quantity=close_qty,
                        side="LONG",
                        realized_pnl=pnl,
                        strategy_id=long_strategy_id,
                        strategy_name=long_strategy_name,
                    ))
                    remaining_qty -= close_qty
                
                # If remaining quantity after closing LONG, open SHORT
                if remaining_qty > 0:
                    position_queue.append((remaining_qty, entry_price, "SHORT", strategy_id, strategy_name))
            else:
                # Opening or adding to SHORT position
                position_queue.append((quantity, entry_price, "SHORT", strategy_id, strategy_name))
    
    # Calculate realized PnL statistics
    total_realized_pnl = sum(t.realized_pnl for t in completed_trades)
    winning_trades = len([t for t in completed_trades if t.realized_pnl > 0])
    losing_trades = len([t for t in completed_trades if t.realized_pnl < 0])
    win_rate = (winning_trades / len(completed_trades) * 100) if completed_trades else 0
    
    # Get open positions from Binance
    open_positions = []
    total_unrealized_pnl = 0.0
    
    try:
        position_data = client.get_open_position(symbol)
        if position_data:
            position_side = "LONG" if position_data["positionAmt"] > 0 else "SHORT"
            
            # Find matching strategy if any
            strategy_match = None
            for strategy in symbol_strategies:
                if strategy.position_size and abs(strategy.position_size) > 0:
                    strategy_match = strategy
                    break
            
            open_positions.append(PositionSummary(
                symbol=symbol,
                position_size=abs(position_data["positionAmt"]),
                entry_price=position_data["entryPrice"],
                current_price=position_data["markPrice"],
                position_side=position_side,
                unrealized_pnl=position_data["unRealizedProfit"],
                leverage=position_data["leverage"],
                strategy_id=strategy_match.id if strategy_match else None,
                strategy_name=strategy_match.name if strategy_match else None,
            ))
            total_unrealized_pnl = position_data["unRealizedProfit"]
    except Exception as exc:
        logger.warning(f"Could not get open position for {symbol}: {exc}")
    
    return SymbolPnL(
        symbol=symbol,
        total_realized_pnl=round(total_realized_pnl, 4),
        total_unrealized_pnl=round(total_unrealized_pnl, 4),
        total_pnl=round(total_realized_pnl + total_unrealized_pnl, 4),
        open_positions=open_positions,
        closed_trades=completed_trades,
        total_trades=len(all_trades),
        completed_trades=len(completed_trades),
        win_rate=round(win_rate, 2),
        winning_trades=winning_trades,
        losing_trades=losing_trades,
    )


@router.get("/pnl/overview", response_model=List[SymbolPnL])
def get_pnl_overview(
    runner: StrategyRunner = Depends(get_strategy_runner),
    client: BinanceClient = Depends(get_binance_client),
) -> List[SymbolPnL]:
    """Get PnL overview for all symbols with trades."""
    # Get all unique symbols
    symbols = set()
    strategies = runner.list_strategies()
    for strategy in strategies:
        trades = runner.get_trades(strategy.id)
        if trades:
            symbols.add(strategy.symbol)
    
    # Get PnL for each symbol
    pnl_list = []
    for symbol in sorted(symbols):
        try:
            pnl = get_symbol_pnl(symbol, runner, client)
            pnl_list.append(pnl)
        except Exception as exc:
            logger.warning(f"Failed to get PnL for {symbol}: {exc}")
            continue
    
    return pnl_list


@router.get("/symbol/{symbol}/trades", response_model=List[TradeWithTimestamp])
def get_symbol_trades(
    symbol: str,
    side: Optional[str] = Query(default=None, description="Filter by side (BUY/SELL)"),
    strategy_id: Optional[str] = Query(default=None, description="Filter by strategy ID"),
    runner: StrategyRunner = Depends(get_strategy_runner),
) -> List[TradeWithTimestamp]:
    """Get all trades for a specific symbol."""
    symbol = symbol.upper()
    
    # Get all strategies for this symbol
    strategies = runner.list_strategies()
    symbol_strategies = [s for s in strategies if s.symbol.upper() == symbol]
    
    if not symbol_strategies:
        return []
    
    all_trades = []
    for strategy in symbol_strategies:
        # Apply strategy_id filter
        if strategy_id and strategy.id != strategy_id:
            continue
        
        trades = runner.get_trades(strategy.id)
        for trade in trades:
            trade_with_ts = _convert_order_to_trade_with_timestamp(
                trade,
                strategy_id=strategy.id,
                strategy_name=strategy.name,
            )
            
            # Apply side filter
            if side and trade_with_ts.side.upper() != side.upper():
                continue
            
            all_trades.append(trade_with_ts)
    
    return all_trades

