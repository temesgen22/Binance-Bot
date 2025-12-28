"""
Strict parameter contract tests.

Ensures every configurable option is honored end-to-end when the strategy
evaluates market data or when orders are prepared.
"""

import pytest
pytestmark = pytest.mark.ci  # Parameter contracts are critical for CI
from unittest.mock import MagicMock, patch

from app.core.my_binance_client import BinanceClient
from app.risk.manager import RiskManager
from app.strategies.base import StrategyContext
from app.strategies.scalping import EmaScalpingStrategy


def build_dummy_klines(count: int, start_price: float = 100.0, interval_ms: int = 60_000):
    """Create deterministic klines for testing."""
    klines: list[list[float]] = []
    for idx in range(count):
        price = start_price + idx * 0.1
        open_time = idx * interval_ms
        close_time = open_time + interval_ms
        klines.append(
            [
                open_time,
                price,
                price + 0.5,
                price - 0.5,
                price,
                100.0,
                close_time,
                0,
                0,
                0,
                0,
                0,
            ]
        )
    return klines


@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceClient)
    client.get_price.return_value = 100.0
    client.get_klines.return_value = build_dummy_klines(40, start_price=100.0)
    return client


class TestRiskParameters:
    """Risk manager should respect both fixed_amount and risk_per_trade."""

    @pytest.fixture
    def risk_client(self):
        client = MagicMock(spec=BinanceClient)
        client.get_min_notional.return_value = 5.0
        client.round_quantity.side_effect = lambda symbol, qty: round(qty, 6)
        client.futures_account_balance.return_value = 1_000.0
        return client

    def test_fixed_amount_overrides_risk(self, risk_client):
        manager = RiskManager(risk_client)

        result = manager.size_position(
            symbol="BTCUSDT", risk_per_trade=0.05, price=100.0, fixed_amount=50.0
        )

        # Quantity * price should match fixed amount (within rounding tolerance)
        assert result.notional == pytest.approx(50.0, rel=1e-3)
        risk_client.futures_account_balance.assert_not_called()

    def test_risk_per_trade_uses_account_balance(self, risk_client):
        manager = RiskManager(risk_client)

        result = manager.size_position(
            symbol="BTCUSDT", risk_per_trade=0.02, price=100.0, fixed_amount=None
        )

        expected_notional = 1_000.0 * 0.02  # 2% of balance
        assert result.notional == pytest.approx(expected_notional, rel=1e-3)
        risk_client.futures_account_balance.assert_called_once()


