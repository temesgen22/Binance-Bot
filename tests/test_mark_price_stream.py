"""
Comprehensive tests for mark price stream: subscribe when position opens (strategy/manual/external;
live or paper) and unsubscribe when no open positions remain after closing.

Validates:
- Subscribe: registry populated, connection created (or reused) for strategy, manual, external.
- Unsubscribe: when last position for a symbol is closed (manual/strategy/external), we call
  maybe_unsubscribe and disconnect mark price for that symbol.
- Multiple positions same symbol: unsubscribe only when registry is empty for that symbol.
- PnL computation and broadcast on tick for all registered entries.
"""

import asyncio
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.mark_price_stream_manager import (
    MarkPriceStreamManager,
    _compute_unrealized_pnl,
)


# --- PnL computation (already in test_realtime_position_websocket; keep for completeness) ---


class TestMarkPricePnlComputation:
    """_compute_unrealized_pnl correctness for LONG/SHORT."""

    def test_long_profit(self):
        assert _compute_unrealized_pnl(51000.0, 50000.0, 0.01, "LONG") == 10.0

    def test_long_loss(self):
        assert _compute_unrealized_pnl(49000.0, 50000.0, 0.01, "LONG") == -10.0

    def test_short_profit(self):
        assert _compute_unrealized_pnl(49000.0, 50000.0, 0.01, "SHORT") == 10.0

    def test_short_loss(self):
        assert _compute_unrealized_pnl(51000.0, 50000.0, 0.01, "SHORT") == -10.0

    def test_zero_size_returns_zero(self):
        assert _compute_unrealized_pnl(51000.0, 50000.0, 0.0, "LONG") == 0.0


# --- Registry: register / unregister (strategy, manual, external; live/paper) ---


class TestMarkPriceRegistryAllPositionTypes:
    """Registry correctly stores and removes positions for strategy, manual, external (live or paper)."""

    def test_register_strategy_position_live_or_paper(self):
        """Strategy-opened position (strategy_id = UUID) is registered."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        strategy_id = str(uuid4())
        manager.register_position(
            "BTCUSDT", strategy_id, user_id, 50000.0, 0.01, "LONG",
            account_id="default", strategy_name="EMA Scalping"
        )
        assert "BTCUSDT" in manager._registry
        assert len(manager._registry["BTCUSDT"]) == 1
        assert manager._registry["BTCUSDT"][0]["strategy_id"] == strategy_id
        assert manager._registry["BTCUSDT"][0]["strategy_name"] == "EMA Scalping"

    def test_register_manual_position_live_or_paper(self):
        """Manual-opened position (strategy_id = manual_<id>) is registered."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position(
            "ETHUSDT", "manual_mp-123", user_id, 3000.0, 0.5, "LONG",
            account_id="paper1", strategy_name="Manual Trade"
        )
        assert "ETHUSDT" in manager._registry
        assert len(manager._registry["ETHUSDT"]) == 1
        assert manager._registry["ETHUSDT"][0]["strategy_id"] == "manual_mp-123"
        assert manager._registry["ETHUSDT"][0]["strategy_name"] == "Manual Trade"

    def test_register_external_position(self):
        """External position (strategy_id = external_LONG or external_SHORT) is registered."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position(
            "BTCUSDT", "external_LONG", user_id, 50000.0, 0.02, "LONG",
            account_id="default", strategy_name="External"
        )
        assert "BTCUSDT" in manager._registry
        assert manager._registry["BTCUSDT"][0]["strategy_id"] == "external_LONG"

    def test_unregister_strategy_position_removes_entry(self):
        """Unregister strategy position removes it; empty registry removes symbol key."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        strategy_id = str(uuid4())
        manager.register_position("BTCUSDT", strategy_id, user_id, 50000.0, 0.01, "LONG", "default")
        manager.unregister_position("BTCUSDT", strategy_id)
        assert "BTCUSDT" not in manager._registry

    def test_unregister_manual_position_removes_entry(self):
        """Unregister manual position removes it."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("ETHUSDT", "manual_mp-456", user_id, 3000.0, 0.5, "LONG", "paper1")
        manager.unregister_position("ETHUSDT", "manual_mp-456")
        assert "ETHUSDT" not in manager._registry

    def test_unregister_external_position_removes_entry(self):
        """Unregister external position removes it."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("BTCUSDT", "external_SHORT", user_id, 50000.0, 0.01, "SHORT", "default")
        manager.unregister_position("BTCUSDT", "external_SHORT")
        assert "BTCUSDT" not in manager._registry


