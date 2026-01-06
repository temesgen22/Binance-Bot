"""
Tests for CircuitBreaker - Phase 3: Advanced Protection
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.risk.circuit_breaker import CircuitBreaker, CircuitBreakerState
from app.models.risk_management import RiskManagementConfigResponse
from app.core.exceptions import CircuitBreakerActiveError


@pytest.fixture
def mock_config():
    """Create a mock risk management config."""
    config = Mock(spec=RiskManagementConfigResponse)
    config.circuit_breaker_enabled = True
    config.max_consecutive_losses = 5
    config.rapid_loss_threshold_pct = 0.05  # 5%
    return config


@pytest.fixture
def mock_db_service():
    """Create a mock database service."""
    db_service = Mock()
    db_service.db = Mock()
    db_service.db.query = Mock()
    db_service.db.add = Mock()
    db_service.db.commit = Mock()
    return db_service


@pytest.fixture
def mock_strategy_runner():
    """Create a mock strategy runner."""
    runner = Mock()
    runner._strategies = {}
    runner.state_manager = Mock()
    runner.state_manager.update_strategy_in_db = Mock()
    return runner


@pytest.fixture
def mock_trade_service():
    """Create a mock trade service."""
    return Mock()


@pytest.fixture
def circuit_breaker(mock_config, mock_db_service, mock_strategy_runner, mock_trade_service):
    """Create a CircuitBreaker instance."""
    from uuid import uuid4
    
    return CircuitBreaker(
        account_id="test_account",
        config=mock_config,
        db_service=mock_db_service,
        user_id=uuid4(),
        strategy_runner=mock_strategy_runner,
        trade_service=mock_trade_service
    )


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""
    
    def test_is_active_no_breakers(self, circuit_breaker):
        """Test is_active returns False when no breakers are active."""
        assert circuit_breaker.is_active("test_account") is False
        assert circuit_breaker.is_active("test_account", "strategy_1") is False
    
    def test_consecutive_losses_trigger(self, circuit_breaker):
        """Test consecutive loss circuit breaker triggers."""
        strategy_id = "test_strategy"
        
        # Create mock trades with 5 consecutive losses
        trades = []
        for i in range(5):
            trade = Mock()
            trade.net_pnl = -10.0 * (i + 1)  # All losses
            trades.append(trade)
        
        # Check for consecutive losses
        breaker_state = circuit_breaker.check_consecutive_losses(strategy_id, trades)
        
        assert breaker_state is not None
        assert breaker_state.breaker_type == "consecutive_losses"
        assert breaker_state.scope == "strategy"
        assert breaker_state.trigger_value == 5
        assert breaker_state.status == "active"
        assert breaker_state.strategy_id == strategy_id
    
    def test_consecutive_losses_no_trigger(self, circuit_breaker):
        """Test consecutive loss breaker doesn't trigger with fewer losses."""
        strategy_id = "test_strategy"
        
        # Create mock trades with only 3 losses
        trades = []
        for i in range(3):
            trade = Mock()
            trade.net_pnl = -10.0
            trades.append(trade)
        
        # Check for consecutive losses
        breaker_state = circuit_breaker.check_consecutive_losses(strategy_id, trades)
        
        # Should not trigger (below threshold of 5)
        assert breaker_state is None
    
    def test_consecutive_losses_win_breaks_streak(self, circuit_breaker):
        """Test that a win breaks the consecutive loss streak."""
        strategy_id = "test_strategy"
        
        # Create mock trades: 4 losses, then 1 win
        trades = []
        for i in range(4):
            trade = Mock()
            trade.net_pnl = -10.0
            trades.append(trade)
        
        # Add a win
        win_trade = Mock()
        win_trade.net_pnl = 20.0
        trades.append(win_trade)
        
        # Check for consecutive losses
        breaker_state = circuit_breaker.check_consecutive_losses(strategy_id, trades)
        
        # Should not trigger (win broke the streak)
        assert breaker_state is None
    
    def test_rapid_loss_trigger(self, circuit_breaker):
        """Test rapid loss circuit breaker triggers."""
        account_id = "test_account"
        
        # Mock account balance
        circuit_breaker._get_account_balance = Mock(return_value=10000.0)
        
        # Mock realized PnL showing 6% loss (above 5% threshold)
        circuit_breaker._get_realized_pnl = Mock(return_value=-600.0)
        
        # Check for rapid loss
        breaker_state = circuit_breaker.check_rapid_loss(account_id, time_window_minutes=60)
        
        assert breaker_state is not None
        assert breaker_state.breaker_type == "rapid_loss"
        assert breaker_state.scope == "account"
        assert breaker_state.trigger_value == pytest.approx(0.06, rel=0.01)  # 6%
        assert breaker_state.status == "active"
    
    def test_rapid_loss_no_trigger(self, circuit_breaker):
        """Test rapid loss breaker doesn't trigger with smaller loss."""
        account_id = "test_account"
        
        # Mock account balance
        circuit_breaker._get_account_balance = Mock(return_value=10000.0)
        
        # Mock realized PnL showing 3% loss (below 5% threshold)
        circuit_breaker._get_realized_pnl = Mock(return_value=-300.0)
        
        # Check for rapid loss
        breaker_state = circuit_breaker.check_rapid_loss(account_id, time_window_minutes=60)
        
        # Should not trigger
        assert breaker_state is None
    
    def test_is_active_with_active_breaker(self, circuit_breaker):
        """Test is_active returns True when breaker is active."""
        strategy_id = "test_strategy"
        
        # Trigger a breaker
        trades = []
        for i in range(5):
            trade = Mock()
            trade.net_pnl = -10.0
            trades.append(trade)
        
        circuit_breaker.check_consecutive_losses(strategy_id, trades)
        
        # Should be active
        assert circuit_breaker.is_active("test_account", strategy_id) is True
    
    def test_cooldown_expiration(self, circuit_breaker):
        """Test that cooldown expiration resolves breaker."""
        strategy_id = "test_strategy"
        
        # Trigger a breaker
        trades = []
        for i in range(5):
            trade = Mock()
            trade.net_pnl = -10.0
            trades.append(trade)
        
        breaker_state = circuit_breaker.check_consecutive_losses(strategy_id, trades)
        
        # Manually expire cooldown
        breaker_state.cooldown_until = datetime.now(timezone.utc) - timedelta(hours=1)
        
        # Should not be active (cooldown expired)
        assert circuit_breaker.is_active("test_account", strategy_id) is False
        assert breaker_state.status == "resolved"
    
    def test_resolve_breaker_manual(self, circuit_breaker):
        """Test manual breaker resolution."""
        strategy_id = "test_strategy"
        
        # Trigger a breaker
        trades = []
        for i in range(5):
            trade = Mock()
            trade.net_pnl = -10.0
            trades.append(trade)
        
        circuit_breaker.check_consecutive_losses(strategy_id, trades)
        
        # Manually resolve
        resolved = circuit_breaker.resolve_breaker(
            breaker_type="consecutive_losses",
            scope="strategy",
            strategy_id=strategy_id,
            manual=True
        )
        
        assert resolved is True
        assert circuit_breaker.is_active("test_account", strategy_id) is False
    
    def test_resolve_breaker_not_found(self, circuit_breaker):
        """Test resolving a non-existent breaker."""
        resolved = circuit_breaker.resolve_breaker(
            breaker_type="nonexistent",
            scope="strategy",
            strategy_id="nonexistent"
        )
        
        assert resolved is False
    
    def test_get_active_breakers(self, circuit_breaker):
        """Test getting all active breakers."""
        strategy_id = "test_strategy"
        
        # Trigger a breaker
        trades = []
        for i in range(5):
            trade = Mock()
            trade.net_pnl = -10.0
            trades.append(trade)
        
        circuit_breaker.check_consecutive_losses(strategy_id, trades)
        
        # Get active breakers
        active = circuit_breaker.get_active_breakers(
            account_id="test_account",
            strategy_id=strategy_id
        )
        
        assert len(active) == 1
        assert active[0].breaker_type == "consecutive_losses"
    
    def test_circuit_breaker_disabled(self, mock_db_service, mock_strategy_runner, mock_trade_service):
        """Test that circuit breaker doesn't trigger when disabled."""
        from uuid import uuid4
        
        # Create config with breaker disabled
        config = Mock(spec=RiskManagementConfigResponse)
        config.circuit_breaker_enabled = False
        
        breaker = CircuitBreaker(
            account_id="test_account",
            config=config,
            db_service=mock_db_service,
            user_id=uuid4(),
            strategy_runner=mock_strategy_runner,
            trade_service=mock_trade_service
        )
        
        strategy_id = "test_strategy"
        trades = []
        for i in range(10):  # Even 10 losses shouldn't trigger
            trade = Mock()
            trade.net_pnl = -10.0
            trades.append(trade)
        
        breaker_state = breaker.check_consecutive_losses(strategy_id, trades)
        
        # Should not trigger (disabled)
        assert breaker_state is None


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState."""
    
    def test_breaker_state_creation(self):
        """Test creating a circuit breaker state."""
        state = CircuitBreakerState(
            breaker_type="consecutive_losses",
            scope="strategy",
            triggered_at=datetime.now(timezone.utc),
            trigger_value=5,
            threshold_value=5,
            status="active",
            strategy_id="test_strategy"
        )
        
        assert state.breaker_type == "consecutive_losses"
        assert state.scope == "strategy"
        assert state.trigger_value == 5
        assert state.status == "active"
        assert state.strategy_id == "test_strategy"
    
    def test_breaker_state_with_cooldown(self):
        """Test breaker state with cooldown."""
        cooldown_until = datetime.now(timezone.utc) + timedelta(hours=1)
        
        state = CircuitBreakerState(
            breaker_type="rapid_loss",
            scope="account",
            triggered_at=datetime.now(timezone.utc),
            trigger_value=0.06,
            threshold_value=0.05,
            status="active",
            cooldown_until=cooldown_until
        )
        
        assert state.cooldown_until == cooldown_until
        assert state.status == "active"
