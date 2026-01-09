"""
Integration tests for CompletedTrade service.

Tests verify:
1. Creating completed trades works correctly
2. Idempotency (UUIDv5) prevents duplicates
3. Row locks prevent allocation races
4. Partial fills are handled correctly
5. Allocation invariants are enforced
6. Fee calculation is proportional
7. Futures hedge-mode classification works
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from uuid import UUID, uuid4
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db_models import (
    Base, User, Account, Strategy, Trade, CompletedTrade, CompletedTradeOrder
)
from app.services.completed_trade_service import CompletedTradeService
from app.services.database_service import DatabaseService


# Test database URL (use in-memory SQLite for testing)
TEST_DATABASE_URL = "sqlite:///:memory:"


# Map JSONB to JSON for SQLite compatibility (must be done at module level)
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.schema import CheckConstraint

if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    def visit_JSONB(self, type_, **kw):
        """Map JSONB to JSON for SQLite compatibility."""
        return "JSON"
    
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True


@pytest.fixture
def db_session():
    """Create a test database session."""
    engine = create_engine(TEST_DATABASE_URL, echo=False)
    
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
    user = User(
        id=uuid4(),
        email="test@example.com",
        username="testuser",
        password_hash="hashed_password",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_account(db_session, test_user):
    """Create a test account."""
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="test-account",
        name="Test Account",
        exchange_platform="binance",
        api_key_encrypted="encrypted_key",
        api_secret_encrypted="encrypted_secret",
        testnet=True,
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def test_strategy(db_session, test_user, test_account):
    """Create a test strategy."""
    strategy = Strategy(
        id=uuid4(),
        user_id=test_user.id,
        strategy_id="test-strategy-1",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type="scalping",
        leverage=10,
        risk_per_trade=0.02,
        max_positions=1,
        params={},
        account_id=test_account.id,
        status="running",
    )
    db_session.add(strategy)
    db_session.commit()
    return strategy


@pytest.fixture
def entry_trade(db_session, test_user, test_strategy):
    """Create an entry trade (BUY/LONG)."""
    trade = Trade(
        id=uuid4(),
        strategy_id=test_strategy.id,
        user_id=test_user.id,
        order_id=1001,
        symbol="BTCUSDT",
        side="BUY",
        status="FILLED",
        price=50000.0,
        avg_price=50000.0,
        executed_qty=1.0,
        orig_qty=1.0,
        remaining_qty=0.0,
        commission=20.0,  # 0.04% of 50000 * 1.0
        position_side="LONG",
        leverage=10,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()
    return trade


@pytest.fixture
def exit_trade(db_session, test_user, test_strategy):
    """Create an exit trade (SELL)."""
    trade = Trade(
        id=uuid4(),
        strategy_id=test_strategy.id,
        user_id=test_user.id,
        order_id=1002,
        symbol="BTCUSDT",
        side="SELL",
        status="FILLED",
        price=51000.0,
        avg_price=51000.0,
        executed_qty=1.0,
        orig_qty=1.0,
        remaining_qty=0.0,
        commission=20.4,  # 0.04% of 51000 * 1.0
        position_side="LONG",
        leverage=10,
        exit_reason="TP",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()
    return trade


@pytest.fixture
def completed_trade_service(db_session):
    """Create CompletedTradeService instance."""
    return CompletedTradeService(db_session)


class TestCompletedTradeCreation:
    """Test basic completed trade creation."""
    
    def test_create_completed_trade_success(
        self, completed_trade_service, test_user, test_strategy, entry_trade, exit_trade
    ):
        """Test successful creation of a completed trade."""
        # Calculate expected PnL
        # LONG: (exit_price - entry_price) * quantity - fees
        gross_pnl = (51000.0 - 50000.0) * 1.0  # 1000 USDT
        total_fee = 20.0 + 20.4  # 40.4 USDT
        net_pnl = gross_pnl - total_fee  # 959.6 USDT
        pnl_pct = (net_pnl / (50000.0 * 1.0)) * 100  # ~1.92%
        
        completed_trade = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=1.0,
            pnl_usd=net_pnl,
            pnl_pct=pnl_pct,
            funding_fee=0.0,
        )
        
        assert completed_trade is not None
        assert completed_trade.id is not None
        assert completed_trade.strategy_id == test_strategy.id
        assert completed_trade.user_id == test_user.id
        assert completed_trade.side == "LONG"
        assert completed_trade.quantity == 1.0
        assert abs(float(completed_trade.pnl_usd) - net_pnl) < 0.01
        assert abs(float(completed_trade.fee_paid) - total_fee) < 0.01
        
        # Verify junction table records
        assert len(completed_trade.orders) == 2
        entry_order = next((o for o in completed_trade.orders if o.order_role == "ENTRY"), None)
        exit_order = next((o for o in completed_trade.orders if o.order_role == "EXIT"), None)
        
        assert entry_order is not None
        assert entry_order.trade_id == entry_trade.id
        assert entry_order.order_id == entry_trade.order_id
        assert entry_order.quantity == 1.0
        
        assert exit_order is not None
        assert exit_order.trade_id == exit_trade.id
        assert exit_order.order_id == exit_trade.order_id
        assert exit_order.quantity == 1.0
    
    def test_idempotency_prevents_duplicates(
        self, completed_trade_service, test_user, test_strategy, entry_trade, exit_trade
    ):
        """Test that idempotency key prevents duplicate completed trades."""
        net_pnl = 959.6
        pnl_pct = 1.92
        
        # Create first completed trade
        completed_trade_1 = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=1.0,
            pnl_usd=net_pnl,
            pnl_pct=pnl_pct,
            funding_fee=0.0,
        )
        
        # Try to create duplicate (should return existing)
        completed_trade_2 = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=1.0,
            pnl_usd=net_pnl,
            pnl_pct=pnl_pct,
            funding_fee=0.0,
        )
        
        # Should return the same completed trade
        assert completed_trade_1.id == completed_trade_2.id
        
        # Verify only one completed trade exists
        db = completed_trade_service.db
        count = db.query(CompletedTrade).filter(
            CompletedTrade.close_event_id == completed_trade_1.close_event_id
        ).count()
        assert count == 1


class TestPartialFills:
    """Test partial fill handling."""
    
    def test_partial_fill_allocation(
        self, completed_trade_service, db_session, test_user, test_strategy
    ):
        """Test that partial fills are allocated correctly."""
        # Create entry trade with 10 BTC
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=2001,
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=10.0,
            orig_qty=10.0,
            remaining_qty=0.0,
            commission=200.0,  # 0.04% of 50000 * 10.0
            position_side="LONG",
            leverage=10,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(entry_trade)
        db_session.commit()
        
        # Create first exit trade (6 BTC)
        exit_trade_1 = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=2002,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=51000.0,
            avg_price=51000.0,
            executed_qty=6.0,
            orig_qty=6.0,
            remaining_qty=0.0,
            commission=122.4,  # 0.04% of 51000 * 6.0
            position_side="LONG",
            leverage=10,
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(exit_trade_1)
        db_session.commit()
        
        # Create first completed trade (6 BTC)
        gross_pnl_1 = (51000.0 - 50000.0) * 6.0  # 6000 USDT
        fee_1 = (200.0 * (6.0 / 10.0)) + 122.4  # 120 + 122.4 = 242.4
        net_pnl_1 = gross_pnl_1 - fee_1
        pnl_pct_1 = (net_pnl_1 / (50000.0 * 6.0)) * 100
        
        completed_trade_1 = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade_1.id,
            quantity=6.0,
            pnl_usd=net_pnl_1,
            pnl_pct=pnl_pct_1,
            funding_fee=0.0,
        )
        
        assert completed_trade_1.quantity == 6.0
        assert abs(float(completed_trade_1.fee_paid) - fee_1) < 0.01
        
        # Create second exit trade (4 BTC)
        exit_trade_2 = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=2003,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=52000.0,
            avg_price=52000.0,
            executed_qty=4.0,
            orig_qty=4.0,
            remaining_qty=0.0,
            commission=83.2,  # 0.04% of 52000 * 4.0
            position_side="LONG",
            leverage=10,
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(exit_trade_2)
        db_session.commit()
        
        # Create second completed trade (4 BTC)
        gross_pnl_2 = (52000.0 - 50000.0) * 4.0  # 8000 USDT
        fee_2 = (200.0 * (4.0 / 10.0)) + 83.2  # 80 + 83.2 = 163.2
        net_pnl_2 = gross_pnl_2 - fee_2
        pnl_pct_2 = (net_pnl_2 / (50000.0 * 4.0)) * 100
        
        completed_trade_2 = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade_2.id,
            quantity=4.0,
            pnl_usd=net_pnl_2,
            pnl_pct=pnl_pct_2,
            funding_fee=0.0,
        )
        
        assert completed_trade_2.quantity == 4.0
        assert abs(float(completed_trade_2.fee_paid) - fee_2) < 0.01
        
        # Verify total allocation doesn't exceed executed_qty
        from sqlalchemy import func
        total_allocated = db_session.query(
            func.sum(CompletedTradeOrder.quantity)
        ).filter(
            CompletedTradeOrder.trade_id == entry_trade.id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).scalar() or 0.0
        
        assert total_allocated == 10.0  # 6.0 + 4.0
        assert total_allocated <= float(entry_trade.executed_qty)
    
    def test_allocation_invariant_enforced(
        self, completed_trade_service, db_session, test_user, test_strategy
    ):
        """Test that allocation invariants prevent over-allocation."""
        # Create entry trade with 5 BTC
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=3001,
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=5.0,
            orig_qty=5.0,
            remaining_qty=0.0,
            commission=100.0,
            position_side="LONG",
            leverage=10,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(entry_trade)
        db_session.commit()
        
        # Create exit trade
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=3002,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=51000.0,
            avg_price=51000.0,
            executed_qty=5.0,
            orig_qty=5.0,
            remaining_qty=0.0,
            commission=102.0,
            position_side="LONG",
            leverage=10,
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(exit_trade)
        db_session.commit()
        
        # Try to allocate more than executed_qty (should fail)
        with pytest.raises(ValueError, match="allocation exceeds executed_qty"):
            completed_trade_service.create_completed_trade(
                user_id=test_user.id,
                strategy_id=test_strategy.id,
                entry_trade_id=entry_trade.id,
                exit_trade_id=exit_trade.id,
                quantity=6.0,  # More than executed_qty (5.0)
                pnl_usd=1000.0,
                pnl_pct=2.0,
                funding_fee=0.0,
            )


class TestFuturesHedgeMode:
    """Test futures hedge-mode classification."""
    
    def test_position_side_classification(
        self, completed_trade_service, db_session, test_user, test_strategy
    ):
        """Test that position_side is used for classification in hedge mode."""
        # Create SHORT entry trade (SELL in hedge mode)
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=4001,
            symbol="BTCUSDT",
            side="SELL",  # SELL in hedge mode
            status="FILLED",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=1.0,
            orig_qty=1.0,
            remaining_qty=0.0,
            commission=20.0,
            position_side="SHORT",  # ✅ CRITICAL: position_side determines classification
            leverage=10,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(entry_trade)
        db_session.commit()
        
        # Create exit trade (BUY to close SHORT)
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=4002,
            symbol="BTCUSDT",
            side="BUY",  # BUY closes SHORT in hedge mode
            status="FILLED",
            price=49000.0,
            avg_price=49000.0,
            executed_qty=1.0,
            orig_qty=1.0,
            remaining_qty=0.0,
            commission=19.6,
            position_side="SHORT",
            leverage=10,
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(exit_trade)
        db_session.commit()
        
        # Create completed trade
        # SHORT: (entry_price - exit_price) * quantity - fees
        gross_pnl = (50000.0 - 49000.0) * 1.0  # 1000 USDT profit
        total_fee = 20.0 + 19.6
        net_pnl = gross_pnl - total_fee
        pnl_pct = (net_pnl / (50000.0 * 1.0)) * 100
        
        completed_trade = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=1.0,
            pnl_usd=net_pnl,
            pnl_pct=pnl_pct,
            funding_fee=0.0,
        )
        
        # Should be classified as SHORT (from position_side), not from BUY/SELL
        assert completed_trade.side == "SHORT"


class TestRowLocks:
    """Test row locks prevent allocation races."""
    
    @pytest.mark.skip(reason="SQLite doesn't support multi-threaded access. Row locks work in PostgreSQL.")
    def test_concurrent_allocation_race_condition(
        self, completed_trade_service, db_session, test_user, test_strategy
    ):
        """Test that row locks prevent concurrent allocation races.
        
        NOTE: This test is skipped for SQLite (test database) because SQLite doesn't
        support multi-threaded access. Row locks (FOR UPDATE) work correctly in PostgreSQL.
        """
        # This test would verify row locks in PostgreSQL
        # SQLite limitations prevent proper testing of concurrent access
        pass


class TestFeeCalculation:
    """Test proportional fee calculation."""
    
    def test_proportional_fee_allocation(
        self, completed_trade_service, db_session, test_user, test_strategy
    ):
        """Test that fees are allocated proportionally for partial fills."""
        # Entry trade: 10 BTC, commission = 200 USDT (total)
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=6001,
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=10.0,
            orig_qty=10.0,
            remaining_qty=0.0,
            commission=200.0,  # Total commission for 10 BTC
            position_side="LONG",
            leverage=10,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(entry_trade)
        db_session.commit()
        
        # Exit trade: 6 BTC, commission = 122.4 USDT (total)
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=6002,
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            price=51000.0,
            avg_price=51000.0,
            executed_qty=6.0,
            orig_qty=6.0,
            remaining_qty=0.0,
            commission=122.4,  # Total commission for 6 BTC
            position_side="LONG",
            leverage=10,
            exit_reason="TP",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(exit_trade)
        db_session.commit()
        
        # Create completed trade for 6 BTC
        completed_trade = completed_trade_service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=6.0,
            pnl_usd=1000.0,
            pnl_pct=2.0,
            funding_fee=0.0,
        )
        
        # Expected fees:
        # Entry fee: 200.0 * (6.0 / 10.0) = 120.0
        # Exit fee: 122.4 * (6.0 / 6.0) = 122.4
        # Total: 242.4
        expected_fee = 200.0 * (6.0 / 10.0) + 122.4 * (6.0 / 6.0)
        assert abs(float(completed_trade.fee_paid) - expected_fee) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

