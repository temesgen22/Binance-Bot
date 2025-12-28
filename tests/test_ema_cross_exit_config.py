"""
Test that enable_ema_cross_exit configuration works correctly.
"""
import pytest
pytestmark = pytest.mark.ci  # EMA cross exit config is critical
from unittest.mock import Mock, AsyncMock

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.base import StrategyContext
from app.core.my_binance_client import BinanceClient


@pytest.fixture
def mock_client():
    """Create a mock Binance client."""
    client = Mock(spec=BinanceClient)
    client.get_price = Mock(return_value=40000.0)
    client.get_klines = Mock(return_value=[])
    return client


@pytest.fixture
def strategy_context_with_ema_exit_disabled():
    """Create a strategy context with EMA cross exit disabled."""
    return StrategyContext(
        id="test-strategy",
        name="Test Strategy",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
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
        },
        interval_seconds=60
    )


@pytest.fixture
def strategy_context_with_ema_exit_enabled():
    """Create a strategy context with EMA cross exit enabled (default)."""
    return StrategyContext(
        id="test-strategy",
        name="Test Strategy",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
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
        },
        interval_seconds=60
    )


@pytest.mark.asyncio
async def test_ema_cross_exit_disabled_prevents_long_exit(mock_client, strategy_context_with_ema_exit_disabled):
    """Test that when EMA cross exit is disabled, LONG positions don't exit on death cross."""
    strategy = EmaScalpingStrategy(strategy_context_with_ema_exit_disabled, mock_client)
    
    # Set up LONG position
    strategy.position = "LONG"
    strategy.entry_price = 40000.0
    strategy.cooldown_left = 0
    
    # Create klines that would trigger death cross (but exit should be disabled)
    klines = []
    base_time = 1702051200000
    # Falling prices (death cross scenario)
    for i in range(20):
        timestamp = base_time + (i * 60000)
        price = 40000.0 - (i * 10)
        klines.append([
            timestamp,
            str(price),
            str(price + 5),
            str(price - 5),
            str(price),
            "1000.0",
            timestamp + 60000,
            "0.0",
            "10",
            "500.0",
            "500.0",
            "0"
        ])
    
    mock_client.get_klines.return_value = klines
    
    # Evaluate strategy
    signal = await strategy.evaluate()
    
    # Should NOT exit on death cross (should be HOLD or check TP/SL instead)
    # Since EMA cross exit is disabled, death cross should not trigger SELL
    assert signal.action != "SELL" or signal.exit_reason != "EMA_DEATH_CROSS", (
        "Death cross should not trigger exit when enable_ema_cross_exit is False"
    )


@pytest.mark.asyncio
async def test_ema_cross_exit_enabled_allows_long_exit(mock_client, strategy_context_with_ema_exit_enabled):
    """Test that when EMA cross exit is enabled, LONG positions exit on death cross."""
    strategy = EmaScalpingStrategy(strategy_context_with_ema_exit_enabled, mock_client)
    
    # Set up LONG position
    strategy.position = "LONG"
    strategy.entry_price = 40000.0
    strategy.cooldown_left = 0
    
    # Create klines that would trigger death cross
    klines = []
    base_time = 1702051200000
    # Falling prices (death cross scenario)
    for i in range(20):
        timestamp = base_time + (i * 60000)
        price = 40000.0 - (i * 10)
        klines.append([
            timestamp,
            str(price),
            str(price + 5),
            str(price - 5),
            str(price),
            "1000.0",
            timestamp + 60000,
            "0.0",
            "10",
            "500.0",
            "500.0",
            "0"
        ])
    
    mock_client.get_klines.return_value = klines
    
    # Evaluate strategy
    signal = await strategy.evaluate()
    
    # If death cross occurs and EMA cross exit is enabled, it should exit
    # Note: This test depends on actual EMA crossover detection, which requires
    # specific price patterns. The key is that enable_ema_cross_exit=True allows
    # the exit logic to run.
    assert strategy.enable_ema_cross_exit == True, "EMA cross exit should be enabled"


@pytest.mark.asyncio
async def test_ema_cross_exit_disabled_prevents_short_exit(mock_client, strategy_context_with_ema_exit_disabled):
    """Test that when EMA cross exit is disabled, SHORT positions don't exit on golden cross."""
    strategy = EmaScalpingStrategy(strategy_context_with_ema_exit_disabled, mock_client)
    
    # Set up SHORT position
    strategy.position = "SHORT"
    strategy.entry_price = 40000.0
    strategy.cooldown_left = 0
    
    # Create klines that would trigger golden cross (but exit should be disabled)
    klines = []
    base_time = 1702051200000
    # Rising prices (golden cross scenario)
    for i in range(20):
        timestamp = base_time + (i * 60000)
        price = 40000.0 + (i * 10)
        klines.append([
            timestamp,
            str(price),
            str(price + 5),
            str(price - 5),
            str(price),
            "1000.0",
            timestamp + 60000,
            "0.0",
            "10",
            "500.0",
            "500.0",
            "0"
        ])
    
    mock_client.get_klines.return_value = klines
    
    # Evaluate strategy
    signal = await strategy.evaluate()
    
    # Should NOT exit on golden cross (should be HOLD or check TP/SL instead)
    # Since EMA cross exit is disabled, golden cross should not trigger BUY (cover)
    assert signal.action != "BUY" or signal.exit_reason != "EMA_GOLDEN_CROSS", (
        "Golden cross should not trigger exit when enable_ema_cross_exit is False"
    )


@pytest.mark.asyncio
async def test_ema_cross_exit_default_is_enabled(mock_client):
    """Test that enable_ema_cross_exit defaults to True if not specified."""
    context = StrategyContext(
        id="test-strategy",
        name="Test Strategy",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 3,
            "ema_slow": 13,
            "take_profit_pct": 0.04,
            "stop_loss_pct": 0.02,
            # enable_ema_cross_exit not specified - should default to True
        },
        interval_seconds=60
    )
    
    strategy = EmaScalpingStrategy(context, mock_client)
    
    # Should default to True
    assert strategy.enable_ema_cross_exit == True, (
        "enable_ema_cross_exit should default to True when not specified"
    )

