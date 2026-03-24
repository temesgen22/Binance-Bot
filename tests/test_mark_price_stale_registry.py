"""
Tests for mark-price registry heartbeat behavior and StrategyPersistence flat cleanup.

Validates:
- Entries persist until explicit unregister (no stale-on-tick eviction).
- Fresh entries still receive broadcasts; mixed registry broadcasts all active rows.
- update_position_info when exchange is flat unregisters mark-price registry (no zombie PnL).
- Heartbeat path: open position unchanged still refreshes register_position (last_seen_at).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.mark_price_stream_manager import MarkPriceStreamManager
from app.models.strategy import StrategyParams, StrategySummary, StrategyState, StrategyType
from app.services.strategy_persistence import StrategyPersistence


def _minimal_summary(
    strategy_id: str,
    *,
    symbol: str = "BTCUSDT",
    position_size: float | None = 0.0,
    position_side: str | None = None,
) -> StrategySummary:
    return StrategySummary(
        id=strategy_id,
        name="Test",
        symbol=symbol,
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
        account_id="default",
        last_signal="HOLD",
        position_size=position_size,
        position_side=position_side,  # type: ignore[arg-type]
    )


class TestMarkPriceRegistryOnTick:
    """Registry entries are kept on tick; broadcasts continue until explicit unregister."""

    @pytest.mark.asyncio
    async def test_old_entry_still_broadcasts_and_is_not_removed(self):
        """Old entry is kept; tick still broadcasts and does not auto-unsubscribe."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        sid = str(uuid4())
        with patch("app.core.mark_price_stream_manager.time.time", return_value=1000.0):
            manager.register_position("BTCUSDT", sid, user_id, 50000.0, 0.01, "LONG", "default")
        maybe_spy = AsyncMock(side_effect=manager.maybe_unsubscribe)
        manager.maybe_unsubscribe = maybe_spy  # type: ignore[method-assign]
        handler = manager._on_mark_price_factory("BTCUSDT")
        with patch("app.core.mark_price_stream_manager.time.time", return_value=1181.0):
            await handler("BTCUSDT", {"mark_price": 50100.0})
        assert "BTCUSDT" in manager._registry
        maybe_spy.assert_not_called()
        mock_broadcast.broadcast_position_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fresh_entry_broadcasts_on_tick(self):
        """When last_seen is within window, tick broadcasts once."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        sid = str(uuid4())
        with patch("app.core.mark_price_stream_manager.time.time", return_value=5000.0):
            manager.register_position("BTCUSDT", sid, user_id, 50000.0, 0.01, "LONG", "default")
        handler = manager._on_mark_price_factory("BTCUSDT")
        with patch("app.core.mark_price_stream_manager.time.time", return_value=5100.0):
            await handler("BTCUSDT", {"mark_price": 50100.0})
        mock_broadcast.broadcast_position_update.assert_awaited_once()
        assert sid in [e["strategy_id"] for e in manager._registry["BTCUSDT"]]

    @pytest.mark.asyncio
    async def test_two_entries_both_broadcast_and_both_remain(self):
        """Two strategies remain registered and both receive broadcasts."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        sid_fresh = str(uuid4())
        sid_stale = str(uuid4())
        with patch("app.core.mark_price_stream_manager.time.time", return_value=1000.0):
            manager.register_position("ETHUSDT", sid_fresh, user_id, 3000.0, 0.1, "LONG", "default")
            manager.register_position("ETHUSDT", sid_stale, user_id, 3000.0, 0.1, "SHORT", "default")
        with patch("app.core.mark_price_stream_manager.time.time", return_value=1200.0):
            manager.register_position("ETHUSDT", sid_fresh, user_id, 3000.0, 0.1, "LONG", "default")
        handler = manager._on_mark_price_factory("ETHUSDT")
        # No stale eviction on tick: both entries should still be present and receive broadcasts.
        with patch("app.core.mark_price_stream_manager.time.time", return_value=1380.0):
            await handler("ETHUSDT", {"mark_price": 3010.0})
        assert sid_fresh in [e["strategy_id"] for e in manager._registry.get("ETHUSDT", [])]
        assert sid_stale in [e["strategy_id"] for e in manager._registry.get("ETHUSDT", [])]
        assert mock_broadcast.broadcast_position_update.await_count == 2


