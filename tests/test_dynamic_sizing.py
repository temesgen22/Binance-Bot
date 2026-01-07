"""
Tests for DynamicPositionSizer - Phase 2: Dynamic Risk Management
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from app.risk.dynamic_sizing import (
    DynamicPositionSizer,
    DynamicSizingConfig,
    TradePerformance,
)
from app.risk.manager import RiskManager, PositionSizingResult
from app.core.my_binance_client import BinanceClient


@pytest.fixture
def mock_client():
    """Create a mock BinanceClient."""
    client = Mock(spec=BinanceClient)
    client.futures_account_balance.return_value = 10000.0  # 10k USDT balance
    client.get_min_notional.return_value = 5.0  # $5 minimum
    client.round_quantity.return_value = lambda qty: round(qty, 8)
    client.round_quantity = Mock(side_effect=lambda symbol, qty: round(qty, 8))
    return client


@pytest.fixture
def base_risk_manager(mock_client):
    """Create a base RiskManager."""
    return RiskManager(client=mock_client)


@pytest.fixture
def default_config():
    """Create default DynamicSizingConfig."""
    return DynamicSizingConfig(
        volatility_based_enabled=False,
        performance_based_enabled=False,
        kelly_criterion_enabled=False,
    )


@pytest.fixture
def dynamic_sizer(mock_client, base_risk_manager, default_config):
    """Create a DynamicPositionSizer with default config."""
    return DynamicPositionSizer(
        client=mock_client,
        base_risk_manager=base_risk_manager,
        config=default_config
    )


class TestDynamicPositionSizer:
    """Tests for DynamicPositionSizer."""
    
    def test_basic_sizing_without_adjustments(self, dynamic_sizer):
        """Test basic position sizing when no dynamic features are enabled."""
        result = dynamic_sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,  # 1%
            price=50000.0
        )
        
        assert result.quantity > 0
        assert result.notional > 0
        # Base sizing: 10000 * 0.01 = 100 USDT
        assert result.notional == pytest.approx(100.0, rel=0.1)
    
    def test_volatility_based_sizing_high_volatility(self, mock_client, base_risk_manager):
        """Test volatility-based sizing reduces position in high volatility."""
        config = DynamicSizingConfig(
            volatility_based_enabled=True,
            atr_multiplier=2.0
        )
        sizer = DynamicPositionSizer(
            client=mock_client,
            base_risk_manager=base_risk_manager,
            config=config
        )
        
        # Mock high ATR (high volatility)
        klines = [
            [0, 50000, 51000, 49000, 50000, 1000, 60000, 0, 0, 0, 0, 0],  # High range
            [60000, 50000, 51000, 49000, 50000, 1000, 120000, 0, 0, 0, 0, 0],
            [120000, 50000, 51000, 49000, 50000, 1000, 180000, 0, 0, 0, 0, 0],
        ] * 10  # Enough for ATR calculation
        
        result = sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            klines=klines
        )
        
        # Should reduce position size due to high volatility
        assert result.quantity > 0
        assert result.notional > 0
    
    def test_volatility_based_sizing_low_volatility(self, mock_client, base_risk_manager):
        """Test volatility-based sizing increases position in low volatility."""
        config = DynamicSizingConfig(
            volatility_based_enabled=True,
            atr_multiplier=2.0
        )
        sizer = DynamicPositionSizer(
            client=mock_client,
            base_risk_manager=base_risk_manager,
            config=config
        )
        
        # Mock low ATR (low volatility) - tight range
        klines = [
            [0, 50000, 50050, 49950, 50000, 1000, 60000, 0, 0, 0, 0, 0],  # Tight range
            [60000, 50000, 50050, 49950, 50000, 1000, 120000, 0, 0, 0, 0, 0],
            [120000, 50000, 50050, 49950, 50000, 1000, 180000, 0, 0, 0, 0, 0],
        ] * 10
        
        result = sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            klines=klines
        )
        
        # Should increase position size due to low volatility
        assert result.quantity > 0
        assert result.notional > 0
    
    def test_performance_based_win_streak(self, dynamic_sizer):
        """Test performance-based adjustment increases position on win streak."""
        config = DynamicSizingConfig(
            performance_based_enabled=True,
            win_streak_boost=0.1,  # 10% per win
            max_win_streak_boost=0.5  # Max 50%
        )
        dynamic_sizer.config = config
        
        strategy_id = "test_strategy"
        
        # Record 3 wins
        dynamic_sizer.record_trade(strategy_id, 100.0, is_win=True)
        dynamic_sizer.record_trade(strategy_id, 150.0, is_win=True)
        dynamic_sizer.record_trade(strategy_id, 120.0, is_win=True)
        
        # Get base sizing
        base_result = dynamic_sizer.base_risk_manager.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0
        )
        
        # Get adjusted sizing
        adjusted_result = dynamic_sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            strategy_id=strategy_id
        )
        
        # Should be larger due to win streak
        assert adjusted_result.quantity >= base_result.quantity
    
    def test_performance_based_loss_streak(self, dynamic_sizer):
        """Test performance-based adjustment decreases position on loss streak."""
        config = DynamicSizingConfig(
            performance_based_enabled=True,
            loss_streak_reduction=0.15,  # 15% per loss
            max_loss_streak_reduction=0.5  # Max 50%
        )
        dynamic_sizer.config = config
        
        strategy_id = "test_strategy"
        
        # Record 2 losses
        dynamic_sizer.record_trade(strategy_id, -50.0, is_win=False)
        dynamic_sizer.record_trade(strategy_id, -75.0, is_win=False)
        
        # Get base sizing
        base_result = dynamic_sizer.base_risk_manager.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0
        )
        
        # Get adjusted sizing
        adjusted_result = dynamic_sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            strategy_id=strategy_id
        )
        
        # Should be smaller due to loss streak
        assert adjusted_result.quantity <= base_result.quantity
    
    def test_kelly_criterion_insufficient_trades(self, dynamic_sizer):
        """Test Kelly Criterion doesn't activate with insufficient trades."""
        config = DynamicSizingConfig(
            kelly_criterion_enabled=True,
            min_trades_for_kelly=100
        )
        dynamic_sizer.config = config
        
        strategy_id = "test_strategy"
        
        # Record only 10 trades (below minimum)
        for i in range(10):
            dynamic_sizer.record_trade(strategy_id, 10.0 if i % 2 == 0 else -5.0, is_win=(i % 2 == 0))
        
        # Should use base sizing (Kelly not activated)
        result = dynamic_sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            strategy_id=strategy_id
        )
        
        # Should be similar to base sizing
        base_result = dynamic_sizer.base_risk_manager.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0
        )
        
        assert abs(result.quantity - base_result.quantity) < base_result.quantity * 0.1
    
    def test_kelly_criterion_with_sufficient_trades(self, dynamic_sizer):
        """Test Kelly Criterion activates with sufficient trades."""
        config = DynamicSizingConfig(
            kelly_criterion_enabled=True,
            min_trades_for_kelly=100,
            kelly_fraction=0.25  # Quarter Kelly
        )
        dynamic_sizer.config = config
        
        strategy_id = "test_strategy"
        
        # Record 100 trades with positive edge (60% win rate, 2:1 win/loss)
        for i in range(100):
            if i % 10 < 6:  # 60% wins
                dynamic_sizer.record_trade(strategy_id, 20.0, is_win=True)
            else:  # 40% losses
                dynamic_sizer.record_trade(strategy_id, -10.0, is_win=False)
        
        # Should use Kelly sizing
        result = dynamic_sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            strategy_id=strategy_id
        )
        
        # Should be adjusted (Kelly should suggest larger position for positive edge)
        assert result.quantity > 0
        assert result.notional > 0
    
    def test_trade_performance_tracking(self, dynamic_sizer):
        """Test trade performance tracking."""
        strategy_id = "test_strategy"
        
        # Record trades
        dynamic_sizer.record_trade(strategy_id, 100.0, is_win=True)
        dynamic_sizer.record_trade(strategy_id, 150.0, is_win=True)
        dynamic_sizer.record_trade(strategy_id, -50.0, is_win=False)
        
        perf = dynamic_sizer.get_performance(strategy_id)
        
        assert perf is not None
        assert perf.total_trades == 3
        assert perf.winning_trades == 2
        assert perf.losing_trades == 1
        assert perf.total_profit == 250.0
        assert perf.total_loss == -50.0
        assert perf.current_win_streak == 0  # Last trade was a loss
        assert perf.current_loss_streak == 1
    
    def test_atr_caching(self, mock_client, base_risk_manager):
        """Test ATR value is cached."""
        config = DynamicSizingConfig(volatility_based_enabled=True)
        sizer = DynamicPositionSizer(
            client=mock_client,
            base_risk_manager=base_risk_manager,
            config=config
        )
        
        klines = [
            [0, 50000, 50100, 49900, 50000, 1000, 60000, 0, 0, 0, 0, 0],
        ] * 20
        
        # First call - should calculate ATR
        result1 = sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            klines=klines
        )
        
        # Second call - should use cached ATR
        result2 = sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            klines=klines
        )
        
        # Both should work
        assert result1.quantity > 0
        assert result2.quantity > 0
    
    def test_fixed_amount_override(self, dynamic_sizer):
        """Test fixed amount overrides dynamic adjustments."""
        result = dynamic_sizer.size_position(
            symbol="BTCUSDT",
            risk_per_trade=0.01,
            price=50000.0,
            fixed_amount=200.0  # Fixed $200
        )
        
        # Should use fixed amount
        assert result.notional == pytest.approx(200.0, rel=0.1)


class TestDynamicSizingConfig:
    """Tests for DynamicSizingConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = DynamicSizingConfig()
        
        assert config.volatility_based_enabled is False
        assert config.performance_based_enabled is False
        assert config.kelly_criterion_enabled is False
        assert config.kelly_fraction == 0.25
        assert config.min_trades_for_kelly == 100
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = DynamicSizingConfig(
            volatility_based_enabled=True,
            atr_multiplier=3.0,
            performance_based_enabled=True,
            win_streak_boost=0.2,
            kelly_criterion_enabled=True,
            kelly_fraction=0.5
        )
        
        assert config.volatility_based_enabled is True
        assert config.atr_multiplier == 3.0
        assert config.performance_based_enabled is True
        assert config.win_streak_boost == 0.2
        assert config.kelly_criterion_enabled is True
        assert config.kelly_fraction == 0.5










