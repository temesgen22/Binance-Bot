"""
Test cases for verifying completed trades are stored during live trading.

Tests verify:
1. Completed trades are created when positions close in live trading
2. Entry and exit trades are properly matched
3. CompletedTrade records are stored in database
4. CompletedTradeOrder junction records are created
5. PnL calculations are correct
6. Partial fills are handled correctly
7. Multiple entry trades are matched correctly (FIFO)
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from uuid import UUID, uuid4
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db_models import (
    Base, User, Account, Strategy, Trade, CompletedTrade, CompletedTradeOrder
)
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.services.completed_trade_helper import create_completed_trades_on_position_close
from app.services.completed_trade_service import CompletedTradeService
from app.services.strategy_executor import StrategyExecutor


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
        account_id=test_account.id,
        strategy_id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type="scalping",
        leverage=5,
        risk_per_trade=0.01,
        status="running",
    )
    db_session.add(strategy)
    db_session.commit()
    return strategy


@pytest.fixture
def entry_trade(db_session, test_user, test_strategy):
    """Create an entry trade (BUY for LONG position)."""
    trade = Trade(
        id=uuid4(),
        strategy_id=test_strategy.id,
        user_id=test_user.id,
        order_id=100001,
        symbol="BTCUSDT",
        side="BUY",
        position_side="LONG",
        price=Decimal("50000.00"),
        avg_price=Decimal("50000.00"),
        executed_qty=Decimal("0.1"),
        orig_qty=Decimal("0.1"),
        remaining_qty=Decimal("0.0"),
        status="FILLED",
        commission=Decimal("2.00"),  # 0.04% of 50,000 * 0.1 = 2.00
        timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        leverage=5,
    )
    db_session.add(trade)
    db_session.commit()
    return trade


@pytest.fixture
def exit_trade(db_session, test_user, test_strategy):
    """Create an exit trade (SELL for closing LONG position)."""
    trade = Trade(
        id=uuid4(),
        strategy_id=test_strategy.id,
        user_id=test_user.id,
        order_id=100002,
        symbol="BTCUSDT",
        side="SELL",
        position_side="LONG",
        price=Decimal("51000.00"),
        avg_price=Decimal("51000.00"),
        executed_qty=Decimal("0.1"),
        orig_qty=Decimal("0.1"),
        remaining_qty=Decimal("0.0"),
        status="FILLED",
        commission=Decimal("2.04"),  # 0.04% of 51,000 * 0.1 = 2.04
        timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        leverage=5,
        exit_reason="TAKE_PROFIT",
    )
    db_session.add(trade)
    db_session.commit()
    return trade


class TestLiveTradingCompletedTrades:
    """Test completed trade creation during live trading scenarios."""
    
    def test_completed_trade_created_on_position_close(
        self,
        db_session,
        test_user,
        test_strategy,
        entry_trade,
        exit_trade,
    ):
        """Test that completed trade is created when position closes in live trading."""
        # Simulate position close: call the helper function
        completed_trade_ids = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,  # Use strategy_id string
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=51000.0,
            position_side="LONG",
            exit_reason="TAKE_PROFIT",
        )
        
        # Verify completed trade was created
        assert len(completed_trade_ids) == 1, "Should create exactly one completed trade"
        
        # Query the completed trade
        completed_trade = db_session.query(CompletedTrade).filter(
            CompletedTrade.id == completed_trade_ids[0]
        ).first()
        
        assert completed_trade is not None, "Completed trade should exist in database"
        assert completed_trade.strategy_id == test_strategy.id
        assert completed_trade.user_id == test_user.id
        assert completed_trade.symbol == "BTCUSDT"
        assert completed_trade.side == "LONG"
        assert float(completed_trade.quantity) == 0.1
        assert float(completed_trade.entry_price) == 50000.0
        assert float(completed_trade.exit_price) == 51000.0
        assert completed_trade.exit_reason == "TAKE_PROFIT"
        
        # Verify PnL calculation
        # LONG: (exit_price - entry_price) * quantity - fees
        # (51000 - 50000) * 0.1 - (2.00 + 2.04) = 1000 - 4.04 = 995.96
        expected_pnl = (51000.0 - 50000.0) * 0.1 - (2.00 + 2.04)
        assert abs(float(completed_trade.pnl_usd) - expected_pnl) < 0.01
        
        # Verify entry and exit order links
        entry_orders = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).all()
        
        assert len(entry_orders) == 1, "Should have one entry order link"
        assert entry_orders[0].trade_id == entry_trade.id
        assert entry_orders[0].order_id == entry_trade.order_id
        assert float(entry_orders[0].quantity) == 0.1
        
        exit_orders = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "EXIT"
        ).all()
        
        assert len(exit_orders) == 1, "Should have one exit order link"
        assert exit_orders[0].trade_id == exit_trade.id
        assert exit_orders[0].order_id == exit_trade.order_id
        assert float(exit_orders[0].quantity) == 0.1
    
    def test_multiple_entry_trades_matched_fifo(
        self,
        db_session,
        test_user,
        test_strategy,
    ):
        """Test that multiple entry trades are matched using FIFO (oldest first)."""
        # Create multiple entry trades
        entry1 = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100001,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            price=Decimal("50000.00"),
            avg_price=Decimal("50000.00"),
            executed_qty=Decimal("0.05"),
            status="FILLED",
            commission=Decimal("1.00"),
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(entry1)
        
        entry2 = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100002,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            price=Decimal("51000.00"),
            avg_price=Decimal("51000.00"),
            executed_qty=Decimal("0.05"),
            status="FILLED",
            commission=Decimal("1.02"),
            timestamp=datetime(2024, 1, 1, 10, 30, 0, tzinfo=timezone.utc),  # Later timestamp
            leverage=5,
        )
        db_session.add(entry2)
        db_session.commit()
        
        # Create exit trade that closes entire position (0.1 total)
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100003,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            price=Decimal("52000.00"),
            avg_price=Decimal("52000.00"),
            executed_qty=Decimal("0.1"),
            status="FILLED",
            commission=Decimal("2.08"),
            timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(exit_trade)
        db_session.commit()
        
        # Create completed trades
        completed_trade_ids = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=52000.0,
            position_side="LONG",
        )
        
        # Should create 2 completed trades (one for each entry)
        assert len(completed_trade_ids) == 2, "Should create 2 completed trades for 2 entry trades"
        
        # Verify FIFO: entry1 (older) should be matched first
        completed_trades = db_session.query(CompletedTrade).filter(
            CompletedTrade.id.in_(completed_trade_ids)
        ).order_by(CompletedTrade.entry_time.asc()).all()
        
        assert len(completed_trades) == 2
        
        # First completed trade should match entry1
        ct1 = completed_trades[0]
        assert float(ct1.entry_price) == 50000.0, "First match should be entry1 (older)"
        assert float(ct1.quantity) == 0.05
        
        # Second completed trade should match entry2
        ct2 = completed_trades[1]
        assert float(ct2.entry_price) == 51000.0, "Second match should be entry2 (newer)"
        assert float(ct2.quantity) == 0.05
    
    def test_partial_fill_matching(
        self,
        db_session,
        test_user,
        test_strategy,
    ):
        """Test that partial fills are handled correctly."""
        # Create entry trade with 0.1 BTC
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100001,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            price=Decimal("50000.00"),
            avg_price=Decimal("50000.00"),
            executed_qty=Decimal("0.1"),
            status="FILLED",
            commission=Decimal("2.00"),
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(entry_trade)
        db_session.commit()
        
        # First exit: close 0.03 BTC
        exit1 = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100002,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            price=Decimal("51000.00"),
            avg_price=Decimal("51000.00"),
            executed_qty=Decimal("0.03"),
            status="FILLED",
            commission=Decimal("0.612"),  # 0.04% of 51,000 * 0.03
            timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(exit1)
        db_session.commit()
        
        # Create first completed trade
        completed_trade_ids_1 = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit1.id,
            exit_order_id=exit1.order_id,
            exit_quantity=0.03,
            exit_price=51000.0,
            position_side="LONG",
        )
        
        assert len(completed_trade_ids_1) == 1
        
        # Second exit: close remaining 0.07 BTC
        exit2 = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100003,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            price=Decimal("52000.00"),
            avg_price=Decimal("52000.00"),
            executed_qty=Decimal("0.07"),
            status="FILLED",
            commission=Decimal("1.456"),  # 0.04% of 52,000 * 0.07
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(exit2)
        db_session.commit()
        
        # Create second completed trade
        completed_trade_ids_2 = create_completed_trades_on_position_close(
            db=db_session,
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit2.id,
            exit_order_id=exit2.order_id,
            exit_quantity=0.07,
            exit_price=52000.0,
            position_side="LONG",
        )
        
        assert len(completed_trade_ids_2) == 1
        
        # Verify both completed trades link to same entry trade
        all_completed = db_session.query(CompletedTrade).filter(
            CompletedTrade.id.in_(completed_trade_ids_1 + completed_trade_ids_2)
        ).all()
        
        assert len(all_completed) == 2
        
        # Verify quantities sum to entry trade quantity
        total_quantity = sum(float(ct.quantity) for ct in all_completed)
        assert abs(total_quantity - 0.1) < 0.0001, "Total quantity should match entry trade"
        
        # Verify entry order links both point to same entry trade
        for ct in all_completed:
            entry_orders = db_session.query(CompletedTradeOrder).filter(
                CompletedTradeOrder.completed_trade_id == ct.id,
                CompletedTradeOrder.order_role == "ENTRY"
            ).all()
            assert len(entry_orders) == 1
            assert entry_orders[0].trade_id == entry_trade.id
    
    def test_short_position_completed_trade(
        self,
        db_session,
        test_user,
        test_strategy,
    ):
        """Test completed trade creation for SHORT position."""
        # Entry: SELL (opens SHORT)
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100001,
            symbol="BTCUSDT",
            side="SELL",
            position_side="SHORT",
            price=Decimal("50000.00"),
            avg_price=Decimal("50000.00"),
            executed_qty=Decimal("0.1"),
            status="FILLED",
            commission=Decimal("2.00"),
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(entry_trade)
        db_session.commit()
        
        # Exit: BUY (closes SHORT)
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100002,
            symbol="BTCUSDT",
            side="BUY",
            position_side="SHORT",
            price=Decimal("49000.00"),  # Lower price = profit for SHORT
            avg_price=Decimal("49000.00"),
            executed_qty=Decimal("0.1"),
            status="FILLED",
            commission=Decimal("1.96"),  # 0.04% of 49,000 * 0.1
            timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(exit_trade)
        db_session.commit()
        
        # Create completed trade
        completed_trade_ids = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=49000.0,
            position_side="SHORT",
        )
        
        assert len(completed_trade_ids) == 1
        
        completed_trade = db_session.query(CompletedTrade).filter(
            CompletedTrade.id == completed_trade_ids[0]
        ).first()
        
        assert completed_trade.side == "SHORT"
        
        # Verify PnL for SHORT: (entry_price - exit_price) * quantity - fees
        # (50000 - 49000) * 0.1 - (2.00 + 1.96) = 1000 - 3.96 = 996.04
        expected_pnl = (50000.0 - 49000.0) * 0.1 - (2.00 + 1.96)
        assert abs(float(completed_trade.pnl_usd) - expected_pnl) < 0.01
    
    def test_skip_when_strategy_not_found(
        self,
        db_session,
        test_user,
        entry_trade,
        exit_trade,
    ):
        """Test that function returns empty list when strategy not found."""
        # Use non-existent strategy_id
        completed_trade_ids = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id="non-existent-strategy",
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=51000.0,
            position_side="LONG",
        )
        
        assert completed_trade_ids == [], "Should return empty list when strategy not found"
        
        # Verify no completed trades were created
        count = db_session.query(CompletedTrade).count()
        assert count == 0, "No completed trades should be created"
    
    def test_skip_when_exit_trade_not_found(
        self,
        db_session,
        test_user,
        test_strategy,
        entry_trade,
    ):
        """Test that function returns empty list when exit trade not found."""
        # Use non-existent exit_trade_id
        fake_exit_trade_id = uuid4()
        
        completed_trade_ids = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=fake_exit_trade_id,
            exit_order_id=100002,
            exit_quantity=0.1,
            exit_price=51000.0,
            position_side="LONG",
        )
        
        assert completed_trade_ids == [], "Should return empty list when exit trade not found"
        
        # Verify no completed trades were created
        count = db_session.query(CompletedTrade).count()
        assert count == 0, "No completed trades should be created"
    
    def test_skip_when_no_entry_trades(
        self,
        db_session,
        test_user,
        test_strategy,
        exit_trade,
    ):
        """Test that function returns empty list when no entry trades exist."""
        # No entry trades created
        
        completed_trade_ids = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=51000.0,
            position_side="LONG",
        )
        
        assert completed_trade_ids == [], "Should return empty list when no entry trades"
        
        # Verify no completed trades were created
        count = db_session.query(CompletedTrade).count()
        assert count == 0, "No completed trades should be created"
    
    def test_idempotency_prevents_duplicates(
        self,
        db_session,
        test_user,
        test_strategy,
        entry_trade,
        exit_trade,
    ):
        """Test that calling the function twice with same parameters doesn't create duplicates."""
        # First call
        completed_trade_ids_1 = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=51000.0,
            position_side="LONG",
        )
        
        assert len(completed_trade_ids_1) == 1
        
        # Second call with same parameters (should be idempotent)
        completed_trade_ids_2 = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=51000.0,
            position_side="LONG",
        )
        
        # Should return empty list (already exists, skipped)
        # OR return the same ID (idempotency check returns existing)
        assert len(completed_trade_ids_2) <= 1
        
        # Verify only one completed trade exists
        count = db_session.query(CompletedTrade).count()
        assert count == 1, "Should have only one completed trade (idempotency)"
    
    def test_proportional_fee_calculation(
        self,
        db_session,
        test_user,
        test_strategy,
    ):
        """Test that fees are calculated proportionally for partial fills."""
        # Entry trade: 0.1 BTC, commission 2.00
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100001,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            price=Decimal("50000.00"),
            avg_price=Decimal("50000.00"),
            executed_qty=Decimal("0.1"),
            status="FILLED",
            commission=Decimal("2.00"),
            timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(entry_trade)
        db_session.commit()
        
        # Exit trade: close 0.03 BTC (30% of entry)
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100002,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            price=Decimal("51000.00"),
            avg_price=Decimal("51000.00"),
            executed_qty=Decimal("0.03"),
            status="FILLED",
            commission=Decimal("0.612"),  # 0.04% of 51,000 * 0.03
            timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            leverage=5,
        )
        db_session.add(exit_trade)
        db_session.commit()
        
        # Create completed trade
        completed_trade_ids = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.03,
            exit_price=51000.0,
            position_side="LONG",
        )
        
        assert len(completed_trade_ids) == 1
        
        completed_trade = db_session.query(CompletedTrade).filter(
            CompletedTrade.id == completed_trade_ids[0]
        ).first()
        
        # Entry fee should be proportional: 2.00 * (0.03 / 0.1) = 0.60
        # Exit fee: 0.612 (full exit commission)
        # Total fee: 0.60 + 0.612 = 1.212
        expected_entry_fee = 2.00 * (0.03 / 0.1)
        expected_total_fee = expected_entry_fee + 0.612
        
        assert abs(float(completed_trade.fee_paid) - expected_total_fee) < 0.01


