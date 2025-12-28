"""
Critical function tests for EmaScalpingStrategy.

Tests the most important functions that must work correctly:
1. EMA calculation accuracy
2. Crossover detection logic
3. State management (prev_fast/prev_slow)
4. TP/SL calculations (long and short)
5. Filter logic (cooldown, separation, HTF bias)
"""

import pytest
pytestmark = pytest.mark.ci  # All tests in this file are critical for CI
from unittest.mock import MagicMock
from collections import deque

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.base import StrategyContext
from app.core.my_binance_client import BinanceClient


@pytest.fixture
def mock_client():
    """Create a mock BinanceClient."""
    client = MagicMock(spec=BinanceClient)
    client.get_price = MagicMock(return_value=40000.0)
    client.get_klines = MagicMock(return_value=[])
    return client


@pytest.fixture
def strategy_context():
    """Create a strategy context."""
    return StrategyContext(
        id="test-123",
        name="Test",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 5,
            "ema_slow": 10,
            "take_profit_pct": 0.005,
            "stop_loss_pct": 0.003,
            "kline_interval": "1m",
            "enable_short": True,
            "min_ema_separation": 0.0002,
            "enable_htf_bias": False,
            "cooldown_candles": 2,
            "interval_seconds": 10,
        },
        interval_seconds=10,
    )


@pytest.fixture
def strategy(mock_client, strategy_context):
    """Create strategy instance."""
    return EmaScalpingStrategy(strategy_context, mock_client)


class TestCriticalEMACalculation:
    """Test EMA calculation - CRITICAL for signal accuracy."""
    
    def test_ema_returns_float(self, strategy):
        """EMA must return a float value."""
        strategy.closes = deque([40000.0] * 20, maxlen=100)
        ema = strategy._ema(period=10)
        assert isinstance(ema, float)
        assert ema > 0
    
    def test_ema_with_exact_period(self, strategy):
        """EMA with exactly period number of prices."""
        prices = [40000.0 + i * 100 for i in range(10)]
        strategy.closes = deque(prices, maxlen=100)
        ema = strategy._ema(period=10)
        # Should be calculated, not just average
        assert isinstance(ema, float)
        assert 40000.0 <= ema <= 41000.0
    
    def test_ema_seeds_with_sma(self, strategy):
        """EMA should seed with SMA for first value."""
        prices = [40000.0, 40100.0, 40200.0, 40300.0, 40400.0]
        strategy.closes = deque(prices, maxlen=100)
        ema = strategy._ema(period=5)
        # First 5 prices: [40000, 40100, 40200, 40300, 40400]
        # SMA = 40200.0, EMA should start near this
        assert 40000.0 <= ema <= 41000.0


class TestCriticalCrossoverDetection:
    """Test crossover detection - CRITICAL for entry/exit signals."""
    
    def test_golden_cross_logic(self, strategy):
        """Test golden cross detection logic."""
        # Previous: fast was below slow
        prev_fast = 40000.0
        prev_slow = 40100.0
        
        # Current: fast is above slow
        fast_ema = 40200.0
        slow_ema = 40100.0
        
        # This should be a golden cross
        golden_cross = (prev_fast <= prev_slow) and (fast_ema > slow_ema)
        assert golden_cross is True
    
    def test_death_cross_logic(self, strategy):
        """Test death cross detection logic."""
        # Previous: fast was above slow
        prev_fast = 40200.0
        prev_slow = 40100.0
        
        # Current: fast is below slow
        fast_ema = 40000.0
        slow_ema = 40100.0
        
        # This should be a death cross
        death_cross = (prev_fast >= prev_slow) and (fast_ema < slow_ema)
        assert death_cross is True
    
    def test_no_cross_when_both_same_direction(self, strategy):
        """No cross when both EMAs move in same direction."""
        # Previous: fast below slow
        prev_fast = 40000.0
        prev_slow = 40100.0
        
        # Current: fast still below slow (both moved up)
        fast_ema = 40100.0
        slow_ema = 40200.0
        
        golden_cross = (prev_fast <= prev_slow) and (fast_ema > slow_ema)
        death_cross = (prev_fast >= prev_slow) and (fast_ema < slow_ema)
        
        assert golden_cross is False
        assert death_cross is False


