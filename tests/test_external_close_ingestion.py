"""
Tests for manual close (external close) ingestion.

Covers:
1. find_closing_order_ids: filter by side, group by orderId, match quantity, return most recent
2. build_order_response_for_external_close: sets exit_reason=EXTERNAL_CLOSE
3. _has_exit_trade_for_position: idempotency guard (uses DB)
4. handle_external_position_close: guards (None position_instance_id, paper_trading, exit exists),
   happy path (fetch, save_trade, create_completed_trades), invalid position_side
5. StrategyPersistence: apply_position_data position_amt=0 calls handler then clear; update_position_info position_was_closed calls handler then clear
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.services.external_close_service import (
    find_closing_order_ids,
    build_order_response_for_external_close,
    _has_exit_trade_for_position,
    handle_external_position_close,
)
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.services.strategy_persistence import StrategyPersistence


# --- find_closing_order_ids (unit, mock client) ---


class TestFindClosingOrderIds:
    """Unit tests for find_closing_order_ids with mock Binance client."""

    def test_long_position_returns_sell_order_matching_quantity(self):
        """Closing LONG = SELL; single order with executedQty matching position_size."""
        client = MagicMock()
        client.get_account_trades.return_value = [
            {"orderId": 1001, "side": "SELL", "qty": 1.5, "executedQty": 1.5, "time": 1700000000000},
        ]
        result = find_closing_order_ids(client, "BTCUSDT", "LONG", 1.5)
        assert result == [1001]
        client.get_account_trades.assert_called_once()
        call_kw = client.get_account_trades.call_args[1]
        assert call_kw["symbol"] == "BTCUSDT"
        assert call_kw["limit"] == 100

    def test_short_position_returns_buy_order_matching_quantity(self):
        """Closing SHORT = BUY; single order with qty matching position_size."""
        client = MagicMock()
        client.get_account_trades.return_value = [
            {"orderId": 2002, "side": "BUY", "qty": 2.0, "executedQty": 2.0, "time": 1700000001000},
        ]
        result = find_closing_order_ids(client, "ETHUSDT", "SHORT", 2.0)
        assert result == [2002]

    def test_uses_executedQty_when_qty_missing(self):
        """Binance may return executedQty only."""
        client = MagicMock()
        client.get_account_trades.return_value = [
            {"orderId": 3003, "side": "SELL", "executedQty": 0.5, "time": 1700000002000},
        ]
        result = find_closing_order_ids(client, "XRPUSDT", "LONG", 0.5)
        assert result == [3003]

    def test_filters_wrong_side(self):
        """LONG close = SELL; BUY trades are ignored."""
        client = MagicMock()
        client.get_account_trades.return_value = [
            {"orderId": 4004, "side": "BUY", "qty": 1.0, "time": 1700000003000},
        ]
        result = find_closing_order_ids(client, "BTCUSDT", "LONG", 1.0)
        assert result == []

    def test_returns_most_recent_when_multiple_match(self):
        """When two orders match quantity, return the most recent by time."""
        client = MagicMock()
        client.get_account_trades.return_value = [
            {"orderId": 5001, "side": "SELL", "qty": 1.0, "time": 1700000000000},
            {"orderId": 5002, "side": "SELL", "qty": 1.0, "time": 1700000005000},
        ]
        result = find_closing_order_ids(client, "BTCUSDT", "LONG", 1.0)
        assert result == [5002]

    def test_tolerance_for_float_position_size(self):
        """Match within QTY_TOLERANCE (1e-6)."""
        client = MagicMock()
        client.get_account_trades.return_value = [
            {"orderId": 6001, "side": "SELL", "qty": 1.0 + 1e-7, "time": 1700000000000},
        ]
        result = find_closing_order_ids(client, "BTCUSDT", "LONG", 1.0)
        assert result == [6001]

    def test_empty_when_no_trades(self):
        """Return [] when client returns empty list."""
        client = MagicMock()
        client.get_account_trades.return_value = []
        result = find_closing_order_ids(client, "BTCUSDT", "LONG", 1.0)
        assert result == []

    def test_empty_when_client_raises(self):
        """Return [] when get_account_trades raises."""
        client = MagicMock()
        client.get_account_trades.side_effect = Exception("API error")
        result = find_closing_order_ids(client, "BTCUSDT", "LONG", 1.0)
        assert result == []


# --- build_order_response_for_external_close (unit, mock client) ---


class TestBuildOrderResponseForExternalClose:
    """Unit tests for build_order_response_for_external_close."""

    def test_sets_exit_reason_external_close(self):
        """Response must have exit_reason='EXTERNAL_CLOSE'."""
        client = MagicMock()
        raw = {"orderId": 99, "symbol": "BTCUSDT", "side": "SELL", "executedQty": "1", "avgPrice": "50000", "status": "FILLED", "time": 1700000000000}
        client.get_order_status.return_value = raw
        client._parse_order_response.return_value = OrderResponse(
            symbol="BTCUSDT",
            order_id=99,
            status="FILLED",
            side="SELL",
            price=0.0,
            avg_price=50000.0,
            executed_qty=1.0,
            exit_reason=None,
        )
        result = build_order_response_for_external_close(client, "BTCUSDT", 99, "LONG")
        assert result is not None
        assert result.exit_reason == "EXTERNAL_CLOSE"

    def test_returns_none_when_get_order_status_fails(self):
        """Return None when get_order_status raises."""
        client = MagicMock()
        client.get_order_status.side_effect = Exception("Not found")
        result = build_order_response_for_external_close(client, "BTCUSDT", 99, "LONG")
        assert result is None

    def test_returns_none_when_raw_empty(self):
        """Return None when get_order_status returns None/empty."""
        client = MagicMock()
        client.get_order_status.return_value = None
        result = build_order_response_for_external_close(client, "BTCUSDT", 99, "SHORT")
        assert result is None


# --- _has_exit_trade_for_position (unit, patch session) ---


class TestHasExitTradeForPosition:
    """Tests for idempotency guard _has_exit_trade_for_position."""

    @patch("app.core.database.get_session_factory")
    def test_returns_true_when_exit_trade_exists(self, mock_factory):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()
        mock_session = MagicMock(return_value=mock_db)
        mock_factory.return_value = mock_session
        sid = uuid4()
        pid = uuid4()
        assert _has_exit_trade_for_position(sid, pid, "SELL") is True
        mock_db.close.assert_called_once()

    @patch("app.core.database.get_session_factory")
    def test_returns_false_when_no_exit_trade(self, mock_factory):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_factory.return_value = MagicMock(return_value=mock_db)
        sid = uuid4()
        pid = uuid4()
        assert _has_exit_trade_for_position(sid, pid, "BUY") is False


# --- handle_external_position_close (async, mocks) ---


class TestHandleExternalPositionClose:
    """Async tests for handle_external_position_close."""

    @pytest.mark.asyncio
    async def test_returns_early_when_position_instance_id_none(self):
        """When position_instance_id is None, return without calling Binance or save."""
        with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
            await handle_external_position_close(
                user_id=uuid4(),
                strategy_id_str="s1",
                strategy_uuid=uuid4(),
                symbol="BTCUSDT",
                account_id="default",
                position_side="LONG",
                position_size=1.0,
                position_instance_id=None,
                entry_timestamp=None,
                account_client=MagicMock(),
                trade_service=MagicMock(),
                paper_trading=False,
            )
            mock_find.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_when_paper_trading(self):
        """When paper_trading is True, skip Binance fetch."""
        with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
            await handle_external_position_close(
                user_id=uuid4(),
                strategy_id_str="s1",
                strategy_uuid=uuid4(),
                symbol="BTCUSDT",
                account_id="default",
                position_side="LONG",
                position_size=1.0,
                position_instance_id=uuid4(),
                entry_timestamp=None,
                account_client=MagicMock(),
                trade_service=MagicMock(),
                paper_trading=True,
            )
            mock_find.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_when_invalid_position_side(self):
        """When position_side is not LONG/SHORT, return early."""
        with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
            await handle_external_position_close(
                user_id=uuid4(),
                strategy_id_str="s1",
                strategy_uuid=uuid4(),
                symbol="BTCUSDT",
                account_id="default",
                position_side="BOTH",
                position_size=1.0,
                position_instance_id=uuid4(),
                entry_timestamp=None,
                account_client=MagicMock(),
                trade_service=MagicMock(),
                paper_trading=False,
            )
            mock_find.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_when_exit_trade_already_exists(self):
        """When guard finds existing exit trade, skip fetch and save."""
        pid = uuid4()
        with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=True):
            with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
                await handle_external_position_close(
                    user_id=uuid4(),
                    strategy_id_str="s1",
                    strategy_uuid=uuid4(),
                    symbol="BTCUSDT",
                    account_id="default",
                    position_side="LONG",
                    position_size=1.0,
                    position_instance_id=pid,
                    entry_timestamp=None,
                    account_client=MagicMock(),
                    trade_service=MagicMock(),
                    paper_trading=False,
                )
                mock_find.assert_not_called()

    @pytest.mark.asyncio
    async def test_happy_path_calls_save_trade_and_create_completed_trades(self):
        """When guard passes and order found: save_trade and create_completed_trades called with EXTERNAL_CLOSE."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        mock_trade_svc.save_trade.return_value = MagicMock(id=uuid4())
        mock_client = MagicMock()
        mock_client.get_account_trades.return_value = [
            {"orderId": 888, "side": "SELL", "qty": 1.0, "time": 1700000000000},
        ]
        raw_order = {"orderId": 888, "symbol": "BTCUSDT", "side": "SELL", "executedQty": "1", "avgPrice": "50000", "status": "FILLED", "time": 1700000000000}
        mock_client.get_order_status.return_value = raw_order
        mock_client._parse_order_response.return_value = OrderResponse(
            symbol="BTCUSDT", order_id=888, status="FILLED", side="SELL", price=0.0,
            avg_price=50000.0, executed_qty=1.0, exit_reason=None,
        )

        with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
            with patch("app.services.external_close_service.build_order_response_for_external_close") as mock_build:
                mock_build.return_value = OrderResponse(
                    symbol="BTCUSDT", order_id=888, status="FILLED", side="SELL", price=0.0,
                    avg_price=50000.0, executed_qty=1.0, exit_reason="EXTERNAL_CLOSE",
                )
                with patch("app.services.completed_trade_helper.create_completed_trades_on_position_close") as mock_create:
                    mock_create.return_value = [uuid4()]

                    await handle_external_position_close(
                        user_id=uid,
                        strategy_id_str=str(sid),
                        strategy_uuid=sid,
                        symbol="BTCUSDT",
                        account_id="default",
                        position_side="LONG",
                        position_size=1.0,
                        position_instance_id=pid,
                        entry_timestamp=None,
                        account_client=mock_client,
                        trade_service=mock_trade_svc,
                        paper_trading=False,
                    )

                    mock_trade_svc.save_trade.assert_called_once()
                    call_kw = mock_trade_svc.save_trade.call_args[1]
                    assert call_kw["user_id"] == uid
                    assert call_kw["strategy_id"] == sid
                    assert call_kw["position_instance_id"] == pid
                    assert call_kw["order"].exit_reason == "EXTERNAL_CLOSE"

                    mock_create.assert_called_once()
                    create_kw = mock_create.call_args[1]
                    assert create_kw["exit_reason"] == "EXTERNAL_CLOSE"
                    assert create_kw["position_side"] == "LONG"