# --- Subscribe: when position opens we subscribe (mock connection to avoid real WS) ---


@pytest.fixture
def mock_mark_price_connection():
    """Mock MarkPriceConnection so connect/disconnect do not open real WebSockets."""
    with patch("app.core.mark_price_stream_manager.MarkPriceConnection") as mock_conn_cls:
        mock_conn = MagicMock()
        mock_conn.connect = AsyncMock()
        mock_conn.disconnect = AsyncMock()
        mock_conn_cls.return_value = mock_conn
        yield mock_conn


@pytest.fixture
def no_sleep():
    """Skip the 2s stagger in subscribe so tests run fast."""
    with patch("app.core.mark_price_stream_manager.asyncio.sleep", new_callable=AsyncMock):
        yield


class TestMarkPriceSubscribeWhenPositionOpens:
    """Subscribe is triggered when position opens (strategy, manual, external); one connection per symbol."""

    @pytest.mark.asyncio
    async def test_subscribe_after_register_strategy_position(self, mock_mark_price_connection, no_sleep):
        """Strategy opens position → register_position + subscribe → connection created."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        strategy_id = str(uuid4())
        manager.register_position("BTCUSDT", strategy_id, user_id, 50000.0, 0.01, "LONG", "default")
        await manager.subscribe("BTCUSDT")
        assert "BTCUSDT" in manager._connections
        assert manager._subscription_counts.get("BTCUSDT") == 1
        mock_mark_price_connection.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_after_register_manual_position(self, mock_mark_price_connection, no_sleep):
        """Manual position opened → register + subscribe → connection created."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("ETHUSDT", "manual_mp-1", user_id, 3000.0, 0.5, "LONG", "default")
        await manager.subscribe("ETHUSDT")
        assert "ETHUSDT" in manager._connections
        mock_mark_price_connection.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_after_register_external_position(self, mock_mark_price_connection, no_sleep):
        """External position → register + subscribe → connection created."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("BTCUSDT", "external_LONG", user_id, 50000.0, 0.01, "LONG", "default")
        await manager.subscribe("BTCUSDT")
        assert "BTCUSDT" in manager._connections
        mock_mark_price_connection.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_reuses_connection_when_second_position_same_symbol(
        self, mock_mark_price_connection, no_sleep
    ):
        """Two positions same symbol (e.g. strategy + external) → subscribe once, reuse for second."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("BTCUSDT", str(uuid4()), user_id, 50000.0, 0.01, "LONG", "default")
        await manager.subscribe("BTCUSDT")
        manager.register_position("BTCUSDT", "external_SHORT", user_id, 50000.0, 0.01, "SHORT", "default")
        await manager.subscribe("BTCUSDT")
        # Still one connection; connect called once (reuse on second subscribe)
        assert mock_mark_price_connection.connect.call_count == 1
        assert len(manager._registry["BTCUSDT"]) == 2


# --- Unsubscribe: when no open positions for symbol we unsubscribe ---


