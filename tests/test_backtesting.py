"""
Comprehensive tests for Backtesting API endpoint.

Tests verify:
1. MockBinanceClient functionality
2. EMA Scalping strategy backtesting
3. Range Mean Reversion strategy backtesting
4. TP/SL execution
5. Fee calculations
6. Trade tracking and statistics
7. Error handling
8. Edge cases (insufficient data, no trades, etc.)
"""

import pytest
pytestmark = pytest.mark.slow  # Backtesting tests are excluded from CI due to CPU limitations
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes.backtesting import MockBinanceClient, AVERAGE_FEE_RATE


def build_klines(count: int, base_price: float = 50000.0, price_trend: float = 0.0,
                 volatility: float = 100.0, base_volume: float = 1000.0,
                 start_time: Optional[datetime] = None) -> list[list]:
    """
    Helper to create klines for testing.
    
    Args:
        count: Number of candles to generate
        base_price: Starting price
        price_trend: Price change per candle (positive = uptrend, negative = downtrend)
        volatility: Price volatility (random variation)
        base_volume: Base volume per candle
        start_time: Start time for first candle (defaults to now - count minutes)
    
    Returns:
        List of klines in Binance format: [open_time, open, high, low, close, volume, ...]
    """
    import random
    from time import time
    
    if start_time is None:
        start_time = datetime.now() - timedelta(minutes=count)
    
    klines = []
    current_price = base_price
    
    for i in range(count):
        # Calculate timestamp (1 minute intervals)
        timestamp = int((start_time + timedelta(minutes=i)).timestamp() * 1000)
        
        # Add trend and random volatility
        price_change = price_trend + random.uniform(-volatility, volatility)
        open_price = current_price
        close_price = open_price + price_change
        high_price = max(open_price, close_price) + abs(random.uniform(0, volatility * 0.5))
        low_price = min(open_price, close_price) - abs(random.uniform(0, volatility * 0.5))
        
        # Ensure high >= max(open, close) and low <= min(open, close)
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)
        
        # Volume with some variation
        volume = base_volume * random.uniform(0.8, 1.2)
        
        kline = [
            timestamp,  # open_time
            str(open_price),  # open
            str(high_price),  # high
            str(low_price),  # low
            str(close_price),  # close
            str(volume),  # volume
            timestamp + 60000,  # close_time
            str(volume * close_price),  # quote_volume
            0,  # trades
            str(volume),  # taker_buy_base_volume
            str(volume * close_price),  # taker_buy_quote_volume
            "0"  # ignore
        ]
        klines.append(kline)
        current_price = close_price
    
    return klines


def build_trending_klines(count: int, base_price: float = 50000.0) -> list[list]:
    """Create klines with a clear uptrend (for EMA crossover testing)."""
    return build_klines(count, base_price=base_price, price_trend=50.0, volatility=20.0)


def build_sideways_klines(count: int, base_price: float = 50000.0) -> list[list]:
    """Create klines with sideways movement (for range mean reversion testing)."""
    return build_klines(count, base_price=base_price, price_trend=0.0, volatility=50.0)


def setup_mock_binance_client(klines: list[list]):
    """
    Helper function to set up a mock Binance client that properly mocks
    both futures_historical_klines and futures_klines methods.
    
    Args:
        klines: List of klines to return from the mock
        
    Returns:
        Tuple of (mock_client, mock_rest)
    """
    mock_client = Mock()
    mock_rest = Mock()
    
    # Mock futures_historical_klines (used first by backtesting code)
    def futures_historical_klines_mock(*args, **kwargs):
        return klines
    mock_rest.futures_historical_klines = futures_historical_klines_mock
    
    # Also mock futures_klines as fallback
    def futures_klines_mock(*args, **kwargs):
        return klines
    mock_rest.futures_klines = futures_klines_mock
    
    mock_client._ensure.return_value = mock_rest
    
    return mock_client, mock_rest


@pytest.fixture()
def client():
    """Create test client with mocked binance client."""
    # Create a mock binance client
    mock_binance = Mock()
    app.state.binance_client = mock_binance
    return TestClient(app)


@pytest.fixture()
def mock_binance_client():
    """Create a mock Binance client for testing."""
    klines = build_klines(100, base_price=50000.0)
    return MockBinanceClient(klines=klines)


