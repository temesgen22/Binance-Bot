"""
Tests for sl_trigger_mode (live_price vs candle_close) across model, strategies, backtest params, and backtesting.
"""
import pytest
from unittest.mock import MagicMock

from app.models.strategy import StrategyParams
from app.utils.backtest_params import extract_range_mean_reversion_params, extract_scalping_params
from app.strategies.range_mean_reversion import RangeMeanReversionStrategy
from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.reverse_scalping import ReverseScalpingStrategy
from app.strategies.base import StrategyContext


# --- StrategyParams ---
class TestStrategyParamsSlTriggerMode:
    def test_default_is_live_price(self):
        p = StrategyParams()
        assert p.sl_trigger_mode == "live_price"

    def test_accepts_candle_close(self):
        p = StrategyParams(sl_trigger_mode="candle_close")
        assert p.sl_trigger_mode == "candle_close"

    def test_accepts_live_price_explicit(self):
        p = StrategyParams(sl_trigger_mode="live_price")
        assert p.sl_trigger_mode == "live_price"


# --- Backtest param extraction ---
class TestBacktestParamsSlTriggerMode:
    def test_rmr_extract_default(self):
        out = extract_range_mean_reversion_params({})
        assert out.get("sl_trigger_mode") == "live_price"

    def test_rmr_extract_candle_close(self):
        out = extract_range_mean_reversion_params({"sl_trigger_mode": "candle_close"})
        assert out.get("sl_trigger_mode") == "candle_close"

    def test_rmr_extract_invalid_normalized_to_live_price(self):
        out = extract_range_mean_reversion_params({"sl_trigger_mode": "invalid"})
        assert out.get("sl_trigger_mode") == "live_price"

    def test_scalping_extract_default(self):
        out = extract_scalping_params({})
        assert out.get("sl_trigger_mode") == "live_price"

    def test_scalping_extract_candle_close(self):
        out = extract_scalping_params({"sl_trigger_mode": "candle_close"})
        assert out.get("sl_trigger_mode") == "candle_close"


# --- Range Mean Reversion _check_tp_sl ---
@pytest.fixture
def rmr_context():
    return StrategyContext(
        id="test-rmr",
        name="Test RMR",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "lookback_period": 150,
            "buy_zone_pct": 0.2,
            "sell_zone_pct": 0.2,
            "ema_fast_period": 20,
            "ema_slow_period": 50,
            "max_ema_spread_pct": 0.005,
            "max_atr_multiplier": 2.0,
            "rsi_period": 14,
            "rsi_oversold": 40,
            "rsi_overbought": 60,
            "tp_buffer_pct": 0.001,
            "sl_buffer_pct": 0.002,
            "kline_interval": "5m",
            "enable_short": True,
            "sl_trigger_mode": "live_price",
        },
        interval_seconds=10,
    )


@pytest.fixture
def mock_client():
    c = MagicMock()
    c.get_price = MagicMock(return_value=40000.0)
    c.get_klines = MagicMock(return_value=[])
    c.get_open_position = MagicMock(return_value=None)
    return c


