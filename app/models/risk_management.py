"""Risk management data models."""

from __future__ import annotations

from datetime import datetime, time
from typing import List, Literal, Optional
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskManagementConfigBase(BaseModel):
    """Base risk management configuration model."""
    
    # Portfolio Limits
    max_portfolio_exposure_usdt: Optional[float] = Field(
        default=None, 
        ge=0, 
        description="Maximum total portfolio exposure in USDT"
    )
    max_portfolio_exposure_pct: Optional[float] = Field(
        default=None, 
        ge=0, 
        le=1, 
        description="Maximum portfolio exposure as percentage of balance (0-1)"
    )
    max_daily_loss_usdt: Optional[float] = Field(
        default=None, 
        ge=0, 
        description="Maximum daily loss in USDT"
    )
    max_daily_loss_pct: Optional[float] = Field(
        default=None, 
        ge=0, 
        le=1, 
        description="Maximum daily loss as percentage of balance (0-1)"
    )
    max_weekly_loss_usdt: Optional[float] = Field(
        default=None, 
        ge=0, 
        description="Maximum weekly loss in USDT"
    )
    max_weekly_loss_pct: Optional[float] = Field(
        default=None, 
        ge=0, 
        le=1, 
        description="Maximum weekly loss as percentage of balance (0-1)"
    )
    max_drawdown_pct: Optional[float] = Field(
        default=None, 
        ge=0, 
        le=1, 
        description="Maximum drawdown percentage (0-1)"
    )
    
    # Loss Reset Configuration
    daily_loss_reset_time: Optional[time] = Field(
        default=None, 
        description="UTC time when daily loss counter resets (e.g., 00:00:00)"
    )
    weekly_loss_reset_day: Optional[int] = Field(
        default=1, 
        ge=1, 
        le=7, 
        description="Day of week when weekly loss counter resets (1=Monday, 7=Sunday)"
    )
    timezone: str = Field(
        default="UTC", 
        description="Timezone for loss reset calculations"
    )
    
    # Circuit Breaker Settings
    circuit_breaker_enabled: bool = Field(
        default=False, 
        description="Enable circuit breakers"
    )
    max_consecutive_losses: int = Field(
        default=5, 
        ge=1, 
        le=100, 
        description="Maximum consecutive losses before circuit breaker triggers"
    )
    rapid_loss_threshold_pct: float = Field(
        default=0.05, 
        ge=0, 
        le=1, 
        description="Rapid loss threshold as percentage (e.g., 0.05 = 5%)"
    )
    rapid_loss_timeframe_minutes: int = Field(
        default=60, 
        ge=1, 
        le=1440, 
        description="Timeframe in minutes for rapid loss detection"
    )
    circuit_breaker_cooldown_minutes: int = Field(
        default=60, 
        ge=1, 
        le=10080, 
        description="Cooldown period in minutes before circuit breaker can be resolved"
    )
    
    # Dynamic Risk Settings
    volatility_based_sizing_enabled: bool = Field(
        default=False, 
        description="Enable volatility-based position sizing"
    )
    performance_based_adjustment_enabled: bool = Field(
        default=False, 
        description="Enable performance-based risk adjustment"
    )
    kelly_criterion_enabled: bool = Field(
        default=False, 
        description="Enable Kelly Criterion position sizing"
    )
    kelly_fraction: float = Field(
        default=0.25, 
        ge=0, 
        le=1, 
        description="Kelly fraction to use (e.g., 0.25 = quarter Kelly)"
    )
    
    # Correlation Limits
    correlation_limits_enabled: bool = Field(
        default=False, 
        description="Enable correlation-based exposure limits"
    )
    max_correlation_exposure_pct: float = Field(
        default=0.5, 
        ge=0, 
        le=1, 
        description="Maximum exposure to correlated assets as percentage (0-1)"
    )
    
    # Margin Protection
    margin_call_protection_enabled: bool = Field(
        default=True, 
        description="Enable margin call protection"
    )
    min_margin_ratio: float = Field(
        default=0.1, 
        ge=0, 
        le=1, 
        description="Minimum margin ratio threshold (e.g., 0.1 = 10%)"
    )
    
    # Trade Frequency Limits
    max_trades_per_day_per_strategy: Optional[int] = Field(
        default=None, 
        ge=1, 
        description="Maximum trades per day per strategy"
    )
    max_trades_per_day_total: Optional[int] = Field(
        default=None, 
        ge=1, 
        description="Maximum total trades per day across all strategies"
    )
    
    # Order Size Adjustment
    auto_reduce_order_size: bool = Field(
        default=False, 
        description="Automatically reduce order size if it would breach limits (instead of rejecting)"
    )


class RiskManagementConfigCreate(RiskManagementConfigBase):
    """Request model for creating risk management configuration."""
    account_id: str = Field(..., description="Binance account ID")


