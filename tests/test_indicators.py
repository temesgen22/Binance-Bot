"""
Comprehensive tests for shared technical indicators.

Tests verify:
1. EMA calculation correctness
2. RSI calculation correctness  
3. ATR calculation correctness
4. Edge cases (insufficient data, empty inputs, etc.)
5. Consistency across different inputs
"""

import pytest
from app.strategies.indicators import calculate_ema, calculate_rsi, calculate_atr


class TestEMA:
    """Tests for Exponential Moving Average calculation."""

    def test_ema_with_sufficient_data(self):
        """Test EMA calculation with sufficient data points."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        ema = calculate_ema(prices, period=3)
        
        # EMA should be calculated
        assert ema is not None
        assert isinstance(ema, float)
        # EMA should be between min and max prices
        assert min(prices) <= ema <= max(prices)

    def test_ema_insufficient_data(self):
        """Test EMA with insufficient data returns None."""
        prices = [100.0, 101.0]  # Only 2 prices, need 3 for period=3
        ema = calculate_ema(prices, period=3)
        assert ema is None

    def test_ema_empty_list(self):
        """Test EMA with empty list returns None."""
        prices = []
        ema = calculate_ema(prices, period=5)
        assert ema is None

    def test_ema_single_price(self):
        """Test EMA with period=1 should return that price."""
        prices = [100.0]
        ema = calculate_ema(prices, period=1)
        assert ema == 100.0

    def test_ema_trending_up(self):
        """Test EMA reflects upward trend."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        ema = calculate_ema(prices, period=3)
        assert ema is not None
        # EMA should be closer to recent prices
        assert ema > 102.0  # Should be above middle price

    def test_ema_trending_down(self):
        """Test EMA reflects downward trend."""
        prices = [105.0, 104.0, 103.0, 102.0, 101.0, 100.0]
        ema = calculate_ema(prices, period=3)
        assert ema is not None
        # EMA should be closer to recent (lower) prices
        assert ema < 103.0  # Should be below middle price

    def test_ema_consistency(self):
        """Test EMA produces consistent results for same input."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        ema1 = calculate_ema(prices, period=3)
        ema2 = calculate_ema(prices, period=3)
        assert ema1 == ema2


class TestRSI:
    """Tests for Relative Strength Index calculation."""

    def test_rsi_with_sufficient_data(self):
        """Test RSI calculation with sufficient data."""
        # Create prices with clear uptrend (should have high RSI)
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 
                 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0]
        rsi = calculate_rsi(prices, period=14)
        
        assert rsi is not None
        assert isinstance(rsi, float)
        # RSI should be between 0 and 100
        assert 0 <= rsi <= 100
        # Upward trend should give high RSI
        assert rsi > 50

    def test_rsi_oversold_condition(self):
        """Test RSI reflects oversold condition (downtrend)."""
        # Create prices with clear downtrend
        prices = [115.0, 114.0, 113.0, 112.0, 111.0, 110.0, 109.0, 108.0,
                 107.0, 106.0, 105.0, 104.0, 103.0, 102.0, 101.0, 100.0]
        rsi = calculate_rsi(prices, period=14)
        
        assert rsi is not None
        # Downward trend should give low RSI
        assert rsi < 50

    def test_rsi_insufficient_data(self):
        """Test RSI with insufficient data returns None."""
        prices = [100.0, 101.0, 102.0]  # Need period+1 = 15 for period=14
        rsi = calculate_rsi(prices, period=14)
        assert rsi is None

    def test_rsi_empty_list(self):
        """Test RSI with empty list returns None."""
        prices = []
        rsi = calculate_rsi(prices, period=14)
        assert rsi is None

    def test_rsi_no_losses(self):
        """Test RSI when there are no losses (all gains)."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        rsi = calculate_rsi(prices, period=4)
        
        # With only gains, RSI should be high
        assert rsi is not None
        assert rsi >= 50

    def test_rsi_no_gains(self):
        """Test RSI when there are no gains (all losses)."""
        prices = [104.0, 103.0, 102.0, 101.0, 100.0]
        rsi = calculate_rsi(prices, period=4)
        
        # With only losses, RSI should be low
        assert rsi is not None
        assert rsi <= 50

    def test_rsi_range(self):
        """Test RSI always returns value between 0 and 100."""
        # Test with various price patterns
        test_cases = [
            [100.0] * 20,  # Flat prices
            list(range(100, 120)),  # Upward
            list(range(120, 100, -1)),  # Downward
            [100.0, 101.0, 100.0, 101.0] * 5,  # Oscillating
        ]
        
        for prices in test_cases:
            rsi = calculate_rsi(prices, period=14)
            if rsi is not None:
                assert 0 <= rsi <= 100, f"RSI out of range: {rsi}"


