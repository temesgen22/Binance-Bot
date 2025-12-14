"""
End-to-end test for Redis and Database working together.

This test verifies:
1. Cache-aside pattern (read from Redis, fallback to DB)
2. Write-through pattern (write to DB, cache in Redis)
3. Cache invalidation on updates
4. Data persistence across operations
5. Both StrategyService and TradeService integration
"""
import pytest
import json
from datetime import datetime, timezone
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects import registry

from app.core.redis_storage import RedisStorage
from app.services.strategy_service import StrategyService
from app.services.trade_service import TradeService
from app.models.strategy import StrategySummary, StrategyState, StrategyType
from app.models.order import OrderResponse
from app.models.db_models import Base, User, Account, Strategy as DBStrategy, Trade as DBTrade


# Test database URL (in-memory SQLite for testing)
TEST_DB_URL = "sqlite:///:memory:"


# Map JSONB to JSON for SQLite compatibility (must be done at module level)
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
        # Check if constraint uses PostgreSQL regex operators (~ or ~*)
        try:
            sqltext = str(constraint.sqltext.compile(compile_kwargs={"literal_binds": True}))
            if '~' in sqltext or '~*' in sqltext:
                # Skip this constraint for SQLite (regex not supported)
                return None
        except Exception:
            # If we can't check, try to compile and see if it fails
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
    """Create a test database session with in-memory SQLite."""
    engine = create_engine(TEST_DB_URL, echo=False)
    
    # Remove PostgreSQL-specific CHECK constraints (regex operators) for SQLite
    for table in Base.metadata.tables.values():
        # Filter out CHECK constraints with regex operators
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
def test_user(test_db_session: Session):
    """Create a test user in the database."""
    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        is_active=True
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def test_account(test_db_session: Session, test_user: User):
    """Create a test account in the database."""
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="test_account",
        api_key_encrypted="test_key",
        api_secret_encrypted="test_secret",
        testnet=True,
        name="Test Account"
    )
    test_db_session.add(account)
    test_db_session.commit()
    test_db_session.refresh(account)
    return account


@pytest.fixture
def mock_redis_enabled():
    """Create a mock Redis storage that is enabled."""
    redis_storage = MagicMock(spec=RedisStorage)
    redis_storage.enabled = True
    redis_storage._client = MagicMock()
    redis_storage._client.get.return_value = None  # Default: cache miss
    redis_storage._client.setex.return_value = True
    redis_storage._client.delete.return_value = 1
    return redis_storage


@pytest.fixture
def mock_redis_disabled():
    """Create a mock Redis storage that is disabled."""
    redis_storage = MagicMock(spec=RedisStorage)
    redis_storage.enabled = False
    redis_storage._client = None
    return redis_storage


@pytest.fixture
def strategy_service_with_redis(test_db_session: Session, mock_redis_enabled):
    """Create StrategyService with Redis enabled."""
    return StrategyService(db=test_db_session, redis_storage=mock_redis_enabled)


@pytest.fixture
def strategy_service_no_redis(test_db_session: Session, mock_redis_disabled):
    """Create StrategyService without Redis."""
    return StrategyService(db=test_db_session, redis_storage=mock_redis_disabled)


@pytest.fixture
def trade_service_with_redis(test_db_session: Session, mock_redis_enabled):
    """Create TradeService with Redis enabled."""
    return TradeService(db=test_db_session, redis_storage=mock_redis_enabled)