class RiskManagementConfigUpdate(RiskManagementConfigBase):
    """Request model for updating risk management configuration."""
    pass  # All fields are optional for updates


class RiskManagementConfigResponse(RiskManagementConfigBase):
    """Response model for risk management configuration."""
    id: str = Field(..., description="Configuration ID")
    user_id: str = Field(..., description="User ID")
    account_id: str = Field(..., description="Binance account ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    model_config = ConfigDict(from_attributes=True)


class RiskMetricsResponse(BaseModel):
    """Response model for risk metrics."""
    id: str
    user_id: str
    account_id: str
    timestamp: datetime
    
    # Balance Tracking
    total_balance_usdt: Optional[float] = None
    available_balance_usdt: Optional[float] = None
    used_margin_usdt: Optional[float] = None
    peak_balance_usdt: Optional[float] = None
    peak_balance_timestamp: Optional[datetime] = None
    
    # Portfolio Metrics
    total_exposure_usdt: Optional[float] = None
    total_exposure_pct: Optional[float] = None
    daily_pnl_usdt: Optional[float] = None
    daily_pnl_pct: Optional[float] = None
    weekly_pnl_usdt: Optional[float] = None
    weekly_pnl_pct: Optional[float] = None
    current_drawdown_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    
    # Performance Metrics
    sharpe_ratio: Optional[float] = None
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    
    # Risk Status
    risk_status: Optional[Literal["normal", "warning", "breach", "paused"]] = None
    active_circuit_breakers: Optional[List[str]] = None
    meta_data: Optional[dict] = None
    
    model_config = ConfigDict(from_attributes=True)


class CircuitBreakerEventResponse(BaseModel):
    """Response model for circuit breaker event."""
    id: str
    user_id: str
    account_id: str
    strategy_id: Optional[str] = None
    breaker_type: str
    breaker_scope: Literal["account", "strategy"]
    trigger_value: float
    threshold_value: float
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    status: Literal["active", "resolved", "manual_override"]
    meta_data: Optional[dict] = None
    
    model_config = ConfigDict(from_attributes=True)


class PortfolioRiskStatusResponse(BaseModel):
    """Response model for current portfolio risk status."""
    account_id: str
    risk_status: Literal["normal", "warning", "breach", "paused"]
    
    # Current Metrics
    total_exposure_usdt: float
    total_exposure_pct: float
    max_exposure_usdt: Optional[float] = None
    max_exposure_pct: Optional[float] = None
    
    # Loss Tracking
    daily_pnl_usdt: float
    daily_pnl_pct: float
    max_daily_loss_usdt: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    
    weekly_pnl_usdt: float
    weekly_pnl_pct: float
    max_weekly_loss_usdt: Optional[float] = None
    max_weekly_loss_pct: Optional[float] = None
    
    # Drawdown
    current_drawdown_pct: float
    max_drawdown_pct: float
    max_drawdown_limit_pct: Optional[float] = None
    
    # Active Circuit Breakers
    active_circuit_breakers: List[str] = Field(default_factory=list)
    
    # Warnings
    warnings: List[str] = Field(default_factory=list)


class OrderRiskCheckRequest(BaseModel):
    """Request model for checking if an order would breach risk limits."""
    account_id: str
    strategy_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    leverage: int = Field(ge=1, le=50)


class OrderRiskCheckResponse(BaseModel):
    """Response model for order risk check."""
    allowed: bool
    reason: Optional[str] = None
    adjusted_quantity: Optional[float] = None
    adjusted_notional: Optional[float] = None
    current_exposure: float
    would_be_exposure: float
    max_exposure: Optional[float] = None


class EnforcementEventResponse(BaseModel):
    """Response model for a single enforcement event."""
    id: str
    event_type: str
    event_level: str
    message: str
    strategy_id: Optional[str] = None
    account_id: Optional[str] = None
    event_metadata: Optional[dict] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class EnforcementHistoryResponse(BaseModel):
    """Response model for enforcement history."""
    events: List[EnforcementEventResponse]
    total: int
    limit: int
    offset: int


class RealTimeRiskStatusResponse(BaseModel):
    """Response model for real-time risk status."""
    account_id: str
    timestamp: datetime
    risk_status: Literal["normal", "warning", "breach", "paused"]
    
    current_exposure: dict
    loss_limits: dict
    drawdown: dict
    circuit_breakers: dict
    recent_enforcement_events: List[dict]


class StrategyRiskStatusResponse(BaseModel):
    """Response model for strategy-specific risk status."""
    strategy_id: str
    account_id: str
    can_trade: bool
    blocked_reasons: List[str]
    circuit_breaker_active: bool
    risk_checks: dict
    last_enforcement_event: Optional[dict] = None





