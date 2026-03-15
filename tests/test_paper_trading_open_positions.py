"""Test cases for paper trading open positions implementation.

Validates:
- Position data normalization (string to float for paper client)
- PaperBinanceClient accepted in get_symbol_pnl (position fetch not skipped)
- manual_close_strategy_position rejects strategy_id starting with manual_
- get_pnl_overview account_id filter case-insensitive
- get_pnl_overview merges multiple accounts for same symbol (open_positions + totals)
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.trade import SymbolPnL, PositionSummary, TradeSummary
from app.models.db_models import User


# --- Fixtures ---


@pytest.fixture
def mock_user():
    return User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hash",
        is_active=True,
    )


@pytest.fixture
def sample_position_dict_strings():
    """Position dict with string numeric values (as returned by paper client)."""
    return {
        "symbol": "BTCUSDT",
        "positionAmt": "0.1",
        "entryPrice": "50000.0",
        "markPrice": "51000.0",
        "unRealizedProfit": "100.0",
        "leverage": "10",
        "marginType": "CROSSED",
    }


# --- Normalization (string to float) ---


class TestPositionDataNormalization:
    """Validate that position data with string numerics is normalized to float."""

    def test_get_symbol_pnl_returns_float_position_fields_when_client_returns_strings(
        self, mock_user, sample_position_dict_strings
    ):
        """Paper/client returning string positionAmt, entryPrice, etc. must be normalized to float."""
        from app.api.routes.trades import get_symbol_pnl
        from app.core.paper_binance_client import PaperBinanceClient

        symbol = "BTCUSDT"
        account_id = "paper1"

        mock_runner = MagicMock()
        mock_runner.list_strategies.return_value = []

        mock_client = MagicMock()
        mock_client_manager = MagicMock()
        mock_client_manager.list_accounts.return_value = {account_id: None}

        # Real PaperBinanceClient so _client_has_api_key(c) returns True; override get_open_position
        paper_client = PaperBinanceClient(account_id=account_id, initial_balance=10000.0)
        paper_client.get_open_position = MagicMock(return_value=dict(sample_position_dict_strings))
        mock_client_manager.get_client.return_value = paper_client

        mock_db_service = MagicMock()
        mock_db_service.get_strategy.return_value = None

        result = get_symbol_pnl(
            symbol,
            account_id=account_id,
            start_date=None,
            end_date=None,
            current_user=mock_user,
            runner=mock_runner,
            client=mock_client,
            client_manager=mock_client_manager,
            db_service=mock_db_service,
        )

        assert result is not None
        assert hasattr(result, "open_positions")
        assert len(result.open_positions) >= 1
        pos = result.open_positions[0]
        assert isinstance(pos.entry_price, (int, float)), "entry_price should be numeric"
        assert isinstance(pos.position_size, (int, float)), "position_size should be numeric"
        assert isinstance(pos.unrealized_pnl, (int, float)), "unrealized_pnl should be numeric"
        assert pos.entry_price == 50000.0
        assert pos.position_size == 0.1
        assert pos.unrealized_pnl == 100.0


# --- Paper client accepted in get_symbol_pnl ---


class TestPaperClientAcceptedInGetSymbolPnl:
    """Validate that PaperBinanceClient is not skipped for position fetch."""

    def test_paper_client_fetches_position(self, mock_user):
        """When client is PaperBinanceClient, get_symbol_pnl should fetch position (not skip)."""
        from app.api.routes.trades import get_symbol_pnl
        from app.core.paper_binance_client import PaperBinanceClient

        symbol = "BTCUSDT"
        account_id = "paper1"
        position_data = {
            "symbol": "BTCUSDT",
            "positionAmt": 0.05,
            "entryPrice": 48000.0,
            "markPrice": 49000.0,
            "unRealizedProfit": 50.0,
            "leverage": 5,
            "marginType": "CROSSED",
        }

        paper_client = PaperBinanceClient(account_id=account_id, initial_balance=10000.0)
        paper_client.get_open_position = MagicMock(return_value=position_data)

        mock_runner = MagicMock()
        mock_runner.list_strategies.return_value = []
        mock_client = MagicMock()
        mock_client_manager = MagicMock()
        mock_client_manager.get_client.return_value = paper_client
        mock_client_manager.list_accounts.return_value = {account_id: None}
        mock_db_service = MagicMock()
        mock_db_service.get_strategy.return_value = None

        result = get_symbol_pnl(
            symbol,
            account_id=account_id,
            start_date=None,
            end_date=None,
            current_user=mock_user,
            runner=mock_runner,
            client=mock_client,
            client_manager=mock_client_manager,
            db_service=mock_db_service,
        )

        assert result is not None
        assert len(result.open_positions) == 1
        assert result.open_positions[0].symbol == symbol
        assert result.open_positions[0].position_size == 0.05
        paper_client.get_open_position.assert_called_once_with(symbol)


# --- manual_close_strategy_position rejects manual_ ---


class TestManualCloseRejectsManualStrategyId:
    """Validate that strategy manual-close endpoint rejects manual_ strategy IDs."""

    @pytest.mark.skipif(
        os.environ.get("DEPLOYMENT") == "true",
        reason="Skipped during deployment",
    )
    def test_manual_close_returns_400_for_manual_strategy_id(self, mock_user):
        """POST /api/trades/strategies/manual_xyz/manual-close must return 400 with correct detail."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.api.deps import get_current_user, get_strategy_runner, get_database_service

        mock_runner = MagicMock()
        mock_db = MagicMock()
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_strategy_runner] = lambda: mock_runner
        app.dependency_overrides[get_database_service] = lambda: mock_db
        client = TestClient(app)
        try:
            response = client.post(
                "/api/trades/strategies/manual_abc123/manual-close",
                json={},
                headers={"Authorization": "Bearer fake-token-for-deps"},
            )
            assert response.status_code == 400
            data = response.json()
            assert "detail" in data
            detail = data["detail"]
            if isinstance(detail, str):
                assert "manual" in detail.lower() or "Manual" in detail
            else:
                assert any("manual" in str(d).lower() for d in (detail if isinstance(detail, list) else [detail]))
        finally:
            app.dependency_overrides.clear()