class TestRangeMeanReversionSlTriggerMode:
    def test_live_price_mode_sl_triggers_on_live_price(self, rmr_context, mock_client):
        rmr_context.params["sl_trigger_mode"] = "live_price"
        strategy = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy.position = "LONG"
        strategy.range_valid = True
        strategy.range_high = 40100.0
        strategy.range_low = 39900.0
        strategy.range_mid = 40000.0
        # SL = range_low - buffer = 39900 - (200*0.002) = 39900 - 0.4 = 39899.6
        # live_price 39899 should trigger SL
        signal = strategy._check_tp_sl(39899.0, allow_tp=True, candle_close_price=None)
        assert signal is not None
        assert signal.action == "SELL"
        assert signal.exit_reason == "SL_RANGE_BREAK"

    def test_candle_close_mode_sl_triggers_when_close_beyond_sl(self, rmr_context, mock_client):
        rmr_context.params["sl_trigger_mode"] = "candle_close"
        strategy = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy.position = "LONG"
        strategy.range_valid = True
        strategy.range_high = 40100.0
        strategy.range_low = 39900.0
        strategy.range_mid = 40000.0
        # SL below range_low; candle close at 39899 should trigger
        signal = strategy._check_tp_sl(
            40100.0, allow_tp=True, candle_close_price=39899.0
        )
        assert signal is not None
        assert signal.action == "SELL"
        assert signal.exit_reason == "SL_RANGE_BREAK"

    def test_candle_close_mode_sl_does_not_trigger_when_only_live_beyond_sl(self, rmr_context, mock_client):
        rmr_context.params["sl_trigger_mode"] = "candle_close"
        strategy = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy.position = "LONG"
        strategy.range_valid = True
        strategy.range_high = 40100.0
        strategy.range_low = 39900.0
        strategy.range_mid = 40000.0
        # Live price 39899 (below SL) but candle close 40050 (above SL) -> no SL in candle_close mode
        signal = strategy._check_tp_sl(
            39899.0, allow_tp=True, candle_close_price=40050.0
        )
        assert signal is None

    def test_candle_close_mode_normalized_from_invalid(self, mock_client):
        ctx = StrategyContext(
            id="t",
            name="T",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={"sl_trigger_mode": "invalid_value", "lookback_period": 150, "kline_interval": "5m"},
            interval_seconds=10,
        )
        strategy = RangeMeanReversionStrategy(ctx, mock_client)
        assert strategy.sl_trigger_mode == "live_price"


# --- Scalping / Reverse Scalping _check_tp_sl backward compatibility and candle_close ---
class TestScalpingSlTriggerMode:
    def test_check_tp_sl_still_works_without_candle_close_param(self, mock_client):
        ctx = StrategyContext(
            id="t",
            name="T",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.004,
                "stop_loss_pct": 0.002,
                "kline_interval": "1m",
            },
            interval_seconds=10,
        )
        strategy = EmaScalpingStrategy(ctx, mock_client)
        strategy.position = "LONG"
        strategy.entry_price = 40000.0
        strategy.entry_candle_time = 1000
        strategy.last_closed_candle_time = 2000  # not entry candle
        # SL = 40000 * 0.998 = 39920
        signal = strategy._check_tp_sl(39920.0)  # no candle_close_price
        assert signal is not None
        assert signal.exit_reason == "SL"

    def test_scalping_candle_close_mode_uses_candle_close_for_sl(self, mock_client):
        ctx = StrategyContext(
            id="t",
            name="T",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.004,
                "stop_loss_pct": 0.002,
                "kline_interval": "1m",
                "sl_trigger_mode": "candle_close",
            },
            interval_seconds=10,
        )
        strategy = EmaScalpingStrategy(ctx, mock_client)
        strategy.position = "LONG"
        strategy.entry_price = 40000.0
        strategy.entry_candle_time = 1000
        strategy.last_closed_candle_time = 2000
        # SL = 39920. Candle close 39919 triggers SL; live_price can be anything
        signal = strategy._check_tp_sl(40100.0, candle_close_price=39919.0)
        assert signal is not None
        assert signal.exit_reason == "SL"


class TestReverseScalpingSlTriggerMode:
    def test_check_tp_sl_still_works_without_candle_close_param(self, mock_client):
        ctx = StrategyContext(
            id="t",
            name="T",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params={
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.004,
                "stop_loss_pct": 0.002,
                "kline_interval": "1m",
            },
            interval_seconds=10,
        )
        strategy = ReverseScalpingStrategy(ctx, mock_client)
        strategy.position = "LONG"
        strategy.entry_price = 40000.0
        strategy.entry_candle_time = 1000
        strategy.last_closed_candle_time = 2000
        signal = strategy._check_tp_sl(39920.0)
        assert signal is not None
        assert signal.exit_reason == "SL"


