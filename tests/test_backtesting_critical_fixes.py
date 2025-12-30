"""
Critical backtesting validation tests.

These tests lock in production-critical guarantees to prevent regression:
1. Entry uses next candle open (no lookahead bias)
2. TP/SL blocked on entry candle
3. Intrabar TP uses exact TP level (not close price)
4. SL wins when both TP and SL hit same candle
5. Range snapshots use only closed candles (no lookahead)
6. No re-entry same candle after exit
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.api.routes import backtesting as bt
from app.strategies.base import StrategySignal


def kline(ts_ms, o, h, l, c, v=1.0):
    """Create a kline in Binance format.
    
    Args:
        ts_ms: Timestamp in milliseconds
        o: Open price
        h: High price
        l: Low price
        c: Close price
        v: Volume (default 1.0)
    
    Returns:
        List in Binance kline format: [open_time, open, high, low, close, volume, close_time, ...]
    """
    return [ts_ms, str(o), str(h), str(l), str(c), str(v), ts_ms + 59999, "0", 0, "0", "0", "0"]


class DummyClient:
    """Dummy BinanceClient for testing.
    
    Only used because run_backtest expects a BinanceClient instance for _fetch_historical_klines.
    """
    pass


def dt(ts_ms):
    """Convert timestamp in milliseconds to timezone-aware datetime (UTC)."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


@pytest.mark.ci
@pytest.mark.asyncio
async def test_entry_uses_next_candle_open(monkeypatch):
    """Test 1: Entry uses next candle open (no lookahead).
    
    Locks the "signal at i-1 close → enter at i open" fix.
    Validates that entry price is candle i's open, not candle i's close.
    
    Note: With ema_slow=1, min_required_candles = 2, so first evaluation is at index 2.
    Signal generated from candle 1 close (100), entry should be at candle 2 open (300).
    """
    t0 = 1700000000000
    klines = [
        kline(t0,          100, 101,  99, 100),  # 0
        kline(t0+60000,    100, 101,  99, 100),  # 1 - signal generated from this close
        kline(t0+120000,   300, 310, 290, 305),  # 2 (open=300 close=305) - entry should use open=300
        kline(t0+180000,   400, 410, 390, 405),  # 3
    ]

    async def fake_fetch(*args, **kwargs):
        return klines
    monkeypatch.setattr(bt, "_fetch_historical_klines", fake_fetch)

    calls = {"n": 0}
    async def fake_eval(self):
        calls["n"] += 1
        # First evaluation (at index 2) creates entry signal based on candle 1 close (100)
        if calls["n"] == 1:
            return StrategySignal(action="BUY", symbol="BTCUSDT", confidence=1.0, price=100.0)
        return StrategySignal(action="HOLD", symbol="BTCUSDT", confidence=0.0, price=None)
    monkeypatch.setattr(bt.EmaScalpingStrategy, "evaluate", fake_eval)

    req = bt.BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=dt(t0),
        end_time=dt(t0+180000),
        leverage=1,
        risk_per_trade=0.01,
        fixed_amount=100,
        initial_balance=1000,
        params={"ema_slow": 1, "ema_fast": 1, "kline_interval": "1m"}  # min_required_candles = 2
    )

    res = await bt.run_backtest(req, DummyClient())
    
    assert len(res.trades) > 0, "Should have at least one trade"
    trade = res.trades[0]

    # Entry should use candle 2's open (300) with spread, NOT candle 2's close (305)
    expected_entry = 300 * (1 + bt.SPREAD_OFFSET)  # LONG pays ask
    assert abs(trade["entry_price"] - expected_entry) < 1e-9, \
        f"Entry price should be candle 2 open with spread ({expected_entry}), got {trade['entry_price']}"
    
    # Verify it's NOT using candle 2's close
    wrong_entry = 305 * (1 + bt.SPREAD_OFFSET)
    assert abs(trade["entry_price"] - wrong_entry) > 1e-6, \
        f"Entry price should NOT be candle 2 close ({wrong_entry}), got {trade['entry_price']}"


