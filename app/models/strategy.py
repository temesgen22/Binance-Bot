from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class StrategyType(str, Enum):
    scalping = "scalping"
    futures = "futures"
    ema_crossover = "ema_crossover"  # EMA 5/20 Crossover Scalping


class StrategyParams(BaseModel):
    # EMA parameters (for EmaScalpingStrategy)
    ema_fast: int = Field(default=8, ge=1, le=200)
    ema_slow: int = Field(default=21, ge=2, le=400)
    # Risk management parameters
    take_profit_pct: float = Field(default=0.004, gt=0)
    stop_loss_pct: float = Field(default=0.002, gt=0)
    # Strategy execution interval
    interval_seconds: int = Field(default=10, ge=1, le=3600)
    # Kline interval for EMA Crossover strategy (1m, 5m, 15m, 1h, etc.)
    kline_interval: str = Field(default="1m", description="Candlestick interval for EMA calculation")
    # Short trading parameters
    enable_short: bool = Field(default=True, description="Enable short trading (death cross entry)")
    min_ema_separation: float = Field(default=0.0002, ge=0, description="Minimum EMA separation filter (0.0002 = 0.02% of price)")
    enable_htf_bias: bool = Field(default=True, description="Enable higher timeframe bias (5m trend check for shorts)")
    cooldown_candles: int = Field(default=2, ge=0, le=10, description="Candles to wait after exit before new entry")
    trailing_stop_enabled: bool = Field(default=False, description="Enable dynamic trailing stop loss (trails TP/SL as price moves favorably)")
    trailing_stop_activation_pct: float = Field(default=0.0, ge=0, le=0.1, description="Percentage price must move before trailing activates (e.g., 0.01 = 1%). 0 = start immediately")


class CreateStrategyRequest(BaseModel):
    name: str
    symbol: str
    strategy_type: StrategyType
    leverage: int = Field(default=5, ge=1, le=50)
    risk_per_trade: float = Field(default=0.01, gt=0, lt=1)
    fixed_amount: Optional[float] = Field(default=None, gt=0, description="Fixed USDT amount to trade per order (overrides risk_per_trade if set)")
    max_positions: int = Field(default=1, ge=1, le=5)
    params: StrategyParams = Field(default_factory=StrategyParams)
    auto_start: bool = False

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.upper()


class StrategyState(str, Enum):
    stopped = "stopped"
    running = "running"
    error = "error"


class StrategySummary(BaseModel):
    id: str
    name: str
    symbol: str
    strategy_type: StrategyType
    status: StrategyState
    leverage: int
    risk_per_trade: float
    fixed_amount: Optional[float] = None  # Fixed USDT amount (if set, overrides risk_per_trade)
    params: StrategyParams
    created_at: datetime
    last_signal: Optional[Literal["BUY", "SELL", "HOLD"]]
    entry_price: Optional[float] = None  # Price when position was opened
    current_price: Optional[float] = None  # Latest market price
    position_size: Optional[float] = None  # Current position quantity (0 if no position)
    position_side: Optional[Literal["LONG", "SHORT"]] = None  # Track current position direction
    unrealized_pnl: Optional[float] = None  # Current unrealized profit/loss
    meta: Dict[str, Any] = Field(default_factory=dict)


class StrategyStats(BaseModel):
    """Statistics for a specific strategy."""
    strategy_id: str
    strategy_name: str
    symbol: str
    total_trades: int
    completed_trades: int  # Number of complete BUY->SELL cycles
    total_pnl: float  # Total profit/loss in USDT
    win_rate: float  # Percentage of profitable trades
    winning_trades: int
    losing_trades: int
    avg_profit_per_trade: float
    largest_win: float
    largest_loss: float
    created_at: datetime
    last_trade_at: Optional[datetime] = None


class OverallStats(BaseModel):
    """Overall statistics across all strategies."""
    total_strategies: int
    active_strategies: int
    total_trades: int
    completed_trades: int
    total_pnl: float
    win_rate: float
    winning_trades: int
    losing_trades: int
    avg_profit_per_trade: float
    best_performing_strategy: Optional[str] = None
    worst_performing_strategy: Optional[str] = None
