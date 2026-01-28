"""
Test case for position_instance_id creation, storage, and matching during entry/exit flow.

This test verifies:
1. Entry order creation generates and stores position_instance_id
2. Position closure matches the instance_id correctly
3. Completed trade is created by matching instance_id
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db_models import (
    Base, User, Account, Strategy, Trade, CompletedTrade, CompletedTradeOrder
)
from app.services.completed_trade_helper import create_completed_trades_on_position_close
from app.services.strategy_persistence import StrategyPersistence
from app.services.trade_service import TradeService
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams


# Test database URL (use in-memory SQLite for testing)
TEST_DATABASE_URL = "sqlite:///:memory:"


# Map JSONB to JSON for SQLite compatibility
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
        testnet=False,
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def test_strategy(db_session, test_user, test_account):
    """Create a test strategy with no position."""
    strategy = Strategy(
        id=uuid4(),
        user_id=test_user.id,
        account_id=test_account.id,
        strategy_id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type="ema_crossover",
        leverage=5,
        risk_per_trade=0.01,
        position_size=0.0,  # No position
        position_side=None,  # No position
        position_instance_id=None,  # No instance ID yet
        status="running",
    )
    db_session.add(strategy)
    db_session.commit()
    return strategy


class TestPositionInstanceIDEntryExitFlow:
    """Test complete flow: entry order -> instance ID generation -> exit order -> completed trade."""
    
    def test_entry_order_creates_instance_id_and_exit_matches_it(
        self, db_session, test_user, test_strategy
    ):
        """
        Test the complete flow:
        1. Create entry order -> generates position_instance_id and stores it
        2. Close position -> matches instance_id correctly
        3. Create completed trade -> matches by instance_id
        """
        # Step 1: Create entry order (BUY LONG)
        entry_order_id = 1001
        entry_price = Decimal("50000.0")
        entry_qty = Decimal("1.0")
        entry_timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        # Create OrderResponse for entry
        entry_order_response = OrderResponse(
            order_id=entry_order_id,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            price=entry_price,
            executed_qty=entry_qty,
            avg_price=entry_price,
            status="FILLED",
            order_type="MARKET",
            time_in_force="GTC",
            timestamp=entry_timestamp,
        )
        
        # Step 2: Generate position_instance_id for entry order
        # This simulates what happens in strategy_executor when opening a new position
        is_opening_new_position = True  # Opening new position
        new_position_size = float(entry_qty)  # Position size after entry
        
        position_instance_id = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=is_opening_new_position,
            current_position_size=new_position_size
        )
        
        # Verify instance ID was generated
        assert position_instance_id is not None, "Should generate position_instance_id for new position"
        assert isinstance(position_instance_id, UUID), "position_instance_id should be a UUID"
        
        # Verify it's stored in strategy
        db_session.refresh(test_strategy)
        assert test_strategy.position_instance_id == position_instance_id, \
            "position_instance_id should be stored in strategy"
        
        # Step 3: Save entry trade with position_instance_id
        trade_service = TradeService(db_session)
        entry_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=entry_order_response,
            position_instance_id=position_instance_id
        )
        db_session.commit()
        
        # Verify entry trade has position_instance_id
        assert entry_trade.position_instance_id == position_instance_id, \
            "Entry trade should have position_instance_id"
        assert entry_trade.side == "BUY", "Entry trade should be BUY"
        assert entry_trade.position_side == "LONG", "Entry trade should be LONG"
        assert entry_trade.status == "FILLED", "Entry trade should be FILLED"
        
        # Step 4: Update strategy position state (simulate position opened)
        test_strategy.position_size = float(entry_qty)
        test_strategy.position_side = "LONG"
        db_session.commit()
        
        # Step 5: Create exit order (SELL LONG)
        exit_order_id = 2001
        exit_price = Decimal("52000.0")
        exit_qty = Decimal("1.0")
        exit_timestamp = datetime.now(timezone.utc)
        
        # Create OrderResponse for exit
        exit_order_response = OrderResponse(
            order_id=exit_order_id,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            price=exit_price,
            executed_qty=exit_qty,
            avg_price=exit_price,
            status="FILLED",
            order_type="MARKET",
            time_in_force="GTC",
            timestamp=exit_timestamp,
            exit_reason="TP",  # Take profit exit
        )
        
        # Step 6: Get position_instance_id for exit order (should reuse existing)
        is_opening_new_position_exit = False  # Not opening, closing
        position_instance_id_exit = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=is_opening_new_position_exit,
            current_position_size=0.0  # Position will be closed
        )
        
        # Verify exit gets same instance ID
        assert position_instance_id_exit == position_instance_id, \
            "Exit order should get same position_instance_id as entry"
        
        # Step 7: Save exit trade with position_instance_id
        exit_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=exit_order_response,
            position_instance_id=position_instance_id_exit
        )
        db_session.commit()
        
        # Verify exit trade has position_instance_id
        assert exit_trade.position_instance_id == position_instance_id, \
            "Exit trade should have same position_instance_id as entry"
        assert exit_trade.side == "SELL", "Exit trade should be SELL"
        assert exit_trade.position_side == "LONG", "Exit trade should be LONG"
        assert exit_trade.status == "FILLED", "Exit trade should be FILLED"
        
        # Step 8: Create completed trades by matching instance_id
        completed_trade_ids = create_completed_trades_on_position_close(
            user_id=test_user.id,
            strategy_id=str(test_strategy.id),
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_order_id,
            exit_quantity=float(exit_qty),
            exit_price=float(exit_price),
            position_side="LONG",
            exit_reason="TP",
            db=db_session  # Pass session for testing
        )
        
        # Verify completed trade was created
        assert len(completed_trade_ids) > 0, "Should create at least one completed trade"
        
        # Step 9: Verify completed trade matches entry and exit by instance_id
        completed_trade = db_session.query(CompletedTrade).filter(
            CompletedTrade.id == completed_trade_ids[0]
        ).first()
        
        assert completed_trade is not None, "Completed trade should exist"
        assert completed_trade.strategy_id == test_strategy.id, "Should match strategy"
        assert completed_trade.symbol == "BTCUSDT", "Should match symbol"
        assert completed_trade.side == "LONG", "Should match position side"
        
        # Verify entry and exit orders are linked
        entry_order_link = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.trade_id == entry_trade.id
        ).first()
        
        exit_order_link = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.trade_id == exit_trade.id
        ).first()
        
        assert entry_order_link is not None, "Entry trade should be linked to completed trade"
        assert exit_order_link is not None, "Exit trade should be linked to completed trade"
        
        # Verify PnL calculation
        expected_pnl = (float(exit_price) - float(entry_price)) * float(entry_qty)
        assert abs(float(completed_trade.pnl_usd) - expected_pnl) < 0.01, \
            f"PnL should be correct. Expected: {expected_pnl}, Got: {completed_trade.pnl_usd}"
        
        # Step 10: Verify position_instance_id is cleared after position closes
        # (This would happen in reconcile_position_state, but we can verify the logic)
        db_session.refresh(test_strategy)
        # Note: In actual flow, position_instance_id is cleared after exit trade is saved
        # For this test, we verify it was used correctly for matching
        
        print(f"\n[PASS] Test passed!")
        print(f"   Entry trade ID: {entry_trade.id}")
        print(f"   Exit trade ID: {exit_trade.id}")
        print(f"   Position instance ID: {position_instance_id}")
        print(f"   Completed trade ID: {completed_trade.id}")
        print(f"   PnL: ${completed_trade.pnl_usd}")
    
    def test_multiple_entries_same_instance_id_and_exit_matches_all(
        self, db_session, test_user, test_strategy
    ):
        """
        Test that multiple entry orders in same position cycle share same instance_id,
        and exit order matches all entries correctly.
        """
        # Step 1: Create first entry order
        entry_order_1_id = 1001
        entry_price_1 = Decimal("50000.0")
        entry_qty_1 = Decimal("0.5")
        entry_timestamp_1 = datetime.now(timezone.utc) - timedelta(minutes=20)
        
        entry_order_1_response = OrderResponse(
            order_id=entry_order_1_id,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            price=entry_price_1,
            executed_qty=entry_qty_1,
            avg_price=entry_price_1,
            status="FILLED",
            order_type="MARKET",
            time_in_force="GTC",
            timestamp=entry_timestamp_1,
        )
        
        # Generate instance ID for first entry
        position_instance_id = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=True,
            current_position_size=float(entry_qty_1)
        )
        
        # Save first entry trade
        trade_service = TradeService(db_session)
        entry_trade_1 = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=entry_order_1_response,
            position_instance_id=position_instance_id
        )
        db_session.commit()
        
        # Step 2: Create second entry order (adding to position)
        entry_order_2_id = 1002
        entry_price_2 = Decimal("51000.0")
        entry_qty_2 = Decimal("0.5")
        entry_timestamp_2 = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        entry_order_2_response = OrderResponse(
            order_id=entry_order_2_id,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            price=entry_price_2,
            executed_qty=entry_qty_2,
            avg_price=entry_price_2,
            status="FILLED",
            order_type="MARKET",
            time_in_force="GTC",
            timestamp=entry_timestamp_2,
        )
        
        # Reuse same instance ID (not opening new position)
        position_instance_id_2 = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=False,  # Adding to existing position
            current_position_size=float(entry_qty_1) + float(entry_qty_2)
        )
        
        # Verify same instance ID
        assert position_instance_id_2 == position_instance_id, \
            "Second entry should reuse same position_instance_id"
        
        # Save second entry trade
        entry_trade_2 = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=entry_order_2_response,
            position_instance_id=position_instance_id_2
        )
        db_session.commit()
        
        # Verify both entries have same instance ID
        assert entry_trade_1.position_instance_id == entry_trade_2.position_instance_id, \
            "Both entry trades should have same position_instance_id"
        
        # Step 3: Create exit order (closes entire position)
        exit_order_id = 2001
        exit_price = Decimal("52000.0")
        exit_qty = Decimal("1.0")  # Closes both entries
        exit_timestamp = datetime.now(timezone.utc)
        
        exit_order_response = OrderResponse(
            order_id=exit_order_id,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            price=exit_price,
            executed_qty=exit_qty,
            avg_price=exit_price,
            status="FILLED",
            order_type="MARKET",
            time_in_force="GTC",
            timestamp=exit_timestamp,
            exit_reason="TP",
        )
        
        # Get instance ID for exit (should be same)
        position_instance_id_exit = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=False,
            current_position_size=0.0
        )
        
        assert position_instance_id_exit == position_instance_id, \
            "Exit should use same position_instance_id"
        
        # Save exit trade
        exit_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=exit_order_response,
            position_instance_id=position_instance_id_exit
        )
        db_session.commit()
        
        # Step 4: Create completed trades (should match both entries)
        completed_trade_ids = create_completed_trades_on_position_close(
            user_id=test_user.id,
            strategy_id=str(test_strategy.id),
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_order_id,
            exit_quantity=float(exit_qty),
            exit_price=float(exit_price),
            position_side="LONG",
            exit_reason="TP",
            db=db_session
        )
        
        # Should create 2 completed trades (one for each entry)
        assert len(completed_trade_ids) == 2, \
            f"Should create 2 completed trades (one per entry), got {len(completed_trade_ids)}"
        
        # Verify both entries are matched
        completed_trades = db_session.query(CompletedTrade).filter(
            CompletedTrade.id.in_(completed_trade_ids)
        ).all()
        
        assert len(completed_trades) == 2, "Should have 2 completed trades"
        
        # Verify each completed trade links to correct entry
        entry_1_matched = False
        entry_2_matched = False
        
        for completed_trade in completed_trades:
            entry_orders = db_session.query(CompletedTradeOrder).filter(
                CompletedTradeOrder.completed_trade_id == completed_trade.id,
                CompletedTradeOrder.trade_id.in_([entry_trade_1.id, entry_trade_2.id])
            ).all()
            
            for order_link in entry_orders:
                if order_link.trade_id == entry_trade_1.id:
                    entry_1_matched = True
                if order_link.trade_id == entry_trade_2.id:
                    entry_2_matched = True
        
        assert entry_1_matched, "Entry trade 1 should be matched"
        assert entry_2_matched, "Entry trade 2 should be matched"
        
        print(f"\n[PASS] Test passed!")
        print(f"   Entry trade 1 ID: {entry_trade_1.id}, Instance ID: {entry_trade_1.position_instance_id}")
        print(f"   Entry trade 2 ID: {entry_trade_2.id}, Instance ID: {entry_trade_2.position_instance_id}")
        print(f"   Exit trade ID: {exit_trade.id}, Instance ID: {exit_trade.position_instance_id}")
        print(f"   Completed trades: {len(completed_trade_ids)}")
        print(f"   All entries matched: {entry_1_matched and entry_2_matched}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

