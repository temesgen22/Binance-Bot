"""API routes for trade and position tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

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


router = APIRouter(prefix="/api/trades", tags=["trades"])


async def _get_completed_trades_from_database_for_trades_page(
    db_service: DatabaseService,
    user_id: UUID,
    strategy_uuid: UUID,
    strategy_id: str,
    strategy_name: str,
    start_datetime: Optional[datetime] = None,
    end_datetime: Optional[datetime] = None,
) -> List[TradeWithTimestamp]:
    """Get completed trades from CompletedTrade table and convert to TradeWithTimestamp.
    
    Returns both entry and exit orders for each completed trade so the frontend
    can display them as individual trades.
    
    Args:
        db_service: Database service (async)
        user_id: User UUID
        strategy_uuid: Strategy UUID (from database)
        strategy_id: Strategy ID string
        strategy_name: Strategy name
        start_datetime: Optional start date filter
        end_datetime: Optional end date filter
    
    Returns:
        List of TradeWithTimestamp objects (entry and exit orders)
    """
    try:
        from app.models.db_models import CompletedTrade, Strategy, Account
        from sqlalchemy import select
        
        # Check if strategy is using paper trading account (async)
        stmt = select(Strategy).filter(Strategy.id == strategy_uuid)
        result = await db_service.db.execute(stmt)
        strategy = result.scalar_one_or_none()
        include_paper_trades = False
        
        if strategy and strategy.account_id:
            account_stmt = select(Account).filter(Account.id == strategy.account_id)
            account_result = await db_service.db.execute(account_stmt)
            account = account_result.scalar_one_or_none()
            if account and account.paper_trading:
                include_paper_trades = True
        
        # Build query (async)
        stmt = select(CompletedTrade).filter(
            CompletedTrade.user_id == user_id,
            CompletedTrade.strategy_id == strategy_uuid,
        )
        
        # Filter paper trades based on strategy's account type
        if include_paper_trades:
            stmt = stmt.filter(CompletedTrade.paper_trading == True)
        else:
            stmt = stmt.filter(CompletedTrade.paper_trading == False)
        
        # Apply date filters
        if start_datetime:
            stmt = stmt.filter(CompletedTrade.exit_time >= start_datetime)
        if end_datetime:
            stmt = stmt.filter(CompletedTrade.exit_time <= end_datetime)
        
        # Order by exit time (most recent first)
        stmt = stmt.order_by(CompletedTrade.exit_time.desc())
        
        # Execute query (async)
        result = await db_service.db.execute(stmt)
        completed_trades = result.scalars().all()
        
        # Convert to TradeWithTimestamp (create entry and exit orders)
        trade_list = []
        for ct in completed_trades:
            # Create entry order
            entry_side = "BUY" if ct.side == "LONG" else "SELL"
            entry_trade = TradeWithTimestamp(
                symbol=ct.symbol,
                order_id=ct.entry_order_id,
                status="FILLED",
                side=entry_side,
                price=float(ct.entry_price),
                avg_price=float(ct.entry_price),
                executed_qty=float(ct.quantity),
                timestamp=ct.entry_time,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                commission=float(ct.fee_paid) / 2 if ct.fee_paid else None,  # Split fee between entry/exit
                leverage=ct.leverage or None,
                initial_margin=float(ct.initial_margin) if ct.initial_margin else None,
                margin_type=ct.margin_type,
                notional_value=float(ct.notional_value) if ct.notional_value else None,
            )
            trade_list.append(entry_trade)
            
            # Create exit order
            exit_side = "SELL" if ct.side == "LONG" else "BUY"
            exit_trade = TradeWithTimestamp(
                symbol=ct.symbol,
                order_id=ct.exit_order_id,
                status="FILLED",
                side=exit_side,
                price=float(ct.exit_price),
                avg_price=float(ct.exit_price),
                executed_qty=float(ct.quantity),
                timestamp=ct.exit_time,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                commission=float(ct.fee_paid) / 2 if ct.fee_paid else None,  # Split fee between entry/exit
                leverage=ct.leverage or None,
                initial_margin=None,  # Exit doesn't have initial margin
                margin_type=ct.margin_type,
                notional_value=float(ct.exit_price * ct.quantity) if ct.exit_price and ct.quantity else None,
            )
            trade_list.append(exit_trade)
        
        logger.info(
            f"_get_completed_trades_from_database_for_trades_page: Found {len(completed_trades)} completed trades "
            f"({len(trade_list)} order entries) for strategy {strategy_id} (UUID {strategy_uuid})"
        )
        return trade_list
        
    except Exception as e:
        logger.warning(
            f"Failed to get completed trades from database for strategy {strategy_id}: {e}",
            exc_info=True
        )
        return []


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
                # Check if it's date-only format (YYYY-MM-DD) or includes time
                if 'T' in start_date or '+' in start_date or start_date.count(':') >= 2:
                    # ISO format with time: parse as-is
                    start_datetime = date_parser.parse(start_date)
                else:
                    # Date-only format: set to start of day (00:00:00)
                    start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Invalid start_date format: {start_date}, error: {exc}")
                start_datetime = None
        
        if end_date:
            try:
                # Check if it's date-only format (YYYY-MM-DD) or includes time
                if 'T' in end_date or '+' in end_date or end_date.count(':') >= 2:
                    # ISO format with time: parse as-is
                    end_datetime = date_parser.parse(end_date)
                else:
                    # Date-only format: set to end of day (23:59:59.999999)
                    end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                    end_datetime = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                if end_datetime.tzinfo is None:
                    end_datetime = end_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Invalid end_date format: {end_date}, error: {exc}")
                end_datetime = None
        
        all_trades = []
        
        # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
        # This is much faster than on-demand matching and uses existing functionality
        try:
            settings = get_settings()
            redis_storage = None
            if settings.redis_enabled:
                redis_storage = RedisStorage(
                    redis_url=settings.redis_url,
                    enabled=settings.redis_enabled
                )
            
            # Get all strategies for this user
            strategies = runner.list_strategies()
            
            # Get strategy service for database lookups
            from app.services.strategy_service import StrategyService
            from sqlalchemy.orm import Session
            db_session: Session = db_service.db
            strategy_service = StrategyService(db_session, redis_storage)
            
            # If strategy_id filter is provided, get trades for that specific strategy
            if strategy_id:
                # Find the strategy
                target_strategy = None
                for s in strategies:
                    if s.id == strategy_id:
                        target_strategy = s
                        break
                
                if target_strategy:
                    # Apply account_id filter
                    if account_id and target_strategy.account_id != account_id:
                        pass  # Skip this strategy
                    else:
                        # Get strategy UUID from database (async)
                        db_strategy = await strategy_service.db_service.async_get_strategy(current_user.id, strategy_id)
                        
                        if db_strategy:
                            # Fetch completed trades from database (pre-computed)
                            completed_trades = await _get_completed_trades_from_database_for_trades_page(
                                db_service=db_service,
                                user_id=current_user.id,
                                strategy_uuid=db_strategy.id,
                                strategy_id=target_strategy.id,
                                strategy_name=target_strategy.name,
                                start_datetime=start_datetime,
                                end_datetime=end_datetime,
                            )
                            
                            # Apply filters
                            for trade in completed_trades:
                                if symbol and trade.symbol.upper() != symbol.upper():
                                    continue
                                if side and trade.side.upper() != side.upper():
                                    continue
                                
                                all_trades.append(trade)
            else:
                # Get completed trades for all strategies
                for strategy in strategies:
                    # Apply account_id filter
                    if account_id and strategy.account_id != account_id:
                        continue
                    # Apply symbol filter (pre-filter for efficiency)
                    if symbol and strategy.symbol.upper() != symbol.upper():
                        continue
                    
                    try:
                        # Get strategy UUID from database (async)
                        db_strategy = await strategy_service.db_service.async_get_strategy(current_user.id, strategy.id)
                        
                        if db_strategy:
                            # Fetch completed trades from database (pre-computed)
                            completed_trades = await _get_completed_trades_from_database_for_trades_page(
                                db_service=db_service,
                                user_id=current_user.id,
                                strategy_uuid=db_strategy.id,
                                strategy_id=strategy.id,
                                strategy_name=strategy.name,
                                start_datetime=start_datetime,
                                end_datetime=end_datetime,
                            )
                            
                            # Apply filters
                            for trade in completed_trades:
                                if side and trade.side.upper() != side.upper():
                                    continue
                                
                                all_trades.append(trade)
                    except Exception as exc:
                        logger.warning(f"Error getting completed trades for strategy {strategy.id}: {exc}")
                        continue
            
            logger.info(f"Retrieved {len(all_trades)} trades from completed_trades table with filters: symbol={symbol}, side={side}, strategy_id={strategy_id}")
            
        except Exception as db_exc:
            logger.warning(f"Failed to fetch completed trades from database: {db_exc}, falling back to StrategyRunner")
            # Fallback to StrategyRunner method (Redis/in-memory) - this is the old behavior
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
    start_date: Optional[str] = Query(default=None, description="Filter from date (ISO format or YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="Filter until date (ISO format or YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner),
    client: BinanceClient = Depends(get_binance_client),
    client_manager: BinanceClientManager = Depends(get_client_manager),
    db_service: DatabaseService = Depends(get_database_service),
) -> SymbolPnL:
    """Get profit and loss summary for a specific symbol."""
    symbol = symbol.upper()
    
    # Parse date filters
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    
    if start_date:
        try:
            # Check if it's date-only format (YYYY-MM-DD) or includes time
            if 'T' in start_date or '+' in start_date or start_date.count(':') >= 2:
                # ISO format with time: parse as-is
                start_datetime = date_parser.parse(start_date)
            else:
                # Date-only format: set to start of day (00:00:00)
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            
            if start_datetime.tzinfo is None:
                start_datetime = start_datetime.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as exc:
            logger.warning(f"Invalid start_date format: {start_date}, error: {exc}")
            start_datetime = None
    
    if end_date:
        try:
            # Check if it's date-only format (YYYY-MM-DD) or includes time
            if 'T' in end_date or '+' in end_date or end_date.count(':') >= 2:
                # ISO format with time: parse as-is
                end_datetime = date_parser.parse(end_date)
            else:
                # Date-only format: set to end of day (23:59:59.999999)
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            if end_datetime.tzinfo is None:
                end_datetime = end_datetime.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as exc:
            logger.warning(f"Invalid end_date format: {end_date}, error: {exc}")
            end_datetime = None
    
    # Get all strategies for this symbol
    strategies = runner.list_strategies()
    symbol_strategies = [s for s in strategies if s.symbol.upper() == symbol]
    
    # Apply account_id filter
    if account_id:
        symbol_strategies = [s for s in symbol_strategies if s.account_id == account_id]
    
    # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
    # This is much faster than on-demand matching and uses existing functionality
    completed_trades = []
    total_trade_fees = 0.0
    total_funding_fees = 0.0
    
    if symbol_strategies and db_service:
        try:
            # Verify db_service is actually a DatabaseService instance (not a Depends object)
            if not isinstance(db_service, DatabaseService):
                logger.warning(f"db_service is not a DatabaseService instance. Type: {type(db_service)}. Skipping database operations.")
                db_service = None
            
            if db_service:
                # Get completed trades from database for all strategies
                from app.api.routes.reports import _get_completed_trades_from_database
                from app.services.strategy_service import StrategyService
                settings = get_settings()
                redis_storage = None
                if settings.redis_enabled:
                    redis_storage = RedisStorage(
                        redis_url=settings.redis_url,
                        enabled=settings.redis_enabled
                    )
                
                # Ensure db_service has db attribute
                if not hasattr(db_service, 'db'):
                    logger.warning(f"db_service does not have 'db' attribute. Type: {type(db_service)}")
                    raise AttributeError("db_service does not have 'db' attribute")
                
                strategy_service = StrategyService(db_service.db, redis_storage)
                
                for strategy in symbol_strategies:
                    try:
                        # Get strategy UUID from database
                        db_strategy = strategy_service.db_service.get_strategy(current_user.id, strategy.id)
                        
                        if db_strategy:
                            # Get completed trades from database (pre-computed)
                            trade_reports = _get_completed_trades_from_database(
                                db_service=db_service,
                                user_id=current_user.id,
                                strategy_uuid=db_strategy.id,
                                strategy_id=strategy.id,
                                start_datetime=start_datetime,
                                end_datetime=end_datetime,
                            )
                            
                            # Convert TradeReport to TradeSummary for PnL calculation
                            # Also accumulate fees from TradeReport
                            for tr in trade_reports:
                                completed_trades.append(TradeSummary(
                                    symbol=tr.symbol,
                                    entry_price=tr.entry_price,
                                    exit_price=tr.exit_price,
                                    quantity=tr.quantity,
                                    side=tr.side,  # "LONG" or "SHORT"
                                    realized_pnl=tr.pnl_usd,  # Use pre-computed PnL from database
                                    entry_time=tr.entry_time,
                                    exit_time=tr.exit_time,
                                    strategy_id=tr.strategy_id,
                                    strategy_name=strategy.name,
                                ))
                                # Accumulate fees from TradeReport
                                total_trade_fees += tr.fee_paid
                                total_funding_fees += tr.funding_fee
                    except Exception as e:
                        logger.warning(f"Could not get completed trades for strategy {strategy.id}: {e}", exc_info=True)
                        continue
                
                logger.info(f"Retrieved {len(completed_trades)} completed trades from database for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to get completed trades from database for {symbol}: {e}", exc_info=True)
            # Fallback: completed_trades will be empty, which is fine - we'll just have no completed trades
    
    # Calculate realized PnL statistics (only if we processed trades)
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
                logger.debug(f"Using account-specific client for {account_id} to get position for {symbol}")
            else:
                logger.warning(
                    f"⚠️ Account '{account_id}' not found in client manager. "
                    f"Falling back to default client. This may cause API key errors if default client has invalid keys."
                )
        except Exception as exc:
            logger.warning(
                f"⚠️ Could not get account-specific client for {account_id}, using default: {exc}. "
                f"This may cause API key errors if default client has invalid keys."
            )
    
    try:
        # Validate client before calling
        if position_client is None:
            logger.warning(f"Position client is None for {symbol} (account_id: {account_id or 'default'}). Cannot get open position.")
            position_data = None
        else:
            logger.debug(f"Getting position for {symbol} using client (account_id: {account_id or 'default'})")
            try:
                position_data = position_client.get_open_position(symbol)
            except Exception as pos_exc:
                # Handle RetryError from tenacity retry decorator
                from tenacity import RetryError
                if isinstance(pos_exc, RetryError):
                    # Extract underlying exception from RetryError
                    try:
                        underlying_exc = pos_exc.last_attempt.exception() if hasattr(pos_exc, 'last_attempt') and pos_exc.last_attempt else pos_exc
                    except (AttributeError, Exception) as extract_exc:
                        # If we can't extract the underlying exception, use the RetryError itself
                        underlying_exc = pos_exc
                        logger.debug(f"Could not extract underlying exception from RetryError: {extract_exc}")
                    
                    logger.warning(
                        f"Could not get open position for {symbol} after retries: {underlying_exc}. "
                        f"RetryError type: {type(pos_exc)}"
                    )
                else:
                    logger.warning(f"Could not get open position for {symbol}: {pos_exc}")
                position_data = None
        
        if position_data:
            position_side = "LONG" if position_data["positionAmt"] > 0 else "SHORT"
            binance_position_size = abs(position_data["positionAmt"])
            
            # Find matching strategy - verify position size and side match
            # Use best match (closest size) instead of first match
            strategy_match = None
            best_match_score = float('inf')
            
            for strategy in symbol_strategies:
                if strategy.position_size and abs(strategy.position_size) > 0:
                    # Check if position side matches
                    strategy_side = "LONG" if strategy.position_size > 0 else "SHORT"
                    if strategy_side == position_side:
                        # Calculate size difference (absolute and relative)
                        strategy_size = abs(strategy.position_size)
                        size_diff_abs = abs(strategy_size - binance_position_size)
                        size_diff_rel = size_diff_abs / max(strategy_size, binance_position_size, 0.01)
                        
                        # Match if within tolerance (5% relative or 0.01 absolute)
                        if size_diff_abs < 0.01 or size_diff_rel < 0.05:
                            # Use the match with smallest difference (best match)
                            if size_diff_rel < best_match_score:
                                best_match_score = size_diff_rel
                                strategy_match = strategy
            
            # BUG FIX: Don't use fallback to first strategy - leave as None if no match
            # This prevents incorrectly attributing positions to wrong strategies
            if not strategy_match:
                logger.debug(
                    f"Position for {symbol} doesn't match any strategy. "
                    f"Binance: {binance_position_size} {position_side}, "
                    f"Available strategies: {[(s.name, abs(s.position_size) if s.position_size else 0, 'LONG' if s.position_size and s.position_size > 0 else 'SHORT' if s.position_size and s.position_size < 0 else 'NONE') for s in symbol_strategies]}"
                )
            
            # Validate position data - skip invalid positions
            if position_data["entryPrice"] <= 0:
                logger.warning(f"Invalid entry price for {symbol}: {position_data['entryPrice']}. Skipping position.")
                # Skip this position - don't add it, but continue with rest of function
            elif position_data["markPrice"] <= 0:
                logger.warning(f"Invalid mark price for {symbol}: {position_data['markPrice']}. Skipping position.")
                # Skip this position - don't add it, but continue with rest of function
            else:
                # Position data is valid, add it
                open_positions.append(PositionSummary(
                    symbol=symbol,
                    position_size=binance_position_size,
                    entry_price=position_data["entryPrice"],
                    current_price=position_data["markPrice"],
                    position_side=position_side,
                    unrealized_pnl=position_data["unRealizedProfit"],
                    leverage=position_data["leverage"],
                    strategy_id=strategy_match.id if strategy_match else None,
                    strategy_name=strategy_match.name if strategy_match else None,
                ))
                total_unrealized_pnl = position_data["unRealizedProfit"]
            
            # Log if position doesn't match any strategy's tracked position
            if symbol_strategies:
                tracked_positions = [
                    (s.name, abs(s.position_size), "LONG" if s.position_size > 0 else "SHORT")
                    for s in symbol_strategies
                    if s.position_size and abs(s.position_size) > 0
                ]
                if tracked_positions:
                    logger.debug(
                        f"Binance position for {symbol}: {binance_position_size} {position_side}, "
                        f"Tracked positions: {tracked_positions}"
                    )
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
        total_trade_fees=round(total_trade_fees, 4) if total_trade_fees > 0 else None,
        total_funding_fees=round(total_funding_fees, 4) if total_funding_fees > 0 else None,
    )


@router.get("/pnl/overview", response_model=List[SymbolPnL])
def get_pnl_overview(
    account_id: Optional[str] = Query(default=None, description="Filter by Binance account ID"),
    start_date: Optional[str] = Query(default=None, description="Filter from date (ISO format or YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="Filter until date (ISO format or YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner),
    client: BinanceClient = Depends(get_binance_client),
    client_manager: BinanceClientManager = Depends(get_client_manager),
) -> List[SymbolPnL]:
    """Get PnL overview for all symbols with trades.
    
    Also checks Binance for positions that might not have corresponding trades
    (e.g., manually opened positions).
    """
    # Get all unique symbols from strategies with trades
    symbols = set()
    strategies = runner.list_strategies()
    for strategy in strategies:
        # Apply account_id filter
        if account_id and strategy.account_id != account_id:
            continue
        trades = runner.get_trades(strategy.id)
        if trades:
            symbols.add(strategy.symbol)
    
    # Also check Binance for positions that might not have trades
    # Use account-specific client when filtering by account_id
    position_client = client
    if account_id:
        try:
            account_client = client_manager.get_client(account_id)
            if account_client:
                position_client = account_client
        except Exception as exc:
            logger.warning(f"Could not get account-specific client for {account_id}, using default: {exc}")
    
    # Query Binance for all positions to find symbols we might have missed
    # This helps catch manually opened positions or positions from other systems
    try:
        # Get all positions from Binance
        # ✅ FIX: Handle both BinanceClient and PaperBinanceClient
        from app.core.paper_binance_client import PaperBinanceClient
        
        if isinstance(position_client, PaperBinanceClient):
            # Paper trading: use futures_position_information() method
            all_binance_positions = position_client.futures_position_information()
        else:
            # Real Binance: use _ensure().futures_position_information()
            rest = position_client._ensure()
            all_binance_positions = rest.futures_position_information()
        
        for pos in all_binance_positions:
            position_amt = float(pos.get("positionAmt", 0))
            if abs(position_amt) > 0:
                symbol = pos.get("symbol", "").upper()
                if symbol:
                    symbols.add(symbol)
                    logger.debug(f"Found position for {symbol} (not in strategies with trades)")
    except Exception as exc:
        logger.debug(f"Could not fetch all positions (this is optional): {exc}")
        # Continue with symbols from strategies only - this is not critical
    
    # Get PnL for each symbol
    pnl_list = []
    for symbol in sorted(symbols):
        try:
            pnl = get_symbol_pnl(
                symbol, 
                account_id=account_id, 
                start_date=start_date,
                end_date=end_date,
                runner=runner, 
                client=client,
                client_manager=client_manager
            )
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

