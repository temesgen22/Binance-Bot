"""Tests for PortfolioRiskManager with async locking and exposure reservation."""

import pytest
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

from app.risk.portfolio_risk_manager import PortfolioRiskManager, ExposureReservation
from app.models.risk_management import RiskManagementConfigResponse
from app.models.strategy import StrategySummary, StrategyState, StrategyType
from app.strategies.base import StrategySignal


@pytest.fixture
def mock_risk_config():
    """Create a mock risk management configuration."""
    return RiskManagementConfigResponse(
        id=str(uuid4()),
        user_id=str(uuid4()),
        account_id="test_account",
        max_portfolio_exposure_pct=0.8,
        max_daily_loss_pct=None,  # Disable by default for tests
        max_daily_loss_usdt=None,
        max_weekly_loss_pct=None,
        max_weekly_loss_usdt=None,
        max_drawdown_pct=None,
        circuit_breaker_enabled=False,
        auto_reduce_order_size=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_strategy_runner():
    """Create a mock StrategyRunner."""
    runner = MagicMock()
    runner._strategies = {}
    runner.get_trades = MagicMock(return_value=[])
    return runner


@pytest.fixture
def portfolio_risk_manager(mock_risk_config, mock_strategy_runner):
    """Create a PortfolioRiskManager instance."""
    return PortfolioRiskManager(
        account_id="test_account",
        config=mock_risk_config,
        strategy_runner=mock_strategy_runner,
        user_id=uuid4(),
    )


@pytest.fixture
def mock_strategy_summary():
    """Create a mock strategy summary."""
    return StrategySummary(
        id="test_strategy",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        fixed_amount=100.0,
        params={},
        created_at=datetime.now(timezone.utc),
        account_id="test_account",
        current_price=50000.0,
        position_size=0.0,
        last_signal=None,  # Add required field
    )


@pytest.fixture
def mock_signal():
    """Create a mock strategy signal."""
    return StrategySignal(
        action="BUY",
        symbol="BTCUSDT",
        price=50000.0,
        confidence=1.0,  # Add required field
    )


class TestPortfolioRiskManagerAsyncLocking:
    """Tests for async locking to prevent race conditions."""
    
    @pytest.mark.asyncio
    async def test_concurrent_order_checks_are_serialized(
        self,
        portfolio_risk_manager: PortfolioRiskManager,
        mock_strategy_summary: StrategySummary,
        mock_signal: StrategySignal
    ):
        """Test that concurrent order checks are serialized by async lock."""
        # Mock exposure calculation
        portfolio_risk_manager._calculate_current_exposure = AsyncMock(return_value=0.0)
        portfolio_risk_manager._get_max_exposure = AsyncMock(return_value=1000.0)
        portfolio_risk_manager._calculate_order_exposure = MagicMock(return_value=100.0)
        
        # Create multiple concurrent checks
        async def check_order():
            return await portfolio_risk_manager.check_order_allowed(
                mock_signal,
                mock_strategy_summary,
                "test_account"
            )
        
        # Run multiple checks concurrently
        results = await asyncio.gather(*[check_order() for _ in range(5)])
        
        # All should succeed (lock serializes them)
        for allowed, reason in results:
            assert allowed is True
        
        # Verify exposure was calculated multiple times (one per check)
        assert portfolio_risk_manager._calculate_current_exposure.call_count == 5
    
    @pytest.mark.asyncio
    async def test_exposure_reservation_prevents_race_condition(
        self,
        portfolio_risk_manager: PortfolioRiskManager,
        mock_strategy_summary: StrategySummary,
        mock_signal: StrategySignal
    ):
        """Test that exposure reservation prevents race conditions."""
        # Set max exposure to 200 USDT
        portfolio_risk_manager._get_max_exposure = AsyncMock(return_value=200.0)
        portfolio_risk_manager._calculate_order_exposure = MagicMock(return_value=150.0)
        portfolio_risk_manager._get_realized_pnl = AsyncMock(return_value=0.0)
        portfolio_risk_manager._get_account_balance = AsyncMock(return_value=1000.0)
        # Mock real exposure (no actual positions)
        portfolio_risk_manager._get_real_exposure = AsyncMock(return_value=0.0)
        # Don't mock _calculate_current_exposure - let it use real implementation which includes reservations
        
        # First check should succeed and reserve 150 USDT
        allowed1, reason1 = await portfolio_risk_manager.check_order_allowed(
            mock_signal,
            mock_strategy_summary,
            "test_account"
        )
        assert allowed1 is True
        
        # Verify reservation was created
        assert "test_account" in portfolio_risk_manager._reservations
        assert "test_strategy" in portfolio_risk_manager._reservations["test_account"]
        
        # Second check should see reserved exposure and fail
        # _calculate_current_exposure will return 0 (real) + 150 (reserved) = 150
        # Then 150 + 150 (new order) = 300 > 200, so it should fail
        
        allowed2, reason2 = await portfolio_risk_manager.check_order_allowed(
            mock_signal,
            mock_strategy_summary,
            "test_account"
        )
        assert allowed2 is False
        assert "exceed" in reason2.lower()


class TestExposureReservation:
    """Tests for exposure reservation system."""
    
    @pytest.mark.asyncio
    async def test_reserve_exposure(
        self,
        portfolio_risk_manager: PortfolioRiskManager
    ):
        """Test reserving exposure."""
        await portfolio_risk_manager._reserve_exposure(
            "test_account",
            100.0,
            "strategy1"
        )
        
        # Verify reservation exists
        assert "test_account" in portfolio_risk_manager._reservations
        assert "strategy1" in portfolio_risk_manager._reservations["test_account"]
        
        reservation = portfolio_risk_manager._reservations["test_account"]["strategy1"]
        assert reservation.reserved_exposure == 100.0
        assert reservation.status == "reserved"
    
    @pytest.mark.asyncio
    async def test_confirm_exposure_full_fill(
        self,
        portfolio_risk_manager: PortfolioRiskManager
    ):
        """Test confirming exposure for full fill."""
        from app.models.order import OrderResponse
        
        # Reserve exposure
        await portfolio_risk_manager._reserve_exposure(
            "test_account",
            100.0,
            "strategy1"
        )
        
        # Confirm with full fill
        order_response = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.002,
            leverage=5,
        )
        
        await portfolio_risk_manager.confirm_exposure(
            "test_account",
            "strategy1",
            order_response
        )
        
        # Verify reservation is confirmed
        reservation = portfolio_risk_manager._reservations["test_account"]["strategy1"]
        assert reservation.status == "confirmed"
        assert reservation.order_id == 12345
    
    @pytest.mark.asyncio
    async def test_confirm_exposure_partial_fill(
        self,
        portfolio_risk_manager: PortfolioRiskManager
    ):
        """Test confirming exposure for partial fill."""
        from app.models.order import OrderResponse
        
        # Reserve exposure for 250 USDT (0.001 BTC * 50000 * 5 leverage)
        await portfolio_risk_manager._reserve_exposure(
            "test_account",
            250.0,
            "strategy1"
        )
        
        # Confirm with partial fill (50% of reserved)
        # Execute 0.0005 BTC instead of 0.001 BTC (50% fill)
        order_response = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="PARTIALLY_FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.0005,  # 50% of 0.001 BTC
            leverage=5,
        )
        
        await portfolio_risk_manager.confirm_exposure(
            "test_account",
            "strategy1",
            order_response
        )
        
        # Verify reservation is partial
        reservation = portfolio_risk_manager._reservations["test_account"]["strategy1"]
        assert reservation.status == "partial"
        # Reserved exposure should be adjusted to actual executed exposure
        # 0.0005 * 50000 * 5 = 125 USDT
        expected_exposure = 0.0005 * 50000.0 * 5
        assert abs(reservation.reserved_exposure - expected_exposure) < 0.01
    
    @pytest.mark.asyncio
    async def test_release_reservation(
        self,
        portfolio_risk_manager: PortfolioRiskManager
    ):
        """Test releasing reservation on order failure."""
        # Reserve exposure
        await portfolio_risk_manager._reserve_exposure(
            "test_account",
            100.0,
            "strategy1"
        )
        
        # Release reservation
        await portfolio_risk_manager.release_reservation(
            "test_account",
            "strategy1"
        )
        
        # Verify reservation is removed
        assert "strategy1" not in portfolio_risk_manager._reservations.get("test_account", {})


