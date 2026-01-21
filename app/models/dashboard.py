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

