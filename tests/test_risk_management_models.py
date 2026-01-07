"""Tests for risk management database models and Pydantic models."""

import pytest
from datetime import datetime, time, timezone
from uuid import uuid4

from app.models.db_models import RiskManagementConfig, RiskMetrics, CircuitBreakerEvent
from app.models.risk_management import (
    RiskManagementConfigCreate,
    RiskManagementConfigUpdate,
    RiskManagementConfigResponse,
)


def test_risk_management_config_create_model():
    """Test RiskManagementConfigCreate model validation."""
    config = RiskManagementConfigCreate(
        account_id="test_account",
        max_portfolio_exposure_pct=0.8,
        max_daily_loss_pct=0.05,
        circuit_breaker_enabled=True,
    )
    
    assert config.account_id == "test_account"
    assert config.max_portfolio_exposure_pct == 0.8
    assert config.max_daily_loss_pct == 0.05
    assert config.circuit_breaker_enabled is True
    assert config.timezone == "UTC"  # Default value


def test_risk_management_config_update_model():
    """Test RiskManagementConfigUpdate model (all fields optional)."""
    # Partial update
    config = RiskManagementConfigUpdate(
        max_daily_loss_pct=0.03,
    )
    
    assert config.max_daily_loss_pct == 0.03
    assert config.max_portfolio_exposure_pct is None  # Not provided


def test_risk_management_config_validation():
    """Test validation constraints on risk config models."""
    # Test percentage bounds
    with pytest.raises(Exception):  # Should fail validation
        RiskManagementConfigCreate(
            account_id="test",
            max_portfolio_exposure_pct=1.5,  # > 1.0
        )
    
    # Test valid percentage
    config = RiskManagementConfigCreate(
        account_id="test",
        max_portfolio_exposure_pct=0.5,  # Valid
    )
    assert config.max_portfolio_exposure_pct == 0.5


def test_risk_management_config_defaults():
    """Test default values in risk config."""
    config = RiskManagementConfigCreate(
        account_id="test",
    )
    
    # Check defaults
    assert config.circuit_breaker_enabled is False
    assert config.max_consecutive_losses == 5
    assert config.rapid_loss_threshold_pct == 0.05
    assert config.kelly_fraction == 0.25
    assert config.margin_call_protection_enabled is True
    assert config.min_margin_ratio == 0.1
    assert config.timezone == "UTC"
    assert config.weekly_loss_reset_day == 1  # Monday


def test_daily_loss_reset_time():
    """Test daily loss reset time field."""
    reset_time = time(0, 0, 0)  # Midnight
    config = RiskManagementConfigCreate(
        account_id="test",
        daily_loss_reset_time=reset_time,
    )
    
    assert config.daily_loss_reset_time == reset_time


def test_risk_management_config_response():
    """Test RiskManagementConfigResponse model."""
    response = RiskManagementConfigResponse(
        id=str(uuid4()),
        user_id=str(uuid4()),
        account_id="test_account",
        max_portfolio_exposure_pct=0.8,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    assert response.account_id == "test_account"
    assert response.max_portfolio_exposure_pct == 0.8
    assert isinstance(response.created_at, datetime)
    assert isinstance(response.updated_at, datetime)