class TestMarkPriceUnsubscribeWhenNoOpenPositions:
    """maybe_unsubscribe disconnects mark price when registry for symbol is empty (after close)."""

    @pytest.mark.asyncio
    async def test_maybe_unsubscribe_after_last_strategy_position_closed(
        self, mock_mark_price_connection, no_sleep
    ):
        """Close last strategy position → unregister + maybe_unsubscribe → connection removed."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        strategy_id = str(uuid4())
        manager.register_position("BTCUSDT", strategy_id, user_id, 50000.0, 0.01, "LONG", "default")
        await manager.subscribe("BTCUSDT")
        assert "BTCUSDT" in manager._connections
        manager.unregister_position("BTCUSDT", strategy_id)
        await manager.maybe_unsubscribe("BTCUSDT")
        assert "BTCUSDT" not in manager._connections
        assert "BTCUSDT" not in manager._subscription_counts
        mock_mark_price_connection.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_unsubscribe_after_last_manual_position_closed(
        self, mock_mark_price_connection, no_sleep
    ):
        """Close last manual position → unregister + maybe_unsubscribe → disconnect."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("ETHUSDT", "manual_mp-99", user_id, 3000.0, 0.5, "LONG", "paper1")
        await manager.subscribe("ETHUSDT")
        manager.unregister_position("ETHUSDT", "manual_mp-99")
        await manager.maybe_unsubscribe("ETHUSDT")
        assert "ETHUSDT" not in manager._connections
        mock_mark_price_connection.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_unsubscribe_after_last_external_position_closed(
        self, mock_mark_price_connection, no_sleep
    ):
        """Close last external position → unregister + maybe_unsubscribe → disconnect."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("BTCUSDT", "external_LONG", user_id, 50000.0, 0.01, "LONG", "default")
        await manager.subscribe("BTCUSDT")
        manager.unregister_position("BTCUSDT", "external_LONG")
        await manager.maybe_unsubscribe("BTCUSDT")
        assert "BTCUSDT" not in manager._connections
        mock_mark_price_connection.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_unsubscribe_does_not_disconnect_when_other_positions_still_open(
        self, mock_mark_price_connection, no_sleep
    ):
        """Two positions same symbol: close one (strategy) → maybe_unsubscribe → still subscribed (manual left)."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        strategy_id = str(uuid4())
        manager.register_position("BTCUSDT", strategy_id, user_id, 50000.0, 0.01, "LONG", "default")
        manager.register_position("BTCUSDT", "manual_mp-2", user_id, 50100.0, 0.02, "LONG", "default")
        await manager.subscribe("BTCUSDT")
        # Close strategy only
        manager.unregister_position("BTCUSDT", strategy_id)
        await manager.maybe_unsubscribe("BTCUSDT")
        # Registry still has manual position → maybe_unsubscribe does NOT call unsubscribe (registry not empty)
        assert "BTCUSDT" in manager._registry
        assert len(manager._registry["BTCUSDT"]) == 1
        # Connection should still be there (we only unsubscribe when registry is empty)
        assert "BTCUSDT" in manager._connections
        mock_mark_price_connection.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_maybe_unsubscribe_disconnects_when_last_of_multiple_closed(
        self, mock_mark_price_connection, no_sleep
    ):
        """Strategy + manual on same symbol: close strategy then manual → after last close, disconnect."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        strategy_id = str(uuid4())
        manager.register_position("BTCUSDT", strategy_id, user_id, 50000.0, 0.01, "LONG", "default")
        manager.register_position("BTCUSDT", "manual_mp-3", user_id, 50100.0, 0.02, "LONG", "default")
        await manager.subscribe("BTCUSDT")
        manager.unregister_position("BTCUSDT", strategy_id)
        await manager.maybe_unsubscribe("BTCUSDT")
        assert "BTCUSDT" in manager._connections
        manager.unregister_position("BTCUSDT", "manual_mp-3")
        await manager.maybe_unsubscribe("BTCUSDT")
        assert "BTCUSDT" not in manager._connections
        assert "BTCUSDT" not in manager._registry
        assert mock_mark_price_connection.disconnect.call_count == 1

    @pytest.mark.asyncio
    async def test_maybe_unsubscribe_when_no_positions_and_not_subscribed_is_noop(self):
        """maybe_unsubscribe when symbol was never subscribed (no connection) does not raise."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        await manager.maybe_unsubscribe("BTCUSDT")
        assert "BTCUSDT" not in manager._connections

    @pytest.mark.asyncio
    async def test_maybe_unsubscribe_when_registry_empty_but_still_subscribed_calls_unsubscribe(
        self, mock_mark_price_connection, no_sleep
    ):
        """After unregister, registry empty → maybe_unsubscribe → unsubscribe runs (connection removed)."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("ETHUSDT", "external_SHORT", user_id, 3000.0, 0.5, "SHORT", "default")
        await manager.subscribe("ETHUSDT")
        manager.unregister_position("ETHUSDT", "external_SHORT")
        assert "ETHUSDT" not in manager._registry
        await manager.maybe_unsubscribe("ETHUSDT")
        assert "ETHUSDT" not in manager._connections


# --- On tick: broadcast only when registry has entries; all entry types get broadcast ---


class TestMarkPriceOnTickBroadcast:
    """On mark price tick, broadcast is called for each registered entry; no broadcast when registry empty."""

    @pytest.mark.asyncio
    async def test_tick_broadcasts_for_strategy_manual_external_entries(self):
        """Single tick triggers one broadcast per registry entry (strategy, manual, external)."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("BTCUSDT", str(uuid4()), user_id, 50000.0, 0.01, "LONG", "default")
        manager.register_position("BTCUSDT", "manual_mp-x", user_id, 49900.0, 0.02, "LONG", "default")
        manager.register_position("BTCUSDT", "external_SHORT", user_id, 50050.0, 0.01, "SHORT", "default")
        handler = manager._on_mark_price_factory("BTCUSDT")
        await handler("BTCUSDT", {"mark_price": 50100.0})
        assert mock_broadcast.broadcast_position_update.await_count == 3
        calls = mock_broadcast.broadcast_position_update.call_args_list
        # LONG profit (50100 - 50000)*0.01 = 1, (50100-49900)*0.02 = 4; SHORT loss (50050-50100)*0.01 = -0.5
        pnls = [c[1]["unrealized_pnl"] for c in calls]
        assert 1.0 in pnls
        assert 4.0 in pnls
        assert -0.5 in pnls

    @pytest.mark.asyncio
    async def test_tick_passes_funding_fields_to_broadcast(self):
        """Mark payload with r/T and interval from cache → broadcast includes funding kwargs."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        sid = str(uuid4())
        manager.register_position("BTCUSDT", sid, user_id, 50000.0, 0.01, "LONG", "default")
        handler = manager._on_mark_price_factory("BTCUSDT")
        with patch(
            "app.core.mark_price_stream_manager.get_funding_interval_hours",
            return_value=8,
        ):
            await handler(
                "BTCUSDT",
                {"mark_price": 50100.0, "r": "0.0001", "T": 2000000000000},
            )
        mock_broadcast.broadcast_position_update.assert_awaited_once()
        kw = mock_broadcast.broadcast_position_update.call_args.kwargs
        assert kw.get("last_funding_rate") == pytest.approx(0.0001)
        assert kw.get("next_funding_time_ms") == 2000000000000
        assert kw.get("funding_interval_hours") == 8

    @pytest.mark.asyncio
    async def test_tick_with_empty_registry_does_not_broadcast(self):
        """Tick for symbol with no positions in registry does not call broadcast (no crash)."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        handler = manager._on_mark_price_factory("BTCUSDT")
        await handler("BTCUSDT", {"mark_price": 50100.0})
        mock_broadcast.broadcast_position_update.assert_not_called()


