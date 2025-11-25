#!/usr/bin/env python3
"""Script to check if Redis is accessible and working."""

import sys
from app.core.config import get_settings
from app.core.redis_storage import RedisStorage


def check_redis() -> bool:
    """Check if Redis is accessible."""
    settings = get_settings()
    
    print(f"Redis Configuration:")
    print(f"  URL: {settings.redis_url}")
    print(f"  Enabled: {settings.redis_enabled}")
    print()
    
    if not settings.redis_enabled:
        print("❌ Redis is disabled in configuration (REDIS_ENABLED=false)")
        return False
    
    try:
        import redis
        print("✅ Redis Python package is installed")
    except ImportError:
        print("❌ Redis Python package is NOT installed")
        print("   Install it with: pip install redis>=5.0.0")
        return False
    
    print(f"\nAttempting to connect to Redis at: {settings.redis_url}")
    
    try:
        storage = RedisStorage(
            redis_url=settings.redis_url,
            enabled=settings.redis_enabled
        )
        
        if storage.enabled and storage._client:
            # Test connection with a ping
            result = storage._client.ping()
            if result:
                print("✅ Redis connection successful!")
                
                # Test read/write
                test_key = "binance_bot:test:connection"
                storage._client.set(test_key, "test_value", ex=10)  # Expires in 10 seconds
                value = storage._client.get(test_key)
                storage._client.delete(test_key)
                
                if value == "test_value":
                    print("✅ Redis read/write test passed!")
                    
                    # Get Redis info
                    info = storage._client.info("server")
                    redis_version = info.get("redis_version", "unknown")
                    print(f"✅ Redis version: {redis_version}")
                    return True
                else:
                    print("❌ Redis read/write test failed!")
                    return False
            else:
                print("❌ Redis ping failed!")
                return False
        else:
            print("❌ Redis storage is not enabled or client is None")
            return False
            
    except Exception as exc:
        print(f"❌ Failed to connect to Redis: {exc}")
        print("\nTroubleshooting:")
        print("  1. Make sure Redis server is running")
        print("  2. Check if the Redis URL is correct")
        print("  3. Check firewall settings")
        print("  4. Try connecting manually: redis-cli -h <host> -p <port>")
        return False


if __name__ == "__main__":
    success = check_redis()
    sys.exit(0 if success else 1)


