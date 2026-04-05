"""
Tests for manual close (external close) ingestion.

Covers:
1. _qty_match: tolerance rules for matching closing order total qty
2. find_closing_order_ids: filter by side, group by orderId, match quantity, return most recent;
   invalid side; chunked fills (sum per orderId) requiring full size not last-stream chunk
3. build_order_response_for_external_close: sets exit_reason=EXTERNAL_CLOSE; BinanceClient path;
   minimal client without _parse_order_response
4. _has_exit_trade_for_position: idempotency guard (uses DB)
5. handle_external_position_close: guards, happy path, SHORT side, entry_quantity tail fallback,
   no fallback for partial-close-sized WS, first-hit skips second find, eq==ws skips redundant find,
   skip completed_trades when save returns TP/SL, skip when order already TP/SL + ingest warning
6. StrategyPersistence: apply_position_data position_amt=0 calls handler then clear; no handler without trade_service
"""

import pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.services.external_close_service import (
    QTY_TOLERANCE,
    _qty_match,
    find_closing_order_ids,
    build_order_response_for_external_close,
    _has_exit_trade_for_position,
    handle_external_position_close,
)
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.services.strategy_persistence import StrategyPersistence


# --- _qty_match (unit) ---


class TestQtyMatch:
    """Unit tests for _qty_match (used by find_closing_order_ids)."""

    def test_exact_match(self):
        assert _qty_match(91.0, 91.0) is True

    def test_zero_position_size_never_matches(self):
        assert _qty_match(0.0, 91.0) is False
        assert _qty_match(-1.0, 1.0) is False

    def test_within_absolute_tolerance(self):
        assert _qty_match(1.0, 1.0 + QTY_TOLERANCE * 0.5) is True

    def test_relative_tolerance_small_position(self):
        """Float noise for small notionals (position_size * 1e-9 floor)."""
        assert _qty_match(0.001, 0.001 + 5e-13) is True

    def test_no_match_when_far(self):
        assert _qty_match(11.0, 91.0) is False


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
        assert call_kw["limit"] == 500

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

    def test_multi_fill_same_order_id_sums_qty(self):
        """Native TP/SL can appear as multiple user trades with same orderId (partial fills)."""
        client = MagicMock()
        client.get_account_trades.return_value = [
            {"orderId": 9001, "side": "SELL", "qty": 0.004, "time": 1700000001000},
            {"orderId": 9001, "side": "SELL", "qty": 0.006, "time": 1700000002000},
        ]
        result = find_closing_order_ids(client, "BTCUSDT", "LONG", 0.01)
        assert result == [9001]

    def test_empty_when_client_raises(self):
        """Return [] when get_account_trades raises."""
        client = MagicMock()
        client.get_account_trades.side_effect = Exception("API error")
        result = find_closing_order_ids(client, "BTCUSDT", "LONG", 1.0)
        assert result == []

    def test_invalid_position_side_returns_empty(self):
        assert find_closing_order_ids(MagicMock(), "BTCUSDT", "BOTH", 1.0) == []

    def test_chunked_manual_close_matches_full_order_total(self):
        """Same as live issue: one SELL orderId with many fills summing to full size; match 91 not 11."""
        client = MagicMock()
        client.get_account_trades.return_value = [
            {"orderId": 777, "side": "SELL", "qty": 19, "time": 1700000001000},
            {"orderId": 777, "side": "SELL", "qty": 11, "time": 1700000002000},
            {"orderId": 777, "side": "SELL", "qty": 19, "time": 1700000003000},
            {"orderId": 777, "side": "SELL", "qty": 31, "time": 1700000004000},
            {"orderId": 777, "side": "SELL", "qty": 11, "time": 1700000005000},
        ]
        assert find_closing_order_ids(client, "SIRENUSDT", "LONG", 11.0) == []
        assert find_closing_order_ids(client, "SIRENUSDT", "LONG", 91.0) == [777]


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
        client._parse_order_response.assert_called_once_with(raw, "BTCUSDT")

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

    def test_no_parse_order_response_builds_minimal_order(self):
        """Clients without _parse_order_response still get EXTERNAL_CLOSE."""
        raw = {
            "orderId": 42,
            "symbol": "ETHUSDT",
            "side": "BUY",
            "executedQty": "2.5",
            "avgPrice": "3000",
            "status": "FILLED",
        }

        def _get_order_status(symbol="", order_id=0):
            return raw

        client = SimpleNamespace(get_order_status=_get_order_status)
        assert not hasattr(client, "_parse_order_response")
        result = build_order_response_for_external_close(client, "ETHUSDT", 42, "SHORT")
        assert result is not None
        assert result.exit_reason == "EXTERNAL_CLOSE"
        assert result.symbol == "ETHUSDT"
        assert result.order_id == 42
        assert result.side == "BUY"
        assert result.executed_qty == 2.5


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
        # exit_reason=None so handler does not skip create_completed_trades (skip only when strategy exit_reason like TP/SL)
        mock_trade_svc.save_trade.return_value = MagicMock(id=uuid4(), exit_reason=None)
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

    @pytest.mark.asyncio
    async def test_retries_find_with_entry_quantity_when_ws_tail_chunk(self):
        """Chunked ACCOUNT_UPDATE before FLAT can leave last snapshot << full close order qty."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        mock_trade_svc.save_trade.return_value = MagicMock(id=uuid4(), exit_reason=None)
        with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
            with patch("app.services.external_close_service.build_order_response_for_external_close") as mock_build:
                mock_build.return_value = OrderResponse(
                    symbol="BTCUSDT",
                    order_id=999,
                    status="FILLED",
                    side="SELL",
                    price=0.0,
                    avg_price=1.0,
                    executed_qty=91.0,
                    exit_reason="EXTERNAL_CLOSE",
                )
                with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
                    mock_find.side_effect = [[], [999]]
                    with patch(
                        "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                    ):
                        await handle_external_position_close(
                            user_id=uid,
                            strategy_id_str="strat-1",
                            strategy_uuid=sid,
                            symbol="BTCUSDT",
                            account_id="default",
                            position_side="LONG",
                            position_size=11.0,
                            position_instance_id=pid,
                            entry_timestamp=None,
                            account_client=MagicMock(),
                            trade_service=mock_trade_svc,
                            paper_trading=False,
                            entry_quantity=91.0,
                        )
                    assert mock_find.call_count == 2
                    assert mock_find.call_args_list[0][0][3] == 11.0
                    assert mock_find.call_args_list[1][0][3] == 91.0

    @pytest.mark.asyncio
    async def test_no_entry_fallback_when_ws_size_not_small_vs_entry(self):
        """Do not second-guess with entry_qty when last WS size looks like real remainder (partial close)."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
            with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
                mock_find.return_value = []
                await handle_external_position_close(
                    user_id=uid,
                    strategy_id_str="strat-1",
                    strategy_uuid=sid,
                    symbol="BTCUSDT",
                    account_id="default",
                    position_side="LONG",
                    position_size=51.0,
                    position_instance_id=pid,
                    entry_timestamp=None,
                    account_client=MagicMock(),
                    trade_service=mock_trade_svc,
                    paper_trading=False,
                    entry_quantity=91.0,
                )
                mock_find.assert_called_once()
                assert mock_find.call_args[0][3] == 51.0

    @pytest.mark.asyncio
    async def test_short_position_passes_short_to_find_closing_order_ids(self):
        """Closing SHORT = BUY side in account trades."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        mock_trade_svc.save_trade.return_value = MagicMock(id=uuid4(), exit_reason=None)
        with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
            with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
                with patch("app.services.external_close_service.build_order_response_for_external_close") as mock_build:
                    mock_build.return_value = OrderResponse(
                        symbol="BTCUSDT",
                        order_id=1,
                        status="FILLED",
                        side="BUY",
                        price=0.0,
                        avg_price=1.0,
                        executed_qty=2.0,
                        exit_reason="EXTERNAL_CLOSE",
                    )
                    with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
                        mock_find.return_value = [1]
                        with patch(
                            "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                        ):
                            await handle_external_position_close(
                                user_id=uid,
                                strategy_id_str="s",
                                strategy_uuid=sid,
                                symbol="BTCUSDT",
                                account_id="default",
                                position_side="SHORT",
                                position_size=2.0,
                                position_instance_id=pid,
                                entry_timestamp=None,
                                account_client=MagicMock(),
                                trade_service=mock_trade_svc,
                                paper_trading=False,
                            )
                        mock_find.assert_called_once()
                        assert mock_find.call_args[0][2] == "SHORT"
                        assert mock_find.call_args[0][3] == 2.0

    @pytest.mark.asyncio
    async def test_no_second_find_when_first_succeeds_with_entry_quantity_set(self):
        """If ws size matches an order, do not retry with entry_quantity."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        mock_trade_svc.save_trade.return_value = MagicMock(id=uuid4(), exit_reason=None)
        with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
            with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
                with patch("app.services.external_close_service.build_order_response_for_external_close") as mock_build:
                    mock_build.return_value = OrderResponse(
                        symbol="BTCUSDT",
                        order_id=5,
                        status="FILLED",
                        side="SELL",
                        price=0.0,
                        avg_price=1.0,
                        executed_qty=1.0,
                        exit_reason="EXTERNAL_CLOSE",
                    )
                    with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
                        mock_find.return_value = [5]
                        with patch(
                            "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                        ):
                            await handle_external_position_close(
                                user_id=uid,
                                strategy_id_str="s",
                                strategy_uuid=sid,
                                symbol="BTCUSDT",
                                account_id="default",
                                position_side="LONG",
                                position_size=1.0,
                                position_instance_id=pid,
                                entry_timestamp=None,
                                account_client=MagicMock(),
                                trade_service=mock_trade_svc,
                                paper_trading=False,
                                entry_quantity=91.0,
                            )
                        mock_find.assert_called_once()
                        assert mock_find.call_args[0][3] == 1.0

    @pytest.mark.asyncio
    async def test_no_entry_fallback_when_entry_equals_ws_size(self):
        """abs(eq - position_size) <= tolerance skips redundant second find."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
            with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
                with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
                    mock_find.return_value = []
                    await handle_external_position_close(
                        user_id=uid,
                        strategy_id_str="s",
                        strategy_uuid=sid,
                        symbol="BTCUSDT",
                        account_id="default",
                        position_side="LONG",
                        position_size=91.0,
                        position_instance_id=pid,
                        entry_timestamp=None,
                        account_client=MagicMock(),
                        trade_service=mock_trade_svc,
                        paper_trading=False,
                        entry_quantity=91.0,
                    )
                    mock_find.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_create_completed_when_save_returns_strategy_exit_reason(self):
        """Existing TP/SL exit_reason on saved row skips completed-trade helper."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        mock_trade_svc.save_trade.return_value = MagicMock(id=uuid4(), exit_reason="STOP_LOSS")
        with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
            with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
                with patch("app.services.external_close_service.build_order_response_for_external_close") as mock_build:
                    mock_build.return_value = OrderResponse(
                        symbol="BTCUSDT",
                        order_id=8,
                        status="FILLED",
                        side="SELL",
                        price=0.0,
                        avg_price=1.0,
                        executed_qty=1.0,
                        exit_reason="EXTERNAL_CLOSE",
                    )
                    with patch("app.services.external_close_service.find_closing_order_ids", return_value=[8]):
                        with patch(
                            "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                        ) as mock_create:
                            await handle_external_position_close(
                                user_id=uid,
                                strategy_id_str="s",
                                strategy_uuid=sid,
                                symbol="BTCUSDT",
                                account_id="default",
                                position_side="LONG",
                                position_size=1.0,
                                position_instance_id=pid,
                                entry_timestamp=None,
                                account_client=MagicMock(),
                                trade_service=mock_trade_svc,
                                paper_trading=False,
                            )
                            mock_trade_svc.save_trade.assert_called_once()
                            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_order_when_trade_already_saved_with_stop_loss(self):
        """If order_id already recorded as TP/SL, try no spurious external save (loop continues)."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        existing = MagicMock()
        existing.exit_reason = "STOP_LOSS"
        mock_trade_svc.get_trade_by_order_id.return_value = existing
        with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
            with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
                with patch("app.services.external_close_service.find_closing_order_ids", return_value=[9]):
                    with patch(
                        "app.services.external_close_service.build_order_response_for_external_close"
                    ) as mock_build:
                        with patch(
                            "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                        ) as mock_create:
                            with patch("app.services.external_close_service.logger.warning") as mock_warn:
                                await handle_external_position_close(
                                    user_id=uid,
                                    strategy_id_str="s",
                                    strategy_uuid=sid,
                                    symbol="BTCUSDT",
                                    account_id="default",
                                    position_side="LONG",
                                    position_size=1.0,
                                    position_instance_id=pid,
                                    entry_timestamp=None,
                                    account_client=MagicMock(),
                                    trade_service=mock_trade_svc,
                                    paper_trading=False,
                                )
                            mock_build.assert_not_called()
                            mock_trade_svc.save_trade.assert_not_called()
                            mock_create.assert_not_called()
                            ingest_warnings = [
                                c
                                for c in mock_warn.call_args_list
                                if c[0] and "did not ingest" in c[0][0]
                            ]
                            assert len(ingest_warnings) == 1


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
