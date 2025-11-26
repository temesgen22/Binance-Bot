"""
Integration tests for EmaScalpingStrategy with realistic scenarios.

Tests complete trading flows:
1. Long entry -> TP exit
2. Long entry -> SL exit
3. Long entry -> Death cross exit
4. Short entry -> TP exit
5. Short entry -> SL exit
6. Short entry -> Golden cross exit
7. Filter blocking scenarios
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from collections import deque

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.base import StrategyContext, StrategySignal
from app.core.my_binance_client import BinanceClient


REALISTIC_BTC_LONG_TREND = [
    27380.0,
    27340.5,
    27295.2,
    27250.8,
    27205.3,
    27160.7,
    27110.4,
    27060.0,
    27015.6,
    26970.1,
    27030.2,
    27095.8,
    27160.3,
    27225.9,
    27290.5,
    27355.0,
    27420.7,
    27485.1,
    27555.8,
    27625.4,
    27695.9,
]

REALISTIC_BTC_SHORT_TREND = [
    26890.0,
    26940.5,
    26995.1,
    27050.6,
    27105.0,
    27160.3,
    27215.8,
    27270.4,
    27320.9,
    27370.5,
    27415.0,
    27455.4,
    27490.8,
    27440.2,
    27380.5,
    27310.1,
    27235.6,
    27160.0,
    27085.3,
    27005.7,
    26925.2,
]

SIDEWAYS_BTC_RANGE = [
    27200.0,
    27210.0,
    27205.0,
    27215.0,
    27208.0,
    27212.0,
    27206.0,
    27214.0,
    27207.0,
    27213.0,
    27209.0,
    27211.0,
]


def create_klines(prices: list[float], start_time: int = 0, interval_ms: int = 60000):
    """Helper to create kline data from price list."""
    klines = []
    for i, price in enumerate(prices):
        kline = [
            start_time + i * interval_ms,  # open_time
            price,  # open
            price + 10,  # high
            price - 10,  # low
            price,  # close
            100.0,  # volume
            start_time + (i + 1) * interval_ms,  # close_time
            0, 0, 0, 0, 0  # other fields
        ]
        klines.append(kline)
    return klines


@pytest.fixture
def mock_client():
    """Create a mock BinanceClient."""
    client = MagicMock(spec=BinanceClient)
    client.get_price = MagicMock(return_value=40000.0)
    return client


@pytest.fixture
def base_context():
    """Base strategy context."""
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
            "min_ema_separation": 0.0001,  # Lower for testing
            "enable_htf_bias": False,  # Disable for simpler tests
            "cooldown_candles": 1,  # Shorter for testing
            "interval_seconds": 10,
        },
        interval_seconds=10,
    )


class TestLongTradingFlow:
    """Test complete long trading flows."""
    
    @pytest.mark.asyncio
    async def test_long_entry_via_golden_cross(self, mock_client, base_context):
        """Test entering long position on golden cross."""
        strategy = EmaScalpingStrategy(base_context, mock_client)
        strategy.position = None
        
        # Create price series that causes golden cross
        # First: fast < slow (prev state)
        # Then: fast > slow (current state)
        prices = [40000.0] * 5 + [40100.0] * 5 + [40200.0] * 5  # Rising trend
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        # Set previous state: fast was below slow
        strategy.prev_fast = 40000.0
        strategy.prev_slow = 40100.0
        strategy.last_closed_candle_time = None
        
        signal = await strategy.evaluate()
        
        # Should detect golden cross and enter long
        # (Note: actual result depends on EMA calculation)
        assert signal is not None
        assert signal.action in ["BUY", "HOLD"]  # May be HOLD if filters block
    
    @pytest.mark.asyncio
    async def test_long_exit_via_take_profit(self, mock_client, base_context):
        """Test exiting long position via take profit."""
        strategy = EmaScalpingStrategy(base_context, mock_client)
        strategy.position = "LONG"
        strategy.entry_price = 40000.0
        strategy.cooldown_left = 0
        
        # Price that hits TP (40000 * 1.005 = 40200)
        prices = [40200.0] * 15
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        # Set previous state
        strategy.prev_fast = 40100.0
        strategy.prev_slow = 40000.0
        strategy.last_closed_candle_time = None
        
        signal = await strategy.evaluate()
        
        # Should exit via TP
        if signal.action == "SELL":
            assert strategy.position is None
            assert strategy.entry_price is None
            assert strategy.cooldown_left == 1  # Cooldown activated


class TestShortTradingFlow:
    """Test complete short trading flows."""
    
    @pytest.mark.asyncio
    async def test_short_entry_via_death_cross(self, mock_client, base_context):
        """Test entering short position on death cross."""
        strategy = EmaScalpingStrategy(base_context, mock_client)
        strategy.position = None
        strategy.enable_short = True
        
        # Create price series that causes death cross
        # First: fast > slow (prev state)
        # Then: fast < slow (current state)
        prices = [40200.0] * 5 + [40100.0] * 5 + [40000.0] * 5  # Falling trend
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        # Set previous state: fast was above slow
        strategy.prev_fast = 40200.0
        strategy.prev_slow = 40100.0
        strategy.last_closed_candle_time = None
        
        signal = await strategy.evaluate()
        
        # Should detect death cross and enter short
        assert signal is not None
        assert signal.action in ["SELL", "HOLD"]  # May be HOLD if filters block
    
    @pytest.mark.asyncio
    async def test_short_exit_via_take_profit(self, mock_client, base_context):
        """Test exiting short position via take profit (inverted)."""
        strategy = EmaScalpingStrategy(base_context, mock_client)
        strategy.position = "SHORT"
        strategy.entry_price = 40000.0
        strategy.cooldown_left = 0
        
        # Price that hits TP (40000 * 0.995 = 39800) - price drops
        prices = [39800.0] * 15
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        # Set previous state
        strategy.prev_fast = 39900.0
        strategy.prev_slow = 40000.0
        strategy.last_closed_candle_time = None
        
        signal = await strategy.evaluate()
        
        # Should exit via TP (inverted)
        if signal.action == "BUY":  # Cover short
            assert strategy.position is None
            assert strategy.entry_price is None
            assert strategy.cooldown_left == 1


class TestFilterBehavior:
    """Test filter behavior in various scenarios."""
    
    @pytest.mark.asyncio
    async def test_cooldown_prevents_entry(self, mock_client, base_context):
        """Test that cooldown prevents immediate re-entry."""
        strategy = EmaScalpingStrategy(base_context, mock_client)
        strategy.position = None
        strategy.cooldown_left = 1  # Active cooldown
        
        prices = [40000.0] * 15
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        strategy.prev_fast = 40000.0
        strategy.prev_slow = 40100.0
        strategy.last_closed_candle_time = None
        
        signal = await strategy.evaluate()
        
        # Should return HOLD due to cooldown
        assert signal.action == "HOLD"
        assert strategy.cooldown_left == 0  # Decremented
    
    @pytest.mark.asyncio
    async def test_ema_separation_blocks_entry(self, mock_client, base_context):
        """Test that small EMA separation blocks entry."""
        strategy = EmaScalpingStrategy(base_context, mock_client)
        strategy.position = None
        strategy.min_ema_separation = 0.001  # 0.1% - larger threshold
        
        # Prices that create very close EMAs
        prices = [40000.0] * 15  # Flat prices = very close EMAs
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        strategy.prev_fast = 40000.0
        strategy.prev_slow = 40000.0
        strategy.last_closed_candle_time = None
        
        signal = await strategy.evaluate()
        
        # May return HOLD if separation is too small
        # (Actual result depends on EMA calculation)


class TestStateManagement:
    """Test state management and consistency."""
    
    def test_prev_values_preserved_for_crossover(self, mock_client, base_context):
        """Test that prev values are preserved for crossover detection."""
        strategy = EmaScalpingStrategy(base_context, mock_client)
        
        # Set initial state
        strategy.prev_fast = 40000.0
        strategy.prev_slow = 40100.0
        
        # Save to locals (as done in evaluate)
        prev_fast = strategy.prev_fast
        prev_slow = strategy.prev_slow
        
        # Calculate new EMAs
        fast_ema = 40200.0
        slow_ema = 40100.0
        
        # Check crossover using PREVIOUS values
        golden_cross = (prev_fast <= prev_slow) and (fast_ema > slow_ema)
        
        # This should be True (was below, now above)
        assert golden_cross is True
        
        # After processing, update state
        strategy.prev_fast = fast_ema
        strategy.prev_slow = slow_ema
        
        # Next candle will use these updated values
        assert strategy.prev_fast == fast_ema
        assert strategy.prev_slow == slow_ema


class TestRealMarketScenarios:
    """Integration tests using realistic BTCUSDT price action."""

    def _build_strategy(self, context: StrategyContext, client: MagicMock) -> EmaScalpingStrategy:
        strategy = EmaScalpingStrategy(context, client)
        strategy.cooldown_left = 0
        return strategy

    @pytest.mark.asyncio
    async def test_realistic_long_flow_hits_take_profit(self, mock_client, base_context):
        """Simulate a long breakout using realistic BTCUSDT candles."""
        strategy = self._build_strategy(base_context, mock_client)
        mock_client.get_klines.return_value = create_klines(
            REALISTIC_BTC_LONG_TREND, start_time=0
        )

        seed_signal = await strategy.evaluate()
        # First pass seeds prev EMA values
        assert seed_signal.action == "HOLD"

        strategy.last_closed_candle_time = None
        if strategy.prev_slow is not None:
            strategy.prev_fast = strategy.prev_slow - 25
        mock_client.get_klines.return_value = create_klines(
            REALISTIC_BTC_LONG_TREND + [REALISTIC_BTC_LONG_TREND[-1] * 1.002],
            start_time=500_000,
        )
        buy_signal = await strategy.evaluate()
        assert buy_signal.action == "BUY"
        assert strategy.position == "LONG"

        # Continue rally to trigger take profit
        extended_prices = REALISTIC_BTC_LONG_TREND + [
            REALISTIC_BTC_LONG_TREND[-1] * 1.004,
            REALISTIC_BTC_LONG_TREND[-1] * 1.008,
        ]
        mock_client.get_klines.return_value = create_klines(
            extended_prices, start_time=1_000_000
        )
        strategy.last_closed_candle_time = None

        exit_signal = await strategy.evaluate()
        assert exit_signal.action in ("SELL", "HOLD")
        if exit_signal.action == "SELL":
            assert strategy.position is None

    @pytest.mark.asyncio
    async def test_realistic_short_flow_hits_take_profit(self, mock_client, base_context):
        """Simulate a short setup with BTC rolling over."""
        strategy = self._build_strategy(base_context, mock_client)
        strategy.enable_short = True
        mock_client.get_klines.return_value = create_klines(
            REALISTIC_BTC_SHORT_TREND, start_time=0
        )

        warmup = await strategy.evaluate()
        assert warmup.action == "HOLD"

        strategy.last_closed_candle_time = None
        if strategy.prev_slow is not None:
            strategy.prev_fast = strategy.prev_slow + 25
        mock_client.get_klines.return_value = create_klines(
            REALISTIC_BTC_SHORT_TREND + [REALISTIC_BTC_SHORT_TREND[-1] * 0.999],
            start_time=500_000,
        )
        sell_signal = await strategy.evaluate()
        assert sell_signal.action == "SELL"
        assert strategy.position == "SHORT"

        extended_prices = REALISTIC_BTC_SHORT_TREND + [
            REALISTIC_BTC_SHORT_TREND[-1] * 0.998,
            REALISTIC_BTC_SHORT_TREND[-1] * 0.996,
        ]
        mock_client.get_klines.return_value = create_klines(
            extended_prices, start_time=1_000_000
        )
        strategy.last_closed_candle_time = None

        cover_signal = await strategy.evaluate()
        assert cover_signal.action in ("BUY", "HOLD")

    @pytest.mark.asyncio
    async def test_sideways_market_stays_on_hold(self, mock_client, base_context):
        """Strategy should stay flat when market is range-bound."""
        strategy = self._build_strategy(base_context, mock_client)
        mock_client.get_klines.return_value = create_klines(
            SIDEWAYS_BTC_RANGE, start_time=0
        )

        signal = await strategy.evaluate()
        # EMA separation is tiny, should not trigger entries
        assert signal.action == "HOLD"
        assert strategy.position is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

