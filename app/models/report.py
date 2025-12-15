"""Report data models for strategy and trade reporting."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TradeReport(BaseModel):
    """Detailed trade report with entry/exit information and Binance trade parameters."""
    
    trade_id: str = Field(description="Unique trade identifier (entry order ID)")
    strategy_id: str = Field(description="Strategy ID that executed this trade")
    symbol: str = Field(description="Trading symbol (e.g., BTCUSDT)")
    side: Literal["LONG", "SHORT"] = Field(description="Position side")
    entry_time: Optional[datetime] = Field(default=None, description="Entry time from Binance")
    entry_price: float = Field(description="Entry price")
    exit_time: Optional[datetime] = Field(default=None, description="Exit time from Binance")
    exit_price: Optional[float] = Field(default=None, description="Exit price (None if still open)")
    quantity: float = Field(description="Trade quantity")
    leverage: int = Field(description="Leverage used (actual from Binance)")
    fee_paid: float = Field(default=0.0, description="Total fees paid for this trade (actual from Binance)")
    pnl_usd: float = Field(description="Profit/Loss in USD")
    pnl_pct: float = Field(description="Profit/Loss percentage")
    exit_reason: Optional[str] = Field(default=None, description="Exit reason: TP, SL, trailing_stop, manual, EMA_CROSS, etc.")
    
    # Additional Binance trade parameters
    initial_margin: Optional[float] = Field(default=None, description="Initial margin used for this trade from Binance")
    margin_type: Optional[Literal["CROSSED", "ISOLATED"]] = Field(default=None, description="Margin type (CROSSED/ISOLATED) from Binance")
    notional_value: Optional[float] = Field(default=None, description="Notional value (quantity * price) in quote currency from Binance")
    entry_order_id: Optional[int] = Field(default=None, description="Entry order ID from Binance")
    exit_order_id: Optional[int] = Field(default=None, description="Exit order ID from Binance")


class StrategyReport(BaseModel):
    """Strategy-level summary report."""
    
    strategy_id: str = Field(description="Strategy unique ID")
    strategy_name: str = Field(description="Strategy name")
    strategy_type: Optional[str] = Field(default=None, description="Strategy type (scalping, range_mean_reversion, etc.)")
    symbol: str = Field(description="Trading symbol (e.g., BTCUSDT)")
    created_at: Optional[datetime] = Field(default=None, description="Strategy creation time")
    stopped_at: Optional[datetime] = Field(default=None, description="Strategy stop time (None if still running)")
    total_trades: int = Field(description="Total number of trades")
    wins: int = Field(description="Number of winning trades")
    losses: int = Field(description="Number of losing trades")
    win_rate: float = Field(description="Win rate percentage")
    total_profit_usd: float = Field(description="Total profit from winning trades")
    total_loss_usd: float = Field(description="Total loss from losing trades")
    net_pnl: float = Field(description="Net profit/loss (total_profit - total_loss)")
    trades: List[TradeReport] = Field(default_factory=list, description="List of detailed trades")
    klines: Optional[List[List]] = Field(default=None, description="Historical candlestick data for charting")
    indicators: Optional[dict] = Field(default=None, description="Indicator data (EMA fast/slow) for charting")


class TradingReport(BaseModel):
    """Complete trading report with strategy summaries and trade details."""
    
    strategies: List[StrategyReport] = Field(description="List of strategy reports")
    total_strategies: int = Field(description="Total number of strategies in report")
    total_trades: int = Field(description="Total number of trades across all strategies")
    overall_win_rate: float = Field(description="Overall win rate percentage")
    overall_net_pnl: float = Field(description="Overall net PnL")
    report_generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Report generation timestamp")
    filters: Optional[dict] = Field(default=None, description="Applied filters for this report")

