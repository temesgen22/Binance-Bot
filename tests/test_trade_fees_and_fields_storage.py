"""Integration tests for trade fees, funding fees, leverage, and margin_type storage.

Tests verify that:
1. Commission is fetched from Binance user trades and stored in trades table
2. Leverage and margin_type are stored correctly in trades table
3. Funding fees are fetched from Binance API and stored in completed_trades
4. Fee_paid correctly sums entry + exit fees in completed_trades
5. All fields are updated correctly when trades are updated
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.schema import CheckConstraint

from app.models.order import OrderResponse
from app.models.db_models import Trade, Strategy, User, Account, CompletedTrade, Base
from app.services.trade_service import TradeService
from app.services.completed_trade_helper import create_completed_trades_on_position_close
from app.services.completed_trade_service import CompletedTradeService
from app.services.database_service import DatabaseService
from app.core.my_binance_client import BinanceClient

# Test database URL (in-memory SQLite for testing)
TEST_DB_URL = "sqlite:///:memory:"

# Map JSONB to JSON for SQLite compatibility
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler, SQLiteDDLCompiler

if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    def visit_JSONB(self, type_, **kw):
        """Map JSONB to JSON for SQLite compatibility."""
        return "JSON"
    
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True

# Skip PostgreSQL-specific CHECK constraints for SQLite
if not hasattr(SQLiteDDLCompiler, '_visit_check_constraint_patched'):
    original_visit_check_constraint = SQLiteDDLCompiler.visit_check_constraint
    
    def visit_check_constraint(self, constraint, **kw):
        """Skip CHECK constraints with PostgreSQL regex operators for SQLite."""
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
def test_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(TEST_DB_URL, echo=False)
    
    # Remove PostgreSQL-specific CHECK constraints for SQLite
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
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(test_db):
    """Create test user."""
    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def test_account(test_db, test_user):
    """Create test account."""
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="default",
        name="Test Account",
        api_key_encrypted="test_api_key",
        api_secret_encrypted="test_api_secret",
        testnet=True,
        is_active=True,
        is_default=True
    )
    test_db.add(account)
    test_db.commit()
    return account


@pytest.fixture
def test_strategy(test_db, test_user, test_account):
    """Create test strategy."""
    strategy = Strategy(
        id=uuid4(),
        user_id=test_user.id,
        account_id=test_account.id,
        strategy_id="test-strategy-1",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type="scalping",
        leverage=5,
        risk_per_trade=Decimal("0.01"),
        fixed_amount=Decimal("1000.0"),
        max_positions=1,
        params={},
        status="running"
    )
    test_db.add(strategy)
    test_db.commit()
    return strategy


@pytest.fixture
def mock_binance_client():
    """Create mock BinanceClient."""
    client = MagicMock(spec=BinanceClient)
    return client


class TestTradeFeesAndFieldsStorage:
    """Test that commission, leverage, margin_type are stored correctly in trades table."""
    
    def test_commission_fetched_and_stored_in_trades(self, test_db, test_user, test_strategy, mock_binance_client):
        """Test that commission is fetched from user trades and stored in trades table."""
        from app.services.trade_service import TradeService
        from app.services.database_service import DatabaseService
        
        db_service = DatabaseService(test_db)
        trade_service = TradeService(test_db)
        
        # Mock order response with commission fetched from user trades
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.5,
            executed_qty=0.1,
            timestamp=datetime.now(timezone.utc),
            commission=0.02,  # Commission fetched from user trades
            commission_asset="USDT",
            leverage=5,
            margin_type="CROSSED",
            initial_margin=100.0,
            notional_value=5000.05,
            cummulative_quote_qty=5000.05,
            order_type="MARKET"
        )
        
        # Save trade
        db_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order
        )
        
        # Verify commission is stored
        assert db_trade.commission == Decimal("0.02"), "Commission should be stored"
        assert db_trade.commission_asset == "USDT", "Commission asset should be stored"
        assert db_trade.leverage == 5, "Leverage should be stored"
        assert db_trade.margin_type == "CROSSED", "Margin_type should be stored"
        assert db_trade.initial_margin == Decimal("100.0"), "Initial margin should be stored"
        
        # Verify trade is in database
        saved_trade = test_db.query(Trade).filter(Trade.id == db_trade.id).first()
        assert saved_trade is not None
        assert saved_trade.commission == Decimal("0.02")
        assert saved_trade.leverage == 5
        assert saved_trade.margin_type == "CROSSED"
    
    def test_trade_update_includes_commission_leverage_margin_type(self, test_db, test_user, test_strategy):
        """Test that updating an existing trade includes commission, leverage, margin_type."""
        from app.services.trade_service import TradeService
        from app.services.database_service import DatabaseService
        
        db_service = DatabaseService(test_db)
        trade_service = TradeService(test_db)
        
        # Create initial order without commission (as might happen initially)
        initial_order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="NEW",
            side="BUY",
            price=50000.0,
            avg_price=None,
            executed_qty=0.0,
            timestamp=datetime.now(timezone.utc),
            commission=None,  # Not available initially
            leverage=None,
            margin_type=None,
            order_type="MARKET"
        )
        
        # Save initial trade
        db_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=initial_order
        )
        
        # Verify initial state
        assert db_trade.commission is None
        assert db_trade.leverage is None
        assert db_trade.margin_type is None
        
        # Update with filled order (commission now available)
        filled_order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,  # Same order_id
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.5,
            executed_qty=0.1,
            timestamp=datetime.now(timezone.utc),
            commission=0.02,  # Now available
            commission_asset="USDT",
            leverage=5,  # Now available
            margin_type="CROSSED",  # Now available
            initial_margin=100.0,
            notional_value=5000.05,
            order_type="MARKET"
        )
        
        # Update trade
        updated_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=filled_order
        )
        
        # Verify all fields are updated
        assert updated_trade.id == db_trade.id, "Should be same trade"
        assert updated_trade.commission == Decimal("0.02"), "Commission should be updated"
        assert updated_trade.commission_asset == "USDT", "Commission asset should be updated"
        assert updated_trade.leverage == 5, "Leverage should be updated"
        assert updated_trade.margin_type == "CROSSED", "Margin_type should be updated"
        assert updated_trade.initial_margin == Decimal("100.0"), "Initial margin should be updated"
        assert updated_trade.status == "FILLED", "Status should be updated"
        assert updated_trade.executed_qty == Decimal("0.1"), "Executed qty should be updated"
    
    def test_completed_trade_fee_paid_sums_entry_and_exit_fees(self, test_db, test_user, test_strategy, test_account):
        """Test that fee_paid in completed_trades correctly sums entry + exit fees."""
        from app.services.completed_trade_service import CompletedTradeService
        
        # Create entry trade with commission
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1001,
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            price=Decimal("50000.0"),
            avg_price=Decimal("50000.0"),
            executed_qty=Decimal("0.1"),
            commission=Decimal("0.02"),  # Entry fee
            commission_asset="USDT",
            leverage=5,
            margin_type="CROSSED",
            initial_margin=Decimal("100.0"),
            notional_value=Decimal("5000.0"),
            position_side="LONG",
            timestamp=datetime.now(timezone.utc)
        )
        test_db.add(entry_trade)
        test_db.flush()
        
        # Create exit trade with commission
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1002,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=Decimal("51000.0"),
            avg_price=Decimal("51000.0"),
            executed_qty=Decimal("0.1"),
            commission=Decimal("0.0204"),  # Exit fee
            commission_asset="USDT",
            leverage=5,
            margin_type="CROSSED",
            initial_margin=Decimal("100.0"),
            notional_value=Decimal("5100.0"),
            position_side="LONG",
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc)
        )
        test_db.add(exit_trade)
        test_db.flush()
        
        # Create completed trade
        completed_trade_service = CompletedTradeService(test_db)
        completed_trade = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=0.1,
            pnl_usd=100.0 - 0.02 - 0.0204,  # Gross PnL minus fees
            pnl_pct=2.0,
            funding_fee=0.0  # Will be tested separately
        )
        
        # Verify fee_paid is sum of entry + exit fees
        expected_fee = Decimal("0.02") + Decimal("0.0204")
        assert float(completed_trade.fee_paid) == pytest.approx(float(expected_fee), rel=1e-6), \
            f"fee_paid should be sum of entry ({entry_trade.commission}) + exit ({exit_trade.commission}) = {expected_fee}, got {completed_trade.fee_paid}"
    
    @patch('app.services.completed_trade_helper.BinanceClient')
    def test_funding_fee_fetched_and_stored_in_completed_trades(
        self, mock_binance_client_class, test_db, test_user, test_strategy, test_account
    ):
        """Test that funding fees are fetched from Binance API and stored in completed_trades."""
        # Mock BinanceClient
        mock_client = MagicMock()
        mock_binance_client_class.return_value = mock_client
        
        # Mock funding fees response
        mock_client.get_funding_fees.return_value = [
            {
                "symbol": "BTCUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.001",  # Negative = paid (LONG position)
                "asset": "USDT",
                "time": int((datetime.now(timezone.utc).timestamp() - 3600) * 1000)  # 1 hour ago
            },
            {
                "symbol": "BTCUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.0005",  # Another funding fee
                "asset": "USDT",
                "time": int((datetime.now(timezone.utc).timestamp() - 1800) * 1000)  # 30 min ago
            }
        ]
        
        # Create entry trade
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1001,
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            price=Decimal("50000.0"),
            avg_price=Decimal("50000.0"),
            executed_qty=Decimal("0.1"),
            commission=Decimal("0.02"),
            commission_asset="USDT",
            leverage=5,
            margin_type="CROSSED",
            position_side="LONG",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2)
        )
        test_db.add(entry_trade)
        test_db.flush()
        
        # Create exit trade
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1002,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=Decimal("51000.0"),
            avg_price=Decimal("51000.0"),
            executed_qty=Decimal("0.1"),
            commission=Decimal("0.0204"),
            commission_asset="USDT",
            leverage=5,
            margin_type="CROSSED",
            position_side="LONG",
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc)
        )
        test_db.add(exit_trade)
        test_db.flush()
        
        # Create completed trades (this will fetch funding fees)
        completed_trade_ids = create_completed_trades_on_position_close(
            user_id=test_user.id,
            strategy_id=str(test_strategy.id),
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=51000.0,
            position_side="LONG",
            exit_reason="TP",
            db=test_db
        )
        
        # Verify completed trade was created
        assert len(completed_trade_ids) == 1
        
        completed_trade = test_db.query(CompletedTrade).filter(
            CompletedTrade.id == completed_trade_ids[0]
        ).first()
        
        assert completed_trade is not None
        # Verify funding fee is stored (sum of absolute values: 0.001 + 0.0005 = 0.0015)
        expected_funding_fee = 0.001 + 0.0005
        assert float(completed_trade.funding_fee) == pytest.approx(expected_funding_fee, rel=1e-6), \
            f"Funding fee should be {expected_funding_fee}, got {completed_trade.funding_fee}"
        
        # Verify fee_paid is sum of entry + exit fees
        expected_fee_paid = float(entry_trade.commission) + float(exit_trade.commission)
        assert float(completed_trade.fee_paid) == pytest.approx(expected_fee_paid, rel=1e-6), \
            f"fee_paid should be {expected_fee_paid}, got {completed_trade.fee_paid}"
    
    def test_leverage_and_margin_type_fallback_to_strategy(self, test_db, test_user, test_strategy):
        """Test that leverage and margin_type use strategy as fallback in completed_trades."""
        from app.services.completed_trade_service import CompletedTradeService
        
        # Create entry trade without leverage/margin_type
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1001,
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            price=Decimal("50000.0"),
            avg_price=Decimal("50000.0"),
            executed_qty=Decimal("0.1"),
            commission=Decimal("0.02"),
            leverage=None,  # Missing
            margin_type=None,  # Missing
            position_side="LONG",
            timestamp=datetime.now(timezone.utc)
        )
        test_db.add(entry_trade)
        test_db.flush()
        
        # Create exit trade without leverage/margin_type
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1002,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=Decimal("51000.0"),
            avg_price=Decimal("51000.0"),
            executed_qty=Decimal("0.1"),
            commission=Decimal("0.0204"),
            leverage=None,  # Missing
            margin_type=None,  # Missing
            position_side="LONG",
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc)
        )
        test_db.add(exit_trade)
        test_db.flush()
        
        # Create completed trade
        completed_trade_service = CompletedTradeService(test_db)
        completed_trade = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=0.1,
            pnl_usd=100.0,
            pnl_pct=2.0,
            funding_fee=0.0
        )
        
        # Verify leverage uses strategy fallback
        assert completed_trade.leverage == test_strategy.leverage, \
            f"Leverage should use strategy fallback ({test_strategy.leverage}), got {completed_trade.leverage}"
        
        # Verify margin_type uses default fallback (CROSSED)
        assert completed_trade.margin_type == "CROSSED", \
            f"Margin_type should default to CROSSED, got {completed_trade.margin_type}"
    
    def test_all_fields_stored_in_trades_table(self, test_db, test_user, test_strategy):
        """Test that all relevant fields are stored in trades table."""
        from app.services.trade_service import TradeService
        
        trade_service = TradeService(test_db)
        
        # Create order with all fields
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.5,
            executed_qty=0.1,
            orig_qty=0.1,
            timestamp=datetime.now(timezone.utc),
            commission=0.02,
            commission_asset="USDT",
            leverage=5,
            margin_type="CROSSED",
            initial_margin=100.0,
            notional_value=5000.05,
            cummulative_quote_qty=5000.05,
            position_side="LONG",
            order_type="MARKET",
            time_in_force="GTC",
            working_type="CONTRACT_PRICE",
            stop_price=None
        )
        
        # Save trade
        db_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order
        )
        
        # Verify all fields are stored
        assert db_trade.commission == Decimal("0.02")
        assert db_trade.commission_asset == "USDT"
        assert db_trade.leverage == 5
        assert db_trade.margin_type == "CROSSED"
        assert db_trade.initial_margin == Decimal("100.0")
        assert db_trade.notional_value == Decimal("5000.05")
        assert db_trade.cummulative_quote_qty == Decimal("5000.05")
        assert db_trade.position_side == "LONG"
        assert db_trade.order_type == "MARKET"
        assert db_trade.time_in_force == "GTC"
        assert db_trade.working_type == "CONTRACT_PRICE"
    
    def test_partial_fill_fee_calculation(self, test_db, test_user, test_strategy):
        """Test that fees are calculated proportionally for partial fills."""
        from app.services.completed_trade_service import CompletedTradeService
        
        # Create entry trade with 0.2 executed, commission 0.04
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1001,
            symbol="BTCUSDT",
            side="BUY",
            status="PARTIALLY_FILLED",
            price=Decimal("50000.0"),
            avg_price=Decimal("50000.0"),
            executed_qty=Decimal("0.2"),  # 0.2 BTC
            commission=Decimal("0.04"),  # Total commission for 0.2 BTC
            commission_asset="USDT",
            leverage=5,
            margin_type="CROSSED",
            position_side="LONG",
            timestamp=datetime.now(timezone.utc)
        )
        test_db.add(entry_trade)
        test_db.flush()
        
        # Create exit trade closing 0.1 BTC (half of entry)
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=1002,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=Decimal("51000.0"),
            avg_price=Decimal("51000.0"),
            executed_qty=Decimal("0.1"),  # Closing 0.1 BTC
            commission=Decimal("0.0204"),  # Commission for 0.1 BTC
            commission_asset="USDT",
            leverage=5,
            margin_type="CROSSED",
            position_side="LONG",
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc)
        )
        test_db.add(exit_trade)
        test_db.flush()
        
        # Create completed trade for 0.1 BTC (half of entry)
        completed_trade_service = CompletedTradeService(test_db)
        completed_trade = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=0.1,  # Half of entry
            pnl_usd=100.0,
            pnl_pct=2.0,
            funding_fee=0.0
        )
        
        # Verify fee_paid is proportional: entry_fee (0.04 * 0.1/0.2 = 0.02) + exit_fee (0.0204)
        expected_entry_fee_portion = float(entry_trade.commission) * (0.1 / 0.2)  # 0.02
        expected_exit_fee = float(exit_trade.commission)  # 0.0204
        expected_total_fee = expected_entry_fee_portion + expected_exit_fee  # 0.0404
        
        assert float(completed_trade.fee_paid) == pytest.approx(expected_total_fee, rel=1e-6), \
            f"fee_paid should be proportional: entry_fee_portion ({expected_entry_fee_portion}) + exit_fee ({expected_exit_fee}) = {expected_total_fee}, got {completed_trade.fee_paid}"

