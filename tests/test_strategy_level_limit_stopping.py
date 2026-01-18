"""
Test cases for strategy-level and account-level daily/weekly limit stopping behavior.

Validates that:
1. Strategy-level daily/weekly limits stop only the specific strategy
2. Account-level daily/weekly limits stop all strategies in the account
3. Both daily and weekly limits use the same stopping flow
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4

from app.services.strategy_order_manager import StrategyOrderManager
from app.models.strategy import StrategySummary, StrategyState
from app.strategies.base import StrategySignal
from app.core.exceptions import RiskLimitExceededError


@pytest.fixture
def mock_strategy_runner():
    """Create a mock StrategyRunner."""
    runner = AsyncMock()
    runner.stop = AsyncMock(return_value=MagicMock(status=StrategyState.stopped))
    runner.pause_all_strategies_for_account = AsyncMock(return_value=["strategy-1", "strategy-2"])
    return runner


@pytest.fixture
def mock_portfolio_risk_manager():
    """Create a mock PortfolioRiskManager."""
    risk_manager = AsyncMock()
    risk_manager.config = MagicMock()
    risk_manager.config.auto_reduce_order_size = False
    return risk_manager


@pytest.fixture
def mock_db_service():
    """Create a mock DatabaseService."""
    db_service = MagicMock()
    db_service._is_async = False
    
    # Mock strategy object
    db_strategy = MagicMock()
    db_strategy.id = uuid4()
    db_strategy.status = "running"
    db_service.get_strategy = MagicMock(return_value=db_strategy)
    
    # Mock database session
    db_service.db = MagicMock()
    db_service.db.commit = MagicMock()
    db_service.db.refresh = MagicMock()
    
    return db_service


@pytest.fixture
def mock_account_manager():
    """Create a mock StrategyAccountManager."""
    account_manager = MagicMock()
    account_manager.get_account_config = MagicMock(return_value=MagicMock(id=uuid4()))
    return account_manager


@pytest.fixture
def mock_notification_service():
    """Create a mock NotificationService."""
    service = MagicMock()
    # Make notify methods return a coroutine
    service.notify_order_blocked_by_risk = AsyncMock()
    service.notify_circuit_breaker_triggered = AsyncMock()
    return service


@pytest.fixture
def order_manager(mock_strategy_runner, mock_portfolio_risk_manager, mock_db_service, mock_account_manager, mock_notification_service):
    """Create StrategyOrderManager with mocked dependencies."""
    # Mock strategy risk config to return None (not configured)
    mock_db_service.get_strategy_risk_config = MagicMock(return_value=None)
    mock_db_service.async_get_strategy_risk_config = AsyncMock(return_value=None)
    
    # Mock get_strategy to return a proper strategy object
    db_strategy = MagicMock()
    db_strategy.id = uuid4()
    db_strategy.status = "running"
    mock_db_service.get_strategy = MagicMock(return_value=db_strategy)
    mock_db_service.async_get_strategy = AsyncMock(return_value=db_strategy)
    
    manager = StrategyOrderManager(
        account_manager=mock_account_manager,
        trade_service=MagicMock(),
        user_id=uuid4(),
        strategy_service=MagicMock(db_service=mock_db_service),
        portfolio_risk_manager_factory=lambda account_id: mock_portfolio_risk_manager,
        strategy_runner=mock_strategy_runner,
        notification_service=mock_notification_service
    )
    manager.db_service = mock_db_service
    # Ensure strategy_runner is set (check attribute name)
    if not hasattr(manager, 'strategy_runner'):
        manager.strategy_runner = mock_strategy_runner
    return manager


@pytest.fixture
def strategy_summary():
    """Create a StrategySummary for testing."""
    from app.models.strategy import StrategyParams
    return StrategySummary(
        id="strategy-1",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type="scalping",
        status=StrategyState.running,
        account_id="test-account",
        leverage=10,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
        last_signal=None
    )


@pytest.fixture
def strategy_signal():
    """Create a StrategySignal for testing."""
    return StrategySignal(
        action="BUY",
        symbol="BTCUSDT",
        price=50000.0,
        confidence=0.8
    )


@pytest.mark.asyncio
async def test_strategy_level_daily_loss_stops_single_strategy(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_strategy_runner, mock_db_service
):
    """Test that strategy-level daily loss limit stops only the specific strategy."""
    # Setup: Strategy-level daily loss limit exceeded
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Daily loss limit exceeded (strategy): -1.50 < 1.00 USDT"
    ))
    
    # Execute order - should raise RiskLimitExceededError
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    
    # Should call stop() for this specific strategy only
    mock_strategy_runner.stop.assert_called_once_with("strategy-1")
    
    # Should NOT call pause_all_strategies_for_account (account-level)
    mock_strategy_runner.pause_all_strategies_for_account.assert_not_called()
    
    # Should update status to stopped_by_risk in database
    mock_db_service.get_strategy.assert_called()
    assert mock_db_service.db.commit.called
    assert mock_db_service.db.refresh.called


@pytest.mark.asyncio
async def test_strategy_level_weekly_loss_stops_single_strategy(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_strategy_runner, mock_db_service
):
    """Test that strategy-level weekly loss limit stops only the specific strategy."""
    # Setup: Strategy-level weekly loss limit exceeded
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Weekly loss limit exceeded (strategy): -5.50 < 5.00 USDT"
    ))
    
    # Execute order - should raise RiskLimitExceededError
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    
    # Should call stop() for this specific strategy only
    mock_strategy_runner.stop.assert_called_once_with("strategy-1")
    
    # Should NOT call pause_all_strategies_for_account
    mock_strategy_runner.pause_all_strategies_for_account.assert_not_called()
    
    # Should update status to stopped_by_risk
    mock_db_service.db.commit.assert_called()


@pytest.mark.asyncio
async def test_account_level_daily_loss_stops_all_strategies(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_strategy_runner
):
    """Test that account-level daily loss limit stops all strategies in the account."""
    # Setup: Account-level daily loss limit exceeded
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Daily loss limit exceeded: -2.50 < 2.00 USDT"
    ))
    
    # Execute order - should raise RiskLimitExceededError
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    
    # Should call pause_all_strategies_for_account (account-level)
    mock_strategy_runner.pause_all_strategies_for_account.assert_called_once_with(
        account_id="test-account",
        reason="Daily Loss limit exceeded: Daily loss limit exceeded: -2.50 < 2.00 USDT"
    )
    
    # Should NOT call stop() for individual strategy
    mock_strategy_runner.stop.assert_not_called()


@pytest.mark.asyncio
async def test_account_level_weekly_loss_stops_all_strategies(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_strategy_runner
):
    """Test that account-level weekly loss limit stops all strategies in the account."""
    # Setup: Account-level weekly loss limit exceeded
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Weekly loss limit exceeded: -10.50 < 10.00 USDT"
    ))
    
    # Execute order - should raise RiskLimitExceededError
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    
    # Should call pause_all_strategies_for_account
    mock_strategy_runner.pause_all_strategies_for_account.assert_called_once_with(
        account_id="test-account",
        reason="Weekly Loss limit exceeded: Weekly loss limit exceeded: -10.50 < 10.00 USDT"
    )
    
    # Should NOT call stop() for individual strategy
    mock_strategy_runner.stop.assert_not_called()


@pytest.mark.asyncio
async def test_strategy_level_vs_account_level_different_actions(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_strategy_runner
):
    """Test that strategy-level and account-level breaches trigger different actions."""
    # Test 1: Strategy-level breach - should stop only this strategy
    strategy_summary.status = StrategyState.running  # Ensure status is running
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Daily loss limit exceeded (strategy): -1.50 < 1.00 USDT"
    ))
    
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    
    # Strategy-level should call stop() for this strategy
    assert mock_strategy_runner.stop.call_count == 1
    assert mock_strategy_runner.pause_all_strategies_for_account.call_count == 0
    
    # Reset mocks and summary status
    mock_strategy_runner.reset_mock()
    strategy_summary.status = StrategyState.running  # Reset status for second test
    
    # Test 2: Account-level breach - should stop all strategies
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Daily loss limit exceeded: -2.50 < 2.00 USDT"
    ))
    
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    
    # Account-level should call pause_all_strategies_for_account
    assert mock_strategy_runner.stop.call_count == 0
    assert mock_strategy_runner.pause_all_strategies_for_account.call_count == 1


@pytest.mark.asyncio
async def test_daily_and_weekly_same_flow_strategy_level(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_strategy_runner
):
    """Test that daily and weekly limits use the same stopping flow for strategy-level."""
    # Test daily loss
    strategy_summary.status = StrategyState.running  # Ensure status is running
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Daily loss limit exceeded (strategy): -1.50 < 1.00 USDT"
    ))
    
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    daily_stop_calls = mock_strategy_runner.stop.call_count
    
    # Reset mocks and summary status
    mock_strategy_runner.reset_mock()
    strategy_summary.status = StrategyState.running  # Reset status for second test
    
    # Test weekly loss
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Weekly loss limit exceeded (strategy): -5.50 < 5.00 USDT"
    ))
    
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    weekly_stop_calls = mock_strategy_runner.stop.call_count
    
    # Both should call stop() once (same flow)
    assert daily_stop_calls == 1
    assert weekly_stop_calls == 1
    assert mock_strategy_runner.pause_all_strategies_for_account.call_count == 0  # Neither calls account-level pause


@pytest.mark.asyncio
async def test_daily_and_weekly_same_flow_account_level(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_strategy_runner
):
    """Test that daily and weekly limits use the same stopping flow for account-level."""
    # Test daily loss
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Daily loss limit exceeded: -2.50 < 2.00 USDT"
    ))
    
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    daily_pause_calls = mock_strategy_runner.pause_all_strategies_for_account.call_count
    
    # Reset
    mock_strategy_runner.reset_mock()
    
    # Test weekly loss
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Weekly loss limit exceeded: -10.50 < 10.00 USDT"
    ))
    
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    weekly_pause_calls = mock_strategy_runner.pause_all_strategies_for_account.call_count
    
    # Both should call pause_all_strategies_for_account once (same flow)
    assert daily_pause_calls == 1
    assert weekly_pause_calls == 1
    assert mock_strategy_runner.stop.call_count == 0  # Neither calls individual stop


@pytest.mark.asyncio
async def test_strategy_status_set_to_stopped_by_risk(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_db_service
):
    """Test that strategy status is set to stopped_by_risk when strategy-level limit is exceeded."""
    # Setup: Strategy-level limit exceeded
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Daily loss limit exceeded (strategy): -1.50 < 1.00 USDT"
    ))
    
    # Get the mock strategy object
    db_strategy = mock_db_service.get_strategy.return_value
    
    # Execute order - should raise RiskLimitExceededError
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    
    # Verify status was set to stopped_by_risk
    assert db_strategy.status == "stopped_by_risk"
    
    # Verify database commit was called
    mock_db_service.db.commit.assert_called()
    mock_db_service.db.refresh.assert_called()


@pytest.mark.asyncio
async def test_exception_handling_strategy_stop_failure(
    order_manager, strategy_summary, strategy_signal, mock_portfolio_risk_manager, mock_strategy_runner
):
    """Test that order execution continues even if strategy stop fails."""
    # Setup: Strategy-level limit exceeded
    mock_portfolio_risk_manager.check_order_allowed = AsyncMock(return_value=(
        False,
        "Daily loss limit exceeded (strategy): -1.50 < 1.00 USDT"
    ))
    
    # Make stop() raise an exception
    mock_strategy_runner.stop = AsyncMock(side_effect=Exception("Stop failed"))
    
    # Execute order - should not raise exception, but should raise RiskLimitExceededError
    with pytest.raises(RiskLimitExceededError):
        await order_manager.execute_order(strategy_signal, strategy_summary)
    
    # Should still attempt to stop the strategy
    mock_strategy_runner.stop.assert_called_once_with("strategy-1")