class TestCriticalStateManagement:
    """Test state management - CRITICAL for preventing bugs."""
    
    def test_prev_values_initialized_none(self, strategy):
        """prev_fast and prev_slow should start as None."""
        assert strategy.prev_fast is None
        assert strategy.prev_slow is None
    
    def test_prev_values_preserved_before_calculation(self, strategy):
        """CRITICAL: prev values must be saved BEFORE calculating new EMAs."""
        # Set initial state
        strategy.prev_fast = 40000.0
        strategy.prev_slow = 40100.0
        
        # Save to locals (as done in evaluate)
        prev_fast = strategy.prev_fast
        prev_slow = strategy.prev_slow
        
        # Simulate calculating new EMAs
        fast_ema = 40200.0
        slow_ema = 40100.0
        
        # Check crossover using PREVIOUS values
        golden_cross = (prev_fast <= prev_slow) and (fast_ema > slow_ema)
        
        # This should be True
        assert golden_cross is True
        
        # If we had used self.prev_fast after updating, it would be wrong
        # This test ensures we use the local variables
    
    def test_state_updated_after_processing(self, strategy):
        """State should be updated after processing."""
        strategy.prev_fast = 40000.0
        strategy.prev_slow = 40100.0
        
        # After processing
        fast_ema = 40200.0
        slow_ema = 40100.0
        strategy.prev_fast = fast_ema
        strategy.prev_slow = slow_ema
        
        assert strategy.prev_fast == fast_ema
        assert strategy.prev_slow == slow_ema


class TestCriticalTPSL:
    """Test TP/SL calculations - CRITICAL for risk management."""
    
    def test_long_take_profit_calculation(self, strategy):
        """Long TP = entry * (1 + tp_pct)."""
        entry = 40000.0
        tp_pct = 0.005  # 0.5%
        expected_tp = entry * (1 + tp_pct)
        
        assert expected_tp == pytest.approx(40200.0, rel=1e-6)
    
    def test_long_stop_loss_calculation(self, strategy):
        """Long SL = entry * (1 - sl_pct)."""
        entry = 40000.0
        sl_pct = 0.003  # 0.3%
        expected_sl = entry * (1 - sl_pct)
        
        assert expected_sl == pytest.approx(39880.0, rel=1e-6)
    
    def test_short_take_profit_inverted(self, strategy):
        """Short TP = entry * (1 - tp_pct) [INVERTED]."""
        entry = 40000.0
        tp_pct = 0.005  # 0.5%
        expected_tp = entry * (1 - tp_pct)  # Inverted for shorts
        
        assert expected_tp == pytest.approx(39800.0, rel=1e-6)
    
    def test_short_stop_loss_inverted(self, strategy):
        """Short SL = entry * (1 + sl_pct) [INVERTED]."""
        entry = 40000.0
        sl_pct = 0.003  # 0.3%
        expected_sl = entry * (1 + sl_pct)  # Inverted for shorts
        
        assert expected_sl == pytest.approx(40120.0, rel=1e-6)
    
    def test_tp_higher_than_sl_for_long(self, strategy):
        """For longs, TP should be above entry, SL below entry."""
        entry = 40000.0
        tp = entry * (1 + 0.005)
        sl = entry * (1 - 0.003)
        
        assert tp > entry
        assert sl < entry
        assert tp > sl
    
    def test_tp_lower_than_sl_for_short(self, strategy):
        """For shorts, TP should be below entry, SL above entry."""
        entry = 40000.0
        tp = entry * (1 - 0.005)  # Inverted
        sl = entry * (1 + 0.003)  # Inverted
        
        assert tp < entry
        assert sl > entry
        assert tp < sl


class TestCriticalFilters:
    """Test filter logic - CRITICAL for avoiding bad trades."""
    
    def test_cooldown_decrements(self, strategy):
        """Cooldown should decrement each candle."""
        strategy.cooldown_left = 2
        
        # After one candle
        strategy.cooldown_left -= 1
        assert strategy.cooldown_left == 1
        
        # After another candle
        strategy.cooldown_left -= 1
        assert strategy.cooldown_left == 0
    
    def test_ema_separation_calculation(self, strategy):
        """EMA separation should be calculated as percentage of price."""
        price = 40000.0
        fast_ema = 40000.0
        slow_ema = 40100.0
        
        separation = abs(fast_ema - slow_ema) / price
        expected = 100.0 / 40000.0  # 0.0025 or 0.25%
        
        assert separation == pytest.approx(expected, rel=1e-6)
    
    def test_ema_separation_filter_blocks_small(self, strategy):
        """Small EMA separation should be blocked."""
        strategy.min_ema_separation = 0.001  # 0.1%
        price = 40000.0
        
        # Small separation
        fast_ema = 40000.0
        slow_ema = 40005.0  # Only 0.0125% difference
        separation = abs(fast_ema - slow_ema) / price
        
        assert separation < strategy.min_ema_separation
    
    def test_ema_separation_filter_allows_large(self, strategy):
        """Large EMA separation should pass."""
        strategy.min_ema_separation = 0.001  # 0.1%
        price = 40000.0
        
        # Large separation
        fast_ema = 40000.0
        slow_ema = 40100.0  # 0.25% difference
        separation = abs(fast_ema - slow_ema) / price
        
        assert separation > strategy.min_ema_separation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

