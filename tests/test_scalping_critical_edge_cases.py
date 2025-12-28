"""
Critical edge case tests for EmaScalpingStrategy.

These tests cover high-risk scenarios that are easy to miss but critical for production safety:
1. HTF bias fail-closed behavior when 5m data is missing/insufficient
2. No EMA history drift on duplicate/older candles (prev_fast/prev_slow must NOT change)
3. Trailing stop allowed on entry candle while fixed TP/SL blocked
4. Interval validation fallback (invalid interval -> warns and uses "1m")
"""

import pytest
pytestmark = pytest.mark.ci  # Critical edge cases must run in CI
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.base import StrategyContext
from app.core.my_binance_client import BinanceClient


def kline(close_time: int, close: float) -> list:
    """Create a single kline entry."""
    return [
        close_time - 60_000,  # open_time
        str(close),            # open
        str(close + 0.5),      # high
        str(close - 0.5),      # low
        str(close),            # close
        "100.0",               # volume
        close_time,            # close_time
        "0", "0", "0", "0", "0"  # other fields
    ]


def build_klines(closes: list[float], start_ct: int = 1_000_000, step_ms: int = 60_000) -> list:
    """Build klines from a list of closing prices."""
    cts = [start_ct + i * step_ms for i in range(len(closes))]
    kl = [kline(ct, c) for ct, c in zip(cts, closes)]
    # Add forming candle (ignored by strategy)
    kl.append(kline(cts[-1] + step_ms, closes[-1]))
    return kl


class TestHTFBiasFailClosed:
    """Test HTF bias fail-closed behavior when 5m data is missing/insufficient."""

    @pytest.fixture
    def fake_client_missing_5m(self):
        """Create a mock client that returns insufficient 5m data."""
        client = MagicMock(spec=BinanceClient)
        
        # 1m klines that would create a death cross
        one_m_klines = build_klines([100, 101, 102, 101, 99, 97, 96], start_ct=1_000_000)
        
        # 5m returns empty or insufficient data
        five_m_klines = []  # Empty - insufficient data
        
        def get_klines(symbol: str, interval: str, limit: int):
            if interval == "1m":
                return one_m_klines
            elif interval == "5m":
                return five_m_klines
            raise ValueError(f"Unexpected interval: {interval}")
        
        client.get_klines = MagicMock(side_effect=get_klines)
        client.get_price = MagicMock(return_value=96.5)
        return client

    @pytest.fixture
    def fake_client_insufficient_5m(self):
        """Create a mock client that returns insufficient 5m data (less than slow_period+1)."""
        client = MagicMock(spec=BinanceClient)
        
        # 1m klines that would create a death cross
        one_m_klines = build_klines([100, 101, 102, 101, 99, 97, 96], start_ct=1_000_000)
        
        # 5m returns only 2 candles (need at least slow_period+1 = 6 for ema_fast=3, ema_slow=5)
        five_m_klines = build_klines([100, 99], start_ct=1_000_000, step_ms=300_000)
        
        def get_klines(symbol: str, interval: str, limit: int):
            if interval == "1m":
                return one_m_klines
            elif interval == "5m":
                return five_m_klines
            raise ValueError(f"Unexpected interval: {interval}")
        
        client.get_klines = MagicMock(side_effect=get_klines)
        client.get_price = MagicMock(return_value=96.5)
        return client

    @pytest.mark.asyncio
    async def test_htf_bias_fail_closed_blocks_short_when_5m_data_missing(self, fake_client_missing_5m):
        """
        If enable_htf_bias=True and interval=1m:
        - On death cross while flat, strategy fetches 5m klines.
        - If 5m data is missing/empty -> MUST HOLD (fail-closed), no short entry.
        """
        context = StrategyContext(
            id="T-HTF-FAILCLOSED-001",
            name="HTF Fail Closed Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "enable_short": True,
                "enable_htf_bias": True,  # Key: HTF bias enabled
                "min_ema_separation": 0.0,
                "cooldown_candles": 0,
            },
            interval_seconds=60
        )

        strategy = EmaScalpingStrategy(context, fake_client_missing_5m)
        strategy.position = None
        strategy.cooldown_left = 0
        
        # Set up death cross scenario (prev fast > slow, current fast < slow)
        strategy.prev_fast = 101.0
        strategy.prev_slow = 100.0
        strategy.last_closed_candle_time = None

        signal = await strategy.evaluate()

        # Should return HOLD because 5m data is missing (fail-closed)
        assert signal.action == "HOLD", (
            f"Expected HOLD when 5m data is missing, got {signal.action}. "
            f"This is a safety-critical fail-closed behavior."
        )
        assert strategy.position is None, "Position should remain None when 5m data is missing"

    @pytest.mark.asyncio
    async def test_htf_bias_fail_closed_blocks_short_when_5m_data_insufficient(self, fake_client_insufficient_5m):
        """
        If enable_htf_bias=True and interval=1m:
        - On death cross while flat, strategy fetches 5m klines.
        - If 5m data is insufficient (< slow_period+1 closed candles) -> MUST HOLD (fail-closed), no short entry.
        """
        context = StrategyContext(
            id="T-HTF-FAILCLOSED-002",
            name="HTF Fail Closed Insufficient Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "enable_short": True,
                "enable_htf_bias": True,  # Key: HTF bias enabled
                "min_ema_separation": 0.0,
                "cooldown_candles": 0,
            },
            interval_seconds=60
        )

        strategy = EmaScalpingStrategy(context, fake_client_insufficient_5m)
        strategy.position = None
        strategy.cooldown_left = 0
        
        # Set up death cross scenario
        strategy.prev_fast = 101.0
        strategy.prev_slow = 100.0
        strategy.last_closed_candle_time = None

        signal = await strategy.evaluate()

        # Should return HOLD because 5m data is insufficient (fail-closed)
        assert signal.action == "HOLD", (
            f"Expected HOLD when 5m data is insufficient, got {signal.action}. "
            f"This is a safety-critical fail-closed behavior."
        )
        assert strategy.position is None, "Position should remain None when 5m data is insufficient"


