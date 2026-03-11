"""
Tests validating exit_reason and external-close conditions.

Covers:
1. save_trade: when updating existing Trade with EXTERNAL_CLOSE, strategy exit_reason (TP/SL) overwrites
   and any CompletedTrade(s) referencing that exit get exit_reason updated.
2. get_trade_by_order_id: returns trade when exists, None when not.
3. handle_external_position_close: skips order when Trade already exists with strategy exit_reason (TP/SL).
4. handle_external_position_close: skips create_completed_trades when db_trade has non-EXTERNAL_CLOSE exit_reason.
5. Idempotency: external path does not overwrite or duplicate when strategy path already saved.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CheckConstraint

from app.models.db_models import (
    Base,
    User,
    Account,
    Strategy,
    Trade,
    CompletedTrade,
    CompletedTradeOrder,
)
from app.models.order import OrderResponse
from app.services.trade_service import TradeService
from app.services.external_close_service import handle_external_position_close

# SQLite for tests
TEST_DB_URL = "sqlite:///:memory:"

# JSONB compatibility for SQLite
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

if not hasattr(SQLiteTypeCompiler, "_visit_JSONB_patched"):
    def _visit_JSONB(self, type_, **kw):
        return "JSON"
    SQLiteTypeCompiler.visit_JSONB = _visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True


def _remove_pg_check_constraints():
    """Remove PostgreSQL-specific CHECK constraints for SQLite."""
    from sqlalchemy.dialects.sqlite.base import SQLiteDDLCompiler
    if hasattr(SQLiteDDLCompiler, "_visit_check_exit_reason_test"):
        return
    orig = SQLiteDDLCompiler.visit_check_constraint

    def visit_check_constraint(self, constraint, **kw):
        try:
            if "~" in str(constraint.sqltext) or "~*" in str(constraint.sqltext):
                return None
        except Exception:
            pass
        return orig(self, constraint, **kw)

    SQLiteDDLCompiler.visit_check_constraint = visit_check_constraint
    SQLiteDDLCompiler._visit_check_exit_reason_test = True


_remove_pg_check_constraints()


@pytest.fixture
def db_session():
    """Create in-memory SQLite database and session."""
    for table in Base.metadata.tables.values():
        to_remove = [
            c for c in table.constraints
            if isinstance(c, CheckConstraint) and (
                "~" in str(getattr(c, "sqltext", "")) or "~*" in str(getattr(c, "sqltext", ""))
            )
        ]
        for c in to_remove:
            table.constraints.discard(c)

    engine = create_engine(TEST_DB_URL, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(db_session):
    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hash",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_account(db_session, test_user):
    acc = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="test-account",
        name="Test",
        exchange_platform="binance",
        api_key_encrypted="k",
        api_secret_encrypted="s",
        testnet=False,
        is_active=True,
    )
    db_session.add(acc)
    db_session.commit()
    return acc


@pytest.fixture
def test_strategy(db_session, test_user, test_account):
    strat = Strategy(
        id=uuid4(),
        user_id=test_user.id,
        account_id=test_account.id,
        strategy_id="test-strat-1",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type="scalping",
        status="running",
        leverage=5,
        risk_per_trade=0.01,
        position_size=0.0,
        position_side=None,
        position_instance_id=None,
    )
    db_session.add(strat)
    db_session.commit()
    return strat


def _make_order_response(order_id, side="SELL", exit_reason=None, executed_qty=1.0, price=50000.0):
    return OrderResponse(
        symbol="BTCUSDT",
        order_id=order_id,
        status="FILLED",
        side=side,
        price=price,
        avg_price=price,
        executed_qty=executed_qty,
        timestamp=datetime.now(timezone.utc),
        commission=0.0,
        position_side="LONG" if side == "SELL" else "SHORT",
        order_type="MARKET",
        exit_reason=exit_reason,
    )


# --- TradeService: strategy exit_reason overwrites EXTERNAL_CLOSE and updates CompletedTrade ---


class TestSaveTradeExitReasonOverwrite:
    """When strategy path runs second, save_trade overwrites EXTERNAL_CLOSE with TP/SL and updates CompletedTrade."""

    def test_update_existing_trade_with_strategy_exit_reason_overwrites_and_updates_completed_trade(
        self, db_session, test_user, test_strategy, test_account
    ):
        """External path created Trade with EXTERNAL_CLOSE and CompletedTrade; strategy path runs second with TP."""
        pos_id = uuid4()
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1001,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            status="FILLED",
            price=Decimal("50000"),
            avg_price=Decimal("50000"),
            executed_qty=Decimal("1.0"),
            timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            position_instance_id=pos_id,
            paper_trading=False,
        )
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1002,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            status="FILLED",
            price=Decimal("51000"),
            avg_price=Decimal("51000"),
            executed_qty=Decimal("1.0"),
            timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            position_instance_id=pos_id,
            exit_reason="EXTERNAL_CLOSE",
            paper_trading=False,
        )
        db_session.add(entry_trade)
        db_session.add(exit_trade)
        db_session.flush()

        close_event_id = uuid4()
        ct = CompletedTrade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            account_id=test_account.id,
            close_event_id=close_event_id,
            symbol="BTCUSDT",
            side="LONG",
            entry_time=entry_trade.timestamp,
            exit_time=exit_trade.timestamp,
            entry_price=Decimal("50000"),
            exit_price=Decimal("51000"),
            quantity=Decimal("1.0"),
            pnl_usd=Decimal("1000"),
            pnl_pct=Decimal("2.0"),
            fee_paid=Decimal("0"),
            funding_fee=Decimal("0"),
            entry_order_id=entry_trade.order_id,
            exit_order_id=exit_trade.order_id,
            exit_reason="EXTERNAL_CLOSE",
            position_instance_id=pos_id,
            paper_trading=False,
        )
        db_session.add(ct)
        db_session.flush()
        db_session.add(CompletedTradeOrder(
            id=uuid4(),
            completed_trade_id=ct.id,
            trade_id=entry_trade.id,
            order_id=entry_trade.order_id,
            account_id=test_account.id,
            order_role="ENTRY",
            quantity=Decimal("1.0"),
            price=Decimal("50000"),
            timestamp=entry_trade.timestamp,
        ))
        db_session.add(CompletedTradeOrder(
            id=uuid4(),
            completed_trade_id=ct.id,
            trade_id=exit_trade.id,
            order_id=exit_trade.order_id,
            account_id=test_account.id,
            order_role="EXIT",
            quantity=Decimal("1.0"),
            price=Decimal("51000"),
            timestamp=exit_trade.timestamp,
        ))
        db_session.commit()

        trade_service = TradeService(db=db_session, redis_storage=None)
        order_tp = _make_order_response(1002, side="SELL", exit_reason="TP", executed_qty=1.0, price=51000.0)

        updated = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order_tp,
            position_instance_id=pos_id,
            commit=True,
        )

        assert updated.id == exit_trade.id
        assert updated.exit_reason == "TP"

        db_session.expire_all()
        ct_refresh = db_session.query(CompletedTrade).filter(CompletedTrade.id == ct.id).first()
        assert ct_refresh is not None
        assert ct_refresh.exit_reason == "TP"

    def test_update_does_not_overwrite_exit_reason_with_external_close(self, db_session, test_user, test_strategy):
        """When updating a trade that already has TP, passing EXTERNAL_CLOSE in order should not overwrite to EXTERNAL_CLOSE (we only set strategy reasons)."""
        pos_id = uuid4()
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=2002,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            status="FILLED",
            price=Decimal("51000"),
            avg_price=Decimal("51000"),
            executed_qty=Decimal("0.5"),
            timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            position_instance_id=pos_id,
            exit_reason="TP",
            paper_trading=False,
        )
        db_session.add(exit_trade)
        db_session.commit()

        trade_service = TradeService(db=db_session, redis_storage=None)
        order_external = _make_order_response(2002, side="SELL", exit_reason="EXTERNAL_CLOSE", executed_qty=0.5, price=51000.0)

        updated = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order_external,
            position_instance_id=pos_id,
            commit=True,
        )

        assert updated.exit_reason == "TP"


# --- get_trade_by_order_id ---


class TestGetTradeByOrderId:
    """TradeService.get_trade_by_order_id returns correct result."""

    def test_returns_trade_when_exists(self, db_session, test_user, test_strategy):
        trade_service = TradeService(db=db_session, redis_storage=None)
        order = _make_order_response(3001, side="BUY", exit_reason=None)
        saved = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order,
            commit=True,
        )
        found = trade_service.get_trade_by_order_id(test_strategy.id, 3001)
        assert found is not None
        assert found.id == saved.id
        assert found.order_id == 3001

    def test_returns_none_when_not_exists(self, db_session, test_strategy):
        trade_service = TradeService(db=db_session, redis_storage=None)
        found = trade_service.get_trade_by_order_id(test_strategy.id, 99999)
        assert found is None


# --- handle_external_position_close: skip when trade already has strategy exit_reason ---


class TestHandleExternalPositionCloseSkipsStrategyExitReason:
    """External path skips order when Trade already exists with TP/SL (strategy path saved first)."""

    @pytest.mark.asyncio
    async def test_skips_order_when_get_trade_by_order_id_returns_trade_with_tp(self):
        """When get_trade_by_order_id returns a trade with exit_reason=TP, we skip that order (no save_trade, no create_completed_trades)."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        order_id = 888

        mock_trade_svc = MagicMock()
        mock_trade_svc.get_trade_by_order_id.return_value = MagicMock(exit_reason="TP")
        mock_trade_svc.save_trade = MagicMock()

        mock_client = MagicMock()
        mock_client.get_account_trades.return_value = [
            {"orderId": order_id, "side": "SELL", "qty": 1.0, "time": 1700000000000},
        ]

        with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
            with patch("app.services.external_close_service.find_closing_order_ids", return_value=[order_id]):
                with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
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

        mock_trade_svc.get_trade_by_order_id.assert_called_with(sid, order_id)
        mock_trade_svc.save_trade.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_create_completed_trades_when_save_trade_returns_trade_with_tp(self):
        """When save_trade returns existing trade with exit_reason=TP (strategy saved first), we skip create_completed_trades."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        order_id = 777

        mock_trade_svc = MagicMock()
        mock_trade_svc.get_trade_by_order_id.return_value = None
        db_trade_with_tp = MagicMock(exit_reason="TP", id=uuid4())
        mock_trade_svc.save_trade.return_value = db_trade_with_tp

        mock_client = MagicMock()
        mock_client.get_account_trades.return_value = [
            {"orderId": order_id, "side": "SELL", "qty": 1.0, "time": 1700000000000},
        ]
        with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=False):
            with patch("app.services.external_close_service.find_closing_order_ids", return_value=[order_id]):
                with patch("app.services.external_close_service.build_order_response_for_external_close") as mock_build:
                    mock_build.return_value = OrderResponse(
                        symbol="BTCUSDT", order_id=order_id, status="FILLED", side="SELL",
                        price=0.0, avg_price=50000.0, executed_qty=1.0, exit_reason="EXTERNAL_CLOSE",
                    )
                    with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
                        with patch("app.services.completed_trade_helper.create_completed_trades_on_position_close") as mock_create:
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
                            mock_create.assert_not_called()


# --- Idempotency: exit_exists guard ---


class TestExternalCloseRecheckAfterWait:
    """External path re-checks exit_exists after brief wait (strategy path can save first)."""

    @pytest.mark.asyncio
    async def test_skips_fetch_when_exit_appears_after_wait(self):
        """When exit_exists is False then True after re-check, we skip fetch (strategy path saved first)."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        mock_client = MagicMock()

        with patch("app.services.external_close_service._has_exit_trade_for_position") as mock_has:
            with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                call_count = [0]

                def side_effect(*args, **kwargs):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        return False
                    return True

                mock_has.side_effect = side_effect
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

        mock_sleep.assert_called_once()
        mock_client.get_account_trades.assert_not_called()
        mock_trade_svc.save_trade.assert_not_called()


class TestExternalCloseIdempotency:
    """External path respects exit_exists and does not duplicate."""

    @pytest.mark.asyncio
    async def test_returns_early_when_exit_trade_already_exists_for_position(self):
        """When _has_exit_trade_for_position returns True, we do not fetch or save."""
        uid = uuid4()
        sid = uuid4()
        pid = uuid4()
        mock_trade_svc = MagicMock()
        mock_client = MagicMock()

        with patch("app.services.external_close_service._has_exit_trade_for_position", return_value=True):
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

        mock_client.get_account_trades.assert_not_called()
        mock_trade_svc.save_trade.assert_not_called()
