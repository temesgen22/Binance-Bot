"""API routes for trade and position tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api.deps import (
    get_strategy_runner, get_binance_client, get_client_manager, 
    get_current_user, get_current_user_async, 
    get_database_service, get_database_service_async
)
from app.core.binance_client_manager import BinanceClientManager
from app.models.trade import (
    TradeWithTimestamp,
    PositionSummary,
    TradeSummary,
    SymbolPnL,
    TradeFilterParams,
)
from app.models.order import OrderResponse
from app.models.db_models import User
from app.services.strategy_runner import StrategyRunner
from app.services.trade_service import TradeService
from app.services.database_service import DatabaseService
from app.core.my_binance_client import BinanceClient
from app.core.exceptions import StrategyNotFoundError
from app.core.redis_storage import RedisStorage
from app.core.config import get_settings


router = APIRouter(prefix="/trades", tags=["trades"])


def _convert_order_to_trade_with_timestamp(
    order: OrderResponse,
    strategy_id: Optional[str] = None,
    strategy_name: Optional[str] = None,
) -> TradeWithTimestamp:
    """Convert OrderResponse to TradeWithTimestamp.
    
    Uses actual Binance order timestamp if available, otherwise falls back.
    """
    # Use actual timestamp from Binance order response if available
    # Order of preference: timestamp -> update_time -> fallback to current time
    order_timestamp = order.timestamp or order.update_time or datetime.now(timezone.utc)
    
    return TradeWithTimestamp(
        symbol=order.symbol,
        order_id=order.order_id,
        status=order.status,
        side=order.side,
        price=order.price,
        avg_price=order.avg_price,
        executed_qty=order.executed_qty,
        timestamp=order_timestamp,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        # Include Binance trade parameters if available
        commission=getattr(order, 'commission', None),
        commission_asset=getattr(order, 'commission_asset', None),
        leverage=getattr(order, 'leverage', None),
        initial_margin=getattr(order, 'initial_margin', None),
        margin_type=getattr(order, 'margin_type', None),
        notional_value=getattr(order, 'notional_value', None),
        client_order_id=getattr(order, 'client_order_id', None),
    )


@router.get("/list", response_model=List[TradeWithTimestamp])
async def list_all_trades(
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    start_date: Optional[str] = Query(default=None, description="Filter from date (ISO format or YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="Filter until date (ISO format or YYYY-MM-DD)"),
    side: Optional[str] = Query(default=None, description="Filter by side (BUY/SELL)"),
    strategy_id: Optional[str] = Query(default=None, description="Filter by strategy ID"),
    account_id: Optional[str] = Query(default=None, description="Filter by Binance account ID"),
    current_user: User = Depends(get_current_user_async),
    runner: StrategyRunner = Depends(get_strategy_runner),
    db_service: DatabaseService = Depends(get_database_service_async),
) -> List[TradeWithTimestamp]:
    """Get all trades across all strategies with optional filtering.
    
    This endpoint prioritizes fetching from the database for accurate historical data.
    Falls back to StrategyRunner (Redis/in-memory) if database query fails.
    """
    try:
        # Parse datetime strings
        start_datetime: Optional[datetime] = None
        end_datetime: Optional[datetime] = None
        
        if start_date:
            try:
                # Try parsing ISO format first, then fallback to other formats
                start_datetime = date_parser.parse(start_date)
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Invalid start_date format: {start_date}, error: {exc}")
                start_datetime = None
        
        if end_date:
            try:
                # Try parsing ISO format first, then fallback to other formats
                end_datetime = date_parser.parse(end_date)
                if end_datetime.tzinfo is None:
                    end_datetime = end_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Invalid end_date format: {end_date}, error: {exc}")
                end_datetime = None
        
        all_trades = []
        
        # Try to fetch from database first (more reliable for historical data)
        try:
            # Create TradeService for database access
            settings = get_settings()
            redis_storage = None
            if settings.redis_enabled:
                redis_storage = RedisStorage(
                    redis_url=settings.redis_url,
                    enabled=settings.redis_enabled
                )
            # Get the underlying SQLAlchemy session from DatabaseService
            from sqlalchemy.orm import Session
            db_session: Session = db_service.db
            trade_service = TradeService(db_session, redis_storage)
            
            # Get all strategies for this user
            strategies = runner.list_strategies()
            
            # If strategy_id filter is provided, get trades for that specific strategy
            if strategy_id:
                # Find the strategy
                target_strategy = None
                for s in strategies:
                    if s.id == strategy_id:
                        target_strategy = s
                        break
                
                if target_strategy:
                    # Get strategy UUID from database (async)
                    from app.services.strategy_service import StrategyService
                    strategy_service = StrategyService(db_session, redis_storage)
                    db_strategy = await strategy_service.db_service.async_get_strategy(current_user.id, strategy_id)
                    
                    if db_strategy:
                        # Fetch trades from database for this strategy (async)
                        db_trades = await trade_service.async_get_strategy_trades(
                            user_id=current_user.id,
                            strategy_id=db_strategy.id,
                            limit=10000  # Large limit to get all trades
                        )
                        
                        for trade in db_trades:
                            trade_with_ts = _convert_order_to_trade_with_timestamp(
                                trade,
                                strategy_id=target_strategy.id,
                                strategy_name=target_strategy.name,
                            )
                            
                            # Apply filters
                            if symbol and trade_with_ts.symbol.upper() != symbol.upper():
                                continue
                            if side and trade_with_ts.side.upper() != side.upper():
                                continue
                            if account_id and target_strategy.account_id != account_id:
                                continue
                            if start_datetime or end_datetime:
                                trade_timestamp = trade_with_ts.timestamp
                                if trade_timestamp.tzinfo is None:
                                    trade_timestamp = trade_timestamp.replace(tzinfo=timezone.utc)
                                if start_datetime and trade_timestamp < start_datetime:
                                    continue
                                if end_datetime and trade_timestamp > end_datetime:
                                    continue
                            
                            all_trades.append(trade_with_ts)
            else:
                # Get trades for all strategies (batch query for efficiency)
                strategy_uuids = []
                strategy_map = {}  # Map UUID to StrategySummary
                
                for strategy in strategies:
                    # Apply account_id filter
                    if account_id and strategy.account_id != account_id:
                        continue
                    # Apply symbol filter
                    if symbol and strategy.symbol.upper() != symbol.upper():
                        continue
                    
                    # Get strategy UUID from database (async)
                    from app.services.strategy_service import StrategyService
                    strategy_service = StrategyService(db_service.db, redis_storage)
                    db_strategy = await strategy_service.db_service.async_get_strategy(current_user.id, strategy.id)
                    
                    if db_strategy:
                        strategy_uuids.append(db_strategy.id)
                        strategy_map[db_strategy.id] = strategy
                
                if strategy_uuids:
                    # Batch fetch trades from database (async)
                    trades_by_strategy = await trade_service.async_get_trades_batch(
                        user_id=current_user.id,
                        strategy_ids=strategy_uuids,
                        limit_per_strategy=10000
                    )
                    
                    # Convert to TradeWithTimestamp and apply filters
                    for strategy_uuid, trades in trades_by_strategy.items():
                        strategy = strategy_map.get(strategy_uuid)
                        if not strategy:
                            continue
                        
                        for trade in trades:
                            trade_with_ts = _convert_order_to_trade_with_timestamp(
                                trade,
                                strategy_id=strategy.id,
                                strategy_name=strategy.name,
                            )
                            
                            # Apply filters
                            if side and trade_with_ts.side.upper() != side.upper():
                                continue
                            if start_datetime or end_datetime:
                                trade_timestamp = trade_with_ts.timestamp
                                if trade_timestamp.tzinfo is None:
                                    trade_timestamp = trade_timestamp.replace(tzinfo=timezone.utc)
                                if start_datetime and trade_timestamp < start_datetime:
                                    continue
                                if end_datetime and trade_timestamp > end_datetime:
                                    continue
                            
                            all_trades.append(trade_with_ts)
            
            logger.info(f"Retrieved {len(all_trades)} trades from database with filters: symbol={symbol}, side={side}, strategy_id={strategy_id}")
            
        except Exception as db_exc:
            logger.warning(f"Failed to fetch trades from database: {db_exc}, falling back to StrategyRunner")
            # Fallback to StrategyRunner method (Redis/in-memory)
            strategies = runner.list_strategies()
            
            for strategy in strategies:
                # Apply filters
                if strategy_id and strategy.id != strategy_id:
                    continue
                if account_id and strategy.account_id != account_id:
                    continue
                if symbol and strategy.symbol.upper() != symbol.upper():
                    continue
                
                try:
                    strategy_trades = runner.get_trades(strategy.id)
                    for trade in strategy_trades:
                        trade_with_ts = _convert_order_to_trade_with_timestamp(
                            trade,
                            strategy_id=strategy.id,
                            strategy_name=strategy.name,
                        )
                        
                        if side and trade_with_ts.side.upper() != side.upper():
                            continue
                        
                        if start_datetime or end_datetime:
                            trade_timestamp = trade_with_ts.timestamp
                            if trade_timestamp.tzinfo is None:
                                trade_timestamp = trade_timestamp.replace(tzinfo=timezone.utc)
                            if start_datetime and trade_timestamp < start_datetime:
                                continue
                            if end_datetime and trade_timestamp > end_datetime:
                                continue
                        
                        all_trades.append(trade_with_ts)
                except Exception as exc:
                    logger.warning(f"Error getting trades for strategy {strategy.id}: {exc}")
                    continue
        
        # Sort by timestamp (newest first)
        all_trades.sort(key=lambda t: t.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        
        logger.info(f"Returning {len(all_trades)} trades with filters: symbol={symbol}, side={side}, strategy_id={strategy_id}")
        return all_trades
    
    except Exception as exc:
        logger.exception(f"Error in list_all_trades endpoint: {exc}")
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving trades: {str(exc)}"
        ) from exc


@router.get("/symbols", response_model=List[str])
def list_symbols(
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner)
) -> List[str]:
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
    account_id: Optional[str] = Query(default=None, description="Filter by Binance account ID"),
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner),
    client: BinanceClient = Depends(get_binance_client),
    client_manager: BinanceClientManager = Depends(get_client_manager),
) -> SymbolPnL:
    """Get profit and loss summary for a specific symbol."""
    symbol = symbol.upper()
    
    # Get all strategies for this symbol
    strategies = runner.list_strategies()
    symbol_strategies = [s for s in strategies if s.symbol.upper() == symbol]
    
    # Apply account_id filter
    if account_id:
        symbol_strategies = [s for s in symbol_strategies if s.account_id == account_id]
    
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
    
    # Get open positions from Binance - use account-specific client if filtering by account_id
    open_positions = []
    total_unrealized_pnl = 0.0
    
    # Use account-specific client when filtering by account_id
    position_client = client
    if account_id:
        try:
            account_client = client_manager.get_client(account_id)
            if account_client:
                position_client = account_client
        except Exception as exc:
            logger.warning(f"Could not get account-specific client for {account_id}, using default: {exc}")
    
    try:
        position_data = position_client.get_open_position(symbol)
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
        total_trades=len(completed_trades),  # Use completed trades for consistency with win rate calculation
        completed_trades=len(completed_trades),
        win_rate=round(win_rate, 2),
        winning_trades=winning_trades,
        losing_trades=losing_trades,
    )


@router.get("/pnl/overview", response_model=List[SymbolPnL])
def get_pnl_overview(
    account_id: Optional[str] = Query(default=None, description="Filter by Binance account ID"),
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner),
    client: BinanceClient = Depends(get_binance_client),
) -> List[SymbolPnL]:
    """Get PnL overview for all symbols with trades."""
    # Get all unique symbols
    symbols = set()
    strategies = runner.list_strategies()
    for strategy in strategies:
        # Apply account_id filter
        if account_id and strategy.account_id != account_id:
            continue
        trades = runner.get_trades(strategy.id)
        if trades:
            symbols.add(strategy.symbol)
    
    # Get PnL for each symbol
    pnl_list = []
    for symbol in sorted(symbols):
        try:
            pnl = get_symbol_pnl(symbol, account_id=account_id, runner=runner, client=client)
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
    current_user: User = Depends(get_current_user),
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