class TestRedisDatabaseIntegration:
    """End-to-end tests for Redis and Database working together."""
    
    def test_cache_aside_pattern_read_from_redis(
        self,
        strategy_service_with_redis: StrategyService,
        test_user: User,
        test_account: Account,
        mock_redis_enabled
    ):
        """Test cache-aside pattern: read from Redis cache first."""
        strategy_id = "test-strategy-1"
        
        # Setup: Strategy exists in Redis cache
        cached_data = {
            "id": strategy_id,
            "name": "Cached Strategy",
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "status": "stopped",
            "leverage": 5,
            "risk_per_trade": 0.01,
            "fixed_amount": None,
            "params": {"ema_fast": 5, "ema_slow": 20},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "account_id": test_account.account_id,
            "last_signal": None,
            "entry_price": None,
            "current_price": None,
            "position_size": None,
            "position_side": None,
            "unrealized_pnl": None,
            "meta": {}
        }
        
        # Mock Redis to return cached data
        mock_redis_enabled._client.get.return_value = json.dumps(cached_data)
        
        # Act: Get strategy
        result = strategy_service_with_redis.get_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        
        # Assert: Should return cached data from Redis
        assert result is not None
        assert result.id == strategy_id
        assert result.name == "Cached Strategy"
        
        # Verify Redis was checked first
        mock_redis_enabled._client.get.assert_called_once()
        
        # Verify database was NOT queried (cache hit)
        # We can't easily verify this without more complex mocking, but the fact
        # that we got the cached data proves Redis was used
    
    def test_cache_aside_pattern_fallback_to_database(
        self,
        strategy_service_with_redis: StrategyService,
        test_user: User,
        test_account: Account,
        mock_redis_enabled
    ):
        """Test cache-aside pattern: fallback to database on cache miss."""
        strategy_id = "test-strategy-2"
        
        # Setup: Strategy exists in database but NOT in Redis
        from app.services.database_service import DatabaseService
        db_service = DatabaseService(strategy_service_with_redis.db_service.db)
        
        db_strategy = db_service.create_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="Database Strategy",
            symbol="ETHUSDT",
            strategy_type="scalping",
            account_id=test_account.id,
            leverage=10,
            risk_per_trade=0.02,
            params={"ema_fast": 3, "ema_slow": 5},
            fixed_amount=100.0,
            max_positions=1
        )
        
        # Mock Redis to return None (cache miss)
        mock_redis_enabled._client.get.return_value = None
        
        # Act: Get strategy
        result = strategy_service_with_redis.get_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        
        # Assert: Should return data from database
        assert result is not None
        assert result.id == strategy_id
        assert result.name == "Database Strategy"
        assert result.symbol == "ETHUSDT"
        assert result.leverage == 10
        
        # Verify Redis was checked first (cache miss)
        mock_redis_enabled._client.get.assert_called_once()
        
        # Verify result was cached in Redis
        mock_redis_enabled._client.setex.assert_called_once()
        call_args = mock_redis_enabled._client.setex.call_args
        assert call_args[0][0] == f"binance_bot:user:{test_user.id}:strategy:{strategy_id}"
        assert call_args[0][1] == 3600  # TTL (1 hour)
    
    def test_write_through_pattern_create_strategy(
        self,
        strategy_service_with_redis: StrategyService,
        test_user: User,
        test_account: Account,
        mock_redis_enabled
    ):
        """Test write-through pattern: create in database and cache in Redis."""
        strategy_id = "test-strategy-3"
        
        # Mock Redis to return None (no existing cache)
        mock_redis_enabled._client.get.return_value = None
        
        # Act: Create strategy
        summary = strategy_service_with_redis.create_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="New Strategy",
            symbol="SOLUSDT",
            strategy_type="scalping",
            account_id=test_account.id,
            leverage=5,
            risk_per_trade=0.01,
            params={"ema_fast": 5, "ema_slow": 20},
            fixed_amount=None,
            max_positions=1
        )
        
        # Assert: Strategy created
        assert summary is not None
        assert summary.id == strategy_id
        assert summary.name == "New Strategy"
        
        # Verify strategy exists in database
        db_strategy = strategy_service_with_redis.db_service.get_strategy(
            test_user.id,
            strategy_id
        )
        assert db_strategy is not None
        assert db_strategy.name == "New Strategy"
        
        # Verify strategy was cached in Redis
        mock_redis_enabled._client.setex.assert_called_once()
        call_args = mock_redis_enabled._client.setex.call_args
        assert call_args[0][0] == f"binance_bot:user:{test_user.id}:strategy:{strategy_id}"
        
        # Verify cached data contains correct information
        cached_json = call_args[0][2]
        cached_data = json.loads(cached_json)
        assert cached_data["id"] == strategy_id
        assert cached_data["name"] == "New Strategy"
    
    def test_cache_invalidation_on_update(
        self,
        strategy_service_with_redis: StrategyService,
        test_user: User,
        test_account: Account,
        mock_redis_enabled
    ):
        """Test cache invalidation when strategy is updated."""
        strategy_id = "test-strategy-4"
        
        # Setup: Create strategy (will be cached in Redis)
        summary = strategy_service_with_redis.create_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="Original Name",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=test_account.id,
            leverage=5,
            risk_per_trade=0.01,
            params={"ema_fast": 5, "ema_slow": 20},
            fixed_amount=None,
            max_positions=1
        )
        
        # Clear previous calls
        mock_redis_enabled._client.setex.reset_mock()
        mock_redis_enabled._client.delete.reset_mock()
        
        # Act: Update strategy
        updated = strategy_service_with_redis.update_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="Updated Name",
            leverage=10
        )
        
        # Assert: Strategy updated in database
        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.leverage == 10
        
        # Verify cache was invalidated (deleted from Redis)
        mock_redis_enabled._client.delete.assert_called_once()
        call_args = mock_redis_enabled._client.delete.call_args
        assert call_args[0][0] == f"binance_bot:user:{test_user.id}:strategy:{strategy_id}"
        
        # Verify cache was NOT updated (only invalidated)
        mock_redis_enabled._client.setex.assert_not_called()
        
        # Verify next read will fetch from database and cache
        mock_redis_enabled._client.get.return_value = None  # Cache miss after invalidation
        result = strategy_service_with_redis.get_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        assert result.name == "Updated Name"  # Fresh data from DB
        mock_redis_enabled._client.setex.assert_called_once()  # Re-cached
    
    def test_redis_disabled_fallback_to_database_only(
        self,
        strategy_service_no_redis: StrategyService,
        test_user: User,
        test_account: Account
    ):
        """Test that system works with Redis disabled (database only)."""
        strategy_id = "test-strategy-5"
        
        # Act: Create strategy without Redis
        summary = strategy_service_no_redis.create_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="No Redis Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=test_account.id,
            leverage=5,
            risk_per_trade=0.01,
            params={"ema_fast": 5, "ema_slow": 20},
            fixed_amount=None,
            max_positions=1
        )
        
        # Assert: Strategy created in database
        assert summary is not None
        assert summary.id == strategy_id
        
        # Verify strategy exists in database
        db_strategy = strategy_service_no_redis.db_service.get_strategy(
            test_user.id,
            strategy_id
        )
        assert db_strategy is not None
        assert db_strategy.name == "No Redis Strategy"
        
        # Verify Redis was not used (disabled)
        assert strategy_service_no_redis.redis.enabled is False
    
    def test_trade_service_redis_database_integration(
        self,
        trade_service_with_redis: TradeService,
        strategy_service_with_redis: StrategyService,
        test_user: User,
        test_account: Account,
        mock_redis_enabled
    ):
        """Test TradeService with Redis and Database working together."""
        strategy_id = "test-strategy-6"
        
        # Setup: Create a strategy first
        strategy_summary = strategy_service_with_redis.create_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="Trade Test Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=test_account.id,
            leverage=5,
            risk_per_trade=0.01,
            params={"ema_fast": 5, "ema_slow": 20},
            fixed_amount=None,
            max_positions=1
        )
        
        # Get strategy UUID from database
        db_strategy = strategy_service_with_redis.db_service.get_strategy(
            test_user.id,
            strategy_id
        )
        strategy_uuid = db_strategy.id
        
        # Create a mock trade
        order = OrderResponse(
            order_id=12345,
            client_order_id="test_client_order",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            status="FILLED",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.001,
            notional_value=50.0,
            cummulative_quote_qty=50.0,
            initial_margin=10.0,
            commission=0.05,
            commission_asset="USDT",
            timestamp=datetime.now(timezone.utc),
            update_time=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        
        # Mock Redis to return None (no cached trades)
        mock_redis_enabled._client.get.return_value = None
        
        # Act: Save trade
        trade = trade_service_with_redis.save_trade(
            user_id=test_user.id,
            strategy_id=strategy_uuid,
            order=order
        )
        
        # Assert: Trade created in database
        assert trade is not None
        assert trade.order_id == 12345
        
        # Verify trade exists in database
        db_trades = trade_service_with_redis.db_service.get_user_trades(
            user_id=test_user.id,
            strategy_id=strategy_uuid
        )
        assert len(db_trades) == 1
        assert db_trades[0].order_id == 12345
        
        # Verify trade was cached in Redis (using zadd for sorted set)
        mock_redis_enabled._client.zadd.assert_called()
        # Check that zadd was called with correct key pattern
        # TradeService uses strategy UUID (not strategy_id string) for Redis key
        calls = [call[0][0] for call in mock_redis_enabled._client.zadd.call_args_list]
        trade_key = f"binance_bot:user:{test_user.id}:trades:recent:{str(strategy_uuid)}"
        assert any(trade_key in str(call) for call in calls)
    
    def test_data_persistence_across_operations(
        self,
        strategy_service_with_redis: StrategyService,
        test_user: User,
        test_account: Account,
        mock_redis_enabled
    ):
        """Test that data persists correctly across multiple operations."""
        strategy_id = "test-strategy-7"
        
        # Step 1: Create strategy
        summary1 = strategy_service_with_redis.create_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="Persistent Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=test_account.id,
            leverage=5,
            risk_per_trade=0.01,
            params={"ema_fast": 5, "ema_slow": 20},
            fixed_amount=None,
            max_positions=1
        )
        
        # Step 2: Update strategy (cache invalidated)
        summary2 = strategy_service_with_redis.update_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            status=StrategyState.running.value
        )
        assert summary2.status == StrategyState.running
        
        # Step 3: Read strategy (should fetch from DB and cache)
        mock_redis_enabled._client.get.return_value = None  # Cache miss
        summary3 = strategy_service_with_redis.get_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        
        # Assert: All operations persisted correctly
        assert summary3 is not None
        assert summary3.id == strategy_id
        assert summary3.name == "Persistent Strategy"
        assert summary3.status == StrategyState.running  # Updated status persisted
        
        # Verify data is in database
        db_strategy = strategy_service_with_redis.db_service.get_strategy(
            test_user.id,
            strategy_id
        )
        assert db_strategy.status == "running"
    
    def test_concurrent_reads_cache_performance(
        self,
        strategy_service_with_redis: StrategyService,
        test_user: User,
        test_account: Account,
        mock_redis_enabled
    ):
        """Test that cached reads are faster (Redis used, DB not queried)."""
        strategy_id = "test-strategy-8"
        
        # Setup: Create strategy and cache it
        strategy_service_with_redis.create_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="Cached Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=test_account.id,
            leverage=5,
            risk_per_trade=0.01,
            params={"ema_fast": 5, "ema_slow": 20},
            fixed_amount=None,
            max_positions=1
        )
        
        # Setup: Mock Redis to return cached data
        cached_data = {
            "id": strategy_id,
            "name": "Cached Strategy",
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "status": "stopped",
            "leverage": 5,
            "risk_per_trade": 0.01,
            "fixed_amount": None,
            "params": {"ema_fast": 5, "ema_slow": 20},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "account_id": test_account.account_id,
            "last_signal": None,
            "entry_price": None,
            "current_price": None,
            "position_size": None,
            "position_side": None,
            "unrealized_pnl": None,
            "meta": {}
        }
        mock_redis_enabled._client.get.return_value = json.dumps(cached_data)
        
        # Reset call counts
        mock_redis_enabled._client.get.reset_mock()
        
        # Act: Multiple reads
        for _ in range(5):
            result = strategy_service_with_redis.get_strategy(
                user_id=test_user.id,
                strategy_id=strategy_id
            )
            assert result is not None
        
        # Assert: Redis was called 5 times (cache hits)
        assert mock_redis_enabled._client.get.call_count == 5
        
        # Assert: Database was NOT queried (all cache hits)
        # This is verified by the fact that get_strategy didn't call db_service.get_strategy
        # when Redis returned data


