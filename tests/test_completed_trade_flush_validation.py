"""
Test case to validate the flush() fix for CompletedTradeOrder validation.

This test specifically validates that:
1. CompletedTradeOrder records are flushed before validation query
2. Validation query can see the newly created records
3. The fix prevents "Entry quantities don't match" errors
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db_models import (
    Base, User, Account, Strategy, Trade, CompletedTrade, CompletedTradeOrder
)
from app.services.completed_trade_service import CompletedTradeService


@pytest.fixture
def db_session():
    """Create a test database session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    from sqlalchemy.schema import CheckConstraint
    
    TEST_DATABASE_URL = "sqlite:///:memory:"
    
    # Map JSONB to JSON for SQLite compatibility
    if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
        def visit_JSONB(self, type_, **kw):
            return "JSON"
        SQLiteTypeCompiler.visit_JSONB = visit_JSONB
        SQLiteTypeCompiler._visit_JSONB_patched = True
    
    engine = create_engine(TEST_DATABASE_URL, echo=False)
    
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
        api_key_encrypted="test_key",
        api_secret_encrypted="test_secret",
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
    db_session.add(strategy)
    db_session.commit()
    return strategy


@pytest.fixture
def entry_trade(db_session, test_user, test_strategy):
    """Create an entry trade (BUY order)."""
    trade = Trade(
        id=uuid4(),
        user_id=test_user.id,
        strategy_id=test_strategy.id,
        order_id=1001,
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        status="FILLED",
        price=Decimal("50000.0"),
        avg_price=Decimal("50000.0"),
        executed_qty=Decimal("0.1"),
        position_side="LONG",
        timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()
    return trade


@pytest.fixture
def exit_trade(db_session, test_user, test_strategy):
    """Create an exit trade (SELL order)."""
    trade = Trade(
        id=uuid4(),
        user_id=test_user.id,
        strategy_id=test_strategy.id,
        order_id=1002,
        symbol="BTCUSDT",
        side="SELL",
        order_type="MARKET",
        status="FILLED",
        price=Decimal("51000.0"),
        avg_price=Decimal("51000.0"),
        executed_qty=Decimal("0.1"),
        position_side="LONG",
        exit_reason="TAKE_PROFIT",
        timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(trade)
    db_session.commit()
    return trade


class TestCompletedTradeFlushValidation:
    """Test that CompletedTradeOrder records are flushed before validation."""
    
    def test_completed_trade_validation_sees_flushed_records(
        self,
        db_session: Session,
        test_user,
        test_strategy,
        entry_trade,
        exit_trade,
    ):
        """Test that validation query can see CompletedTradeOrder records after flush.
        
        This test validates the fix for the issue where validation was failing because
        CompletedTradeOrder records weren't flushed before the validation query ran.
        """
        service = CompletedTradeService(db_session)
        
        # Create completed trade
        quantity = 0.1
        pnl_usd = (51000.0 - 50000.0) * quantity  # 100.0
        pnl_pct = (pnl_usd / (50000.0 * quantity)) * 100  # 2.0%
        
        completed_trade = service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=quantity,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            funding_fee=0.0,
        )
        
        # Verify completed trade was created
        assert completed_trade is not None
        assert float(completed_trade.quantity) == quantity
        assert float(completed_trade.pnl_usd) == pnl_usd
        
        # Verify CompletedTradeOrder records were created
        entry_orders = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).all()
        
        exit_orders = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "EXIT"
        ).all()
        
        assert len(entry_orders) == 1, "Should have exactly one ENTRY CompletedTradeOrder"
        assert len(exit_orders) == 1, "Should have exactly one EXIT CompletedTradeOrder"
        
        # Verify quantities match
        entry_order = entry_orders[0]
        exit_order = exit_orders[0]
        
        assert float(entry_order.quantity) == quantity
        assert float(exit_order.quantity) == quantity
        assert entry_order.trade_id == entry_trade.id
        assert exit_order.trade_id == exit_trade.id
        
        # Verify validation query can see the records (this is what the fix ensures)
        entry_sum = db_session.query(
            func.sum(CompletedTradeOrder.quantity)
        ).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).scalar() or 0.0
        
        exit_sum = db_session.query(
            func.sum(CompletedTradeOrder.quantity)
        ).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "EXIT"
        ).scalar() or 0.0
        
        # This should pass because records are flushed before validation
        assert abs(float(entry_sum) - quantity) < 0.0001, \
            f"Entry sum {entry_sum} should equal quantity {quantity}"
        assert abs(float(exit_sum) - quantity) < 0.0001, \
            f"Exit sum {exit_sum} should equal quantity {quantity}"
    
    def test_partial_fill_validation_works(
        self,
        db_session: Session,
        test_user,
        test_strategy,
        entry_trade,
    ):
        """Test that partial fill validation works correctly with flush."""
        service = CompletedTradeService(db_session)
        
        # Create first exit trade
        exit_trade_1 = Trade(
            id=uuid4(),
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order_id=2001,
            symbol="BTCUSDT",
            side="SELL",
            order_type="MARKET",
            status="FILLED",
            price=Decimal("51000.0"),
            avg_price=Decimal("51000.0"),
            executed_qty=Decimal("0.1"),
            position_side="LONG",
            exit_reason="TAKE_PROFIT",
            timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        )
        db_session.add(exit_trade_1)
        db_session.commit()
        
        # Create first completed trade (partial fill)
        quantity_1 = 0.05
        pnl_usd_1 = (51000.0 - 50000.0) * quantity_1
        
        completed_trade_1 = service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade_1.id,
            quantity=quantity_1,
            pnl_usd=pnl_usd_1,
            pnl_pct=2.0,
            funding_fee=0.0,
        )
        
        # Verify first trade was created
        assert completed_trade_1 is not None
        
        # Create second exit trade (different order_id to avoid idempotency)
        exit_trade_2 = Trade(
            id=uuid4(),
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order_id=2002,
            symbol="BTCUSDT",
            side="SELL",
            order_type="MARKET",
            status="FILLED",
            price=Decimal("51000.0"),
            avg_price=Decimal("51000.0"),
            executed_qty=Decimal("0.1"),
            position_side="LONG",
            exit_reason="TAKE_PROFIT",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        db_session.add(exit_trade_2)
        db_session.commit()
        
        # Create second completed trade (remaining quantity)
        quantity_2 = 0.05
        pnl_usd_2 = (51000.0 - 50000.0) * quantity_2
        
        completed_trade_2 = service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade_2.id,
            quantity=quantity_2,
            pnl_usd=pnl_usd_2,
            pnl_pct=2.0,
            funding_fee=0.0,
        )
        
        # Verify second trade was created
        assert completed_trade_2 is not None
        
        # Verify both CompletedTradeOrder records exist and quantities match
        all_entry_orders = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.trade_id == entry_trade.id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).all()
        
        all_exit_orders = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.trade_id.in_([exit_trade_1.id, exit_trade_2.id]),
            CompletedTradeOrder.order_role == "EXIT"
        ).all()
        
        assert len(all_entry_orders) == 2, "Should have 2 ENTRY CompletedTradeOrder records"
        assert len(all_exit_orders) == 2, "Should have 2 EXIT CompletedTradeOrder records"
        
        # Verify total quantities match
        total_entry_qty = sum(float(o.quantity) for o in all_entry_orders)
        total_exit_qty = sum(float(o.quantity) for o in all_exit_orders)
        
        assert abs(total_entry_qty - 0.1) < 0.0001, \
            f"Total entry quantity {total_entry_qty} should equal 0.1"
        assert abs(total_exit_qty - 0.1) < 0.0001, \
            f"Total exit quantity {total_exit_qty} should equal 0.1"
    
    def test_validation_query_sees_records_immediately(
        self,
        db_session: Session,
        test_user,
        test_strategy,
        entry_trade,
        exit_trade,
    ):
        """Test that validation query can see records immediately after creation.
        
        This is the critical test - it verifies that the flush() fix works.
        Before the fix, this would fail because records weren't visible in the query.
        """
        service = CompletedTradeService(db_session)
        
        quantity = 0.1
        pnl_usd = 100.0
        pnl_pct = 2.0
        
        # This should NOT raise an error (before the fix, it would fail validation)
        completed_trade = service.create_completed_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            entry_trade_id=entry_trade.id,
            exit_trade_id=exit_trade.id,
            quantity=quantity,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            funding_fee=0.0,
        )
        
        # If we get here, the validation passed (records were visible)
        assert completed_trade is not None
        
        # Double-check by querying immediately
        entry_sum = db_session.query(
            func.sum(CompletedTradeOrder.quantity)
        ).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).scalar()
        
        assert entry_sum is not None, "Entry sum should not be None"
        assert abs(float(entry_sum) - quantity) < 0.0001, \
            f"Entry sum {entry_sum} should equal quantity {quantity} immediately after creation"