@pytest.mark.ci
@pytest.mark.asyncio
async def test_scalping_blocks_tp_on_entry_candle(monkeypatch):
    """Test 2: Scalping TP/SL blocked on entry candle.
    
    Validates that TP hit on the same candle as entry does NOT trigger exit.
    Specifically tests: on_entry_candle = (entry_candle_time == int(kline[0]))
    """
    t0 = 1700000000000
    # candle 1 high hits TP immediately, but entry happens at candle 1 open
    klines = [
        kline(t0,        100, 101,  99, 100),  # 0 - signal generated here
        kline(t0+60000,  200, 250, 190, 205),  # 1 - entry candle: high=250 (hits TP), open=200
        kline(t0+120000, 205, 210, 200, 208),  # 2 - later candle
    ]

    async def fake_fetch(*args, **kwargs):
        return klines
    monkeypatch.setattr(bt, "_fetch_historical_klines", fake_fetch)

    calls = {"n": 0}
    async def fake_eval(self):
        calls["n"] += 1
        if calls["n"] == 1:
            # Signal generated from candle 0 close
            return StrategySignal(action="BUY", symbol="BTCUSDT", confidence=1.0, price=100.0)
        return StrategySignal(action="HOLD", symbol="BTCUSDT", confidence=0.0, price=None)
    monkeypatch.setattr(bt.EmaScalpingStrategy, "evaluate", fake_eval)

    req = bt.BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=dt(t0),
        end_time=dt(t0+120000),
        leverage=1,
        risk_per_trade=0.01,
        fixed_amount=100,
        initial_balance=1000,
        params={
            "ema_slow": 1, "ema_fast": 1, "kline_interval": "1m",
            "trailing_stop_enabled": False,
            "take_profit_pct": 0.01,  # TP 1% - candle 1 high (250) would hit this
            "stop_loss_pct": 0.01,
        }
    )

    res = await bt.run_backtest(req, DummyClient())

    assert len(res.trades) > 0, "Should have at least one trade"
    trade = res.trades[0]
    
    # If entry candle protection works, trade should NOT be closed at candle 1
    # Entry happens at candle 1 open, so TP should be blocked on candle 1
    assert trade["exit_time"] is None or trade["exit_reason"] != "TP", \
        f"TP should be blocked on entry candle, but trade exited with {trade.get('exit_reason')}"


@pytest.mark.ci
@pytest.mark.asyncio
async def test_scalping_intrabar_tp_uses_high_and_exits_at_level(monkeypatch):
    """Test 3: Scalping intrabar TP hits on later candle → exit at exact TP level (not close).
    
    Validates that:
    - TP detection uses candle high (intrabar detection)
    - Exit price is exact TP level, not candle close
    """
    t0 = 1700000000000
    klines = [
        kline(t0,        100, 101,  99, 100),  # 0
        kline(t0+60000,  100, 101,  99, 100),  # 1 - signal generated from this close
        kline(t0+120000, 200, 201, 199, 200),  # 2 - entry candle (TP blocked here)
        kline(t0+180000, 200, 206, 198, 199),  # 3 - TP hit by high=206, close=199 (below TP)
    ]

    async def fake_fetch(*args, **kwargs):
        return klines
    monkeypatch.setattr(bt, "_fetch_historical_klines", fake_fetch)

    calls = {"n": 0}
    async def fake_eval(self):
        calls["n"] += 1
        if calls["n"] == 1:
            return StrategySignal(action="BUY", symbol="BTCUSDT", confidence=1.0, price=100.0)
        return StrategySignal(action="HOLD", symbol="BTCUSDT", confidence=0.0, price=None)
    monkeypatch.setattr(bt.EmaScalpingStrategy, "evaluate", fake_eval)

    tp_pct = 0.02  # 2%
    req = bt.BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=dt(t0),
        end_time=dt(t0+180000),
        leverage=1,
        risk_per_trade=0.01,
        fixed_amount=100,
        initial_balance=1000,
        params={
            "ema_slow": 1, "ema_fast": 1, "kline_interval": "1m",
            "trailing_stop_enabled": False,
            "take_profit_pct": tp_pct,
            "stop_loss_pct": 0.5,  # not relevant for this test
        }
    )

    res = await bt.run_backtest(req, DummyClient())
    
    assert len(res.trades) > 0, "Should have at least one trade"
    trade = res.trades[0]
    assert trade["exit_reason"] == "TP", f"Trade should exit with TP, got {trade.get('exit_reason')}"

    # Entry uses candle 2 open with spread
    entry_base = 200
    entry_real = entry_base * (1 + bt.SPREAD_OFFSET)
    tp_level = entry_real * (1 + tp_pct)
    expected_exit = tp_level * (1 - bt.SPREAD_OFFSET)  # LONG exits at bid

    assert abs(trade["exit_price"] - expected_exit) < 1e-6, \
        f"Exit price should be exact TP level ({expected_exit}), got {trade['exit_price']}"
    
    # Must NOT exit at candle close (199)
    assert abs(trade["exit_price"] - 199) > 1e-3, \
        f"Exit price should NOT be candle close (199), got {trade['exit_price']}"


