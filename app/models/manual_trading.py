"""Pydantic models for manual trading API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ============================================
# REQUEST MODELS
# ============================================

class ManualOpenRequest(BaseModel):
    """Request to open a manual position."""
    
    symbol: str = Field(..., description="Trading symbol (e.g., 'BTCUSDT')")
    side: Literal["LONG", "SHORT"] = Field(..., description="Position side")
    usdt_amount: float = Field(..., gt=0, description="Position size in USDT (e.g., 100 for $100)")
    account_id: str = Field(default="default", description="Binance account ID")
    leverage: int = Field(default=10, ge=1, le=125, description="Leverage (1-125)")
    margin_type: Optional[Literal["CROSSED", "ISOLATED"]] = Field(
        default="CROSSED", description="Margin type"
    )
    
    # TP/SL configuration (percentage-based)
    take_profit_pct: Optional[float] = Field(
        default=None, ge=0, le=1, description="Take profit as decimal (e.g., 0.02 = 2%)"
    )
    stop_loss_pct: Optional[float] = Field(
        default=None, ge=0, le=1, description="Stop loss as decimal (e.g., 0.01 = 1%)"
    )
    
    # TP/SL configuration (price-based - takes precedence over percentage)
    tp_price: Optional[float] = Field(
        default=None, gt=0, description="Take profit price (overrides take_profit_pct)"
    )
    sl_price: Optional[float] = Field(
        default=None, gt=0, description="Stop loss price (overrides stop_loss_pct)"
    )
    
    # Trailing stop
    trailing_stop_enabled: bool = Field(default=False, description="Enable trailing stop")
    trailing_stop_callback_rate: Optional[float] = Field(
        default=None, ge=0.1, le=5.0, description="Trailing stop callback rate (0.1-5%)"
    )
    
    # Notes
    notes: Optional[str] = Field(default=None, max_length=500, description="Optional notes")
    
    model_config = ConfigDict(from_attributes=True)


class ManualCloseRequest(BaseModel):
    """Request to close a manual position."""
    
    position_id: UUID = Field(..., description="Manual position ID to close")
    quantity: Optional[float] = Field(
        default=None, gt=0, description="Quantity to close (None = full close)"
    )
    
    model_config = ConfigDict(from_attributes=True)


class ManualModifyTPSLRequest(BaseModel):
    """Request to modify TP/SL on an existing position."""
    
    position_id: UUID = Field(..., description="Manual position ID")
    
    # New TP/SL (percentage-based)
    take_profit_pct: Optional[float] = Field(
        default=None, ge=0, le=1, description="New take profit percentage"
    )
    stop_loss_pct: Optional[float] = Field(
        default=None, ge=0, le=1, description="New stop loss percentage"
    )
    
    # New TP/SL (price-based)
    tp_price: Optional[float] = Field(
        default=None, gt=0, description="New take profit price"
    )
    sl_price: Optional[float] = Field(
        default=None, gt=0, description="New stop loss price"
    )
    
    # Cancel existing orders
    cancel_tp: bool = Field(default=False, description="Cancel existing TP order")
    cancel_sl: bool = Field(default=False, description="Cancel existing SL order")
    
    # Trailing stop
    trailing_stop_enabled: Optional[bool] = Field(
        default=None, description="Enable/disable trailing stop"
    )
    trailing_stop_callback_rate: Optional[float] = Field(
        default=None, ge=0.1, le=5.0, description="Trailing stop callback rate"
    )
    
    model_config = ConfigDict(from_attributes=True)


# ============================================
# RESPONSE MODELS
# ============================================

class ManualOpenResponse(BaseModel):
    """Response after opening a manual position."""
    
    position_id: UUID = Field(..., description="New position ID")
    entry_order_id: int = Field(..., description="Binance entry order ID")
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: float
    entry_price: float
    leverage: int
    margin_type: str
    
    # TP/SL order info
    tp_order_id: Optional[int] = None
    tp_price: Optional[float] = None
    sl_order_id: Optional[int] = None
    sl_price: Optional[float] = None
    trailing_stop_enabled: bool = False
    
    # Position info
    initial_margin: Optional[float] = None
    liquidation_price: Optional[float] = None
    paper_trading: bool = False
    
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ManualCloseResponse(BaseModel):
    """Response after closing a manual position."""
    
    position_id: UUID
    exit_order_id: int
    symbol: str
    side: Literal["LONG", "SHORT"]
    closed_quantity: float
    remaining_quantity: float
    exit_price: float
    realized_pnl: float
    fee_paid: float
    exit_reason: str
    closed_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ManualModifyResponse(BaseModel):
    """Response after modifying TP/SL."""
    
    position_id: UUID
    symbol: str
    tp_order_id: Optional[int] = None
    tp_price: Optional[float] = None
    sl_order_id: Optional[int] = None
    sl_price: Optional[float] = None
    trailing_stop_enabled: bool = False
    cancelled_orders: List[int] = Field(default_factory=list)
    
    model_config = ConfigDict(from_attributes=True)


class ManualTradeResponse(BaseModel):
    """Details of a single trade within a manual position."""
    
    id: UUID
    order_id: int
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: str
    quantity: float
    price: float
    trade_type: str
    commission: Optional[float] = None
    commission_asset: Optional[str] = None
    realized_pnl: Optional[float] = None
    executed_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ManualPositionResponse(BaseModel):
    """Full details of a manual position."""
    
    id: UUID
    user_id: UUID
    account_id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: float
    remaining_quantity: Optional[float] = None
    entry_price: float
    leverage: int
    margin_type: str
    
    # Order IDs
    entry_order_id: int
    tp_order_id: Optional[int] = None
    sl_order_id: Optional[int] = None
    
    # TP/SL configuration
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    trailing_stop_enabled: bool = False
    trailing_stop_callback_rate: Optional[float] = None
    
    # Status
    status: str
    paper_trading: bool = False
    
    # Exit info (if closed)
    exit_price: Optional[float] = None
    exit_order_id: Optional[int] = None
    exit_reason: Optional[str] = None
    realized_pnl: Optional[float] = None
    fee_paid: Optional[float] = None
    funding_fee: Optional[float] = None
    
    # Current market data (enriched at runtime)
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    liquidation_price: Optional[float] = None
    initial_margin: Optional[float] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    
    # Notes
    notes: Optional[str] = None
    
    # Trade history
    trades: List[ManualTradeResponse] = Field(default_factory=list)
    
    model_config = ConfigDict(from_attributes=True)


class ManualPositionListResponse(BaseModel):
    """List of manual positions."""
    
    positions: List[ManualPositionResponse]
    total: int
    open_count: int
    closed_count: int
    
    model_config = ConfigDict(from_attributes=True)
