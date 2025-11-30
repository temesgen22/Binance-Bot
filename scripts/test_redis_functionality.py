"""Quick script to test Redis functionality based on test cases."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.redis_storage import RedisStorage
from app.models.order import OrderResponse
from datetime import datetime, timezone
import json


def test_redis_connection():
    """Test basic Redis connection."""
    print("=" * 60)
    print("Testing Redis Connection")
    print("=" * 60)
    
    storage = RedisStorage(redis_url="redis://localhost:6379/0", enabled=True)
    
    if storage.enabled and storage._client:
        try:
            storage._client.ping()
            print("✅ Redis connection: SUCCESS")
            return True
        except Exception as e:
            print(f"❌ Redis connection: FAILED - {e}")
            return False
    else:
        print("⚠️  Redis is disabled or not available")
        return False


def test_save_and_retrieve_strategy():
    """Test saving and retrieving strategy."""
    print("\n" + "=" * 60)
    print("Testing Strategy Save/Retrieve")
    print("=" * 60)
    
    storage = RedisStorage(redis_url="redis://localhost:6379/0", enabled=True)
    
    if not storage.enabled or not storage._client:
        print("⚠️  Redis is disabled, skipping test")
        return False
    
    strategy_data = {
        "id": "test-redis-check",
        "name": "Redis Test Strategy",
        "symbol": "BTCUSDT",
        "status": "running",
        "leverage": 10,
    }
    
    # Save
    result = storage.save_strategy("test-redis-check", strategy_data)
    if result:
        print("✅ Save strategy: SUCCESS")
    else:
        print("❌ Save strategy: FAILED")
        return False
    
    # Retrieve
    retrieved = storage.get_strategy("test-redis-check")
    if retrieved and retrieved.get("id") == "test-redis-check":
        print("✅ Retrieve strategy: SUCCESS")
        
        # Cleanup
        storage.delete_strategy("test-redis-check")
        return True
    else:
        print("❌ Retrieve strategy: FAILED")
        return False


def test_save_and_retrieve_trades_with_binance_params():
    """Test saving and retrieving trades with Binance parameters."""
    print("\n" + "=" * 60)
    print("Testing Trades Save/Retrieve with Binance Parameters")
    print("=" * 60)
    
    storage = RedisStorage(redis_url="redis://localhost:6379/0", enabled=True)
    
    if not storage.enabled or not storage._client:
        print("⚠️  Redis is disabled, skipping test")
        return False
    
    # Create OrderResponse with Binance parameters
    order_time = datetime.now(timezone.utc)
    order = OrderResponse(
        symbol="BTCUSDT",
        order_id=99999,
        status="FILLED",
        side="BUY",
        price=50000.0,
        avg_price=50000.5,
        executed_qty=0.1,
        timestamp=order_time,
        commission=0.0195,
        commission_asset="USDT",
        leverage=10,
        initial_margin=50.25,
        margin_type="ISOLATED",
        notional_value=5000.05,
    )
    
    # Convert to dict
    trades = [order.model_dump()]
    
    # Save
    result = storage.save_trades("test-redis-trades", trades)
    if result:
        print("✅ Save trades with Binance parameters: SUCCESS")
    else:
        print("❌ Save trades: FAILED")
        return False
    
    # Retrieve
    retrieved = storage.get_trades("test-redis-trades")
    if retrieved and len(retrieved) == 1:
        trade = retrieved[0]
        
        # Verify Binance parameters
        checks = [
            ("symbol", trade.get("symbol") == "BTCUSDT"),
            ("commission", trade.get("commission") == 0.0195),
            ("leverage", trade.get("leverage") == 10),
            ("initial_margin", trade.get("initial_margin") == 50.25),
            ("margin_type", trade.get("margin_type") == "ISOLATED"),
            ("timestamp", "timestamp" in trade),
        ]
        
        all_passed = True
        for name, passed in checks:
            if passed:
                print(f"  ✅ {name}: OK")
            else:
                print(f"  ❌ {name}: FAILED")
                all_passed = False
        
        if all_passed:
            print("✅ Retrieve trades with Binance parameters: SUCCESS")
            
            # Cleanup
            storage.delete_trades("test-redis-trades")
            return True
        else:
            print("❌ Some Binance parameters missing or incorrect")
            return False
    else:
        print("❌ Retrieve trades: FAILED")
        return False


def test_datetime_serialization():
    """Test datetime serialization."""
    print("\n" + "=" * 60)
    print("Testing Datetime Serialization")
    print("=" * 60)
    
    storage = RedisStorage(redis_url="redis://localhost:6379/0", enabled=True)
    
    if not storage.enabled or not storage._client:
        print("⚠️  Redis is disabled, skipping test")
        return False
    
    order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
    order = OrderResponse(
        symbol="BTCUSDT",
        order_id=88888,
        status="FILLED",
        side="BUY",
        price=50000.0,
        avg_price=50000.0,
        executed_qty=0.1,
        timestamp=order_time,
    )
    
    trades = [order.model_dump()]
    result = storage.save_trades("test-datetime", trades)
    
    if result:
        retrieved = storage.get_trades("test-datetime")
        if retrieved and retrieved[0].get("timestamp"):
            timestamp_str = retrieved[0]["timestamp"]
            if isinstance(timestamp_str, str):
                print(f"✅ Datetime serialized to ISO string: {timestamp_str}")
                storage.delete_trades("test-datetime")
                return True
            else:
                print(f"❌ Datetime not serialized correctly: {type(timestamp_str)}")
                return False
        else:
            print("❌ Failed to retrieve timestamp")
            return False
    else:
        print("❌ Failed to save with datetime")
        return False


def main():
    """Run all Redis tests."""
    print("\n" + "=" * 60)
    print("Redis Functionality Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Connection", test_redis_connection()))
    results.append(("Strategy Save/Retrieve", test_save_and_retrieve_strategy()))
    results.append(("Trades with Binance Params", test_save_and_retrieve_trades_with_binance_params()))
    results.append(("Datetime Serialization", test_datetime_serialization()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("\n" + "-" * 60)
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n✅ All Redis tests PASSED!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())

