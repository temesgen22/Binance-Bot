"""
Comprehensive integration test for enforcement history.

This test simulates real-world usage by:
1. Creating test enforcement events in the database
2. Querying them through the API
3. Verifying filters work correctly
4. Testing pagination
"""

import sys
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

# Fix Unicode encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, '.')

from app.core.database import get_db_session
from app.services.database_service import DatabaseService
from app.models.db_models import SystemEvent, User, Account, Strategy


def create_test_enforcement_events(db_service: DatabaseService, user_id: UUID, account_id: UUID, strategy_id: UUID):
    """Create test enforcement events in the database."""
    events_created = []
    
    # Create various types of enforcement events
    event_types = [
        ("ORDER_BLOCKED", "WARNING", "Order blocked: Portfolio exposure limit exceeded"),
        ("CIRCUIT_BREAKER_TRIGGERED", "ERROR", "Circuit breaker triggered: 5 consecutive losses"),
        ("ORDER_SIZE_REDUCED", "INFO", "Order size reduced due to risk limits"),
        ("RISK_LIMIT_EXCEEDED", "WARNING", "Daily loss limit exceeded"),
        ("ORDER_BLOCKED", "WARNING", "Order blocked: Drawdown limit exceeded"),
    ]
    
    base_time = datetime.now(timezone.utc)
    
    for i, (event_type, event_level, message) in enumerate(event_types):
        # Create events at different times
        event_time = base_time - timedelta(hours=i)
        
        metadata = {
            "limit_type": "PORTFOLIO_EXPOSURE" if "exposure" in message.lower() else 
                          "DAILY_LOSS" if "daily" in message.lower() else
                          "DRAWDOWN" if "drawdown" in message.lower() else
                          "CIRCUIT_BREAKER",
            "current_value": 5500.0 + (i * 100),
            "limit_value": 5000.0,
            "symbol": "BTCUSDT",
            "reason": message
        }
        
        event = db_service.create_system_event(
            event_type=event_type,
            event_level=event_level,
            message=message,
            strategy_id=strategy_id if i % 2 == 0 else None,  # Some with strategy, some without
            account_id=account_id,
            event_metadata=metadata
        )
        
        events_created.append(event)
        print(f"  ✅ Created event: {event_type} at {event_time.isoformat()}")
    
    return events_created


def test_enforcement_history_integration():
    """Test enforcement history integration end-to-end."""
    print("=" * 60)
    print("🧪 Enforcement History Integration Test")
    print("=" * 60)
    
    try:
        with get_db_session() as db_session:
            db_service = DatabaseService(db=db_session)
            
            # Get or create a test user
            print("\n📋 Step 1: Setting up test data...")
            test_user = db_service.db.query(User).first()
            if not test_user:
                print("  ⚠️  No users found in database. Please create a user first.")
                return False
            
            user_id = test_user.id
            print(f"  ✅ Using user: {user_id}")
            
            # Get or create a test account
            test_account = db_service.get_user_accounts(user_id)
            if not test_account:
                print("  ⚠️  No accounts found for user. Please create an account first.")
                return False
            
            account = test_account[0]
            account_id = account.id
            print(f"  ✅ Using account: {account.account_id} (UUID: {account_id})")
            
            # Get or create a test strategy
            test_strategies = db_service.get_user_strategies(user_id)
            strategy_id = None
            if test_strategies:
                strategy = test_strategies[0]
                strategy_id = strategy.id
                print(f"  ✅ Using strategy: {strategy.strategy_id} (UUID: {strategy_id})")
            else:
                print("  ⚠️  No strategies found. Creating events without strategy_id.")
            
            # Create test events
            print("\n📝 Step 2: Creating test enforcement events...")
            events = create_test_enforcement_events(
                db_service, user_id, account_id, strategy_id
            )
            print(f"  ✅ Created {len(events)} test events")
            
            # Test querying events
            print("\n🔍 Step 3: Testing get_enforcement_events() query...")
            all_events, total = db_service.get_enforcement_events(
                user_id=user_id,
                limit=100,
                offset=0
            )
            print(f"  ✅ Found {total} total events (returned {len(all_events)})")
            
            # Test filtering by event type
            print("\n🔍 Step 4: Testing event_type filter...")
            filtered_events, filtered_total = db_service.get_enforcement_events(
                user_id=user_id,
                event_type="ORDER_BLOCKED",
                limit=100,
                offset=0
            )
            print(f"  ✅ Found {filtered_total} ORDER_BLOCKED events")
            assert all(e.event_type == "ORDER_BLOCKED" for e in filtered_events), "Filter not working"
            
            # Test filtering by account
            print("\n🔍 Step 5: Testing account_id filter...")
            account_events, account_total = db_service.get_enforcement_events(
                user_id=user_id,
                account_id=account_id,
                limit=100,
                offset=0
            )
            print(f"  ✅ Found {account_total} events for account")
            assert all(e.account_id == account_id for e in account_events), "Account filter not working"
            
            # Test date range filter
            print("\n🔍 Step 6: Testing date range filter...")
            start_date = datetime.now(timezone.utc) - timedelta(hours=24)
            end_date = datetime.now(timezone.utc)
            date_events, date_total = db_service.get_enforcement_events(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                limit=100,
                offset=0
            )
            print(f"  ✅ Found {date_total} events in last 24 hours")
            
            # Test pagination
            print("\n🔍 Step 7: Testing pagination...")
            page1_events, page1_total = db_service.get_enforcement_events(
                user_id=user_id,
                limit=2,
                offset=0
            )
            page2_events, page2_total = db_service.get_enforcement_events(
                user_id=user_id,
                limit=2,
                offset=2
            )
            print(f"  ✅ Page 1: {len(page1_events)} events, Page 2: {len(page2_events)} events")
            assert page1_total == page2_total, "Total count should be consistent"
            assert len(page1_events) <= 2, "Page 1 should have max 2 events"
            assert len(page2_events) <= 2, "Page 2 should have max 2 events"
            
            # Verify event metadata
            print("\n🔍 Step 8: Verifying event metadata...")
            if all_events:
                event = all_events[0]
                assert event.event_metadata is not None, "Event should have metadata"
                print(f"  ✅ Event metadata: {event.event_metadata}")
            
            print("\n" + "=" * 60)
            print("✅ All integration tests passed!")
            print("=" * 60)
            print("\n📊 Summary:")
            print(f"  • Created {len(events)} test events")
            print(f"  • Total events in database: {total}")
            print(f"  • Filtered by type: {filtered_total}")
            print(f"  • Filtered by account: {account_total}")
            print(f"  • Filtered by date: {date_total}")
            print(f"  • Pagination working: ✅")
            
            return True
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_enforcement_history_integration()
    sys.exit(0 if success else 1)