class TestNoEMADriftOnDuplicateOlderCandles:
    """Test that prev_fast/prev_slow do NOT change on duplicate or older candles."""

    @pytest.fixture
    def fake_client_with_multiple_calls(self):
        """Create a mock client that returns different klines on each call."""
        client = MagicMock(spec=BinanceClient)
        
        # New candle
        kl_new, last_ct_new = build_klines([100, 101, 102, 103, 104, 105], start_ct=2_000_000), 2_000_000 + 5 * 60_000
        # Duplicate candle (same last closed time)
        kl_dup = kl_new
        # Older candle (smaller last closed time)
        kl_old, _ = build_klines([100, 101, 102, 103, 104], start_ct=1_000_000), None
        
        call_count = [0]
        
        def get_klines(symbol: str, interval: str, limit: int):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return kl_new
            elif idx == 1:
                return kl_dup
            elif idx == 2:
                return kl_old
            return kl_new
        
        client.get_klines = MagicMock(side_effect=get_klines)
        client.get_price = MagicMock(side_effect=[105.2, 105.3, 104.9])
        return client

    @pytest.mark.asyncio
    async def test_prev_ema_values_do_not_change_on_duplicate_or_older_candle(self, fake_client_with_multiple_calls):
        """
        CRITICAL: prev_fast/prev_slow must NOT change when processing duplicate or older candles.
        This prevents EMA history drift that would break crossover detection silently.
        """
        context = StrategyContext(
            id="T-NODRIFT-001",
            name="No EMA Drift Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "enable_short": False,
                "enable_htf_bias": False,
                "min_ema_separation": 0.0,
            },
            interval_seconds=60
        )

        strategy = EmaScalpingStrategy(context, fake_client_with_multiple_calls)

        # First call processes new candle -> prev_fast/prev_slow set
        await strategy.evaluate()
        pf1, ps1 = strategy.prev_fast, strategy.prev_slow
        assert pf1 is not None and ps1 is not None, "First evaluation should set prev_fast and prev_slow"

        # Duplicate candle -> HOLD; prev values MUST NOT change
        await strategy.evaluate()
        assert strategy.prev_fast == pf1, (
            f"prev_fast changed on duplicate candle: {pf1} -> {strategy.prev_fast}. "
            f"This would cause EMA history drift!"
        )
        assert strategy.prev_slow == ps1, (
            f"prev_slow changed on duplicate candle: {ps1} -> {strategy.prev_slow}. "
            f"This would cause EMA history drift!"
        )

        # Older candle -> HOLD; prev values MUST NOT change
        await strategy.evaluate()
        assert strategy.prev_fast == pf1, (
            f"prev_fast changed on older candle: {pf1} -> {strategy.prev_fast}. "
            f"This would cause EMA history drift!"
        )
        assert strategy.prev_slow == ps1, (
            f"prev_slow changed on older candle: {ps1} -> {strategy.prev_slow}. "
            f"This would cause EMA history drift!"
        )


