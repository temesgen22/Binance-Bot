"""Strategy performance data models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from app.models.strategy import StrategySummary, StrategyStats, StrategyState, StrategyType


class StrategyPerformance(BaseModel):
    """Combined strategy information with performance metrics."""
    
    # Strategy identification
    strategy_id: str
    strategy_name: str
    symbol: str
    strategy_type: StrategyType
    status: StrategyState
    
    # Performance metrics
    total_realized_pnl: float = Field(default=0.0, description="Realized PnL from closed trades")
    total_unrealized_pnl: float = Field(default=0.0, description="Unrealized PnL from open position")
    total_pnl: float = Field(default=0.0, description="Total PnL (realized + unrealized)")
    
    # Trade statistics
    total_trades: int = Field(default=0)
    completed_trades: int = Field(default=0)
    win_rate: float = Field(default=0.0)
    winning_trades: int = Field(default=0)
    losing_trades: int = Field(default=0)
    avg_profit_per_trade: float = Field(default=0.0)
    largest_win: float = Field(default=0.0)
    largest_loss: float = Field(default=0.0)
    
    # Current position
    position_size: Optional[float] = Field(default=None)
    position_side: Optional[Literal["LONG", "SHORT"]] = Field(default=None)
    entry_price: Optional[float] = Field(default=None)
    current_price: Optional[float] = Field(default=None)
    
    # Strategy configuration
    leverage: int
    risk_per_trade: float
    fixed_amount: Optional[float] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = Field(default=None, description="When strategy was last started")
    stopped_at: Optional[datetime] = Field(default=None, description="When strategy was last stopped")
    last_trade_at: Optional[datetime] = None
    last_signal: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    
    # Ranking
    rank: Optional[int] = Field(default=None, description="Rank based on total PnL (1 = best)")
    percentile: Optional[float] = Field(default=None, description="Performance percentile (0-100)")


class StrategyPerformanceList(BaseModel):
    """List of strategy performances with ranking."""
    
    strategies: list[StrategyPerformance] = Field(default_factory=list)
    total_strategies: int = Field(default=0)
    ranked_by: str = Field(default="total_pnl", description="Field used for ranking")
    summary: Dict[str, Any] = Field(default_factory=dict, description="Overall summary statistics")

