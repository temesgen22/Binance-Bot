"""
Scenario matrix for external close → exit Trade + completed trade creation.

Documents expected behavior for:
- Full flat (WS size matches closing order total)
- Chunked full close (WS tail + entry_quantity fallback)
- Final-leg partial close (remainder before flat; no entry fallback)
- SHORT / LONG, guards (paper, no instance, idempotency)
- Negative paths (no Binance match, build_order None, TP/SL already on order id)

Most tests assert the contract on ``create_completed_trades_on_position_close`` (args + called or not).
One test runs the real helper against SQLite with a patched session injection.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CheckConstraint

from app.models.db_models import Base, User, Account, Strategy, Trade, CompletedTrade
from app.models.order import OrderResponse
from app.services.external_close_service import handle_external_position_close, find_closing_order_ids
from app.services.trade_service import TradeService


# --- SQLite test DB (same pattern as test_exit_reason_and_external_close_conditions) ---

TEST_DB_URL = "sqlite:///:memory:"

from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

if not hasattr(SQLiteTypeCompiler, "_visit_JSONB_patched"):
    def _visit_JSONB(self, type_, **kw):
        return "JSON"

    SQLiteTypeCompiler.visit_JSONB = _visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True


def _strip_pg_regex_checks():
    from sqlalchemy.dialects.sqlite.base import SQLiteDDLCompiler

    if hasattr(SQLiteDDLCompiler, "_visit_check_ext_close"):
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
    SQLiteDDLCompiler._visit_check_ext_close = True


_strip_pg_regex_checks()


@pytest.fixture
def db_session():
    for table in Base.metadata.tables.values():
        to_remove = [
            c
            for c in table.constraints
            if isinstance(c, CheckConstraint)
            and ("~" in str(getattr(c, "sqltext", "")) or "~*" in str(getattr(c, "sqltext", "")))
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
def fx_user(db_session):
    u = User(
        id=uuid4(),
        username="u_ext_close",
        email="ext@example.com",
        password_hash="h",
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def fx_account(db_session, fx_user):
    a = Account(
        id=uuid4(),
        user_id=fx_user.id,
        account_id="acct-ext",
        name="A",
        exchange_platform="binance",
        api_key_encrypted="k",
        api_secret_encrypted="s",
        testnet=False,
        is_active=True,
    )
    db_session.add(a)
    db_session.commit()
    return a


@pytest.fixture
def fx_strategy(db_session, fx_user, fx_account):
    s = Strategy(
        id=uuid4(),
        user_id=fx_user.id,
        account_id=fx_account.id,
        strategy_id="public-strategy-id",
        name="Ext Close Scen",
        symbol="BTCUSDT",
        strategy_type="scalping",
        status="running",
        leverage=5,
        risk_per_trade=0.01,
        fixed_amount=10.0,
        position_size=0.0,
        position_side=None,
        position_instance_id=None,
    )
    db_session.add(s)
    db_session.commit()
    return s


def _order_for_side(position_side: str, order_id: int, executed_qty: float, price: float = 50000.0):
    if position_side.upper() == "LONG":
        oside = "SELL"
    else:
        oside = "BUY"
    return OrderResponse(
        symbol="BTCUSDT",
        order_id=order_id,
        status="FILLED",
        side=oside,
        price=price,
        avg_price=price,
        executed_qty=executed_qty,
        timestamp=datetime.now(timezone.utc),
        commission=0.0,
        position_side="LONG" if position_side.upper() == "LONG" else "SHORT",
        order_type="MARKET",
        exit_reason="EXTERNAL_CLOSE",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,position_side,ws_size,entry_qty,find_returns,exit_qty_from_binance,expect_create,expected_find_qty_args",
    [
        pytest.param(
            "long_full_ws_matches",
            "LONG",
            10.0,
            None,
            [[7001]],
            10.0,
            True,
            [10.0],
            id="long_full_ws_matches",
        ),
        pytest.param(
            "long_chunked_entry_fallback",
            "LONG",
            2.0,
            100.0,
            [[], [7002]],
            100.0,
            True,
            [2.0, 100.0],
            id="long_chunked_entry_fallback",
        ),
        pytest.param(
            "long_partial_final_leg_only",
            "LONG",
            40.0,
            100.0,
            [[7003]],
            40.0,
            True,
            [40.0],
            id="long_partial_final_leg_only",
        ),
        pytest.param(
            "short_full_close",
            "SHORT",
            5.0,
            None,
            [[7004]],
            5.0,
            True,
            [5.0],
            id="short_full_close",
        ),
        pytest.param(
            "long_tail_at_25pct_boundary_fallback",
            "LONG",
            25.0,
            100.0,
            [[], [7005]],
            100.0,
            True,
            [25.0, 100.0],
            id="long_tail_25pct_boundary",
        ),
        pytest.param(
            "long_no_fallback_ws_too_large_vs_entry",
            "LONG",
            50.0,
            100.0,
            [[]],
            0.0,
            False,
            [50.0],
            id="long_no_fallback_ws_50pct",
        ),
        pytest.param(
            "long_no_second_find_when_ws_eq_entry",
            "LONG",
            91.0,
            91.0,
            [[]],
            0.0,
            False,
            [91.0],
            id="long_ws_eq_entry_no_redundant_find",
        ),
        pytest.param(
            "no_create_find_empty",
            "LONG",
            1.0,
            None,
            [[]],
            0.0,
            False,
            [1.0],
            id="no_create_find_empty",
        ),
    ],
)
async def test_external_close_completed_trade_contract(
    name,
    position_side,
    ws_size,
    entry_qty,
    find_returns,
    exit_qty_from_binance,
    expect_create,
    expected_find_qty_args,
):
    """Assert find_closing_order_ids qty args and whether create_completed_trades runs."""
    del name  # for ids only
    uid = uuid4()
    strat_pk = uuid4()
    pos_inst = uuid4()
    exit_trade_id = uuid4()
    mock_ts = MagicMock()
    mock_ts.save_trade.return_value = MagicMock(id=exit_trade_id, exit_reason=None)
    mock_ts.get_trade_by_order_id.return_value = None

    order_id_used = find_returns[-1][0] if find_returns and find_returns[-1] else 9999

    def _build(client, symbol, oid, ps):
        return _order_for_side(position_side, int(oid), exit_qty_from_binance)

    with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
        with patch(
            "app.services.external_close_service._has_exit_trade_for_position", return_value=False
        ):
            with patch(
                "app.services.external_close_service.find_closing_order_ids",
                side_effect=find_returns,
            ) as mock_find:
                with patch(
                    "app.services.external_close_service.build_order_response_for_external_close",
                    side_effect=_build,
                ):
                    with patch(
                        "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                    ) as mock_create:
                        mock_create.return_value = [uuid4()]
                        await handle_external_position_close(
                            user_id=uid,
                            strategy_id_str="public-strategy-id",
                            strategy_uuid=strat_pk,
                            symbol="BTCUSDT",
                            account_id="default",
                            position_side=position_side,
                            position_size=ws_size,
                            position_instance_id=pos_inst,
                            entry_timestamp=None,
                            account_client=MagicMock(),
                            trade_service=mock_ts,
                            paper_trading=False,
                            entry_quantity=entry_qty,
                        )

                    assert mock_find.call_count == len(expected_find_qty_args)
                    for i, expected_qty in enumerate(expected_find_qty_args):
                        assert mock_find.call_args_list[i][0][3] == expected_qty
                        assert mock_find.call_args_list[i][0][2] == position_side

                    if expect_create:
                        mock_create.assert_called_once()
                        kw = mock_create.call_args[1]
                        assert kw["user_id"] == uid
                        assert kw["strategy_id"] == "public-strategy-id"
                        assert kw["exit_trade_id"] == exit_trade_id
                        assert kw["exit_order_id"] == order_id_used
                        assert kw["exit_quantity"] == exit_qty_from_binance
                        assert kw["position_side"] == position_side
                        assert kw["exit_reason"] == "EXTERNAL_CLOSE"
                    else:
                        mock_create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "paper,position_instance_id,position_side,expect_find",
    [
        pytest.param(True, uuid4(), "LONG", False, id="paper_skips_all"),
        pytest.param(False, None, "LONG", False, id="no_position_instance"),
        pytest.param(False, uuid4(), "BOTH", False, id="invalid_side"),
    ],
)
async def test_external_close_guards_no_completed_trade(
    paper, position_instance_id, position_side, expect_find
):
    with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
        with patch(
            "app.services.external_close_service._has_exit_trade_for_position", return_value=False
        ):
            with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
                with patch(
                    "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                ) as mock_create:
                    await handle_external_position_close(
                        user_id=uuid4(),
                        strategy_id_str="s",
                        strategy_uuid=uuid4(),
                        symbol="BTCUSDT",
                        account_id="default",
                        position_side=position_side,
                        position_size=1.0,
                        position_instance_id=position_instance_id,
                        entry_timestamp=None,
                        account_client=MagicMock(),
                        trade_service=MagicMock(),
                        paper_trading=paper,
                    )
                if expect_find:
                    mock_find.assert_called()
                else:
                    mock_find.assert_not_called()
                mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_idempotent_skip_when_exit_trade_already_exists():
    with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
        with patch(
            "app.services.external_close_service._has_exit_trade_for_position", return_value=True
        ):
            with patch("app.services.external_close_service.find_closing_order_ids") as mock_find:
                with patch(
                    "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                ) as mock_create:
                    await handle_external_position_close(
                        user_id=uuid4(),
                        strategy_id_str="s",
                        strategy_uuid=uuid4(),
                        symbol="BTCUSDT",
                        account_id="default",
                        position_side="LONG",
                        position_size=1.0,
                        position_instance_id=uuid4(),
                        entry_timestamp=None,
                        account_client=MagicMock(),
                        trade_service=MagicMock(),
                        paper_trading=False,
                    )
                mock_find.assert_not_called()
                mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_no_completed_trade_when_build_order_returns_none():
    mock_ts = MagicMock()
    mock_ts.save_trade.return_value = MagicMock(id=uuid4(), exit_reason=None)
    mock_ts.get_trade_by_order_id.return_value = None
    with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
        with patch(
            "app.services.external_close_service._has_exit_trade_for_position", return_value=False
        ):
            with patch(
                "app.services.external_close_service.find_closing_order_ids", return_value=[8080]
            ):
                with patch(
                    "app.services.external_close_service.build_order_response_for_external_close",
                    return_value=None,
                ):
                    with patch(
                        "app.services.completed_trade_helper.create_completed_trades_on_position_close"
                    ) as mock_create:
                        with patch("app.services.external_close_service.logger.warning") as mock_warn:
                            await handle_external_position_close(
                                user_id=uuid4(),
                                strategy_id_str="s",
                                strategy_uuid=uuid4(),
                                symbol="BTCUSDT",
                                account_id="default",
                                position_side="LONG",
                                position_size=1.0,
                                position_instance_id=uuid4(),
                                entry_timestamp=None,
                                account_client=MagicMock(),
                                trade_service=mock_ts,
                                paper_trading=False,
                            )
                        mock_create.assert_not_called()
                        mock_ts.save_trade.assert_not_called()
                        msgs = [c[0][0] for c in mock_warn.call_args_list if c[0]]
                        assert any("did not ingest" in m for m in msgs)


@pytest.mark.asyncio
async def test_find_closing_order_ids_partial_close_order_matches_remainder_not_full_entry():
    """Manual partial close of remainder: closing order total = last WS size, not original entry."""
    client = MagicMock()
    client.get_account_trades.return_value = [
        {"orderId": 111, "side": "SELL", "qty": 40.0, "time": 1700000000000},
    ]
    assert find_closing_order_ids(client, "BTCUSDT", "LONG", 40.0) == [111]
    assert find_closing_order_ids(client, "BTCUSDT", "LONG", 100.0) == []


@pytest.mark.asyncio
async def test_integration_external_close_creates_completed_trade_row(
    db_session, fx_user, fx_strategy
):
    """
    End-to-end: entry trade on DB → handle_external_position_close saves exit → real completed_trade_helper
    with injected session creates a CompletedTrade row.
    """
    pos_id = uuid4()
    entry = Trade(
        id=uuid4(),
        strategy_id=fx_strategy.id,
        user_id=fx_user.id,
        order_id=100001,
        symbol="BTCUSDT",
        side="BUY",
        position_side="LONG",
        price=49000.0,
        avg_price=49000.0,
        executed_qty=2.0,
        status="FILLED",
        commission=0.01,
        timestamp=datetime.now(timezone.utc),
        position_instance_id=pos_id,
    )
    db_session.add(entry)
    db_session.commit()

    trade_service = TradeService(db=db_session, redis_storage=None)
    uid = fx_user.id
    strat_pk = fx_strategy.id
    public_id = fx_strategy.strategy_id

    from app.services import completed_trade_helper as cth

    real_create = cth.create_completed_trades_on_position_close

    def _create_with_test_db(*args, **kwargs):
        kwargs = {**kwargs, "db": db_session}
        return real_create(*args, **kwargs)

    with patch("app.services.external_close_service.asyncio.sleep", new_callable=AsyncMock):
        with patch(
            "app.services.external_close_service._has_exit_trade_for_position", return_value=False
        ):
            with patch(
                "app.services.external_close_service.find_closing_order_ids", return_value=[200002]
            ):
                with patch(
                    "app.services.external_close_service.build_order_response_for_external_close"
                ) as mock_build:
                    mock_build.return_value = _order_for_side("LONG", 200002, 2.0, price=49500.0)
                    with patch.object(cth, "create_completed_trades_on_position_close", side_effect=_create_with_test_db):
                        with patch("app.services.completed_trade_helper.BinanceClient") as mock_bc:
                            mock_bc.return_value.get_funding_fees.return_value = []
                            await handle_external_position_close(
                                user_id=uid,
                                strategy_id_str=public_id,
                                strategy_uuid=strat_pk,
                                symbol="BTCUSDT",
                                account_id="default",
                                position_side="LONG",
                                position_size=2.0,
                                position_instance_id=pos_id,
                                entry_timestamp=None,
                                account_client=MagicMock(),
                                trade_service=trade_service,
                                paper_trading=False,
                                entry_quantity=2.0,
                            )

    exits = (
        db_session.query(Trade)
        .filter(
            Trade.strategy_id == strat_pk,
            Trade.side == "SELL",
            Trade.position_instance_id == pos_id,
        )
        .all()
    )
    assert len(exits) >= 1
    assert exits[0].exit_reason == "EXTERNAL_CLOSE"

    completed = (
        db_session.query(CompletedTrade)
        .filter(CompletedTrade.strategy_id == strat_pk)
        .all()
    )
    assert len(completed) == 1
    ct = completed[0]
    assert float(ct.quantity) == pytest.approx(2.0)
    assert ct.side == "LONG"
    assert float(ct.entry_price) == pytest.approx(49000.0)
    assert float(ct.exit_price) == pytest.approx(49500.0)