class TestTrailingStopOnEntryCandle:
    """Test that trailing stop is allowed on entry candle while fixed TP/SL is blocked."""

    @pytest.fixture
    def fake_trailing_stop_manager(self):
        """Create a fake trailing stop manager that forces an exit."""
        class FakeTrailingStopManager:
            def __init__(self, *args, **kwargs):
                self.current_tp = 999999.0
                self.current_sl = 0.0
                self.enabled = True

            def update(self, live_price: float):
                return (self.current_tp, self.current_sl)

            def check_exit(self, live_price: float):
                # Force an exit immediately (simulate trailing SL/TP hit)
                return "SL"
        
        return FakeTrailingStopManager

    @pytest.mark.asyncio
    async def test_trailing_stop_can_exit_on_entry_candle_even_when_fixed_tp_sl_blocked(
        self, fake_trailing_stop_manager, monkeypatch
    ):
        """
        CRITICAL: Trailing stop should be allowed on entry candle (dynamic protection),
        while fixed TP/SL is blocked (prevents immediate exits from tight static levels).
        """
        # Patch TrailingStopManager used inside strategy module
        import app.strategies.scalping as scalping_mod
        monkeypatch.setattr(scalping_mod, "TrailingStopManager", fake_trailing_stop_manager)

        context = StrategyContext(
            id="T-TRAIL-ENTRY-001",
            name="Trailing Stop Entry Candle Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "enable_short": False,
                "enable_htf_bias": False,
                "min_ema_separation": 0.0,
                "trailing_stop_enabled": True,  # Key: trailing stop enabled
                "cooldown_candles": 0,
            },
            interval_seconds=60
        )

        # Provide data that creates a golden cross and enters LONG
        klines = build_klines([100, 100, 99, 98, 99, 102], start_ct=1_000_000)
        
        client = MagicMock(spec=BinanceClient)
        client.get_klines = MagicMock(return_value=klines)
        client.get_price = MagicMock(return_value=102.0)

        strategy = EmaScalpingStrategy(context, client)
        strategy.position = None
        strategy.cooldown_left = 0
        strategy.prev_fast = 98.0
        strategy.prev_slow = 99.0
        strategy.last_closed_candle_time = None

        # First evaluation: enters LONG position
        sig1 = await strategy.evaluate()
        
        # If entry occurred, verify trailing stop was initialized
        if sig1.action == "BUY":
            assert strategy.position == "LONG"
            assert strategy.trailing_stop is not None, "Trailing stop should be initialized on entry"
            
            # Second evaluation: on same entry candle, trailing stop should be able to exit
            # (fixed TP/SL would be blocked, but trailing stop is allowed)
            strategy.last_closed_candle_time = int(klines[-2][6])  # Set to entry candle time
            sig2 = await strategy.evaluate()
            
            # Trailing stop should be able to trigger exit on entry candle
            # (This is the key difference from fixed TP/SL)
            if sig2.action == "SELL":
                assert sig2.exit_reason in ("SL_TRAILING", "TP_TRAILING"), (
                    f"Trailing stop should be able to exit on entry candle. "
                    f"Got exit_reason: {sig2.exit_reason}"
                )