class TestATR:
    """Tests for Average True Range calculation."""

    def build_klines(self, count: int, base_price: float = 100.0, volatility: float = 1.0):
        """Helper to create klines for testing."""
        klines = []
        for i in range(count):
            open_time = i * 60000
            close_time = open_time + 60000
            price = base_price + (i * 0.1)
            klines.append([
                open_time,           # open_time
                price,               # open
                price + volatility,  # high
                price - volatility,  # low
                price,               # close
                1000.0,              # volume
                close_time,          # close_time
                0, 0, 0, 0, 0        # placeholders
            ])
        return klines

    def test_atr_with_sufficient_data(self):
        """Test ATR calculation with sufficient data."""
        klines = self.build_klines(count=20, base_price=100.0, volatility=2.0)
        atr = calculate_atr(klines, period=14)
        
        assert atr is not None
        assert isinstance(atr, float)
        assert atr > 0

    def test_atr_reflects_volatility(self):
        """Test ATR reflects market volatility."""
        # Low volatility
        low_vol_klines = self.build_klines(count=20, base_price=100.0, volatility=0.5)
        low_atr = calculate_atr(low_vol_klines, period=14)
        
        # High volatility
        high_vol_klines = self.build_klines(count=20, base_price=100.0, volatility=5.0)
        high_atr = calculate_atr(high_vol_klines, period=14)
        
        assert low_atr is not None
        assert high_atr is not None
        assert high_atr > low_atr

    def test_atr_insufficient_data(self):
        """Test ATR with insufficient data returns None."""
        klines = self.build_klines(count=10, base_price=100.0)  # Need 15 for period=14
        atr = calculate_atr(klines, period=14)
        assert atr is None

    def test_atr_empty_list(self):
        """Test ATR with empty list returns None."""
        klines = []
        atr = calculate_atr(klines, period=14)
        assert atr is None

    def test_atr_considers_gaps(self):
        """Test ATR accounts for price gaps (previous close)."""
        # Create klines with a gap
        klines = [
            [0, 100.0, 101.0, 99.0, 100.0, 1000.0, 60000, 0, 0, 0, 0, 0],  # Previous candle
            [60000, 105.0, 106.0, 104.0, 105.0, 1000.0, 120000, 0, 0, 0, 0, 0],  # Gap up
        ]
        # Add more klines to meet minimum period
        for i in range(2, 20):
            open_time = i * 60000
            close_time = open_time + 60000
            price = 105.0 + (i * 0.1)
            klines.append([
                open_time, price, price + 1, price - 1, price, 1000.0, close_time,
                0, 0, 0, 0, 0
            ])
        
        atr = calculate_atr(klines, period=14)
        
        # ATR should account for the gap (5.0 gap from 100 to 105)
        assert atr is not None
        assert atr > 1.0  # Should be larger due to gap

    def test_atr_positive_value(self):
        """Test ATR always returns positive value."""
        klines = self.build_klines(count=20, base_price=100.0, volatility=1.0)
        atr = calculate_atr(klines, period=14)
        
        assert atr is not None
        assert atr > 0


@pytest.mark.slow
class TestIndicatorIntegration:
    """Integration tests using indicators together."""

    def test_all_indicators_with_same_data(self):
        """Test all indicators can be calculated from same price data."""
        # Create klines
        klines = []
        prices = []
        for i in range(50):
            open_time = i * 60000
            close_time = open_time + 60000
            price = 100.0 + (i * 0.5)
            prices.append(price)
            klines.append([
                open_time, price, price + 1, price - 1, price, 1000.0, close_time,
                0, 0, 0, 0, 0
            ])
        
        # All indicators should calculate successfully
        ema = calculate_ema(prices, period=10)
        rsi = calculate_rsi(prices, period=14)
        atr = calculate_atr(klines, period=14)
        
        assert ema is not None
        assert rsi is not None
        assert atr is not None
        
        # Values should be reasonable
        assert ema > 0
        assert 0 <= rsi <= 100
        assert atr > 0

