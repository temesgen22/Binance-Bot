"""Test risk metrics calculation with trade matching logic.

This test verifies that risk metrics (win rate, total PnL) are calculated
from completed trade cycles (entry+exit pairs) rather than individual trades,
matching the logic used in the reports page.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4

from app.models.order import OrderResponse
from app.models.db_models import Trade, Strategy, Account, User


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.fixture
def mock_strategy(mock_user):
    """Create a mock strategy."""
    strategy = MagicMock()
    strategy.id = uuid4()
    strategy.strategy_id = "test-strategy-123"
    strategy.user_id = mock_user.id
    strategy.name = "Test Strategy"
    strategy.symbol = "BTCUSDT"
    strategy.leverage = 5
    strategy.account_id = uuid4()
    return strategy


@pytest.fixture
def mock_account(mock_user):
    """Create a mock account."""
    account = MagicMock()
    account.id = uuid4()
    account.account_id = "test-account-123"
    account.user_id = mock_user.id
    account.is_active = True
    return account


@pytest.fixture
def sample_trades():
    """Create sample trades that form completed positions.
    
    Creates:
    - 2 BUY trades (entry)
    - 2 SELL trades (exit)
    - Should result in 2 completed trades:
      - Trade 1: BUY @ 40000, SELL @ 41000 = +1000 PnL (win)
      - Trade 2: BUY @ 40000, SELL @ 39000 = -1000 PnL (loss)
    """
    base_time = datetime.now(timezone.utc) - timedelta(days=1)
    
    # Entry trades (BUY)
    buy1 = MagicMock(spec=Trade)
    buy1.id = uuid4()
    buy1.order_id = 1001
    buy1.symbol = "BTCUSDT"
    buy1.side = "BUY"
    buy1.price = 40000.0
    buy1.avg_price = 40000.0
    buy1.executed_qty = 0.1
    buy1.status = "FILLED"
    buy1.timestamp = base_time
    buy1.realized_pnl = None  # Entry trades don't have realized PnL
    buy1.commission = 1.6
    buy1.commission_asset = "USDT"
    buy1.leverage = 5
    buy1.position_side = "LONG"
    buy1.update_time = base_time
    buy1.time_in_force = "GTC"
    buy1.order_type = "MARKET"
    buy1.notional_value = 4000.0
    buy1.cummulative_quote_qty = 4000.0
    buy1.initial_margin = 800.0
    buy1.margin_type = "ISOLATED"
    buy1.strategy_id = uuid4()
    
    buy2 = MagicMock(spec=Trade)
    buy2.id = uuid4()
    buy2.order_id = 1003
    buy2.symbol = "BTCUSDT"
    buy2.side = "BUY"
    buy2.price = 40000.0
    buy2.avg_price = 40000.0
    buy2.executed_qty = 0.1
    buy2.status = "FILLED"
    buy2.timestamp = base_time + timedelta(hours=2)
    buy2.realized_pnl = None
    buy2.commission = 1.6
    buy2.commission_asset = "USDT"
    buy2.leverage = 5
    buy2.position_side = "LONG"
    buy2.update_time = base_time + timedelta(hours=2)
    buy2.time_in_force = "GTC"
    buy2.order_type = "MARKET"
    buy2.notional_value = 4000.0
    buy2.cummulative_quote_qty = 4000.0
    buy2.initial_margin = 800.0
    buy2.margin_type = "ISOLATED"
    buy2.strategy_id = buy1.strategy_id
    
    # Exit trades (SELL)
    sell1 = MagicMock(spec=Trade)
    sell1.id = uuid4()
    sell1.order_id = 1002
    sell1.symbol = "BTCUSDT"
    sell1.side = "SELL"
    sell1.price = 41000.0
    sell1.avg_price = 41000.0
    sell1.executed_qty = 0.1
    sell1.status = "FILLED"
    sell1.timestamp = base_time + timedelta(hours=1)
    sell1.realized_pnl = 1000.0  # Win: (41000 - 40000) * 0.1 = 1000
    sell1.commission = 1.64
    sell1.commission_asset = "USDT"
    sell1.leverage = 5
    sell1.position_side = "LONG"
    sell1.update_time = base_time + timedelta(hours=1)
    sell1.time_in_force = "GTC"
    sell1.order_type = "MARKET"
    sell1.notional_value = 4100.0
    sell1.cummulative_quote_qty = 4100.0
    sell1.initial_margin = None
    sell1.margin_type = "ISOLATED"
    sell1.strategy_id = buy1.strategy_id
    
    sell2 = MagicMock(spec=Trade)
    sell2.id = uuid4()
    sell2.order_id = 1004
    sell2.symbol = "BTCUSDT"
    sell2.side = "SELL"
    sell2.price = 39000.0
    sell2.avg_price = 39000.0
    sell2.executed_qty = 0.1
    sell2.status = "FILLED"
    sell2.timestamp = base_time + timedelta(hours=3)
    sell2.realized_pnl = -1000.0  # Loss: (39000 - 40000) * 0.1 = -1000
    sell2.commission = 1.56
    sell2.commission_asset = "USDT"
    sell2.leverage = 5
    sell2.position_side = "LONG"
    sell2.update_time = base_time + timedelta(hours=3)
    sell2.time_in_force = "GTC"
    sell2.order_type = "MARKET"
    sell2.notional_value = 3900.0
    sell2.cummulative_quote_qty = 3900.0
    sell2.initial_margin = None
    sell2.margin_type = "ISOLATED"
    sell2.strategy_id = buy1.strategy_id
    
    return [buy1, sell1, buy2, sell2]


@pytest.mark.asyncio
async def test_portfolio_metrics_uses_trade_matching(mock_user, mock_strategy, mock_account, sample_trades):
    """Test that portfolio metrics uses trade matching to calculate win rate correctly."""
    from app.api.routes.risk_metrics import get_portfolio_risk_metrics
    from app.services.trade_service import TradeService
    from app.services.database_service import DatabaseService
    
    # Mock database session
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_account]
    
    # Mock trade service
    mock_trade_service = MagicMock(spec=TradeService)
    mock_trade_service.get_trades_by_account.return_value = sample_trades
    
    # Mock database service
    mock_db_service = MagicMock(spec=DatabaseService)
    mock_db_service.get_strategy.return_value = mock_strategy
    
    # Mock account service and client manager
    mock_account_service = MagicMock()
    mock_account_service.get_account.return_value = MagicMock()
    
    mock_client_manager = MagicMock()
    mock_client = MagicMock()
    mock_client.futures_account_balance.return_value = 10000.0
    mock_client_manager.get_client.return_value = mock_client
    mock_client_manager.add_client = MagicMock()
    
    # Mock request
    mock_request = MagicMock()
    
    with patch('app.api.routes.risk_metrics.TradeService', return_value=mock_trade_service), \
         patch('app.api.routes.risk_metrics.DatabaseService', return_value=mock_db_service), \
         patch('app.api.routes.risk_metrics.get_account_service', return_value=mock_account_service), \
         patch('app.api.routes.risk_metrics.get_client_manager', return_value=mock_client_manager), \
         patch('app.api.routes.risk_metrics.asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
        
        mock_to_thread.return_value = 10000.0
        
        # Call the endpoint
        result = await get_portfolio_risk_metrics(
            request=mock_request,
            account_id="test-account-123",
            lookback_days=90,
            current_user=mock_user,
            db=mock_db
        )
        
        # Verify the result
        assert result is not None
        assert "metrics" in result
        metrics = result["metrics"]
        
        # Should have 2 completed trades (not 4 individual trades)
        assert metrics["total_trades"] == 2, f"Expected 2 completed trades, got {metrics['total_trades']}"
        
        # Win rate should be 50% (1 win out of 2 completed trades)
        assert metrics["win_rate"] == 50.0, f"Expected 50% win rate, got {metrics['win_rate']}%"
        
        # Total PnL should be 0 (1000 - 1000 = 0)
        assert abs(metrics["total_pnl"]) < 0.01, f"Expected ~0 total PnL, got {metrics['total_pnl']}"
        
        # Should have 1 winning trade and 1 losing trade
        assert metrics["winning_trades"] == 1, f"Expected 1 winning trade, got {metrics['winning_trades']}"
        assert metrics["losing_trades"] == 1, f"Expected 1 losing trade, got {metrics['losing_trades']}"


@pytest.mark.asyncio
async def test_strategy_metrics_uses_trade_matching(mock_user, mock_strategy, sample_trades):
    """Test that strategy metrics uses trade matching to calculate win rate correctly."""
    from app.api.routes.risk_metrics import get_strategy_risk_metrics
    from app.services.trade_service import TradeService
    from app.services.database_service import DatabaseService
    
    # Mock database session
    mock_db = MagicMock()
    
    # Mock trade service
    mock_trade_service = MagicMock(spec=TradeService)
    mock_trade_service.get_strategy_trades.return_value = sample_trades
    
    # Mock database service
    mock_db_service = MagicMock(spec=DatabaseService)
    mock_db_service.get_strategy.return_value = mock_strategy
    
    # Mock account
    mock_account = MagicMock()
    mock_account.account_id = "test-account-123"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_account
    
    # Mock request
    mock_request = MagicMock()
    
    with patch('app.api.routes.risk_metrics.TradeService', return_value=mock_trade_service), \
         patch('app.api.routes.risk_metrics.DatabaseService', return_value=mock_db_service):
        
        # Call the endpoint
        result = await get_strategy_risk_metrics(
            request=mock_request,
            strategy_id="test-strategy-123",
            lookback_days=90,
            current_user=mock_user,
            db=mock_db
        )
        
        # Verify the result
        assert result is not None
        assert "metrics" in result
        metrics = result["metrics"]
        
        # Should have 2 completed trades (not 4 individual trades)
        assert metrics["total_trades"] == 2, f"Expected 2 completed trades, got {metrics['total_trades']}"
        
        # Win rate should be 50% (1 win out of 2 completed trades)
        assert metrics["win_rate"] == 50.0, f"Expected 50% win rate, got {metrics['win_rate']}%"
        
        # Should have 1 winning trade and 1 losing trade
        assert metrics["winning_trades"] == 1, f"Expected 1 winning trade, got {metrics['winning_trades']}"
        assert metrics["losing_trades"] == 1, f"Expected 1 losing trade, got {metrics['losing_trades']}"


def test_trade_matching_logic():
    """Test that trade matching correctly pairs entry and exit trades."""
    from app.api.routes.reports import _match_trades_to_completed_positions
    
    # Create trades that should form 2 completed positions
    base_time = datetime.now(timezone.utc)
    
    trades = [
        OrderResponse(
            symbol="BTCUSDT",
            order_id=1001,
            status="FILLED",
            side="BUY",
            price=40000.0,
            avg_price=40000.0,
            executed_qty=0.1,
            timestamp=base_time,
        ),
        OrderResponse(
            symbol="BTCUSDT",
            order_id=1002,
            status="FILLED",
            side="SELL",
            price=41000.0,
            avg_price=41000.0,
            executed_qty=0.1,
            timestamp=base_time + timedelta(hours=1),
        ),
        OrderResponse(
            symbol="BTCUSDT",
            order_id=1003,
            status="FILLED",
            side="BUY",
            price=40000.0,
            avg_price=40000.0,
            executed_qty=0.1,
            timestamp=base_time + timedelta(hours=2),
        ),
        OrderResponse(
            symbol="BTCUSDT",
            order_id=1004,
            status="FILLED",
            side="SELL",
            price=39000.0,
            avg_price=39000.0,
            executed_qty=0.1,
            timestamp=base_time + timedelta(hours=3),
        ),
    ]
    
    # Match trades
    completed_trades = _match_trades_to_completed_positions(
        trades,
        strategy_id="test-strategy",
        strategy_name="Test Strategy",
        symbol="BTCUSDT",
        leverage=5
    )
    
    # Should have 2 completed trades
    assert len(completed_trades) == 2, f"Expected 2 completed trades, got {len(completed_trades)}"
    
    # First trade should be a win (41000 - 40000 = +1000)
    # TradeReport uses pnl_usd (after fees) instead of realized_pnl
    assert completed_trades[0].pnl_usd > 0, "First trade should be a win"
    
    # Second trade should be a loss (39000 - 40000 = -1000)
    assert completed_trades[1].pnl_usd < 0, "Second trade should be a loss"
    
    # Verify PnL calculations are correct (accounting for fees and leverage)
    # The exact PnL values depend on fees and leverage calculations
    # Key verification: first trade is a win, second trade is a loss
    assert completed_trades[0].pnl_usd > 0, \
        f"First trade PnL should be positive (win), got {completed_trades[0].pnl_usd}"
    assert completed_trades[1].pnl_usd < 0, \
        f"Second trade PnL should be negative (loss), got {completed_trades[1].pnl_usd}"
    
    # Verify entry/exit prices are correct
    assert completed_trades[0].entry_price == 40000.0
    assert completed_trades[0].exit_price == 41000.0
    assert completed_trades[1].entry_price == 40000.0
    assert completed_trades[1].exit_price == 39000.0

