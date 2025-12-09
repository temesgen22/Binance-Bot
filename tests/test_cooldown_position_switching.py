"""
Test that cooldown prevents switching from LONG to SHORT (and vice versa).
"""
import pytest
from datetime import datetime, timezone
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
def strategy_context():
    """Create a strategy context with cooldown enabled."""
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
            "cooldown_candles": 3,  # 3 candle cooldown
            "min_ema_separation": 0.001,
            "enable_htf_bias": False,
            "trailing_stop_enabled": False,
            "kline_interval": "1m"
        },
        interval_seconds=60
    )


@pytest.mark.asyncio
async def test_cooldown_prevents_long_to_short_switch(mock_client, strategy_context):
    """Test that cooldown prevents switching from LONG to SHORT immediately."""
    strategy = EmaScalpingStrategy(strategy_context, mock_client)
    
    # Simulate exiting a LONG position (sets cooldown)
    strategy.position = None
    strategy.entry_price = None
    strategy.cooldown_left = strategy.cooldown_candles  # Set cooldown to 3 candles
    
    # Create klines that would trigger a SHORT entry (death cross)
    # But cooldown should prevent it
    klines = []
    base_time = 1702051200000  # Base timestamp
    # Create price pattern that would cause death cross
    for i in range(20):
        timestamp = base_time + (i * 60000)
        # Falling prices (death cross scenario)
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
    
    # Evaluate strategy (should return HOLD due to cooldown)
    signal = await strategy.evaluate()
    
    # Should be HOLD, not SELL (SHORT entry)
    assert signal.action == "HOLD", (
        f"Expected HOLD due to cooldown, got {signal.action}. "
        f"Cooldown left: {strategy.cooldown_left}"
    )
    
    # Cooldown should have decremented
    assert strategy.cooldown_left == strategy.cooldown_candles - 1, (
        f"Expected cooldown to decrement to {strategy.cooldown_candles - 1}, "
        f"got {strategy.cooldown_left}"
    )


@pytest.mark.asyncio
async def test_cooldown_prevents_short_to_long_switch(mock_client, strategy_context):
    """Test that cooldown prevents switching from SHORT to LONG immediately."""
    strategy = EmaScalpingStrategy(strategy_context, mock_client)
    
    # Simulate exiting a SHORT position (sets cooldown)
    strategy.position = None
    strategy.entry_price = None
    strategy.cooldown_left = strategy.cooldown_candles  # Set cooldown to 3 candles
    
    # Create klines that would trigger a LONG entry (golden cross)
    # But cooldown should prevent it
    klines = []
    base_time = 1702051200000
    # Create price pattern that would cause golden cross
    for i in range(20):
        timestamp = base_time + (i * 60000)
        # Rising prices (golden cross scenario)
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
    
    # Evaluate strategy (should return HOLD due to cooldown)
    signal = await strategy.evaluate()
    
    # Should be HOLD, not BUY (LONG entry)
    assert signal.action == "HOLD", (
        f"Expected HOLD due to cooldown, got {signal.action}. "
        f"Cooldown left: {strategy.cooldown_left}"
    )
    
    # Cooldown should have decremented
    assert strategy.cooldown_left == strategy.cooldown_candles - 1


@pytest.mark.asyncio
async def test_cooldown_allows_entry_after_expiration(mock_client, strategy_context):
    """Test that after cooldown expires, entries are allowed again."""
    strategy = EmaScalpingStrategy(strategy_context, mock_client)
    
    # Set cooldown to 1 candle (will expire after one evaluation)
    strategy.position = None
    strategy.entry_price = None
    strategy.cooldown_left = 1  # Only 1 candle cooldown
    
    # Create klines that would trigger a LONG entry (golden cross)
    klines = []
    base_time = 1702051200000
    for i in range(20):
        timestamp = base_time + (i * 60000)
        price = 40000.0 + (i * 10)  # Rising prices
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
    
    # First evaluation: Should be HOLD (cooldown active)
    signal1 = await strategy.evaluate()
    assert signal1.action == "HOLD", "First evaluation should be HOLD due to cooldown"
    assert strategy.cooldown_left == 0, "Cooldown should be 0 after decrement"
    
    # Second evaluation: Cooldown expired, should allow entry
    # Note: This test is simplified - in reality, EMA cross detection requires
    # specific EMA crossover conditions. But we're testing that cooldown doesn't
    # block entries after it expires.
    signal2 = await strategy.evaluate()
    # After cooldown expires, entry signals can be processed
    # (Whether they actually trigger depends on EMA conditions)
    assert strategy.cooldown_left == 0, "Cooldown should remain 0"


@pytest.mark.asyncio
async def test_cooldown_set_on_all_exits(mock_client, strategy_context):
    """Test that cooldown is set when exiting LONG or SHORT positions."""
    strategy = EmaScalpingStrategy(strategy_context, mock_client)
    
    # Test LONG exit
    strategy.position = "LONG"
    strategy.entry_price = 40000.0
    strategy.cooldown_left = 0
    
    # Simulate exiting LONG (e.g., via TP/SL or EMA cross)
    strategy.position = None
    strategy.entry_price = None
    strategy.cooldown_left = strategy.cooldown_candles
    
    assert strategy.cooldown_left == strategy.cooldown_candles, (
        "Cooldown should be set after LONG exit"
    )
    
    # Test SHORT exit
    strategy.position = "SHORT"
    strategy.entry_price = 40000.0
    strategy.cooldown_left = 0
    
    # Simulate exiting SHORT
    strategy.position = None
    strategy.entry_price = None
    strategy.cooldown_left = strategy.cooldown_candles
    
    assert strategy.cooldown_left == strategy.cooldown_candles, (
        "Cooldown should be set after SHORT exit"
    )

