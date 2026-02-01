"""API routes for trading reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor, as_completed

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api.deps import get_strategy_runner, get_binance_client, get_current_user, get_database_service
from app.models.report import StrategyReport, TradeReport, TradingReport
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary
from app.models.db_models import User
from app.services.strategy_runner import StrategyRunner
from app.services.trade_service import TradeService
from app.services.database_service import DatabaseService
from app.core.my_binance_client import BinanceClient
from app.core.redis_storage import RedisStorage
from app.core.config import get_settings


router = APIRouter(prefix="/api/reports", tags=["reports"])


def _fetch_klines_for_strategy(
    client: BinanceClient,
    strategy: StrategySummary,
    chart_start: datetime,
    chart_end: datetime
) -> Tuple[str, Optional[List]]:
    """Fetch klines for a single strategy (helper for parallelization).
    
    Returns:
        Tuple of (strategy_id, klines_data or None)
    """
    try:
        # Get strategy's kline interval (default to 1m if not available)
        strategy_interval = '1m'  # Default
        if hasattr(strategy, 'params') and strategy.params:
            if isinstance(strategy.params, dict):
                strategy_interval = strategy.params.get('kline_interval', '1m')
            elif hasattr(strategy.params, 'kline_interval'):
                strategy_interval = getattr(strategy.params, 'kline_interval', '1m')
            elif hasattr(strategy.params, 'get'):
                strategy_interval = strategy.params.get('kline_interval', '1m')
        if not isinstance(strategy_interval, str):
            strategy_interval = '1m'
        
        # Calculate time range in milliseconds
        start_timestamp = int(chart_start.timestamp() * 1000)
        end_timestamp = int(chart_end.timestamp() * 1000)
        duration_seconds = (end_timestamp - start_timestamp) / 1000
        
        # Map interval to seconds
        interval_seconds_map = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200, "1d": 86400
        }
        interval_seconds = interval_seconds_map.get(strategy_interval, 60)
        estimated_candles = int(duration_seconds / interval_seconds) + 200
        
        # Fetch klines using Binance client
        rest = client._ensure()
        limit = min(estimated_candles, 1500)
        
        try:
            # Prefer timestamp-based approach (unambiguous UTC)
            klines = rest.futures_klines(
                symbol=strategy.symbol,
                interval=strategy_interval,
                limit=limit,
                startTime=start_timestamp,
                endTime=end_timestamp
            )
            if klines:
                # Filter by time range to ensure accuracy
                klines_data = [
                    k for k in klines
                    if start_timestamp <= int(k[0]) <= end_timestamp
                ]
                return (strategy.id, klines_data)
            return (strategy.id, None)
        except (TypeError, AttributeError) as timestamp_error:
            # Fallback: try futures_historical_klines with string format
            if hasattr(rest, 'futures_historical_klines'):
                start_str = chart_start.strftime("%d %b %Y %H:%M:%S")
                end_str = chart_end.strftime("%d %b %Y %H:%M:%S")
                klines = rest.futures_historical_klines(
                    symbol=strategy.symbol,
                    interval=strategy_interval,
                    start_str=start_str,
                    end_str=end_str
                )
                return (strategy.id, klines if klines else None)
            else:
                # Last fallback: fetch recent and filter
                klines = rest.futures_klines(
                    symbol=strategy.symbol,
                    interval=strategy_interval,
                    limit=limit
                )
                if klines:
                    klines_data = [
                        k for k in klines
                        if start_timestamp <= int(k[0]) <= end_timestamp
                    ]
                    return (strategy.id, klines_data)
                return (strategy.id, None)
    except Exception as e:
        logger.warning(f"Failed to fetch klines for strategy {strategy.id}: {e}")
        return (strategy.id, None)


def _get_completed_trades_from_database(
    db_service: DatabaseService,
    user_id: UUID,
    strategy_uuid: UUID,
    strategy_id: str,
    start_datetime: Optional[datetime] = None,
    end_datetime: Optional[datetime] = None,
) -> List[TradeReport]:
    """Get completed trades from CompletedTrade table (pre-computed, ON-WRITE).
    
    This is much faster than on-demand matching because trades are pre-computed
    when positions close.
    
    Args:
        db_service: Database service
        user_id: User UUID
        strategy_uuid: Strategy UUID (from database)
        strategy_id: Strategy ID string (for TradeReport)
        start_datetime: Optional start date filter
        end_datetime: Optional end date filter
    
    Returns:
        List of TradeReport objects
    """
    try:
        from app.models.db_models import CompletedTrade, Strategy, Account
        
        # Check if strategy is using paper trading account
        # If so, include paper trades; otherwise exclude them
        strategy = db_service.db.query(Strategy).filter(Strategy.id == strategy_uuid).first()
        include_paper_trades = False
        
        if strategy and strategy.account_id:
            account = db_service.db.query(Account).filter(Account.id == strategy.account_id).first()
            if account and account.paper_trading:
                include_paper_trades = True
        
        # Build query
        query = db_service.db.query(CompletedTrade).filter(
            CompletedTrade.user_id == user_id,
            CompletedTrade.strategy_id == strategy_uuid,
        )
        
        # Filter paper trades based on strategy's account type
        if include_paper_trades:
            # Include only paper trades for paper trading strategies
            query = query.filter(CompletedTrade.paper_trading == True)
        else:
            # Exclude paper trades for live trading strategies
            query = query.filter(CompletedTrade.paper_trading == False)
        
        # Apply date filters
        if start_datetime:
            query = query.filter(CompletedTrade.exit_time >= start_datetime)
        if end_datetime:
            query = query.filter(CompletedTrade.exit_time <= end_datetime)
        
        # Order by exit time (most recent first)
        query = query.order_by(CompletedTrade.exit_time.desc())
        
        # Execute query
        completed_trades = query.all()
        
        # Convert to TradeReport
        trade_reports = []
        for ct in completed_trades:
            trade_report = TradeReport(
                trade_id=str(ct.entry_order_id),  # Use entry_order_id as trade_id
                strategy_id=strategy_id,
                symbol=ct.symbol,
                side=ct.side,  # "LONG" or "SHORT"
                entry_time=ct.entry_time,
                entry_price=float(ct.entry_price),
                exit_time=ct.exit_time,
                exit_price=float(ct.exit_price),
                quantity=float(ct.quantity),
                leverage=ct.leverage or 1,
                fee_paid=float(ct.fee_paid),
                funding_fee=float(ct.funding_fee),
                pnl_usd=float(ct.pnl_usd),
                pnl_pct=float(ct.pnl_pct),
                exit_reason=ct.exit_reason,
                initial_margin=float(ct.initial_margin) if ct.initial_margin else None,
                margin_type=ct.margin_type,
                notional_value=float(ct.notional_value) if ct.notional_value else None,
                entry_order_id=ct.entry_order_id,
                exit_order_id=ct.exit_order_id,
            )
            trade_reports.append(trade_report)
        
        logger.info(
            f"_get_completed_trades_from_database: Found {len(trade_reports)} completed trades "
            f"for strategy {strategy_id} (UUID {strategy_uuid})"
        )
        return trade_reports
        
    except Exception as e:
        logger.warning(
            f"Failed to get completed trades from database for strategy {strategy_id}: {e}",
            exc_info=True
        )
        return []


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
    
    # Log trade details for debugging
    logger.info(f"_match_trades_to_completed_positions: Processing {len(trades)} trades for strategy {strategy_id}")
    for i, trade in enumerate(trades):
        logger.debug(f"  Trade {i+1}: order_id={trade.order_id}, side={trade.side}, qty={trade.executed_qty}, price={trade.avg_price or trade.price}, timestamp={order_id_to_timestamp.get(trade.order_id)}")
    
    sorted_trades = sorted(trades, key=lambda t: order_id_to_timestamp.get(t.order_id, datetime.min.replace(tzinfo=timezone.utc)))
    logger.debug(f"_match_trades_to_completed_positions: Sorted {len(sorted_trades)} trades by timestamp")
    
    for trade in sorted_trades:
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
                    
                    # Get additional Binance parameters from entry and exit orders
                    entry_order = order_id_to_order.get(short_entry_order_id)
                    exit_order = order_id_to_order.get(trade.order_id)
                    
                    # Determine exit reason from exit order (preferred) or fallback to entry
                    exit_reason = None
                    if exit_order and hasattr(exit_order, 'exit_reason') and exit_order.exit_reason:
                        exit_reason = exit_order.exit_reason
                    elif exit_order and exit_order.order_type:
                        # Check if it's a Binance native TP/SL order
                        if exit_order.order_type == "TAKE_PROFIT_MARKET":
                            exit_reason = "TP"
                        elif exit_order.order_type == "STOP_MARKET":
                            exit_reason = "SL"
                    # Fallback to stored exit_reason in entry (legacy) or "MANUAL"
                    if not exit_reason:
                        exit_reason = short_exit_reason or "MANUAL"
                    
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
                        funding_fee=0.0,  # Will be updated later when funding fees are fetched
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
                    logger.debug(f"  After closing SHORT, opening LONG: qty={remaining_qty}, price={entry_price}")
            else:
                # Opening or adding to LONG position
                position_queue.append((quantity, entry_price, trade_time, trade.order_id, "LONG", None, actual_fee, trade_leverage))
                logger.debug(f"  Opening LONG position: qty={quantity}, price={entry_price}, order_id={trade.order_id}")
        
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
                    
                    # Get additional Binance parameters from entry and exit orders
                    entry_order = order_id_to_order.get(long_entry_order_id)
                    exit_order = order_id_to_order.get(trade.order_id)
                    
                    # Determine exit reason from exit order (preferred) or fallback to entry
                    exit_reason = None
                    if exit_order and hasattr(exit_order, 'exit_reason') and exit_order.exit_reason:
                        exit_reason = exit_order.exit_reason
                    elif exit_order and exit_order.order_type:
                        # Check if it's a Binance native TP/SL order
                        if exit_order.order_type == "TAKE_PROFIT_MARKET":
                            exit_reason = "TP"
                        elif exit_order.order_type == "STOP_MARKET":
                            exit_reason = "SL"
                    # Fallback to stored exit_reason in entry (legacy) or "MANUAL"
                    if not exit_reason:
                        exit_reason = long_exit_reason or "MANUAL"
                    
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
                        funding_fee=0.0,  # Will be updated later when funding fees are fetched
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
                    logger.debug(f"  After closing LONG, opening SHORT: qty={remaining_qty}, price={entry_price}")
            else:
                # Opening or adding to SHORT position
                position_queue.append((quantity, entry_price, trade_time, trade.order_id, "SHORT", None, actual_fee, trade_leverage))
                logger.debug(f"  Opening SHORT position: qty={quantity}, price={entry_price}, order_id={trade.order_id}")
    
    logger.info(f"_match_trades_to_completed_positions: Created {len(completed_trades)} completed trades from {len(trades)} raw trades")
    if position_queue:
        logger.warning(f"_match_trades_to_completed_positions: {len(position_queue)} open positions remain in queue (not shown as completed trades)")
        for pos in position_queue:
            logger.debug(f"  Open position: side={pos[4]}, qty={pos[0]}, price={pos[1]}, order_id={pos[3]}")
    
    return completed_trades


@router.get("/", response_model=TradingReport)
def get_trading_report(
    strategy_id: Optional[str] = Query(default=None, description="Filter by strategy ID"),
    strategy_name: Optional[str] = Query(default=None, description="Filter by strategy name (partial match)"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    start_date: Optional[str] = Query(default=None, description="Filter from date/time (ISO format)"),
    end_date: Optional[str] = Query(default=None, description="Filter to date/time (ISO format)"),
    account_id: Optional[str] = Query(default=None, description="Filter by Binance account ID"),
    current_user: Optional[User] = Depends(get_current_user),
    runner: Optional[StrategyRunner] = Depends(get_strategy_runner),
    client: Optional[BinanceClient] = Depends(get_binance_client),
    db_service: Optional[DatabaseService] = Depends(get_database_service),
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
        
        # Normalize Query objects to their actual values (handles direct function calls in tests)
        # When called directly, Query(default=None) becomes Query(None) which is truthy
        # Check if account_id is a Query object and extract its default value
        if account_id is not None and not isinstance(account_id, str):
            # Likely a Query object - extract the default value
            if hasattr(account_id, 'default'):
                account_id = account_id.default
            elif 'Query' in str(type(account_id)):
                account_id = None  # Query object with no accessible default - treat as None
            else:
                account_id = None  # Not a string and not a Query - treat as None
        
        # Get all strategies
        all_strategies = runner.list_strategies()
        logger.debug(f"Reports endpoint: Found {len(all_strategies)} total strategies in memory")
        
        # Apply filters
        filtered_strategies = []
        for strategy in all_strategies:
            if strategy_id and strategy.id != strategy_id:
                continue
            if strategy_name and strategy_name.lower() not in strategy.name.lower():
                continue
            if symbol and strategy.symbol.upper() != symbol.upper():
                continue
            # Filter by account_id if provided (only filter if account_id is explicitly set)
            # When account_id is None (not provided), don't filter by account
            if account_id:
                # Handle case where strategy.account_id might be None or missing
                strategy_account_id = getattr(strategy, 'account_id', None) or "default"
                if strategy_account_id != account_id:
                    continue
            filtered_strategies.append(strategy)
        
        # Build strategy reports
        strategy_reports = []
        total_trades_count = 0  # Total completed trades (for consistency with win rate calculation)
        total_winning = 0
        total_losing = 0
        total_profit = 0.0
        total_loss = 0.0
        
        # Batch load trades for all strategies (optimizes N+1 query problem)
        strategy_ids = [s.id for s in filtered_strategies]
        
        # Try to fetch from database first (more reliable for historical data)
        trades_by_strategy: Dict[str, List[OrderResponse]] = {}
        try:
            if current_user and db_service:
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
                
                # Get strategy UUIDs from database
                from app.services.strategy_service import StrategyService
                strategy_service = StrategyService(db_session, redis_storage)
                strategy_uuid_map: Dict[str, str] = {}  # Map strategy_id (string) to UUID
                
                for strategy_id in strategy_ids:
                    db_strategy = strategy_service.db_service.get_strategy(current_user.id, strategy_id)
                    if db_strategy:
                        strategy_uuid_map[strategy_id] = str(db_strategy.id)
                
                if strategy_uuid_map:
                    # Batch fetch trades from database
                    uuid_list = [UUID(uuid_str) for uuid_str in strategy_uuid_map.values()]
                    logger.info(f"Reports: Fetching trades from database for {len(uuid_list)} strategies (UUIDs: {[str(u) for u in uuid_list[:3]]}...)")
                    trades_by_uuid = trade_service.get_trades_batch(
                        user_id=current_user.id,
                        strategy_ids=uuid_list,
                        limit_per_strategy=10000
                    )
                    
                    # Convert UUID keys back to string strategy_id keys
                    for strategy_id, uuid_str in strategy_uuid_map.items():
                        strategy_uuid = UUID(uuid_str)
                        if strategy_uuid in trades_by_uuid:
                            trades_by_strategy[strategy_id] = trades_by_uuid[strategy_uuid]
                            logger.debug(f"Reports: Strategy {strategy_id} (UUID {uuid_str}) has {len(trades_by_uuid[strategy_uuid])} trades from database")
                        else:
                            trades_by_strategy[strategy_id] = []
                            logger.warning(f"Reports: Strategy {strategy_id} (UUID {uuid_str}) has no trades in database result")
                    
                    logger.info(f"Reports: Fetched {sum(len(t) for t in trades_by_strategy.values())} trades from database for {len(trades_by_strategy)} strategies")
                else:
                    logger.warning("Reports: No strategies found in database, falling back to StrategyRunner")
                    trades_by_strategy = runner.get_trades_batch(strategy_ids)
            else:
                # No user authenticated or db_service not available - use StrategyRunner
                logger.debug("Reports: No user authenticated or db_service unavailable, using StrategyRunner")
                trades_by_strategy = runner.get_trades_batch(strategy_ids)
        except Exception as db_exc:
            logger.warning(f"Reports: Failed to fetch trades from database: {db_exc}, falling back to StrategyRunner")
            # Fallback to StrategyRunner method (Redis/in-memory)
            trades_by_strategy = runner.get_trades_batch(strategy_ids)
        
        # Parallel fetch klines for all strategies (optimizes sequential API calls)
        klines_by_strategy: Dict[str, Optional[List]] = {}
        if client and filtered_strategies:
            # Prepare klines fetching tasks
            klines_tasks = []
            for strategy in filtered_strategies:
                # Determine time range for klines
                chart_start = start_datetime or strategy.created_at
                if chart_start and chart_start.tzinfo is None:
                    chart_start = chart_start.replace(tzinfo=timezone.utc)
                
                chart_end = end_datetime or strategy.stopped_at or datetime.now(timezone.utc)
                if chart_end and chart_end.tzinfo is None:
                    chart_end = chart_end.replace(tzinfo=timezone.utc)
                
                if chart_start and chart_end and chart_start < chart_end:
                    klines_tasks.append((strategy, chart_start, chart_end))
            
            # Fetch klines in parallel using ThreadPoolExecutor
            if klines_tasks:
                with ThreadPoolExecutor(max_workers=min(len(klines_tasks), 5)) as executor:
                    future_to_strategy = {
                        executor.submit(_fetch_klines_for_strategy, client, strategy, chart_start, chart_end): strategy
                        for strategy, chart_start, chart_end in klines_tasks
                    }
                    
                    for future in as_completed(future_to_strategy):
                        try:
                            strategy_id, klines_data = future.result()
                            klines_by_strategy[strategy_id] = klines_data
                        except Exception as e:
                            strategy = future_to_strategy[future]
                            logger.warning(f"Error fetching klines for strategy {strategy.id}: {e}")
                            klines_by_strategy[strategy.id] = None
        
        for strategy in filtered_strategies:
            try:
                # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
                # This is much faster than on-demand matching
                completed_trades_list: List[TradeReport] = []
                
                if current_user and db_service:
                    try:
                        # Get strategy UUID from database
                        from app.services.strategy_service import StrategyService
                        settings = get_settings()
                        redis_storage = None
                        if settings.redis_enabled:
                            redis_storage = RedisStorage(
                                redis_url=settings.redis_url,
                                enabled=settings.redis_enabled
                            )
                        strategy_service = StrategyService(db_service.db, redis_storage)
                        db_strategy = strategy_service.db_service.get_strategy(current_user.id, strategy.id)
                        
                        if db_strategy:
                            # Query from CompletedTrade table (pre-computed)
                            completed_trades_list = _get_completed_trades_from_database(
                                db_service=db_service,
                                user_id=current_user.id,
                                strategy_uuid=db_strategy.id,
                                strategy_id=strategy.id,
                                start_datetime=start_datetime,
                                end_datetime=end_datetime,
                            )
                            logger.info(
                                f"Reports: Strategy {strategy.id} has {len(completed_trades_list)} "
                                f"completed trades from CompletedTrade table (pre-computed)"
                            )
                    except Exception as db_exc:
                        logger.warning(
                            f"Reports: Failed to get completed trades from database for strategy {strategy.id}: {db_exc}. "
                            f"Falling back to on-demand matching."
                        )
                
                # ✅ FALLBACK: If no completed trades from database, use on-demand matching
                # This handles cases where:
                # - CompletedTrade table is empty (migration not run, or old data)
                # - Some trades haven't been matched yet (edge cases)
                if not completed_trades_list:
                    # Get trades for this strategy (from batch-loaded data)
                    trades = trades_by_strategy.get(strategy.id, [])
                    logger.info(
                        f"Reports: Strategy {strategy.id} ({strategy.name}) has {len(trades)} raw trades. "
                        f"Using on-demand matching (fallback)."
                    )
                    
                    # Match trades to form completed positions (on-demand)
                    completed_trades_list = _match_trades_to_completed_positions(
                        trades,
                        strategy.id,
                        strategy.name,
                        strategy.symbol,
                        strategy.leverage,
                    )
                    logger.info(
                        f"Reports: Strategy {strategy.id} has {len(completed_trades_list)} "
                        f"completed trades after on-demand matching"
                    )
                
                # Note: Date filtering is already applied in _get_completed_trades_from_database
                # For on-demand matching, we apply date filters here
                if not completed_trades_list or (start_datetime or end_datetime):
                    # Only apply date filters if we used on-demand matching (fallback)
                    # Database query already filters by date
                    if start_datetime or end_datetime:
                        filtered_trades = []
                        for trade in completed_trades_list:
                            trade_time = trade.entry_time or trade.exit_time
                            if trade_time:
                                # Ensure trade_time is timezone-aware for comparison
                                if trade_time.tzinfo is None:
                                    trade_time = trade_time.replace(tzinfo=timezone.utc)
                                
                                if start_datetime and trade_time < start_datetime:
                                    continue
                                if end_datetime and trade_time > end_datetime:
                                    continue
                            filtered_trades.append(trade)
                        logger.info(
                            f"Reports: Strategy {strategy.id} has {len(filtered_trades)} trades "
                            f"after date filtering (from {len(completed_trades_list)} completed trades)"
                        )
                        completed_trades_list = filtered_trades
                
                # Fetch funding fees for this strategy if client is available
                funding_fees_by_trade: Dict[str, float] = {}  # Map trade_id to total funding fee
                total_funding_fee = 0.0
                
                if client and completed_trades_list:
                    try:
                        # Determine time range for funding fees
                        earliest_entry = min(
                            (t.entry_time for t in completed_trades_list if t.entry_time),
                            default=None
                        )
                        latest_exit = max(
                            (t.exit_time for t in completed_trades_list if t.exit_time),
                            default=None
                        )
                        
                        if earliest_entry and latest_exit:
                            # Convert to milliseconds for Binance API
                            start_time_ms = int(earliest_entry.timestamp() * 1000)
                            end_time_ms = int(latest_exit.timestamp() * 1000)
                            
                            # Fetch funding fees from Binance
                            funding_fees = client.get_funding_fees(
                                symbol=strategy.symbol,
                                start_time=start_time_ms,
                                end_time=end_time_ms,
                                limit=1000
                            )
                            
                            # Match funding fees to trades based on entry/exit times
                            for trade in completed_trades_list:
                                trade_funding_fee = 0.0
                                if trade.entry_time and trade.exit_time:
                                    entry_ms = int(trade.entry_time.timestamp() * 1000)
                                    exit_ms = int(trade.exit_time.timestamp() * 1000)
                                    
                                    # Sum funding fees that occurred during this trade's holding period
                                    for fee_record in funding_fees:
                                        fee_time = fee_record.get("time", 0)
                                        # Funding fees occur every 8 hours, check if within trade period
                                        # Include fees that occurred during the position holding period
                                        # Use <= for entry to include funding fees at entry time
                                        if entry_ms <= fee_time <= exit_ms:
                                            income = float(fee_record.get("income", 0))
                                            # Income is negative when paid, positive when received
                                            # For reporting, we want the absolute value paid (negative income = fee paid)
                                            if income < 0:
                                                trade_funding_fee += abs(income)
                                
                                # Update trade report with funding fee
                                trade.funding_fee = round(trade_funding_fee, 4)
                                total_funding_fee += trade_funding_fee
                    except Exception as fee_exc:
                        logger.warning(f"Failed to fetch funding fees for strategy {strategy.id}: {fee_exc}")
                
                # Calculate strategy statistics (single pass for efficiency)
                wins = 0
                losses = 0
                total_profit_usd = 0.0
                total_loss_usd = 0.0
                total_fee = 0.0
                
                for trade in completed_trades_list:
                    pnl = trade.pnl_usd
                    if pnl > 0:
                        wins += 1
                        total_profit_usd += pnl
                    elif pnl < 0:
                        losses += 1
                        total_loss_usd += abs(pnl)
                    
                    # Sum trading fees
                    total_fee += trade.fee_paid
                
                win_rate = ((wins / len(completed_trades_list)) * 100) if completed_trades_list else 0.0
                # Calculate net_pnl from already computed profit and loss
                net_pnl = total_profit_usd - total_loss_usd
                
                # Determine stopped_at
                stopped_at = None
                if strategy.status.value != "running":
                    # If stopped, try to get last trade time or use current time
                    if completed_trades_list:
                        stopped_at = max((t.exit_time for t in completed_trades_list if t.exit_time), 
                                       default=strategy.created_at)
                    else:
                        stopped_at = strategy.created_at
                
                # Ensure stopped_at is timezone-aware (UTC)
                if stopped_at and stopped_at.tzinfo is None:
                    stopped_at = stopped_at.replace(tzinfo=timezone.utc)
                
                # Get klines from parallel-fetched data (fetched earlier for all strategies)
                klines_data = klines_by_strategy.get(strategy.id)
                
                # Calculate indicators for charting if klines are available
                indicators_data = None
                if klines_data:
                    try:
                        from app.strategies.indicators import calculate_ema, calculate_rsi
                        
                        # Extract closing prices
                        closing_prices = [float(k[4]) for k in klines_data]
                        
                        # Get strategy type (handle both enum and string)
                        strategy_type_str = None
                        if hasattr(strategy, 'strategy_type'):
                            if hasattr(strategy.strategy_type, 'value'):
                                strategy_type_str = strategy.strategy_type.value
                            else:
                                strategy_type_str = str(strategy.strategy_type)
                        
                        if strategy_type_str == "scalping":
                            # Scalping strategy: Calculate EMA fast and slow
                            fast_period = 8  # default
                            slow_period = 21  # default
                            if hasattr(strategy, 'params') and strategy.params:
                                if isinstance(strategy.params, dict):
                                    fast_period = int(strategy.params.get('ema_fast', 8))
                                    slow_period = int(strategy.params.get('ema_slow', 21))
                                elif hasattr(strategy.params, 'ema_fast'):
                                    fast_period = int(getattr(strategy.params, 'ema_fast', 8))
                                    slow_period = int(getattr(strategy.params, 'ema_slow', 21))
                            
                            # Calculate EMA fast and slow
                            ema_fast_values = []
                            ema_slow_values = []
                            
                            for i in range(len(closing_prices)):
                                # EMA fast
                                prices_up_to_i = closing_prices[:i+1]
                                ema_fast = calculate_ema(prices_up_to_i, fast_period) if len(prices_up_to_i) >= fast_period else None
                                ema_fast_values.append(ema_fast)
                                
                                # EMA slow
                                ema_slow = calculate_ema(prices_up_to_i, slow_period) if len(prices_up_to_i) >= slow_period else None
                                ema_slow_values.append(ema_slow)
                            
                            # Create indicators data with timestamps matching klines
                            indicators_data = {
                                "ema_fast": [
                                    {"time": int(k[0]) // 1000, "value": ema_fast_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if ema_fast_values[i] is not None
                                ],
                                "ema_slow": [
                                    {"time": int(k[0]) // 1000, "value": ema_slow_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if ema_slow_values[i] is not None
                                ],
                                "ema_fast_period": fast_period,
                                "ema_slow_period": slow_period
                            }
                        elif strategy_type_str == "range_mean_reversion":
                            # Range mean reversion strategy: Calculate EMA, RSI, and basic range detection
                            # Get parameters from strategy
                            lookback_period = 150
                            ema_fast_period = 20
                            ema_slow_period = 50
                            rsi_period = 14
                            rsi_oversold = 40
                            rsi_overbought = 60
                            buy_zone_pct = 0.2
                            sell_zone_pct = 0.2
                            
                            if hasattr(strategy, 'params') and strategy.params:
                                if isinstance(strategy.params, dict):
                                    lookback_period = int(strategy.params.get('lookback_period', 150))
                                    ema_fast_period = int(strategy.params.get('ema_fast_period', 20))
                                    ema_slow_period = int(strategy.params.get('ema_slow_period', 50))
                                    rsi_period = int(strategy.params.get('rsi_period', 14))
                                    rsi_oversold = float(strategy.params.get('rsi_oversold', 40))
                                    rsi_overbought = float(strategy.params.get('rsi_overbought', 60))
                                    buy_zone_pct = float(strategy.params.get('buy_zone_pct', 0.2))
                                    sell_zone_pct = float(strategy.params.get('sell_zone_pct', 0.2))
                                elif hasattr(strategy.params, 'lookback_period'):
                                    lookback_period = int(getattr(strategy.params, 'lookback_period', 150))
                                    ema_fast_period = int(getattr(strategy.params, 'ema_fast_period', 20))
                                    ema_slow_period = int(getattr(strategy.params, 'ema_slow_period', 50))
                                    rsi_period = int(getattr(strategy.params, 'rsi_period', 14))
                                    rsi_oversold = float(getattr(strategy.params, 'rsi_oversold', 40))
                                    rsi_overbought = float(getattr(strategy.params, 'rsi_overbought', 60))
                                    buy_zone_pct = float(getattr(strategy.params, 'buy_zone_pct', 0.2))
                                    sell_zone_pct = float(getattr(strategy.params, 'sell_zone_pct', 0.2))
                            
                            # Calculate EMA fast and slow
                            ema_fast_values = []
                            ema_slow_values = []
                            for i in range(len(closing_prices)):
                                prices_up_to_i = closing_prices[:i+1]
                                ema_fast = calculate_ema(prices_up_to_i, ema_fast_period) if len(prices_up_to_i) >= ema_fast_period else None
                                ema_slow = calculate_ema(prices_up_to_i, ema_slow_period) if len(prices_up_to_i) >= ema_slow_period else None
                                ema_fast_values.append(ema_fast)
                                ema_slow_values.append(ema_slow)
                            
                            # Calculate RSI
                            rsi_values = []
                            for i in range(len(closing_prices)):
                                prices_up_to_i = closing_prices[:i+1]
                                rsi = calculate_rsi(prices_up_to_i, rsi_period) if len(prices_up_to_i) >= rsi_period + 1 else None
                                rsi_values.append(rsi)
                            
                            # Simple range detection: calculate range for each lookback window
                            range_high_values = []
                            range_low_values = []
                            range_mid_values = []
                            buy_zone_upper_values = []
                            sell_zone_lower_values = []
                            
                            for i in range(len(klines_data)):
                                if i < lookback_period:
                                    range_high_values.append(None)
                                    range_low_values.append(None)
                                    range_mid_values.append(None)
                                    buy_zone_upper_values.append(None)
                                    sell_zone_lower_values.append(None)
                                else:
                                    # Get lookback window
                                    lookback_klines = klines_data[i - lookback_period:i]
                                    highs = [float(k[2]) for k in lookback_klines]
                                    lows = [float(k[3]) for k in lookback_klines]
                                    
                                    range_high = max(highs)
                                    range_low = min(lows)
                                    range_mid = (range_high + range_low) / 2
                                    range_size = range_high - range_low
                                    
                                    range_high_values.append(range_high)
                                    range_low_values.append(range_low)
                                    range_mid_values.append(range_mid)
                                    buy_zone_upper_values.append(range_low + (range_size * buy_zone_pct))
                                    sell_zone_lower_values.append(range_high - (range_size * sell_zone_pct))
                            
                            # Calculate EMA spread percentage
                            ema_spread_pct_values = []
                            for i in range(len(klines_data)):
                                if ema_fast_values[i] is not None and ema_slow_values[i] is not None:
                                    ema_mid = (ema_fast_values[i] + ema_slow_values[i]) / 2
                                    if ema_mid > 0:
                                        spread = abs(ema_fast_values[i] - ema_slow_values[i]) / ema_mid
                                        ema_spread_pct_values.append(spread)
                                    else:
                                        ema_spread_pct_values.append(None)
                                else:
                                    ema_spread_pct_values.append(None)
                            
                            # Create indicators data with timestamps matching klines
                            indicators_data = {
                                "range_high": [
                                    {"time": int(k[0]) // 1000, "value": range_high_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if range_high_values[i] is not None
                                ],
                                "range_low": [
                                    {"time": int(k[0]) // 1000, "value": range_low_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if range_low_values[i] is not None
                                ],
                                "range_mid": [
                                    {"time": int(k[0]) // 1000, "value": range_mid_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if range_mid_values[i] is not None
                                ],
                                "buy_zone_upper": [
                                    {"time": int(k[0]) // 1000, "value": buy_zone_upper_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if buy_zone_upper_values[i] is not None
                                ],
                                "sell_zone_lower": [
                                    {"time": int(k[0]) // 1000, "value": sell_zone_lower_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if sell_zone_lower_values[i] is not None
                                ],
                                "rsi": [
                                    {"time": int(k[0]) // 1000, "value": rsi_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if rsi_values[i] is not None
                                ],
                                "ema_fast": [
                                    {"time": int(k[0]) // 1000, "value": ema_fast_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if ema_fast_values[i] is not None
                                ],
                                "ema_slow": [
                                    {"time": int(k[0]) // 1000, "value": ema_slow_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if ema_slow_values[i] is not None
                                ],
                                "ema_spread_pct": [
                                    {"time": int(k[0]) // 1000, "value": ema_spread_pct_values[i]} 
                                    for i, k in enumerate(klines_data) 
                                    if ema_spread_pct_values[i] is not None
                                ],
                                "rsi_period": rsi_period,
                                "rsi_oversold": rsi_oversold,
                                "rsi_overbought": rsi_overbought,
                                "ema_fast_period": ema_fast_period,
                                "ema_slow_period": ema_slow_period,
                                "buy_zone_pct": buy_zone_pct,
                                "sell_zone_pct": sell_zone_pct,
                            }
                    except Exception as indicators_error:
                        logger.warning(f"Failed to calculate indicators for strategy {strategy.id}: {indicators_error}")
                        indicators_data = None
                
                # Get strategy type (handle both enum and string)
                strategy_type_value = None
                if hasattr(strategy, 'strategy_type'):
                    if hasattr(strategy.strategy_type, 'value'):
                        strategy_type_value = strategy.strategy_type.value
                    else:
                        strategy_type_value = str(strategy.strategy_type)
                
                strategy_report = StrategyReport(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    strategy_type=strategy_type_value,
                    symbol=strategy.symbol,
                    created_at=strategy.created_at,
                    stopped_at=stopped_at,
                    total_trades=len(completed_trades_list),  # Count completed trades to match wins/losses
                    wins=wins,
                    losses=losses,
                    win_rate=round(win_rate, 2),
                    total_profit_usd=round(total_profit_usd, 4),
                    total_loss_usd=round(total_loss_usd, 4),
                    net_pnl=round(net_pnl, 4),
                    total_fee=round(total_fee, 4),
                    total_funding_fee=round(total_funding_fee, 4),
                    trades=completed_trades_list,
                    klines=klines_data,
                    indicators=indicators_data,
                )
                logger.info(f"Reports: Strategy {strategy.id} report created with {len(completed_trades_list)} trades in trades list")
                
                strategy_reports.append(strategy_report)
                # Count completed trades for consistency with win rate and profit/loss calculations
                # This ensures total_trades matches the actual trades used in statistics
                total_trades_count += len(completed_trades_list)
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
        
        # Build filters dict - normalize Query objects here too
        normalized_account_id = account_id
        if hasattr(normalized_account_id, '__class__') and 'Query' in str(type(normalized_account_id)):
            normalized_account_id = getattr(normalized_account_id, 'default', None) if hasattr(normalized_account_id, 'default') else None
        if normalized_account_id is not None and not isinstance(normalized_account_id, str):
            normalized_account_id = None
        
        filters = {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "account_id": normalized_account_id,
        }
        filters = {k: v for k, v in filters.items() if v is not None}
        
        # Log final report summary
        logger.info(f"Reports: Final report summary - {len(strategy_reports)} strategies, {total_trades_count} total completed trades")
        for sr in strategy_reports:
            logger.info(f"Reports: Strategy {sr.strategy_id} ({sr.strategy_name}) has {len(sr.trades)} trades in final report")
        
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

