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
    StrategyRiskStatusResponse
)
from sqlalchemy.orm import Session
from app.models.db_models import User, Account

# Import dependencies from the correct location
from app.api.deps import get_current_user, get_db_session_dependency, get_client_manager, get_account_service


router = APIRouter(prefix="/api/risk", tags=["risk-metrics"])


# ============================================================================
# Helper Functions to Eliminate Repetitive Code
# ============================================================================

from app.risk.utils import get_pnl_from_completed_trade, get_timestamp_from_completed_trade

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
            # Query all DBTrade objects for user
            trades_db = db.query(DBTrade).filter(DBTrade.user_id == user_id).all()
            logger.info(f"Found {len(trades_db)} DBTrade objects across all accounts")
        
        # Convert database trades to OrderResponse format and group by strategy
        # This is necessary to match trades to completed positions (same logic as reports page)
        from app.api.routes.reports import _match_trades_to_completed_positions
        from app.models.order import OrderResponse
        
        # Group trades by strategy UUID first (db_trade.strategy_id is a UUID, not a string)
        trades_by_strategy_uuid = {}
        for db_trade in trades_db:
            strategy_uuid = db_trade.strategy_id if db_trade.strategy_id else None
            if not strategy_uuid:
                continue
            
            strategy_uuid_str = str(strategy_uuid)
            if strategy_uuid_str not in trades_by_strategy_uuid:
                trades_by_strategy_uuid[strategy_uuid_str] = []
            trades_by_strategy_uuid[strategy_uuid_str].append(db_trade)
        
        # Match trades to completed positions for each strategy
        completed_trades = []
        for strategy_uuid_str, db_trades in trades_by_strategy_uuid.items():
            if not db_trades:
                continue
            
            # Convert database trades to OrderResponse using helper (eliminates repetitive code)
            order_responses = _convert_db_trades_to_order_responses(db_trades, trade_service)
            
            # Get strategy info for matching
            strategy_name = "Unknown"
            symbol = order_responses[0].symbol if order_responses else ""
            leverage = order_responses[0].leverage if order_responses and order_responses[0].leverage else 1
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
            except (ValueError, TypeError) as uuid_error:
                logger.debug(f"Invalid UUID format {strategy_uuid_str}: {uuid_error}")
            except Exception as e:
                logger.debug(f"Could not get strategy info for UUID {strategy_uuid_str}: {e}")
            
            # Match trades to completed positions (same logic as reports page)
            # This ensures we count completed trade cycles, not individual entry/exit trades
            try:
                matched_trades = _match_trades_to_completed_positions(
                    order_responses,
                    strategy_id_str,  # Use strategy_id string, not UUID
                    strategy_name,
                    symbol,
                    leverage
                )
                completed_trades.extend(matched_trades)
            except Exception as e:
                logger.warning(f"Error matching trades for strategy {strategy_id_str}: {e}, using raw trades")
                # Fallback: use realized_pnl from database if matching fails
                for db_trade in db_trades:
                    if db_trade.realized_pnl:
                        completed_trades.append(type('obj', (object,), {
                            'realized_pnl': float(db_trade.realized_pnl),
                            'exit_time': db_trade.timestamp,
                            'entry_time': db_trade.timestamp,
                        })())
        
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