# --- StrategyPersistence integration (apply_position_data / update_position_info) ---


class TestStrategyPersistenceExternalClose:
    """Tests that persistence calls handle_external_position_close when position goes to zero."""

    @pytest.mark.asyncio
    async def test_apply_position_data_position_zero_calls_handler_then_clear(self):
        """When position_amt==0 and we had position, call handle_external_position_close then _clear_position_state_and_persist."""
        strat_id = str(uuid4())
        pos_id = uuid4()
        summary = StrategySummary(
            id=strat_id,
            name="Test",
            symbol="BTCUSDT",
            strategy_type=StrategyType.ema_crossover,
            status=StrategyState.running,
            leverage=10,
            risk_per_trade=0.01,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            account_id="default",
            last_signal="SELL",
            position_size=1.0,
            position_side="LONG",
            position_instance_id=pos_id,
        )
        persistence = StrategyPersistence(
            user_id=uuid4(),
            trade_service=MagicMock(),
            account_manager=MagicMock(),
            strategy_service=MagicMock(),
        )
        persistence.account_manager.get_account_client.return_value = MagicMock()
        persistence._clear_position_state_and_persist = AsyncMock()

        with patch("app.services.external_close_service.handle_external_position_close", new_callable=AsyncMock) as mock_handler:
            await persistence.apply_position_data(summary, {"position_amt": 0})

            mock_handler.assert_called_once()
            call_kw = mock_handler.call_args[1]
            assert call_kw["symbol"] == "BTCUSDT"
            assert call_kw["position_side"] == "LONG"
            assert call_kw["position_size"] == 1.0
            assert call_kw["position_instance_id"] == summary.position_instance_id

            persistence._clear_position_state_and_persist.assert_called_once_with(summary)

    @pytest.mark.asyncio
    async def test_apply_position_data_position_zero_no_handler_when_no_trade_service(self):
        """When trade_service is None, do not call handle_external_position_close."""
        strat_id = str(uuid4())
        summary = StrategySummary(
            id=strat_id,
            name="Test",
            symbol="BTCUSDT",
            strategy_type=StrategyType.ema_crossover,
            status=StrategyState.running,
            leverage=10,
            risk_per_trade=0.01,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            account_id="default",
            last_signal="SELL",
            position_size=1.0,
            position_side="LONG",
            position_instance_id=uuid4(),
        )
        persistence = StrategyPersistence(
            user_id=uuid4(),
            trade_service=None,
            account_manager=MagicMock(),
        )
        persistence._clear_position_state_and_persist = AsyncMock()

        with patch("app.services.external_close_service.handle_external_position_close", new_callable=AsyncMock) as mock_handler:
            await persistence.apply_position_data(summary, {"position_amt": 0})

            mock_handler.assert_not_called()
            persistence._clear_position_state_and_persist.assert_called_once_with(summary)