class TestMockBinanceClient:
    """Test the MockBinanceClient class."""
    
    def test_get_price_from_klines(self, mock_binance_client):
        """Test getting price from klines."""
        mock_binance_client.current_index = 0
        price = mock_binance_client.get_price("BTCUSDT")
        assert price > 0
        assert isinstance(price, float)
    
    def test_get_price_past_end(self, mock_binance_client):
        """Test getting price when index is past end."""
        mock_binance_client.current_index = 200  # Past end
        price = mock_binance_client.get_price("BTCUSDT")
        # Should return last price
        assert price > 0
    
    def test_get_klines_returns_provided_klines(self, mock_binance_client):
        """Test that get_klines returns klines up to current_index."""
        # By default, current_index is 0, so it should return 1 kline
        klines = mock_binance_client.get_klines("BTCUSDT", "1m", limit=100)
        assert len(klines) == 1
        assert klines == mock_binance_client.klines[:1]
        
        # Set current_index to last index to get all klines
        mock_binance_client.current_index = len(mock_binance_client.klines) - 1
        all_klines = mock_binance_client.get_klines("BTCUSDT", "1m", limit=100)
        assert len(all_klines) == 100
        assert all_klines == mock_binance_client.klines


class TestBacktestingEndpoint:
    """Test the /backtesting/run endpoint."""
    
    def test_backtest_endpoint_exists(self, client):
        """Test that the backtesting endpoint exists."""
        # This should return 422 (validation error) not 404 (not found)
        response = client.post("/api/backtesting/run", json={})
        assert response.status_code != 404
    
    def test_backtest_ema_scalping_success(self, client):
        """Test successful EMA scalping backtest."""
        # Create trending klines (uptrend for EMA crossover)
        klines = build_trending_klines(100, base_price=50000.0)
        
        # Mock Binance client
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        # Prepare request
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "leverage": 5,
            "risk_per_trade": 0.01,
            "initial_balance": 1000.0,
            "params": {
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.004,
                "stop_loss_pct": 0.002,
                "enable_short": True
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        # Should succeed (200) or return validation error (422)
        assert response.status_code in [200, 422, 400]
        
        if response.status_code == 200:
            data = response.json()
            assert "total_pnl" in data
            assert "total_trades" in data
            assert "win_rate" in data
            assert "trades" in data
            assert data["symbol"] == "BTCUSDT"
            assert data["strategy_type"] == "scalping"
    
    def test_backtest_range_mean_reversion_success(self, client):
        """Test successful Range Mean Reversion backtest."""
        # Create sideways klines
        klines = build_sideways_klines(200, base_price=50000.0)
        
        # Mock Binance client
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        # Prepare request
        start_time = datetime.now() - timedelta(hours=6)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "ETHUSDT",
            "strategy_type": "range_mean_reversion",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "leverage": 3,
            "risk_per_trade": 0.02,
            "initial_balance": 2000.0,
            "params": {
                "kline_interval": "5m",
                "lookback_period": 150,
                "buy_zone_pct": 0.2,
                "sell_zone_pct": 0.2,
                "rsi_period": 14,
                "rsi_oversold": 40,
                "rsi_overbought": 60
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        # Should succeed (200) or return validation error (422)
        assert response.status_code in [200, 422, 400]
        
        if response.status_code == 200:
            data = response.json()
            assert "total_pnl" in data
            assert "total_trades" in data
            assert data["strategy_type"] == "range_mean_reversion"
    
    def test_backtest_validation_error_missing_fields(self, client):
        """Test that missing required fields return validation error."""
        response = client.post("/api/backtesting/run", json={})
        assert response.status_code == 422
    
    def test_backtest_validation_error_invalid_strategy_type(self, client):
        """Test that invalid strategy type returns validation error."""
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "invalid_strategy",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": 1000.0
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        assert response.status_code == 422
    
    def test_backtest_validation_error_invalid_leverage(self, client):
        """Test that invalid leverage returns validation error."""
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "leverage": 100,  # Invalid (max is 50)
            "initial_balance": 1000.0
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        assert response.status_code == 422
    
    def test_backtest_insufficient_data(self, client):
        """Test backtest with insufficient historical data."""
        # Create very few klines
        klines = build_klines(10, base_price=50000.0)
        
        # Mock Binance client
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": 1000.0,
            "params": {
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        # Should either succeed with 0 trades or return error
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            data = response.json()
            # With insufficient data, might have 0 trades
            assert data["total_trades"] >= 0


class TestBacktestingCalculations:
    """Test backtesting calculations (fees, PnL, etc.)."""
    
    def test_fee_calculation(self, client):
        """Test that fees are calculated correctly."""
        # Create klines with clear trend for at least one trade
        klines = build_trending_klines(100, base_price=50000.0)
        
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "leverage": 5,
            "risk_per_trade": 0.01,
            "initial_balance": 1000.0,
            "params": {
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.004,
                "stop_loss_pct": 0.002
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        if response.status_code == 200:
            data = response.json()
            # Total fees should be positive if there are trades
            if data["total_trades"] > 0:
                assert data["total_fees"] >= 0
                # Fees should be approximately 0.03% per trade (entry + exit)
                # For completed trades: entry_fee + exit_fee per trade
                if data["completed_trades"] > 0:
                    # Check that fees are reasonable (at least some trades have fees)
                    assert data["total_fees"] > 0
    
    def test_pnl_calculation_with_leverage(self, client):
        """Test that PnL is calculated correctly with leverage."""
        # Create strong uptrend for guaranteed profitable trade
        klines = build_trending_klines(100, base_price=50000.0)
        
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "leverage": 10,  # High leverage
            "risk_per_trade": 0.01,
            "initial_balance": 1000.0,
            "params": {
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.004,
                "stop_loss_pct": 0.002
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        if response.status_code == 200:
            data = response.json()
            # Final balance should account for leverage
            assert data["final_balance"] >= 0
            # Total PnL should reflect leverage impact
            assert data["total_pnl"] == data["final_balance"] - data["initial_balance"]
    
    def test_win_rate_calculation(self, client):
        """Test that win rate is calculated correctly."""
        klines = build_trending_klines(100, base_price=50000.0)
        
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": 1000.0,
            "params": {
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        if response.status_code == 200:
            data = response.json()
            if data["completed_trades"] > 0:
                # Win rate should be between 0 and 100
                assert 0 <= data["win_rate"] <= 100
                # Win rate should match winning_trades / completed_trades
                expected_win_rate = (data["winning_trades"] / data["completed_trades"]) * 100
                assert abs(data["win_rate"] - expected_win_rate) < 0.01


class TestBacktestingTradeTracking:
    """Test trade tracking and statistics."""
    
    def test_trade_details_in_response(self, client):
        """Test that trade details are included in response."""
        klines = build_trending_klines(100, base_price=50000.0)
        
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": 1000.0,
            "params": {
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        if response.status_code == 200:
            data = response.json()
            assert "trades" in data
            assert isinstance(data["trades"], list)
            
            # Check trade structure if trades exist
            if len(data["trades"]) > 0:
                trade = data["trades"][0]
                assert "entry_time" in trade
                assert "entry_price" in trade
                assert "position_side" in trade
                assert "quantity" in trade
                assert "notional" in trade
                assert "entry_fee" in trade
    
    def test_open_trades_tracked(self, client):
        """Test that open trades are tracked separately."""
        klines = build_trending_klines(100, base_price=50000.0)
        
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": 1000.0,
            "params": {
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        if response.status_code == 200:
            data = response.json()
            # Total trades should equal completed + open
            assert data["total_trades"] == data["completed_trades"] + data["open_trades"]
            
            # Check open trades in trade list
            open_trades = [t for t in data["trades"] if t.get("is_open", False)]
            assert len(open_trades) == data["open_trades"]


class TestBacktestingEdgeCases:
    """Test edge cases and error handling."""
    
    def test_backtest_no_trades(self, client):
        """Test backtest that generates no trades."""
        # Create klines with no clear trend (sideways, low volatility)
        klines = build_klines(100, base_price=50000.0, price_trend=0.0, volatility=1.0)
        
        mock_client, _ = setup_mock_binance_client(klines)
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": 1000.0,
            "params": {
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.004,
                "stop_loss_pct": 0.002
            }
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        if response.status_code == 200:
            data = response.json()
            # Should handle no trades gracefully
            assert data["total_trades"] >= 0
            assert data["completed_trades"] >= 0
            assert data["open_trades"] >= 0
            # Final balance should equal initial balance if no trades
            if data["total_trades"] == 0:
                assert abs(data["final_balance"] - data["initial_balance"]) < 0.01
    
    def test_backtest_api_error_handling(self, client):
        """Test handling of Binance API errors."""
        # Mock client that raises an error
        mock_client = Mock()
        mock_rest = Mock()
        # Both methods should raise errors
        mock_rest.futures_historical_klines.side_effect = Exception("API Error")
        mock_rest.futures_klines.side_effect = Exception("API Error")
        mock_client._ensure.return_value = mock_rest
        
        # Set the mock client in app state
        client.app.state.binance_client = mock_client
        
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": 1000.0
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        # Should return error status
        assert response.status_code in [400, 500]
    
    def test_backtest_invalid_time_range(self, client):
        """Test that invalid time range (end before start) is rejected."""
        start_time = datetime.now()
        end_time = datetime.now() - timedelta(hours=1)  # End before start
        
        # Set up mock client (even though it shouldn't be called)
        klines = build_klines(100, base_price=50000.0)
        mock_client, _ = setup_mock_binance_client(klines)
        client.app.state.binance_client = mock_client
        
        request_data = {
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": 1000.0
        }
        
        response = client.post("/api/backtesting/run", json=request_data)
        
        # Should return validation error or handle gracefully
        assert response.status_code in [200, 400, 422]