class TestPortfolioExposureCalculation:
    """Tests for portfolio exposure calculation with leverage."""
    
    @pytest.mark.asyncio
    async def test_calculate_exposure_with_leverage(
        self,
        portfolio_risk_manager: PortfolioRiskManager,
        mock_strategy_runner
    ):
        """Test that exposure calculation includes leverage."""
        # Create strategy with position
        strategy = StrategySummary(
            id="strategy1",
            name="Test",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            params={},
            created_at=datetime.now(timezone.utc),
            account_id="test_account",
            position_size=0.002,  # 0.002 BTC
            current_price=50000.0,
            last_signal=None,  # Add required field
        )
        
        mock_strategy_runner._strategies = {"strategy1": strategy}
        
        # Calculate exposure
        exposure = await portfolio_risk_manager._get_real_exposure("test_account")
        
        # Expected: 0.002 * 50000 * 5 = 500 USDT
        expected = 0.002 * 50000.0 * 5
        assert abs(exposure - expected) < 0.01
    
    @pytest.mark.asyncio
    async def test_exposure_includes_reservations(
        self,
        portfolio_risk_manager: PortfolioRiskManager
    ):
        """Test that current exposure includes reservations."""
        # Reserve exposure
        await portfolio_risk_manager._reserve_exposure(
            "test_account",
            100.0,
            "strategy1"
        )
        
        # Mock real exposure
        portfolio_risk_manager._get_real_exposure = AsyncMock(return_value=200.0)
        
        # Calculate current exposure (should include reservation)
        current = await portfolio_risk_manager._calculate_current_exposure("test_account")
        
        # Should be 200 (real) + 100 (reserved) = 300
        assert current == 300.0


