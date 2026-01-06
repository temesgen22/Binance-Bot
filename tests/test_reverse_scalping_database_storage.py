"""
Verification that reverse_scalping strategy orders are stored in the database.

This script checks:
1. Database schema allows reverse_scalping as strategy_type
2. No filters prevent reverse_scalping orders from being saved
3. TradeService and DatabaseService don't filter by strategy_type
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.schema import CheckConstraint

from app.models.db_models import Strategy, Trade, Backtest, Base
from app.services.database_service import DatabaseService

# Test database URL (in-memory SQLite for testing)
TEST_DB_URL = "sqlite:///:memory:"

# Map JSONB to JSON for SQLite compatibility
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler, SQLiteDDLCompiler

if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    def visit_JSONB(self, type_, **kw):
        return "JSON"
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True

# Skip PostgreSQL-specific CHECK constraints for SQLite
if not hasattr(SQLiteDDLCompiler, '_visit_check_constraint_patched'):
    original_visit_check_constraint = SQLiteDDLCompiler.visit_check_constraint
    def visit_check_constraint(self, constraint, **kw):
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


def test_strategy_type_no_constraints(test_db):
    """Verify that strategy_type column has no constraints that would exclude reverse_scalping."""
    # Check Strategy table
    strategy_table = Strategy.__table__
    strategy_type_col = strategy_table.c.strategy_type
    
    # Verify it's a String column (not an Enum with limited values)
    assert strategy_type_col.type.python_type == str
    
    # Check for any CHECK constraints on strategy_type
    strategy_constraints = [c for c in strategy_table.constraints 
                           if isinstance(c, CheckConstraint) and 'strategy_type' in str(c.sqltext)]
    assert len(strategy_constraints) == 0, "No CHECK constraints should limit strategy_type values"
    
    # Check Backtest table
    backtest_table = Backtest.__table__
    backtest_type_col = backtest_table.c.strategy_type
    assert backtest_type_col.type.python_type == str
    
    backtest_constraints = [c for c in backtest_table.constraints 
                           if isinstance(c, CheckConstraint) and 'strategy_type' in str(c.sqltext)]
    assert len(backtest_constraints) == 0, "No CHECK constraints should limit strategy_type values"


def test_reverse_scalping_strategy_creation(test_db):
    """Test that a strategy with reverse_scalping type can be created."""
    db_service = DatabaseService(test_db)
    
    user_id = uuid4()
    account_id = uuid4()
    
    # Create account first
    from app.models.db_models import Account, User
    user = User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        password_hash="hash",
        is_active=True
    )
    test_db.add(user)
    
    account = Account(
        id=account_id,
        user_id=user_id,
        account_id="test_account",
        name="Test Account",
        exchange_platform="binance",
        api_key_encrypted="test_key",
        api_secret_encrypted="test_secret",
        testnet=True,
        is_active=True,
        is_default=True
    )
    test_db.add(account)
    test_db.commit()
    
    # Create strategy with reverse_scalping type
    strategy = db_service.create_strategy(
        user_id=user_id,
        strategy_id="test_reverse_scalping",
        name="Test Reverse Scalping",
        symbol="BTCUSDT",
        strategy_type="reverse_scalping",
        account_id=account_id,
        leverage=10,
        risk_per_trade=0.02,
        params={"ema_fast": 8, "ema_slow": 21}
    )
    
    assert strategy is not None
    assert strategy.strategy_type == "reverse_scalping"
    assert strategy.symbol == "BTCUSDT"
    
    # Cleanup
    test_db.delete(strategy)
    test_db.delete(account)
    test_db.delete(user)
    test_db.commit()


def test_reverse_scalping_trade_storage(test_db):
    """Test that trades from reverse_scalping strategy are saved to database."""
    db_service = DatabaseService(test_db)
    
    user_id = uuid4()
    account_id = uuid4()
    
    # Create account and user first
    from app.models.db_models import Account, User
    user = User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        password_hash="hash",
        is_active=True
    )
    test_db.add(user)
    
    account = Account(
        id=account_id,
        user_id=user_id,
        account_id="test_account",
        name="Test Account",
        exchange_platform="binance",
        api_key_encrypted="test_key",
        api_secret_encrypted="test_secret",
        testnet=True,
        is_active=True,
        is_default=True
    )
    test_db.add(account)
    test_db.commit()
    
    # Create strategy with reverse_scalping type
    strategy = db_service.create_strategy(
        user_id=user_id,
        strategy_id="test_reverse_scalping",
        name="Test Reverse Scalping",
        symbol="BTCUSDT",
        strategy_type="reverse_scalping",
        account_id=account_id,
        leverage=10,
        risk_per_trade=0.02,
        params={"ema_fast": 8, "ema_slow": 21}
    )
    
    # Create a trade for this strategy
    trade_data = {
        "strategy_id": strategy.id,
        "user_id": user_id,
        "order_id": 123456789,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "status": "FILLED",
        "price": 50000.0,
        "executed_qty": 0.001,
        "position_side": "LONG",
        "leverage": 10,
        "timestamp": datetime.now(timezone.utc)
    }
    
    trade = db_service.create_trade(trade_data)
    
    assert trade is not None
    assert trade.strategy_id == strategy.id
    assert trade.symbol == "BTCUSDT"
    
    # Verify we can query trades by strategy
    trades = db_service.get_user_trades(user_id, strategy_id=strategy.id)
    assert len(trades) == 1
    assert trades[0].order_id == 123456789
    
    # Cleanup
    test_db.delete(trade)
    test_db.delete(strategy)
    test_db.delete(account)
    test_db.delete(user)
    test_db.commit()


def test_reverse_scalping_backtest_storage(test_db):
    """Test that backtest results with reverse_scalping are stored correctly."""
    db_service = DatabaseService(test_db)
    
    user_id = uuid4()
    
    # Create backtest with reverse_scalping type
    backtest_data = {
        "user_id": user_id,
        "symbol": "BTCUSDT",
        "strategy_type": "reverse_scalping",
        "start_time": datetime.now(timezone.utc),
        "end_time": datetime.now(timezone.utc),
        "leverage": 10,
        "risk_per_trade": 0.02,
        "initial_balance": 1000.0,
        "params": {"ema_fast": 8, "ema_slow": 21},
        "total_trades": 5,
        "completed_trades": 5,
        "winning_trades": 3,
        "losing_trades": 2,
        "total_pnl": 50.0,
        "win_rate": 60.0,
        "avg_profit_per_trade": 10.0
    }
    
    backtest = db_service.create_backtest(backtest_data)
    
    assert backtest is not None
    assert backtest.strategy_type == "reverse_scalping"
    assert backtest.symbol == "BTCUSDT"
    assert backtest.total_trades == 5
    
    # Verify we can query backtests by strategy_type
    all_backtests = db_service.get_user_backtests(user_id)
    reverse_backtests = [b for b in all_backtests if b.strategy_type == "reverse_scalping"]
    assert len(reverse_backtests) >= 1
    
    # Cleanup
    test_db.delete(backtest)
    test_db.commit()