@pytest.mark.ci
@pytest.mark.asyncio
async def test_scalping_tp_sl_same_candle_sl_wins(monkeypatch):
    """Test 4: Both TP and SL hit in same candle → SL wins (scalping).
    
    Validates priority: SL first (conservative - assume worse outcome if both hit).
    """
    t0 = 1700000000000
    klines = [
        kline(t0,        100, 101,  99, 100),  # 0
        kline(t0+60000,  100, 101,  99, 100),  # 1 - signal generated from this close
        kline(t0+120000, 200, 201, 199, 200),  # 2 - entry candle
        kline(t0+180000, 200, 250, 150, 199),  # 3 - both TP (high=250) and SL (low=150) hit
    ]

    async def fake_fetch(*args, **kwargs):
        return klines
    monkeypatch.setattr(bt, "_fetch_historical_klines", fake_fetch)

    calls = {"n": 0}
    async def fake_eval(self):
        calls["n"] += 1
        if calls["n"] == 1:
            return StrategySignal(action="BUY", symbol="BTCUSDT", confidence=1.0, price=100.0)
        return StrategySignal(action="HOLD", symbol="BTCUSDT", confidence=0.0, price=None)
    monkeypatch.setattr(bt.EmaScalpingStrategy, "evaluate", fake_eval)

    req = bt.BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=dt(t0),
        end_time=dt(t0+180000),
        leverage=1,
        risk_per_trade=0.01,
        fixed_amount=100,
        initial_balance=1000,
        params={
            "ema_slow": 1, "ema_fast": 1, "kline_interval": "1m",
            "trailing_stop_enabled": False,
            "take_profit_pct": 0.10,  # 10% - high=250 would hit this
            "stop_loss_pct": 0.10,    # 10% - low=150 would hit this
        }
    )

    res = await bt.run_backtest(req, DummyClient())
    
    assert len(res.trades) > 0, "Should have at least one trade"
    trade = res.trades[0]
    assert trade["exit_reason"] == "SL", \
        f"When both TP and SL hit, SL should win (conservative), got {trade.get('exit_reason')}"