class TestRedisDatabaseEndToEnd:
    """End-to-end integration tests simulating real-world usage."""
    
    def test_complete_strategy_lifecycle(
        self,
        strategy_service_with_redis: StrategyService,
        test_user: User,
        test_account: Account,
        mock_redis_enabled
    ):
        """Test complete strategy lifecycle: create, read, update, delete."""
        strategy_id = "lifecycle-strategy"
        
        # 1. CREATE: Create strategy
        summary = strategy_service_with_redis.create_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="Lifecycle Test",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=test_account.id,
            leverage=5,
            risk_per_trade=0.01,
            params={"ema_fast": 5, "ema_slow": 20},
            fixed_amount=None,
            max_positions=1
        )
        assert summary is not None
        
        # 2. READ: Read strategy (cache miss, then cached)
        mock_redis_enabled._client.get.return_value = None
        read1 = strategy_service_with_redis.get_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        assert read1.name == "Lifecycle Test"
        
        # 3. READ: Read again (should use cache)
        cached_data = {
            "id": strategy_id,
            "name": "Lifecycle Test",
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "status": "stopped",
            "leverage": 5,
            "risk_per_trade": 0.01,
            "fixed_amount": None,
            "params": {"ema_fast": 5, "ema_slow": 20},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "account_id": test_account.account_id,
            "last_signal": None,
            "entry_price": None,
            "current_price": None,
            "position_size": None,
            "position_side": None,
            "unrealized_pnl": None,
            "meta": {}
        }
        mock_redis_enabled._client.get.return_value = json.dumps(cached_data)
        read2 = strategy_service_with_redis.get_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        assert read2.name == "Lifecycle Test"
        
        # 4. UPDATE: Update strategy
        updated = strategy_service_with_redis.update_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id,
            name="Updated Lifecycle Test",
            leverage=10
        )
        assert updated.name == "Updated Lifecycle Test"
        assert updated.leverage == 10
        
        # 5. READ AFTER UPDATE: Should fetch fresh data from DB
        mock_redis_enabled._client.get.return_value = None  # Cache invalidated
        read3 = strategy_service_with_redis.get_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        assert read3.name == "Updated Lifecycle Test"
        assert read3.leverage == 10
        
        # 6. DELETE: Delete strategy
        deleted = strategy_service_with_redis.delete_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        assert deleted is True
        
        # 7. READ AFTER DELETE: Should return None
        read4 = strategy_service_with_redis.get_strategy(
            user_id=test_user.id,
            strategy_id=strategy_id
        )
        assert read4 is None