class TestStrategyParameterBehavior:
    """Strategy-level verification for every runtime configuration toggle."""

    def make_strategy(self, mock_client, **param_overrides) -> EmaScalpingStrategy:
        params = {
            "ema_fast": 8,
            "ema_slow": 21,
            "take_profit_pct": 0.004,
            "stop_loss_pct": 0.002,
            "interval_seconds": 10,
            "kline_interval": "1m",
            "enable_short": True,
            "min_ema_separation": 0.0,
            "enable_htf_bias": False,
            "cooldown_candles": 0,
            "trailing_stop_enabled": False,
            "trailing_stop_activation_pct": 0.0,
        }
        params.update(param_overrides)
        context = StrategyContext(
            id="param-test",
            name="Param Test",
            symbol="BTCUSDT",
            leverage=5,
            risk_per_trade=0.01,
            params=params,
            interval_seconds=params["interval_seconds"],
        )
        return EmaScalpingStrategy(context, mock_client)

    @pytest.mark.asyncio
    async def test_enable_short_false_blocks_death_cross(self, mock_client):
        mock_client.get_klines.return_value = build_dummy_klines(40, start_price=100.0)
        strategy = self.make_strategy(mock_client, enable_short=False)
        strategy.prev_fast = 1.2
        strategy.prev_slow = 1.0
        strategy.last_closed_candle_time = None

        with patch.object(EmaScalpingStrategy, "_ema", side_effect=[0.9, 1.0]):
            signal = await strategy.evaluate()

        assert signal.action == "HOLD"  # death cross ignored because shorts disabled

    @pytest.mark.asyncio
    async def test_min_ema_separation_blocks_entry(self, mock_client):
        strategy = self.make_strategy(
            mock_client, min_ema_separation=0.05, trailing_stop_enabled=False
        )
        strategy.prev_fast = 1.0
        strategy.prev_slow = 1.0
        mock_client.get_klines.return_value = build_dummy_klines(40, start_price=100.0)

        with patch.object(EmaScalpingStrategy, "_ema", side_effect=[1.01, 1.0]):
            signal = await strategy.evaluate()

        assert signal.action == "HOLD"  # separation too small vs 5%

    @pytest.mark.asyncio
    async def test_cooldown_enforced(self, mock_client):
        strategy = self.make_strategy(mock_client, cooldown_candles=2)
        strategy.cooldown_left = 2
        mock_client.get_klines.return_value = build_dummy_klines(40, start_price=100.0)

        signal = await strategy.evaluate()

        assert signal.action == "HOLD"
        assert strategy.cooldown_left == 1  # decremented

    @pytest.mark.asyncio
    async def test_enable_htf_bias_blocks_short_when_trend_up(self, mock_client):
        strategy = self.make_strategy(mock_client, enable_short=True, enable_htf_bias=True)
        strategy.prev_fast = 1.2
        strategy.prev_slow = 1.0

        main_klines = build_dummy_klines(40, start_price=100.0)
        htf_klines = build_dummy_klines(strategy.slow_period + 5, start_price=200.0)
        mock_client.get_klines.side_effect = [main_klines, htf_klines]

        with patch.object(EmaScalpingStrategy, "_ema", side_effect=[0.9, 1.0]):
            signal = await strategy.evaluate()

        assert signal.action == "HOLD"  # blocked because 5m trend up
        # ensure HTF call used 5m interval
        mock_client.get_klines.assert_any_call(
            symbol="BTCUSDT", interval="5m", limit=strategy.slow_period + 5
        )

    @pytest.mark.asyncio
    async def test_configured_kline_interval_used(self, mock_client):
        strategy = self.make_strategy(mock_client, kline_interval="5m")
        mock_client.get_klines.return_value = build_dummy_klines(40, start_price=100.0)

        with patch.object(EmaScalpingStrategy, "_ema", side_effect=[1.2, 1.0, 1.3, 1.1]):
            await strategy.evaluate()

        args, kwargs = mock_client.get_klines.call_args
        assert kwargs["interval"] == "5m"

    @pytest.mark.asyncio
    async def test_trailing_stop_runtime_updates(self, mock_client):
        strategy = self.make_strategy(
            mock_client,
            trailing_stop_enabled=True,
            trailing_stop_activation_pct=0.0,
            min_ema_separation=0.0,
        )
        strategy.prev_fast = 1.0
        strategy.prev_slow = 1.1
        mock_client.get_klines.return_value = build_dummy_klines(40, start_price=100.0)

        with patch.object(EmaScalpingStrategy, "_ema", side_effect=[1.2, 1.0, 1.3, 1.1]):
            with patch("app.strategies.scalping.TrailingStopManager") as mock_manager:
                trailing_instance = MagicMock()
                trailing_instance.current_tp = 0.0
                trailing_instance.current_sl = 0.0
                trailing_instance.activation_price = 0.0
                trailing_instance.update.return_value = (101.0, 99.0)
                trailing_instance.check_exit.return_value = None
                mock_manager.return_value = trailing_instance

                # First evaluate enters long and creates trailing stop
                signal = await strategy.evaluate()
                assert signal.action == "BUY"

                # Simulate already-long state and ensure trailing stop updates on next eval
                strategy.position = "LONG"
                strategy.entry_price = 100.0
                strategy.trailing_stop = trailing_instance
                strategy.last_closed_candle_time = None
                mock_client.get_klines.return_value = build_dummy_klines(40, start_price=110.0)

                signal2 = await strategy.evaluate()
                assert signal2.action in ("HOLD", "SELL")  # no forced direction
                trailing_instance.update.assert_called()


