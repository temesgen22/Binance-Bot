import pytest
from unittest.mock import MagicMock

from app.core.my_binance_client import BinanceClient
from app.models.strategy import StrategyParams
from app.strategies.base import Strategy, StrategyContext
from app.strategies.reverse_scalping import ReverseScalpingStrategy
from app.strategies.scalping import EmaScalpingStrategy


def _build_klines(count: int, start_price: float = 100.0, volume: float = 1000.0) -> list[list[float]]:
    klines: list[list[float]] = []
    for i in range(count):
        close = start_price + i * 0.1
        open_time = i * 60000
        close_time = open_time + 60000
        klines.append([
            open_time,
            close - 0.05,
            close + 0.2,
            close - 0.2,
            close,
            volume,
            close_time,
            0, 0, 0, 0, 0,
        ])
    return klines


def _context(params: dict) -> StrategyContext:
    base = {
        "ema_fast": 8,
        "ema_slow": 21,
        "take_profit_pct": 0.004,
        "stop_loss_pct": 0.002,
        "kline_interval": "1m",
        "interval_seconds": 10,
    }
    base.update(params)
    return StrategyContext(
        id="test-filter",
        name="test-filter",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params=base,
        interval_seconds=10,
    )


@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceClient)
    client.get_price = MagicMock(return_value=100.0)
    client.get_klines = MagicMock(return_value=_build_klines(80))
    return client


def test_strategy_params_reject_invalid_atr_bounds():
    with pytest.raises(ValueError):
        StrategyParams(atr_min_pct=10.0, atr_max_pct=5.0)


def test_param_float_treats_json_null_as_default():
    assert Strategy.param_float({"atr_min_pct": None}, "atr_min_pct", 0.0) == 0.0
    assert Strategy.param_int({"volume_ma_period": None}, "volume_ma_period", 20) == 20


def test_scalping_required_candles_respects_enabled_filters(mock_client):
    s = EmaScalpingStrategy(
        _context(
            {
                "use_rsi_filter": True,
                "rsi_period": 14,
                "use_atr_filter": True,
                "atr_period": 21,
                "use_volume_filter": True,
                "volume_ma_period": 30,
            }
        ),
        mock_client,
    )
    assert s._required_filter_candles() == 31


def test_scalping_rsi_long_gate_blocks_entry(mock_client):
    s = EmaScalpingStrategy(
        _context(
            {
                "use_rsi_filter": True,
                "rsi_period": 14,
                    "rsi_long_min": 100.1,
            }
        ),
        mock_client,
    )
    closed = _build_klines(60, start_price=100.0, volume=1000.0)
    closes = [float(k[4]) for k in closed]
    assert s._passes_entry_filters("LONG", closed, closes, int(closed[-1][6])) is False


def test_scalping_volume_filter_passes_on_boundary(mock_client):
    s = EmaScalpingStrategy(
        _context(
            {
                "use_volume_filter": True,
                "volume_ma_period": 20,
                "volume_multiplier_min": 1.0,
            }
        ),
        mock_client,
    )
    closed = _build_klines(50, start_price=100.0, volume=1000.0)
    closes = [float(k[4]) for k in closed]
    assert s._passes_entry_filters("SHORT", closed, closes, int(closed[-1][6])) is True


def test_scalping_volume_ratio_uses_prior_window_not_including_current_bar(mock_client):
    """SMA must exclude the signal candle so ratio matches 'volume vs prior N-bar average'."""
    s = EmaScalpingStrategy(
        _context(
            {
                "use_volume_filter": True,
                "volume_ma_period": 20,
                # Old (wrong): inclusive SMA mean=1050, ratio=2000/1050≈1.90 → blocked
                # Correct: prior mean=1000, ratio=2.0 → pass
                "volume_multiplier_min": 1.95,
            }
        ),
        mock_client,
    )
    closed = _build_klines(50, start_price=100.0, volume=1000.0)
    # Spike only on entry bar
    closed[-1][5] = 2000.0
    closes = [float(k[4]) for k in closed]
    assert s._passes_entry_filters("LONG", closed, closes, int(closed[-1][6])) is True


def test_scalping_atr_filter_fail_closed_on_invalid_close(mock_client):
    s = EmaScalpingStrategy(
        _context(
            {
                "use_atr_filter": True,
                "atr_period": 14,
            }
        ),
        mock_client,
    )
    closed = _build_klines(40)
    closes = [0.0 for _ in closed]
    assert s._passes_entry_filters("LONG", closed, closes, int(closed[-1][6])) is False


def test_reverse_uses_same_directional_rsi_rules(mock_client):
    r = ReverseScalpingStrategy(
        _context(
            {
                "use_rsi_filter": True,
                "rsi_period": 14,
                "rsi_short_max": 10.0,
            }
        ),
        mock_client,
    )
    closed = _build_klines(60, start_price=100.0, volume=1000.0)
    closes = [float(k[4]) for k in closed]
    assert r._passes_entry_filters("SHORT", closed, closes, int(closed[-1][6])) is False
