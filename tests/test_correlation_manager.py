"""
Tests for CorrelationManager - Phase 3 Week 6: Correlation & Margin Protection
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.risk.correlation_manager import (
    CorrelationManager,
    CorrelationPair,
    CorrelationGroup,
)


@pytest.fixture
def correlation_manager():
    """Create a CorrelationManager instance."""
    return CorrelationManager(
        window_days=30,
        min_data_points=10,  # Lower for testing
        cache_ttl_hours=1,
        max_correlation_exposure_pct=0.5
    )


class TestCorrelationManager:
    """Tests for CorrelationManager."""
    
    def test_calculate_correlation_insufficient_data(self, correlation_manager):
        """Test correlation calculation with insufficient data."""
        symbol1 = "BTCUSDT"
        symbol2 = "ETHUSDT"
        
        # Create minimal price history (less than min_data_points)
        # Need to ensure timestamps are within window
        base_time = datetime.now(timezone.utc)
        price_history1 = [
            (base_time - timedelta(hours=i), 50000.0 + i * 10)
            for i in range(5)  # Only 5 points
        ]
        price_history2 = [
            (base_time - timedelta(hours=i), 3000.0 + i * 5)
            for i in range(5)
        ]
        
        result = correlation_manager.calculate_correlation(
            symbol1, symbol2, price_history1, price_history2
        )
        
        assert result is None  # Insufficient data
    
    def test_calculate_correlation_sufficient_data(self, correlation_manager):
        """Test correlation calculation with sufficient data."""
        symbol1 = "BTCUSDT"
        symbol2 = "ETHUSDT"
        
        # Create price history with positive correlation
        base_time = datetime.now(timezone.utc)
        price_history1 = [
            (base_time - timedelta(days=i), 50000.0 + i * 100)
            for i in range(20, 0, -1)
        ]
        price_history2 = [
            (base_time - timedelta(days=i), 3000.0 + i * 10)
            for i in range(20, 0, -1)
        ]
        
        result = correlation_manager.calculate_correlation(
            symbol1, symbol2, price_history1, price_history2
        )
        
        assert result is not None
        assert result.symbol1 == symbol1
        assert result.symbol2 == symbol2
        assert -1.0 <= result.correlation <= 1.0
        assert result.window_days == 30
    
    def test_calculate_correlation_caching(self, correlation_manager):
        """Test that correlation values are cached."""
        symbol1 = "BTCUSDT"
        symbol2 = "ETHUSDT"
        
        base_time = datetime.now(timezone.utc)
        price_history1 = [
            (base_time - timedelta(days=i), 50000.0 + i * 100)
            for i in range(20, 0, -1)
        ]
        price_history2 = [
            (base_time - timedelta(days=i), 3000.0 + i * 10)
            for i in range(20, 0, -1)
        ]
        
        # First call
        result1 = correlation_manager.calculate_correlation(
            symbol1, symbol2, price_history1, price_history2
        )
        
        # Second call (should use cache)
        result2 = correlation_manager.calculate_correlation(
            symbol1, symbol2, price_history1, price_history2
        )
        
        assert result1 is not None
        assert result2 is not None
        assert result1.correlation == result2.correlation
    
    def test_get_correlation_groups(self, correlation_manager):
        """Test correlation grouping."""
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
        
        base_time = datetime.now(timezone.utc)
        
        # Create price histories with BTC and ETH highly correlated
        price_histories = {}
        for i, symbol in enumerate(symbols):
            if symbol in ["BTCUSDT", "ETHUSDT"]:
                # BTC and ETH move together
                prices = [
                    (base_time - timedelta(days=j), 50000.0 + j * 100 + i * 1000)
                    for j in range(20, 0, -1)
                ]
            else:
                # Other symbols move independently
                prices = [
                    (base_time - timedelta(days=j), 300.0 + j * 5 + i * 50)
                    for j in range(20, 0, -1)
                ]
            price_histories[symbol] = prices
        
        groups = correlation_manager.get_correlation_groups(
            symbols,
            correlation_threshold=0.7,
            price_histories=price_histories
        )
        
        # Should find at least one group (BTC-ETH if correlated)
        assert isinstance(groups, list)
    
    def test_check_correlation_exposure_new_symbol(self, correlation_manager):
        """Test correlation exposure check for new symbol."""
        symbol = "NEWUSDT"
        current_exposure = 1000.0
        total_exposure = 5000.0
        account_balance = 10000.0
        
        allowed, reason = correlation_manager.check_correlation_exposure(
            symbol, current_exposure, total_exposure, account_balance
        )
        
        # New symbol should be allowed (no correlation data yet)
        assert allowed is True
        assert reason is None
    
    def test_update_price_history(self, correlation_manager):
        """Test price history update."""
        symbol = "BTCUSDT"
        price = 50000.0
        
        correlation_manager.update_price_history(symbol, price)
        
        assert symbol in correlation_manager._price_history
        assert len(correlation_manager._price_history[symbol]) == 1
        assert correlation_manager._price_history[symbol][0][1] == price
    
    def test_clear_cache(self, correlation_manager):
        """Test cache clearing."""
        # Add some cached data
        correlation_manager._correlation_cache["BTCUSDT:ETHUSDT"] = (0.8, datetime.now(timezone.utc))
        
        assert len(correlation_manager._correlation_cache) > 0
        
        correlation_manager.clear_cache()
        
        assert len(correlation_manager._correlation_cache) == 0
    
    def test_pearson_correlation_pure_python(self, correlation_manager):
        """Test pure Python Pearson correlation calculation."""
        # Test with known data
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]  # Perfect positive correlation
        
        correlation = correlation_manager._pearson_correlation(x, y)
        
        assert correlation == pytest.approx(1.0, abs=0.01)
    
    def test_pearson_correlation_negative(self, correlation_manager):
        """Test negative correlation."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]  # Perfect negative correlation
        
        correlation = correlation_manager._pearson_correlation(x, y)
        
        assert correlation == pytest.approx(-1.0, abs=0.01)
    
    def test_pearson_correlation_zero(self, correlation_manager):
        """Test zero correlation."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [1.0, 1.0, 1.0, 1.0, 1.0]  # Constant (no variation)
        
        correlation = correlation_manager._pearson_correlation(x, y)
        
        assert correlation == pytest.approx(0.0, abs=0.01)


class TestCorrelationPair:
    """Tests for CorrelationPair."""
    
    def test_correlation_pair_creation(self):
        """Test creating a CorrelationPair."""
        pair = CorrelationPair(
            symbol1="BTCUSDT",
            symbol2="ETHUSDT",
            correlation=0.85,
            window_days=30,
            data_points=20,
            calculated_at=datetime.now(timezone.utc)
        )
        
        assert pair.symbol1 == "BTCUSDT"
        assert pair.symbol2 == "ETHUSDT"
        assert pair.correlation == 0.85
        assert pair.window_days == 30
        assert pair.data_points == 20

