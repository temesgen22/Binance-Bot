"""
Tests for CircuitBreaker - Phase 3: Advanced Protection
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from uuid import uuid4

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
    # So CircuitBreaker._load_active_breakers_from_db() returns early (no account found)
    chain = Mock()
    chain.filter.return_value.first.return_value = None
    db_service.db.query.return_value = chain
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


class TestCircuitBreakerLoadFromDb:
    """Tests for _load_active_breakers_from_db (restore state after restart)."""

    def test_load_active_breakers_from_db_restores_strategy_breaker(self, mock_config, mock_strategy_runner, mock_trade_service):
        """When DB has an active strategy-level event, new CircuitBreaker reports is_active True for that strategy."""
        from uuid import uuid4
        from app.models.db_models import CircuitBreakerEvent as DBCircuitBreakerEvent, Account, Strategy

        user_id = uuid4()
        account_uuid = uuid4()
        strategy_uuid = uuid4()
        account_id_str = "default"

        mock_account = Mock(spec=Account)
        mock_account.id = account_uuid

        mock_event = Mock(spec=DBCircuitBreakerEvent)
        mock_event.breaker_scope = "strategy"
        mock_event.strategy_id = strategy_uuid
        mock_event.breaker_type = "consecutive_losses"
        mock_event.trigger_value = 5
        mock_event.threshold_value = 5
        mock_event.triggered_at = datetime.now(timezone.utc)
        mock_event.status = "active"

        mock_strategy = Mock(spec=Strategy)
        mock_strategy.strategy_id = "my_strategy"

        db = Mock()
        # Account query: filter().first() -> account
        q_account = Mock()
        q_account.filter.return_value.first.return_value = mock_account
        # Event query: filter().all() -> [event]
        q_events = Mock()
        q_events.filter.return_value.all.return_value = [mock_event]
        # Strategy query: filter().first() -> strategy
        q_strategy = Mock()
        q_strategy.filter.return_value.first.return_value = mock_strategy

        def query(model):
            if model is Account:
                return q_account
            if model is DBCircuitBreakerEvent:
                return q_events
            if model is Strategy:
                return q_strategy
            return Mock()

        db.query = query
        db_service = Mock()
        db_service.db = db

        breaker = CircuitBreaker(
            account_id=account_id_str,
            config=mock_config,
            db_service=db_service,
            user_id=user_id,
            strategy_runner=mock_strategy_runner,
            trade_service=mock_trade_service,
        )

        assert breaker.is_active(account_id_str, "my_strategy") is True
        assert breaker.is_active(account_id_str, "other_strategy") is False

    def test_load_active_breakers_from_db_restores_account_breaker(self, mock_config, mock_strategy_runner, mock_trade_service):
        """When DB has an active account-level event, new CircuitBreaker reports is_active True for any strategy."""
        from uuid import uuid4
        from app.models.db_models import CircuitBreakerEvent as DBCircuitBreakerEvent, Account

        user_id = uuid4()
        account_uuid = uuid4()
        account_id_str = "default"

        mock_account = Mock(spec=Account)
        mock_account.id = account_uuid

        mock_event = Mock(spec=DBCircuitBreakerEvent)
        mock_event.breaker_scope = "account"
        mock_event.strategy_id = None
        mock_event.breaker_type = "rapid_loss"
        mock_event.trigger_value = 0.06
        mock_event.threshold_value = 0.05
        mock_event.triggered_at = datetime.now(timezone.utc)
        mock_event.status = "active"

        db = Mock()
        q_account = Mock()
        q_account.filter.return_value.first.return_value = mock_account
        q_events = Mock()
        q_events.filter.return_value.all.return_value = [mock_event]

        def query(model):
            if model is Account:
                return q_account
            if model is DBCircuitBreakerEvent:
                return q_events
            return Mock()

        db.query = query
        db_service = Mock()
        db_service.db = db

        breaker = CircuitBreaker(
            account_id=account_id_str,
            config=mock_config,
            db_service=db_service,
            user_id=user_id,
            strategy_runner=mock_strategy_runner,
            trade_service=mock_trade_service,
        )

        assert breaker.is_active(account_id_str) is True
        assert breaker.is_active(account_id_str, "any_strategy") is True

    def test_load_active_breakers_skipped_when_no_account(self, mock_config, mock_strategy_runner, mock_trade_service):
        """When DB has no account for this account_id, no events are loaded."""
        from uuid import uuid4
        from app.models.db_models import Account

        user_id = uuid4()
        db = Mock()
        q_account = Mock()
        q_account.filter.return_value.first.return_value = None
        db.query = lambda m: q_account if m is Account else Mock()
        db_service = Mock()
        db_service.db = db

        breaker = CircuitBreaker(
            account_id="nonexistent",
            config=mock_config,
            db_service=db_service,
            user_id=user_id,
            strategy_runner=mock_strategy_runner,
            trade_service=mock_trade_service,
        )

        assert breaker.is_active("nonexistent") is False
        assert breaker.is_active("nonexistent", "s1") is False


class TestCircuitBreakerFactory:
    """Tests for CircuitBreakerFactory."""

    def test_get_circuit_breaker_returns_none_when_disabled(self):
        """Factory returns None when risk config has circuit_breaker_enabled=False."""
        from uuid import uuid4
        from app.services.circuit_breaker_factory import CircuitBreakerFactory

        risk_service = Mock()
        risk_service.get_risk_config.return_value = Mock(
            circuit_breaker_enabled=False,
            max_consecutive_losses=5,
        )
        factory = CircuitBreakerFactory(
            risk_config_service=risk_service,
            user_id=uuid4(),
        )
        assert factory.get_circuit_breaker("default") is None

    def test_get_circuit_breaker_returns_none_when_no_config(self):
        """Factory returns None when risk config is missing."""
        from uuid import uuid4
        from app.services.circuit_breaker_factory import CircuitBreakerFactory

        risk_service = Mock()
        risk_service.get_risk_config.return_value = None
        factory = CircuitBreakerFactory(
            risk_config_service=risk_service,
            user_id=uuid4(),
        )
        assert factory.get_circuit_breaker("default") is None

    def test_get_circuit_breaker_returns_breaker_when_enabled(self, mock_db_service):
        """Factory returns a CircuitBreaker when enabled and config present."""
        from uuid import uuid4
        from app.services.circuit_breaker_factory import CircuitBreakerFactory

        risk_service = Mock()
        risk_service.get_risk_config.return_value = Mock(
            circuit_breaker_enabled=True,
            max_consecutive_losses=5,
            rapid_loss_threshold_pct=0.05,
            rapid_loss_timeframe_minutes=60,
        )
        factory = CircuitBreakerFactory(
            risk_config_service=risk_service,
            user_id=uuid4(),
            db_service=mock_db_service,
        )
        breaker = factory.get_circuit_breaker("default")
        assert breaker is not None
        assert breaker.account_id == "default"
        assert breaker.is_active("default") is False

    def test_get_circuit_breaker_caches_by_account(self, mock_db_service):
        """Same account returns same breaker instance (cached)."""
        from uuid import uuid4
        from app.services.circuit_breaker_factory import CircuitBreakerFactory

        risk_service = Mock()
        risk_service.get_risk_config.return_value = Mock(
            circuit_breaker_enabled=True,
            max_consecutive_losses=5,
        )
        factory = CircuitBreakerFactory(
            risk_config_service=risk_service,
            user_id=uuid4(),
            db_service=mock_db_service,
        )
        b1 = factory.get_circuit_breaker("default")
        b2 = factory.get_circuit_breaker("default")
        assert b1 is b2


class TestCircuitBreakerOrderManagerIntegration:
    """Tests that order manager blocks orders when circuit breaker is active."""

    @pytest.mark.asyncio
    async def test_execute_order_raises_when_circuit_breaker_active(self):
        """StrategyOrderManager.execute_order raises CircuitBreakerActiveError when breaker is active."""
        from app.services.strategy_order_manager import StrategyOrderManager
        from app.services.strategy_account_manager import StrategyAccountManager
        from app.models.strategy import StrategySummary
        from app.strategies.base import StrategySignal

        mock_breaker = Mock()
        mock_breaker.is_active = Mock(return_value=True)

        class FakeFactory:
            get_circuit_breaker = Mock(return_value=mock_breaker)
        factory = FakeFactory()

        account_manager = Mock(spec=StrategyAccountManager)
        account_manager.get_account_client = Mock(return_value=Mock())

        summary = Mock(spec=StrategySummary)
        summary.id = "strat_1"
        summary.symbol = "BTCUSDT"
        summary.account_id = "default"
        summary.leverage = 10
        summary.position_side = None
        summary.position_size = 0.0
        summary.entry_price = None
        summary.fixed_amount = 100.0
        summary.risk_per_trade = 0.01
        summary.name = "Test"
        from app.models.strategy import StrategyState
        summary.status = StrategyState.running

        order_manager = StrategyOrderManager(
            account_manager=account_manager,
            default_risk=Mock(),
            default_executor=Mock(),
            trade_service=Mock(),
            user_id=uuid4(),
            strategy_service=Mock(),
            strategies={},
            trades={},
            circuit_breaker_factory=factory,
        )

        signal = StrategySignal(action="BUY", symbol="BTCUSDT", confidence=1.0)

        with pytest.raises(CircuitBreakerActiveError) as exc_info:
            await order_manager.execute_order(
                signal=signal,
                summary=summary,
                risk=Mock(),
                executor=Mock(),
                klines=None,
            )

        assert "default" in str(exc_info.value)
        assert exc_info.value.account_id == "default"
        assert exc_info.value.strategy_id == "strat_1"
        factory.get_circuit_breaker.assert_called_once_with("default")
        mock_breaker.is_active.assert_called_with("default", "strat_1")

    @pytest.mark.asyncio
    async def test_execute_order_proceeds_when_circuit_breaker_inactive(self):
        """StrategyOrderManager.execute_order does not raise when breaker is inactive."""
        from app.services.strategy_order_manager import StrategyOrderManager
        from app.services.strategy_account_manager import StrategyAccountManager
        from app.models.strategy import StrategySummary
        from app.strategies.base import StrategySignal

        mock_breaker = Mock()
        mock_breaker.is_active = Mock(return_value=False)

        class FakeFactoryInactive:
            get_circuit_breaker = Mock(return_value=mock_breaker)
        factory = FakeFactoryInactive()

        account_manager = Mock(spec=StrategyAccountManager)
        account_manager.get_account_client = Mock(return_value=Mock())

        summary = Mock(spec=StrategySummary)
        summary.id = "strat_1"
        summary.symbol = "BTCUSDT"
        summary.account_id = "default"
        summary.leverage = 10
        summary.position_side = None
        summary.position_size = 0.0
        summary.entry_price = None
        summary.fixed_amount = 100.0
        summary.risk_per_trade = 0.01
        summary.name = "Test"
        from app.models.strategy import StrategyState
        summary.status = StrategyState.running

        order_manager = StrategyOrderManager(
            account_manager=account_manager,
            default_risk=Mock(),
            default_executor=Mock(),
            trade_service=Mock(),
            user_id=uuid4(),
            strategy_service=Mock(),
            strategies={},
            trades={},
            circuit_breaker_factory=factory,
        )

        signal = StrategySignal(action="BUY", symbol="BTCUSDT", confidence=1.0)
        try:
            await order_manager.execute_order(
                signal=signal,
                summary=summary,
                risk=Mock(),
                executor=Mock(),
                klines=None,
            )
        except CircuitBreakerActiveError:
            pytest.fail("CircuitBreakerActiveError should not be raised when breaker is inactive")
        except Exception:
            pass  # Other errors (e.g. client, leverage) are expected with mocks
