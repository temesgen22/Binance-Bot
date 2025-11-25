#!/usr/bin/env python3
"""Test Redis integration with the actual application code."""

import sys
import asyncio
from datetime import datetime

# Test imports
print("Testing Redis integration...")
print("=" * 50)

# 1. Check if redis package can be imported
print("\n1. Checking Redis package import...")
try:
    import redis
    print(f"   ✅ Redis package imported successfully (version: {redis.__version__})")
except ImportError as e:
    print(f"   ❌ Failed to import redis: {e}")
    sys.exit(1)

# 2. Check REDIS_AVAILABLE flag
print("\n2. Checking REDIS_AVAILABLE flag...")
try:
    from app.core.redis_storage import REDIS_AVAILABLE
    if REDIS_AVAILABLE:
        print("   ✅ REDIS_AVAILABLE = True")
    else:
        print("   ❌ REDIS_AVAILABLE = False (this is the problem!)")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Error importing REDIS_AVAILABLE: {e}")
    sys.exit(1)

# 3. Test RedisStorage initialization
print("\n3. Testing RedisStorage initialization...")
from app.core.config import get_settings
from app.core.redis_storage import RedisStorage

settings = get_settings()
print(f"   Redis URL: {settings.redis_url}")
print(f"   Redis Enabled: {settings.redis_enabled}")

try:
    storage = RedisStorage(
        redis_url=settings.redis_url,
        enabled=settings.redis_enabled
    )
    
    if storage.enabled:
        print("   ✅ RedisStorage enabled successfully")
        if storage._client:
            print("   ✅ Redis client created")
            
            # Test connection
            try:
                result = storage._client.ping()
                print(f"   ✅ Redis ping successful: {result}")
            except Exception as e:
                print(f"   ❌ Redis ping failed: {e}")
                sys.exit(1)
        else:
            print("   ❌ Redis client is None")
            sys.exit(1)
    else:
        print("   ❌ RedisStorage is not enabled")
        print("   This might be because:")
        print("     - REDIS_ENABLED=false in .env")
        print("     - Redis connection failed")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Failed to initialize RedisStorage: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 4. Test save/load operations
print("\n4. Testing save/load operations...")
test_strategy_id = "test-strategy-123"
test_data = {
    "id": test_strategy_id,
    "name": "Test Strategy",
    "symbol": "BTCUSDT",
    "created_at": datetime.utcnow().isoformat(),
    "status": "stopped"
}

try:
    # Save
    saved = storage.save_strategy(test_strategy_id, test_data)
    if saved:
        print("   ✅ Strategy saved to Redis")
    else:
        print("   ❌ Failed to save strategy")
        sys.exit(1)
    
    # Load
    loaded = storage.get_strategy(test_strategy_id)
    if loaded:
        print("   ✅ Strategy loaded from Redis")
        print(f"      Loaded name: {loaded.get('name')}")
    else:
        print("   ❌ Failed to load strategy")
        sys.exit(1)
    
    # Cleanup
    storage.delete_strategy(test_strategy_id)
    print("   ✅ Test strategy deleted")
    
except Exception as e:
    print(f"   ❌ Save/load test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 5. Test with StrategyRunner
print("\n5. Testing StrategyRunner integration...")
try:
    from app.core.my_binance_client import BinanceClient
    from app.risk.manager import RiskManager
    from app.services.order_executor import OrderExecutor
    from app.services.strategy_runner import StrategyRunner
    
    # Create mock client (won't actually connect)
    client = BinanceClient(
        api_key="test",
        api_secret="test",
        testnet=True
    )
    risk = RiskManager(client=client)
    executor = OrderExecutor(client=client)
    
    runner = StrategyRunner(
        client=client,
        risk=risk,
        executor=executor,
        max_concurrent=3,
        redis_storage=storage
    )
    
    print("   ✅ StrategyRunner initialized with Redis storage")
    print(f"      Redis enabled in runner: {runner.redis is not None and runner.redis.enabled}")
    
except Exception as e:
    print(f"   ⚠️  StrategyRunner test failed (might be expected if Binance not configured): {e}")

print("\n" + "=" * 50)
print("✅ All Redis integration tests passed!")
print("=" * 50)