class TestDailyWeeklyLossLimits:
    """Tests for daily/weekly loss limits (realized PnL only)."""
    
    @pytest.mark.asyncio
    async def test_daily_loss_limit_uses_realized_pnl(
        self,
        portfolio_risk_manager: PortfolioRiskManager,
        mock_strategy_summary: StrategySummary,
        mock_signal: StrategySignal
    ):
        """Test that daily loss limit uses realized PnL only."""
        # Mock realized PnL to be -100 USDT (loss)
        portfolio_risk_manager._get_realized_pnl = AsyncMock(return_value=-100.0)
        portfolio_risk_manager._get_account_balance = AsyncMock(return_value=1000.0)
        portfolio_risk_manager._calculate_order_exposure = MagicMock(return_value=50.0)
        portfolio_risk_manager._calculate_current_exposure = AsyncMock(return_value=0.0)
        portfolio_risk_manager._get_max_exposure = AsyncMock(return_value=1000.0)
        
        # Set daily loss limit to 50 USDT
        portfolio_risk_manager.config.max_daily_loss_usdt = 50.0
        
        # Check should fail (loss -100 > limit -50)
        allowed, reason = await portfolio_risk_manager.check_order_allowed(
            mock_signal,
            mock_strategy_summary,
            "test_account"
        )
        
        assert allowed is False
        assert "daily loss" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_weekly_loss_limit_uses_realized_pnl(
        self,
        portfolio_risk_manager: PortfolioRiskManager,
        mock_strategy_summary: StrategySummary,
        mock_signal: StrategySignal
    ):
        """Test that weekly loss limit uses realized PnL only."""
        # Mock realized PnL to be -200 USDT (loss)
        portfolio_risk_manager._get_realized_pnl = AsyncMock(return_value=-200.0)
        portfolio_risk_manager._get_account_balance = AsyncMock(return_value=1000.0)
        portfolio_risk_manager._calculate_order_exposure = MagicMock(return_value=50.0)
        portfolio_risk_manager._calculate_current_exposure = AsyncMock(return_value=0.0)
        portfolio_risk_manager._get_max_exposure = AsyncMock(return_value=1000.0)
        
        # Disable daily loss limit to test weekly limit
        portfolio_risk_manager.config.max_daily_loss_usdt = None
        portfolio_risk_manager.config.max_daily_loss_pct = None
        # Set weekly loss limit to 150 USDT
        portfolio_risk_manager.config.max_weekly_loss_usdt = 150.0
        
        # Check should fail (loss -200 > limit -150)
        allowed, reason = await portfolio_risk_manager.check_order_allowed(
            mock_signal,
            mock_strategy_summary,
            "test_account"
        )
        
        assert allowed is False
        assert "weekly loss" in reason.lower()


