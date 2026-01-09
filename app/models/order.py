"""Order-related data models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class OrderResponse(BaseModel):
    """Response model for executed orders with actual Binance trade data."""

    symbol: str
    order_id: int
    status: str
    side: Literal["BUY", "SELL"]
    price: float
    avg_price: Optional[float] = None
    executed_qty: float
    orig_qty: Optional[float] = Field(
        default=None,
        description="Original order quantity from Binance (for partial fill tracking)"
    )
    
    # Actual Binance trade data fields
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Order creation/update timestamp from Binance (milliseconds converted to datetime)"
    )
    commission: Optional[float] = Field(
        default=None,
        description="Actual commission/fee paid in commissionAsset from Binance"
    )
    commission_asset: Optional[str] = Field(
        default=None,
        description="Asset used for commission (usually USDT) from Binance"
    )
    leverage: Optional[int] = Field(
        default=None,
        description="Actual leverage used for this order from Binance"
    )
    position_side: Optional[Literal["LONG", "SHORT"]] = Field(
        default=None,
        description="Position side (LONG/SHORT) from Binance order"
    )
    update_time: Optional[datetime] = Field(
        default=None,
        description="Last update timestamp from Binance (milliseconds converted to datetime)"
    )
    time_in_force: Optional[str] = Field(
        default=None,
        description="Time in force (GTC, IOC, FOK) from Binance"
    )
    order_type: Optional[str] = Field(
        default=None,
        description="Order type (MARKET, LIMIT, etc.) from Binance"
    )
    
    # Additional Binance trade parameters
    notional_value: Optional[float] = Field(
        default=None,
        description="Notional value (quantity * price) in quote currency from Binance"
    )
    cummulative_quote_qty: Optional[float] = Field(
        default=None,
        description="Cummulative quote quantity (total cost) in quote currency from Binance"
    )
    initial_margin: Optional[float] = Field(
        default=None,
        description="Initial margin required/used for this order from Binance"
    )
    margin_type: Optional[Literal["CROSSED", "ISOLATED"]] = Field(
        default=None,
        description="Margin type (CROSSED/ISOLATED) from Binance"
    )
    client_order_id: Optional[str] = Field(
        default=None,
        description="Client order ID from Binance"
    )
    working_type: Optional[str] = Field(
        default=None,
        description="Working type (MARK_PRICE/CONTRACT_PRICE) for conditional orders from Binance"
    )
    realized_pnl: Optional[float] = Field(
        default=None,
        description="Realized PnL from this order (if available from Binance user trades)"
    )
    stop_price: Optional[float] = Field(
        default=None,
        description="Stop price for stop-loss/take-profit orders from Binance"
    )
    exit_reason: Optional[str] = Field(
        default=None,
        description="Exit reason from strategy signal: TP, SL, TP_TRAILING, SL_TRAILING, EMA_CROSS, MANUAL, etc."
    )

    model_config = ConfigDict(from_attributes=True)

