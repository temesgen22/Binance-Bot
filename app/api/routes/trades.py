"""API routes for trade and position tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel

from app.api.deps import (
    get_strategy_runner, get_binance_client, get_client_manager,
    get_current_user, get_current_user_async,
    get_database_service, get_database_service_async,
    get_account_service,
    get_mark_price_stream_manager,
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
from app.models.db_models import User, ManualPosition, Account
from app.services.strategy_runner import StrategyRunner
from app.services.trade_service import TradeService
from app.services.account_service import AccountService
from app.services.database_service import DatabaseService
from app.core.my_binance_client import BinanceClient
from app.core.exceptions import StrategyNotFoundError
from app.core.redis_storage import RedisStorage
from app.core.config import get_settings
from app.core.mark_price_stream_manager import MarkPriceStreamManager


router = APIRouter(prefix="/api/trades", tags=["trades"])


class ManualCloseRequest(BaseModel):
    symbol: Optional[str] = None
    position_side: Optional[str] = None


class ManualCloseResponse(BaseModel):
    strategy_id: str
    symbol: str
    position_side: str
    closed_quantity: float
    order_id: int
    exit_reason: str


def _normalize_margin_type(mt: Optional[str]) -> Optional[str]:
    """Normalize Binance marginType to CROSSED/ISOLATED for PositionSummary."""
    if mt is None or not str(mt).strip():
        return None
    u = str(mt).strip().upper()
    if u == "CROSS":
        return "CROSSED"
    if u in ("CROSSED", "ISOLATED"):
        return u
    return None


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


@router.post(
    "/strategies/{strategy_id}/manual-close",
    response_model=ManualCloseResponse,
    status_code=status.HTTP_200_OK,
)
async def manual_close_strategy_position(
    strategy_id: str,
    payload: ManualCloseRequest,
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner),
    db_service: DatabaseService = Depends(get_database_service),
) -> ManualCloseResponse:
    """Manually close a strategy-owned open position and record exit_reason=MANUAL."""
    if strategy_id.startswith("external_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="External positions cannot be closed via the bot; close them on Binance or the Binance app.",
        )
    if strategy_id.startswith("manual_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manual positions must be closed via POST /api/manual-trades/close with position_id.",
        )
    db_strategy = db_service.get_strategy(current_user.id, strategy_id)
    if not db_strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy not found: {strategy_id}",
        )

    try:
        result = await runner.manual_close_position(
            strategy_id,
            expected_symbol=payload.symbol,
            expected_position_side=payload.position_side,
        )
        return ManualCloseResponse(**result)
    except StrategyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy not found: {strategy_id}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(f"Manual close failed for strategy {strategy_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to manually close position: {exc}",
        ) from exc


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
    mark_price_manager: Optional[MarkPriceStreamManager] = Depends(get_mark_price_stream_manager),
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
    
    # Apply account_id filter (case-insensitive to match get_pnl_overview)
    if account_id:
        acc_normalized = (account_id or "").strip().lower()
        symbol_strategies = [
            s for s in symbol_strategies
            if ((getattr(s, "account_id", None) or "") or "default").strip().lower() == acc_normalized
        ]
    
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
    
    # Get open positions from Binance - use account-specific client (from DB when no .env keys)
    open_positions = []
    total_unrealized_pnl = 0.0
    
    position_client = client
    account_id_for_client = account_id
    if account_id_for_client:
        try:
            account_client = client_manager.get_client(account_id_for_client)
            if account_client:
                position_client = account_client
                logger.debug(f"Using account-specific client for {account_id_for_client} to get position for {symbol}")
        except Exception as exc:
            logger.warning(
                f"Could not get account-specific client for {account_id_for_client}, using default: {exc}"
            )
    elif symbol_strategies:
        # No account_id filter: use the account of the first strategy for this symbol (DB-backed keys)
        account_id_for_client = getattr(symbol_strategies[0], "account_id", None) or "default"
        try:
            account_client = client_manager.get_client(account_id_for_client)
            if account_client:
                position_client = account_client
                logger.debug(f"Using client for account {account_id_for_client} (from strategy) to get position for {symbol}")
        except Exception as exc:
            logger.debug(f"Could not get client for account {account_id_for_client}: {exc}")
    
    # Skip Binance position fetch if client has no valid API key (e.g. no keys in .env, account not loaded yet).
    # Paper (PaperBinanceClient) has no API key but we still fetch position from it.
    from app.core.paper_binance_client import PaperBinanceClient as _PaperBinanceClient

    def _client_has_api_key(c) -> bool:
        if c is None:
            return False
        if isinstance(c, _PaperBinanceClient):
            return True  # Paper client: no API key but valid for position fetch
        rest = getattr(c, "_rest", None)
        if rest is None:
            return False
        key = getattr(rest, "api_key", None) or getattr(rest, "_api_key", None)
        return bool(key and str(key).strip() and str(key).lower() not in ("demo", ""))

    def _normalize_position_data(data: dict) -> dict:
        """Normalize numeric position fields to float for both live (sometimes numeric) and paper (strings)."""
        if not data:
            return data
        result = dict(data)
        for key, default in [("positionAmt", 0), ("entryPrice", 0), ("markPrice", 0), ("unRealizedProfit", 0)]:
            val = result.get(key)
            if val is None:
                result[key] = float(default)
            else:
                try:
                    result[key] = float(val)
                except (TypeError, ValueError):
                    result[key] = float(default)
        return result

    try:
        if position_client is None or not _client_has_api_key(position_client):
            if position_client is None:
                logger.warning(f"Position client is None for {symbol} (account_id: {account_id or 'default'}). Cannot get open position.")
            else:
                logger.debug(f"Skipping Binance position fetch for {symbol} (no valid API key on client). Completed trades from DB still returned.")
            position_data = None
        else:
            logger.debug(f"Getting position for {symbol} using client (account_id: {account_id_for_client or account_id or 'default'})")
            try:
                position_data = position_client.get_open_position(symbol)
                if position_data:
                    position_data = _normalize_position_data(position_data)
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
            
            # Find matching strategy only when we can confirm ownership (position_instance_id).
            # This prevents showing a strategy name for manually opened positions or positions
            # the bot synced to but did not open (no entry trade → no position_instance_id).
            strategy_match = None
            best_match_score = float('inf')

            for strategy in symbol_strategies:
                # Only attribute to a strategy that actually opened this position (has position_instance_id)
                if getattr(strategy, "position_instance_id", None) is None:
                    continue
                if not strategy.position_size or abs(strategy.position_size) <= 0:
                    continue
                strategy_side = "LONG" if strategy.position_size > 0 else "SHORT"
                if strategy_side != position_side:
                    continue
                strategy_size = abs(strategy.position_size)
                size_diff_abs = abs(strategy_size - binance_position_size)
                size_diff_rel = size_diff_abs / max(strategy_size, binance_position_size, 0.01)
                if size_diff_abs >= 0.01 and size_diff_rel >= 0.05:
                    continue
                if size_diff_rel < best_match_score:
                    best_match_score = size_diff_rel
                    strategy_match = strategy

            # Require strategy to have unclosed entry quantity (avoid attributing when position_instance_id was recovered from old trade but position is manual)
            if strategy_match and db_service and current_user:
                try:
                    db_strat = db_service.get_strategy(current_user.id, strategy_match.id)
                    if db_strat and getattr(strategy_match, "position_instance_id", None):
                        owned_qty, has_entries = db_service.get_strategy_owned_quantity(
                            db_strat.id,
                            symbol,
                            strategy_match.position_instance_id,
                            position_side,
                        )
                        if not has_entries or owned_qty <= 0:
                            strategy_match = None
                except Exception as e:
                    logger.debug(f"Ownership check for {symbol} failed: {e}")
                    strategy_match = None

            if not strategy_match:
                logger.debug(
                    f"Position for {symbol} not attributed to any strategy (manual or no position_instance_id). "
                    f"Binance: {binance_position_size} {position_side}."
                )

            # When no strategy matched, check for open manual position so REST returns consistent owner on refresh.
            # Only attribute to manual if the Binance position actually matches the ManualPosition (same entry + size);
            # otherwise it was opened on Binance externally and we show External.
            manual_attribution = None
            if not strategy_match and db_service and current_user and hasattr(db_service, "db"):
                try:
                    acc = (account_id_for_client or "default").lower()
                    manual_candidate = db_service.db.query(ManualPosition).filter(
                        ManualPosition.user_id == current_user.id,
                        ManualPosition.symbol == symbol,
                        ManualPosition.side == position_side,
                        ManualPosition.status == "OPEN",
                        ManualPosition.account_id == acc,
                    ).first()
                    if manual_candidate is not None:
                        binance_entry = float(position_data.get("entryPrice") or 0)
                        manual_entry = float(manual_candidate.entry_price or 0)
                        manual_qty = float(manual_candidate.remaining_quantity or manual_candidate.quantity or 0)
                        entry_ok = abs(binance_entry - manual_entry) <= max(1e-6, 1e-4 * max(abs(binance_entry), abs(manual_entry), 0.01))
                        size_ok = abs(binance_position_size - manual_qty) <= max(1e-8, 0.01 * max(binance_position_size, manual_qty, 0.0001))
                        if entry_ok and size_ok:
                            manual_attribution = manual_candidate
                        else:
                            logger.debug(
                                f"Binance position {symbol} {position_side} (entry={binance_entry}, size={binance_position_size}) "
                                f"does not match open ManualPosition (entry={manual_entry}, qty={manual_qty}); showing as External"
                            )
                except Exception as e:
                    logger.debug(f"Manual position lookup for {symbol} {position_side}: {e}")
            
            # Validate position data - skip invalid positions
            if position_data["entryPrice"] <= 0:
                logger.warning(f"Invalid entry price for {symbol}: {position_data['entryPrice']}. Skipping position.")
                # Skip this position - don't add it, but continue with rest of function
            elif position_data["markPrice"] <= 0:
                logger.warning(f"Invalid mark price for {symbol}: {position_data['markPrice']}. Skipping position.")
                # Skip this position - don't add it, but continue with rest of function
            else:
                # Position data is valid. Prefer Binance leverage: from position dict first, then get_current_leverage (same API, non-zero position), then strategy.
                binance_leverage = position_data.get("leverage") or 0
                try:
                    binance_leverage = int(binance_leverage)
                except (TypeError, ValueError):
                    binance_leverage = 0
                if binance_leverage >= 1:
                    display_leverage = binance_leverage
                else:
                    # Position dict had 0/missing (e.g. wrong row in hedge mode); get from Binance using non-zero position
                    try:
                        current_lev = position_client.get_current_leverage(symbol)
                        if current_lev and current_lev >= 1:
                            display_leverage = current_lev
                        elif strategy_match:
                            display_leverage = strategy_match.leverage
                        else:
                            display_leverage = 1
                    except Exception:
                        display_leverage = strategy_match.leverage if strategy_match else 1
                # initial_margin: from Binance or compute notional/leverage when API omits it (e.g. positionRisk v2)
                raw_initial_margin = position_data.get("initialMargin")
                initial_margin_val = None
                if raw_initial_margin is not None:
                    try:
                        initial_margin_val = float(raw_initial_margin)
                    except (TypeError, ValueError):
                        pass
                if (initial_margin_val is None or initial_margin_val <= 0) and display_leverage >= 1:
                    try:
                        notional = abs(float(position_data["positionAmt"])) * float(position_data["markPrice"])
                        if notional > 0:
                            initial_margin_val = notional / display_leverage
                    except (TypeError, ValueError, KeyError):
                        pass
                if initial_margin_val is None or initial_margin_val < 0:
                    initial_margin_val = 0.0
                # Owner attribution: strategy > manual > external (None)
                if strategy_match:
                    out_strategy_id = strategy_match.id
                    out_strategy_name = strategy_match.name
                    out_account_id = getattr(strategy_match, "account_id", None) or account_id_for_client
                elif manual_attribution:
                    out_strategy_id = f"manual_{manual_attribution.id}"
                    out_strategy_name = "Manual Trade"
                    out_account_id = (manual_attribution.account_id or account_id_for_client) or "default"
                else:
                    out_strategy_id = f"external_{position_side}"
                    out_strategy_name = "External"
                    out_account_id = account_id_for_client
                max_peak: Optional[float] = None
                if mark_price_manager and out_strategy_id:
                    max_peak = mark_price_manager.get_max_unrealized_pnl(symbol, out_strategy_id)
                open_positions.append(PositionSummary(
                    symbol=symbol,
                    position_size=binance_position_size,
                    entry_price=position_data["entryPrice"],
                    current_price=position_data["markPrice"],
                    position_side=position_side,
                    unrealized_pnl=position_data["unRealizedProfit"],
                    max_unrealized_pnl=max_peak,
                    leverage=display_leverage,
                    strategy_id=out_strategy_id,
                    strategy_name=out_strategy_name,
                    account_id=out_account_id,
                    liquidation_price=position_data.get("liquidationPrice"),
                    initial_margin=initial_margin_val,
                    margin_type=_normalize_margin_type(position_data.get("marginType")),
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
    db_service: DatabaseService = Depends(get_database_service),
    account_service: AccountService = Depends(get_account_service),
) -> List[SymbolPnL]:
    """Get PnL overview for all symbols with trades.

    Also checks Binance for positions that might not have corresponding trades
    (e.g., manually opened positions). When no account_id filter is set, fetches
    positions from all known accounts so symbols like BTCUSDT (no strategy) appear.
    Supports (symbol, account_id) so the same symbol on multiple accounts (e.g. live + paper) both appear.
    """
    from app.core.paper_binance_client import PaperBinanceClient

    strategies = runner.list_strategies()
    symbols = set()
    symbol_to_account: dict[str, str] = {}
    symbol_account_pairs: set[tuple[str, str]] = set()

    for strategy in strategies:
        if account_id and ((strategy.account_id or "default").strip().lower() != (account_id or "").strip().lower()):
            continue
        trades = runner.get_trades(strategy.id)
        if trades:
            symbols.add(strategy.symbol)
            acc = (strategy.account_id or "default").strip().lower()
            if strategy.symbol not in symbol_to_account:
                symbol_to_account[strategy.symbol] = acc
            symbol_account_pairs.add((strategy.symbol, acc))

    if account_id:
        account_ids_to_fetch = [account_id.strip().lower()]
    else:
        account_ids_to_fetch = list(
            {s.account_id or "default" for s in strategies}
            | set(client_manager.list_accounts().keys())
        )
        try:
            user_accounts = db_service.get_user_accounts(current_user.id)
            for a in user_accounts:
                if a and getattr(a, "account_id", None):
                    aid = (a.account_id or "").strip().lower()
                    if aid:
                        account_ids_to_fetch.append(aid)
        except Exception as exc:
            logger.debug(f"Could not get user accounts from DB: {exc}")
        account_ids_to_fetch = list(dict.fromkeys(account_ids_to_fetch))
        if not account_ids_to_fetch:
            account_ids_to_fetch = ["default"]

    for acc_id in account_ids_to_fetch:
        position_client = client_manager.get_client(acc_id) or (client if acc_id == "default" else None)
        if position_client is None:
            try:
                config = account_service.get_account(current_user.id, acc_id)
                if config:
                    client_manager.add_client(acc_id, config)
                    position_client = client_manager.get_client(acc_id)
            except Exception as exc:
                logger.debug(f"Could not load client for account {acc_id}: {exc}")
        if position_client is None:
            continue
        try:
            if isinstance(position_client, PaperBinanceClient):
                all_binance_positions = position_client.futures_position_information()
            else:
                rest = position_client._ensure()
                all_binance_positions = rest.futures_position_information()
            for pos in all_binance_positions or []:
                position_amt = float(pos.get("positionAmt", 0))
                if abs(position_amt) > 0:
                    sym = (pos.get("symbol") or "").strip().upper()
                    if sym:
                        symbols.add(sym)
                        symbol_account_pairs.add((sym, acc_id))
                        if sym not in symbol_to_account:
                            symbol_to_account[sym] = acc_id
                        logger.debug(f"Found position for {sym} on account {acc_id}")
        except Exception as exc:
            logger.debug(f"Could not fetch positions for account {acc_id}: {exc}")

    if account_id:
        for sym in symbols:
            symbol_account_pairs.add((sym, account_id.strip().lower()))
    elif not symbol_account_pairs and symbols:
        for sym in symbols:
            symbol_account_pairs.add((sym, symbol_to_account.get(sym, "default")))

    pnl_by_symbol: dict[str, list[SymbolPnL]] = {}
    for (sym, acc_id) in sorted(symbol_account_pairs):
        try:
            pnl = get_symbol_pnl(
                sym,
                account_id=acc_id,
                start_date=start_date,
                end_date=end_date,
                current_user=current_user,
                runner=runner,
                client=client,
                client_manager=client_manager,
                db_service=db_service,
                mark_price_manager=getattr(runner, "mark_price_stream_manager", None),
            )
            if sym not in pnl_by_symbol:
                pnl_by_symbol[sym] = []
            pnl_by_symbol[sym].append(pnl)
        except Exception as exc:
            logger.warning(f"Failed to get PnL for {sym} account {acc_id}: {exc}")

    pnl_list = []
    for symbol in sorted(pnl_by_symbol.keys()):
        rows = pnl_by_symbol[symbol]
        if len(rows) == 1:
            pnl_list.append(rows[0])
            continue
        all_open = []
        all_closed = []
        seen_trade_ids = set()
        total_realized = sum(r.total_realized_pnl for r in rows)
        total_unrealized = sum(r.total_unrealized_pnl for r in rows)
        total_trade_fees_merged = sum((getattr(r, "total_trade_fees") or 0) for r in rows)
        total_funding_fees_merged = sum((getattr(r, "total_funding_fees") or 0) for r in rows)
        for r in rows:
            all_open.extend(r.open_positions)
            for t in r.closed_trades or []:
                tid = getattr(t, "id", None) or getattr(t, "trade_id", id(t))
                if tid not in seen_trade_ids:
                    seen_trade_ids.add(tid)
                    all_closed.append(t)
        winning = sum(1 for t in all_closed if getattr(t, "realized_pnl", 0) > 0)
        losing = sum(1 for t in all_closed if getattr(t, "realized_pnl", 0) < 0)
        n_closed = len(all_closed)
        win_rate = (winning / n_closed * 100) if n_closed else 0.0
        pnl_list.append(SymbolPnL(
            symbol=symbol,
            total_realized_pnl=round(total_realized, 4),
            total_unrealized_pnl=round(total_unrealized, 4),
            total_pnl=round(total_realized + total_unrealized, 4),
            open_positions=all_open,
            closed_trades=all_closed,
            total_trades=n_closed,
            completed_trades=n_closed,
            win_rate=round(win_rate, 2),
            winning_trades=winning,
            losing_trades=losing,
            total_trade_fees=round(total_trade_fees_merged, 4) if total_trade_fees_merged > 0 else None,
            total_funding_fees=round(total_funding_fees_merged, 4) if total_funding_fees_merged > 0 else None,
        ))
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