class TestMaxUnrealizedPnl:
    """Peak open unrealized PnL tracked per registry entry and passed to broadcast."""

    @pytest.mark.asyncio
    async def test_tick_updates_peak_and_broadcast_includes_max(self):
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        sid = str(uuid4())
        manager.register_position("BTCUSDT", sid, user_id, 50000.0, 0.01, "LONG", "default")
        handler = manager._on_mark_price_factory("BTCUSDT")
        await handler("BTCUSDT", {"mark_price": 49900.0})
        await handler("BTCUSDT", {"mark_price": 50200.0})
        assert manager.get_max_unrealized_pnl("BTCUSDT", sid) == pytest.approx(2.0)
        assert mock_broadcast.broadcast_position_update.await_count == 2
        last_call = mock_broadcast.broadcast_position_update.await_args_list[-1]
        assert last_call.kwargs.get("max_unrealized_pnl") == pytest.approx(2.0)

    def test_position_instance_change_resets_peak(self):
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        sid = str(uuid4())
        pid1 = uuid4()
        pid2 = uuid4()
        manager.register_position(
            "BTCUSDT", sid, user_id, 50000.0, 0.01, "LONG", "default",
            position_instance_id=pid1,
        )
        for e in manager._registry["BTCUSDT"]:
            if e["strategy_id"] == sid:
                e["max_unrealized_pnl"] = 99.0
        manager.register_position(
            "BTCUSDT", sid, user_id, 50000.0, 0.01, "LONG", "default",
            position_instance_id=pid2,
        )
        for e in manager._registry["BTCUSDT"]:
            if e["strategy_id"] == sid:
                assert e.get("max_unrealized_pnl") is None


# --- stop_all cleans connections and fallback tasks ---


class TestMarkPriceStopAll:
    """stop_all disconnects all and cancels REST fallback tasks."""

    @pytest.mark.asyncio
    async def test_stop_all_clears_connections_and_tasks(self, mock_mark_price_connection, no_sleep):
        """After stop_all, no connections or fallback tasks remain."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        manager.register_position("BTCUSDT", "strat-1", user_id, 50000.0, 0.01, "LONG", "default")
        await manager.subscribe("BTCUSDT")
        # subscribe creates a rest fallback task; stop_all should cancel it
        await manager.stop_all()
        assert len(manager._connections) == 0
        assert len(manager._subscription_counts) == 0
        assert len(manager._rest_fallback_tasks) == 0
        assert len(manager._mark_handlers) == 0
        mock_mark_price_connection.disconnect.assert_called_once()