class TestDrawdownCalculation:
    """Tests for drawdown calculation (total equity)."""
    
    @pytest.mark.asyncio
    async def test_drawdown_uses_total_equity(
        self,
        portfolio_risk_manager: PortfolioRiskManager,
        mock_strategy_summary: StrategySummary,
        mock_signal: StrategySignal
    ):
        """Test that drawdown uses total equity (realized + unrealized)."""
        # Mock balance: current 800, peak 1000 (20% drawdown)
        portfolio_risk_manager._get_account_balance = AsyncMock(return_value=800.0)
        portfolio_risk_manager._get_peak_balance = AsyncMock(return_value=1000.0)
        portfolio_risk_manager._calculate_order_exposure = MagicMock(return_value=50.0)
        portfolio_risk_manager._calculate_current_exposure = AsyncMock(return_value=0.0)
        portfolio_risk_manager._get_max_exposure = AsyncMock(return_value=1000.0)
        portfolio_risk_manager._get_realized_pnl = AsyncMock(return_value=0.0)
        
        # Set max drawdown to 15%
        portfolio_risk_manager.config.max_drawdown_pct = 0.15
        
        # Check should fail (drawdown 20% > limit 15%)
        allowed, reason = await portfolio_risk_manager.check_order_allowed(
            mock_signal,
            mock_strategy_summary,
            "test_account"
        )
        
        assert allowed is False
        assert "drawdown" in reason.lower()


class TestExposureLimit:
    """Tests for portfolio exposure limits."""
    
    @pytest.mark.asyncio
    async def test_exposure_limit_check(
        self,
        portfolio_risk_manager: PortfolioRiskManager,
        mock_strategy_summary: StrategySummary,
        mock_signal: StrategySignal
    ):
        """Test that exposure limit is checked."""
        # Mock current exposure: 700 USDT
        portfolio_risk_manager._calculate_current_exposure = AsyncMock(return_value=700.0)
        portfolio_risk_manager._get_max_exposure = AsyncMock(return_value=800.0)
        portfolio_risk_manager._calculate_order_exposure = MagicMock(return_value=150.0)
        portfolio_risk_manager._get_realized_pnl = AsyncMock(return_value=0.0)
        
        # Check should fail (700 + 150 = 850 > 800)
        allowed, reason = await portfolio_risk_manager.check_order_allowed(
            mock_signal,
            mock_strategy_summary,
            "test_account"
        )
        
        assert allowed is False
        assert "exceed" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_exposure_limit_with_reservation(
        self,
        portfolio_risk_manager: PortfolioRiskManager,
        mock_strategy_summary: StrategySummary,
        mock_signal: StrategySignal
    ):
        """Test that reservations are included in exposure calculation."""
        # Reserve 100 USDT
        await portfolio_risk_manager._reserve_exposure(
            "test_account",
            100.0,
            "strategy1"
        )
        
        # Mock real exposure: 600 USDT
        portfolio_risk_manager._get_real_exposure = AsyncMock(return_value=600.0)
        portfolio_risk_manager._get_max_exposure = AsyncMock(return_value=800.0)
        portfolio_risk_manager._calculate_order_exposure = MagicMock(return_value=150.0)
        portfolio_risk_manager._get_realized_pnl = AsyncMock(return_value=0.0)
        
        # Current exposure = 600 (real) + 100 (reserved) = 700
        # New order = 150
        # Total = 850 > 800 (should fail)
        allowed, reason = await portfolio_risk_manager.check_order_allowed(
            mock_signal,
            mock_strategy_summary,
            "test_account"
        )
        
        assert allowed is False
        assert "exceed" in reason.lower()

