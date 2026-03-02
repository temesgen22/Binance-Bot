"""
Test cases for the User Data Stream / open position update implementation.

Covers:
1. FuturesUserDataStreamManager: _normalize_position_entry, _on_ws_message (ACCOUNT_UPDATE)
2. StrategyPersistence: apply_position_data (open/closed), _clear_position_state_and_persist
3. StrategyRunner: _on_user_data_position_update (account/symbol/side matching, hedge break)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.services.strategy_persistence import StrategyPersistence
from app.core.futures_user_data_stream_manager import (
    _normalize_position_entry,
    FuturesUserDataStreamManager,
)


# --- _normalize_position_entry (module-level in futures_user_data_stream_manager) ---


class TestNormalizePositionEntry:
    """Tests for _normalize_position_entry (Binance a.P entry -> position_data)."""

    def test_long_position_one_way(self):
        entry = {"s": "BTCUSDT", "pa": "0.01", "ep": "50000", "up": "10.5", "ps": "BOTH"}
        out = _normalize_position_entry(entry)
        assert out["position_amt"] == 0.01
        assert out["entry_price"] == 50000.0
        assert out["unrealized_pnl"] == 10.5
        assert out["position_side"] == "LONG"
        assert out["mark_price"] is None

    def test_short_position_one_way(self):
        entry = {"s": "ETHUSDT", "pa": "-0.1", "ep": "3000", "up": "-5.0", "ps": "BOTH"}
        out = _normalize_position_entry(entry)
        assert out["position_amt"] == -0.1
        assert out["position_side"] == "SHORT"
        assert out["unrealized_pnl"] == -5.0

    def test_hedge_mode_long(self):
        entry = {"s": "BTCUSDT", "pa": "0.02", "ep": "51000", "up": "20", "ps": "LONG"}
        out = _normalize_position_entry(entry)
        assert out["position_side"] == "LONG"
        assert out["position_amt"] == 0.02

    def test_hedge_mode_short(self):
        entry = {"s": "BTCUSDT", "pa": "-0.02", "ep": "51000", "up": "-10", "ps": "SHORT"}
        out = _normalize_position_entry(entry)
        assert out["position_side"] == "SHORT"

    def test_closed_position_zero_amount(self):
        entry = {"s": "BTCUSDT", "pa": "0", "ep": "0", "up": "0", "ps": "BOTH"}
        out = _normalize_position_entry(entry)
        assert out["position_amt"] == 0.0
        assert out["position_side"] == "BOTH"

    def test_missing_fields_defaults(self):
        entry = {"s": "XRPUSDT"}
        out = _normalize_position_entry(entry)
        assert out["position_amt"] == 0.0
        assert out["entry_price"] == 0.0
        assert out["unrealized_pnl"] == 0.0
        assert out["position_side"] == "BOTH"

    def test_invalid_numeric_coerced_to_zero(self):
        entry = {"s": "BTCUSDT", "pa": "x", "ep": "y", "up": "z", "ps": "BOTH"}
        out = _normalize_position_entry(entry)
        assert out["position_amt"] == 0.0
        assert out["entry_price"] == 0.0
        assert out["unrealized_pnl"] == 0.0


# --- FuturesUserDataStreamManager._on_ws_message ---


class TestFuturesUserDataStreamManagerOnWsMessage:
    """Tests for manager parsing ACCOUNT_UPDATE and invoking callback."""

    @pytest.mark.asyncio
    async def test_account_update_invokes_callback_per_position(self):
        calls = []

        async def on_update(account_id: str, symbol: str, position_data: dict):
            calls.append((account_id, symbol, position_data))

        manager = FuturesUserDataStreamManager(account_manager=MagicMock(), on_position_update=on_update)
        payload = {
            "e": "ACCOUNT_UPDATE",
            "a": {
                "P": [
                    {"s": "BTCUSDT", "pa": "0.01", "ep": "50000", "up": "10", "ps": "LONG"},
                    {"s": "ETHUSDT", "pa": "-0.1", "ep": "3000", "up": "-2", "ps": "SHORT"},
                ]
            },
        }
        await manager._on_ws_message("acc1", "ACCOUNT_UPDATE", payload)
        assert len(calls) == 2
        assert calls[0][0] == "acc1" and calls[0][1] == "BTCUSDT"
        assert calls[0][2]["position_amt"] == 0.01 and calls[0][2]["position_side"] == "LONG"
        assert calls[1][0] == "acc1" and calls[1][1] == "ETHUSDT"
        assert calls[1][2]["position_side"] == "SHORT"

    @pytest.mark.asyncio
    async def test_non_account_update_ignored(self):
        calls = []

        async def on_update(account_id: str, symbol: str, position_data: dict):
            calls.append((account_id, symbol, position_data))

        manager = FuturesUserDataStreamManager(account_manager=MagicMock(), on_position_update=on_update)
        await manager._on_ws_message("acc1", "ORDER_TRADE_UPDATE", {"e": "ORDER_TRADE_UPDATE"})
        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_empty_positions_list_no_calls(self):
        calls = []

        async def on_update(account_id: str, symbol: str, position_data: dict):
            calls.append((account_id, symbol, position_data))

        manager = FuturesUserDataStreamManager(account_manager=MagicMock(), on_position_update=on_update)
        await manager._on_ws_message("acc1", "ACCOUNT_UPDATE", {"e": "ACCOUNT_UPDATE", "a": {"P": []}})
        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_skips_entry_with_empty_symbol(self):
        calls = []

        async def on_update(account_id: str, symbol: str, position_data: dict):
            calls.append((account_id, symbol, position_data))

        manager = FuturesUserDataStreamManager(account_manager=MagicMock(), on_position_update=on_update)
        payload = {
            "e": "ACCOUNT_UPDATE",
            "a": {
                "P": [
                    {"s": "", "pa": "0.01", "ep": "50000", "up": "0", "ps": "BOTH"},
                    {"s": "BTCUSDT", "pa": "0.01", "ep": "50000", "up": "0", "ps": "BOTH"},
                ]
            },
        }
        await manager._on_ws_message("acc1", "ACCOUNT_UPDATE", payload)
        assert len(calls) == 1
        assert calls[0][1] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_callback_exception_logged_other_entries_still_processed(self):
        call_symbols = []

        async def on_update(account_id: str, symbol: str, position_data: dict):
            call_symbols.append(symbol)
            if symbol == "BTCUSDT":
                raise ValueError("test error")

        manager = FuturesUserDataStreamManager(account_manager=MagicMock(), on_position_update=on_update)
        payload = {
            "e": "ACCOUNT_UPDATE",
            "a": {
                "P": [
                    {"s": "BTCUSDT", "pa": "0.01", "ep": "50000", "up": "0", "ps": "BOTH"},
                    {"s": "ETHUSDT", "pa": "0.1", "ep": "3000", "up": "0", "ps": "BOTH"},
                ]
            },
        }
        await manager._on_ws_message("acc1", "ACCOUNT_UPDATE", payload)
        assert call_symbols == ["BTCUSDT", "ETHUSDT"]


# --- StrategyPersistence.apply_position_data & _clear_position_state_and_persist ---


def _make_summary(
    strategy_id: str = "strat-1",
    symbol: str = "BTCUSDT",
    account_id: str = "default",
    position_size: float = None,
    position_side: str = None,
    entry_price: float = None,
    unrealized_pnl: float = None,
    current_price: float = None,
    meta: dict = None,
) -> StrategySummary:
    return StrategySummary(
        id=strategy_id,
        name="Test",
        symbol=symbol,
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        fixed_amount=100.0,
        max_positions=1,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
        last_signal=None,
        position_size=position_size,
        position_side=position_side,
        entry_price=entry_price,
        unrealized_pnl=unrealized_pnl,
        current_price=current_price,
        account_id=account_id,
        meta=meta or {},
    )


class TestStrategyPersistenceApplyPositionData:
    """Tests for apply_position_data (WebSocket/REST position apply)."""

    @pytest.mark.asyncio
    async def test_apply_open_position_updates_summary_and_db(self):
        summary = _make_summary(position_size=0.0, entry_price=None)
        update_db = MagicMock()
        persistence = StrategyPersistence(
            strategies={summary.id: summary},
            strategy_service=MagicMock(),
            user_id=None,
        )
        persistence.update_strategy_in_db = update_db

        await persistence.apply_position_data(summary, {
            "position_amt": 0.01,
            "entry_price": 50000.0,
            "unrealized_pnl": 10.0,
            "position_side": "LONG",
            "mark_price": None,
        })

        assert summary.position_size == 0.01
        assert summary.entry_price == 50000.0
        assert summary.unrealized_pnl == 10.0
        assert summary.position_side == "LONG"
        update_db.assert_called_once()
        call_kw = update_db.call_args[1]
        assert call_kw["position_size"] == 0.01
        assert call_kw["entry_price"] == 50000.0
        assert "current_price" not in call_kw  # None not passed

    @pytest.mark.asyncio
    async def test_apply_open_position_with_mark_price_passes_current_price(self):
        summary = _make_summary(current_price=49000.0)
        update_db = MagicMock()
        persistence = StrategyPersistence(
            strategies={summary.id: summary},
            strategy_service=MagicMock(),
            user_id=None,
        )
        persistence.update_strategy_in_db = update_db

        await persistence.apply_position_data(summary, {
            "position_amt": 0.01,
            "entry_price": 50000.0,
            "unrealized_pnl": 10.0,
            "position_side": "LONG",
            "mark_price": 50500.0,
        })

        assert summary.current_price == 50500.0
        call_kw = update_db.call_args[1]
        assert call_kw["current_price"] == 50500.0

    @pytest.mark.asyncio
    async def test_apply_closed_position_clears_summary_and_persists(self):
        summary = _make_summary(
            position_size=0.01,
            position_side="LONG",
            entry_price=50000.0,
            unrealized_pnl=10.0,
            meta={},
        )
        update_db = MagicMock()
        persistence = StrategyPersistence(
            strategies={summary.id: summary},
            strategy_service=MagicMock(),
            user_id=None,
        )
        persistence.update_strategy_in_db = update_db

        await persistence.apply_position_data(summary, {
            "position_amt": 0,
            "entry_price": 0,
            "unrealized_pnl": 0,
            "position_side": "BOTH",
            "mark_price": None,
        })

        assert summary.position_size == 0
        assert summary.entry_price is None
        assert summary.unrealized_pnl == 0
        assert summary.position_side is None
        assert update_db.call_count >= 1

    @pytest.mark.asyncio
    async def test_apply_short_negative_position_amt(self):
        summary = _make_summary()
        persistence = StrategyPersistence(
            strategies={summary.id: summary},
            strategy_service=MagicMock(),
            user_id=None,
        )
        persistence.update_strategy_in_db = MagicMock()

        await persistence.apply_position_data(summary, {
            "position_amt": -0.02,
            "entry_price": 3000.0,
            "unrealized_pnl": -5.0,
            "position_side": "SHORT",
            "mark_price": None,
        })

        assert summary.position_size == 0.02
        assert summary.position_side == "SHORT"


class TestStrategyPersistenceClearPositionStateAndPersist:
    """Tests for _clear_position_state_and_persist."""

    @pytest.mark.asyncio
    async def test_clears_summary_and_updates_db(self):
        summary = _make_summary(
            position_size=0.01,
            position_side="LONG",
            entry_price=50000.0,
            unrealized_pnl=10.0,
        )
        update_db = MagicMock()
        persistence = StrategyPersistence(
            strategies={summary.id: summary},
            strategy_service=MagicMock(),
            user_id=None,
        )
        persistence.update_strategy_in_db = update_db

        await persistence._clear_position_state_and_persist(summary)

        assert summary.position_size == 0
        assert summary.entry_price is None
        assert summary.unrealized_pnl == 0
        assert summary.position_side is None
        assert update_db.call_count >= 1
        first_call = update_db.call_args_list[0]
        assert first_call[1]["position_size"] == 0
        assert first_call[1]["entry_price"] is None

    @pytest.mark.asyncio
    async def test_meta_none_becomes_dict(self):
        summary = _make_summary(meta=None)
        summary.meta = None
        persistence = StrategyPersistence(
            strategies={summary.id: summary},
            strategy_service=MagicMock(),
            user_id=None,
        )
        persistence.update_strategy_in_db = MagicMock()

        await persistence._clear_position_state_and_persist(summary)

        assert isinstance(summary.meta, dict)

    @pytest.mark.asyncio
    async def test_cancels_tp_sl_orders_when_present(self):
        summary = _make_summary(meta={"tp_sl_orders": {"tp_order_id": "123", "sl_order_id": "456"}})
        order_manager = MagicMock()
        order_manager.cancel_tp_sl_orders = AsyncMock()
        persistence = StrategyPersistence(
            strategies={summary.id: summary},
            strategy_service=MagicMock(),
            user_id=None,
            order_manager=order_manager,
        )
        persistence.update_strategy_in_db = MagicMock()

        await persistence._clear_position_state_and_persist(summary)

        order_manager.cancel_tp_sl_orders.assert_awaited_once_with(summary)
        assert summary.meta.get("tp_sl_orders") == {}


# --- StrategyRunner._on_user_data_position_update ---


def _make_runner():
    """Minimal StrategyRunner for testing _on_user_data_position_update."""
    from app.services.strategy_runner import StrategyRunner
    from app.core.binance_client_manager import BinanceClientManager
    from app.core.config import get_settings, BinanceAccountConfig

    client = MagicMock()
    settings = get_settings()
    manager = BinanceClientManager(settings)
    default_account = BinanceAccountConfig(
        account_id="default",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )
    manager._clients = {"default": client}
    manager._accounts = {"default": default_account}

    class DummyRedis:
        enabled = False

    return StrategyRunner(
        client=client,
        client_manager=manager,
        risk=MagicMock(),
        executor=MagicMock(),
        max_concurrent=2,
        redis_storage=DummyRedis(),
        use_websocket=False,
    )


class TestStrategyRunnerOnUserDataPositionUpdate:
    """Tests for runner callback: account/symbol/position_side matching and single update in hedge."""

    @pytest.mark.asyncio
    async def test_matching_account_and_symbol_gets_update(self):
        summary = _make_summary(strategy_id="s1", symbol="BTCUSDT", account_id="default")
        runner = _make_runner()
        runner._strategies = {summary.id: summary}
        runner.state_manager.apply_position_data = AsyncMock()

        await runner._on_user_data_position_update(
            "default",
            "BTCUSDT",
            {"position_amt": 0.01, "entry_price": 50000.0, "unrealized_pnl": 10.0, "position_side": "LONG", "mark_price": None},
        )

        runner.state_manager.apply_position_data.assert_awaited_once()
        assert runner.state_manager.apply_position_data.call_args[0][0] == summary

    @pytest.mark.asyncio
    async def test_wrong_account_no_update(self):
        summary = _make_summary(strategy_id="s1", symbol="BTCUSDT", account_id="other")
        runner = _make_runner()
        runner._strategies = {summary.id: summary}
        runner.state_manager.apply_position_data = AsyncMock()

        await runner._on_user_data_position_update(
            "default",
            "BTCUSDT",
            {"position_amt": 0.01, "entry_price": 50000.0, "unrealized_pnl": 10.0, "position_side": "LONG", "mark_price": None},
        )

        runner.state_manager.apply_position_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_symbol_no_update(self):
        summary = _make_summary(strategy_id="s1", symbol="ETHUSDT", account_id="default")
        runner = _make_runner()
        runner._strategies = {summary.id: summary}
        runner.state_manager.apply_position_data = AsyncMock()

        await runner._on_user_data_position_update(
            "default",
            "BTCUSDT",
            {"position_amt": 0.01, "entry_price": 50000.0, "unrealized_pnl": 10.0, "position_side": "LONG", "mark_price": None},
        )

        runner.state_manager.apply_position_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_hedge_mode_only_matching_side_updated_and_break(self):
        long_summary = _make_summary(strategy_id="s-long", symbol="BTCUSDT", account_id="default", position_side="LONG")
        short_summary = _make_summary(strategy_id="s-short", symbol="BTCUSDT", account_id="default", position_side="SHORT")
        runner = _make_runner()
        runner._strategies = {long_summary.id: long_summary, short_summary.id: short_summary}
        runner.state_manager.apply_position_data = AsyncMock()

        await runner._on_user_data_position_update(
            "default",
            "BTCUSDT",
            {"position_amt": 0.01, "entry_price": 50000.0, "unrealized_pnl": 10.0, "position_side": "LONG", "mark_price": None},
        )

        # Only LONG strategy should be updated; we break after first so SHORT is not updated
        assert runner.state_manager.apply_position_data.await_count == 1
        applied_summary = runner.state_manager.apply_position_data.call_args[0][0]
        assert applied_summary.id == "s-long"

    @pytest.mark.asyncio
    async def test_one_way_mode_both_none_position_side_updates_first_match(self):
        s1 = _make_summary(strategy_id="s1", symbol="BTCUSDT", account_id="default", position_side=None)
        s2 = _make_summary(strategy_id="s2", symbol="BTCUSDT", account_id="default", position_side=None)
        runner = _make_runner()
        runner._strategies = {s1.id: s1, s2.id: s2}
        runner.state_manager.apply_position_data = AsyncMock()

        await runner._on_user_data_position_update(
            "default",
            "BTCUSDT",
            {"position_amt": 0.01, "entry_price": 50000.0, "unrealized_pnl": 10.0, "position_side": "LONG", "mark_price": None},
        )

        # LONG side triggers break after first; only one update
        assert runner.state_manager.apply_position_data.await_count == 1
