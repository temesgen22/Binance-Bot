"""
Test for StrategyStatistics loading trades from database.

This test verifies the fix where StrategyStatistics can now load trades
from the database when they're not in memory or Redis, ensuring statistics
show correct values even after server restarts.
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch, Mock

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.redis_storage import RedisStorage
from app.services.strategy_statistics import StrategyStatistics
from app.services.trade_service import TradeService
from app.services.strategy_service import StrategyService
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.models.order import OrderResponse
from app.models.db_models import Base, User, Account, Strategy as DBStrategy

# Test database URL (in-memory SQLite for testing)
TEST_DB_URL = "sqlite:///:memory:"

# Map JSONB to JSON for SQLite compatibility
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler, SQLiteDDLCompiler
from sqlalchemy.schema import CheckConstraint

if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    original_visit_JSONB = getattr(SQLiteTypeCompiler, 'visit_JSONB', None)
    
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
def db_session():
    """Create in-memory SQLite database session."""
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    
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
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    from app.models.db_models import User
    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        is_active=True,
        is_verified=True
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_account(db_session, test_user):
    """Create a test account."""
    from app.models.db_models import Account
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="test_account",
        name="Test Account",
        exchange_platform="binance",
        api_key_encrypted="encrypted_key",
        api_secret_encrypted="encrypted_secret",
        testnet=True,
        is_active=True,
        is_default=True
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def test_strategy(db_session, test_user, test_account):
    """Create a test strategy in database."""
    strategy = DBStrategy(
        id=uuid4(),
        user_id=test_user.id,
        strategy_id="test-strategy-1",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type="scalping",
        account_id=test_account.id,
        leverage=5,
        risk_per_trade=0.01,
        params={"ema_fast": 5, "ema_slow": 20},
        status="stopped"
    )
    db_session.add(strategy)
    db_session.commit()
    return strategy


@pytest.fixture
def strategy_service(db_session):
    """Create StrategyService with database."""
    redis_storage = RedisStorage(enabled=False)  # Disable Redis for this test
    return StrategyService(db_session, redis_storage)


@pytest.fixture
def trade_service(db_session):
    """Create TradeService with database."""
    redis_storage = RedisStorage(enabled=False)  # Disable Redis for this test
    return TradeService(db_session, redis_storage)


@pytest.fixture
def sample_trades():
    """Create sample trades for testing."""
    base_time = datetime.now(timezone.utc)
    return [
        OrderResponse(
            order_id=1001,
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.001,
            timestamp=base_time,
        ),
        OrderResponse(
            order_id=1002,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=51000.0,
            avg_price=51000.0,
            executed_qty=0.001,
            timestamp=base_time.replace(second=base_time.second + 10),
        ),
    ]


class TestStrategyStatisticsDatabaseLoading:
    """Test StrategyStatistics loading trades from database."""
    
    def test_load_trades_from_database_when_not_in_memory(
        self,
        test_user: User,
        test_strategy: DBStrategy,
        strategy_service: StrategyService,
        trade_service: TradeService,
        sample_trades: list[OrderResponse],
        db_session: Session
    ):
        """Test that statistics loads trades from database when not in memory."""
        # Save trades to database
        for trade in sample_trades:
            trade_service.save_trade(
                user_id=test_user.id,
                strategy_id=test_strategy.id,
                order=trade
            )
        
        # Create strategy summary (in-memory representation)
        strategy_summary = StrategySummary(
            id=test_strategy.strategy_id,  # Use string ID
            name=test_strategy.name,
            symbol=test_strategy.symbol,
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=test_strategy.leverage,
            risk_per_trade=float(test_strategy.risk_per_trade),
            params=StrategyParams(**test_strategy.params),
            created_at=test_strategy.created_at,
            last_signal=None,
        )
        
        # Initialize dictionaries (empty - simulating server restart)
        strategies = {test_strategy.strategy_id: strategy_summary}
        trades = {}  # Empty - trades not in memory
        
        # Redis is disabled
        redis_storage = RedisStorage(enabled=False)
        
        # Create StrategyStatistics with database services
        statistics = StrategyStatistics(
            strategies=strategies,
            trades=trades,
            redis_storage=redis_storage,
            trade_service=trade_service,
            strategy_service=strategy_service,
            user_id=test_user.id,
        )
        
        # Calculate stats - should load from database
        stats = statistics.calculate_strategy_stats(test_strategy.strategy_id)
        
        # Verify statistics were calculated correctly
        assert stats.total_trades == 2  # 2 trades in database
        assert stats.completed_trades == 1  # 1 completed trade (BUY + SELL pair)
        assert stats.total_pnl > 0  # Profit from BUY @ 50000, SELL @ 51000
        assert stats.win_rate == 100.0  # 1 winning trade
        assert stats.winning_trades == 1
        assert stats.losing_trades == 0
        
        # Verify trades were loaded into memory
        assert test_strategy.strategy_id in statistics._trades
        assert len(statistics._trades[test_strategy.strategy_id]) == 2
    
    def test_load_trades_fallback_order_memory_redis_database(
        self,
        test_user: User,
        test_strategy: DBStrategy,
        strategy_service: StrategyService,
        trade_service: TradeService,
        sample_trades: list[OrderResponse],
        db_session: Session
    ):
        """Test that statistics uses fallback order: memory -> Redis -> database."""
        # Save trades to database
        for trade in sample_trades:
            trade_service.save_trade(
                user_id=test_user.id,
                strategy_id=test_strategy.id,
                order=trade
            )
        
        # Create strategy summary
        strategy_summary = StrategySummary(
            id=test_strategy.strategy_id,
            name=test_strategy.name,
            symbol=test_strategy.symbol,
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=test_strategy.leverage,
            risk_per_trade=float(test_strategy.risk_per_trade),
            params=StrategyParams(**test_strategy.params),
            created_at=test_strategy.created_at,
            last_signal=None,
        )
        
        # Test 1: Trades in memory - should use memory (highest priority)
        strategies = {test_strategy.strategy_id: strategy_summary}
        memory_trades = [sample_trades[0]]  # Only first trade in memory
        trades = {test_strategy.strategy_id: memory_trades}
        
        redis_storage = RedisStorage(enabled=False)
        statistics = StrategyStatistics(
            strategies=strategies,
            trades=trades,
            redis_storage=redis_storage,
            trade_service=trade_service,
            strategy_service=strategy_service,
            user_id=test_user.id,
        )
        
        stats = statistics.calculate_strategy_stats(test_strategy.strategy_id)
        # Should use memory trades (only 1 trade)
        assert stats.total_trades == 1
        assert test_strategy.strategy_id in statistics._trades
        assert len(statistics._trades[test_strategy.strategy_id]) == 1
        
        # Test 2: No trades in memory, Redis disabled - should use database
        trades_empty = {}
        statistics2 = StrategyStatistics(
            strategies=strategies,
            trades=trades_empty,
            redis_storage=redis_storage,
            trade_service=trade_service,
            strategy_service=strategy_service,
            user_id=test_user.id,
        )
        
        stats2 = statistics2.calculate_strategy_stats(test_strategy.strategy_id)
        # Should load from database (2 trades)
        assert stats2.total_trades == 2
        assert stats2.completed_trades == 1
    
    def test_statistics_without_database_services_fallback(
        self,
        test_strategy: DBStrategy
    ):
        """Test that statistics works without database services (backward compatibility)."""
        strategy_summary = StrategySummary(
            id=test_strategy.strategy_id,
            name=test_strategy.name,
            symbol=test_strategy.symbol,
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=test_strategy.leverage,
            risk_per_trade=float(test_strategy.risk_per_trade),
            params=StrategyParams(**test_strategy.params),
            created_at=test_strategy.created_at,
            last_signal=None,
        )
        
        strategies = {test_strategy.strategy_id: strategy_summary}
        trades = {}  # Empty
        
        # Create Statistics without database services (backward compatibility)
        statistics = StrategyStatistics(
            strategies=strategies,
            trades=trades,
            redis_storage=None,
            trade_service=None,  # No database services
            strategy_service=None,
            user_id=None,
        )
        
        # Should not crash, but stats will be zero
        stats = statistics.calculate_strategy_stats(test_strategy.strategy_id)
        assert stats.total_trades == 0
        assert stats.completed_trades == 0
        assert stats.total_pnl == 0.0
    
    def test_statistics_with_empty_database(
        self,
        test_user: User,
        test_strategy: DBStrategy,
        strategy_service: StrategyService,
        trade_service: TradeService
    ):
        """Test that statistics handles empty database gracefully."""
        strategy_summary = StrategySummary(
            id=test_strategy.strategy_id,
            name=test_strategy.name,
            symbol=test_strategy.symbol,
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=test_strategy.leverage,
            risk_per_trade=float(test_strategy.risk_per_trade),
            params=StrategyParams(**test_strategy.params),
            created_at=test_strategy.created_at,
            last_signal=None,
        )
        
        strategies = {test_strategy.strategy_id: strategy_summary}
        trades = {}  # Empty
        
        redis_storage = RedisStorage(enabled=False)
        statistics = StrategyStatistics(
            strategies=strategies,
            trades=trades,
            redis_storage=redis_storage,
            trade_service=trade_service,
            strategy_service=strategy_service,
            user_id=test_user.id,
        )
        
        # Should not crash, stats will be zero (no trades in database)
        stats = statistics.calculate_strategy_stats(test_strategy.strategy_id)
        assert stats.total_trades == 0
        assert stats.completed_trades == 0
        assert stats.total_pnl == 0.0
        assert stats.win_rate == 0.0