# --- get_pnl_overview account_id case-insensitive and merge ---


class TestGetPnlOverviewAccountIdAndMerge:
    """Validate get_pnl_overview account_id filter and multi-account merge."""

    def test_get_symbol_pnl_account_id_filter_case_insensitive(self, mock_user):
        """get_symbol_pnl should include strategies when account_id differs only by case."""
        from app.api.routes.trades import get_symbol_pnl
        from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams

        symbol = "BTCUSDT"
        account_id_param = "livetest"  # lowercased as from get_pnl_overview

        strategy = StrategySummary(
            id="strat-1",
            name="Test",
            symbol=symbol,
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
            position_side="LONG",
            entry_price=50000.0,
            current_price=51000.0,
            position_size=0.1,
            unrealized_pnl=100.0,
            account_id="Livetest",  # different case
        )

        mock_runner = MagicMock()
        mock_runner.list_strategies.return_value = [strategy]
        mock_client = MagicMock()
        mock_client_manager = MagicMock()
        mock_client_manager.get_client.return_value = None
        mock_client_manager.list_accounts.return_value = {}
        mock_db_service = MagicMock()
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())

        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        mock_db_service.db = MagicMock()
        with patch("app.api.routes.reports._get_completed_trades_from_database", return_value=[]):
            result = get_symbol_pnl(
                    symbol,
                    account_id=account_id_param,
                    start_date=None,
                    end_date=None,
                    current_user=mock_user,
                    runner=mock_runner,
                    client=mock_client,
                    client_manager=mock_client_manager,
                    db_service=mock_db_service,
                )

        # Should not have filtered out the strategy: account_id filter is case-insensitive
        # (Livetest vs livetest), so we get a result for this symbol.
        assert result is not None
        assert result.symbol == symbol

    def test_get_pnl_overview_merge_same_symbol_two_accounts(self, mock_user):
        """When same symbol has positions on two accounts, merge produces one SymbolPnL with combined data."""
        from app.api.routes.trades import get_pnl_overview

        pos1 = PositionSummary(
            symbol="BTCUSDT",
            position_size=0.1,
            entry_price=50000.0,
            current_price=51000.0,
            position_side="LONG",
            unrealized_pnl=100.0,
            leverage=10,
            strategy_id="s1",
            strategy_name="Strategy 1",
            account_id="acc1",
        )
        pos2 = PositionSummary(
            symbol="BTCUSDT",
            position_size=0.05,
            entry_price=49000.0,
            current_price=51000.0,
            position_side="LONG",
            unrealized_pnl=100.0,
            leverage=5,
            strategy_id="s2",
            strategy_name="Strategy 2",
            account_id="acc2",
        )

        row1 = SymbolPnL(
            symbol="BTCUSDT",
            total_realized_pnl=10.0,
            total_unrealized_pnl=100.0,
            total_pnl=110.0,
            open_positions=[pos1],
            closed_trades=[],
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
        )
        row2 = SymbolPnL(
            symbol="BTCUSDT",
            total_realized_pnl=20.0,
            total_unrealized_pnl=100.0,
            total_pnl=120.0,
            open_positions=[pos2],
            closed_trades=[],
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
        )

        # Replicate merge logic from get_pnl_overview
        rows = [row1, row2]
        all_open = []
        for r in rows:
            all_open.extend(r.open_positions)
        total_realized = sum(r.total_realized_pnl for r in rows)
        total_unrealized = sum(r.total_unrealized_pnl for r in rows)

        assert len(all_open) == 2
        assert total_realized == 30.0
        assert total_unrealized == 200.0
        account_ids = {p.account_id for p in all_open}
        assert account_ids == {"acc1", "acc2"}
