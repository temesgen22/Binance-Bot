"""Order-related data models."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class OrderResponse(BaseModel):
    """Response model for executed orders."""

    symbol: str
    order_id: int
    status: str
    side: Literal["BUY", "SELL"]
    price: float
    avg_price: Optional[float] = None
    executed_qty: float

    class Config:
        from_attributes = True

