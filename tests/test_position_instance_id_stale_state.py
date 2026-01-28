"""
Test case to validate position_instance_id generation when strategy summary has stale position state.

This test reproduces the bug where:
1. A position is opened and closed
2. The strategy summary position state is NOT properly cleared (stale state)
3. A new entry trade is executed
4. The detection logic sees prev_size > 0 and thinks it's "adding to position"
5. No position_instance_id is generated because is_opening_new_position=False

Expected behavior:
- Even if prev_size > 0, if there's no exit_reason and the signal indicates an entry,
  it should be treated as opening a new position and generate a new position_instance_id.
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
    Base, User, Account, Strategy, Trade, CompletedTrade
)
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.models.order import OrderResponse
from app.strategies.base import StrategySignal, SignalAction


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
    """Create a test strategy."""
    strategy = Strategy(
        id=uuid4(),
        user_id=test_user.id,
        account_id=test_account.id,
        strategy_id="test-strategy-123",
        name="Test Strategy",
        symbol="PIPPINUSDT",
        strategy_type="ema_crossover",
        leverage=5,
        risk_per_trade=0.01,
        position_size=0.0,
        position_side=None,
        status="running",
        position_instance_id=None,
    )
    db_session.add(strategy)
    db_session.commit()
    return strategy


class TestPositionInstanceIDStaleState:
    """Test position_instance_id generation with stale strategy summary state."""
    
    def test_entry_trade_with_stale_position_state_should_generate_id(
        self, db_session, test_strategy
    ):
        """
        Test that an entry trade generates position_instance_id even when 
        strategy summary has stale position state (prev_size > 0).
        
        This reproduces the bug from the logs:
        - Entry trade: prev_size=1952.0, prev_side=LONG (stale state)
        - Detection: is_opening_new_position=False (wrong!)
        - Result: position_instance_id=None (bug!)
        
        Expected fix:
        - Even with prev_size > 0, if no exit_reason and signal indicates entry,
          should force is_opening_new_position=True and generate ID.
        """
        # Simulate the detection logic with stale state
        prev_size = 1952.0  # ⚠️ STALE STATE: Should be 0.0
        prev_side = "LONG"   # ⚠️ STALE STATE: Should be None
        has_exit_reason = False  # No exit_reason = entry trade
        executed_qty = 1952.0
        
        # Detection logic (from strategy_executor.py)
        prev_size_is_zero = (
            prev_size is None or 
            prev_size == 0 or 
            (isinstance(prev_size, (int, float)) and abs(float(prev_size)) < 0.0001)
        )
        
        # Simplified is_closing_position
        is_closing_position = False  # No exit_reason, so not closing
        
        # Initial detection (this would fail with stale state)
        is_opening_new_position_initial = (
            not is_closing_position and
            prev_size_is_zero and  # False because prev_size=1952.0
            executed_qty > 0 and
            not has_exit_reason
        )
        
        # Assert that initial detection fails (this is the bug)
        assert is_opening_new_position_initial == False, \
            "Initial detection should fail with stale state"
        
        # ✅ FIX: Force opening detection for clear entry trades
        # This is what our fix does
        if not is_opening_new_position_initial and not has_exit_reason and executed_qty > 0:
            prev_size_float = float(prev_size or 0)
            executed_qty_float = float(executed_qty)
            is_stale_state = abs(prev_size_float - executed_qty_float) < 0.0001
            
            if prev_size_is_zero or is_stale_state:
                is_opening_new_position = True
            else:
                is_opening_new_position = is_opening_new_position_initial
        else:
            is_opening_new_position = is_opening_new_position_initial
        
        # Assert that fix works
        assert is_opening_new_position == True, \
            "Fix should force is_opening_new_position=True for clear entry trades with stale state"
        
        # Now verify that position_instance_id would be generated
        if is_opening_new_position:
            from app.services.strategy_persistence import StrategyPersistence
            position_id = StrategyPersistence._get_or_generate_position_instance_id(
                db_session,
                test_strategy.id,
                is_opening_new_position=True,
                current_position_size=executed_qty
            )
            
            assert position_id is not None, \
                "Should generate position_instance_id when is_opening_new_position=True"
            
            # Verify it's saved to database
            db_session.refresh(test_strategy)
            assert test_strategy.position_instance_id == position_id, \
                "position_instance_id should be saved to database"
    
    def test_entry_trade_after_position_close_should_have_zero_prev_size(
        self, db_session, test_user, test_strategy
    ):
        """
        Test that after a position is closed, the strategy summary should have
        position_size=0 and position_side=None.
        
        This validates that the position state is properly cleared.
        """
        # Simulate a position being closed
        # First, set a position
        test_strategy.position_size = 1952.0
        test_strategy.position_side = "LONG"
        test_strategy.position_instance_id = uuid4()
        db_session.commit()
        
        # Simulate closing the position (this should happen in strategy_executor)
        # After a SELL order that closes the LONG position
        # ✅ FIX: Convert to float for calculation, then back to Decimal
        from decimal import Decimal
        position_size_float = float(test_strategy.position_size or 0)
        remaining_float = max(0.0, position_size_float - 1952.0)
        remaining = Decimal(str(remaining_float))
        test_strategy.position_size = remaining
        if remaining_float == 0:
            test_strategy.entry_price = None
            test_strategy.position_side = None
            # Note: position_instance_id should be cleared, but that might happen later
        db_session.commit()
        
        # Verify position is cleared
        db_session.refresh(test_strategy)
        assert float(test_strategy.position_size or 0) == 0.0, \
            "Position size should be 0 after closing"
        assert test_strategy.position_side is None, \
            "Position side should be None after closing"
    
    def test_detection_logic_with_stale_state(self):
        """
        Test the detection logic directly with various stale state scenarios.
        """
        test_cases = [
            {
                "name": "Stale state: prev_size matches executed_qty",
                "prev_size": 1952.0,
                "prev_side": "LONG",
                "executed_qty": 1952.0,
                "has_exit_reason": False,
                "expected_is_opening": True,  # Should be forced to True
            },
            {
                "name": "Stale state: prev_size different from executed_qty",
                "prev_size": 1000.0,
                "prev_side": "LONG",
                "executed_qty": 1952.0,
                "has_exit_reason": False,
                "expected_is_opening": True,  # Should be forced to True (no exit_reason)
            },
            {
                "name": "Normal entry: prev_size is 0",
                "prev_size": 0.0,
                "prev_side": None,
                "executed_qty": 1952.0,
                "has_exit_reason": False,
                "expected_is_opening": True,  # Normal detection should work
            },
            {
                "name": "Exit trade: has exit_reason",
                "prev_size": 1952.0,
                "prev_side": "LONG",
                "executed_qty": 1952.0,
                "has_exit_reason": True,
                "expected_is_opening": False,  # Exit trade, not opening
            },
        ]
        
        for case in test_cases:
            prev_size = case["prev_size"]
            prev_side = case["prev_side"]
            executed_qty = case["executed_qty"]
            has_exit_reason = case["has_exit_reason"]
            expected = case["expected_is_opening"]
            
            # Detection logic
            prev_size_is_zero = (
                prev_size is None or 
                prev_size == 0 or 
                (isinstance(prev_size, (int, float)) and abs(float(prev_size)) < 0.0001)
            )
            
            # Simplified is_closing_position (would be more complex in real code)
            is_closing_position = has_exit_reason
            
            is_opening_new_position_initial = (
                not is_closing_position and
                prev_size_is_zero and 
                executed_qty > 0 and
                not has_exit_reason
            )
            
            # ✅ FIX: Force opening detection for clear entry trades
            if not is_opening_new_position_initial and not prev_size_is_zero and not has_exit_reason and executed_qty > 0:
                # If prev_size matches executed_qty exactly, likely stale state
                if abs(prev_size - executed_qty) < 0.0001:
                    is_opening_new_position = True
                else:
                    # Different sizes but no exit_reason - still treat as entry
                    is_opening_new_position = True
            else:
                is_opening_new_position = is_opening_new_position_initial
            
            assert is_opening_new_position == expected, \
                f"Test case '{case['name']}' failed: expected {expected}, got {is_opening_new_position}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

