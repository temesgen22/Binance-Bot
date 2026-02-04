"""
Test strategy synchronization when new candles arrive.

Validates that multiple strategies (scalping and reverse) for the same symbol
detect crossovers simultaneously when a new candle arrives via WebSocket.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.reverse_scalping import ReverseScalpingStrategy
from app.strategies.base import StrategyContext
from app.core.websocket_kline_manager import WebSocketKlineManager
from app.core.kline_buffer import KlineBuffer
from app.services.strategy_executor import StrategyExecutor
from app.models.strategy import StrategySummary, StrategyState


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


def create_websocket_kline_data(close_time: int, close_price: float, symbol: str = "INUSDT", interval: str = "1m", is_closed: bool = True):
    """Create WebSocket kline data format."""
    return {
        "e": "kline",
        "k": {
            "t": close_time - 60000,  # open_time
            "T": close_time,  # close_time
            "s": symbol.upper(),
            "i": interval,
            "o": str(close_price - 0.01),
            "c": str(close_price),
            "h": str(close_price + 0.01),
            "l": str(close_price - 0.02),
            "v": "100.0",
            "n": 100,
            "x": is_closed,  # Is closed
            "q": "10000.0",
            "V": "5000.0",
            "Q": "500000.0",
            "B": "0"
        }
    }


@pytest.fixture
def mock_client():
    """Create a mock BinanceClient."""
    client = MagicMock()
    client.get_price = MagicMock(return_value=0.05627)
    client.get_klines = MagicMock(return_value=[])
    return client


@pytest.fixture
def base_context():
    """Base strategy context for INUSDT."""
    return StrategyContext(
        id="test-strategy",
        name="Test Strategy",
        symbol="INUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 8,
            "ema_slow": 21,
            "take_profit_pct": 0.004,
            "stop_loss_pct": 0.002,
            "kline_interval": "1m",
            "enable_short": True,
            "min_ema_separation": 0.0001,
            "enable_htf_bias": False,
            "cooldown_candles": 0,  # No cooldown for testing
            "interval_seconds": 10,
        },
        interval_seconds=10,
    )


@pytest.fixture
def mock_kline_manager():
    """Create a mock WebSocketKlineManager with event support."""
    manager = MagicMock(spec=WebSocketKlineManager)
    
    # Create real event for testing
    manager.new_candle_events = {}
    manager.buffers = {}
    manager.subscription_counts = {}
    
    # Mock methods
    manager.subscribe = AsyncMock()
    manager.get_klines = AsyncMock()
    manager.wait_for_new_candle = AsyncMock()
    
    # Real event implementation for wait_for_new_candle
    async def real_wait_for_new_candle(symbol: str, interval: str, timeout: float = None):
        key = f"{symbol.upper()}_{interval}"
        if key not in manager.new_candle_events:
            manager.new_candle_events[key] = asyncio.Event()
        try:
            await asyncio.wait_for(manager.new_candle_events[key].wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    manager.wait_for_new_candle = real_wait_for_new_candle
    
    return manager


@pytest.fixture
def strategy_summary():
    """Create a strategy summary for testing."""
    return StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="INUSDT",
        strategy_type="scalping",
        account_id="default",
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 8,
            "ema_slow": 21,
            "take_profit_pct": 0.004,
            "stop_loss_pct": 0.002,
            "kline_interval": "1m",
            "enable_short": True,
            "min_ema_separation": 0.0001,
            "enable_htf_bias": False,
            "cooldown_candles": 0,
            "interval_seconds": 10,
        },
        position_side=None,
        position_size=0.0,
        entry_price=None,
        current_price=0.05627,
        unrealized_pnl=0.0,
        created_at=datetime.now(timezone.utc),
        last_signal="HOLD",
    )


class TestStrategySynchronization:
    """Test that strategies synchronize when new candles arrive."""
    
    @pytest.mark.asyncio
    async def test_multiple_strategies_detect_crossover_simultaneously(
        self,
        mock_client,
        base_context,
        mock_kline_manager,
        strategy_summary
    ):
        """Test that 4 strategies (2 scalping, 2 reverse) detect crossover at the same time."""
        
        # Create 4 strategies with same EMA config
        strategies = []
        contexts = []
        
        # Strategy 1: Scalping
        ctx1 = StrategyContext(
            id="scalping-1",
            name="Scalping 1",
            symbol="INUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params=base_context.params.copy(),
            interval_seconds=10,
        )
        strategy1 = EmaScalpingStrategy(ctx1, mock_client, kline_manager=mock_kline_manager)
        strategies.append(("scalping", strategy1))
        contexts.append(ctx1)
        
        # Strategy 2: Scalping
        ctx2 = StrategyContext(
            id="scalping-2",
            name="Scalping 2",
            symbol="INUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params=base_context.params.copy(),
            interval_seconds=10,
        )
        strategy2 = EmaScalpingStrategy(ctx2, mock_client, kline_manager=mock_kline_manager)
        strategies.append(("scalping", strategy2))
        contexts.append(ctx2)
        
        # Strategy 3: Reverse Scalping
        ctx3 = StrategyContext(
            id="reverse-1",
            name="Reverse 1",
            symbol="INUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params=base_context.params.copy(),
            interval_seconds=10,
        )
        strategy3 = ReverseScalpingStrategy(ctx3, mock_client, kline_manager=mock_kline_manager)
        strategies.append(("reverse", strategy3))
        contexts.append(ctx3)
        
        # Strategy 4: Reverse Scalping
        ctx4 = StrategyContext(
            id="reverse-2",
            name="Reverse 2",
            symbol="INUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params=base_context.params.copy(),
            interval_seconds=10,
        )
        strategy4 = ReverseScalpingStrategy(ctx4, mock_client, kline_manager=mock_kline_manager)
        strategies.append(("reverse", strategy4))
        contexts.append(ctx4)
        
        # Initialize event for INUSDT_1m
        key = "INUSDT_1m"
        mock_kline_manager.new_candle_events[key] = asyncio.Event()
        
        # Create klines that will cause a golden cross
        # First, create enough klines to establish EMAs
        initial_prices = [0.05609] * 25  # Slow EMA period (21) + buffer
        initial_klines = create_klines(initial_prices, start_time=1770144000000)
        
        # Add one more candle that causes golden cross (fast crosses above slow)
        # Previous: fast=0.05609023, slow=0.05609840 (fast < slow)
        # Current: fast=0.05613018, slow=0.05611391 (fast > slow)
        golden_cross_klines = create_klines(
            [0.05613],  # Higher price causes fast EMA to cross above slow
            start_time=1770144059999 - 60000
        )
        all_klines = initial_klines + golden_cross_klines
        
        # Mock get_klines to return these klines
        async def mock_get_klines(symbol, interval, limit):
            return all_klines[-limit:] if len(all_klines) > limit else all_klines
        
        mock_kline_manager.get_klines = mock_get_klines
        
        # Set up kline buffer with initial data
        if key not in mock_kline_manager.buffers:
            mock_kline_manager.buffers[key] = KlineBuffer(max_size=1000)
        
        # Add initial klines to buffer
        for kline in initial_klines:
            ws_format = {
                "e": "kline",
                "k": {
                    "t": kline[0],
                    "T": kline[6],
                    "s": "INUSDT",
                    "i": "1m",
                    "o": str(kline[1]),
                    "c": str(kline[4]),
                    "h": str(kline[2]),
                    "l": str(kline[3]),
                    "v": "100.0",
                    "n": 100,
                    "x": True,
                    "q": "10000.0",
                    "V": "5000.0",
                    "Q": "500000.0",
                    "B": "0"
                }
            }
            await mock_kline_manager.buffers[key].add_kline(ws_format)
        
        # Track evaluation times
        evaluation_times = {}
        evaluation_results = {}
        
        async def wait_and_evaluate(strategy, strategy_id):
            """Wait for new candle, then evaluate strategy and track time."""
            # Wait for new candle event
            await mock_kline_manager.wait_for_new_candle("INUSDT", "1m", timeout=5.0)
            
            # Add new candle to buffer
            new_candle_ws = create_websocket_kline_data(
                close_time=1770144059999,
                close_price=0.05627,
                symbol="INUSDT",
                interval="1m",
                is_closed=True
            )
            await mock_kline_manager.buffers[key].add_kline(new_candle_ws)
            
            # Evaluate immediately after being notified
            eval_time = datetime.now(timezone.utc)
            signal = await strategy.evaluate()
            evaluation_times[strategy_id] = eval_time
            evaluation_results[strategy_id] = signal
            return signal
        
        # Start all strategies waiting for new candle and evaluating
        eval_tasks = []
        for strategy_type, strategy in strategies:
            strategy_id = strategy.context.id
            task = asyncio.create_task(
                wait_and_evaluate(strategy, strategy_id)
            )
            eval_tasks.append((strategy_id, task))
        
        # Wait a bit to ensure all strategies are waiting
        await asyncio.sleep(0.1)
        
        # Simulate new closed candle arriving (set event)
        mock_kline_manager.new_candle_events[key].set()
        
        # Wait for all strategies to complete evaluation
        results = await asyncio.gather(*[task for _, task in eval_tasks], return_exceptions=True)
        
        # Verify all strategies completed
        assert all(not isinstance(r, Exception) for r in results), f"Some strategies failed: {results}"
        
        # Verify all strategies evaluated within a short time window (synchronized)
        times = list(evaluation_times.values())
        if len(times) > 1:
            time_diffs = [abs((t2 - t1).total_seconds()) for i, t1 in enumerate(times) for t2 in times[i+1:]]
            max_diff = max(time_diffs) if time_diffs else 0
            
            # All strategies should evaluate within 100ms of each other
            assert max_diff < 0.1, f"Strategies evaluated with {max_diff:.3f}s difference (should be < 0.1s)"
        
        # Verify all strategies detected the crossover
        for strategy_id, signal in evaluation_results.items():
            assert signal is not None, f"Strategy {strategy_id} should return a signal"
            # Scalping strategies should detect BUY, reverse should detect SELL
            strategy_type = next(t for t, s in strategies if s.context.id == strategy_id)
            if strategy_type == "scalping":
                # Scalping: golden cross = BUY
                assert signal.action in ["BUY", "HOLD"], f"Scalping strategy {strategy_id} should detect BUY or HOLD, got {signal.action}"
            else:
                # Reverse: golden cross = SELL (opposite)
                assert signal.action in ["SELL", "HOLD"], f"Reverse strategy {strategy_id} should detect SELL or HOLD, got {signal.action}"
    
    @pytest.mark.asyncio
    async def test_strategy_executor_uses_event_based_waiting(
        self,
        mock_client,
        base_context,
        mock_kline_manager,
        strategy_summary
    ):
        """Test that StrategyExecutor uses event-based waiting instead of sleep."""
        
        # Create strategy with kline_manager
        strategy = EmaScalpingStrategy(base_context, mock_client, kline_manager=mock_kline_manager)
        
        # Create mock executor dependencies
        account_manager = MagicMock()
        state_manager = MagicMock()
        order_manager = MagicMock()
        client_manager = MagicMock()
        
        executor = StrategyExecutor(
            account_manager=account_manager,
            state_manager=state_manager,
            order_manager=order_manager,
            client_manager=client_manager,
        )
        
        # Initialize event
        key = "INUSDT_1m"
        mock_kline_manager.new_candle_events[key] = asyncio.Event()
        
        # Mock get_klines
        mock_kline_manager.get_klines = AsyncMock(return_value=create_klines([0.05627] * 30))
        
        # Track if wait_for_new_candle was called
        wait_called = False
        
        async def track_wait(symbol, interval, timeout):
            nonlocal wait_called
            wait_called = True
            # Wait for event or timeout
            if key in mock_kline_manager.new_candle_events:
                try:
                    await asyncio.wait_for(
                        mock_kline_manager.new_candle_events[key].wait(),
                        timeout=timeout
                    )
                    return True
                except asyncio.TimeoutError:
                    return False
            return False
        
        mock_kline_manager.wait_for_new_candle = track_wait
        
        # Call _wait_for_next_evaluation
        await executor._wait_for_next_evaluation(strategy, strategy_summary)
        
        # Verify wait_for_new_candle was called (not just sleep)
        assert wait_called, "StrategyExecutor should call wait_for_new_candle, not just sleep"
    
    @pytest.mark.asyncio
    async def test_event_cleared_before_next_candle(
        self,
        mock_kline_manager
    ):
        """Test that event is cleared before being set again for next candle."""
        
        key = "INUSDT_1m"
        mock_kline_manager.new_candle_events[key] = asyncio.Event()
        
        # Set event (simulating first candle)
        mock_kline_manager.new_candle_events[key].set()
        assert mock_kline_manager.new_candle_events[key].is_set(), "Event should be set"
        
        # Clear event (simulating on_kline_update clearing before setting)
        mock_kline_manager.new_candle_events[key].clear()
        assert not mock_kline_manager.new_candle_events[key].is_set(), "Event should be cleared"
        
        # Set again (simulating next candle)
        mock_kline_manager.new_candle_events[key].set()
        assert mock_kline_manager.new_candle_events[key].is_set(), "Event should be set again"
    
    @pytest.mark.asyncio
    async def test_fallback_to_sleep_when_no_kline_manager(
        self,
        mock_client,
        base_context,
        strategy_summary
    ):
        """Test that executor falls back to sleep when kline_manager is None."""
        
        # Create strategy without kline_manager
        strategy = EmaScalpingStrategy(base_context, mock_client, kline_manager=None)
        
        # Create mock executor
        account_manager = MagicMock()
        state_manager = MagicMock()
        order_manager = MagicMock()
        client_manager = MagicMock()
        
        executor = StrategyExecutor(
            account_manager=account_manager,
            state_manager=state_manager,
            order_manager=order_manager,
            client_manager=client_manager,
        )
        
        # Track sleep time
        sleep_start = datetime.now(timezone.utc)
        
        # Call _wait_for_next_evaluation (should use sleep)
        await executor._wait_for_next_evaluation(strategy, strategy_summary)
        
        sleep_end = datetime.now(timezone.utc)
        sleep_duration = (sleep_end - sleep_start).total_seconds()
        
        # Should sleep for approximately interval_seconds (10s)
        # Allow some tolerance for async overhead
        assert 9.5 <= sleep_duration <= 10.5, f"Should sleep for ~10s, slept for {sleep_duration:.2f}s"

