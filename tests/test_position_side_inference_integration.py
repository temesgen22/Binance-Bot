"""Comprehensive integration tests for position_side inference and column population.

Tests the complete flow from order execution to database storage,
ensuring position_side and other columns are correctly inferred and populated.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.schema import CheckConstraint

from app.models.order import OrderResponse
from app.models.db_models import Trade, Strategy, User, Account, Base
from app.services.trade_service import TradeService
from app.services.database_service import DatabaseService

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
        account_id="test_account",
        name="Test Account",
        api_key_encrypted="test_key",
        api_secret_encrypted="test_secret",
        testnet=True,
        is_active=True
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
        status="running",
        leverage=5,
        risk_per_trade=0.01,
        fixed_amount=1000.0,
        max_positions=1,
    )
    test_db.add(strategy)
    test_db.commit()
    return strategy


@pytest.fixture
def trade_service(test_db):
    """Create TradeService instance."""
    return TradeService(db=test_db, redis_storage=None)


class TestPositionSideInferenceIntegration:
    """Comprehensive integration tests for position_side inference."""
    
    def test_complete_long_trade_cycle(self, trade_service, test_user, test_strategy):
        """Test complete LONG trade cycle: BUY (open) -> SELL (close with exit_reason)."""
        # Step 1: Open LONG position with BUY order (no position_side, no exit_reason)
        buy_order = OrderResponse(
            symbol="BTCUSDT",
            order_id=3001,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=None,  # Missing - should be inferred from price
            executed_qty=0.1,
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            position_side=None,  # Missing - should be inferred
            order_type=None,  # Missing - should default to MARKET
            notional_value=None,  # Missing - should be calculated
            cummulative_quote_qty=None,  # Missing - should be calculated
            exit_reason=None,  # No exit reason = opening position
        )
        
        buy_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=buy_order
        )
        
        # Verify position_side inferred as LONG (BUY opens LONG)
        assert buy_trade.position_side == "LONG"
        # Verify avg_price inferred from price
        assert float(buy_trade.avg_price) == 50000.0
        # Verify notional_value calculated
        assert float(buy_trade.notional_value) == 5000.0  # 0.1 * 50000
        # Verify cummulative_quote_qty calculated
        assert float(buy_trade.cummulative_quote_qty) == 5000.0
        # Verify order_type defaulted
        assert buy_trade.order_type == "MARKET"
        
        # Step 2: Close LONG position with SELL order (exit_reason present)
        sell_order = OrderResponse(
            symbol="BTCUSDT",
            order_id=3002,
            status="FILLED",
            side="SELL",
            price=51000.0,
            avg_price=51000.5,  # Provided
            executed_qty=0.1,
            timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            position_side=None,  # Missing - should be inferred
            order_type="MARKET",
            notional_value=None,  # Missing - should be calculated
            cummulative_quote_qty=None,  # Missing - should be calculated
            exit_reason="TAKE_PROFIT",  # Exit reason = closing position
        )
        
        sell_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=sell_order
        )
        
        # Verify position_side inferred as LONG (SELL closes LONG when exit_reason present)
        assert sell_trade.position_side == "LONG"
        # Verify notional_value calculated
        assert float(sell_trade.notional_value) == 5100.05  # 0.1 * 51000.5
        # Verify cummulative_quote_qty calculated
        assert float(sell_trade.cummulative_quote_qty) == 5100.05
        # Verify exit_reason preserved
        assert sell_trade.exit_reason == "TAKE_PROFIT"
    
    def test_complete_short_trade_cycle(self, trade_service, test_user, test_strategy):
        """Test complete SHORT trade cycle: SELL (open) -> BUY (close with exit_reason)."""
        # Step 1: Open SHORT position with SELL order
        sell_order = OrderResponse(
            symbol="ETHUSDT",
            order_id=3003,
            status="FILLED",
            side="SELL",
            price=3000.0,
            avg_price=3000.5,
            executed_qty=1.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            position_side=None,  # Missing - should be inferred
            exit_reason=None,  # No exit reason = opening position
        )
        
        sell_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=sell_order
        )
        
        # Verify position_side inferred as SHORT (SELL opens SHORT)
        assert sell_trade.position_side == "SHORT"
        
        # Step 2: Close SHORT position with BUY order
        buy_order = OrderResponse(
            symbol="ETHUSDT",
            order_id=3004,
            status="FILLED",
            side="BUY",
            price=2900.0,
            avg_price=2900.5,
            executed_qty=1.0,
            timestamp=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
            position_side=None,  # Missing - should be inferred
            exit_reason="STOP_LOSS",  # Exit reason = closing position
        )
        
        buy_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=buy_order
        )
        
        # Verify position_side inferred as SHORT (BUY closes SHORT when exit_reason present)
        assert buy_trade.position_side == "SHORT"
        assert buy_trade.exit_reason == "STOP_LOSS"
    
    def test_position_side_preserved_from_binance_hedge_mode(self, trade_service, test_user, test_strategy):
        """Test that position_side from Binance (hedge mode) is preserved."""
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=3005,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
            position_side="LONG",  # Provided by Binance (hedge mode)
            exit_reason=None,
        )
        
        trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order
        )
        
        # Verify position_side preserved from Binance
        assert trade.position_side == "LONG"
    
    def test_all_columns_populated_when_missing(self, trade_service, test_user, test_strategy):
        """Test that all useful columns are populated when missing."""
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=3006,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=None,  # Missing
            executed_qty=0.1,
            timestamp=datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
            position_side=None,  # Missing
            order_type=None,  # Missing
            time_in_force=None,  # Missing
            notional_value=None,  # Missing
            cummulative_quote_qty=None,  # Missing
            exit_reason=None,
        )
        
        trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order
        )
        
        # Verify all columns populated
        assert trade.position_side == "LONG"  # Inferred
        assert float(trade.avg_price) == 50000.0  # Inferred from price
        assert trade.order_type == "MARKET"  # Defaulted
        assert float(trade.notional_value) == 5000.0  # Calculated
        assert float(trade.cummulative_quote_qty) == 5000.0  # Calculated
        # time_in_force should be None for MARKET orders (only set for LIMIT)
        assert trade.time_in_force is None
    
    def test_update_existing_trade_with_missing_fields(self, trade_service, test_user, test_strategy):
        """Test that updating existing trade populates missing fields."""
        # Create initial trade with missing position_side
        order1 = OrderResponse(
            symbol="BTCUSDT",
            order_id=3007,
            status="PARTIALLY_FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.05,  # Partial fill
            timestamp=datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc),
            position_side=None,  # Missing
            exit_reason=None,
        )
        
        trade1 = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order1
        )
        
        # Verify position_side inferred
        assert trade1.position_side == "LONG"
        
        # Update with full fill
        order2 = OrderResponse(
            symbol="BTCUSDT",
            order_id=3007,  # Same order_id
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50010.0,  # Updated avg_price
            executed_qty=0.1,  # Full fill
            timestamp=datetime(2024, 1, 1, 16, 1, 0, tzinfo=timezone.utc),
            position_side=None,  # Still missing
            exit_reason=None,
        )
        
        trade2 = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=order2
        )
        
        # Verify it's the same trade (updated)
        assert trade2.id == trade1.id
        # Verify position_side still inferred (not lost)
        assert trade2.position_side == "LONG"
        # Verify avg_price updated
        assert float(trade2.avg_price) == 50010.0
        # Verify executed_qty updated
        assert float(trade2.executed_qty) == 0.1
    
    def test_multiple_strategies_same_symbol(self, trade_service, test_user, test_account, test_db):
        """Test that position_side inference works correctly for multiple strategies on same symbol."""
        # Create two strategies for same symbol
        strategy1 = Strategy(
            id=uuid4(),
            user_id=test_user.id,
            account_id=test_account.id,
            strategy_id="strategy-1",
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type="scalping",
            status="running",
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
        )
        strategy2 = Strategy(
            id=uuid4(),
            user_id=test_user.id,
            account_id=test_account.id,
            strategy_id="strategy-2",
            name="Strategy 2",
            symbol="BTCUSDT",
            strategy_type="scalping",
            status="running",
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
        )
        test_db.add(strategy1)
        test_db.add(strategy2)
        test_db.commit()
        
        # Strategy 1: BUY order (should infer LONG)
        order1 = OrderResponse(
            symbol="BTCUSDT",
            order_id=3008,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=datetime(2024, 1, 1, 17, 0, 0, tzinfo=timezone.utc),
            position_side=None,
            exit_reason=None,
        )
        
        trade1 = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=strategy1.id,
            order=order1
        )
        assert trade1.position_side == "LONG"
        
        # Strategy 2: SELL order (should infer SHORT)
        order2 = OrderResponse(
            symbol="BTCUSDT",
            order_id=3009,
            status="FILLED",
            side="SELL",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=datetime(2024, 1, 1, 17, 1, 0, tzinfo=timezone.utc),
            position_side=None,
            exit_reason=None,
        )
        
        trade2 = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=strategy2.id,
            order=order2
        )
        assert trade2.position_side == "SHORT"
        
        # Verify both trades stored correctly
        assert trade1.strategy_id == strategy1.id
        assert trade2.strategy_id == strategy2.id
        assert trade1.position_side != trade2.position_side  # Different positions