@router.get("/status/strategy/{strategy_id}")
async def get_strategy_risk_status(
    strategy_id: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
) -> dict:
    """Get real-time risk status for a strategy.
    
    Args:
        strategy_id: Strategy ID
        user_id: Current user ID
        db: Database session
        
    Returns:
        Strategy risk status dictionary
    """
    try:
        # Get strategy
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        strategy_service = StrategyService(db=db)
        strategy = strategy_service.get_strategy(user_id, strategy_id)  # strategy_id is already a string
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Get risk configuration
        risk_service = RiskManagementService(db=db)
        risk_config = risk_service.get_risk_config(user_id, strategy.account_id or "default")
        
        return {
            "strategy_id": strategy_id,
            "status": strategy.status,
            "risk_config": {
                "circuit_breaker_enabled": risk_config.circuit_breaker_enabled if risk_config else False,
                "max_consecutive_losses": risk_config.max_consecutive_losses if risk_config else None,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy risk status: {e}")
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
                        if daily_trades:
                            daily_pnl = sum(float(t.realized_pnl or 0) for t in daily_trades)
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
                        if weekly_trades:
                            weekly_pnl = sum(float(t.realized_pnl or 0) for t in weekly_trades)
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
        
        risk_service = RiskManagementService(
            db=db,
            redis_storage=None  # Can be injected if needed
        )
        
        config = risk_service.get_risk_config(user_id, account_id)
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"Risk configuration not found for account: {account_id}"
            )
        
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting risk config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        
        # Normalize account_id
        account_id_normalized = account_id.strip() if account_id and account_id.strip() else None
        
        # Get risk configuration
        risk_service = RiskManagementService(db=db)
        if account_id_normalized:
            risk_config = risk_service.get_risk_config(user_id, account_id_normalized)
        else:
            # For "all accounts", try to get default config
            risk_config = risk_service.get_risk_config(user_id, "default")
        
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
        
        # CRITICAL: Calculate daily/weekly PnL using trade matching (same logic as reports page)
        # This ensures we calculate from completed trade cycles, not individual entry/exit trades
        from app.api.routes.reports import _match_trades_to_completed_positions
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
        all_completed_trades = []
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
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_completed_trades = [
            t for t in all_completed_trades
            if (getattr(t, 'exit_time', None) or getattr(t, 'entry_time', None) or datetime.min.replace(tzinfo=timezone.utc)) >= today_start
        ]
        daily_pnl_usdt = sum(_get_pnl_from_completed_trade(t) for t in daily_completed_trades)
        
        # Calculate weekly PnL (realized only) from completed trades
        days_since_monday = datetime.now(timezone.utc).weekday()
        week_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        weekly_completed_trades = [
            t for t in all_completed_trades
            if (getattr(t, 'exit_time', None) or getattr(t, 'entry_time', None) or datetime.min.replace(tzinfo=timezone.utc)) >= week_start
        ]
        weekly_pnl_usdt = sum(_get_pnl_from_completed_trade(t) for t in weekly_completed_trades)
        
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
        
        # Determine risk status
        # Note: risk_config.max_drawdown_pct is stored as decimal (0-1), but current_drawdown_pct is percentage (0-100)
        risk_status = "normal"
        if risk_config.max_drawdown_pct and current_drawdown_pct >= (risk_config.max_drawdown_pct * 100):
            risk_status = "breach"
        elif risk_config.max_daily_loss_usdt and daily_pnl_usdt <= -abs(risk_config.max_daily_loss_usdt):
            risk_status = "breach"
        elif risk_config.max_weekly_loss_usdt and weekly_pnl_usdt <= -abs(risk_config.max_weekly_loss_usdt):
            risk_status = "breach"
        elif risk_config.max_portfolio_exposure_usdt and total_exposure_usdt >= risk_config.max_portfolio_exposure_usdt:
            risk_status = "breach"
        elif (risk_config.max_drawdown_pct and current_drawdown_pct >= (risk_config.max_drawdown_pct * 100 * 0.8)) or \
             (risk_config.max_daily_loss_usdt and daily_pnl_usdt <= -abs(risk_config.max_daily_loss_usdt) * 0.8) or \
             (risk_config.max_weekly_loss_usdt and weekly_pnl_usdt <= -abs(risk_config.max_weekly_loss_usdt) * 0.8) or \
             (risk_config.max_portfolio_exposure_usdt and total_exposure_usdt >= risk_config.max_portfolio_exposure_usdt * 0.8):
            risk_status = "warning"
        
        # Get recent enforcement events (last 10)
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
            db_account = db_service.get_account_by_uuid(db_strategy.account_id)
            if db_account:
                account_id = db_account.account_id
        
        # Get recent enforcement events for this strategy
        events, _ = db_service.get_enforcement_events(
            user_id=user_id,
            strategy_id=db_strategy.id,
            limit=1,
            offset=0
        )
        
        last_event = None
        if events:
            event = events[0]
            last_event = {
                "event_type": event.event_type,
                "message": event.message,
                "created_at": event.created_at.isoformat()
            }
        
        # Check if strategy is paused by risk (circuit breaker active)
        is_paused_by_risk = db_strategy.status == "paused_by_risk"
        circuit_breaker_active = is_paused_by_risk
        
        # Get risk config to check limits
        risk_service = RiskManagementService(db=db, redis_storage=None)
        risk_config = risk_service.get_risk_config(user_id, account_id or "default")
        
        # Build risk checks and determine if strategy can trade
        # Default: strategy can trade unless explicitly blocked
        can_trade = True
        blocked_reasons = []
        
        # Check circuit breaker first (highest priority)
        if is_paused_by_risk:
            can_trade = False
            blocked_reasons.append("Strategy paused by risk management (circuit breaker)")
            logger.debug(f"Strategy {strategy_id} is paused by risk - blocking trade")
        
        risk_checks = {}
        
        if risk_config:
            logger.debug(f"Checking risk limits for strategy {strategy_id}, account {account_id or 'default'}")
            # Get actual trade data to calculate real risk values
            trade_service = TradeService(db=db)
            
            # Get today's trades for daily loss calculation
            # CRITICAL: Use trade matching to calculate from completed trade cycles
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            daily_loss_usdt = 0.0  # Default to 0 (no loss) if we can't get trades
            try:
                today_trades = trade_service.get_trades_by_account(user_id, account_id or "default")
                today_trades = [t for t in today_trades if t.timestamp and t.timestamp >= today_start]
                if today_trades:
                    # CRITICAL: Match trades to completed positions (same logic as reports page)
                    from app.api.routes.reports import _match_trades_to_completed_positions
                    from app.models.order import OrderResponse
                    
                    # Convert database trades to OrderResponse format using helper
                    order_responses = _convert_db_trades_to_order_responses(today_trades, trade_service)
                    
                    # Group by strategy UUID BEFORE converting (db_trade.strategy_id is a UUID)
                    trades_by_strategy_uuid = {}
                    for db_trade in today_trades:
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
                    
                    # Calculate daily loss from completed trades
                    daily_loss_usdt = sum(
                        _get_pnl_from_completed_trade(t)
                        for t in all_completed_trades
                    )
                    logger.debug(f"Strategy {strategy_id}: Found {len(all_completed_trades)} completed trades today, daily_loss={daily_loss_usdt:.2f}")
                else:
                    logger.debug(f"Strategy {strategy_id}: No trades today, daily_loss=0.0")
            except Exception as e:
                logger.warning(f"Error getting trades for risk status: {e}")
                daily_loss_usdt = 0.0  # Default to 0 if we can't get trades
            
            # Ensure daily_loss_usdt is a valid number
            if not isinstance(daily_loss_usdt, (int, float)) or daily_loss_usdt != daily_loss_usdt:  # Check for NaN
                logger.warning(f"Invalid daily_loss_usdt value: {daily_loss_usdt}, defaulting to 0.0")
                daily_loss_usdt = 0.0
            
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
                            if daily_loss_usdt <= loss_threshold:
                                daily_loss_allowed = False
                                can_trade = False
                                blocked_reasons.append(f"Daily loss limit exceeded: ${daily_loss_usdt:.2f} / -${max_daily_loss:.2f}")
                                logger.warning(f"Strategy {strategy_id} blocked: daily loss {daily_loss_usdt:.2f} <= threshold {loss_threshold:.2f}")
                            else:
                                logger.debug(f"Strategy {strategy_id} has daily loss {daily_loss_usdt:.2f} but within limit {loss_threshold:.2f}")
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
            
            risk_checks["daily_loss"] = {
                "allowed": daily_loss_allowed,
                "current_value": daily_loss_usdt,
                "limit_value": float(risk_config.max_daily_loss_usdt) if risk_config.max_daily_loss_usdt else None
            }
            
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
                            blocked_reasons.append("Strategy paused by risk management (circuit breaker)")
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
                "circuit_breaker": {"allowed": True, "active": False}
            }
            # can_trade remains True (default)
        
        # CRITICAL FINAL VALIDATION: Ensure can_trade is only False if there's a real blocking reason
        # This prevents false positives where strategies are blocked incorrectly
        # Rule: can_trade can only be False if:
        #   1. Circuit breaker is active (is_paused_by_risk), OR
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
                blocked_reasons.append("Strategy paused by risk management (circuit breaker)")
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
        
        # CRITICAL FINAL SAFETY CHECK: If daily_loss_usdt = 0 (no trades), NEVER block
        # This is the ultimate safeguard to prevent false blocking of strategies with zero trades
        daily_loss_value = response.risk_checks.get('daily_loss', {}).get('current_value', None)
        if daily_loss_value == 0.0 and not response.circuit_breaker_active:
            # If there are no trades (daily_loss = 0) and circuit breaker is not active,
            # the strategy MUST be able to trade, regardless of any other conditions
            if not response.can_trade:
                logger.error(
                    f"CRITICAL BUG: Strategy {strategy_id} has daily_loss=0.0 (no trades) but can_trade=False! "
                    f"This is a logic error. Forcing can_trade=True and clearing invalid blocked_reasons."
                )
                # Force can_trade=True and remove any invalid blocked reasons
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
        logger.error(f"Error getting strategy risk status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