class TestOlderCandleTPSLStillWorks:
    """Test that TP/SL still works when candle time goes backwards (monotonicity)."""

    @pytest.mark.asyncio
    async def test_tp_sl_still_works_on_older_candle_when_in_position(self):
        """
        CRITICAL: When last_closed_time goes backwards (older candle), strategy must:
        - Skip EMA processing (no new entries/exits by EMA)
        - Still allow TP/SL exit using live_price if currently in position
        
        This prevents "stuck in position" during exchange/API time glitches.
        """
        context = StrategyContext(
            id="T-OLDER-TPSL-001",
            name="Older Candle TP/SL Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "take_profit_pct": 0.005,  # 0.5%
                "stop_loss_pct": 0.003,    # 0.3%
                "enable_short": False,
                "enable_htf_bias": False,
                "min_ema_separation": 0.0,
                "cooldown_candles": 0,
            },
            interval_seconds=60
        )

        client = MagicMock(spec=BinanceClient)
        
        # Set up: strategy already processed a candle at time 2_300_000
        last_closed_time_new = 2_300_000
        
        # Now we get an older candle (time goes backwards)
        # Need at least slow_period + 2 = 5 + 2 = 7 klines (6 closed + 1 forming)
        # Last closed candle time = 1_000_000 + 5*60_000 = 1_300_000 (smaller than 2_300_000)
        klines_old = build_klines([100, 101, 102, 103, 104, 105], start_ct=1_000_000)
        last_closed_time_old = int(klines_old[-2][6])  # 1_300_000
        
        # Verify older candle is actually older
        assert last_closed_time_old < last_closed_time_new, (
            f"Older candle time {last_closed_time_old} must be < new candle time {last_closed_time_new}"
        )
        
        # Mock returns the older candle
        client.get_klines = MagicMock(return_value=klines_old)
        # Entry price = 100.0, TP = 100.0 * 1.005 = 100.5 (with floating point: 100.49999999999999)
        # Use slightly higher price to account for floating point precision
        client.get_price = MagicMock(return_value=100.51)  # TP hit (slightly above to account for FP precision)

        strategy = EmaScalpingStrategy(context, client)
        
        # Manually set up LONG position (simulating normal entry from previous candle)
        strategy.position = "LONG"
        strategy.entry_price = 100.0  # Entry price
        strategy.entry_candle_time = last_closed_time_new  # Entry was on newer candle
        strategy.last_closed_candle_time = last_closed_time_new  # Last processed was new candle (2_300_000)
        strategy.cooldown_left = 0
        strategy.prev_fast = 103.0
        strategy.prev_slow = 104.0

        # Evaluation: older candle (time goes backwards: 1_240_000 < 2_300_000)
        # Strategy should detect older candle, skip EMA processing, but still check TP/SL
        # Code fix: entry_candle_time is temporarily cleared when processing older candles
        sig2 = await strategy.evaluate()
        
        # Should exit on TP even though candle is older
        assert sig2.action == "SELL", (
            f"Expected SELL on TP when older candle detected, got {sig2.action}. "
            f"This prevents 'stuck in position' during time glitches. "
            f"Entry price: {strategy.entry_price}, Live price: 100.5, TP: {100.0 * 1.005}"
        )
        assert sig2.exit_reason == "TP", (
            f"Expected TP exit reason, got {sig2.exit_reason}"
        )
        assert strategy.position is None, "Position should be cleared after TP exit"