@pytest.mark.ci
@pytest.mark.asyncio
async def test_range_snapshots_do_not_use_current_candle_close(monkeypatch):
    """Test 5: Range Mean Reversion snapshot indicators use only closed candles (no lookahead).
    
    Validates the filtered_klines[:i] fix - indicators should not include candle i's close.
    """
    t0 = 1700000000000

    # Make candle 55 close crazy to detect leakage
    klines = []
    price = 100
    for n in range(60):
        close = price if n != 55 else 999999  # huge spike at candle 55 close
        klines.append(kline(t0+n*60000, price, price+1, price-1, close))
        price += 1

    async def fake_fetch(*args, **kwargs):
        return klines
    monkeypatch.setattr(bt, "_fetch_historical_klines", fake_fetch)

    # Strategy doesn't need to trade; keep HOLD always
    async def fake_eval(self):
        return StrategySignal(action="HOLD", symbol="BTCUSDT", confidence=0.0, price=None)
    monkeypatch.setattr(bt.RangeMeanReversionStrategy, "evaluate", fake_eval)

    req = bt.BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="range_mean_reversion",
        start_time=dt(t0),
        end_time=dt(t0+59*60000),
        leverage=1,
        risk_per_trade=0.01,
        fixed_amount=100,
        initial_balance=1000,
        params={
            "kline_interval": "1m",
            "lookback_period": 10,
            "ema_fast_period": 5,
            "ema_slow_period": 10,
            "rsi_period": 14,
        }
    )

    res = await bt.run_backtest(req, DummyClient())

    # Find snapshot at time of the "spike" candle (55)
    # Because we now use closed candles up to i-1, the snapshot at candle 55 must NOT reflect close=999999 yet.
    # It will reflect it only starting from candle 56 snapshot.
    snaps = res.indicators
    assert snaps is not None, "Indicators should be present"
    
    ema_fast_points = snaps.get("ema_fast", [])
    # time is seconds; candle 55 time:
    t55 = (t0 + 55*60000) // 1000

    # Get ema_fast value at t55 (if exists) and ensure it is not absurdly huge
    # (exact ema depends, so we assert "not blown up")
    v55 = next((p["value"] for p in ema_fast_points if p["time"] == t55), None)
    if v55 is not None:
        assert v55 < 100000, \
            f"EMA at candle 55 should not incorporate 999999 close yet (lookahead bug), got {v55}"


@pytest.mark.ci
@pytest.mark.asyncio
async def test_no_reentry_same_candle_after_exit(monkeypatch):
    """Test 6: "Close then re-enter same candle" is blocked.
    
    Validates position_just_closed_this_iteration prevents immediate re-entry.
    """
    t0 = 1700000000000
    klines = [
        kline(t0,        100, 101,  99, 100),  # 0 - signal generated
        kline(t0+60000,  200, 201, 199, 200),  # 1 - entry
        kline(t0+120000, 200, 220, 180, 210),  # 2 - triggers TP/SL and also returns BUY signal
        kline(t0+180000, 210, 211, 209, 210),  # 3 - later candle
    ]

    async def fake_fetch(*args, **kwargs):
        return klines
    monkeypatch.setattr(bt, "_fetch_historical_klines", fake_fetch)

    calls = {"n": 0}
    async def fake_eval(self):
        calls["n"] += 1
        # 1) First eval enters
        if calls["n"] == 1:
            return StrategySignal(action="BUY", symbol="BTCUSDT", confidence=1.0, price=100.0)
        # 2) On candle where TP/SL triggers, also emits BUY again
        if calls["n"] == 2:
            return StrategySignal(action="BUY", symbol="BTCUSDT", confidence=1.0, price=200.0)
        return StrategySignal(action="HOLD", symbol="BTCUSDT", confidence=0.0, price=None)
    monkeypatch.setattr(bt.EmaScalpingStrategy, "evaluate", fake_eval)

    req = bt.BacktestRequest(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=dt(t0),
        end_time=dt(t0+180000),
        leverage=1,
        risk_per_trade=0.01,
        fixed_amount=100,
        initial_balance=1000,
        params={
            "ema_slow": 1, "ema_fast": 1, "kline_interval": "1m",
            "trailing_stop_enabled": False,
            "take_profit_pct": 0.02,  # TP will trigger on candle 2
            "stop_loss_pct": 0.02,
        }
    )

    res = await bt.run_backtest(req, DummyClient())
    
    # Should not open 2nd trade on same candle as exit
    # Either only 1 trade, or 2nd trade entry_time > 1st trade exit_time
    assert res.total_trades >= 1, "Should have at least one trade"
    
    if res.total_trades == 1:
        # Only one trade - exit happened, but re-entry was blocked
        trade = res.trades[0]
        assert trade.get("exit_time") is not None, "First trade should have exited"
    else:
        # Two trades - second trade must start after first trade exits
        assert res.total_trades == 2, f"Expected 1 or 2 trades, got {res.total_trades}"
        trade1 = res.trades[0]
        trade2 = res.trades[1]
        
        assert trade1.get("exit_time") is not None, "First trade should have exited"
        assert trade2.get("entry_time") > trade1["exit_time"], \
            f"Second trade entry ({trade2['entry_time']}) must be after first trade exit ({trade1['exit_time']})"

