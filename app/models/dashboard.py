"""Dashboard data models for aggregated performance overview."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from app.models.strategy_performance import StrategyPerformance
from app.models.trade import SymbolPnL


class DashboardOverview(BaseModel):
    """Dashboard overview summary data aggregated from multiple endpoints."""
    
    total_pnl: float = Field(description="Total portfolio PnL (realized + unrealized)")
    realized_pnl: float = Field(description="Total realized PnL from closed trades")
    unrealized_pnl: float = Field(description="Total unrealized PnL from open positions")
    pnl_change_24h: Optional[float] = Field(
        default=None,
        description="PnL change in last 24 hours (requires historical data)"
    )
    pnl_change_7d: Optional[float] = Field(
        default=None,
        description="PnL change in last 7 days (requires historical data)"
    )
    pnl_change_30d: Optional[float] = Field(
        default=None,
        description="PnL change in last 30 days (requires historical data)"
    )
    active_strategies: int = Field(description="Number of currently running strategies")
    total_strategies: int = Field(description="Total number of strategies")
    total_trades: int = Field(description="Total number of trades across all strategies")
    completed_trades: int = Field(description="Total number of completed trades")
    overall_win_rate: float = Field(description="Overall win rate percentage across all strategies")
    best_strategy: Optional[StrategyPerformance] = Field(
        default=None,
        description="Best performing strategy by total PnL"
    )
    worst_strategy: Optional[StrategyPerformance] = Field(
        default=None,
        description="Worst performing strategy by total PnL"
    )
    top_symbol: Optional[SymbolPnL] = Field(
        default=None,
        description="Top performing symbol by total PnL"
    )
    account_balance: Optional[float] = Field(
        default=None,
        description="Account balance from Binance (if available)"
    )
    total_trade_fees: Optional[float] = Field(
        default=None,
        description="Total trading fees paid across all completed trades"
    )
    total_funding_fees: Optional[float] = Field(
        default=None,
        description="Total funding fees paid across all completed trades"
    )
    pnl_timeline: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Time series data for PnL chart (list of {timestamp, pnl} objects)"
    )


class DateRange(BaseModel):
    """Date range for filtering comparison data."""
    start: Optional[datetime] = Field(default=None, description="Start date/time")
    end: Optional[datetime] = Field(default=None, description="End date/time")


class ComparisonMetric(BaseModel):
    """Individual metric comparison across strategies."""
    name: str = Field(description="Metric name (e.g., 'total_pnl', 'win_rate')")
    unit: str = Field(description="Metric unit (e.g., 'USD', '%', 'count')")
    values: Dict[str, float] = Field(description="Strategy ID to metric value mapping")
    best_strategy_id: Optional[str] = Field(default=None, description="Strategy ID with best value")
    worst_strategy_id: Optional[str] = Field(default=None, description="Strategy ID with worst value")
    average: float = Field(description="Average value across all strategies")
    median: float = Field(description="Median value across all strategies")


class ComparisonSummary(BaseModel):
    """Summary statistics for strategy comparison."""
    total_strategies: int = Field(description="Number of strategies being compared")
    best_overall_strategy: Optional[str] = Field(default=None, description="Best strategy by total PnL (strategy_id)")
    most_consistent_strategy: Optional[str] = Field(default=None, description="Most consistent strategy by win rate (strategy_id)")
    most_active_strategy: Optional[str] = Field(default=None, description="Most active strategy by trade count (strategy_id)")
    riskiest_strategy: Optional[str] = Field(default=None, description="Riskiest strategy by leverage/risk (strategy_id)")


class StrategyComparisonResponse(BaseModel):
    """Response model for strategy comparison endpoint."""
    strategies: List[StrategyPerformance] = Field(description="List of strategies with performance metrics")
    comparison_metrics: Dict[str, ComparisonMetric] = Field(description="Comparison metrics keyed by metric name")
    date_range: Optional[DateRange] = Field(default=None, description="Date range used for comparison")
    summary: ComparisonSummary = Field(description="Summary statistics for the comparison")
