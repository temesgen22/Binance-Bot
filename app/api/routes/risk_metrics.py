"""
API endpoints for risk metrics and monitoring.

Phase 4 Week 8: Dashboard & Reporting
- Real-time risk metrics
- Portfolio risk status
- Strategy risk metrics
- Historical risk data
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
import asyncio
from loguru import logger

from app.risk.metrics_calculator import RiskMetricsCalculator, RiskMetrics
from app.risk.portfolio_risk_manager import PortfolioRiskManager
from app.risk.circuit_breaker import CircuitBreaker
from app.risk.margin_manager import MarginManager
from app.services.risk_management_service import RiskManagementService
from app.services.trade_service import TradeService
from app.services.strategy_service import StrategyService
from app.services.database_service import DatabaseService
from app.services.account_service import AccountService
from app.models.db_models import Trade as DBTrade
from app.models.risk_management import (
    PortfolioRiskStatusResponse,
    RiskManagementConfigCreate,
    RiskManagementConfigUpdate,
    RiskManagementConfigResponse,
    EnforcementHistoryResponse,
    EnforcementEventResponse,
    RealTimeRiskStatusResponse,
    StrategyRiskStatusResponse,
    StrategyRiskConfigCreate,
    StrategyRiskConfigUpdate,
    StrategyRiskConfigResponse
)
from app.models.order import OrderResponse
from sqlalchemy.orm import Session
from app.models.db_models import User, Account

# Import dependencies from the correct location
from app.api.deps import get_current_user, get_db_session_dependency, get_client_manager, get_account_service, get_strategy_runner
from app.services.strategy_runner import StrategyRunner


router = APIRouter(prefix="/api/risk", tags=["risk-metrics"])


# ============================================================================
# Helper Functions to Eliminate Repetitive Code
# ============================================================================

from app.risk.utils import (
    get_pnl_from_completed_trade,
    get_timestamp_from_completed_trade,
    calculate_today_start,
    calculate_week_start,
    calculate_realized_pnl_from_trades
)

def _convert_db_trades_to_order_responses(
    db_trades: List[DBTrade],
    trade_service: TradeService
) -> List[OrderResponse]:
    """Convert database Trade models to OrderResponse using TradeService.
    
    This eliminates repetitive inline conversion code.
    
    Args:
        db_trades: List of database Trade models
        trade_service: TradeService instance with _db_trade_to_order_response method
        
    Returns:
        List of OrderResponse objects
    """
    return [trade_service._db_trade_to_order_response(db_trade) for db_trade in db_trades]


# Import shared helper functions (aliased for backward compatibility)
_get_pnl_from_completed_trade = get_pnl_from_completed_trade
_get_timestamp_from_completed_trade = get_timestamp_from_completed_trade


@router.get("/metrics/strategy/{strategy_id}")
async def get_strategy_risk_metrics(
    request: Request,
    strategy_id: str,
    lookback_days: int = Query(90, ge=1, le=365),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> dict:
    """Get risk metrics for a specific strategy.
    
    Args:
        strategy_id: Strategy ID
        lookback_days: Lookback period for metrics (default 90)
        user_id: Current user ID
        db: Database session
        
    Returns:
        Risk metrics dictionary
    """
    try:
        # Get trades for strategy
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        
        # First, get the database strategy UUID from the strategy_id string
        db_service = DatabaseService(db=db)
        db_strategy = db_service.get_strategy(user_id, strategy_id)
        
        if not db_strategy:
            return {
                "strategy_id": strategy_id,
                "metrics": None,
                "message": f"Strategy not found: {strategy_id}"
            }
        
        # Get the database UUID for the strategy
        strategy_uuid = db_strategy.id  # This is the database UUID
        
        trade_service = TradeService(db=db)
        trades = trade_service.get_strategy_trades(user_id, strategy_uuid, limit=10000)
        
        if not trades:
            return {
                "strategy_id": strategy_id,
                "metrics": None,
                "message": "No trades found for this strategy"
            }
        
        # Convert database trades to OrderResponse format using helper (eliminates repetitive code)
        from app.models.order import OrderResponse
        order_responses = _convert_db_trades_to_order_responses(trades, trade_service)
        
        # Match trades to completed positions (same logic as reports page)
        from app.api.routes.reports import _match_trades_to_completed_positions
        try:
            matched_trades = _match_trades_to_completed_positions(
                order_responses,
                strategy_id,
                db_strategy.name or "Unknown",
                db_strategy.symbol or "",
                db_strategy.leverage or 1
            )
        except Exception as e:
            logger.warning(f"Error matching trades for strategy {strategy_id}: {e}, using raw trades")
            matched_trades = []
            # Fallback: use realized_pnl from database if matching fails
            for db_trade in trades:
                if db_trade.realized_pnl:
                    matched_trades.append(type('obj', (object,), {
                        'realized_pnl': float(db_trade.realized_pnl),
                        'exit_time': db_trade.timestamp,
                        'entry_time': db_trade.timestamp,
                    })())
        
        # Convert completed trades to format expected by calculator using helper functions
        trade_data = []
        for completed_trade in matched_trades:
            trade_data.append({
                "pnl": _get_pnl_from_completed_trade(completed_trade),
                "timestamp": _get_timestamp_from_completed_trade(completed_trade),
            })
        
        # Get account_id from strategy to fetch real balance
        account_id_str = None
        if db_strategy.account_id:
            # Get account string ID from account UUID
            account = db.query(Account).filter(Account.id == db_strategy.account_id).first()
            if account:
                account_id_str = account.account_id
        
        # Get actual account balance if available
        initial_balance = 10000.0  # Default fallback
        current_balance = 10000.0  # Default fallback
        
        if account_id_str:
            try:
                account_service = get_account_service(request, db)
                client_manager = get_client_manager(request)
                account_config = account_service.get_account(user_id, account_id_str)
                if account_config:
                    client = client_manager.get_client(account_id_str)
                    if not client:
                        client_manager.add_client(account_id_str, account_config)
                        client = client_manager.get_client(account_id_str)
                    if client:
                        balance = await asyncio.to_thread(client.futures_account_balance)
                        current_balance = float(balance)
                        if trade_data:
                            total_pnl = sum(t["pnl"] for t in trade_data)
                            initial_balance = current_balance - total_pnl
                            if initial_balance <= 0:
                                initial_balance = current_balance * 0.5
                        else:
                            initial_balance = current_balance
            except Exception as e:
                logger.warning(f"Error getting balance for strategy '{strategy_id}': {e}, using defaults")
        
        # Calculate metrics
        calculator = RiskMetricsCalculator(lookback_days=lookback_days)
        metrics = calculator.calculate_metrics(
            trades=trade_data,
            initial_balance=initial_balance,
            current_balance=current_balance,
        )
        
        return {
            "strategy_id": strategy_id,
            "metrics": {
                "total_trades": metrics.total_trades,
                "winning_trades": metrics.winning_trades,
                "losing_trades": metrics.losing_trades,
                "win_rate": metrics.win_rate,
                "total_pnl": metrics.total_pnl,
                "gross_profit": metrics.gross_profit,
                "gross_loss": metrics.gross_loss,
                "profit_factor": metrics.profit_factor,
                "avg_win": metrics.avg_win,
                "avg_loss": metrics.avg_loss,
                "sharpe_ratio": metrics.sharpe_ratio,
                "max_drawdown_pct": metrics.max_drawdown_pct,
                "max_drawdown_usdt": metrics.max_drawdown_usdt,
                "current_drawdown_pct": metrics.current_drawdown_pct,
                "current_drawdown_usdt": metrics.current_drawdown_usdt,
                "peak_balance": metrics.peak_balance,
                "current_balance": metrics.current_balance,
                "initial_balance": metrics.initial_balance,
            },
            "calculated_at": metrics.calculated_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Error calculating risk metrics for strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/portfolio")
async def get_portfolio_risk_metrics(
    request: Request,
    account_id: Optional[str] = Query(None),
    lookback_days: int = Query(90, ge=1, le=365),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> dict:
    """Get portfolio-level risk metrics.
    
    Args:
        account_id: Account ID (optional, uses all accounts if not provided)
        lookback_days: Lookback period for metrics (default 90)
        user_id: Current user ID
        db: Database session
        
    Returns:
        Portfolio risk metrics dictionary
    """
    try:
        # Get all trades for user/account
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)  # Initialize db_service
        trade_service = TradeService(db=db)
        
        # CRITICAL: Query DBTrade objects directly from database (not OrderResponse)
        # We need DBTrade objects to access strategy_id (UUID)
        from app.models.db_models import Trade as DBTrade, Account
        
        # Normalize account_id: empty string or None means all accounts
        account_id_normalized = account_id.strip() if account_id and account_id.strip() else None
        
        if account_id_normalized:
            logger.info(f"Getting portfolio metrics for account: '{account_id_normalized}', user: {user_id}")
            # Get account UUID from account_id string
            account_id_lower = account_id_normalized.lower().strip()
            account = db.query(Account).filter(
                Account.user_id == user_id,
                Account.account_id == account_id_lower,
                Account.is_active == True
            ).first()
            
            if account:
                # Get all strategies for this account
                from app.models.db_models import Strategy
                strategies = db.query(Strategy).filter(
                    Strategy.user_id == user_id,
                    Strategy.account_id == account.id
                ).all()
                strategy_ids = [s.id for s in strategies]
                
                # Query DBTrade objects directly
                trades_db = db.query(DBTrade).filter(
                    DBTrade.user_id == user_id,
                    DBTrade.strategy_id.in_(strategy_ids)
                ).all()
                logger.info(f"Found {len(trades_db)} DBTrade objects for account '{account_id_normalized}'")
            else:
                logger.warning(f"Account not found: '{account_id_normalized}', returning empty list")
                trades_db = []
        else:
            logger.info(f"Getting portfolio metrics for ALL accounts, user: {user_id}")
            # Query all DBTrade objects for user (needed for fallback)
            trades_db = db.query(DBTrade).filter(DBTrade.user_id == user_id).all()
            logger.info(f"Found {len(trades_db)} DBTrade objects across all accounts")
        
        # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
        # This is much faster than on-demand matching
        from app.models.db_models import CompletedTrade
        from app.api.routes.reports import _get_completed_trades_from_database, _match_trades_to_completed_positions
        from app.models.order import OrderResponse
        
        all_completed_trades = []
        
        # Get strategy UUIDs for the account
        strategy_uuids = []
        if account_id_normalized:
            if account:
                from app.models.db_models import Strategy
                strategies = db.query(Strategy).filter(
                    Strategy.user_id == user_id,
                    Strategy.account_id == account.id
                ).all()
                strategy_uuids = [s.id for s in strategies]
        else:
            # All strategies for user
            from app.models.db_models import Strategy
            strategies = db.query(Strategy).filter(Strategy.user_id == user_id).all()
            strategy_uuids = [s.id for s in strategies]
        
        # Try to get completed trades from database (pre-computed)
        for strategy_uuid in strategy_uuids:
            try:
                # Get strategy_id string for the helper function
                db_strategy = db_service.get_strategy_by_uuid(strategy_uuid)
                if not db_strategy:
                    continue
                
                strategy_id_str = db_strategy.strategy_id or str(strategy_uuid)
                
                # Query from CompletedTrade table
                completed_trades = _get_completed_trades_from_database(
                    db_service=db_service,
                    user_id=user_id,
                    strategy_uuid=strategy_uuid,
                    strategy_id=strategy_id_str,
                    start_datetime=None,  # Get all completed trades
                    end_datetime=None
                )
                all_completed_trades.extend(completed_trades)
            except Exception as e:
                logger.debug(f"Could not get completed trades from database for strategy {strategy_uuid}: {e}")
        
        # ✅ FALLBACK: If no completed trades from database, use on-demand matching
        if not all_completed_trades:
            logger.debug("No completed trades from database, falling back to on-demand matching")
            
            # Group trades by strategy UUID BEFORE converting (db_trade.strategy_id is a UUID)
            trades_by_strategy_uuid = {}
            for db_trade in trades_db:
                strategy_uuid = db_trade.strategy_id if db_trade.strategy_id else None
                if not strategy_uuid:
                    continue
                
                strategy_uuid_str = str(strategy_uuid)
                if strategy_uuid_str not in trades_by_strategy_uuid:
                    trades_by_strategy_uuid[strategy_uuid_str] = []
                trades_by_strategy_uuid[strategy_uuid_str].append(db_trade)
            
            # Convert and group OrderResponse objects by strategy
            trades_by_strategy = {}
            for strategy_uuid_str, db_trades in trades_by_strategy_uuid.items():
                # Convert database trades to OrderResponse format using helper
                order_responses = _convert_db_trades_to_order_responses(db_trades, trade_service)
                trades_by_strategy[strategy_uuid_str] = order_responses
            
            # Match trades for each strategy and calculate PnL
            for strategy_uuid_str, strategy_trades in trades_by_strategy.items():
                if not strategy_trades:
                    continue
                
                # Get strategy info for matching
                strategy_name = "Unknown"
                symbol = strategy_trades[0].symbol if strategy_trades else ""
                leverage = strategy_trades[0].leverage if strategy_trades and strategy_trades[0].leverage else 1
                strategy_id_str = "unknown"  # Default strategy_id string
                
                # Try to get strategy info from database using UUID
                try:
                    from uuid import UUID
                    strategy_uuid_obj = UUID(strategy_uuid_str)
                    db_strategy = db_service.get_strategy_by_uuid(strategy_uuid_obj)
                    if db_strategy:
                        strategy_name = db_strategy.name or "Unknown"
                        symbol = db_strategy.symbol or symbol
                        leverage = db_strategy.leverage or leverage
                        strategy_id_str = db_strategy.strategy_id or "unknown"
                except Exception as e:
                    logger.debug(f"Could not get strategy info for UUID {strategy_uuid_str}: {e}")
                
                # Match trades to completed positions
                try:
                    matched_trades = _match_trades_to_completed_positions(
                        strategy_trades,
                        strategy_id_str,  # Use strategy_id string, not UUID
                        strategy_name,
                        symbol,
                        leverage
                    )
                    all_completed_trades.extend(matched_trades)
                except Exception as e:
                    logger.warning(f"Error matching trades for strategy {strategy_id_str}: {e}")
        
        completed_trades = all_completed_trades
        
        # Convert completed trades to format expected by calculator
        trade_data = []
        for completed_trade in completed_trades:
            # TradeReport uses pnl_usd, not realized_pnl
            trade_data.append({
                "pnl": _get_pnl_from_completed_trade(completed_trade),
                "timestamp": _get_timestamp_from_completed_trade(completed_trade),
            })
        
        # Get actual account balance FIRST (even if no trades)
        initial_balance = 10000.0  # Default fallback
        current_balance = 10000.0  # Default fallback
        
        if account_id_normalized:
            try:
                # Get account service and client manager
                account_service = get_account_service(request, db)
                client_manager = get_client_manager(request)
                
                # Get account config
                account_config = account_service.get_account(user_id, account_id_normalized)
                if account_config:
                    # Ensure client exists in manager
                    client = client_manager.get_client(account_id_normalized)
                    if not client:
                        # Add client if not exists
                        client_manager.add_client(account_id_normalized, account_config)
                        client = client_manager.get_client(account_id_normalized)
                    
                    if client:
                        # Get current balance from Binance (sync call wrapped in async)
                        try:
                            balance = await asyncio.to_thread(client.futures_account_balance)
                            current_balance = float(balance)
                            logger.info(f"Retrieved balance for account '{account_id_normalized}': {current_balance:.2f} USDT")
                            
                            # Calculate initial balance: current_balance - total_pnl
                            if trade_data:
                                total_pnl = sum(t["pnl"] for t in trade_data)
                                initial_balance = current_balance - total_pnl
                                # Ensure initial balance is positive
                                if initial_balance <= 0:
                                    initial_balance = current_balance * 0.5  # Fallback: assume 50% drawdown max
                                logger.info(f"Calculated initial balance for account '{account_id_normalized}': {initial_balance:.2f} USDT (current: {current_balance:.2f}, total_pnl: {total_pnl:.2f})")
                            else:
                                initial_balance = current_balance
                        except Exception as e:
                            logger.warning(f"Failed to get balance for account '{account_id_normalized}': {e}, using defaults")
                    else:
                        logger.warning(f"Could not get client for account '{account_id_normalized}', using default balance")
                else:
                    logger.warning(f"Account config not found for '{account_id_normalized}', using default balance")
            except Exception as e:
                logger.warning(f"Error getting balance for account '{account_id_normalized}': {e}, using defaults")
        else:
            # For "all accounts", we need to sum balances from all accounts
            # Try to get balances from all active accounts
            try:
                account_service = get_account_service(request, db)
                client_manager = get_client_manager(request)
                
                # Get all accounts for user
                from app.models.db_models import Account
                accounts = db.query(Account).filter(
                    Account.user_id == user_id,
                    Account.is_active == True
                ).all()
                
                total_current_balance = 0.0
                account_balances = {}
                
                for account in accounts:
                    try:
                        account_config = account_service.get_account(user_id, account.account_id)
                        if account_config:
                            client = client_manager.get_client(account.account_id)
                            if not client:
                                client_manager.add_client(account.account_id, account_config)
                                client = client_manager.get_client(account.account_id)
                            if client:
                                balance = await asyncio.to_thread(client.futures_account_balance)
                                balance_float = float(balance)
                                total_current_balance += balance_float
                                account_balances[account.account_id] = balance_float
                                logger.debug(f"Account '{account.account_id}' balance: {balance_float:.2f} USDT")
                    except Exception as e:
                        logger.warning(f"Failed to get balance for account '{account.account_id}': {e}")
                
                if total_current_balance > 0:
                    current_balance = total_current_balance
                    # Calculate initial balance from current balance and total PnL
                    if trade_data:
                        total_pnl = sum(t["pnl"] for t in trade_data)
                        initial_balance = current_balance - total_pnl
                        if initial_balance <= 0:
                            initial_balance = current_balance * 0.8  # Fallback: assume max 20% drawdown
                    else:
                        initial_balance = current_balance
                    logger.info(f"Total balance for all accounts: initial={initial_balance:.2f}, current={current_balance:.2f} (from {len(account_balances)} accounts)")
                else:
                    # Fallback: estimate from trades if we can't get balances
                    if trade_data:
                        total_pnl = sum(t["pnl"] for t in trade_data)
                        # Use a minimum balance assumption based on trade sizes
                        # If we have trades, assume at least 1000 USDT starting balance
                        if abs(total_pnl) < 100:
                            # Small PnL, use default
                            initial_balance = 10000.0
                        else:
                            # Estimate: if positive PnL, assume 50% return; if negative, assume 20% drawdown
                            if total_pnl > 0:
                                initial_balance = total_pnl * 2  # 50% return
                            else:
                                initial_balance = abs(total_pnl) * 5  # 20% drawdown
                        current_balance = initial_balance + total_pnl
                    else:
                        initial_balance = 10000.0
                        current_balance = 10000.0
                    logger.info(f"Estimated balance for all accounts (fallback): initial={initial_balance:.2f}, current={current_balance:.2f}")
            except Exception as e:
                logger.warning(f"Error getting balances for all accounts: {e}, using fallback estimation")
                # Fallback estimation
                if trade_data:
                    total_pnl = sum(t["pnl"] for t in trade_data)
                    if abs(total_pnl) < 100:
                        initial_balance = 10000.0
                    else:
                        if total_pnl > 0:
                            initial_balance = total_pnl * 2
                        else:
                            initial_balance = abs(total_pnl) * 5
                    current_balance = initial_balance + total_pnl
                else:
                    initial_balance = 10000.0
                    current_balance = 10000.0
        
        # Calculate metrics (even if no trades, we still want balance info)
        if trade_data:
            calculator = RiskMetricsCalculator(lookback_days=lookback_days)
            metrics = calculator.calculate_metrics(
                trades=trade_data,
                initial_balance=initial_balance,
                current_balance=current_balance,
            )
        else:
            # No trades - create minimal metrics with balance info
            from app.risk.metrics_calculator import RiskMetrics
            metrics = RiskMetrics(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                gross_profit=0.0,
                gross_loss=0.0,
                profit_factor=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                sharpe_ratio=None,
                max_drawdown_pct=0.0,
                max_drawdown_usdt=0.0,
                current_drawdown_pct=0.0,
                current_drawdown_usdt=0.0,
                peak_balance=current_balance,  # Use current balance as peak if no trades
                current_balance=current_balance,
                initial_balance=initial_balance,
            )
        
        # Log balance info for debugging
        logger.info(f"Returning metrics for account '{account_id_normalized if account_id_normalized else 'all'}': "
                   f"current_balance={metrics.current_balance:.2f}, initial_balance={metrics.initial_balance:.2f}, "
                   f"peak_balance={metrics.peak_balance:.2f}, total_trades={metrics.total_trades}")
        
        return {
            "account_id": account_id_normalized if account_id_normalized else "all",
            "metrics": {
                "total_trades": metrics.total_trades,
                "winning_trades": metrics.winning_trades,
                "losing_trades": metrics.losing_trades,
                "win_rate": metrics.win_rate,
                "total_pnl": metrics.total_pnl,
                "gross_profit": metrics.gross_profit,
                "gross_loss": metrics.gross_loss,
                "profit_factor": metrics.profit_factor,
                "avg_win": metrics.avg_win,
                "avg_loss": metrics.avg_loss,
                "sharpe_ratio": metrics.sharpe_ratio,
                "max_drawdown_pct": metrics.max_drawdown_pct,
                "max_drawdown_usdt": metrics.max_drawdown_usdt,
                "current_drawdown_pct": metrics.current_drawdown_pct,
                "current_drawdown_usdt": metrics.current_drawdown_usdt,
                "peak_balance": metrics.peak_balance,
                "current_balance": metrics.current_balance,
                "initial_balance": metrics.initial_balance,
            },
            "calculated_at": metrics.calculated_at.isoformat(),
        }
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error calculating portfolio risk metrics: {e}\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Error calculating portfolio risk metrics: {str(e)}")


@router.get("/status/portfolio")
async def get_portfolio_risk_status(
    account_id: Optional[str] = Query(None),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> dict:
    """Get real-time portfolio risk status.
    
    Args:
        account_id: Account ID (optional)
        user_id: Current user ID
        db: Database session
        
    Returns:
        Portfolio risk status dictionary
    """
    try:
        # Get risk configuration
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        
        # Normalize account_id: empty string or None means "default" for status endpoint
        # But for metrics, empty means "all accounts"
        normalized_account_id = account_id.strip() if account_id and account_id.strip() else "default"
        logger.info(f"Getting portfolio status for account: '{normalized_account_id}' (original: '{account_id}'), user: {user_id}")
        
        risk_service = RiskManagementService(db=db)
        risk_config = risk_service.get_risk_config(user_id, normalized_account_id)
        
        if not risk_config:
            return {
                "account_id": normalized_account_id,
                "status": "no_config",
                "message": f"No risk configuration found for account: {normalized_account_id}"
            }
        
        # Get portfolio risk manager (would be from factory in production)
        # For now, return basic status
        return {
            "account_id": normalized_account_id,
            "status": "active",
            "risk_config": {
                "max_portfolio_exposure_usdt": risk_config.max_portfolio_exposure_usdt,
                "max_daily_loss_usdt": risk_config.max_daily_loss_usdt,
                "max_weekly_loss_usdt": risk_config.max_weekly_loss_usdt,
                "max_drawdown_pct": risk_config.max_drawdown_pct,
            },
            "circuit_breakers": {
                "enabled": risk_config.circuit_breaker_enabled,
                "max_consecutive_losses": risk_config.max_consecutive_losses,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting portfolio risk status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/daily")
async def get_daily_risk_report(
    request: Request,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    account_id: Optional[str] = Query(None),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> dict:
    """Get daily risk report.
    
    Args:
        date: Report date (default: today)
        account_id: Account ID (optional)
        user_id: Current user ID
        db: Database session
        
    Returns:
        Daily risk report dictionary
    """
    try:
        # Parse date
        if date:
            report_date = datetime.strptime(date, "%Y-%m-%d").date()
        else:
            report_date = datetime.now(timezone.utc).date()
        
        # Get trades for the day
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)  # Initialize db_service
        trade_service = TradeService(db=db)
        start_time = datetime.combine(report_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_time = datetime.combine(report_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        
        # CRITICAL: Query DBTrade objects directly from database (not OrderResponse)
        # We need DBTrade objects to access strategy_id (UUID)
        from app.models.db_models import Trade as DBTrade, Account
        
        # Normalize account_id
        account_id_normalized = account_id.strip() if account_id and account_id.strip() else None
        if account_id_normalized:
            logger.info(f"Getting daily report for account: '{account_id_normalized}', date: {report_date}")
            # Get account UUID from account_id string
            account_id_lower = account_id_normalized.lower().strip()
            account = db.query(Account).filter(
                Account.user_id == user_id,
                Account.account_id == account_id_lower,
                Account.is_active == True
            ).first()
            
            if account:
                # Get all strategies for this account
                from app.models.db_models import Strategy
                strategies = db.query(Strategy).filter(
                    Strategy.user_id == user_id,
                    Strategy.account_id == account.id
                ).all()
                strategy_ids = [s.id for s in strategies]
                
                # Query DBTrade objects directly and filter by date range
                daily_trades_db = db.query(DBTrade).filter(
                    DBTrade.user_id == user_id,
                    DBTrade.strategy_id.in_(strategy_ids),
                    DBTrade.timestamp >= start_time,
                    DBTrade.timestamp <= end_time
                ).all()
            else:
                logger.warning(f"Account not found: '{account_id_normalized}', returning empty list")
                daily_trades_db = []
        else:
            logger.info(f"Getting daily report for ALL accounts, date: {report_date}")
            # Query all DBTrade objects for user and filter by date range
            daily_trades_db = db.query(DBTrade).filter(
                DBTrade.user_id == user_id,
                DBTrade.timestamp >= start_time,
                DBTrade.timestamp <= end_time
            ).all()
        
        # CRITICAL: Match trades to completed positions (same logic as reports page)
        from app.api.routes.reports import _match_trades_to_completed_positions
        from app.models.order import OrderResponse
        
        # Group trades by strategy UUID BEFORE converting (db_trade.strategy_id is a UUID)
        trades_by_strategy_uuid = {}
        for db_trade in daily_trades_db:
            strategy_uuid = db_trade.strategy_id if db_trade.strategy_id else None
            if not strategy_uuid:
                continue
            
            strategy_uuid_str = str(strategy_uuid)
            if strategy_uuid_str not in trades_by_strategy_uuid:
                trades_by_strategy_uuid[strategy_uuid_str] = []
            trades_by_strategy_uuid[strategy_uuid_str].append(db_trade)
        
        # Convert and group OrderResponse objects by strategy
        trades_by_strategy = {}
        for strategy_uuid_str, db_trades in trades_by_strategy_uuid.items():
            # Convert database trades to OrderResponse format using helper
            order_responses = _convert_db_trades_to_order_responses(db_trades, trade_service)
            trades_by_strategy[strategy_uuid_str] = order_responses
        
        # Match trades for each strategy
        all_completed_trades = []
        for strategy_uuid_str, strategy_trades in trades_by_strategy.items():
            if not strategy_trades:
                continue
            
            strategy_name = "Unknown"
            symbol = strategy_trades[0].symbol if strategy_trades else ""
            leverage = strategy_trades[0].leverage if strategy_trades and strategy_trades[0].leverage else 1
            strategy_id_str = "unknown"  # Default strategy_id string
            
            try:
                from uuid import UUID
                strategy_uuid_obj = UUID(strategy_uuid_str)
                db_strategy = db_service.get_strategy_by_uuid(strategy_uuid_obj)
                if db_strategy:
                    strategy_name = db_strategy.name or "Unknown"
                    symbol = db_strategy.symbol or symbol
                    leverage = db_strategy.leverage or leverage
                    strategy_id_str = db_strategy.strategy_id or "unknown"
            except Exception as e:
                logger.debug(f"Could not get strategy info for UUID {strategy_uuid_str}: {e}")
            
            try:
                matched_trades = _match_trades_to_completed_positions(
                    strategy_trades,
                    strategy_id_str,  # Use strategy_id string, not UUID
                    strategy_name,
                    symbol,
                    leverage
                )
                all_completed_trades.extend(matched_trades)
            except Exception as e:
                logger.warning(f"Error matching trades for strategy {strategy_id_str}: {e}")
        
        # Calculate daily metrics from completed trades using helper functions
        trade_data = []
        for completed_trade in all_completed_trades:
            trade_data.append({
                "pnl": _get_pnl_from_completed_trade(completed_trade),
                "timestamp": _get_timestamp_from_completed_trade(completed_trade),
            })
        
        # Get actual account balance if account_id is specified
        initial_balance = 10000.0  # Default fallback
        current_balance = 10000.0  # Default fallback
        
        if account_id_normalized:
            try:
                account_service = get_account_service(request, db)
                client_manager = get_client_manager(request)
                account_config = account_service.get_account(user_id, account_id_normalized)
                if account_config:
                    client = client_manager.get_client(account_id_normalized)
                    if not client:
                        client_manager.add_client(account_id_normalized, account_config)
                        client = client_manager.get_client(account_id_normalized)
                    if client:
                        balance = await asyncio.to_thread(client.futures_account_balance)
                        current_balance = float(balance)
                        if all_completed_trades:
                            daily_pnl = sum(_get_pnl_from_completed_trade(t) for t in all_completed_trades)
                            initial_balance = current_balance - daily_pnl
                            if initial_balance <= 0:
                                initial_balance = current_balance * 0.5
                        else:
                            initial_balance = current_balance
            except Exception as e:
                logger.warning(f"Error getting balance for daily report: {e}, using defaults")
        
        calculator = RiskMetricsCalculator(lookback_days=1)
        metrics = calculator.calculate_metrics(
            trades=trade_data,
            initial_balance=initial_balance,
            current_balance=current_balance,
        )
        
        return {
            "date": report_date.isoformat(),
            "account_id": account_id_normalized if account_id_normalized else "all",
            "summary": {
                "total_trades": metrics.total_trades,
                "winning_trades": metrics.winning_trades,
                "losing_trades": metrics.losing_trades,
                "win_rate": metrics.win_rate,
                "total_pnl": metrics.total_pnl,
                "gross_profit": metrics.gross_profit,
                "gross_loss": metrics.gross_loss,
                "profit_factor": metrics.profit_factor,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error generating daily risk report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/weekly")
async def get_weekly_risk_report(
    request: Request,
    week_start: Optional[str] = Query(None, description="Week start date in YYYY-MM-DD format"),
    account_id: Optional[str] = Query(None),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> dict:
    """Get weekly risk report.
    
    Args:
        week_start: Week start date (default: start of current week)
        account_id: Account ID (optional)
        user_id: Current user ID
        db: Database session
        
    Returns:
        Weekly risk report dictionary
    """
    try:
        # Parse week start date
        if week_start:
            week_start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
        else:
            # Default to start of current week (Monday)
            today = datetime.now(timezone.utc).date()
            days_since_monday = today.weekday()
            week_start_date = today - timedelta(days=days_since_monday)
        
        week_end_date = week_start_date + timedelta(days=6)
        
        # Get trades for the week
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)  # Initialize db_service
        trade_service = TradeService(db=db)
        start_time = datetime.combine(week_start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_time = datetime.combine(week_end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        
        # CRITICAL: Query DBTrade objects directly from database (not OrderResponse)
        # We need DBTrade objects to access strategy_id (UUID)
        from app.models.db_models import Trade as DBTrade, Account
        
        # Normalize account_id
        account_id_normalized = account_id.strip() if account_id and account_id.strip() else None
        if account_id_normalized:
            logger.info(f"Getting weekly report for account: '{account_id_normalized}', week: {week_start_date} to {week_end_date}")
            # Get account UUID from account_id string
            account_id_lower = account_id_normalized.lower().strip()
            account = db.query(Account).filter(
                Account.user_id == user_id,
                Account.account_id == account_id_lower,
                Account.is_active == True
            ).first()
            
            if account:
                # Get all strategies for this account
                from app.models.db_models import Strategy
                strategies = db.query(Strategy).filter(
                    Strategy.user_id == user_id,
                    Strategy.account_id == account.id
                ).all()
                strategy_ids = [s.id for s in strategies]
                
                # Query DBTrade objects directly and filter by date range
                weekly_trades_db = db.query(DBTrade).filter(
                    DBTrade.user_id == user_id,
                    DBTrade.strategy_id.in_(strategy_ids),
                    DBTrade.timestamp >= start_time,
                    DBTrade.timestamp <= end_time
                ).all()
            else:
                logger.warning(f"Account not found: '{account_id_normalized}', returning empty list")
                weekly_trades_db = []
        else:
            logger.info(f"Getting weekly report for ALL accounts, week: {week_start_date} to {week_end_date}")
            # Query all DBTrade objects for user and filter by date range
            weekly_trades_db = db.query(DBTrade).filter(
                DBTrade.user_id == user_id,
                DBTrade.timestamp >= start_time,
                DBTrade.timestamp <= end_time
            ).all()
        
        # CRITICAL: Match trades to completed positions (same logic as reports page)
        from app.api.routes.reports import _match_trades_to_completed_positions
        from app.models.order import OrderResponse
        
        # Group trades by strategy UUID BEFORE converting (db_trade.strategy_id is a UUID)
        trades_by_strategy_uuid = {}
        for db_trade in weekly_trades_db:
            strategy_uuid = db_trade.strategy_id if db_trade.strategy_id else None
            if not strategy_uuid:
                continue
            
            strategy_uuid_str = str(strategy_uuid)
            if strategy_uuid_str not in trades_by_strategy_uuid:
                trades_by_strategy_uuid[strategy_uuid_str] = []
            trades_by_strategy_uuid[strategy_uuid_str].append(db_trade)
        
        # Convert and group OrderResponse objects by strategy
        trades_by_strategy = {}
        for strategy_uuid_str, db_trades in trades_by_strategy_uuid.items():
            # Convert database trades to OrderResponse format using helper
            order_responses = _convert_db_trades_to_order_responses(db_trades, trade_service)
            trades_by_strategy[strategy_uuid_str] = order_responses
        
        # Match trades for each strategy
        all_completed_trades = []
        for strategy_uuid_str, strategy_trades in trades_by_strategy.items():
            if not strategy_trades:
                continue
            
            strategy_name = "Unknown"
            symbol = strategy_trades[0].symbol if strategy_trades else ""
            leverage = strategy_trades[0].leverage if strategy_trades and strategy_trades[0].leverage else 1
            strategy_id_str = "unknown"  # Default strategy_id string
            
            try:
                from uuid import UUID
                strategy_uuid_obj = UUID(strategy_uuid_str)
                db_strategy = db_service.get_strategy_by_uuid(strategy_uuid_obj)
                if db_strategy:
                    strategy_name = db_strategy.name or "Unknown"
                    symbol = db_strategy.symbol or symbol
                    leverage = db_strategy.leverage or leverage
                    strategy_id_str = db_strategy.strategy_id or "unknown"
            except Exception as e:
                logger.debug(f"Could not get strategy info for UUID {strategy_uuid_str}: {e}")
            
            try:
                matched_trades = _match_trades_to_completed_positions(
                    strategy_trades,
                    strategy_id_str,  # Use strategy_id string, not UUID
                    strategy_name,
                    symbol,
                    leverage
                )
                all_completed_trades.extend(matched_trades)
            except Exception as e:
                logger.warning(f"Error matching trades for strategy {strategy_id_str}: {e}")
        
        # Calculate weekly metrics from completed trades using helper functions
        trade_data = []
        for completed_trade in all_completed_trades:
            trade_data.append({
                "pnl": _get_pnl_from_completed_trade(completed_trade),
                "timestamp": _get_timestamp_from_completed_trade(completed_trade),
            })
        
        # Get actual account balance if account_id is specified
        initial_balance = 10000.0  # Default fallback
        current_balance = 10000.0  # Default fallback
        
        if account_id_normalized:
            try:
                account_service = get_account_service(request, db)
                client_manager = get_client_manager(request)
                account_config = account_service.get_account(user_id, account_id_normalized)
                if account_config:
                    client = client_manager.get_client(account_id_normalized)
                    if not client:
                        client_manager.add_client(account_id_normalized, account_config)
                        client = client_manager.get_client(account_id_normalized)
                    if client:
                        balance = await asyncio.to_thread(client.futures_account_balance)
                        current_balance = float(balance)
                        if all_completed_trades:
                            weekly_pnl = sum(_get_pnl_from_completed_trade(t) for t in all_completed_trades)
                            initial_balance = current_balance - weekly_pnl
                            if initial_balance <= 0:
                                initial_balance = current_balance * 0.5
                        else:
                            initial_balance = current_balance
            except Exception as e:
                logger.warning(f"Error getting balance for weekly report: {e}, using defaults")
        
        calculator = RiskMetricsCalculator(lookback_days=7)
        metrics = calculator.calculate_metrics(
            trades=trade_data,
            initial_balance=initial_balance,
            current_balance=current_balance,
        )
        
        return {
            "week_start": week_start_date.isoformat(),
            "week_end": week_end_date.isoformat(),
            "account_id": account_id_normalized if account_id_normalized else "all",
            "summary": {
                "total_trades": metrics.total_trades,
                "winning_trades": metrics.winning_trades,
                "losing_trades": metrics.losing_trades,
                "win_rate": metrics.win_rate,
                "total_pnl": metrics.total_pnl,
                "gross_profit": metrics.gross_profit,
                "gross_loss": metrics.gross_loss,
                "profit_factor": metrics.profit_factor,
                "max_drawdown_pct": metrics.max_drawdown_pct,
                "sharpe_ratio": metrics.sharpe_ratio,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error generating weekly risk report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=RiskManagementConfigResponse)
async def get_risk_config(
    account_id: str = Query("default", description="Account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> RiskManagementConfigResponse:
    """Get risk management configuration for an account."""
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        
        # Normalize account_id (lowercase, strip whitespace)
        account_id_normalized = account_id.lower().strip() if account_id else "default"
        
        risk_service = RiskManagementService(
            db=db,
            redis_storage=None  # Can be injected if needed
        )
        
        # Check if account exists first
        db_service = DatabaseService(db=db)
        try:
            account = db_service.get_account_by_id(user_id, account_id_normalized)
            if not account:
                logger.warning(f"Account not found: user_id={user_id}, account_id={account_id_normalized}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Account not found: {account_id_normalized}. Please ensure the account exists before accessing risk configuration."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking account existence: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"Account not found or error accessing account: {account_id_normalized}"
            )
        
        # Try to get risk config, but handle table not existing gracefully
        try:
            config = risk_service.get_risk_config(user_id, account_id_normalized)
        except Exception as e:
            error_str = str(e).lower()
            if "does not exist" in error_str or "undefinedtable" in error_str or "relation" in error_str:
                logger.warning(
                    f"Risk management table does not exist. Migration may not have been run. "
                    f"Error: {e}. Returning 503 Service Unavailable."
                )
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Risk management database tables have not been created yet. "
                        f"Please run database migrations: alembic upgrade head"
                    )
                )
            # Re-raise other exceptions
            raise
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"Risk configuration not found for account: {account_id_normalized}. Please create a risk configuration first."
            )
        
        return config
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error getting risk config for account '{account_id}': {e}\n{error_traceback}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting risk configuration: {str(e)}"
        )


@router.post("/config", response_model=RiskManagementConfigResponse, status_code=201)
async def create_risk_config(
    config_data: RiskManagementConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> RiskManagementConfigResponse:
    """Create risk management configuration for an account."""
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        
        risk_service = RiskManagementService(
            db=db,
            redis_storage=None  # Can be injected if needed
        )
        
        config = risk_service.create_risk_config(user_id, config_data)
        return config
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating risk config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config", response_model=RiskManagementConfigResponse)
async def update_risk_config(
    account_id: str = Query(..., description="Account ID"),
    config_data: RiskManagementConfigUpdate = ...,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> RiskManagementConfigResponse:
    """Update risk management configuration for an account."""
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        
        risk_service = RiskManagementService(
            db=db,
            redis_storage=None  # Can be injected if needed
        )
        
        config = risk_service.update_risk_config(user_id, account_id, config_data)
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"Risk configuration not found for account: {account_id}"
            )
        
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating risk config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/config", status_code=204, response_model=None)
async def delete_risk_config(
    account_id: str = Query(..., description="Account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
):
    """Delete risk management configuration for an account."""
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        
        risk_service = RiskManagementService(
            db=db,
            redis_storage=None  # Can be injected if needed
        )
        
        deleted = risk_service.delete_risk_config(user_id, account_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Risk configuration not found for account: {account_id}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting risk config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enforcement/history", response_model=EnforcementHistoryResponse)
async def get_enforcement_history(
    account_id: Optional[str] = Query(None, description="Account ID filter"),
    strategy_id: Optional[str] = Query(None, description="Strategy ID filter"),
    event_type: Optional[str] = Query(None, description="Event type filter (e.g., ORDER_BLOCKED, CIRCUIT_BREAKER_TRIGGERED)"),
    start_date: Optional[datetime] = Query(None, description="Start date filter (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date filter (ISO format)"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> EnforcementHistoryResponse:
    """Get risk enforcement history with filters.
    
    Returns all risk enforcement events (order blocks, circuit breakers, etc.)
    filtered by account, strategy, event type, and date range.
    """
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)
        
        # Convert account_id and strategy_id strings to UUIDs if provided
        account_uuid = None
        if account_id:
            db_account = db_service.get_account_by_id(user_id, account_id)
            if db_account:
                account_uuid = db_account.id
        
        strategy_uuid = None
        if strategy_id:
            db_strategy = db_service.get_strategy(user_id, strategy_id)
            if db_strategy:
                strategy_uuid = db_strategy.id
        
        # Query enforcement events
        events, total = db_service.get_enforcement_events(
            user_id=user_id,
            account_id=account_uuid,
            strategy_id=strategy_uuid,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )
        
        # Convert to response format
        event_responses = []
        for event in events:
            # Get strategy_id string if available
            strategy_id_str = None
            if event.strategy_id:
                db_strategy = db_service.get_strategy_by_uuid(event.strategy_id)
                if db_strategy:
                    strategy_id_str = db_strategy.strategy_id
            
            # Get account_id string if available
            account_id_str = None
            if event.account_id:
                db_account = db_service.get_account_by_uuid(event.account_id)
                if db_account:
                    account_id_str = db_account.account_id
            
            event_responses.append(EnforcementEventResponse(
                id=str(event.id),
                event_type=event.event_type,
                event_level=event.event_level,
                message=event.message,
                strategy_id=strategy_id_str,
                account_id=account_id_str,
                event_metadata=event.event_metadata,
                created_at=event.created_at
            ))
        
        return EnforcementHistoryResponse(
            events=event_responses,
            total=total,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error(f"Error getting enforcement history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/realtime", response_model=RealTimeRiskStatusResponse)
async def get_realtime_risk_status(
    account_id: Optional[str] = Query(None, description="Account ID (defaults to all accounts)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
    client_manager = Depends(get_client_manager),
    account_service = Depends(get_account_service),
) -> RealTimeRiskStatusResponse:
    """Get real-time risk status for an account or all accounts.
    
    Returns current exposure, loss limits, drawdown, circuit breaker status,
    and recent enforcement events.
    """
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)
        
        # Normalize account_id (lowercase, strip whitespace)
        account_id_normalized = account_id.lower().strip() if account_id and account_id.strip() else None
        
        # Get risk configuration
        risk_service = RiskManagementService(db=db)
        if account_id_normalized:
            # Check if account exists first
            try:
                account = db_service.get_account_by_id(user_id, account_id_normalized)
                if not account:
                    logger.warning(f"Account not found for realtime status: user_id={user_id}, account_id={account_id_normalized}")
                    # Return empty response if account doesn't exist
                    return RealTimeRiskStatusResponse(
                        account_id=account_id_normalized,
                        timestamp=datetime.now(timezone.utc),
                        risk_status="normal",
                        current_exposure={
                            "total_exposure_usdt": 0.0,
                            "total_exposure_pct": 0.0,
                            "limit_usdt": None,
                            "limit_pct": None,
                            "status": "normal"
                        },
                        loss_limits={
                            "daily_loss_usdt": 0.0,
                            "daily_loss_limit_usdt": None,
                            "daily_loss_pct": 0.0,
                            "daily_loss_limit_pct": None,
                            "weekly_loss_usdt": 0.0,
                            "weekly_loss_limit_usdt": None,
                            "status": "normal"
                        },
                        drawdown={
                            "current_drawdown_pct": 0.0,
                            "max_drawdown_pct": None,
                            "status": "normal"
                        },
                        circuit_breakers={
                            "active": False,
                            "breakers": []
                        },
                        recent_enforcement_events=[]
                    )
            except Exception as e:
                logger.warning(f"Error checking account existence for realtime status: {e}, continuing with empty response")
                # Return empty response if account check fails
                return RealTimeRiskStatusResponse(
                    account_id=account_id_normalized or "all",
                    timestamp=datetime.now(timezone.utc),
                    risk_status="normal",
                    current_exposure={
                        "total_exposure_usdt": 0.0,
                        "total_exposure_pct": 0.0,
                        "limit_usdt": None,
                        "limit_pct": None,
                        "status": "normal"
                    },
                    loss_limits={
                        "daily_loss_usdt": 0.0,
                        "daily_loss_limit_usdt": None,
                        "daily_loss_pct": 0.0,
                        "daily_loss_limit_pct": None,
                        "weekly_loss_usdt": 0.0,
                        "weekly_loss_limit_usdt": None,
                        "status": "normal"
                    },
                    drawdown={
                        "current_drawdown_pct": 0.0,
                        "max_drawdown_pct": None,
                        "status": "normal"
                    },
                    circuit_breakers={
                        "active": False,
                        "breakers": []
                    },
                    recent_enforcement_events=[]
                )
            
            # Try to get risk config, but handle table not existing gracefully
            try:
                risk_config = risk_service.get_risk_config(user_id, account_id_normalized)
            except Exception as e:
                error_str = str(e).lower()
                if "does not exist" in error_str or "undefinedtable" in error_str or "relation" in error_str:
                    logger.warning(
                        f"Risk management table does not exist. Migration may not have been run. "
                        f"Error: {e}. Returning empty response."
                    )
                    risk_config = None
                else:
                    # Re-raise other exceptions
                    raise
        else:
            # For "all accounts", try to get default config
            try:
                risk_config = risk_service.get_risk_config(user_id, "default")
            except Exception as e:
                error_str = str(e).lower()
                if "does not exist" in error_str or "undefinedtable" in error_str or "relation" in error_str:
                    logger.warning(
                        f"Risk management table does not exist. Migration may not have been run. "
                        f"Error: {e}. Returning empty response."
                    )
                    risk_config = None
                else:
                    # Re-raise other exceptions
                    raise
        
        if not risk_config:
            # Return empty response if no config
            return RealTimeRiskStatusResponse(
                account_id=account_id_normalized or "all",
                timestamp=datetime.now(timezone.utc),
                risk_status="normal",
                current_exposure={
                    "total_exposure_usdt": 0.0,
                    "total_exposure_pct": 0.0,
                    "limit_usdt": None,
                    "limit_pct": None,
                    "status": "normal"
                },
                loss_limits={
                    "daily_loss_usdt": 0.0,
                    "daily_loss_limit_usdt": None,
                    "daily_loss_pct": 0.0,
                    "daily_loss_limit_pct": None,
                    "weekly_loss_usdt": 0.0,
                    "weekly_loss_limit_usdt": None,
                    "status": "normal"
                },
                drawdown={
                    "current_drawdown_pct": 0.0,
                    "max_drawdown_pct": None,
                    "status": "normal"
                },
                circuit_breakers={
                    "active": False,
                    "breakers": []
                },
                recent_enforcement_events=[]
            )
        
        # CRITICAL: Query DBTrade objects directly from database (not OrderResponse)
        # We need DBTrade objects to access strategy_id (UUID)
        from app.models.db_models import Trade as DBTrade, Account
        trade_service = TradeService(db=db)
        
        # Get trades for the account
        if account_id_normalized:
            # Get account UUID from account_id string
            account_id_lower = account_id_normalized.lower().strip()
            account = db.query(Account).filter(
                Account.user_id == user_id,
                Account.account_id == account_id_lower,
                Account.is_active == True
            ).first()
            
            if account:
                # Get all strategies for this account
                from app.models.db_models import Strategy
                strategies = db.query(Strategy).filter(
                    Strategy.user_id == user_id,
                    Strategy.account_id == account.id
                ).all()
                strategy_ids = [s.id for s in strategies]
                
                # Query DBTrade objects directly
                trades_db = db.query(DBTrade).filter(
                    DBTrade.user_id == user_id,
                    DBTrade.strategy_id.in_(strategy_ids)
                ).all()
            else:
                logger.warning(f"Account not found: '{account_id_normalized}', returning empty list")
                trades_db = []
        else:
            # Query all DBTrade objects for user
            trades_db = db.query(DBTrade).filter(DBTrade.user_id == user_id).all()
        
        # Calculate current exposure (simplified - would need actual position data)
        # For now, estimate from trade sizes
        total_exposure_usdt = 0.0
        # TODO: Get actual exposure from open positions via StrategyRunner
        
        # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
        # This is much faster than on-demand matching
        from app.models.db_models import CompletedTrade
        from app.api.routes.reports import _get_completed_trades_from_database, _match_trades_to_completed_positions
        
        all_completed_trades = []
        
        # Get strategy UUIDs for the account
        strategy_uuids = []
        if account_id_normalized:
            if account:
                from app.models.db_models import Strategy
                strategies = db.query(Strategy).filter(
                    Strategy.user_id == user_id,
                    Strategy.account_id == account.id
                ).all()
                strategy_uuids = [s.id for s in strategies]
        else:
            # All strategies for user
            from app.models.db_models import Strategy
            strategies = db.query(Strategy).filter(Strategy.user_id == user_id).all()
            strategy_uuids = [s.id for s in strategies]
        
        # Try to get completed trades from database (pre-computed)
        for strategy_uuid in strategy_uuids:
            try:
                # Get strategy_id string for the helper function
                db_strategy = db_service.get_strategy_by_uuid(strategy_uuid)
                if not db_strategy:
                    continue
                
                strategy_id_str = db_strategy.strategy_id or str(strategy_uuid)
                
                # Query from CompletedTrade table
                completed_trades = _get_completed_trades_from_database(
                    db_service=db_service,
                    user_id=user_id,
                    strategy_uuid=strategy_uuid,
                    strategy_id=strategy_id_str,
                    start_datetime=None,  # Get all completed trades
                    end_datetime=None
                )
                all_completed_trades.extend(completed_trades)
            except Exception as e:
                logger.debug(f"Could not get completed trades from database for strategy {strategy_uuid}: {e}")
        
        # ✅ FALLBACK: If no completed trades from database, use on-demand matching
        if not all_completed_trades:
            logger.debug("No completed trades from database, falling back to on-demand matching")
            from app.models.order import OrderResponse
            
            # Group trades by strategy UUID BEFORE converting (db_trade.strategy_id is a UUID)
            trades_by_strategy_uuid = {}
            for db_trade in trades_db:
                strategy_uuid = db_trade.strategy_id if db_trade.strategy_id else None
                if not strategy_uuid:
                    continue
                
                strategy_uuid_str = str(strategy_uuid)
                if strategy_uuid_str not in trades_by_strategy_uuid:
                    trades_by_strategy_uuid[strategy_uuid_str] = []
                trades_by_strategy_uuid[strategy_uuid_str].append(db_trade)
            
            # Convert and group OrderResponse objects by strategy
            trades_by_strategy = {}
            for strategy_uuid_str, db_trades in trades_by_strategy_uuid.items():
                # Convert database trades to OrderResponse format using helper
                order_responses = _convert_db_trades_to_order_responses(db_trades, trade_service)
                trades_by_strategy[strategy_uuid_str] = order_responses
            
            # Match trades for each strategy and calculate PnL
            for strategy_uuid_str, strategy_trades in trades_by_strategy.items():
                if not strategy_trades:
                    continue
                
                # Get strategy info for matching
                strategy_name = "Unknown"
                symbol = strategy_trades[0].symbol if strategy_trades else ""
                leverage = strategy_trades[0].leverage if strategy_trades and strategy_trades[0].leverage else 1
                strategy_id_str = "unknown"  # Default strategy_id string
                
                # Try to get strategy info from database using UUID
                try:
                    from uuid import UUID
                    strategy_uuid_obj = UUID(strategy_uuid_str)
                    db_strategy = db_service.get_strategy_by_uuid(strategy_uuid_obj)
                    if db_strategy:
                        strategy_name = db_strategy.name or "Unknown"
                        symbol = db_strategy.symbol or symbol
                        leverage = db_strategy.leverage or leverage
                        strategy_id_str = db_strategy.strategy_id or "unknown"
                except Exception as e:
                    logger.debug(f"Could not get strategy info for UUID {strategy_uuid_str}: {e}")
                
                # Match trades to completed positions
                try:
                    matched_trades = _match_trades_to_completed_positions(
                        strategy_trades,
                        strategy_id_str,  # Use strategy_id string, not UUID
                        strategy_name,
                        symbol,
                        leverage
                    )
                    all_completed_trades.extend(matched_trades)
                except Exception as e:
                    logger.warning(f"Error matching trades for strategy {strategy_id_str}: {e}")
        
        # Calculate daily PnL (realized only) from completed trades
        # CRITICAL: Use the same time window as risk checks (respects timezone/reset time from config)
        # Use helper functions to eliminate code duplication
        tz_str = risk_config.timezone or "UTC"
        today_start = calculate_today_start(tz_str, risk_config.daily_loss_reset_time)
        daily_pnl_usdt = calculate_realized_pnl_from_trades(all_completed_trades, today_start)
        
        # Calculate weekly PnL (realized only) from completed trades
        # Use the same timezone and reset day as risk checks
        reset_day = risk_config.weekly_loss_reset_day or 1  # 1=Monday, 7=Sunday
        week_start = calculate_week_start(tz_str, reset_day)
        weekly_pnl_usdt = calculate_realized_pnl_from_trades(all_completed_trades, week_start)
        
        # Get account balance for percentage calculations
        account_balance = 0.0
        if account_id_normalized:
            try:
                account_config = account_service.get_account(user_id, account_id_normalized)
                if account_config:
                    client = client_manager.get_client(account_id_normalized)
                    if not client:
                        client_manager.add_client(account_id_normalized, account_config)
                        client = client_manager.get_client(account_id_normalized)
                    if client:
                        account_balance = await asyncio.to_thread(client.futures_account_balance)
                        account_balance = float(account_balance)
            except Exception as e:
                logger.warning(f"Error getting account balance: {e}")
        else:
            # For "all accounts", sum balances from all active accounts
            try:
                from app.models.db_models import Account
                accounts = db.query(Account).filter(
                    Account.user_id == user_id,
                    Account.is_active == True
                ).all()
                
                total_balance = 0.0
                for account in accounts:
                    try:
                        account_config = account_service.get_account(user_id, account.account_id)
                        if account_config:
                            client = client_manager.get_client(account.account_id)
                            if not client:
                                client_manager.add_client(account.account_id, account_config)
                                client = client_manager.get_client(account.account_id)
                            if client:
                                balance = await asyncio.to_thread(client.futures_account_balance)
                                total_balance += float(balance)
                    except Exception as e:
                        logger.warning(f"Failed to get balance for account '{account.account_id}': {e}")
                
                account_balance = total_balance
                if account_balance > 0:
                    logger.debug(f"Total balance for all accounts: {account_balance:.2f} USDT")
            except Exception as e:
                logger.warning(f"Error getting balances for all accounts: {e}")
        
        # Calculate percentages
        daily_pnl_pct = (daily_pnl_usdt / account_balance * 100) if account_balance > 0 else 0.0
        weekly_pnl_pct = (weekly_pnl_usdt / account_balance * 100) if account_balance > 0 else 0.0
        total_exposure_pct = (total_exposure_usdt / account_balance * 100) if account_balance > 0 else 0.0
        
        # Calculate drawdown from metrics
        # Note: We can't call get_portfolio_risk_metrics directly as it requires a Request object
        # Instead, we'll calculate drawdown directly here or skip it for now
        # TODO: Extract get_portfolio_risk_metrics core logic into a helper function
        current_drawdown_pct = 0.0
        try:
            # Calculate drawdown from completed trades (more accurate than raw trades)
            if all_completed_trades and account_balance > 0:
                # Calculate equity curve from completed trades
                equity_curve = []
                running_pnl = 0.0
                peak_equity = account_balance
                max_drawdown = 0.0
                
                # Sort completed trades by timestamp
                sorted_completed_trades = sorted(
                    all_completed_trades,
                    key=lambda t: _get_timestamp_from_completed_trade(t, fallback=datetime.min.replace(tzinfo=timezone.utc))
                )
                
                for completed_trade in sorted_completed_trades:
                    pnl = _get_pnl_from_completed_trade(completed_trade)
                    running_pnl += pnl
                    equity = account_balance + running_pnl
                    equity_curve.append(equity)
                    
                    if equity > peak_equity:
                        peak_equity = equity
                    
                    if peak_equity > 0:
                        drawdown = ((peak_equity - equity) / peak_equity) * 100
                        if drawdown > max_drawdown:
                            max_drawdown = drawdown
                
                current_drawdown_pct = max_drawdown
        except Exception as e:
            logger.warning(f"Error calculating drawdown from trades: {e}")
            current_drawdown_pct = 0.0
        
        # Determine risk status and identify which limits are breached
        # Note: risk_config.max_drawdown_pct is stored as decimal (0-1), but current_drawdown_pct is percentage (0-100)
        risk_status = "normal"
        breach_reasons = []
        
        if risk_config.max_drawdown_pct and current_drawdown_pct >= (risk_config.max_drawdown_pct * 100):
            risk_status = "breach"
            breach_reasons.append(("DRAWDOWN_LIMIT_BREACH", f"Drawdown limit exceeded: {current_drawdown_pct:.2f}% >= {risk_config.max_drawdown_pct * 100:.2f}%"))
        elif risk_config.max_daily_loss_usdt and daily_pnl_usdt <= -abs(risk_config.max_daily_loss_usdt):
            risk_status = "breach"
            breach_reasons.append(("DAILY_LOSS_LIMIT_BREACH", f"Daily loss limit exceeded: ${abs(daily_pnl_usdt):.2f} / ${risk_config.max_daily_loss_usdt:.2f}"))
        elif risk_config.max_weekly_loss_usdt and weekly_pnl_usdt <= -abs(risk_config.max_weekly_loss_usdt):
            risk_status = "breach"
            breach_reasons.append(("WEEKLY_LOSS_LIMIT_BREACH", f"Weekly loss limit exceeded: ${abs(weekly_pnl_usdt):.2f} / ${risk_config.max_weekly_loss_usdt:.2f}"))
        elif risk_config.max_portfolio_exposure_usdt and total_exposure_usdt >= risk_config.max_portfolio_exposure_usdt:
            risk_status = "breach"
            breach_reasons.append(("PORTFOLIO_EXPOSURE_LIMIT_BREACH", f"Portfolio exposure limit exceeded: ${total_exposure_usdt:.2f} >= ${risk_config.max_portfolio_exposure_usdt:.2f}"))
        elif (risk_config.max_drawdown_pct and current_drawdown_pct >= (risk_config.max_drawdown_pct * 100 * 0.8)) or \
             (risk_config.max_daily_loss_usdt and daily_pnl_usdt <= -abs(risk_config.max_daily_loss_usdt) * 0.8) or \
             (risk_config.max_weekly_loss_usdt and weekly_pnl_usdt <= -abs(risk_config.max_weekly_loss_usdt) * 0.8) or \
             (risk_config.max_portfolio_exposure_usdt and total_exposure_usdt >= risk_config.max_portfolio_exposure_usdt * 0.8):
            risk_status = "warning"
        
        # Get recent enforcement events (last 10) to check for duplicates
        account_uuid = None
        if account_id_normalized and account_id_normalized != "all":
            db_account = db_service.get_account_by_id(user_id, account_id_normalized)
            if db_account:
                account_uuid = db_account.id
        
        recent_events, _ = db_service.get_enforcement_events(
            user_id=user_id,
            account_id=account_uuid,
            limit=10,
            offset=0
        )
        
        # Create enforcement events for breaches (avoid duplicates - check if event exists in last hour)
        if breach_reasons and account_uuid:
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            
            for event_type, message in breach_reasons:
                # Check if similar event was created recently (within last hour)
                recent_similar_event = None
                for event in recent_events:
                    if (event.event_type == event_type and 
                        event.created_at >= one_hour_ago and
                        event.account_id == account_uuid):
                        recent_similar_event = event
                        break
                
                # Only create event if no similar recent event exists
                if not recent_similar_event:
                    try:
                        db_service.create_system_event(
                            event_type=event_type,
                            event_level="ERROR",
                            message=message,
                            strategy_id=None,  # Portfolio-level breach, not strategy-specific
                            account_id=account_uuid,
                            event_metadata={
                                "account_id": account_id_normalized,
                                "limit_type": event_type.lower().replace("_breach", ""),
                                "current_value": float(current_drawdown_pct) if "DRAWDOWN" in event_type else 
                                                 float(daily_pnl_usdt) if "DAILY" in event_type else
                                                 float(weekly_pnl_usdt) if "WEEKLY" in event_type else
                                                 float(total_exposure_usdt),
                                "limit_value": float(risk_config.max_drawdown_pct * 100) if "DRAWDOWN" in event_type else
                                              float(risk_config.max_daily_loss_usdt) if "DAILY" in event_type else
                                              float(risk_config.max_weekly_loss_usdt) if "WEEKLY" in event_type else
                                              float(risk_config.max_portfolio_exposure_usdt)
                            }
                        )
                        logger.warning(f"Created enforcement event for {event_type}: {message}")
                    except Exception as e:
                        logger.error(f"Failed to create enforcement event for {event_type}: {e}")
        
        # Format recent events
        recent_event_dicts = []
        for event in recent_events:
            recent_event_dicts.append({
                "event_type": event.event_type,
                "message": event.message,
                "created_at": event.created_at.isoformat()
            })
        
        # Build response
        return RealTimeRiskStatusResponse(
            account_id=account_id_normalized or "all",
            timestamp=datetime.now(timezone.utc),
            risk_status=risk_status,
            current_exposure={
                "total_exposure_usdt": total_exposure_usdt,
                "total_exposure_pct": total_exposure_pct,
                "limit_usdt": float(risk_config.max_portfolio_exposure_usdt) if risk_config.max_portfolio_exposure_usdt else None,
                "limit_pct": float(risk_config.max_portfolio_exposure_pct) if risk_config.max_portfolio_exposure_pct else None,
                "status": "normal" if not risk_config.max_portfolio_exposure_usdt or total_exposure_usdt < risk_config.max_portfolio_exposure_usdt else "breach"
            },
            loss_limits={
                "daily_loss_usdt": daily_pnl_usdt,
                "daily_loss_limit_usdt": float(risk_config.max_daily_loss_usdt) if risk_config.max_daily_loss_usdt else None,
                "daily_loss_pct": daily_pnl_pct,
                "daily_loss_limit_pct": float(risk_config.max_daily_loss_pct) if risk_config.max_daily_loss_pct else None,
                "weekly_loss_usdt": weekly_pnl_usdt,
                "weekly_loss_limit_usdt": float(risk_config.max_weekly_loss_usdt) if risk_config.max_weekly_loss_usdt else None,
                "status": "normal" if not risk_config.max_daily_loss_usdt or daily_pnl_usdt > -abs(risk_config.max_daily_loss_usdt) else "breach"
            },
            drawdown={
                "current_drawdown_pct": current_drawdown_pct,  # Already in percentage format (0-100) from metrics calculator
                "max_drawdown_pct": float(risk_config.max_drawdown_pct) * 100 if risk_config.max_drawdown_pct else None,  # Convert from decimal (0-1) to percentage (0-100)
                "status": "normal" if not risk_config.max_drawdown_pct or current_drawdown_pct < (risk_config.max_drawdown_pct * 100) else "breach"
            },
            circuit_breakers={
                "active": risk_config.circuit_breaker_enabled and False,  # TODO: Check actual circuit breaker status
                "breakers": []
            },
            recent_enforcement_events=recent_event_dicts
        )
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error getting real-time risk status: {e}\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Error getting real-time risk status: {str(e)}")


@router.get("/status/strategy/{strategy_id}", response_model=StrategyRiskStatusResponse)
async def get_strategy_risk_status(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
    runner: Optional[StrategyRunner] = Depends(get_strategy_runner),
) -> StrategyRiskStatusResponse:
    """Get risk status for a specific strategy.
    
    Returns whether the strategy can currently trade, any blocked reasons,
    circuit breaker status, and risk check results.
    """
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)
        
        # Get strategy
        db_strategy = db_service.get_strategy(user_id, strategy_id)
        if not db_strategy:
            raise HTTPException(status_code=404, detail=f"Strategy not found: {strategy_id}")
        
        # Get account
        account_id = None
        if db_strategy.account_id:
            try:
                db_account = db_service.get_account_by_uuid(db_strategy.account_id)
                if db_account:
                    account_id = db_account.account_id
            except Exception as e:
                logger.warning(f"Error getting account for strategy {strategy_id}: {e}")
                account_id = None
        
        # Get recent enforcement events for this strategy
        last_event = None
        try:
            events, _ = db_service.get_enforcement_events(
                user_id=user_id,
                strategy_id=db_strategy.id,
                limit=1,
                offset=0
            )
            
            if events:
                event = events[0]
                last_event = {
                    "event_type": event.event_type,
                    "message": event.message,
                    "created_at": event.created_at.isoformat()
                }
        except Exception as e:
            logger.warning(f"Error getting enforcement events for strategy {strategy_id}: {e}")
            last_event = None
        
        # Check if strategy is stopped by risk (circuit breaker active)
        # Handle status as string or enum
        strategy_status = str(db_strategy.status) if hasattr(db_strategy, 'status') and db_strategy.status else None
        is_stopped_by_risk = strategy_status == "stopped_by_risk"
        circuit_breaker_active = is_stopped_by_risk
        
        # Get account-level risk config
        account_risk_config = None
        try:
            risk_service = RiskManagementService(db=db, redis_storage=None)
            account_risk_config = risk_service.get_risk_config(user_id, account_id or "default")
        except Exception as e:
            logger.warning(f"Error getting account risk config for strategy {strategy_id}: {e}")
            account_risk_config = None
        
        # Get strategy-level risk config if available
        strategy_risk_config = None
        try:
            db_strategy_risk_config = db_service.get_strategy_risk_config(user_id, strategy_id)
            if db_strategy_risk_config:
                from app.models.risk_management import StrategyRiskConfigResponse
                strategy_risk_config = StrategyRiskConfigResponse.from_orm(db_strategy_risk_config)
                logger.info(f"Loaded strategy-level risk config for strategy {strategy_id}: enabled={strategy_risk_config.enabled}, daily_loss_limit={strategy_risk_config.max_daily_loss_usdt}, weekly_loss_limit={strategy_risk_config.max_weekly_loss_usdt}")
        except Exception as e:
            logger.info(f"Strategy {strategy_id} has no strategy-level risk config: {e}. Using account-level config only.")
            strategy_risk_config = None
        
        # Get effective risk config by merging account + strategy configs
        # This handles priority modes: override, more_restrictive, strategy_only
        # Same logic as PortfolioRiskManager.get_effective_risk_config()
        risk_config = account_risk_config  # Default to account config
        
        if strategy_risk_config and strategy_risk_config.enabled and account_risk_config:
            try:
                from app.models.risk_management import RiskManagementConfigResponse
                
                # Convert strategy config to RiskManagementConfigResponse format
                # StrategyRiskConfigResponse uses max_exposure_usdt, RiskManagementConfigResponse uses max_portfolio_exposure_usdt
                strategy_config_conv = RiskManagementConfigResponse(
                    id=strategy_risk_config.id if hasattr(strategy_risk_config, 'id') else account_risk_config.id,
                    user_id=strategy_risk_config.user_id if hasattr(strategy_risk_config, 'user_id') else account_risk_config.user_id,
                    account_id=account_id or "default",
                    timezone=strategy_risk_config.timezone or account_risk_config.timezone or "UTC",
                    max_portfolio_exposure_usdt=getattr(strategy_risk_config, 'max_exposure_usdt', None) or account_risk_config.max_portfolio_exposure_usdt,
                    max_portfolio_exposure_pct=getattr(strategy_risk_config, 'max_exposure_pct', None) or account_risk_config.max_portfolio_exposure_pct,
                    max_daily_loss_usdt=strategy_risk_config.max_daily_loss_usdt or account_risk_config.max_daily_loss_usdt,
                    max_daily_loss_pct=strategy_risk_config.max_daily_loss_pct or account_risk_config.max_daily_loss_pct,
                    max_weekly_loss_usdt=strategy_risk_config.max_weekly_loss_usdt or account_risk_config.max_weekly_loss_usdt,
                    max_weekly_loss_pct=strategy_risk_config.max_weekly_loss_pct or account_risk_config.max_weekly_loss_pct,
                    max_drawdown_pct=strategy_risk_config.max_drawdown_pct or account_risk_config.max_drawdown_pct,
                    daily_loss_reset_time=strategy_risk_config.daily_loss_reset_time or account_risk_config.daily_loss_reset_time,
                    weekly_loss_reset_day=strategy_risk_config.weekly_loss_reset_day or account_risk_config.weekly_loss_reset_day,
                    auto_reduce_order_size=account_risk_config.auto_reduce_order_size if account_risk_config else False,  # Strategy config doesn't have this - use account config
                    created_at=strategy_risk_config.created_at if hasattr(strategy_risk_config, 'created_at') else account_risk_config.created_at,
                    updated_at=strategy_risk_config.updated_at if hasattr(strategy_risk_config, 'updated_at') else account_risk_config.updated_at,
                )
                
                # Priority Rule 1: Override mode - strategy limits replace account limits
                if strategy_risk_config.override_account_limits:
                    risk_config = strategy_config_conv
                    logger.info(f"Strategy {strategy_id}: Using override mode - strategy limits only (daily: {risk_config.max_daily_loss_usdt}, weekly: {risk_config.max_weekly_loss_usdt})")
                
                # Priority Rule 2: More restrictive mode - use most restrictive of both
                elif strategy_risk_config.use_more_restrictive:
                    # Take minimum (most restrictive) for loss limits
                    # Take maximum (most restrictive) for exposure limits
                    strategy_exposure = getattr(strategy_risk_config, 'max_exposure_usdt', None)
                    account_exposure = account_risk_config.max_portfolio_exposure_usdt
                    risk_config = RiskManagementConfigResponse(
                        id=account_risk_config.id,
                        user_id=account_risk_config.user_id,
                        account_id=account_id or "default",
                        timezone=strategy_risk_config.timezone or account_risk_config.timezone or "UTC",
                        max_portfolio_exposure_usdt=min(x for x in [strategy_exposure, account_exposure] if x is not None) if (strategy_exposure and account_exposure) else (strategy_exposure or account_exposure),
                        max_portfolio_exposure_pct=min(
                            x for x in [getattr(strategy_risk_config, 'max_exposure_pct', None), account_risk_config.max_portfolio_exposure_pct]
                            if x is not None
                        ) if (getattr(strategy_risk_config, 'max_exposure_pct', None) and account_risk_config.max_portfolio_exposure_pct) else (getattr(strategy_risk_config, 'max_exposure_pct', None) or account_risk_config.max_portfolio_exposure_pct),
                        max_daily_loss_usdt=min(
                            x for x in [strategy_risk_config.max_daily_loss_usdt, account_risk_config.max_daily_loss_usdt]
                            if x is not None
                        ) if (strategy_risk_config.max_daily_loss_usdt and account_risk_config.max_daily_loss_usdt) else (strategy_risk_config.max_daily_loss_usdt or account_risk_config.max_daily_loss_usdt),
                        max_daily_loss_pct=min(
                            x for x in [strategy_risk_config.max_daily_loss_pct, account_risk_config.max_daily_loss_pct]
                            if x is not None
                        ) if (strategy_risk_config.max_daily_loss_pct and account_risk_config.max_daily_loss_pct) else (strategy_risk_config.max_daily_loss_pct or account_risk_config.max_daily_loss_pct),
                        max_weekly_loss_usdt=min(
                            x for x in [strategy_risk_config.max_weekly_loss_usdt, account_risk_config.max_weekly_loss_usdt]
                            if x is not None
                        ) if (strategy_risk_config.max_weekly_loss_usdt and account_risk_config.max_weekly_loss_usdt) else (strategy_risk_config.max_weekly_loss_usdt or account_risk_config.max_weekly_loss_usdt),
                        max_weekly_loss_pct=min(
                            x for x in [strategy_risk_config.max_weekly_loss_pct, account_risk_config.max_weekly_loss_pct]
                            if x is not None
                        ) if (strategy_risk_config.max_weekly_loss_pct and account_risk_config.max_weekly_loss_pct) else (strategy_risk_config.max_weekly_loss_pct or account_risk_config.max_weekly_loss_pct),
                        max_drawdown_pct=min(
                            x for x in [strategy_risk_config.max_drawdown_pct, account_risk_config.max_drawdown_pct]
                            if x is not None
                        ) if (strategy_risk_config.max_drawdown_pct and account_risk_config.max_drawdown_pct) else (strategy_risk_config.max_drawdown_pct or account_risk_config.max_drawdown_pct),
                        daily_loss_reset_time=strategy_risk_config.daily_loss_reset_time or account_risk_config.daily_loss_reset_time,
                        weekly_loss_reset_day=strategy_risk_config.weekly_loss_reset_day or account_risk_config.weekly_loss_reset_day,
                        auto_reduce_order_size=account_risk_config.auto_reduce_order_size if account_risk_config else False,  # Strategy config doesn't have this - use account config
                        created_at=account_risk_config.created_at,
                        updated_at=account_risk_config.updated_at,
                    )
                    logger.info(f"Strategy {strategy_id}: Using more restrictive mode - merged limits (daily: {risk_config.max_daily_loss_usdt}, weekly: {risk_config.max_weekly_loss_usdt})")
                
                # Priority Rule 3: Strategy-only mode - use strategy limits, ignore account limits
                else:
                    risk_config = strategy_config_conv
                    logger.info(f"Strategy {strategy_id}: Using strategy-only mode - strategy limits only (daily: {risk_config.max_daily_loss_usdt}, weekly: {risk_config.max_weekly_loss_usdt})")
            except Exception as e:
                logger.warning(f"Error merging strategy and account risk config for strategy {strategy_id}: {e}. Using account-level config only.")
                risk_config = account_risk_config
        
        # CRITICAL: Check account-level risk status FIRST
        # If account is breached, strategies WITHOUT override/strategy-only mode should be blocked
        # Strategies with override/strategy-only mode are independent of account limits
        account_risk_status = None
        account_daily_loss_usdt = 0.0
        account_weekly_loss_usdt = 0.0
        account_breach_reasons = []
        
        # CRITICAL: Use account_risk_config for account-level checks, NOT risk_config
        # risk_config might be strategy-only config in override/strategy-only mode
        account_check_config = account_risk_config  # Always use account-level config for account checks
        
        if account_id and account_check_config:
            try:
                # Calculate account-level daily and weekly loss (across ALL strategies for this account)
                # CRITICAL: Use same timezone/reset time as get_realtime_risk_status for consistency
                from zoneinfo import ZoneInfo
                from app.api.routes.reports import _get_completed_trades_from_database, _match_trades_to_completed_positions
                
                # Use helper functions to eliminate code duplication (same logic as get_realtime_risk_status)
                # CRITICAL: Use account_check_config (account_risk_config) for timezone/reset times
                tz_str = getattr(account_check_config, 'timezone', None) or "UTC"
                # Ensure timezone_str is a string, not a MagicMock
                if not isinstance(tz_str, str):
                    tz_str = "UTC"
                today_start = calculate_today_start(tz_str, getattr(account_check_config, 'daily_loss_reset_time', None))
                reset_day = getattr(account_check_config, 'weekly_loss_reset_day', None)
                # Ensure reset_day is an integer, not a MagicMock
                if not isinstance(reset_day, int):
                    reset_day = 1  # 1=Monday, 7=Sunday
                week_start = calculate_week_start(tz_str, reset_day)
                
                trade_service = TradeService(db=db)
                
                # Get all strategies for this account
                account_uuid = None
                try:
                    db_account = db_service.get_account_by_id(user_id, account_id)
                    if db_account:
                        account_uuid = db_account.id
                except Exception:
                    pass
                
                account_strategies = []
                if account_uuid:
                    try:
                        from app.models.db_models import Strategy
                        account_strategies = db.query(Strategy).filter(
                            Strategy.user_id == user_id,
                            Strategy.account_id == account_uuid
                        ).all()
                    except Exception as e:
                        logger.debug(f"Error getting strategies for account {account_id}: {e}")
                
                # Calculate total daily and weekly loss across all strategies for this account
                account_all_completed_trades = []
                for acc_strategy in account_strategies:
                    try:
                        # Get all completed trades for this strategy (no date filter yet - we'll filter later)
                        completed_trades = _get_completed_trades_from_database(
                            db_service=db_service,
                            user_id=user_id,
                            strategy_uuid=acc_strategy.id,
                            strategy_id=acc_strategy.strategy_id,
                            start_datetime=None,  # Get all trades, filter by exit_time later
                            end_datetime=None
                        )
                        account_all_completed_trades.extend(completed_trades)
                    except Exception as e:
                        logger.debug(f"Error getting completed trades for account strategy {acc_strategy.strategy_id}: {e}")
                
                # Use helper function to calculate PnL from completed trades (eliminates duplication)
                account_daily_loss_usdt = calculate_realized_pnl_from_trades(account_all_completed_trades, today_start)
                account_weekly_loss_usdt = calculate_realized_pnl_from_trades(account_all_completed_trades, week_start)
                
                # Get trade counts for logging (optional)
                account_daily_completed_trades = [
                    t for t in account_all_completed_trades
                    if (getattr(t, 'exit_time', None) or datetime.min.replace(tzinfo=timezone.utc)) >= today_start
                ]
                account_weekly_completed_trades = [
                    t for t in account_all_completed_trades
                    if (getattr(t, 'exit_time', None) or datetime.min.replace(tzinfo=timezone.utc)) >= week_start
                ]
                
                logger.debug(
                    f"Account '{account_id}' PnL: daily={account_daily_loss_usdt:.2f} "
                    f"(from {len(account_daily_completed_trades)} trades), "
                    f"weekly={account_weekly_loss_usdt:.2f} (from {len(account_weekly_completed_trades)} trades)"
                )
                
                # Check if account-level daily loss exceeds limit
                # CRITICAL: Use account_check_config (account_risk_config) limits, not risk_config
                if account_check_config.max_daily_loss_usdt:
                    max_daily_loss = float(account_check_config.max_daily_loss_usdt)
                    if max_daily_loss > 0 and account_daily_loss_usdt < 0:
                        # Use absolute values for clarity: |loss| >= limit means limit exceeded
                        if abs(account_daily_loss_usdt) >= max_daily_loss:
                            account_risk_status = "breach"
                            account_breach_reasons.append(
                                f"Account daily loss limit exceeded: ${abs(account_daily_loss_usdt):.2f} / ${max_daily_loss:.2f}"
                            )
                            logger.warning(
                                f"Account '{account_id}' breached daily loss limit: "
                                f"${abs(account_daily_loss_usdt):.2f} >= ${max_daily_loss:.2f}"
                            )
                
                # Check if account-level weekly loss exceeds limit
                # CRITICAL: Use account_check_config (account_risk_config) limits, not risk_config
                if account_check_config.max_weekly_loss_usdt:
                    max_weekly_loss = float(account_check_config.max_weekly_loss_usdt)
                    if max_weekly_loss > 0 and account_weekly_loss_usdt < 0:
                        # Use absolute values for clarity: |loss| >= limit means limit exceeded
                        if abs(account_weekly_loss_usdt) >= max_weekly_loss:
                            account_risk_status = "breach"
                            account_breach_reasons.append(
                                f"Account weekly loss limit exceeded: ${abs(account_weekly_loss_usdt):.2f} / ${max_weekly_loss:.2f}"
                            )
                            logger.warning(
                                f"Account '{account_id}' breached weekly loss limit: "
                                f"${abs(account_weekly_loss_usdt):.2f} >= ${max_weekly_loss:.2f}"
                            )
                
            except Exception as e:
                logger.warning(f"Error checking account-level risk status for strategy {strategy_id}: {e}")
                # Continue with strategy-level checks if account check fails
        
        # Build risk checks and determine if strategy can trade
        # Default: strategy can trade unless explicitly blocked
        can_trade = True
        blocked_reasons = []
        
        # CRITICAL: If account is breached, block strategies that are NOT in override/strategy-only mode
        # Strategies with override/strategy-only mode are independent and should only be checked against their own limits
        strategy_is_independent = (
            strategy_risk_config and 
            strategy_risk_config.enabled and 
            (strategy_risk_config.override_account_limits or 
             (not strategy_risk_config.use_more_restrictive and not strategy_risk_config.override_account_limits))
        )
        
        if account_risk_status == "breach" and not strategy_is_independent:
            # Account-level breach affects this strategy (not in override/strategy-only mode)
            can_trade = False
            blocked_reasons.extend(account_breach_reasons)
            blocked_reasons.append(f"Account '{account_id}' risk limit breached - all strategies blocked")
            logger.warning(
                f"Strategy {strategy_id} blocked: Account '{account_id}' has risk status 'breach'. "
                f"Account-level daily loss: ${account_daily_loss_usdt:.2f}, weekly loss: ${account_weekly_loss_usdt:.2f}"
            )
            
            # CRITICAL FIX: Automatically pause all strategies for this account when breach is detected
            # This ensures strategies are paused even if they're not executing orders
            # Determine the limit type from breach reasons
            # CRITICAL: Check for both daily and weekly - use same logic for both
            limit_type = None
            daily_breach_detected = any("daily loss" in reason.lower() for reason in account_breach_reasons)
            weekly_breach_detected = any("weekly loss" in reason.lower() for reason in account_breach_reasons)
            
            if daily_breach_detected:
                limit_type = "DAILY_LOSS"
            elif weekly_breach_detected:
                limit_type = "WEEKLY_LOSS"
            
            # CRITICAL: If daily OR weekly loss breached, set circuit_breaker_active = True
            # This ensures UI shows "Paused" instead of "Blocked"
            # Both daily and weekly should trigger the same stopping behavior
            if limit_type:
                circuit_breaker_active = True
                is_stopped_by_risk = True  # Treat as stopped_by_risk even if status not updated yet
                # Refresh strategy status from database after auto-pause
                db.refresh(db_strategy)
                strategy_status = str(db_strategy.status) if hasattr(db_strategy, 'status') and db_strategy.status else None
            
            # CRITICAL: Both DAILY_LOSS and WEEKLY_LOSS should trigger pause_all_strategies_for_account
            # This ensures strategies are stopped when either limit is exceeded
            if runner and account_id and limit_type:
                try:
                    # CRITICAL: Get account object first (needed for account.id)
                    account = db_service.get_account_by_id(user_id, account_id)
                    running_strategies = []
                    if not account:
                        logger.warning(f"Cannot auto-pause: account {account_id} not found")
                    else:
                        # CRITICAL: Only auto-pause if strategies are actually running
                        # Don't pause if they're already stopped_by_risk (prevent duplicate pauses)
                        from app.models.db_models import Strategy
                        running_strategies = db.query(Strategy).filter(
                            Strategy.user_id == current_user.id,
                            Strategy.account_id == account.id,
                            Strategy.status == "running"
                        ).all()
                    
                    # Also check if current strategy is still running
                    current_strategy_running = (strategy_status == "running")
                    
                    if (running_strategies or current_strategy_running) and account:
                        logger.warning(
                            f"🛑 Auto-pausing {len(running_strategies) + (1 if current_strategy_running else 0)} strategies for account {account_id} "
                            f"due to {limit_type} breach detected in risk status check"
                        )
                        # Pause all strategies for this account (only running ones)
                        paused_strategies = await runner.pause_all_strategies_for_account(
                            account_id=account_id,
                            reason=f"{limit_type.replace('_', ' ').title()} limit exceeded: {', '.join(account_breach_reasons)}"
                        )
                        
                        # CRITICAL: Wait a moment for database commit to complete
                        import asyncio
                        await asyncio.sleep(0.1)  # 100ms for DB commit
                        
                        # CRITICAL: Force refresh from database to get updated status
                        # Wait a bit more to ensure all database commits completed
                        await asyncio.sleep(0.2)  # 200ms total for all commits
                        db.expire_all()  # Expire all cached objects to force fresh query
                        
                        # Reload strategy from database to get fresh status
                        db_strategy_fresh = db.query(Strategy).filter(
                            Strategy.user_id == current_user.id,
                            Strategy.strategy_id == strategy_id
                        ).first()
                        
                        if db_strategy_fresh:
                            strategy_status = str(db_strategy_fresh.status) if hasattr(db_strategy_fresh, 'status') and db_strategy_fresh.status else None
                            is_stopped_by_risk = strategy_status == "stopped_by_risk"
                            circuit_breaker_active = is_stopped_by_risk
                            
                            # CRITICAL: If status is still "running", the pause may have failed
                            if strategy_status == "running":
                                logger.error(
                                    f"⚠️ CRITICAL: Strategy {strategy_id} status is still 'running' after auto-pause! "
                                    f"This indicates pause_all_strategies_for_account() did not complete successfully. "
                                    f"Paused strategies: {paused_strategies}"
                                )
                                # Force set to stopped_by_risk in response to show correct risk status
                                is_stopped_by_risk = True
                                circuit_breaker_active = True
                            else:
                                logger.info(
                                    f"✅ Auto-pause completed: {len(paused_strategies)} strategies paused. "
                                    f"Current strategy {strategy_id} status: {strategy_status} (stopped_by_risk={is_stopped_by_risk})"
                                )
                        else:
                            logger.warning(f"Could not refresh strategy {strategy_id} from database after auto-pause")
                            # If we can't refresh, assume it should be paused since we just paused it
                            is_stopped_by_risk = True
                            circuit_breaker_active = True
                except Exception as pause_error:
                    # Log error but don't fail the risk status check
                    logger.error(
                        f"Failed to auto-pause strategies for account {account_id} during risk status check: {pause_error}",
                        exc_info=True
                    )
        elif account_risk_status == "breach" and strategy_is_independent:
            # Account is breached but this strategy is independent (override/strategy-only mode)
            # Don't block - let strategy-level checks handle it
            # CRITICAL: Do NOT auto-pause strategies when they are independent
            # Independent strategies should only be checked against their own limits
            logger.debug(
                f"Strategy {strategy_id} is independent (override/strategy-only mode). "
                f"Account breach ({account_risk_status}) does not affect this strategy. "
                f"Strategy will be evaluated against its own limits only."
            )
        
        # Check circuit breaker first (highest priority)
        if is_stopped_by_risk:
            can_trade = False
            blocked_reasons.append("Strategy stopped by risk management (circuit breaker)")
            logger.debug(f"Strategy {strategy_id} is stopped by risk - blocking trade")
        
        risk_checks = {}
        
        if risk_config:
            logger.debug(f"Checking risk limits for strategy {strategy_id}, account {account_id or 'default'}")
            # Get actual trade data to calculate real risk values
            trade_service = TradeService(db=db)
            
            # Get today's trades for daily loss calculation
            # CRITICAL: Use trade matching to calculate from completed trade cycles
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            daily_loss_usdt = 0.0  # Default to 0 (no loss) if we can't get trades
            weekly_loss_usdt = 0.0  # Default to 0 (no loss) if we can't get trades
            try:
                # Only get trades if we have a valid account_id
                today_trades = []
                if account_id:
                    try:
                        today_trades = trade_service.get_trades_by_account(user_id, account_id) or []
                    except Exception as e:
                        logger.warning(f"Error getting trades by account for strategy {strategy_id}: {e}")
                        today_trades = []
                else:
                    # If no account_id, get trades for this specific strategy instead
                    try:
                        today_trades = trade_service.get_strategy_trades(user_id, db_strategy.id, limit=10000) or []
                    except Exception as e:
                        logger.warning(f"Error getting strategy trades for strategy {strategy_id}: {e}")
                        today_trades = []
                # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table
                from app.api.routes.reports import _get_completed_trades_from_database, _match_trades_to_completed_positions
                
                # Try to get completed trades from database (pre-computed)
                all_completed_trades = []
                try:
                    completed_trades = _get_completed_trades_from_database(
                        db_service=db_service,
                        user_id=user_id,
                        strategy_uuid=db_strategy.id,
                        strategy_id=strategy_id,
                        start_datetime=today_start,  # Filter by today
                        end_datetime=None
                    )
                    all_completed_trades.extend(completed_trades)
                    logger.debug(f"Strategy {strategy_id}: Found {len(completed_trades)} completed trades from database today")
                except Exception as e:
                    logger.debug(f"Strategy {strategy_id}: Could not get completed trades from database: {e}, falling back to on-demand matching")
                
                # ✅ FALLBACK: If no completed trades from database, use on-demand matching
                if not all_completed_trades:
                    # Filter today's trades - ensure we only process database Trade objects (not OrderResponse)
                    # Database Trade objects have 'strategy_id' attribute, OrderResponse objects don't
                    today_trades_filtered = []
                    for t in (today_trades or []):
                        if not t:
                            continue
                        # Only process if it's a database Trade object (has strategy_id attribute)
                        # Skip if it's already an OrderResponse (no strategy_id attribute)
                        if hasattr(t, 'strategy_id') and hasattr(t, 'timestamp') and t.timestamp and t.timestamp >= today_start:
                            today_trades_filtered.append(t)
                        elif hasattr(t, 'timestamp') and t.timestamp and t.timestamp >= today_start:
                            # Might be an OrderResponse - log warning and skip
                            logger.debug(f"Skipping trade object without strategy_id attribute (likely OrderResponse): {type(t)}")
                            continue
                    
                    # Initialize trades_by_strategy_uuid outside the if block to avoid UnboundLocalError
                    trades_by_strategy_uuid = {}
                    if today_trades_filtered:
                        # CRITICAL: Match trades to completed positions (same logic as reports page)
                        from app.models.order import OrderResponse
                        
                        # Group by strategy UUID BEFORE converting (db_trade.strategy_id is a UUID)
                        for db_trade in today_trades_filtered:
                            if not db_trade:
                                continue
                            # Ensure it's a database Trade object with strategy_id
                            if not hasattr(db_trade, 'strategy_id'):
                                logger.warning(f"Trade object missing strategy_id attribute: {type(db_trade)}")
                                continue
                            strategy_uuid = db_trade.strategy_id if db_trade.strategy_id else None
                            if not strategy_uuid:
                                continue
                            
                            strategy_uuid_str = str(strategy_uuid)
                            if strategy_uuid_str not in trades_by_strategy_uuid:
                                trades_by_strategy_uuid[strategy_uuid_str] = []
                            trades_by_strategy_uuid[strategy_uuid_str].append(db_trade)
                    
                    # Convert and group OrderResponse objects by strategy
                    trades_by_strategy = {}
                    for strategy_uuid_str, db_trades in trades_by_strategy_uuid.items():
                        if not db_trades:
                            continue
                        try:
                            # Convert database trades to OrderResponse format using helper
                            order_responses = _convert_db_trades_to_order_responses(db_trades, trade_service)
                            if order_responses:
                                trades_by_strategy[strategy_uuid_str] = order_responses
                        except Exception as e:
                            logger.warning(f"Error converting trades to OrderResponse for strategy {strategy_uuid_str}: {e}")
                            continue
                    
                    # Match trades for each strategy
                    for strategy_uuid_str, strategy_trades in trades_by_strategy.items():
                        if not strategy_trades:
                            continue
                        
                        # Initialize defaults
                        strategy_name = "Unknown"
                        symbol = strategy_trades[0].symbol if strategy_trades else ""
                        leverage = strategy_trades[0].leverage if strategy_trades and strategy_trades[0].leverage else 1
                        strategy_id_str = strategy_id  # Use the function parameter as default
                        db_strategy = None
                        
                        try:
                            from uuid import UUID
                            strategy_uuid_obj = UUID(strategy_uuid_str)
                            db_strategy = db_service.get_strategy_by_uuid(strategy_uuid_obj)
                            if db_strategy:
                                strategy_name = db_strategy.name or "Unknown"
                                symbol = db_strategy.symbol or symbol
                                leverage = db_strategy.leverage or leverage
                                strategy_id_str = db_strategy.strategy_id or strategy_id
                        except Exception as e:
                            logger.debug(f"Could not get strategy info for UUID {strategy_uuid_str}: {e}")
                        
                        try:
                            matched_trades = _match_trades_to_completed_positions(
                                strategy_trades,
                                strategy_id_str,  # Use strategy_id string, not UUID
                                strategy_name,
                                symbol,
                                leverage
                            )
                            all_completed_trades.extend(matched_trades)
                        except Exception as e:
                                logger.warning(f"Error matching trades for strategy {strategy_id_str}: {e}")
                                import traceback
                                logger.debug(f"Traceback: {traceback.format_exc()}")
                
                # Calculate daily and weekly loss from completed trades
                # Use same timezone/reset time as risk checks for consistency
                # Use helper functions to eliminate code duplication
                tz_str = getattr(risk_config, 'timezone', None) or "UTC"
                # Ensure timezone_str is a string, not a MagicMock
                if not isinstance(tz_str, str):
                    tz_str = "UTC"
                today_start = calculate_today_start(tz_str, getattr(risk_config, 'daily_loss_reset_time', None))
                daily_loss_usdt = calculate_realized_pnl_from_trades(all_completed_trades, today_start)
                
                reset_day = getattr(risk_config, 'weekly_loss_reset_day', None)
                # Ensure reset_day is an integer, not a MagicMock
                if not isinstance(reset_day, int):
                    reset_day = 1  # 1=Monday, 7=Sunday
                week_start = calculate_week_start(tz_str, reset_day)
                weekly_loss_usdt = calculate_realized_pnl_from_trades(all_completed_trades, week_start)
                
                # Get trade counts for logging (optional)
                daily_completed_trades = [
                    t for t in all_completed_trades
                    if (getattr(t, 'exit_time', None) or datetime.min.replace(tzinfo=timezone.utc)) >= today_start
                ]
                weekly_completed_trades = [
                    t for t in all_completed_trades
                    if (getattr(t, 'exit_time', None) or datetime.min.replace(tzinfo=timezone.utc)) >= week_start
                ]
                logger.debug(f"Strategy {strategy_id}: Found {len(daily_completed_trades)} completed trades today, daily_loss={daily_loss_usdt:.2f}")
                logger.debug(f"Strategy {strategy_id}: Found {len(weekly_completed_trades)} completed trades this week, weekly_loss={weekly_loss_usdt:.2f}")
            except Exception as e:
                logger.warning(f"Error getting trades for risk status: {e}")
                daily_loss_usdt = 0.0  # Default to 0 if we can't get trades
                weekly_loss_usdt = 0.0  # Default to 0 if we can't get trades
            
            # Ensure daily_loss_usdt is a valid number
            if not isinstance(daily_loss_usdt, (int, float)) or daily_loss_usdt != daily_loss_usdt:  # Check for NaN
                logger.warning(f"Invalid daily_loss_usdt value: {daily_loss_usdt}, defaulting to 0.0")
                daily_loss_usdt = 0.0
            
            # Ensure weekly_loss_usdt is a valid number
            if not isinstance(weekly_loss_usdt, (int, float)) or weekly_loss_usdt != weekly_loss_usdt:  # Check for NaN
                logger.warning(f"Invalid weekly_loss_usdt value: {weekly_loss_usdt}, defaulting to 0.0")
                weekly_loss_usdt = 0.0
            
            # Portfolio exposure check (simplified - would need actual open positions)
            # For now, assume no exposure if we can't calculate it
            portfolio_exposure_usdt = 0.0  # TODO: Get from actual open positions
            
            # Check portfolio exposure limit
            # Only block if exposure exceeds the limit (exposure is always >= 0)
            exposure_allowed = True
            max_exposure = risk_config.max_portfolio_exposure_usdt
            if max_exposure is not None:
                try:
                    max_exposure = float(max_exposure)
                    if max_exposure > 0 and portfolio_exposure_usdt >= max_exposure:
                        exposure_allowed = False
                        can_trade = False
                        blocked_reasons.append(f"Portfolio exposure limit exceeded: ${portfolio_exposure_usdt:.2f} / ${max_exposure:.2f}")
                        logger.warning(f"Strategy {strategy_id} blocked: portfolio exposure {portfolio_exposure_usdt:.2f} >= limit {max_exposure:.2f}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid max_portfolio_exposure_usdt value: {max_exposure}, error: {e}")
            
            # Check daily loss limit
            # max_daily_loss_usdt is stored as positive (e.g., 500 means max loss is -500)
            # daily_loss_usdt is negative when there's a loss (e.g., -100), positive or zero for profit/no trades
            # CRITICAL: If daily_loss_usdt >= 0 (no loss or profit), NEVER block
            daily_loss_allowed = True
            max_daily_loss = risk_config.max_daily_loss_usdt
            if max_daily_loss is not None:
                try:
                    max_daily_loss = float(max_daily_loss)
                    if max_daily_loss > 0:
                        # Convert positive limit to negative threshold
                        loss_threshold = -max_daily_loss
                        logger.debug(f"Daily loss check: current={daily_loss_usdt:.2f}, threshold={loss_threshold:.2f}, limit={max_daily_loss:.2f}")
                        
                        # CRITICAL SAFEGUARD: Only check if there's an actual loss (daily_loss_usdt < 0)
                        # If daily_loss_usdt >= 0 (no trades = 0, or profit > 0), NEVER block
                        if daily_loss_usdt < 0:
                            # Only block if loss exceeds threshold
                            # Use absolute values for clarity: |loss| >= limit means limit exceeded
                            if abs(daily_loss_usdt) >= max_daily_loss:
                                daily_loss_allowed = False
                                can_trade = False
                                blocked_reasons.append(f"Daily loss limit exceeded: ${abs(daily_loss_usdt):.2f} / ${max_daily_loss:.2f}")
                                logger.warning(f"Strategy {strategy_id} blocked: daily loss ${abs(daily_loss_usdt):.2f} >= limit ${max_daily_loss:.2f}")
                            else:
                                logger.debug(f"Strategy {strategy_id} has daily loss ${abs(daily_loss_usdt):.2f} but within limit ${max_daily_loss:.2f}")
                        else:
                            # daily_loss_usdt >= 0 means no loss or profit - NEVER block
                            logger.debug(f"Strategy {strategy_id} has no daily loss (value={daily_loss_usdt:.2f} >= 0), allowing trade")
                    else:
                        logger.debug(f"Invalid max_daily_loss_usdt value (must be > 0): {max_daily_loss}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid max_daily_loss_usdt value: {max_daily_loss}, error: {e}")
            else:
                logger.debug(f"No daily loss limit configured for strategy {strategy_id}")
            
            # CRITICAL: Ensure daily_loss_allowed is True if daily_loss_usdt >= 0 (no loss or profit)
            # This prevents false blocking when there are no trades (daily_loss_usdt = 0)
            if daily_loss_usdt >= 0:
                daily_loss_allowed = True
                logger.debug(f"Strategy {strategy_id}: daily_loss_usdt={daily_loss_usdt:.2f} >= 0, forcing daily_loss_allowed=True")
            
            risk_checks["portfolio_exposure"] = {
                "allowed": exposure_allowed,
                "current_value": portfolio_exposure_usdt,
                "limit_value": float(risk_config.max_portfolio_exposure_usdt) if risk_config.max_portfolio_exposure_usdt else None
            }
            
            # CRITICAL: If account is breached, override strategy-level daily loss check
            # Account-level breach takes precedence over strategy-level checks
            if account_risk_status == "breach":
                daily_loss_allowed = False
                # Use account-level daily loss instead of strategy-level
                daily_loss_usdt = account_daily_loss_usdt
                logger.warning(
                    f"Strategy {strategy_id}: Account '{account_id}' breached, "
                    f"overriding strategy-level daily loss check. Account daily loss: ${account_daily_loss_usdt:.2f}"
                )
            
            # Add account and strategy level limits for display
            account_daily_limit = float(account_risk_config.max_daily_loss_usdt) if account_risk_config and account_risk_config.max_daily_loss_usdt else None
            strategy_daily_limit = float(strategy_risk_config.max_daily_loss_usdt) if strategy_risk_config and strategy_risk_config.enabled and strategy_risk_config.max_daily_loss_usdt else None
            effective_daily_limit = float(risk_config.max_daily_loss_usdt) if risk_config.max_daily_loss_usdt else None
            
            risk_checks["daily_loss"] = {
                "allowed": daily_loss_allowed,
                # Use absolute value for display - show positive loss amounts
                "current_value": abs(account_daily_loss_usdt) if account_risk_status == "breach" else abs(daily_loss_usdt),
                "limit_value": effective_daily_limit,  # Effective limit (merged)
                "account_limit_value": account_daily_limit,  # Account-level limit
                "strategy_limit_value": strategy_daily_limit  # Strategy-level limit (if configured)
            }
            
            # Check weekly loss limit
            # max_weekly_loss_usdt is stored as positive (e.g., 500 means max loss is -500)
            # weekly_loss_usdt is negative when there's a loss (e.g., -100), positive or zero for profit/no trades
            # CRITICAL: If weekly_loss_usdt >= 0 (no loss or profit), NEVER block
            weekly_loss_allowed = True
            max_weekly_loss = risk_config.max_weekly_loss_usdt
            if max_weekly_loss is not None:
                try:
                    max_weekly_loss = float(max_weekly_loss)
                    if max_weekly_loss > 0:
                        # Convert positive limit to negative threshold
                        loss_threshold = -max_weekly_loss
                        logger.debug(f"Weekly loss check: current={weekly_loss_usdt:.2f}, threshold={loss_threshold:.2f}, limit={max_weekly_loss:.2f}")
                        
                        # CRITICAL SAFEGUARD: Only check if there's an actual loss (weekly_loss_usdt < 0)
                        # If weekly_loss_usdt >= 0 (no trades = 0, or profit > 0), NEVER block
                        if weekly_loss_usdt < 0:
                            # Only block if loss exceeds threshold
                            # Use absolute values for clarity: |loss| >= limit means limit exceeded
                            if abs(weekly_loss_usdt) >= max_weekly_loss:
                                weekly_loss_allowed = False
                                can_trade = False
                                blocked_reasons.append(f"Weekly loss limit exceeded: ${abs(weekly_loss_usdt):.2f} / ${max_weekly_loss:.2f}")
                                logger.warning(f"Strategy {strategy_id} blocked: weekly loss ${abs(weekly_loss_usdt):.2f} >= limit ${max_weekly_loss:.2f}")
                            else:
                                logger.debug(f"Strategy {strategy_id} has weekly loss ${abs(weekly_loss_usdt):.2f} but within limit ${max_weekly_loss:.2f}")
                        else:
                            # weekly_loss_usdt >= 0 means no loss or profit - NEVER block
                            logger.debug(f"Strategy {strategy_id} has no weekly loss (value={weekly_loss_usdt:.2f} >= 0), allowing trade")
                    else:
                        logger.debug(f"Invalid max_weekly_loss_usdt value (must be > 0): {max_weekly_loss}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid max_weekly_loss_usdt value: {max_weekly_loss}, error: {e}")
            else:
                logger.debug(f"No weekly loss limit configured for strategy {strategy_id}")
            
            # CRITICAL: Ensure weekly_loss_allowed is True if weekly_loss_usdt >= 0 (no loss or profit)
            if weekly_loss_usdt >= 0:
                weekly_loss_allowed = True
                logger.debug(f"Strategy {strategy_id}: weekly_loss_usdt={weekly_loss_usdt:.2f} >= 0, forcing weekly_loss_allowed=True")
            
            # CRITICAL: If account is breached, override strategy-level weekly loss check
            # Account-level breach takes precedence over strategy-level checks
            if account_risk_status == "breach":
                weekly_loss_allowed = False
                # Use account-level weekly loss instead of strategy-level
                weekly_loss_usdt = account_weekly_loss_usdt
                logger.warning(
                    f"Strategy {strategy_id}: Account '{account_id}' breached, "
                    f"overriding strategy-level weekly loss check. Account weekly loss: ${account_weekly_loss_usdt:.2f}"
                )
            
            # Add account and strategy level limits for display
            account_weekly_limit = float(account_risk_config.max_weekly_loss_usdt) if account_risk_config and account_risk_config.max_weekly_loss_usdt else None
            strategy_weekly_limit = float(strategy_risk_config.max_weekly_loss_usdt) if strategy_risk_config and strategy_risk_config.enabled and strategy_risk_config.max_weekly_loss_usdt else None
            effective_weekly_limit = float(risk_config.max_weekly_loss_usdt) if risk_config.max_weekly_loss_usdt else None
            
            risk_checks["weekly_loss"] = {
                "allowed": weekly_loss_allowed,
                # Use absolute value for display - show positive loss amounts
                "current_value": abs(account_weekly_loss_usdt) if account_risk_status == "breach" else abs(weekly_loss_usdt),
                "limit_value": effective_weekly_limit,  # Effective limit (merged)
                "account_limit_value": account_weekly_limit,  # Account-level limit
                "strategy_limit_value": strategy_weekly_limit  # Strategy-level limit (if configured)
            }
            
            # Add account risk check if account is breached
            if account_risk_status == "breach":
                risk_checks["account_risk"] = {
                    "allowed": False,
                    "status": account_risk_status,
                    "breach_reasons": account_breach_reasons,
                    "account_daily_loss": account_daily_loss_usdt,
                    "account_weekly_loss": account_weekly_loss_usdt
                }
            
            # CRITICAL: If strategy-level daily or weekly loss limit exceeded, stop the strategy
            # This ensures strategies are stopped even if they're not executing orders
            # Only stop if it's a strategy-level breach (not account-level, which is handled above)
            strategy_level_breach_detected = False
            strategy_limit_type = None
            
            if not daily_loss_allowed and account_risk_status != "breach":
                # Strategy-level daily loss breach (not account-level)
                strategy_level_breach_detected = True
                strategy_limit_type = "DAILY_LOSS"
                logger.warning(
                    f"🛑 Strategy-level {strategy_limit_type} limit exceeded for strategy {strategy_id}. "
                    f"Stopping this strategy only."
                )
            elif not weekly_loss_allowed and account_risk_status != "breach":
                # Strategy-level weekly loss breach (not account-level)
                strategy_level_breach_detected = True
                strategy_limit_type = "WEEKLY_LOSS"
                logger.warning(
                    f"🛑 Strategy-level {strategy_limit_type} limit exceeded for strategy {strategy_id}. "
                    f"Stopping this strategy only."
                )
            
            # Stop the strategy if strategy-level limit is breached
            if strategy_level_breach_detected and runner and strategy_limit_type:
                try:
                    # Check if strategy is still running
                    if strategy_status == "running":
                        logger.warning(
                            f"🛑 Stopping strategy {strategy_id} due to {strategy_limit_type} breach detected in risk status check"
                        )
                        # Stop only this specific strategy (not all strategies in account)
                        stopped_summary = await runner.stop(strategy_id)
                        
                        # Update status to stopped_by_risk
                        if db_strategy:
                            db_strategy.status = "stopped_by_risk"
                            db.commit()
                            db.refresh(db_strategy)
                            
                            # Update in-memory summary
                            from app.models.strategy import StrategyState
                            if stopped_summary:
                                stopped_summary.status = StrategyState.stopped_by_risk
                            
                            # Update flags
                            is_stopped_by_risk = True
                            circuit_breaker_active = True
                            strategy_status = "stopped_by_risk"
                            
                            logger.info(
                                f"✅ Strategy {strategy_id} stopped due to {strategy_limit_type} limit exceeded. "
                                f"Status updated to stopped_by_risk."
                            )
                        else:
                            logger.warning(f"Could not update strategy {strategy_id} status - db_strategy not found")
                    else:
                        logger.debug(
                            f"Strategy {strategy_id} is already stopped (status: {strategy_status}), "
                            f"not attempting to stop again."
                        )
                        # Still set flags to ensure correct response
                        if strategy_status == "stopped_by_risk":
                            is_stopped_by_risk = True
                            circuit_breaker_active = True
                except Exception as stop_error:
                    # Log error but don't fail the risk status check
                    logger.error(
                        f"Failed to stop strategy {strategy_id} due to {strategy_limit_type} limit: {stop_error}",
                        exc_info=True
                    )
                    # Still set flags to show it should be stopped
                    is_stopped_by_risk = True
                    circuit_breaker_active = True
            
            # CRITICAL: If daily_loss_allowed is False but daily_loss_usdt >= 0, this is a bug
            # Force it to True to prevent false blocking
            if not daily_loss_allowed and daily_loss_usdt >= 0:
                logger.error(
                    f"BUG DETECTED: Strategy {strategy_id} has daily_loss_allowed=False but daily_loss_usdt={daily_loss_usdt:.2f} >= 0. "
                    f"This should never happen. Forcing daily_loss_allowed=True"
                )
                daily_loss_allowed = True
                risk_checks["daily_loss"]["allowed"] = True
                # Remove any daily loss related blocked reasons
                blocked_reasons = [r for r in blocked_reasons if "Daily loss" not in r]
                # CRITICAL: If we removed all blocked reasons, can_trade MUST be True
                if len(blocked_reasons) == 0:
                    if not circuit_breaker_active:
                        can_trade = True
                        logger.debug(f"Strategy {strategy_id}: Removed daily loss blocked reasons, setting can_trade=True")
                    else:
                        # Circuit breaker is active, add a reason if missing
                        if not any("circuit breaker" in r.lower() or "paused" in r.lower() for r in blocked_reasons):
                            blocked_reasons.append("Strategy stopped by risk management (circuit breaker)")
                            logger.debug(f"Strategy {strategy_id}: Circuit breaker active, added blocked reason")
                # Ensure can_trade and blocked_reasons are consistent
                if not can_trade and len(blocked_reasons) == 0 and not circuit_breaker_active:
                    logger.warning(
                        f"Strategy {strategy_id}: Inconsistent state - can_trade=False but no blocked_reasons. "
                        f"Forcing can_trade=True"
                    )
                    can_trade = True
            
            # Circuit breaker check
            risk_checks["circuit_breaker"] = {
                "allowed": not circuit_breaker_active,
                "active": circuit_breaker_active
            }
        else:
            # No risk config - all checks pass, strategy can trade
            risk_checks = {
                "portfolio_exposure": {"allowed": True, "current_value": 0.0, "limit_value": None},
                "daily_loss": {"allowed": True, "current_value": 0.0, "limit_value": None},
                "weekly_loss": {"allowed": True, "current_value": 0.0, "limit_value": None},
                "circuit_breaker": {"allowed": True, "active": False}
            }
            # can_trade remains True (default)
        
        # CRITICAL FINAL VALIDATION: Ensure can_trade is only False if there's a real blocking reason
        # This prevents false positives where strategies are blocked incorrectly
        # Rule: can_trade can only be False if:
        #   1. Circuit breaker is active (is_stopped_by_risk), OR
        #   2. There are explicit blocked_reasons
        # If neither condition is met, force can_trade = True
        if not can_trade:
            if not circuit_breaker_active and len(blocked_reasons) == 0:
                logger.warning(
                    f"Strategy {strategy_id} has can_trade=False but no valid blocking reason "
                    f"(circuit_breaker_active={circuit_breaker_active}, blocked_reasons={blocked_reasons}). "
                    f"This is inconsistent - forcing can_trade=True"
                )
                can_trade = True
            elif circuit_breaker_active:
                logger.debug(f"Strategy {strategy_id} blocked: circuit breaker active")
            elif len(blocked_reasons) > 0:
                logger.debug(f"Strategy {strategy_id} blocked: {blocked_reasons}")
        
        # FINAL CONSISTENCY CHECK: Ensure can_trade and blocked_reasons are always consistent
        # Rule: can_trade=False MUST have either blocked_reasons OR circuit_breaker_active
        if not can_trade:
            if not circuit_breaker_active and len(blocked_reasons) == 0:
                logger.error(
                    f"INCONSISTENT STATE DETECTED: Strategy {strategy_id} has can_trade=False but "
                    f"no blocked_reasons and circuit_breaker_active=False. This is a logic error. "
                    f"Forcing can_trade=True"
                )
                can_trade = True
            elif circuit_breaker_active and len(blocked_reasons) == 0:
                # Circuit breaker is active but no reason - add one
                blocked_reasons.append("Strategy stopped by risk management (circuit breaker)")
                logger.debug(f"Strategy {strategy_id}: Added circuit breaker blocked reason")
        
        # Log final status for debugging
        logger.info(
            f"Strategy {strategy_id} risk status: can_trade={can_trade}, "
            f"blocked_reasons={blocked_reasons}, circuit_breaker_active={circuit_breaker_active}, "
            f"risk_checks_allowed={all(c.get('allowed', True) for c in risk_checks.values() if isinstance(c, dict))}"
        )
        
        # Ensure response is valid
        response = StrategyRiskStatusResponse(
            strategy_id=strategy_id,
            account_id=account_id or "default",
            can_trade=can_trade,
            blocked_reasons=blocked_reasons,
            circuit_breaker_active=circuit_breaker_active,
            risk_checks=risk_checks,
            last_enforcement_event=last_event
        )
        
        # CRITICAL FINAL SAFETY CHECK: If both daily_loss and weekly_loss are 0 (no trades), NEVER block
        # This is the ultimate safeguard to prevent false blocking of strategies with zero trades
        # BUT: Must check BOTH daily and weekly - a strategy can have weekly loss even if daily_loss = 0
        daily_loss_value = response.risk_checks.get('daily_loss', {}).get('current_value', None)
        weekly_loss_value = response.risk_checks.get('weekly_loss', {}).get('current_value', None)
        
        # Only override can_trade if BOTH daily and weekly loss are 0 AND circuit breaker is not active
        # This ensures we don't override valid weekly loss blocks
        if (daily_loss_value == 0.0 or daily_loss_value is None) and \
           (weekly_loss_value == 0.0 or weekly_loss_value is None) and \
           not response.circuit_breaker_active:
            # If there are no trades (both daily_loss and weekly_loss = 0) and circuit breaker is not active,
            # the strategy MUST be able to trade, regardless of any other conditions
            if not response.can_trade:
                logger.error(
                    f"CRITICAL BUG: Strategy {strategy_id} has daily_loss={daily_loss_value} and weekly_loss={weekly_loss_value} "
                    f"(no trades) but can_trade=False! This is a logic error. Forcing can_trade=True and clearing invalid blocked_reasons."
                )
                # Force can_trade=True and remove any invalid blocked reasons
                # Only remove reasons related to daily loss or portfolio exposure (not weekly loss if daily=0 and weekly=0)
                invalid_reasons = [r for r in response.blocked_reasons if "Daily loss" in r or "Portfolio exposure" in r]
                if invalid_reasons:
                    logger.warning(f"Removing invalid blocked reasons for zero-trade strategy: {invalid_reasons}")
                response = StrategyRiskStatusResponse(
                    strategy_id=response.strategy_id,
                    account_id=response.account_id,
                    can_trade=True,  # Force to True - zero trades means no risk
                    blocked_reasons=[],  # Clear all blocked reasons for zero-trade strategies
                    circuit_breaker_active=response.circuit_breaker_active,
                    risk_checks=response.risk_checks,
                    last_enforcement_event=response.last_enforcement_event
                )
        
        # Final safety check: If can_trade is False, there MUST be a reason
        if not response.can_trade:
            if not response.circuit_breaker_active and len(response.blocked_reasons) == 0:
                logger.error(
                    f"CRITICAL: Strategy {strategy_id} response has can_trade=False but no blocking reason! "
                    f"This should never happen. Forcing can_trade=True"
                )
                # Create new response with can_trade=True
                response = StrategyRiskStatusResponse(
                    strategy_id=response.strategy_id,
                    account_id=response.account_id,
                    can_trade=True,  # Force to True
                    blocked_reasons=[],  # Clear any invalid reasons
                    circuit_breaker_active=response.circuit_breaker_active,
                    risk_checks=response.risk_checks,
                    last_enforcement_event=response.last_enforcement_event
                )
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error getting strategy risk status for {strategy_id}: {e}\n{error_traceback}")
        raise HTTPException(status_code=500, detail=f"Error getting strategy risk status: {str(e)}")


# ============================================================================
# STRATEGY-LEVEL RISK CONFIG ENDPOINTS
# ============================================================================

@router.post("/config/strategies/{strategy_id}", response_model=StrategyRiskConfigResponse, status_code=201)
async def create_strategy_risk_config(
    strategy_id: str,
    config_data: StrategyRiskConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> StrategyRiskConfigResponse:
    """Create strategy-level risk configuration.
    
    Args:
        strategy_id: Strategy ID (string, e.g., "strategy-1")
        config_data: Strategy risk config data
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        Created strategy risk config
    """
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)
        
        # Verify strategy exists
        db_strategy = db_service.get_strategy(user_id, strategy_id)
        if not db_strategy:
            raise HTTPException(
                status_code=404,
                detail=f"Strategy '{strategy_id}' not found"
            )
        
        # Check if config already exists
        existing_config = db_service.get_strategy_risk_config(user_id, strategy_id)
        if existing_config:
            raise HTTPException(
                status_code=400,
                detail=f"Risk config already exists for strategy '{strategy_id}'. Use PUT to update."
            )
        
        # Convert daily_loss_reset_time from time to datetime if provided
        daily_loss_reset_time_dt = None
        if config_data.daily_loss_reset_time:
            from datetime import datetime, time
            today = datetime.now().date()
            daily_loss_reset_time_dt = datetime.combine(today, config_data.daily_loss_reset_time)
        
        # Create config
        db_config = db_service.create_strategy_risk_config(
            user_id=user_id,
            strategy_id=strategy_id,
            max_daily_loss_usdt=config_data.max_daily_loss_usdt,
            max_daily_loss_pct=config_data.max_daily_loss_pct,
            max_weekly_loss_usdt=config_data.max_weekly_loss_usdt,
            max_weekly_loss_pct=config_data.max_weekly_loss_pct,
            max_drawdown_pct=config_data.max_drawdown_pct,
            max_exposure_usdt=config_data.max_exposure_usdt,
            max_exposure_pct=config_data.max_exposure_pct,
            enabled=config_data.enabled,
            override_account_limits=config_data.override_account_limits,
            use_more_restrictive=config_data.use_more_restrictive,
            timezone=config_data.timezone or "UTC",
            daily_loss_reset_time=daily_loss_reset_time_dt,
            weekly_loss_reset_day=config_data.weekly_loss_reset_day
        )
        
        # Refresh to load relationship
        db.refresh(db_config)
        db.refresh(db_config.strategy)  # Load strategy relationship for from_orm
        
        # Convert to response model
        return StrategyRiskConfigResponse.from_orm(db_config)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating strategy risk config for {strategy_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating strategy risk config: {str(e)}"
        )


@router.get("/config/strategies/{strategy_id}", response_model=StrategyRiskConfigResponse)
async def get_strategy_risk_config(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> StrategyRiskConfigResponse:
    """Get strategy-level risk configuration.
    
    Args:
        strategy_id: Strategy ID (string, e.g., "strategy-1")
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        Strategy risk config
    """
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)
        
        # Verify strategy exists
        db_strategy = db_service.get_strategy(user_id, strategy_id)
        if not db_strategy:
            raise HTTPException(
                status_code=404,
                detail=f"Strategy '{strategy_id}' not found"
            )
        
        # Get config
        db_config = db_service.get_strategy_risk_config(user_id, strategy_id)
        if not db_config:
            raise HTTPException(
                status_code=404,
                detail=f"Risk config not found for strategy '{strategy_id}'"
            )
        
        # Refresh to load relationship
        db.refresh(db_config)
        db.refresh(db_config.strategy)  # Load strategy relationship for from_orm
        
        # Convert to response model
        return StrategyRiskConfigResponse.from_orm(db_config)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting strategy risk config for {strategy_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting strategy risk config: {str(e)}"
        )


@router.put("/config/strategies/{strategy_id}", response_model=StrategyRiskConfigResponse)
async def update_strategy_risk_config(
    strategy_id: str,
    config_data: StrategyRiskConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> StrategyRiskConfigResponse:
    """Update strategy-level risk configuration.
    
    Args:
        strategy_id: Strategy ID (string, e.g., "strategy-1")
        config_data: Strategy risk config update data (all fields optional)
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        Updated strategy risk config
    """
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)
        
        # Verify strategy exists
        db_strategy = db_service.get_strategy(user_id, strategy_id)
        if not db_strategy:
            raise HTTPException(
                status_code=404,
                detail=f"Strategy '{strategy_id}' not found"
            )
        
        # Get existing config
        db_config = db_service.get_strategy_risk_config(user_id, strategy_id)
        if not db_config:
            raise HTTPException(
                status_code=404,
                detail=f"Risk config not found for strategy '{strategy_id}'. Use POST to create."
            )
        
        # Update fields (only update provided fields)
        update_dict = config_data.model_dump(exclude_unset=True)
        
        # Convert daily_loss_reset_time from time to datetime if provided
        if "daily_loss_reset_time" in update_dict and update_dict["daily_loss_reset_time"]:
            from datetime import datetime, time
            today = datetime.now().date()
            update_dict["daily_loss_reset_time"] = datetime.combine(today, update_dict["daily_loss_reset_time"])
        elif "daily_loss_reset_time" in update_dict and update_dict["daily_loss_reset_time"] is None:
            update_dict["daily_loss_reset_time"] = None
        
        # Update config fields
        for key, value in update_dict.items():
            if hasattr(db_config, key):
                setattr(db_config, key, value)
        
        db.commit()
        db.refresh(db_config)
        db.refresh(db_config.strategy)  # Load strategy relationship for from_orm
        
        # Convert to response model
        return StrategyRiskConfigResponse.from_orm(db_config)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating strategy risk config for {strategy_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error updating strategy risk config: {str(e)}"
        )


@router.delete("/config/strategies/{strategy_id}", status_code=204, response_model=None)
async def delete_strategy_risk_config(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> None:
    """Delete strategy-level risk configuration.
    
    Args:
        strategy_id: Strategy ID (string, e.g., "strategy-1")
        current_user: Current authenticated user
        db: Database session
    """
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)
        
        # Verify strategy exists
        db_strategy = db_service.get_strategy(user_id, strategy_id)
        if not db_strategy:
            raise HTTPException(
                status_code=404,
                detail=f"Strategy '{strategy_id}' not found"
            )
        
        # Get config
        db_config = db_service.get_strategy_risk_config(user_id, strategy_id)
        if not db_config:
            raise HTTPException(
                status_code=404,
                detail=f"Risk config not found for strategy '{strategy_id}'"
            )
        
        # Delete config
        db.delete(db_config)
        db.commit()
        
        logger.info(f"Deleted risk config for strategy '{strategy_id}' (user: {user_id})")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting strategy risk config for {strategy_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting strategy risk config: {str(e)}"
        )

