"""
Verification script for daily/weekly limit pause functionality.

This script verifies that:
1. pause_all_strategies_for_account() is blocking (not background task)
2. Positions are closed when strategies are paused
3. TP/SL orders are cancelled when strategies are paused
4. Status is updated to paused_by_risk
5. All strategies for the account are paused

Run with: python verify_pause_functionality.py
"""

import asyncio
import sys
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to path
sys.path.insert(0, '.')

from app.services.strategy_runner import StrategyRunner
from app.models.strategy import StrategySummary, StrategyState
from app.models.db_models import Strategy, User, Account
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.db_models import Base

# Test database URL (in-memory SQLite)
TEST_DB_URL = "sqlite:///:memory:"

# Map JSONB to JSON for SQLite compatibility
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    def visit_JSONB(self, type_, **kw):
        return "JSON"
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True


async def verify_pause_functionality():
    """Verify that pause_all_strategies_for_account works correctly."""
    
    print("=" * 80)
    print("VERIFICATION: Daily/Weekly Limit Pause Functionality")
    print("=" * 80)
    
    # Setup test database
    engine = create_engine(TEST_DB_URL, echo=False)
    
    # Remove PostgreSQL-specific CHECK constraints for SQLite
    from sqlalchemy.schema import CheckConstraint
    from sqlalchemy.dialects.sqlite.base import SQLiteDDLCompiler
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
    
    # Remove constraints from metadata
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
    db = SessionLocal()
    
    try:
        # Create test user and account
        user = User(
            id=uuid4(),
            username="testuser",
            email="test@example.com",
            password_hash="hashed",
            is_active=True
        )
        db.add(user)
        
        account = Account(
            id=uuid4(),
            user_id=user.id,
            account_id="default",
            name="Test Account",
            api_key_encrypted="test_key",
            api_secret_encrypted="test_secret",
            testnet=True,
            is_active=True,
            is_default=True
        )
        db.add(account)
        
        # Create test strategies
        strategies = []
        for i in range(3):
            strategy = Strategy(
                id=uuid4(),
                user_id=user.id,
                account_id=account.id,
                strategy_id=f"strategy-{i+1}",
                name=f"Strategy {i+1}",
                symbol="BTCUSDT",
                strategy_type="scalping",
                leverage=5,
                risk_per_trade=Decimal("0.01"),
                fixed_amount=Decimal("1000.0"),
                max_positions=1,
                params={},
                status="running"
            )
            db.add(strategy)
            strategies.append(strategy)
        
        db.commit()
        
        # Create StrategyRunner
        from app.services.strategy_service import StrategyService
        from app.services.database_service import DatabaseService
        from app.core.redis_storage import RedisStorage
        from app.core.binance_client_manager import BinanceClientManager
        
        db_service = DatabaseService(db)
        strategy_service = StrategyService(db)
        
        redis_storage = MagicMock(spec=RedisStorage)
        redis_storage.enabled = False
        
        client_manager = MagicMock(spec=BinanceClientManager)
        
        runner = StrategyRunner(
            client_manager=client_manager,
            strategy_service=strategy_service,
            user_id=user.id,
            redis_storage=redis_storage,
        )
        
        # Mock BinanceClient
        mock_client = MagicMock()
        mock_client.get_open_position = MagicMock(return_value={
            "positionAmt": "0.001",
            "entryPrice": "40000.0",
            "unRealizedProfit": "-5.50",
            "markPrice": "40000.0"
        })
        mock_client.close_position = MagicMock(return_value=MagicMock(
            side="SELL",
            symbol="BTCUSDT",
            executed_qty=0.001,
            avg_price=40000.0,
            price=40000.0,
            order_id=12345,
            status="FILLED"
        ))
        
        runner.client_manager.get_client = MagicMock(return_value=mock_client)
        runner._get_account_client = MagicMock(return_value=mock_client)
        
        # Mock order manager
        mock_order_manager = MagicMock()
        mock_order_manager.cancel_tp_sl_orders = AsyncMock()
        runner.order_manager = mock_order_manager
        
        # Mock trade service
        mock_trade_service = MagicMock()
        mock_trade_service.save_trade = MagicMock()
        runner.trade_service = mock_trade_service
        
        # Add strategies to in-memory cache with positions
        for strategy in strategies:
            summary = StrategySummary(
                id=strategy.strategy_id,
                name=strategy.name,
                symbol=strategy.symbol,
                strategy_type=strategy.strategy_type,
                status=StrategyState.running,
                leverage=strategy.leverage,
                risk_per_trade=float(strategy.risk_per_trade),
                fixed_amount=float(strategy.fixed_amount) if strategy.fixed_amount else None,
                params=strategy.params or {},
                account_id="default",
                position_size=0.001,  # Has position
                position_side="LONG",
                entry_price=40000.0,
                created_at=datetime.now(timezone.utc),
                last_signal=None
            )
            runner._strategies[strategy.strategy_id] = summary
        
        print("\n[OK] Test Setup Complete")
        print(f"   - Created {len(strategies)} strategies")
        print(f"   - All strategies have open positions")
        
        # Test 1: Verify pause is blocking (not background task)
        print("\n" + "=" * 80)
        print("TEST 1: Verify pause is blocking (awaited, not background task)")
        print("=" * 80)
        
        pause_completed = False
        
        async def track_pause():
            nonlocal pause_completed
            await runner.pause_all_strategies_for_account(
                account_id="default",
                reason="Daily loss limit exceeded"
            )
            pause_completed = True
        
        await track_pause()
        
        assert pause_completed, "FAIL: Pause should complete synchronously"
        print("PASS: Pause completes synchronously (not background task)")
        
        # Test 2: Verify positions are closed
        print("\n" + "=" * 80)
        print("TEST 2: Verify positions are closed")
        print("=" * 80)
        
        assert mock_client.get_open_position.call_count == 3, \
            f"FAIL: Should check position for all 3 strategies, got {mock_client.get_open_position.call_count}"
        print(f"PASS: Position checked for all {mock_client.get_open_position.call_count} strategies")
        
        assert mock_client.close_position.call_count == 3, \
            f"FAIL: Should close position for all 3 strategies, got {mock_client.close_position.call_count}"
        print(f"PASS: Position closed for all {mock_client.close_position.call_count} strategies")
        
        # Test 3: Verify TP/SL orders are cancelled
        print("\n" + "=" * 80)
        print("TEST 3: Verify TP/SL orders are cancelled")
        print("=" * 80)
        
        assert mock_order_manager.cancel_tp_sl_orders.call_count == 3, \
            f"FAIL: Should cancel TP/SL orders for all 3 strategies, got {mock_order_manager.cancel_tp_sl_orders.call_count}"
        print(f"PASS: TP/SL orders cancelled for all {mock_order_manager.cancel_tp_sl_orders.call_count} strategies")
        
        # Test 4: Verify closing trades are saved
        print("\n" + "=" * 80)
        print("TEST 4: Verify closing trades are saved")
        print("=" * 80)
        
        assert mock_trade_service.save_trade.call_count == 3, \
            f"FAIL: Should save closing trade for all 3 strategies, got {mock_trade_service.save_trade.call_count}"
        print(f"PASS: Closing trades saved for all {mock_trade_service.save_trade.call_count} strategies")
        
        # Test 5: Verify status is updated to paused_by_risk
        print("\n" + "=" * 80)
        print("TEST 5: Verify status is updated to paused_by_risk")
        print("=" * 80)
        
        db.expire_all()
        paused_count = db.query(Strategy).filter(
            Strategy.account_id == account.id,
            Strategy.status == "paused_by_risk"
        ).count()
        
        assert paused_count == 3, \
            f"FAIL: Should have 3 paused strategies, got {paused_count}"
        print(f"PASS: All {paused_count} strategies have status 'paused_by_risk'")
        
        # Test 6: Verify in-memory summaries are updated
        print("\n" + "=" * 80)
        print("TEST 6: Verify in-memory summaries are updated")
        print("=" * 80)
        
        for strategy_id in [s.strategy_id for s in strategies]:
            summary = runner._strategies.get(strategy_id)
            assert summary is not None, f"FAIL: Summary not found for {strategy_id}"
            assert summary.status == StrategyState.paused_by_risk, \
                f"FAIL: Summary status should be paused_by_risk, got {summary.status}"
        
        print("PASS: All in-memory summaries updated to paused_by_risk")
        
        print("\n" + "=" * 80)
        print("ALL TESTS PASSED!")
        print("=" * 80)
        print("\nSummary:")
        print("  PASS: Pause is blocking (awaited, not background task)")
        print("  PASS: Positions are closed for all strategies")
        print("  PASS: TP/SL orders are cancelled for all strategies")
        print("  PASS: Closing trades are saved to database")
        print("  PASS: Status is updated to 'paused_by_risk' in database")
        print("  PASS: In-memory summaries are updated")
        print("\nThe fix is working correctly!")
        
    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()
        Base.metadata.drop_all(engine)


if __name__ == "__main__":
    asyncio.run(verify_pause_functionality())

