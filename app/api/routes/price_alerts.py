"""
Price alert CRUD API for Binance-style price alerts (push when price crosses threshold).
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, field_validator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_current_user_async, get_async_db
from app.core.config import get_settings
from app.models.db_models import User, PriceAlert

router = APIRouter(prefix="/api/price-alerts", tags=["price-alerts"])

ALERT_TYPES = ("PRICE_RISES_ABOVE", "PRICE_DROPS_BELOW", "PRICE_REACHES")


# ---------- Request / Response models ----------


class CreatePriceAlertRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    alert_type: str = Field(...)
    target_price: Decimal = Field(..., gt=0)
    trigger_once: bool = True

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return (v or "").strip().upper()

    @field_validator("alert_type")
    @classmethod
    def alert_type_enum(cls, v: str) -> str:
        u = (v or "").strip().upper()
        if u not in ALERT_TYPES:
            raise ValueError(f"alert_type must be one of {ALERT_TYPES}")
        return u


class UpdatePriceAlertRequest(BaseModel):
    symbol: Optional[str] = Field(None, min_length=1, max_length=20)
    alert_type: Optional[str] = None
    target_price: Optional[Decimal] = Field(None, gt=0)
    enabled: Optional[bool] = None
    trigger_once: Optional[bool] = None

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return (v or "").strip().upper()

    @field_validator("alert_type")
    @classmethod
    def alert_type_enum(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        u = (v or "").strip().upper()
        if u not in ALERT_TYPES:
            raise ValueError(f"alert_type must be one of {ALERT_TYPES}")
        return u


class PriceAlertResponse(BaseModel):
    id: UUID
    user_id: UUID
    symbol: str
    alert_type: str
    target_price: Decimal
    enabled: bool
    last_price: Optional[Decimal] = None
    trigger_once: bool
    triggered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PriceAlertListResponse(BaseModel):
    alerts: List[PriceAlertResponse]
    count: int


# ---------- Endpoints ----------


@router.get("", response_model=PriceAlertListResponse)
async def list_price_alerts(
    enabled: Optional[bool] = Query(None, description="Filter by enabled (true/false)"),
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> PriceAlertListResponse:
    """List current user's price alerts."""
    stmt = select(PriceAlert).where(PriceAlert.user_id == current_user.id)
    if enabled is not None:
        stmt = stmt.where(PriceAlert.enabled == enabled)
    stmt = stmt.order_by(PriceAlert.created_at.desc())
    result = await db.execute(stmt)
    alerts = list(result.scalars().all())
    return PriceAlertListResponse(
        alerts=[PriceAlertResponse.model_validate(a) for a in alerts],
        count=len(alerts),
    )


@router.post("", response_model=PriceAlertResponse, status_code=status.HTTP_201_CREATED)
async def create_price_alert(
    body: CreatePriceAlertRequest,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> PriceAlertResponse:
    """Create a price alert. last_price is NULL so first run only sets last_price (Option B)."""
    settings = get_settings()
    if settings.price_alert_max_per_user is not None:
        count_stmt = select(func.count(PriceAlert.id)).where(PriceAlert.user_id == current_user.id)
        r = await db.execute(count_stmt)
        if (r.scalar() or 0) >= settings.price_alert_max_per_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum price alerts per user ({settings.price_alert_max_per_user}) reached",
            )
    alert = PriceAlert(
        user_id=current_user.id,
        symbol=body.symbol,
        alert_type=body.alert_type,
        target_price=body.target_price,
        enabled=True,
        last_price=None,
        trigger_once=body.trigger_once,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return PriceAlertResponse.model_validate(alert)


@router.get("/{alert_id}", response_model=PriceAlertResponse)
async def get_price_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> PriceAlertResponse:
    """Get one price alert by id (must belong to current user)."""
    stmt = select(PriceAlert).where(
        PriceAlert.id == alert_id,
        PriceAlert.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price alert not found")
    return PriceAlertResponse.model_validate(alert)


@router.patch("/{alert_id}", response_model=PriceAlertResponse)
async def update_price_alert(
    alert_id: UUID,
    body: UpdatePriceAlertRequest,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> PriceAlertResponse:
    """Update a price alert. If symbol is changed, last_price is reset to NULL."""
    stmt = select(PriceAlert).where(
        PriceAlert.id == alert_id,
        PriceAlert.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price alert not found")

    updates = body.model_dump(exclude_unset=True)
    symbol_changed = "symbol" in updates and updates["symbol"] != alert.symbol

    for key, value in updates.items():
        setattr(alert, key, value)
    if symbol_changed:
        alert.last_price = None

    await db.commit()
    await db.refresh(alert)
    return PriceAlertResponse.model_validate(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_price_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """Delete a price alert (must belong to current user)."""
    stmt = select(PriceAlert).where(
        PriceAlert.id == alert_id,
        PriceAlert.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price alert not found")
    await db.delete(alert)
    await db.commit()
