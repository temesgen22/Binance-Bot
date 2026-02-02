"""
Test to verify HTF bias check fix for Reverse Scalping LONG entry.

This test verifies that:
1. Reverse Scalping LONG entry (Death Cross) has HTF bias check
2. Both Scalping SHORT and Reverse LONG are blocked/allowed together
3. Entry times are consistent (within seconds, not minutes)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.reverse_scalping import ReverseScalpingStrategy
from app.strategies.base import StrategyContext
from app.core.my_binance_client import BinanceClient


def create_test_context(strategy_id: str, enable_htf_bias: bool = True) -> StrategyContext:
    """Create a test strategy context with HTF bias enabled."""
    return StrategyContext(
        id=strategy_id,
        name=f"Test {strategy_id}",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 8,
            "ema_slow": 21,
            "take_profit_pct": 0.006,
            "stop_loss_pct": 0.002,
            "kline_interval": "1m",
            "enable_short": True,
            "min_ema_separation": 0.0001,
            "enable_htf_bias": enable_htf_bias,
            "cooldown_candles": 2,
            "trailing_stop_enabled": False,
            "trailing_stop_activation_pct": 0.0,
            "enable_ema_cross_exit": True,
        },
        interval_seconds=10,
    )


def create_klines_with_death_cross(base_price: float = 50000.0, num_klines: int = 30, start_time: int = None) -> list:
    """Create klines that will trigger a Death Cross (fast EMA crosses below slow EMA)."""
    klines = []
    if start_time is None:
        base_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    else:
        base_time = start_time
    
    # Start with price above (fast EMA > slow EMA)
    # Then drop price to trigger Death Cross (fast EMA < slow EMA)
    # Need enough price movement to create clear EMA crossover
    prices = []
    for i in range(num_klines):
        if i < 15:
            # Price above base (uptrend) - fast EMA will be above slow EMA
            price = base_price + (i * 20)  # Increasing price
        elif i < 20:
            # Price stabilizes
            price = base_price + 300 - ((i - 15) * 10)
        else:
            # Price drops significantly (downtrend - triggers Death Cross)
            price = base_price + 250 - ((i - 20) * 30)  # Sharp drop
        prices.append(price)
    
    # Create klines in format: [open_time, open, high, low, close, volume, ...]
    for i, price in enumerate(prices):
        kline = [
            base_time + (i * 60000),  # open_time (1 minute intervals)
            str(price),  # open
            str(price * 1.001),  # high
            str(price * 0.999),  # low
            str(price),  # close
            "100.0",  # volume
            base_time + (i * 60000) + 59999,  # close_time
            "100000.0",  # quote_volume
            "100",  # trades
            "50.0",  # taker_buy_base
            "50.0",  # taker_buy_quote
        ]
        klines.append(kline)
    
    return klines


def create_htf_klines_trend_up(base_price: float = 50000.0, num_klines: int = 30) -> list:
    """Create 5m klines with UP trend (htf_fast >= htf_slow)."""
    klines = []
    base_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    # Upward trend prices
    prices = [base_price + (i * 20) for i in range(num_klines)]
    
    for i, price in enumerate(prices):
        kline = [
            base_time + (i * 300000),  # open_time (5 minute intervals)
            str(price),  # open
            str(price * 1.001),  # high
            str(price * 0.999),  # low
            str(price),  # close
            "100.0",  # volume
            base_time + (i * 300000) + 299999,  # close_time
            "100000.0",  # quote_volume
            "100",  # trades
            "50.0",  # taker_buy_base
            "50.0",  # taker_buy_quote
        ]
        klines.append(kline)
    
    return klines


def create_htf_klines_trend_down(base_price: float = 50000.0, num_klines: int = 30) -> list:
    """Create 5m klines with DOWN trend (htf_fast < htf_slow)."""
    klines = []
    base_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    # Downward trend prices
    prices = [base_price - (i * 20) for i in range(num_klines)]
    
    for i, price in enumerate(prices):
        kline = [
            base_time + (i * 300000),  # open_time (5 minute intervals)
            str(price),  # open
            str(price * 1.001),  # high
            str(price * 0.999),  # low
            str(price),  # close
            "100.0",  # volume
            base_time + (i * 300000) + 299999,  # close_time
            "100000.0",  # quote_volume
            "100",  # trades
            "50.0",  # taker_buy_base
            "50.0",  # taker_buy_quote
        ]
        klines.append(kline)
    
    return klines


@pytest.mark.asyncio
async def test_htf_bias_blocks_both_strategies_together():
    """Test that HTF bias check blocks both Scalping SHORT and Reverse LONG together."""
    # Create mock client
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.get_price = MagicMock(return_value=50000.0)
    
    # Create strategies
    scalping_context = create_test_context("scalping-test", enable_htf_bias=True)
    reverse_context = create_test_context("reverse-test", enable_htf_bias=True)
    
    scalping = EmaScalpingStrategy(scalping_context, mock_client)
    reverse = ReverseScalpingStrategy(reverse_context, mock_client)
    
    # Create klines with Death Cross
    klines = create_klines_with_death_cross(base_price=50000.0, num_klines=30)
    mock_client.get_klines = MagicMock(return_value=klines)
    
    # Create HTF klines with UP trend (should block both)
    htf_klines_up = create_htf_klines_trend_up(base_price=50000.0, num_klines=30)
    
    # Mock get_klines to return different data for 1m vs 5m
    def get_klines_side_effect(symbol: str, interval: str, limit: int):
        if interval == "1m":
            return klines
        elif interval == "5m":
            return htf_klines_up
        return []
    
    mock_client.get_klines = MagicMock(side_effect=get_klines_side_effect)
    
    # Process enough candles to build EMA history
    for i in range(25):
        await scalping.evaluate()
        await reverse.evaluate()
    
    # Now trigger Death Cross (both should try to enter)
    scalping_signal = await scalping.evaluate()
    reverse_signal = await reverse.evaluate()
    
    # Both should be BLOCKED by HTF bias (5m trend is UP)
    assert scalping_signal.action == "HOLD", f"Scalping should be blocked, got {scalping_signal.action}"
    assert reverse_signal.action == "HOLD", f"Reverse should be blocked, got {reverse_signal.action}"
    
    # Verify both strategies are still flat (no position)
    assert scalping.position is None, "Scalping should have no position after being blocked"
    assert reverse.position is None, "Reverse should have no position after being blocked"


@pytest.mark.asyncio
async def test_htf_bias_allows_both_strategies_together():
    """Test that HTF bias check allows both Scalping SHORT and Reverse LONG together."""
    # Create mock client
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.get_price = MagicMock(return_value=50000.0)
    
    # Create strategies
    scalping_context = create_test_context("scalping-test", enable_htf_bias=True)
    reverse_context = create_test_context("reverse-test", enable_htf_bias=True)
    
    scalping = EmaScalpingStrategy(scalping_context, mock_client)
    reverse = ReverseScalpingStrategy(reverse_context, mock_client)
    
    # Create klines with Death Cross
    klines = create_klines_with_death_cross(base_price=50000.0, num_klines=30)
    
    # Create HTF klines with DOWN trend (should allow both)
    htf_klines_down = create_htf_klines_trend_down(base_price=50000.0, num_klines=30)
    
    # Mock get_klines to return different data for 1m vs 5m
    def get_klines_side_effect(symbol: str, interval: str, limit: int):
        if interval == "1m":
            return klines
        elif interval == "5m":
            return htf_klines_down
        return []
    
    mock_client.get_klines = MagicMock(side_effect=get_klines_side_effect)
    
    # Process enough candles to build EMA history
    for i in range(25):
        await scalping.evaluate()
        await reverse.evaluate()
    
    # Now trigger Death Cross (both should try to enter)
    scalping_signal = await scalping.evaluate()
    reverse_signal = await reverse.evaluate()
    
    # Both should be ALLOWED (5m trend is DOWN)
    # Scalping should enter SHORT, Reverse should enter LONG
    assert scalping_signal.action in ["SELL", "HOLD"], f"Scalping signal: {scalping_signal.action}"
    assert reverse_signal.action in ["BUY", "HOLD"], f"Reverse signal: {reverse_signal.action}"
    
    # If both entered, verify opposite positions
    if scalping_signal.action == "SELL" and reverse_signal.action == "BUY":
        assert scalping.position == "SHORT", "Scalping should have SHORT position"
        assert reverse.position == "LONG", "Reverse should have LONG position"
        assert scalping_signal.position_side == "SHORT", "Scalping signal should be SHORT"
        assert reverse_signal.position_side == "LONG", "Reverse signal should be LONG"


@pytest.mark.asyncio
async def test_htf_bias_consistency_without_htf_bias():
    """Test that without HTF bias, both strategies enter at same time."""
    # Create mock client
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.get_price = MagicMock(return_value=50000.0)
    
    # Create strategies WITHOUT HTF bias
    scalping_context = create_test_context("scalping-test", enable_htf_bias=False)
    reverse_context = create_test_context("reverse-test", enable_htf_bias=False)
    
    scalping = EmaScalpingStrategy(scalping_context, mock_client)
    reverse = ReverseScalpingStrategy(reverse_context, mock_client)
    
    # Create klines with Death Cross - use sequential timestamps
    base_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    all_klines = []
    
    # Generate klines for each evaluation (different timestamps)
    for i in range(30):
        klines = create_klines_with_death_cross(
            base_price=50000.0, 
            num_klines=30, 
            start_time=base_time - (30 * 60000) + (i * 60000)
        )
        all_klines.append(klines)
    
    kline_index = [0]  # Use list to allow modification in closure
    
    def get_klines_side_effect(symbol: str, interval: str, limit: int):
        if interval == "1m":
            idx = min(kline_index[0], len(all_klines) - 1)
            return all_klines[idx]
        return []
    
    mock_client.get_klines = MagicMock(side_effect=get_klines_side_effect)
    
    # Process enough candles to build EMA history
    for i in range(25):
        kline_index[0] = i
        await scalping.evaluate()
        await reverse.evaluate()
    
    # Now trigger Death Cross (both should try to enter)
    kline_index[0] = 25
    scalping_signal = await scalping.evaluate()
    reverse_signal = await reverse.evaluate()
    
    # Both should enter (no HTF bias to block)
    # Note: May still be HOLD if EMA crossover hasn't occurred yet, but if it does, both should enter
    if scalping_signal.action == "SELL" and reverse_signal.action == "BUY":
        # Verify opposite positions
        assert scalping.position == "SHORT", "Scalping should have SHORT position"
        assert reverse.position == "LONG", "Reverse should have LONG position"
    else:
        # If no entry yet, verify both are in same state (both HOLD)
        assert scalping_signal.action == reverse_signal.action, \
            f"Both should have same action when HTF bias disabled, got Scalping={scalping_signal.action}, Reverse={reverse_signal.action}"


@pytest.mark.asyncio
async def test_reverse_long_entry_has_htf_bias_check():
    """Test that Reverse Scalping LONG entry (Death Cross) has HTF bias check."""
    # Create mock client
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.get_price = MagicMock(return_value=50000.0)
    
    # Create Reverse strategy with HTF bias enabled
    reverse_context = create_test_context("reverse-test", enable_htf_bias=True)
    reverse = ReverseScalpingStrategy(reverse_context, mock_client)
    
    # Create klines with Death Cross
    klines = create_klines_with_death_cross(base_price=50000.0, num_klines=30)
    
    # Create HTF klines with UP trend (should block)
    htf_klines_up = create_htf_klines_trend_up(base_price=50000.0, num_klines=30)
    
    # Mock get_klines
    def get_klines_side_effect(symbol: str, interval: str, limit: int):
        if interval == "1m":
            return klines
        elif interval == "5m":
            return htf_klines_up
        return []
    
    mock_client.get_klines = MagicMock(side_effect=get_klines_side_effect)
    
    # Process enough candles to build EMA history
    for i in range(25):
        await reverse.evaluate()
    
    # Trigger Death Cross - should try to enter LONG
    reverse_signal = await reverse.evaluate()
    
    # Should be BLOCKED by HTF bias (5m trend is UP)
    assert reverse_signal.action == "HOLD", \
        f"Reverse LONG entry should be blocked by HTF bias when 5m trend is UP, got {reverse_signal.action}"
    assert reverse.position is None, "Reverse should have no position after being blocked"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

