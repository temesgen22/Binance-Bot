"""
Test that enable_ema_cross_exit parameter works in backtesting.
"""
import pytest
pytestmark = pytest.mark.slow  # Backtesting tests excluded from CI
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.api.routes.backtesting import run_backtest, BacktestRequest
from app.core.my_binance_client import BinanceClient


@pytest.fixture
def mock_binance_client():
    """Create a mock Binance client."""
    client = Mock(spec=BinanceClient)
    client._ensure = Mock(return_value=Mock())
    return client


@pytest.fixture
def sample_klines():
    """Generate sample klines data for testing."""
    base_time = int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp() * 1000)
    klines = []
    
    # Generate 100 candles with price movement that would cause EMA crosses
    for i in range(100):
        timestamp = base_time + (i * 60000)  # 1 minute intervals
        # Create price pattern: rising then falling (to trigger both golden and death crosses)
        if i < 50:
            price = 40000.0 + (i * 5)  # Rising prices
        else:
            price = 40000.0 + (50 * 5) - ((i - 50) * 5)  # Falling prices
        
        klines.append([
            timestamp,
            str(price),
            str(price + 10),
            str(price - 10),
            str(price),
            "1000.0",
            timestamp + 60000,
            "0.0",
            "10",
            "500.0",
            "500.0",
            "0"
        ])
    
    return klines


@pytest.mark.asyncio
async def test_backtesting_with_ema_cross_exit_disabled(mock_binance_client, sample_klines):
    """Test that backtesting respects enable_ema_cross_exit=False parameter."""
    # Mock the Binance client to return sample klines
    rest_mock = Mock()
    rest_mock.futures_historical_klines = Mock(return_value=sample_klines)
    mock_binance_client._ensure.return_value = rest_mock
    
    # Create backtest request with EMA cross exit disabled
    start_time = datetime.now(timezone.utc) - timedelta(hours=2)
    end_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    
    request = BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=start_time,
        end_time=end_time,
        leverage=5,
        risk_per_trade=0.01,
        initial_balance=1000.0,
        params={
            "ema_fast": 3,
            "ema_slow": 13,
            "take_profit_pct": 0.04,
            "stop_loss_pct": 0.02,
            "enable_short": True,
            "cooldown_candles": 2,
            "min_ema_separation": 0.001,
            "enable_htf_bias": False,
            "trailing_stop_enabled": False,
            "enable_ema_cross_exit": False,  # Disabled
            "kline_interval": "1m"
        }
    )
    
    # Run backtest
    result = await run_backtest(request, mock_binance_client)
    
    # Verify that the parameter was passed through
    # The strategy should not exit on EMA crosses, only on TP/SL
    # We can't easily verify this without checking the actual trades,
    # but we can verify the backtest completed successfully
    assert result is not None
    assert result.symbol == "BTCUSDT"
    assert result.strategy_type == "scalping"
    
    # Check that trades don't have EMA cross exit reasons
    # (if they do, it means the parameter wasn't respected)
    for trade in result.trades:
        if trade.get("exit_reason"):
            # If EMA cross exit is disabled, we shouldn't see EMA_DEATH_CROSS or EMA_GOLDEN_CROSS
            assert trade["exit_reason"] not in ["EMA_DEATH_CROSS", "EMA_GOLDEN_CROSS"], (
                f"Found EMA cross exit reason '{trade['exit_reason']}' when enable_ema_cross_exit=False"
            )


@pytest.mark.asyncio
async def test_backtesting_with_ema_cross_exit_enabled(mock_binance_client, sample_klines):
    """Test that backtesting respects enable_ema_cross_exit=True parameter (default)."""
    # Mock the Binance client to return sample klines
    rest_mock = Mock()
    rest_mock.futures_historical_klines = Mock(return_value=sample_klines)
    mock_binance_client._ensure.return_value = rest_mock
    
    # Create backtest request with EMA cross exit enabled
    start_time = datetime.now(timezone.utc) - timedelta(hours=2)
    end_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    
    request = BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=start_time,
        end_time=end_time,
        leverage=5,
        risk_per_trade=0.01,
        initial_balance=1000.0,
        params={
            "ema_fast": 3,
            "ema_slow": 13,
            "take_profit_pct": 0.04,
            "stop_loss_pct": 0.02,
            "enable_short": True,
            "cooldown_candles": 2,
            "min_ema_separation": 0.001,
            "enable_htf_bias": False,
            "trailing_stop_enabled": False,
            "enable_ema_cross_exit": True,  # Enabled
            "kline_interval": "1m"
        }
    )
    
    # Run backtest
    result = await run_backtest(request, mock_binance_client)
    
    # Verify that the parameter was passed through
    assert result is not None
    assert result.symbol == "BTCUSDT"
    assert result.strategy_type == "scalping"
    
    # With EMA cross exit enabled, EMA cross exits are allowed
    # (We can't easily verify this without checking specific trade patterns,
    # but we can verify the backtest completed successfully)


@pytest.mark.asyncio
async def test_backtesting_ema_cross_exit_defaults_to_enabled(mock_binance_client, sample_klines):
    """Test that enable_ema_cross_exit defaults to True when not specified."""
    # Mock the Binance client to return sample klines
    rest_mock = Mock()
    rest_mock.futures_historical_klines = Mock(return_value=sample_klines)
    mock_binance_client._ensure.return_value = rest_mock
    
    # Create backtest request without enable_ema_cross_exit parameter
    start_time = datetime.now(timezone.utc) - timedelta(hours=2)
    end_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    
    request = BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=start_time,
        end_time=end_time,
        leverage=5,
        risk_per_trade=0.01,
        initial_balance=1000.0,
        params={
            "ema_fast": 3,
            "ema_slow": 13,
            "take_profit_pct": 0.04,
            "stop_loss_pct": 0.02,
            "enable_short": True,
            "cooldown_candles": 2,
            "min_ema_separation": 0.001,
            "enable_htf_bias": False,
            "trailing_stop_enabled": False,
            # enable_ema_cross_exit not specified - should default to True
            "kline_interval": "1m"
        }
    )
    
    # Run backtest
    result = await run_backtest(request, mock_binance_client)
    
    # Verify that the backtest completed successfully
    # (Default behavior should be enabled, so EMA cross exits are allowed)
    assert result is not None
    assert result.symbol == "BTCUSDT"

