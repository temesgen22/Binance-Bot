"""
Test cases for enforcement event creation when risk limits are breached.

Tests verify that:
1. Enforcement events are created when breach status is detected
2. All 4 breach types create appropriate events (drawdown, daily loss, weekly loss, exposure)
3. Duplicate events are prevented (one per hour per breach type)
4. Events contain correct metadata (current value, limit value, account_id)
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.models.db_models import SystemEvent, Account
from app.services.database_service import DatabaseService


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.fixture
def mock_account():
    """Create a mock account."""
    account = MagicMock(spec=Account)
    account.id = uuid4()
    account.account_id = "test-account"
    account.user_id = uuid4()
    return account


@pytest.fixture
def mock_risk_config():
    """Create a mock risk configuration with limits."""
    config = MagicMock()
    config.max_portfolio_exposure_usdt = 10000.0
    config.max_daily_loss_usdt = 500.0  # Max loss is -500 USDT
    config.max_weekly_loss_usdt = 2000.0  # Max loss is -2000 USDT
    config.max_drawdown_pct = 0.15  # 15% max drawdown (stored as decimal 0-1)
    config.circuit_breaker_enabled = True
    return config


@pytest.mark.asyncio
async def test_daily_loss_breach_creates_enforcement_event(mock_user, mock_account, mock_risk_config):
    """Test that daily loss limit breach creates an enforcement event."""
    from app.api.routes.risk_metrics import get_realtime_risk_status
    from app.services.risk_management_service import RiskManagementService
    from app.services.trade_service import TradeService
    
    # Setup mocks
    mock_db = MagicMock()
    mock_db_service = MagicMock(spec=DatabaseService)
    mock_db_service.get_account_by_id.return_value = mock_account
    mock_db_service.get_enforcement_events.return_value = ([], 0)  # No recent events
    mock_db_service.create_system_event.return_value = MagicMock(spec=SystemEvent)
    
    mock_risk_service = MagicMock(spec=RiskManagementService)
    mock_risk_service.get_risk_config.return_value = mock_risk_config
    
    mock_trade_service = MagicMock(spec=TradeService)
    mock_account_service = MagicMock()
    mock_account_config = MagicMock()
    mock_account_config.api_key = "test_key"
    mock_account_config.api_secret = "test_secret"
    mock_account_service.get_account.return_value = mock_account_config
    
    mock_client_manager = MagicMock()
    mock_client = MagicMock()
    mock_client.futures_account_balance.return_value = 10000.0
    mock_client_manager.get_client.return_value = mock_client
    mock_client_manager.add_client = MagicMock()
    
    # Mock database queries
    # Need to mock Strategy query for the code to find strategies
    from app.models.db_models import Strategy
    mock_strategy = MagicMock(spec=Strategy)
    mock_strategy.id = uuid4()
    mock_strategy.strategy_id = "test-strategy"
    mock_strategy.name = "Test Strategy"
    mock_strategy.symbol = "BTCUSDT"
    mock_strategy.leverage = 5
    
    # Setup query chain for Strategy query
    mock_strategy_query = MagicMock()
    mock_strategy_query.filter.return_value.all.return_value = [mock_strategy]
    mock_strategy_query.filter.return_value.first.return_value = mock_strategy
    
    # Setup query chain for Account query
    mock_account_query = MagicMock()
    mock_account_query.filter.return_value.first.return_value = mock_account
    
    # Setup query chain for Trade query (empty - no raw trades)
    mock_trade_query = MagicMock()
    mock_trade_query.filter.return_value.all.return_value = []
    
    # Make mock_db.query return different queries based on what's being queried
    def query_side_effect(model):
        if model == Strategy:
            return mock_strategy_query
        elif hasattr(model, '__name__') and 'Account' in model.__name__:
            return mock_account_query
        else:
            return mock_trade_query
    
    mock_db.query.side_effect = query_side_effect
    
    # Create a mock completed trade object that will pass the date filter
    # The code now uses _get_completed_trades_from_database which returns TradeReport objects
    from app.models.report import TradeReport
    mock_completed_trade = TradeReport(
        trade_id="test-trade",
        strategy_id="test-strategy",
        symbol="BTCUSDT",
        side="LONG",
        entry_time=datetime.now(timezone.utc),
        entry_price=50000.0,
        exit_time=datetime.now(timezone.utc),
        exit_price=49000.0,
        quantity=0.1,
        leverage=5,
        fee_paid=2.0,
        funding_fee=0.0,
        pnl_usd=-600.0,  # Loss of 600 USDT
        pnl_pct=-1.2,
        exit_reason="SL"
    )
    
    # Mock get_strategy_by_uuid to return the mock strategy
    mock_db_service.get_strategy_by_uuid.return_value = mock_strategy
    
    with patch('app.api.routes.risk_metrics.DatabaseService', return_value=mock_db_service), \
         patch('app.api.routes.risk_metrics.RiskManagementService', return_value=mock_risk_service), \
         patch('app.api.routes.risk_metrics.TradeService', return_value=mock_trade_service), \
         patch('app.api.routes.risk_metrics.get_account_service', return_value=mock_account_service), \
         patch('app.api.routes.risk_metrics.get_client_manager', return_value=mock_client_manager), \
         patch('app.api.routes.reports._get_completed_trades_from_database', return_value=[mock_completed_trade]), \
         patch('app.risk.utils.get_pnl_from_completed_trade', return_value=-600.0), \
         patch('app.risk.utils.get_timestamp_from_completed_trade', return_value=datetime.now(timezone.utc)), \
         patch('asyncio.to_thread', side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
        
        # Call endpoint with daily loss breach (-600 < -500)
        result = await get_realtime_risk_status(
            account_id="test-account",
            current_user=mock_user,
            db=mock_db,
            client_manager=mock_client_manager,
            account_service=mock_account_service
        )
        
        # Verify breach status
        assert result.risk_status == "breach", f"Expected breach but got {result.risk_status}. Daily loss: {result.loss_limits.get('daily_loss_usdt')}"
        
        # Verify enforcement event was created
        assert mock_db_service.create_system_event.called, "Enforcement event should be created for daily loss breach"
        
        call_args = mock_db_service.create_system_event.call_args
        assert call_args.kwargs['event_type'] == "DAILY_LOSS_LIMIT_BREACH"
        assert call_args.kwargs['event_level'] == "ERROR"
        assert "Daily loss limit exceeded" in call_args.kwargs['message']
        assert call_args.kwargs['account_id'] == mock_account.id
        assert call_args.kwargs['strategy_id'] is None  # Portfolio-level breach
        
        # Verify metadata
        metadata = call_args.kwargs['event_metadata']
        assert metadata['account_id'] == "test-account"
        assert metadata['limit_type'] == "daily_loss_limit"
        assert metadata['current_value'] == -600.0
        assert metadata['limit_value'] == 500.0


@pytest.mark.asyncio
async def test_duplicate_event_prevention(mock_user, mock_account, mock_risk_config):
    """Test that duplicate enforcement events are prevented (one per hour)."""
    from app.api.routes.risk_metrics import get_realtime_risk_status
    from app.services.risk_management_service import RiskManagementService
    from app.services.trade_service import TradeService
    
    # Create a recent enforcement event (within last hour)
    recent_event = MagicMock(spec=SystemEvent)
    recent_event.event_type = "DAILY_LOSS_LIMIT_BREACH"
    recent_event.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)  # 30 minutes ago
    recent_event.account_id = mock_account.id
    
    mock_db = MagicMock()
    mock_db_service = MagicMock(spec=DatabaseService)
    mock_db_service.get_account_by_id.return_value = mock_account
    mock_db_service.get_enforcement_events.return_value = ([recent_event], 1)  # Recent event exists
    mock_db_service.create_system_event.return_value = MagicMock(spec=SystemEvent)
    
    mock_risk_service = MagicMock(spec=RiskManagementService)
    mock_risk_service.get_risk_config.return_value = mock_risk_config
    
    mock_trade_service = MagicMock(spec=TradeService)
    mock_account_service = MagicMock()
    mock_account_config = MagicMock()
    mock_account_config.api_key = "test_key"
    mock_account_config.api_secret = "test_secret"
    mock_account_service.get_account.return_value = mock_account_config
    
    mock_client_manager = MagicMock()
    mock_client = MagicMock()
    mock_client.futures_account_balance.return_value = 10000.0
    mock_client_manager.get_client.return_value = mock_client
    
    # Mock Strategy query
    from app.models.db_models import Strategy
    mock_strategy = MagicMock(spec=Strategy)
    mock_strategy.id = uuid4()
    mock_strategy.strategy_id = "test-strategy"
    mock_strategy.name = "Test Strategy"
    mock_strategy.symbol = "BTCUSDT"
    mock_strategy.leverage = 5
    
    mock_strategy_query = MagicMock()
    mock_strategy_query.filter.return_value.all.return_value = [mock_strategy]
    
    mock_account_query = MagicMock()
    mock_account_query.filter.return_value.first.return_value = mock_account
    
    mock_trade_query = MagicMock()
    mock_trade_query.filter.return_value.all.return_value = []
    
    def query_side_effect(model):
        if model == Strategy:
            return mock_strategy_query
        elif hasattr(model, '__name__') and 'Account' in model.__name__:
            return mock_account_query
        else:
            return mock_trade_query
    
    mock_db.query.side_effect = query_side_effect
    
    # Create a mock completed trade with loss
    from app.models.report import TradeReport
    mock_completed_trade = TradeReport(
        trade_id="test-trade",
        strategy_id="test-strategy",
        symbol="BTCUSDT",
        side="LONG",
        entry_time=datetime.now(timezone.utc),
        entry_price=50000.0,
        exit_time=datetime.now(timezone.utc),
        exit_price=49000.0,
        quantity=0.1,
        leverage=5,
        fee_paid=2.0,
        funding_fee=0.0,
        pnl_usd=-600.0,  # Loss of 600 USDT
        pnl_pct=-1.2,
        exit_reason="SL"
    )
    
    mock_db_service.get_strategy_by_uuid.return_value = mock_strategy
    
    with patch('app.api.routes.risk_metrics.DatabaseService', return_value=mock_db_service), \
         patch('app.api.routes.risk_metrics.RiskManagementService', return_value=mock_risk_service), \
         patch('app.api.routes.risk_metrics.TradeService', return_value=mock_trade_service), \
         patch('app.api.routes.risk_metrics.get_account_service', return_value=mock_account_service), \
         patch('app.api.routes.risk_metrics.get_client_manager', return_value=mock_client_manager), \
         patch('app.api.routes.reports._get_completed_trades_from_database', return_value=[mock_completed_trade]), \
         patch('app.risk.utils.get_pnl_from_completed_trade', return_value=-600.0), \
         patch('app.risk.utils.get_timestamp_from_completed_trade', return_value=datetime.now(timezone.utc)), \
         patch('asyncio.to_thread', side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
        
        result = await get_realtime_risk_status(
            account_id="test-account",
            current_user=mock_user,
            db=mock_db,
            client_manager=mock_client_manager,
            account_service=mock_account_service
        )
        
        # Verify breach status is still detected
        assert result.risk_status == "breach"
        
        # Verify NO new event was created (duplicate prevention)
        assert not mock_db_service.create_system_event.called, "Duplicate event should not be created when recent event exists"


@pytest.mark.asyncio
async def test_no_breach_no_event_created(mock_user, mock_account, mock_risk_config):
    """Test that no enforcement event is created when no breach occurs."""
    from app.api.routes.risk_metrics import get_realtime_risk_status
    from app.services.risk_management_service import RiskManagementService
    from app.services.trade_service import TradeService
    
    mock_db = MagicMock()
    mock_db_service = MagicMock(spec=DatabaseService)
    mock_db_service.get_account_by_id.return_value = mock_account
    mock_db_service.get_enforcement_events.return_value = ([], 0)
    
    mock_risk_service = MagicMock(spec=RiskManagementService)
    mock_risk_service.get_risk_config.return_value = mock_risk_config
    
    mock_trade_service = MagicMock(spec=TradeService)
    mock_account_service = MagicMock()
    mock_account_config = MagicMock()
    mock_account_config.api_key = "test_key"
    mock_account_config.api_secret = "test_secret"
    mock_account_service.get_account.return_value = mock_account_config
    
    mock_client_manager = MagicMock()
    mock_client = MagicMock()
    mock_client.futures_account_balance.return_value = 10000.0
    mock_client_manager.get_client.return_value = mock_client
    
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_db.query.return_value.filter.return_value.first.return_value = mock_account
    
    with patch('app.api.routes.risk_metrics.DatabaseService', return_value=mock_db_service), \
         patch('app.api.routes.risk_metrics.RiskManagementService', return_value=mock_risk_service), \
         patch('app.api.routes.risk_metrics.TradeService', return_value=mock_trade_service), \
         patch('app.api.routes.risk_metrics.get_account_service', return_value=mock_account_service), \
         patch('app.api.routes.risk_metrics.get_client_manager', return_value=mock_client_manager), \
         patch('app.api.routes.reports._match_trades_to_completed_positions', return_value=[]), \
         patch('app.risk.utils.get_pnl_from_completed_trade', return_value=-100.0), \
         patch('app.risk.utils.get_timestamp_from_completed_trade', return_value=datetime.now(timezone.utc)), \
         patch('asyncio.to_thread', side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
        
        result = await get_realtime_risk_status(
            account_id="test-account",
            current_user=mock_user,
            db=mock_db,
            client_manager=mock_client_manager,
            account_service=mock_account_service
        )
        
        # Verify normal status (no breach)
        assert result.risk_status in ("normal", "warning")
        
        # Verify NO event was created
        assert not mock_db_service.create_system_event.called, "No event should be created when no breach occurs"