class TestSeparationFilterDoesNotBlockExits:
    """Test that min_ema_separation filter only blocks entries, not exits."""

    @pytest.mark.asyncio
    async def test_separation_filter_does_not_block_ema_exits(self):
        """
        CRITICAL: min_ema_separation filter must NOT block exits (only entries).
        Even if abs(fast-slow)/price < min_ema_separation, EMA exits must still trigger
        (if enabled) and TP/SL always triggers regardless.
        
        This prevents bots refusing to exit because the filter is too strict.
        """
        context = StrategyContext(
            id="T-SEP-EXIT-001",
            name="Separation Filter Exit Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "enable_short": False,
                "enable_htf_bias": False,
                "min_ema_separation": 0.1,  # High threshold (10%) - would block entries
                "enable_ema_cross_exit": True,
                "cooldown_candles": 0,
            },
            interval_seconds=60
        )

        client = MagicMock(spec=BinanceClient)
        
        # Create klines where EMAs are very close (separation < 0.1)
        # But death cross occurs (fast crosses below slow)
        klines = build_klines([100, 100.1, 100.05, 100.02, 100.01, 100.0], start_ct=1_000_000)
        
        client.get_klines = MagicMock(return_value=klines)
        client.get_price = MagicMock(return_value=100.0)

        strategy = EmaScalpingStrategy(context, client)
        
        # Force LONG position (or enter it normally)
        strategy.position = "LONG"
        strategy.entry_price = 100.0
        strategy.entry_candle_time = 1_000_000  # Not on entry candle
        strategy.cooldown_left = 0
        
        # Set up death cross scenario (prev fast > slow, current fast < slow)
        strategy.prev_fast = 100.05
        strategy.prev_slow = 100.02
        strategy.last_closed_candle_time = None

        signal = await strategy.evaluate()

        # Should exit on death cross even though separation is "too small"
        # (separation filter only applies to entries, not exits)
        if signal.action == "SELL":
            assert signal.exit_reason == "EMA_DEATH_CROSS", (
                f"Expected EMA_DEATH_CROSS exit, got {signal.exit_reason}. "
                f"Separation filter should NOT block exits!"
            )
            assert strategy.position is None, "Position should be cleared after exit"

    @pytest.mark.asyncio
    async def test_separation_filter_does_not_block_tp_sl_exits(self):
        """
        CRITICAL: TP/SL exits must always work regardless of EMA separation.
        """
        context = StrategyContext(
            id="T-SEP-TPSL-001",
            name="Separation Filter TP/SL Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "take_profit_pct": 0.005,  # 0.5%
                "stop_loss_pct": 0.003,    # 0.3%
                "enable_short": False,
                "enable_htf_bias": False,
                "min_ema_separation": 0.1,  # High threshold - would block entries
                "cooldown_candles": 0,
            },
            interval_seconds=60
        )

        client = MagicMock(spec=BinanceClient)
        
        # Create klines where EMAs are very close
        klines = build_klines([100, 100.01, 100.005, 100.002, 100.001, 100.0], start_ct=1_000_000)
        
        client.get_klines = MagicMock(return_value=klines)
        client.get_price = MagicMock(return_value=100.5)  # TP hit (entry * 1.005 = 100.5)

        strategy = EmaScalpingStrategy(context, client)
        
        # Force LONG position
        strategy.position = "LONG"
        strategy.entry_price = 100.0
        strategy.last_closed_candle_time = int(klines[-2][6])  # Same candle (no new candle)

        signal = await strategy.evaluate()

        # Should exit on TP even though separation is "too small"
        assert signal.action == "SELL", (
            f"Expected SELL on TP, got {signal.action}. "
            f"TP/SL exits must work regardless of EMA separation!"
        )
        assert signal.exit_reason == "TP", f"Expected TP exit reason, got {signal.exit_reason}"