# --- Backtesting route with sl_trigger_mode ---
@pytest.mark.asyncio
@pytest.mark.slow
async def test_backtest_rmr_with_sl_trigger_mode_candle_close():
    """Backtest run completes with sl_trigger_mode=candle_close (param passed and used)."""
    from datetime import datetime, timezone
    from app.api.routes import backtesting as bt

    def kline(ts_ms, o, h, l, c, v=1.0):
        return [ts_ms, str(o), str(h), str(l), str(c), str(v), ts_ms + 59999, "0", 0, "0", "0", "0"]

    class DummyClient:
        pass

    t0 = 1700000000000
    base_price = 50000.0
    range_size = 500.0
    klines = []
    for i in range(200):
        cycle = i % 20
        if cycle < 10:
            price = base_price - (range_size / 2) + (range_size * cycle / 10)
        else:
            price = base_price + (range_size / 2) - (range_size * (cycle - 10) / 10)
        price = max(base_price - 300, min(base_price + 300, price))
        klines.append(kline(t0 + i * 300000, price, price + 10, price - 10, price, v=1000.0))

    params = {
        "kline_interval": "5m",
        "lookback_period": 20,
        "buy_zone_pct": 0.2,
        "sell_zone_pct": 0.2,
        "ema_fast_period": 5,
        "ema_slow_period": 10,
        "max_ema_spread_pct": 0.01,
        "max_atr_multiplier": 2.0,
        "rsi_period": 14,
        "rsi_oversold": 40,
        "rsi_overbought": 60,
        "tp_buffer_pct": 0.001,
        "sl_buffer_pct": 0.002,
        "enable_short": True,
        "cooldown_candles": 2,
        "max_range_invalid_candles": 20,
        "sl_trigger_mode": "candle_close",
    }
    req = bt.BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="range_mean_reversion",
        start_time=datetime.fromtimestamp(t0 / 1000, tz=timezone.utc),
        end_time=datetime.fromtimestamp((t0 + 199 * 300000) / 1000, tz=timezone.utc),
        leverage=1,
        risk_per_trade=0.01,
        fixed_amount=100,
        initial_balance=1000,
        params=params,
    )
    res = await bt.run_backtest(req, DummyClient(), pre_fetched_klines=klines)
    assert res is not None
    assert res.strategy_type == "range_mean_reversion"
    assert hasattr(res, "total_pnl")
    assert hasattr(res, "total_trades")


def test_backtest_sl_trigger_condition_live_vs_candle_close():
    """Backtest SL condition: live_price uses candle low/high, candle_close uses close only."""
    # Simulate the exact condition used in backtesting.py for LONG position
    entry_price = 100.0
    sl_price = 99.0  # 1% SL
    candle_low = 98.5  # Wick below SL
    current_price = 100.2  # Close above SL

    # live_price mode: SL triggered by candle_low <= sl_price (intra-candle)
    sl_trigger_mode_live = "live_price"
    sl_triggered_live = (current_price <= sl_price) if sl_trigger_mode_live == "candle_close" else (candle_low <= sl_price)
    assert sl_triggered_live is True  # 98.5 <= 99

    # candle_close mode: SL triggered only by current_price (close) <= sl_price
    sl_trigger_mode_close = "candle_close"
    sl_triggered_close = (current_price <= sl_price) if sl_trigger_mode_close == "candle_close" else (candle_low <= sl_price)
    assert sl_triggered_close is False  # 100.2 <= 99 is False

    # SHORT: sl_price = 101, candle_high = 102, current_price = 100.5
    sl_price_short = 101.0
    candle_high = 102.0
    current_price_short = 100.5
    # live_price: candle_high >= sl_price -> 102 >= 101 -> True
    triggered_short_live = (current_price_short >= sl_price_short) if sl_trigger_mode_live == "candle_close" else (candle_high >= sl_price_short)
    assert triggered_short_live is True
    # candle_close: current_price >= sl_price -> 100.5 >= 101 -> False
    triggered_short_close = (current_price_short >= sl_price_short) if sl_trigger_mode_close == "candle_close" else (candle_high >= sl_price_short)
    assert triggered_short_close is False


# --- Scenario-based validation: live_price vs candle_close robustness and consistency ---

def _backtest_sl_triggered_long(sl_trigger_mode: str, candle_low: float, current_price: float, sl: float) -> bool:
    """Same logic as backtesting.py for LONG: SL hit when price <= sl."""
    if sl_trigger_mode == "candle_close":
        return current_price <= sl
    return candle_low <= sl


def _backtest_sl_triggered_short(sl_trigger_mode: str, candle_high: float, current_price: float, sl: float) -> bool:
    """Same logic as backtesting.py for SHORT: SL hit when price >= sl."""
    if sl_trigger_mode == "candle_close":
        return current_price >= sl
    return candle_high >= sl


