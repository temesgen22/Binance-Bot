"""Trade and position data models for PnL tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TradeWithTimestamp(BaseModel):
    """Extended order model with timestamp for filtering."""
    
    symbol: str
    order_id: int
    status: str
    side: Literal["BUY", "SELL"]
    price: float
    avg_price: Optional[float] = None
    executed_qty: float
    timestamp: Optional[datetime] = Field(default=None, description="Trade execution timestamp")
    strategy_id: Optional[str] = Field(default=None, description="Strategy ID that executed this trade")
    strategy_name: Optional[str] = Field(default=None, description="Strategy name")
    
    class Config:
        from_attributes = True


class PositionSummary(BaseModel):
    """Summary of an open position."""
    
    symbol: str
    position_size: float
    entry_price: float
    current_price: float
    position_side: Literal["LONG", "SHORT"]
    unrealized_pnl: float
    leverage: int
    strategy_id: Optional[str] = None
    strategy_name: Optional[str] = None


class TradeSummary(BaseModel):
    """Summary of a completed trade (BUY->SELL cycle)."""
    
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    side: Literal["LONG", "SHORT"]
    realized_pnl: float
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    strategy_id: Optional[str] = None
    strategy_name: Optional[str] = None


class SymbolPnL(BaseModel):
    """Profit and Loss summary for a cryptocurrency symbol."""
    
    symbol: str
    total_realized_pnl: float = Field(default=0.0, description="Total realized PnL from closed trades")
    total_unrealized_pnl: float = Field(default=0.0, description="Total unrealized PnL from open positions")
    total_pnl: float = Field(default=0.0, description="Total PnL (realized + unrealized)")
    open_positions: list[PositionSummary] = Field(default_factory=list)
    closed_trades: list[TradeSummary] = Field(default_factory=list)
    total_trades: int = Field(default=0, description="Total number of trades (open + closed)")
    completed_trades: int = Field(default=0, description="Number of completed trade cycles")
    win_rate: float = Field(default=0.0, description="Win rate percentage")
    winning_trades: int = Field(default=0)
    losing_trades: int = Field(default=0)


class TradeFilterParams(BaseModel):
    """Parameters for filtering trades."""
    
    symbol: Optional[str] = Field(default=None, description="Filter by symbol (e.g., 'BTCUSDT')")
    start_date: Optional[datetime] = Field(default=None, description="Filter trades from this date")
    end_date: Optional[datetime] = Field(default=None, description="Filter trades until this date")
    side: Optional[Literal["BUY", "SELL"]] = Field(default=None, description="Filter by trade side")
    status: Optional[str] = Field(default=None, description="Filter by order status")
    strategy_id: Optional[str] = Field(default=None, description="Filter by strategy ID")
    min_pnl: Optional[float] = Field(default=None, description="Minimum PnL value")
    max_pnl: Optional[float] = Field(default=None, description="Maximum PnL value")