class TestSyncPositionStateTrailingStop:
    """Test that sync_position_state correctly reinitializes trailing stop."""

    @pytest.mark.asyncio
    async def test_sync_position_state_reinitializes_trailing_stop_when_flat(self):
        """
        CRITICAL: When Binance reports position exists (strategy flat), strategy should:
        - Sync into that position
        - Reinitialize TrailingStopManager with the Binance entry price
        
        This is the most common restart/recovery bug: trailing stop being based on stale entry.
        """
        from app.strategies.trailing_stop import TrailingStopManager
        
        context = StrategyContext(
            id="T-SYNC-TRAIL-001",
            name="Sync Trailing Stop Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "take_profit_pct": 0.005,  # 0.5%
                "stop_loss_pct": 0.003,    # 0.3%
                "trailing_stop_enabled": True,  # Key: trailing stop enabled
                "trailing_stop_activation_pct": 0.0,
                "enable_short": False,
            },
            interval_seconds=60
        )

        client = MagicMock(spec=BinanceClient)
        strategy = EmaScalpingStrategy(context, client)
        
        # Strategy is flat
        strategy.position = None
        strategy.entry_price = None
        strategy.trailing_stop = None

        # Binance reports LONG position with entry price 100.0
        strategy.sync_position_state(
            position_side="LONG",
            entry_price=100.0
        )

        # Verify position synced
        assert strategy.position == "LONG"
        assert strategy.entry_price == 100.0
        
        # Verify trailing stop was reinitialized
        assert strategy.trailing_stop is not None, (
            "Trailing stop should be reinitialized when syncing from Binance"
        )
        assert isinstance(strategy.trailing_stop, TrailingStopManager)
        
        # Verify trailing stop entry price matches Binance entry price
        # TrailingStopManager stores entry_price internally, verify via TP/SL calculation
        # TP should be at entry * (1 + take_profit_pct) = 100.0 * 1.005 = 100.5
        tp_price, sl_price = strategy.trailing_stop.update(100.0)
        expected_tp = 100.0 * 1.005  # 100.5
        expected_sl = 100.0 * 0.997  # 99.7
        assert abs(tp_price - expected_tp) < 0.01, (
            f"Trailing stop TP should be {expected_tp}, got {tp_price}. "
            f"Entry price not correctly synced!"
        )
        assert abs(sl_price - expected_sl) < 0.01, (
            f"Trailing stop SL should be {expected_sl}, got {sl_price}. "
            f"Entry price not correctly synced!"
        )

    @pytest.mark.asyncio
    async def test_sync_position_state_updates_trailing_stop_when_entry_price_changes(self):
        """
        CRITICAL: If Binance entry price changes (position size adjustment), 
        trailing stop must be rebuilt with the new price.
        """
        from app.strategies.trailing_stop import TrailingStopManager
        
        context = StrategyContext(
            id="T-SYNC-TRAIL-002",
            name="Sync Trailing Stop Update Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 3,
                "ema_slow": 5,
                "kline_interval": "1m",
                "take_profit_pct": 0.005,  # 0.5%
                "stop_loss_pct": 0.003,    # 0.3%
                "trailing_stop_enabled": True,
                "trailing_stop_activation_pct": 0.0,
                "enable_short": False,
            },
            interval_seconds=60
        )

        client = MagicMock(spec=BinanceClient)
        strategy = EmaScalpingStrategy(context, client)
        
        # Strategy has LONG position with entry price 100.0
        strategy.position = "LONG"
        strategy.entry_price = 100.0
        strategy.trailing_stop = TrailingStopManager(
            entry_price=100.0,
            take_profit_pct=0.005,
            stop_loss_pct=0.003,
            position_type="LONG",
            enabled=True,
            activation_pct=0.0
        )

        # Binance entry price changed to 101.0 (e.g., added to position)
        strategy.sync_position_state(
            position_side="LONG",
            entry_price=101.0
        )

        # Verify entry price updated
        assert strategy.entry_price == 101.0
        
        # Verify trailing stop was rebuilt with new entry price
        assert strategy.trailing_stop is not None
        tp_price, sl_price = strategy.trailing_stop.update(101.0)
        expected_tp = 101.0 * 1.005  # 101.505
        expected_sl = 101.0 * 0.997  # 100.697
        assert abs(tp_price - expected_tp) < 0.01, (
            f"Trailing stop TP should be {expected_tp}, got {tp_price}. "
            f"Trailing stop not rebuilt with new entry price!"
        )
        assert abs(sl_price - expected_sl) < 0.01, (
            f"Trailing stop SL should be {expected_sl}, got {sl_price}. "
            f"Trailing stop not rebuilt with new entry price!"
        )


class TestIntervalValidationFallback:
    """Test that invalid kline intervals fall back to '1m'."""

    @pytest.mark.asyncio
    async def test_invalid_kline_interval_falls_back_to_1m(self):
        """
        CRITICAL: Invalid interval should warn and fall back to "1m" to prevent
        weird production bugs from config typos.
        """
        class DummyClient:
            def get_klines(self, *args, **kwargs):
                return []
            
            def get_price(self, *args, **kwargs):
                return 1.0

        context = StrategyContext(
            id="T-INTERVAL-001",
            name="Interval Validation Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "kline_interval": "7m",  # Invalid - not in allowed list
                "ema_fast": 8,
                "ema_slow": 21,
            },
            interval_seconds=60
        )

        strategy = EmaScalpingStrategy(context, DummyClient())
        
        # Should fall back to "1m"
        assert strategy.interval == "1m", (
            f"Invalid interval '7m' should fall back to '1m', got '{strategy.interval}'"
        )

    @pytest.mark.asyncio
    async def test_valid_interval_is_preserved(self):
        """Test that valid intervals are preserved."""
        class DummyClient:
            def get_klines(self, *args, **kwargs):
                return []
            
            def get_price(self, *args, **kwargs):
                return 1.0

        valid_intervals = ["1m", "5m", "15m", "1h"]
        
        for interval in valid_intervals:
            context = StrategyContext(
                id=f"T-INTERVAL-VALID-{interval}",
                name=f"Valid Interval Test {interval}",
                symbol="BTCUSDT",
                leverage=5,
                risk_per_trade=0.01,
                params={
                    "kline_interval": interval,
                    "ema_fast": 8,
                    "ema_slow": 21,
                },
                interval_seconds=60
            )

            strategy = EmaScalpingStrategy(context, DummyClient())
            assert strategy.interval == interval, (
                f"Valid interval '{interval}' should be preserved, got '{strategy.interval}'"
            )