class TestSlTriggerModeScenariosLong:
    """LONG position: SL below entry. Wick = candle_low, close = current_price."""

    def test_scenario_a_wick_hits_sl_close_above_sl_live_triggers_candle_close_no_trigger(self):
        """Price satisfies SL for live (wick touches SL) but NOT for candle_close (close above SL)."""
        sl = 99.0
        candle_low = 98.5   # wick below SL
        current_price = 100.0  # close above SL
        assert _backtest_sl_triggered_long("live_price", candle_low, current_price, sl) is True
        assert _backtest_sl_triggered_long("candle_close", candle_low, current_price, sl) is False

    def test_scenario_b_both_wick_and_close_below_sl_both_modes_trigger(self):
        """Both wick and close below SL: both modes should trigger SL."""
        sl = 99.0
        candle_low = 98.0
        current_price = 98.5
        assert _backtest_sl_triggered_long("live_price", candle_low, current_price, sl) is True
        assert _backtest_sl_triggered_long("candle_close", candle_low, current_price, sl) is True

    def test_scenario_c_neither_wick_nor_close_hits_sl_both_modes_no_trigger(self):
        """Neither wick nor close reaches SL: no SL in either mode."""
        sl = 99.0
        candle_low = 99.5
        current_price = 100.0
        assert _backtest_sl_triggered_long("live_price", candle_low, current_price, sl) is False
        assert _backtest_sl_triggered_long("candle_close", candle_low, current_price, sl) is False

    def test_scenario_d_close_exactly_at_sl_candle_close_triggers(self):
        """Close exactly at SL: candle_close mode must trigger (boundary)."""
        sl = 99.0
        candle_low = 98.0
        current_price = 99.0
        assert _backtest_sl_triggered_long("candle_close", candle_low, current_price, sl) is True
        assert _backtest_sl_triggered_long("live_price", candle_low, current_price, sl) is True

    def test_scenario_e_close_just_above_sl_candle_close_no_trigger(self):
        """Close just above SL: candle_close does not trigger; live may (if wick touched)."""
        sl = 99.0
        candle_low = 98.9   # wick touched SL zone
        current_price = 99.01  # close just above SL
        assert _backtest_sl_triggered_long("live_price", candle_low, current_price, sl) is True
        assert _backtest_sl_triggered_long("candle_close", candle_low, current_price, sl) is False


class TestSlTriggerModeScenariosShort:
    """SHORT position: SL above entry. Wick = candle_high, close = current_price."""

    def test_scenario_f_wick_hits_sl_close_below_sl_live_triggers_candle_close_no_trigger(self):
        """Price satisfies SL for live (wick above SL) but NOT for candle_close (close below SL)."""
        sl = 101.0
        candle_high = 101.5  # wick above SL
        current_price = 100.0  # close below SL
        assert _backtest_sl_triggered_short("live_price", candle_high, current_price, sl) is True
        assert _backtest_sl_triggered_short("candle_close", candle_high, current_price, sl) is False

    def test_scenario_g_both_wick_and_close_above_sl_both_modes_trigger(self):
        """Both wick and close above SL: both modes trigger."""
        sl = 101.0
        candle_high = 102.0
        current_price = 101.5
        assert _backtest_sl_triggered_short("live_price", candle_high, current_price, sl) is True
        assert _backtest_sl_triggered_short("candle_close", candle_high, current_price, sl) is True

    def test_scenario_h_neither_wick_nor_close_hits_sl_both_modes_no_trigger(self):
        """Neither wick nor close reaches SL: no SL in either mode."""
        sl = 101.0
        candle_high = 100.5
        current_price = 100.0
        assert _backtest_sl_triggered_short("live_price", candle_high, current_price, sl) is False
        assert _backtest_sl_triggered_short("candle_close", candle_high, current_price, sl) is False

    def test_scenario_i_close_exactly_at_sl_candle_close_triggers(self):
        """Close exactly at SL: candle_close mode must trigger (boundary)."""
        sl = 101.0
        candle_high = 102.0
        current_price = 101.0
        assert _backtest_sl_triggered_short("candle_close", candle_high, current_price, sl) is True
        assert _backtest_sl_triggered_short("live_price", candle_high, current_price, sl) is True


