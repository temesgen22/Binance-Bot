"""
Test case for closing SHORT position by SL/TP and verifying correct completed trade creation.

This test verifies the same logic works for reverse scalping strategy (SHORT positions):
1. Entry order (SELL) creates SHORT position with correct position_side
2. Exit order (BUY) with exit_reason (SL/TP) has correct position_side="SHORT"
3. position_instance_id matches between entry and exit
4. Completed trade correctly matches entry (SELL) and exit (BUY) trades
5. position_side is correctly inferred from exit_reason + order side (BUY + exit_reason → SHORT)
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
        strategy_id="test-strategy-reverse",
        name="Test Reverse Scalping Strategy",
        symbol="BTCUSDT",
        strategy_type="reverse_scalping",
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


class TestShortPositionSLTPExit:
    """Test closing SHORT position by SL/TP and verifying correct completed trade creation."""
    
    def test_short_position_closed_by_sl_creates_correct_completed_trade(
        self, db_session, test_user, test_strategy
    ):
        """
        Test that closing SHORT position by SL creates exit trade with correct position_side
        and matches correctly to entry trade for completed trade creation.
        
        This tests reverse scalping strategy behavior.
        """
        # Step 1: Create entry order (SELL SHORT) - Reverse scalping opens SHORT
        entry_order_id = 3001
        entry_price = Decimal("50000.0")
        entry_qty = Decimal("0.1")
        entry_timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        # Create OrderResponse for entry (no exit_reason = opening position)
        entry_order_response = OrderResponse(
            order_id=entry_order_id,
            symbol="BTCUSDT",
            side="SELL",
            position_side=None,  # Will be inferred
            price=float(entry_price),
            executed_qty=float(entry_qty),
            avg_price=float(entry_price),
            status="FILLED",
            order_type="MARKET",
            time_in_force="GTC",
            timestamp=entry_timestamp,
            exit_reason=None,  # ✅ No exit_reason = entry order
        )
        
        # Step 2: Generate position_instance_id for entry order
        is_opening_new_position = True
        position_instance_id = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=is_opening_new_position,
            current_position_size=float(entry_qty)
        )
        
        # Verify instance ID was generated
        assert position_instance_id is not None, "Should generate position_instance_id for new position"
        
        # Step 3: Save entry trade
        trade_service = TradeService(db_session)
        entry_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=entry_order_response,
            position_instance_id=position_instance_id
        )
        db_session.commit()
        
        # Verify entry trade has correct position_side
        assert entry_trade.position_side == "SHORT", \
            f"Entry trade should have position_side='SHORT', got '{entry_trade.position_side}'"
        assert entry_trade.side == "SELL", "Entry trade should be SELL"
        assert entry_trade.position_instance_id == position_instance_id, \
            "Entry trade should have position_instance_id"
        assert entry_trade.exit_reason is None, "Entry trade should have no exit_reason"
        
        # Step 4: Update strategy position state
        test_strategy.position_size = float(entry_qty)
        test_strategy.position_side = "SHORT"
        db_session.commit()
        
        # Step 5: Create exit order (BUY with SL exit_reason) - SHORT closes with BUY
        exit_order_id = 4001
        exit_price = Decimal("51000.0")  # SL hit (price went up)
        exit_qty = Decimal("0.1")
        exit_timestamp = datetime.now(timezone.utc)
        
        # Create OrderResponse for exit (WITH exit_reason = closing position)
        exit_order_response = OrderResponse(
            order_id=exit_order_id,
            symbol="BTCUSDT",
            side="BUY",
            position_side=None,  # Will be inferred from exit_reason + side
            price=float(exit_price),
            executed_qty=float(exit_qty),
            avg_price=float(exit_price),
            status="FILLED",
            order_type="MARKET",
            time_in_force="GTC",
            timestamp=exit_timestamp,
            exit_reason="SL",  # ✅ KEY: exit_reason present = closing position
        )
        
        # Step 6: Get position_instance_id for exit (should reuse existing)
        position_instance_id_exit = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=False,  # Closing position
            current_position_size=0.0
        )
        
        # Verify exit gets same instance ID
        assert position_instance_id_exit == position_instance_id, \
            "Exit order should get same position_instance_id as entry"
        
        # Step 7: Save exit trade
        exit_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=exit_order_response,
            position_instance_id=position_instance_id_exit
        )
        db_session.commit()
        
        # ✅ CRITICAL: Verify exit trade has correct position_side
        # This is the key test - exit trade should have position_side="SHORT" because:
        # - order.side == "BUY"
        # - order.exit_reason == "SL" (present)
        # - Therefore: BUY + exit_reason → SHORT (closing SHORT position)
        assert exit_trade.position_side == "SHORT", \
            f"Exit trade should have position_side='SHORT' (BUY + exit_reason → SHORT), " \
            f"got '{exit_trade.position_side}'"
        assert exit_trade.side == "BUY", "Exit trade should be BUY"
        assert exit_trade.exit_reason == "SL", "Exit trade should have exit_reason='SL'"
        assert exit_trade.position_instance_id == position_instance_id, \
            "Exit trade should have same position_instance_id as entry"
        
        # Step 8: Create completed trades
        completed_trade_ids = create_completed_trades_on_position_close(
            user_id=test_user.id,
            strategy_id=str(test_strategy.id),
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_order_id,
            exit_quantity=float(exit_qty),
            exit_price=float(exit_price),
            position_side="SHORT",  # ✅ Correct position_side
            exit_reason="SL",
            db=db_session
        )
        
        # Verify completed trade was created
        assert len(completed_trade_ids) > 0, \
            f"Should create at least one completed trade, got {len(completed_trade_ids)}"
        
        # Step 9: Verify completed trade matches entry and exit correctly
        completed_trade = db_session.query(CompletedTrade).filter(
            CompletedTrade.id == completed_trade_ids[0]
        ).first()
        
        assert completed_trade is not None, "Completed trade should exist"
        assert completed_trade.strategy_id == test_strategy.id, "Should match strategy"
        assert completed_trade.symbol == "BTCUSDT", "Should match symbol"
        assert completed_trade.side == "SHORT", \
            f"Completed trade should have side='SHORT', got '{completed_trade.side}'"
        
        # ✅ CRITICAL: Verify entry and exit trades are correctly linked
        entry_order_link = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.trade_id == entry_trade.id
        ).first()
        
        exit_order_link = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.trade_id == exit_trade.id
        ).first()
        
        assert entry_order_link is not None, \
            f"Entry trade (order_id={entry_order_id}) should be linked to completed trade"
        assert exit_order_link is not None, \
            f"Exit trade (order_id={exit_order_id}) should be linked to completed trade"
        
        # ✅ CRITICAL: Verify entry and exit are different trades (not matching exit to itself)
        assert entry_trade.id != exit_trade.id, \
            "Entry and exit trades should be different (not matching exit to itself)"
        assert entry_trade.order_id == entry_order_id, \
            f"Entry trade should have order_id={entry_order_id}"
        assert exit_trade.order_id == exit_order_id, \
            f"Exit trade should have order_id={exit_order_id}"
        
        # Verify PnL calculation (SHORT: profit when price goes down, loss when price goes up)
        # Entry: SELL @ 50000, Exit: BUY @ 51000 (price went up) → Loss
        expected_pnl = (float(entry_price) - float(exit_price)) * float(entry_qty)
        assert abs(float(completed_trade.pnl_usd) - expected_pnl) < 0.01, \
            f"PnL should be correct. Expected: {expected_pnl}, Got: {completed_trade.pnl_usd}"
        
        print(f"\n[PASS] Test passed!")
        print(f"   Entry trade: order_id={entry_order_id}, side={entry_trade.side}, "
              f"position_side={entry_trade.position_side}")
        print(f"   Exit trade: order_id={exit_order_id}, side={exit_trade.side}, "
              f"position_side={exit_trade.position_side}, exit_reason={exit_trade.exit_reason}")
        print(f"   Completed trade: side={completed_trade.side}, pnl=${completed_trade.pnl_usd}")
        print(f"   Entry matched: {entry_order_link is not None}, Exit matched: {exit_order_link is not None}")
    
    def test_short_position_closed_by_tp_creates_correct_completed_trade(
        self, db_session, test_user, test_strategy
    ):
        """
        Test that closing SHORT position by TP creates exit trade with correct position_side
        and matches correctly to entry trade for completed trade creation.
        """
        # Step 1: Create entry order (SELL SHORT)
        entry_order_id = 5001
        entry_price = Decimal("50000.0")
        entry_qty = Decimal("0.1")
        
        entry_order_response = OrderResponse(
            order_id=entry_order_id,
            symbol="BTCUSDT",
            side="SELL",
            price=float(entry_price),
            executed_qty=float(entry_qty),
            avg_price=float(entry_price),
            status="FILLED",
            exit_reason=None,  # Entry order
        )
        
        # Generate position_instance_id
        position_instance_id = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=True,
            current_position_size=float(entry_qty)
        )
        
        # Save entry trade
        trade_service = TradeService(db_session)
        entry_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=entry_order_response,
            position_instance_id=position_instance_id
        )
        db_session.commit()
        
        # Verify entry trade
        assert entry_trade.position_side == "SHORT", "Entry trade should be SHORT"
        
        # Step 2: Create exit order (BUY with TP exit_reason)
        exit_order_id = 6001
        exit_price = Decimal("49000.0")  # TP price (price went down)
        exit_qty = Decimal("0.1")
        
        exit_order_response = OrderResponse(
            order_id=exit_order_id,
            symbol="BTCUSDT",
            side="BUY",
            price=float(exit_price),
            executed_qty=float(exit_qty),
            avg_price=float(exit_price),
            status="FILLED",
            exit_reason="TP",  # ✅ Take profit exit
        )
        
        # Get same position_instance_id
        position_instance_id_exit = StrategyPersistence._get_or_generate_position_instance_id(
            db_session,
            test_strategy.id,
            is_opening_new_position=False,
            current_position_size=0.0
        )
        
        assert position_instance_id_exit == position_instance_id, "Should reuse same instance ID"
        
        # Save exit trade
        exit_trade = trade_service.save_trade(
            user_id=test_user.id,
            strategy_id=test_strategy.id,
            order=exit_order_response,
            position_instance_id=position_instance_id_exit
        )
        db_session.commit()
        
        # ✅ CRITICAL: Verify exit trade has correct position_side
        assert exit_trade.position_side == "SHORT", \
            f"Exit trade should have position_side='SHORT' (BUY + exit_reason → SHORT), " \
            f"got '{exit_trade.position_side}'"
        assert exit_trade.exit_reason == "TP", "Exit trade should have exit_reason='TP'"
        
        # Step 3: Create completed trades
        completed_trade_ids = create_completed_trades_on_position_close(
            user_id=test_user.id,
            strategy_id=str(test_strategy.id),
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_order_id,
            exit_quantity=float(exit_qty),
            exit_price=float(exit_price),
            position_side="SHORT",
            exit_reason="TP",
            db=db_session
        )
        
        assert len(completed_trade_ids) > 0, "Should create completed trade"
        
        # Verify completed trade
        completed_trade = db_session.query(CompletedTrade).filter(
            CompletedTrade.id == completed_trade_ids[0]
        ).first()
        
        assert completed_trade.side == "SHORT", "Completed trade should be SHORT"
        # SHORT TP: Entry SELL @ 50000, Exit BUY @ 49000 (price down) → Profit
        assert completed_trade.pnl_usd > 0, "TP trade should have positive PnL"
        
        # Verify entry and exit are linked
        entry_link = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.trade_id == entry_trade.id
        ).first()
        
        exit_link = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.trade_id == exit_trade.id
        ).first()
        
        assert entry_link is not None, "Entry trade should be linked"
        assert exit_link is not None, "Exit trade should be linked"
        assert entry_trade.id != exit_trade.id, "Entry and exit should be different trades"
        
        print(f"\n[PASS] TP exit test passed!")
        print(f"   Entry: {entry_trade.order_id} (SELL, SHORT)")
        print(f"   Exit: {exit_trade.order_id} (BUY, SHORT, TP)")
        print(f"   Completed: side={completed_trade.side}, pnl=${completed_trade.pnl_usd}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