class TestStrategyPersistenceMarkPriceFlatCleanup:
    """update_position_info unregisters mark price when exchange reports flat."""

    @pytest.mark.asyncio
    async def test_flat_exchange_unregisters_mark_price(self):
        """get_open_position returns None → unregister + maybe_unsubscribe on mark manager."""
        user_id = uuid4()
        strategy_id = str(uuid4())
        summary = _minimal_summary(strategy_id, position_size=0.0, position_side=None)

        mock_client = MagicMock()
        mock_client.get_open_position = MagicMock(return_value=None)

        account_manager = MagicMock()
        account_manager.get_account_client = MagicMock(return_value=mock_client)

        mark_mgr = MagicMock(spec=MarkPriceStreamManager)
        mark_mgr.unregister_position = MagicMock()
        mark_mgr.maybe_unsubscribe = AsyncMock()

        persistence = StrategyPersistence(
            account_manager=account_manager,
            user_id=user_id,
            mark_price_stream_manager=mark_mgr,
        )
        persistence.update_strategy_in_db = MagicMock(return_value=True)  # type: ignore[method-assign]

        await persistence.update_position_info(summary)

        mark_mgr.unregister_position.assert_called_once_with(summary.symbol, summary.id)
        mark_mgr.maybe_unsubscribe.assert_awaited_once_with(summary.symbol)

    @pytest.mark.asyncio
    async def test_open_position_unchanged_still_refreshes_mark_registry_heartbeat(self):
        """state_changed False → elif branch calls register_position to refresh last_seen."""
        user_id = uuid4()
        strategy_id = str(uuid4())
        summary = _minimal_summary(
            strategy_id,
            position_size=0.5,
            position_side="LONG",
        )
        summary.entry_price = 50000.0

        pos = {
            "positionAmt": 0.5,
            "entryPrice": 50000.0,
            "unRealizedProfit": 1.0,
            "markPrice": 50100.0,
            "leverage": "5",
        }
        mock_client = MagicMock()
        mock_client.get_open_position = MagicMock(return_value=pos)
        mock_client.get_current_leverage = MagicMock(return_value=5)

        account_manager = MagicMock()
        account_manager.get_account_client = MagicMock(return_value=mock_client)

        mark_mgr = MagicMock(spec=MarkPriceStreamManager)
        mark_mgr.register_position = MagicMock()
        mark_mgr.subscribe = AsyncMock()

        persistence = StrategyPersistence(
            account_manager=account_manager,
            user_id=user_id,
            mark_price_stream_manager=mark_mgr,
        )
        persistence.update_strategy_in_db = MagicMock(return_value=True)  # type: ignore[method-assign]

        await persistence.update_position_info(summary)

        mark_mgr.register_position.assert_called_once()
        args, kwargs = mark_mgr.register_position.call_args
        # register_position(symbol, strategy_id, user_id, entry_price, position_size, position_side, ...)
        assert args[4] == 0.5
        assert args[5] == "LONG"
        mark_mgr.subscribe.assert_not_awaited()


class TestMarkPriceStaleRegistryConsistency:
    """Guards against inconsistent registry behavior."""

    @pytest.mark.asyncio
    async def test_missing_last_seen_does_not_evict_entry(self):
        """If last_seen_at is missing, entry is still retained and broadcast proceeds."""
        mock_broadcast = AsyncMock()
        manager = MarkPriceStreamManager(mock_broadcast, testnet=True)
        user_id = uuid4()
        sid = str(uuid4())
        manager.register_position("BTCUSDT", sid, user_id, 50000.0, 0.01, "LONG", "default")
        # Simulate legacy entry without last_seen_at
        for e in manager._registry["BTCUSDT"]:
            if e["strategy_id"] == sid:
                e.pop("last_seen_at", None)
        handler = manager._on_mark_price_factory("BTCUSDT")
        with patch("app.core.mark_price_stream_manager.time.time", return_value=10_000.0):
            await handler("BTCUSDT", {"mark_price": 50100.0})
        assert "BTCUSDT" in manager._registry
        mock_broadcast.broadcast_position_update.assert_awaited_once()
