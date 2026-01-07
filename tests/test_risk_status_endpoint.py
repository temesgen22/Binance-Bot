"""
Test cases for risk status endpoint and frontend integration.

Tests verify that:
1. Risk status endpoint returns correct data structure
2. Different strategy statuses are handled correctly
3. Circuit breaker status is properly detected
4. Risk checks are included in response
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4

from app.models.db_models import Strategy, Account, User
from app.models.strategy import StrategyState
from app.services.risk_management_service import RiskManagementService
from app.services.database_service import DatabaseService


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    return user


@pytest.fixture
def mock_account():
    """Create a mock account."""
    account = MagicMock(spec=Account)
    account.id = uuid4()
    account.account_id = "test-account-123"
    account.user_id = uuid4()
    return account


@pytest.fixture
def mock_strategy_running(mock_user, mock_account):
    """Create a mock strategy with running status."""
    strategy = MagicMock(spec=Strategy)
    strategy.id = uuid4()
    strategy.strategy_id = "test-strategy-123"
    strategy.user_id = mock_user.id
    strategy.account_id = mock_account.id
    strategy.status = "running"
    strategy.name = "Test Strategy"
    strategy.symbol = "BTCUSDT"
    return strategy


@pytest.fixture
def mock_strategy_paused_by_risk(mock_user, mock_account):
    """Create a mock strategy with paused_by_risk status."""
    strategy = MagicMock(spec=Strategy)
    strategy.id = uuid4()
    strategy.strategy_id = "test-strategy-paused"
    strategy.user_id = mock_user.id
    strategy.account_id = mock_account.id
    strategy.status = "paused_by_risk"
    strategy.name = "Paused Strategy"
    strategy.symbol = "ETHUSDT"
    return strategy


@pytest.fixture
def mock_risk_config():
    """Create a mock risk configuration."""
    config = MagicMock()
    config.max_portfolio_exposure_usdt = 10000.0
    config.max_daily_loss_usdt = -500.0
    config.max_weekly_loss_usdt = -2000.0
    config.max_drawdown_pct = 0.15
    config.circuit_breaker_enabled = True
    config.max_consecutive_losses = 5
    return config


@pytest.mark.asyncio
async def test_risk_status_endpoint_running_strategy(mock_user, mock_strategy_running, mock_account, mock_risk_config):
    """Test risk status endpoint for a running strategy."""
    from app.api.routes.risk_metrics import get_strategy_risk_status
    from fastapi import HTTPException
    
    # Mock database service
    with patch('app.api.routes.risk_metrics.DatabaseService') as MockDBService, \
         patch('app.api.routes.risk_metrics.RiskManagementService') as MockRiskService:
        
        # Setup mocks
        mock_db_service = MagicMock()
        mock_db_service.get_strategy.return_value = mock_strategy_running
        mock_db_service.get_account_by_uuid.return_value = mock_account
        mock_db_service.get_enforcement_events.return_value = ([], 0)
        MockDBService.return_value = mock_db_service
        
        mock_risk_service = MagicMock()
        mock_risk_service.get_risk_config.return_value = mock_risk_config
        MockRiskService.return_value = mock_risk_service
        
        # Mock database session
        mock_db = MagicMock()
        
        # Call endpoint
        result = await get_strategy_risk_status(
            strategy_id="test-strategy-123",
            current_user=mock_user,
            db=mock_db
        )
        
        # Verify response structure
        assert result.strategy_id == "test-strategy-123"
        assert result.account_id == "test-account-123"
        assert result.can_trade is True  # Running strategy can trade
        assert result.circuit_breaker_active is False  # Not paused
        assert len(result.blocked_reasons) == 0
        assert result.risk_checks is not None
        assert "portfolio_exposure" in result.risk_checks
        assert "daily_loss" in result.risk_checks
        assert "circuit_breaker" in result.risk_checks
        assert result.risk_checks["circuit_breaker"]["active"] is False


@pytest.mark.asyncio
async def test_risk_status_endpoint_paused_strategy(mock_user, mock_strategy_paused_by_risk, mock_account, mock_risk_config):
    """Test risk status endpoint for a paused_by_risk strategy."""
    from app.api.routes.risk_metrics import get_strategy_risk_status
    
    # Mock database service
    with patch('app.api.routes.risk_metrics.DatabaseService') as MockDBService, \
         patch('app.api.routes.risk_metrics.RiskManagementService') as MockRiskService:
        
        # Setup mocks
        mock_db_service = MagicMock()
        mock_db_service.get_strategy.return_value = mock_strategy_paused_by_risk
        mock_db_service.get_account_by_uuid.return_value = mock_account
        mock_db_service.get_enforcement_events.return_value = ([], 0)
        MockDBService.return_value = mock_db_service
        
        mock_risk_service = MagicMock()
        mock_risk_service.get_risk_config.return_value = mock_risk_config
        MockRiskService.return_value = mock_risk_service
        
        # Mock database session
        mock_db = MagicMock()
        
        # Call endpoint
        result = await get_strategy_risk_status(
            strategy_id="test-strategy-paused",
            current_user=mock_user,
            db=mock_db
        )
        
        # Verify response structure
        assert result.strategy_id == "test-strategy-paused"
        assert result.account_id == "test-account-123"
        assert result.can_trade is False  # Paused strategy cannot trade
        assert result.circuit_breaker_active is True  # Circuit breaker is active
        assert len(result.blocked_reasons) > 0
        assert "Strategy paused by risk management" in " ".join(result.blocked_reasons)
        assert result.risk_checks["circuit_breaker"]["active"] is True


@pytest.mark.asyncio
async def test_risk_status_endpoint_strategy_not_found(mock_user):
    """Test risk status endpoint when strategy is not found."""
    from app.api.routes.risk_metrics import get_strategy_risk_status
    from fastapi import HTTPException
    
    # Mock database service
    with patch('app.api.routes.risk_metrics.DatabaseService') as MockDBService:
        # Setup mocks
        mock_db_service = MagicMock()
        mock_db_service.get_strategy.return_value = None  # Strategy not found
        MockDBService.return_value = mock_db_service
        
        # Mock database session
        mock_db = MagicMock()
        
        # Call endpoint - should raise 404
        with pytest.raises(HTTPException) as exc_info:
            await get_strategy_risk_status(
                strategy_id="non-existent-strategy",
                current_user=mock_user,
                db=mock_db
            )
        
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_risk_status_endpoint_no_risk_config(mock_user, mock_strategy_running, mock_account):
    """Test risk status endpoint when no risk config exists."""
    from app.api.routes.risk_metrics import get_strategy_risk_status
    
    # Mock database service
    with patch('app.api.routes.risk_metrics.DatabaseService') as MockDBService, \
         patch('app.api.routes.risk_metrics.RiskManagementService') as MockRiskService:
        
        # Setup mocks
        mock_db_service = MagicMock()
        mock_db_service.get_strategy.return_value = mock_strategy_running
        mock_db_service.get_account_by_uuid.return_value = mock_account
        mock_db_service.get_enforcement_events.return_value = ([], 0)
        MockDBService.return_value = mock_db_service
        
        mock_risk_service = MagicMock()
        mock_risk_service.get_risk_config.return_value = None  # No risk config
        MockRiskService.return_value = mock_risk_service
        
        # Mock database session
        mock_db = MagicMock()
        
        # Call endpoint
        result = await get_strategy_risk_status(
            strategy_id="test-strategy-123",
            current_user=mock_user,
            db=mock_db
        )
        
        # Verify response - should still work with default values
        assert result.strategy_id == "test-strategy-123"
        assert result.can_trade is True
        assert result.risk_checks is not None
        # Risk checks should have None limit values when no config
        assert result.risk_checks["portfolio_exposure"]["limit_value"] is None


@pytest.mark.asyncio
async def test_risk_status_endpoint_with_enforcement_event(mock_user, mock_strategy_running, mock_account, mock_risk_config):
    """Test risk status endpoint with enforcement event history."""
    from app.api.routes.risk_metrics import get_strategy_risk_status
    from app.models.db_models import SystemEvent
    
    # Create mock enforcement event
    mock_event = MagicMock(spec=SystemEvent)
    mock_event.event_type = "ORDER_BLOCKED"
    mock_event.message = "Order blocked due to daily loss limit"
    mock_event.created_at = datetime.now(timezone.utc)
    
    # Mock database service
    with patch('app.api.routes.risk_metrics.DatabaseService') as MockDBService, \
         patch('app.api.routes.risk_metrics.RiskManagementService') as MockRiskService:
        
        # Setup mocks
        mock_db_service = MagicMock()
        mock_db_service.get_strategy.return_value = mock_strategy_running
        mock_db_service.get_account_by_uuid.return_value = mock_account
        mock_db_service.get_enforcement_events.return_value = ([mock_event], 1)
        MockDBService.return_value = mock_db_service
        
        mock_risk_service = MagicMock()
        mock_risk_service.get_risk_config.return_value = mock_risk_config
        MockRiskService.return_value = mock_risk_service
        
        # Mock database session
        mock_db = MagicMock()
        
        # Call endpoint
        result = await get_strategy_risk_status(
            strategy_id="test-strategy-123",
            current_user=mock_user,
            db=mock_db
        )
        
        # Verify response includes enforcement event
        assert result.last_enforcement_event is not None
        assert result.last_enforcement_event["event_type"] == "ORDER_BLOCKED"
        assert "daily loss limit" in result.last_enforcement_event["message"]


def test_risk_status_response_model():
    """Test that StrategyRiskStatusResponse model validates correctly."""
    from app.models.risk_management import StrategyRiskStatusResponse
    
    # Valid response
    response = StrategyRiskStatusResponse(
        strategy_id="test-123",
        account_id="account-123",
        can_trade=True,
        blocked_reasons=[],
        circuit_breaker_active=False,
        risk_checks={
            "portfolio_exposure": {
                "allowed": True,
                "current_value": 0.0,
                "limit_value": 10000.0
            },
            "daily_loss": {
                "allowed": True,
                "current_value": 0.0,
                "limit_value": -500.0
            },
            "circuit_breaker": {
                "allowed": True,
                "active": False
            }
        },
        last_enforcement_event=None
    )
    
    assert response.strategy_id == "test-123"
    assert response.can_trade is True
    assert response.circuit_breaker_active is False
    assert len(response.blocked_reasons) == 0


def test_risk_status_response_model_with_blocked():
    """Test StrategyRiskStatusResponse with blocked reasons."""
    from app.models.risk_management import StrategyRiskStatusResponse
    
    response = StrategyRiskStatusResponse(
        strategy_id="test-123",
        account_id="account-123",
        can_trade=False,
        blocked_reasons=["Strategy paused by risk management (circuit breaker)"],
        circuit_breaker_active=True,
        risk_checks={
            "circuit_breaker": {
                "allowed": False,
                "active": True
            }
        }
    )
    
    assert response.can_trade is False
    assert response.circuit_breaker_active is True
    assert len(response.blocked_reasons) == 1
    assert "circuit breaker" in response.blocked_reasons[0].lower()