class TestLiveTradingIntegration:
    """Integration tests simulating full live trading flow."""
    
    def test_simulated_live_trading_flow(
        self,
        db_session,
        test_user,
        test_strategy,
    ):
        """Test simulated live trading flow: entry -> exit -> completed trade creation.
        
        This test simulates what happens during live trading:
        1. Entry trade is saved to database
        2. Exit trade is saved to database
        3. Completed trade creation is triggered (as it would be in strategy_executor)
        4. Verify completed trade is stored correctly
        """
        # Simulate entry trade execution (as would happen in live trading)
        entry_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100001,
            symbol="BTCUSDT",
            side="BUY",
            position_side="LONG",
            price=Decimal("50000.00"),
            avg_price=Decimal("50000.00"),
            executed_qty=Decimal("0.1"),
            status="FILLED",
            commission=Decimal("2.00"),
            timestamp=datetime.now(timezone.utc),
            leverage=5,
        )
        db_session.add(entry_trade)
        db_session.commit()
        
        # Simulate exit trade execution (as would happen in live trading)
        exit_trade = Trade(
            id=uuid4(),
            strategy_id=test_strategy.id,
            user_id=test_user.id,
            order_id=100002,
            symbol="BTCUSDT",
            side="SELL",
            position_side="LONG",
            price=Decimal("51000.00"),
            avg_price=Decimal("51000.00"),
            executed_qty=Decimal("0.1"),
            status="FILLED",
            commission=Decimal("2.04"),
            timestamp=datetime.now(timezone.utc),
            leverage=5,
        )
        db_session.add(exit_trade)
        db_session.commit()
        
        # Simulate completed trade creation (as would be called from strategy_executor)
        completed_trade_ids = create_completed_trades_on_position_close(
            db=db_session,  # Pass test session for testing
            user_id=test_user.id,
            strategy_id=test_strategy.strategy_id,
            exit_trade_id=exit_trade.id,
            exit_order_id=exit_trade.order_id,
            exit_quantity=0.1,
            exit_price=51000.0,
            position_side="LONG",
        )
        
        # Verify completed trade was created and stored
        assert len(completed_trade_ids) == 1, "Should create exactly one completed trade"
        
        completed_trade = db_session.query(CompletedTrade).filter(
            CompletedTrade.id == completed_trade_ids[0]
        ).first()
        
        assert completed_trade is not None, "Completed trade should exist in database"
        assert completed_trade.symbol == "BTCUSDT"
        assert completed_trade.side == "LONG"
        assert float(completed_trade.quantity) == 0.1
        assert completed_trade.strategy_id == test_strategy.id
        assert completed_trade.user_id == test_user.id
        
        # Verify links to entry and exit trades (via CompletedTradeOrder junction table)
        entry_links = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).all()
        assert len(entry_links) == 1, "Should have one entry order link"
        assert entry_links[0].trade_id == entry_trade.id
        assert entry_links[0].order_id == entry_trade.order_id
        
        exit_links = db_session.query(CompletedTradeOrder).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "EXIT"
        ).all()
        assert len(exit_links) == 1, "Should have one exit order link"
        assert exit_links[0].trade_id == exit_trade.id
        assert exit_links[0].order_id == exit_trade.order_id
        
        # Verify PnL calculation
        expected_pnl = (51000.0 - 50000.0) * 0.1 - (2.00 + 2.04)
        assert abs(float(completed_trade.pnl_usd) - expected_pnl) < 0.01

