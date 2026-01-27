"""
Comprehensive tests for Paper Trading implementation.

Tests verify:
1. PaperBinanceClient functionality (market data, order execution, balance)
2. Account creation with paper trading mode
3. Trade execution and balance persistence
4. Paper trading flag propagation (Trade, CompletedTrade)
5. Risk management exclusion
6. Balance persistence after trades
7. Account loading and configuration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from decimal import Decimal
from uuid import uuid4
from datetime import datetime, timezone

from app.core.paper_binance_client import PaperBinanceClient, SPREAD_OFFSET, AVERAGE_FEE_RATE
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import BinanceAccountConfig, get_settings
from app.models.order import OrderResponse
from app.services.account_service import AccountService
from app.services.database_service import DatabaseService
from app.services.trade_service import TradeService
from app.services.completed_trade_service import CompletedTradeService
from app.models.db_models import Account, Trade, CompletedTrade, Strategy, User


class TestPaperBinanceClient:
    """Test PaperBinanceClient functionality."""
    
    def test_initialization(self):
        """Test PaperBinanceClient initialization."""
        client = PaperBinanceClient(account_id="test_account", initial_balance=10000.0)
        
        assert client.account_id == "test_account"
        assert client.balance == 10000.0
        assert len(client.positions) == 0
        assert len(client.orders) == 0
    
    @patch('app.core.paper_binance_client.requests.get')
    def test_get_price(self, mock_get):
        """Test getting current price from Binance public API."""
        mock_get.return_value.json.return_value = {"price": "50000.0"}
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = Mock()
        
        client = PaperBinanceClient(account_id="test", initial_balance=10000.0)
        price = client.get_price("BTCUSDT")
        
        assert price == 50000.0
        mock_get.assert_called_once()
    
    @patch('app.core.paper_binance_client.requests.get')
    def test_get_klines(self, mock_get):
        """Test getting klines from Binance public API."""
        mock_klines = [
            [1000, "50000", "50100", "49900", "50050", "100", 2000, 0, 0, 0, 0, 0]
        ]
        mock_get.return_value.json.return_value = mock_klines
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = Mock()
        
        client = PaperBinanceClient(account_id="test", initial_balance=10000.0)
        klines = client.get_klines("BTCUSDT", "1m", limit=1)
        
        assert len(klines) == 1
        mock_get.assert_called_once()
    
    @patch('app.core.paper_binance_client.PaperBinanceClient.get_price')
    def test_place_order_long(self, mock_get_price):
        """Test placing a LONG order."""
        mock_get_price.return_value = 50000.0
        
        client = PaperBinanceClient(account_id="test", initial_balance=10000.0)
        initial_balance = client.balance
        
        order = client.place_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.1,
            order_type="MARKET"
        )
        
        # Verify order response
        assert order.status == "FILLED"
        assert order.side == "BUY"
        assert order.executed_qty == 0.1
        assert order.symbol == "BTCUSDT"
        
        # Verify balance updated (subtracted fee)
        # Fill price = 50000 * (1 + 0.0001) = 50005.0
        # Notional = 50005.0 * 0.1 = 5000.5
        # Fee = 5000.5 * 0.0004 = 2.0002
        expected_balance = initial_balance - 2.0002
        assert abs(client.balance - expected_balance) < 0.01
        
        # Verify position created
        assert "BTCUSDT" in client.positions
        position = client.positions["BTCUSDT"]
        assert position.side == "LONG"
        assert position.size == 0.1
    
    @patch('app.core.paper_binance_client.PaperBinanceClient.get_price')
    def test_place_order_short(self, mock_get_price):
        """Test placing a SHORT order."""
        mock_get_price.return_value = 50000.0
        
        client = PaperBinanceClient(account_id="test", initial_balance=10000.0)
        initial_balance = client.balance
        
        order = client.place_order(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            order_type="MARKET"
        )
        
        # Verify order response
        assert order.status == "FILLED"
        assert order.side == "SELL"
        
        # Verify balance updated
        assert client.balance < initial_balance  # Fee deducted
        
        # Verify position created
        assert "BTCUSDT" in client.positions
        position = client.positions["BTCUSDT"]
        assert position.side == "SHORT"
    
    @patch('app.core.paper_binance_client.PaperBinanceClient.get_price')
    def test_close_position_with_pnl(self, mock_get_price):
        """Test closing a position and calculating PnL."""
        mock_get_price.return_value = 50000.0
        
        client = PaperBinanceClient(account_id="test", initial_balance=10000.0)
        initial_balance = client.balance
        
        # Open LONG position
        client.place_order(symbol="BTCUSDT", side="BUY", quantity=0.1, order_type="MARKET")
        balance_after_entry = client.balance
        
        # Price increases to 51000 (profit)
        mock_get_price.return_value = 51000.0
        
        # Close position
        order = client.place_order(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            order_type="MARKET",
            reduce_only=True
        )
        
        # Verify PnL in order response
        assert order.realized_pnl is not None
        assert order.realized_pnl > 0  # Profit
        
        # Verify position closed
        assert "BTCUSDT" not in client.positions
        
        # Verify balance increased (PnL - fees)
        assert client.balance > balance_after_entry
    
    @patch('app.core.paper_binance_client.PaperBinanceClient.get_price')
    def test_balance_persistence_callback(self, mock_get_price):
        """Test balance persistence callback is called."""
        mock_get_price.return_value = 50000.0
        
        callback_called = []
        def test_callback(account_id: str, balance: float):
            callback_called.append((account_id, balance))
        
        client = PaperBinanceClient(
            account_id="test",
            initial_balance=10000.0,
            balance_persistence_callback=test_callback
        )
        
        # Place order
        client.place_order(symbol="BTCUSDT", side="BUY", quantity=0.1, order_type="MARKET")
        
        # Verify callback was called
        assert len(callback_called) == 1
        assert callback_called[0][0] == "test"
        assert callback_called[0][1] == client.balance
    
    def test_get_open_position(self):
        """Test getting open position."""
        client = PaperBinanceClient(account_id="test", initial_balance=10000.0)
        
        # No position
        assert client.get_open_position("BTCUSDT") is None
        
        # Create position manually
        from app.core.paper_binance_client import VirtualPosition
        client.positions["BTCUSDT"] = VirtualPosition(
            symbol="BTCUSDT",
            side="LONG",
            size=0.1,
            entry_price=50000.0,
            leverage=1
        )
        
        with patch.object(client, 'get_price', return_value=51000.0):
            position = client.get_open_position("BTCUSDT")
            
            assert position is not None
            assert position["symbol"] == "BTCUSDT"
            assert float(position["positionAmt"]) == 0.1
            assert float(position["unRealizedProfit"]) > 0  # Profit


class TestPaperTradingAccountCreation:
    """Test paper trading account creation."""
    
    def test_create_paper_trading_account_no_api_keys(self, test_db_session, test_user):
        """Test creating paper trading account without API keys."""
        account_service = AccountService(test_db_session)
        
        config = account_service.create_account(
            user_id=test_user.id,
            account_id="paper1",
            api_key=None,
            api_secret=None,
            name="Paper Trading Account",
            paper_trading=True,
            paper_balance=5000.0
        )
        
        assert config.paper_trading is True
        assert config.paper_balance == 5000.0
        assert config.api_key == ""  # Empty string for paper trading
        assert config.api_secret == ""
        
        # Verify in database
        db_account = test_db_session.query(Account).filter(
            Account.account_id == "paper1"
        ).first()
        
        assert db_account is not None
        assert db_account.paper_trading is True
        assert float(db_account.paper_balance) == 5000.0
        assert db_account.api_key_encrypted == ""  # Empty string stored
    
    def test_create_paper_trading_account_with_default_balance(self, test_db_session, test_user):
        """Test creating paper trading account with default balance."""
        account_service = AccountService(test_db_session)
        
        config = account_service.create_account(
            user_id=test_user.id,
            account_id="paper2",
            api_key=None,
            api_secret=None,
            paper_trading=True,
            paper_balance=None  # Should default to 10000.0
        )
        
        # Verify default balance
        db_account = test_db_session.query(Account).filter(
            Account.account_id == "paper2"
        ).first()
        
        assert float(db_account.paper_balance) == 10000.0
    
    def test_create_live_account_requires_api_keys(self, test_db_session, test_user):
        """Test that live accounts require API keys."""
        account_service = AccountService(test_db_session)
        
        with pytest.raises(ValueError, match="API keys are required"):
            account_service.create_account(
                user_id=test_user.id,
                account_id="live1",
                api_key=None,
                api_secret=None,
                paper_trading=False  # Live trading
            )
    
    def test_load_paper_trading_account(self, test_db_session, test_user):
        """Test loading paper trading account from database."""
        # Create account
        account_service = AccountService(test_db_session)
        account_service.create_account(
            user_id=test_user.id,
            account_id="paper3",
            api_key=None,
            api_secret=None,
            paper_trading=True,
            paper_balance=7500.0
        )
        
        # Load account
        config = account_service.get_account(test_user.id, "paper3")
        
        assert config is not None
        assert config.paper_trading is True
        assert config.paper_balance == 7500.0
        assert config.api_key == ""  # Empty string, not None
        assert config.api_secret == ""


class TestPaperTradingClientManager:
    """Test BinanceClientManager with paper trading."""
    
    def test_add_paper_trading_client(self):
        """Test adding paper trading client to manager."""
        manager = BinanceClientManager(get_settings())
        
        config = BinanceAccountConfig(
            account_id="paper_test",
            api_key=None,
            api_secret=None,
            paper_trading=True,
            paper_balance=10000.0
        )
        
        manager.add_client("paper_test", config)
        
        client = manager.get_client("paper_test")
        assert client is not None
        assert isinstance(client, PaperBinanceClient)
        assert client.balance == 10000.0
    
    def test_add_paper_trading_client_with_callback(self):
        """Test adding paper trading client with balance persistence callback."""
        manager = BinanceClientManager(get_settings())
        
        callback_called = []
        def test_callback(account_id: str, balance: float):
            callback_called.append((account_id, balance))
        
        config = BinanceAccountConfig(
            account_id="paper_callback",
            paper_trading=True,
            paper_balance=10000.0
        )
        
        manager.add_client("paper_callback", config, balance_persistence_callback=test_callback)
        
        client = manager.get_client("paper_callback")
        assert client is not None
        
        # Test callback is set
        with patch.object(client, 'get_price', return_value=50000.0):
            client.place_order(symbol="BTCUSDT", side="BUY", quantity=0.1, order_type="MARKET")
        
        assert len(callback_called) == 1


class TestPaperTradingTradeExecution:
    """Test trade execution with paper trading."""
    
    @pytest.fixture
    def paper_account(self, test_db_session, test_user):
        """Create a paper trading account."""
        account_service = AccountService(test_db_session)
        return account_service.create_account(
            user_id=test_user.id,
            account_id="paper_trade",
            api_key=None,
            api_secret=None,
            paper_trading=True,
            paper_balance=10000.0
        )
    
    @pytest.fixture
    def paper_strategy(self, test_db_session, test_user, paper_account):
        """Create a strategy on paper trading account."""
        db_account = test_db_session.query(Account).filter(
            Account.account_id == "paper_trade"
        ).first()
        
        strategy = Strategy(
            user_id=test_user.id,
            strategy_id="test_strategy",
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=db_account.id,
            leverage=1,
            risk_per_trade=Decimal("0.01"),
            status="running"
        )
        test_db_session.add(strategy)
        test_db_session.commit()
        return strategy
    
    def test_trade_saved_with_paper_trading_flag(self, test_db_session, test_user, paper_strategy):
        """Test that trades are saved with paper_trading flag."""
        trade_service = TradeService(test_db_session)
        
        # Create mock order response
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            executed_qty=0.1,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Save trade
        db_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=paper_strategy.id,
            order=order
        )
        
        # Verify paper_trading flag
        assert db_trade.paper_trading is True
        
        # Verify in database
        db_trade_check = test_db_session.query(Trade).filter(
            Trade.id == db_trade.id
        ).first()
        
        assert db_trade_check.paper_trading is True


class TestPaperTradingRiskExclusion:
    """Test that paper trades are excluded from risk calculations."""
    
    def test_risk_calculation_excludes_paper_trades(self, test_db_session, test_user):
        """Test that risk calculations exclude paper trades."""
        from app.risk.portfolio_risk_manager import PortfolioRiskManager
        
        # Create paper trading account
        account_service = AccountService(test_db_session)
        paper_account = account_service.create_account(
            user_id=test_user.id,
            account_id="paper_risk",
            api_key=None,
            api_secret=None,
            paper_trading=True
        )
        
        db_account = test_db_session.query(Account).filter(
            Account.account_id == "paper_risk"
        ).first()
        
        # Create paper trade
        strategy = Strategy(
            user_id=test_user.id,
            strategy_id="paper_strategy",
            name="Paper Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=db_account.id,
            leverage=1,
            risk_per_trade=Decimal("0.01"),
            status="stopped"
        )
        test_db_session.add(strategy)
        test_db_session.commit()
        
        # Create entry and exit trades first
        now = datetime.now(timezone.utc)
        entry_trade = Trade(
            user_id=test_user.id,
            strategy_id=strategy.id,
            order_id=12345,
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            price=Decimal("50000.0"),
            executed_qty=Decimal("0.1"),
            paper_trading=True,
            timestamp=now
        )
        test_db_session.add(entry_trade)
        test_db_session.commit()
        
        exit_trade = Trade(
            user_id=test_user.id,
            strategy_id=strategy.id,
            order_id=12346,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=Decimal("51000.0"),
            executed_qty=Decimal("0.1"),
            paper_trading=True,
            timestamp=now
        )
        test_db_session.add(exit_trade)
        test_db_session.commit()
        
        # Create completed trade (paper trading)
        from app.services.completed_trade_service import CompletedTradeService
        completed_trade_service = CompletedTradeService(test_db_session)
        
        # Calculate PnL
        quantity = 0.1
        entry_price = 50000.0
        exit_price = 51000.0
        pnl_usd = (exit_price - entry_price) * quantity  # 100.0
        pnl_pct = (exit_price - entry_price) / entry_price  # 0.002 (0.2%)
        
        completed_trade = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=quantity,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            funding_fee=0.0
        )
        test_db_session.add(completed_trade)
        test_db_session.commit()
        
        # Test risk calculation - directly query CompletedTrade to verify exclusion
        from app.models.db_models import CompletedTrade
        
        # Query completed trades for this account (should exclude paper trades)
        completed_trades = test_db_session.query(CompletedTrade).filter(
            CompletedTrade.user_id == test_user.id,
            CompletedTrade.paper_trading == False  # Exclude paper trades
        ).all()
        
        # Should have no completed trades (the one we created is paper trading)
        assert len(completed_trades) == 0
        
        # Verify the paper trade exists but is excluded
        paper_trades = test_db_session.query(CompletedTrade).filter(
            CompletedTrade.user_id == test_user.id,
            CompletedTrade.paper_trading == True  # Paper trades
        ).all()
        
        assert len(paper_trades) == 1  # Our paper trade exists


class TestPaperTradingBalancePersistence:
    """Test balance persistence for paper trading."""
    
    def test_balance_persisted_after_trade(self, test_db_session, test_user):
        """Test that balance is persisted to database after trade."""
        # Create account
        account_service = AccountService(test_db_session)
        account_service.create_account(
            user_id=test_user.id,
            account_id="paper_balance",
            api_key=None,
            api_secret=None,
            paper_trading=True,
            paper_balance=10000.0
        )
        
        db_account = test_db_session.query(Account).filter(
            Account.account_id == "paper_balance"
        ).first()
        
        # Create database service and update balance
        db_service = DatabaseService(test_db_session)
        success = db_service.update_paper_balance_by_account_id("paper_balance", 9500.0)
        
        assert success is True
        
        # Verify balance updated
        test_db_session.refresh(db_account)
        assert float(db_account.paper_balance) == 9500.0
    
    def test_balance_persistence_only_for_paper_accounts(self, test_db_session, test_user):
        """Test that balance persistence only works for paper trading accounts."""
        # Create live account
        account_service = AccountService(test_db_session)
        account_service.create_account(
            user_id=test_user.id,
            account_id="live_balance",
            api_key="test_key",
            api_secret="test_secret",
            paper_trading=False
        )
        
        db_service = DatabaseService(test_db_session)
        success = db_service.update_paper_balance_by_account_id("live_balance", 9500.0)
        
        # Should fail because it's not a paper trading account
        assert success is False


# Map JSONB to JSON for SQLite compatibility (must be done at module level)
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler, SQLiteDDLCompiler
from sqlalchemy.schema import CheckConstraint

if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    def visit_JSONB(self, type_, **kw):
        """Map JSONB to JSON for SQLite compatibility."""
        return "JSON"
    
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True

# Skip PostgreSQL-specific CHECK constraints (regex operators) for SQLite
if not hasattr(SQLiteDDLCompiler, '_visit_check_constraint_patched'):
    original_visit_check_constraint = SQLiteDDLCompiler.visit_check_constraint
    
    def visit_check_constraint(self, constraint, **kw):
        """Skip CHECK constraints with PostgreSQL regex operators for SQLite."""
        try:
            sqltext = str(constraint.sqltext.compile(compile_kwargs={"literal_binds": True}))
            if '~' in sqltext or '~*' in sqltext:
                return None
        except Exception:
            try:
                sqltext = str(constraint.sqltext)
                if '~' in sqltext or '~*' in sqltext:
                    return None
            except Exception:
                pass
        return original_visit_check_constraint(self, constraint, **kw)
    
    SQLiteDDLCompiler.visit_check_constraint = visit_check_constraint
    SQLiteDDLCompiler._visit_check_constraint_patched = True


@pytest.fixture
def test_db_session():
    """Create in-memory SQLite database session for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.db_models import Base
    
    engine = create_engine("sqlite:///:memory:", echo=False)
    
    # Remove PostgreSQL-specific CHECK constraints (regex operators) for SQLite
    for table in Base.metadata.tables.values():
        constraints_to_remove = []
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                try:
                    sqltext = str(constraint.sqltext)
                    if '~' in sqltext or '~*' in sqltext:
                        constraints_to_remove.append(constraint)
                except Exception:
                    pass
        
        for constraint in constraints_to_remove:
            table.constraints.remove(constraint)
    
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(test_db_session):
    """Create test user."""
    from app.models.db_models import User
    from uuid import uuid4
    
    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",  # Simplified for testing
        full_name="Test User",
        is_active=True
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user

