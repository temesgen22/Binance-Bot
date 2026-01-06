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

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from app.risk.metrics_calculator import RiskMetricsCalculator, RiskMetrics
from app.risk.portfolio_risk_manager import PortfolioRiskManager
from app.risk.circuit_breaker import CircuitBreaker
from app.risk.margin_manager import MarginManager
from app.services.risk_management_service import RiskManagementService
from app.services.trade_service import TradeService
from app.services.strategy_service import StrategyService
from app.models.risk_management import (
    PortfolioRiskStatusResponse,
    RiskManagementConfigCreate,
    RiskManagementConfigUpdate,
    RiskManagementConfigResponse
)
from sqlalchemy.orm import Session
from app.models.db_models import User

# Import dependencies from the correct location
from app.api.deps import get_current_user, get_db_session_dependency


router = APIRouter(prefix="/api/risk", tags=["risk-metrics"])


@router.get("/metrics/strategy/{strategy_id}")
async def get_strategy_risk_metrics(
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
        trade_service = TradeService(db=db)
        trades = trade_service.get_strategy_trades(user_id, UUID(strategy_id), limit=10000)
        
        if not trades:
            return {
                "strategy_id": strategy_id,
                "metrics": None,
                "message": "No trades found for this strategy"
            }
        
        # Convert trades to format expected by calculator
        trade_data = []
        for trade in trades:
            trade_data.append({
                "pnl": float(trade.realized_pnl or 0),
                "timestamp": trade.timestamp or datetime.now(timezone.utc),
            })
        
        # Get initial balance (from first trade or account)
        initial_balance = 10000.0  # TODO: Get from account history
        current_balance = 10000.0  # TODO: Get current balance
        
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
        trade_service = TradeService(db=db)
        if account_id:
            trades = trade_service.get_trades_by_account(user_id, account_id)
        else:
            trades = trade_service.get_all_trades(user_id)
        
        if not trades:
            return {
                "account_id": account_id,
                "metrics": None,
                "message": "No trades found"
            }
        
        # Convert trades to format expected by calculator
        trade_data = []
        for trade in trades:
            trade_data.append({
                "pnl": float(trade.realized_pnl or 0),
                "timestamp": trade.timestamp or datetime.now(timezone.utc),
            })
        
        # Get initial and current balance
        initial_balance = 10000.0  # TODO: Get from account history
        current_balance = 10000.0  # TODO: Get current balance
        
        # Calculate metrics
        calculator = RiskMetricsCalculator(lookback_days=lookback_days)
        metrics = calculator.calculate_metrics(
            trades=trade_data,
            initial_balance=initial_balance,
            current_balance=current_balance,
        )
        
        return {
            "account_id": account_id,
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
        logger.error(f"Error calculating portfolio risk metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        risk_service = RiskManagementService(db=db)
        risk_config = risk_service.get_risk_config(user_id, account_id or "default")
        
        if not risk_config:
            return {
                "account_id": account_id,
                "status": "no_config",
                "message": "No risk configuration found"
            }
        
        # Get portfolio risk manager (would be from factory in production)
        # For now, return basic status
        return {
            "account_id": account_id,
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
        strategy = strategy_service.get_strategy(user_id, UUID(strategy_id))
        
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
        trade_service = TradeService(db=db)
        start_time = datetime.combine(report_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_time = datetime.combine(report_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        
        if account_id:
            trades = trade_service.get_trades_by_account(user_id, account_id)
        else:
            trades = trade_service.get_all_trades(user_id)
        
        # Filter to date range
        daily_trades = [
            t for t in trades
            if t.timestamp and start_time <= t.timestamp <= end_time
        ]
        
        # Calculate daily metrics
        trade_data = [{"pnl": float(t.realized_pnl or 0), "timestamp": t.timestamp} for t in daily_trades]
        
        calculator = RiskMetricsCalculator(lookback_days=1)
        metrics = calculator.calculate_metrics(
            trades=trade_data,
            initial_balance=10000.0,  # TODO: Get from account
            current_balance=10000.0,  # TODO: Get current balance
        )
        
        return {
            "date": report_date.isoformat(),
            "account_id": account_id,
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
        trade_service = TradeService(db=db)
        start_time = datetime.combine(week_start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_time = datetime.combine(week_end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        if account_id:
            trades = trade_service.get_trades_by_account(user_id, account_id)
        else:
            trades = trade_service.get_all_trades(user_id)
        
        # Filter to week range
        weekly_trades = [
            t for t in trades
            if t.timestamp and start_time <= t.timestamp <= end_time
        ]
        
        # Calculate weekly metrics
        trade_data = [{"pnl": float(t.realized_pnl or 0), "timestamp": t.timestamp} for t in weekly_trades]
        
        calculator = RiskMetricsCalculator(lookback_days=7)
        metrics = calculator.calculate_metrics(
            trades=trade_data,
            initial_balance=10000.0,  # TODO: Get from account
            current_balance=10000.0,  # TODO: Get current balance
        )
        
        return {
            "week_start": week_start_date.isoformat(),
            "week_end": week_end_date.isoformat(),
            "account_id": account_id,
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