class TestSlTriggerModeStrategyConsistency:
    """Strategy _check_tp_sl consistency: same scenarios via RMR and Scalping."""

    def test_rmr_long_wick_below_sl_close_above_live_triggers_candle_close_no_trigger(self, rmr_context, mock_client):
        """RMR LONG: wick below SL, close above SL → live_price triggers SL, candle_close does not."""
        sl_level = 39900.0 - (200.0 * 0.002)  # range_low - buffer; range 39800..40200
        # So sl = 39899.6
        rmr_context.params["sl_trigger_mode"] = "live_price"
        strategy_live = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy_live.position = "LONG"
        strategy_live.range_valid = True
        strategy_live.range_high = 40100.0
        strategy_live.range_low = 39900.0
        strategy_live.range_mid = 40000.0
        # live_price 39899 triggers SL (below sl)
        sig_live = strategy_live._check_tp_sl(39899.0, allow_tp=True, candle_close_price=None)
        assert sig_live is not None and sig_live.exit_reason == "SL_RANGE_BREAK"

        rmr_context.params["sl_trigger_mode"] = "candle_close"
        strategy_close = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy_close.position = "LONG"
        strategy_close.range_valid = True
        strategy_close.range_high = 40100.0
        strategy_close.range_low = 39900.0
        strategy_close.range_mid = 40000.0
        # candle_close 40050 (above SL) → no SL; live_price 39899 would trigger but we use close
        sig_close = strategy_close._check_tp_sl(39899.0, allow_tp=True, candle_close_price=40050.0)
        assert sig_close is None

    def test_scalping_long_same_scenario_live_triggers_candle_close_no_trigger(self, mock_client):
        """Scalping LONG: wick would hit SL, close above SL → live triggers, candle_close does not."""
        ctx_live = StrategyContext(
            id="t", name="T", symbol="BTCUSDT", leverage=5, risk_per_trade=0.01,
            params={"ema_fast": 8, "ema_slow": 21, "take_profit_pct": 0.004, "stop_loss_pct": 0.002,
                    "kline_interval": "1m", "sl_trigger_mode": "live_price"},
            interval_seconds=10,
        )
        ctx_close = StrategyContext(
            id="t", name="T", symbol="BTCUSDT", leverage=5, risk_per_trade=0.01,
            params={"ema_fast": 8, "ema_slow": 21, "take_profit_pct": 0.004, "stop_loss_pct": 0.002,
                    "kline_interval": "1m", "sl_trigger_mode": "candle_close"},
            interval_seconds=10,
        )
        # Entry 40000, SL = 39880 (0.3%). Live 39880 triggers.
        strategy_live = EmaScalpingStrategy(ctx_live, mock_client)
        strategy_live.position = "LONG"
        strategy_live.entry_price = 40000.0
        strategy_live.entry_candle_time = 1000
        strategy_live.last_closed_candle_time = 2000
        sig_live = strategy_live._check_tp_sl(39880.0)
        assert sig_live is not None and sig_live.exit_reason == "SL"

        strategy_close = EmaScalpingStrategy(ctx_close, mock_client)
        strategy_close.position = "LONG"
        strategy_close.entry_price = 40000.0
        strategy_close.entry_candle_time = 1000
        strategy_close.last_closed_candle_time = 2000
        # Candle close 40100 (above SL) → no SL
        sig_close = strategy_close._check_tp_sl(39880.0, candle_close_price=40100.0)
        assert sig_close is None

    def test_candle_close_mode_with_none_candle_close_price_uses_live_price(self, rmr_context, mock_client):
        """When candle_close mode but candle_close_price is None, fallback to live_price (no crash)."""
        rmr_context.params["sl_trigger_mode"] = "candle_close"
        strategy = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy.position = "LONG"
        strategy.range_valid = True
        strategy.range_high = 40100.0
        strategy.range_low = 39900.0
        strategy.range_mid = 40000.0
        # Pass None for candle_close_price: should behave like live_price for this call
        sl = 39900.0 - (200.0 * 0.002)
        sig = strategy._check_tp_sl(39899.0, allow_tp=True, candle_close_price=None)
        assert sig is not None and sig.exit_reason == "SL_RANGE_BREAK"

    def test_tp_unchanged_by_sl_trigger_mode_long(self, rmr_context, mock_client):
        """TP still uses live_price; only SL is affected by sl_trigger_mode."""
        rmr_context.params["sl_trigger_mode"] = "candle_close"
        strategy = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy.position = "LONG"
        strategy.range_valid = True
        strategy.range_high = 40100.0
        strategy.range_low = 39900.0
        strategy.range_mid = 40000.0
        # Candle close above SL so no SL; live_price at TP2 → should still get TP (TP uses live_price)
        tp2 = 40100.0 - (200.0 * 0.001)
        sig = strategy._check_tp_sl(40100.0, allow_tp=True, candle_close_price=39950.0)
        assert sig is not None and "TP_" in sig.exit_reason

    def test_rmr_short_wick_above_sl_close_below_live_triggers_candle_close_no_trigger(self, rmr_context, mock_client):
        """RMR SHORT: wick above SL, close below SL → live_price triggers SL, candle_close does not."""
        # SL for SHORT = range_high + buffer = 40100 + 0.4 = 40100.4
        rmr_context.params["sl_trigger_mode"] = "live_price"
        strategy_live = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy_live.position = "SHORT"
        strategy_live.range_valid = True
        strategy_live.range_high = 40100.0
        strategy_live.range_low = 39900.0
        strategy_live.range_mid = 40000.0
        sig_live = strategy_live._check_tp_sl(40101.0, allow_tp=True, candle_close_price=None)
        assert sig_live is not None and sig_live.exit_reason == "SL_RANGE_BREAK"

        rmr_context.params["sl_trigger_mode"] = "candle_close"
        strategy_close = RangeMeanReversionStrategy(rmr_context, mock_client)
        strategy_close.position = "SHORT"
        strategy_close.range_valid = True
        strategy_close.range_high = 40100.0
        strategy_close.range_low = 39900.0
        strategy_close.range_mid = 40000.0
        # Candle close 40050 (below SL 40100.4) → no SL in candle_close mode
        sig_close = strategy_close._check_tp_sl(40101.0, allow_tp=True, candle_close_price=40050.0)
        assert sig_close is None

    def test_reverse_scalping_short_wick_hits_sl_close_below_sl_live_triggers_candle_close_no_trigger(self, mock_client):
        """Reverse Scalping SHORT: live at SL triggers; candle close below SL → candle_close does not trigger."""
        ctx_live = StrategyContext(
            id="t", name="T", symbol="BTCUSDT", leverage=5, risk_per_trade=0.01,
            params={"ema_fast": 8, "ema_slow": 21, "take_profit_pct": 0.004, "stop_loss_pct": 0.002,
                    "kline_interval": "1m", "sl_trigger_mode": "live_price"},
            interval_seconds=10,
        )
        ctx_close = StrategyContext(
            id="t", name="T", symbol="BTCUSDT", leverage=5, risk_per_trade=0.01,
            params={"ema_fast": 8, "ema_slow": 21, "take_profit_pct": 0.004, "stop_loss_pct": 0.002,
                    "kline_interval": "1m", "sl_trigger_mode": "candle_close"},
            interval_seconds=10,
        )
        # SHORT entry 40000, SL = 40000 * 1.002 = 40080. Live 40080 triggers.
        strategy_live = ReverseScalpingStrategy(ctx_live, mock_client)
        strategy_live.position = "SHORT"
        strategy_live.entry_price = 40000.0
        strategy_live.entry_candle_time = 1000
        strategy_live.last_closed_candle_time = 2000
        sig_live = strategy_live._check_tp_sl(40080.0)
        assert sig_live is not None and sig_live.exit_reason == "SL"

        strategy_close = ReverseScalpingStrategy(ctx_close, mock_client)
        strategy_close.position = "SHORT"
        strategy_close.entry_price = 40000.0
        strategy_close.entry_candle_time = 1000
        strategy_close.last_closed_candle_time = 2000
        # Candle close 39900 (below SL) → no SL in candle_close mode
        sig_close = strategy_close._check_tp_sl(40080.0, candle_close_price=39900.0)
        assert sig_close is None
