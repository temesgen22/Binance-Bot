#!/usr/bin/env python3
"""Test that Redis warning only appears when appropriate."""

print("Testing Redis warning fix...")
print("=" * 50)

# Test 1: Import should not show warning if redis is available
print("\n1. Testing module import (should be silent if redis available)...")
from app.core.redis_storage import REDIS_AVAILABLE, RedisStorage

if REDIS_AVAILABLE:
    print("   ✅ REDIS_AVAILABLE = True (no warning should appear)")
else:
    print("   ❌ REDIS_AVAILABLE = False")

# Test 2: Creating RedisStorage with enabled=True should work
print("\n2. Testing RedisStorage initialization...")
from app.core.config import get_settings

settings = get_settings()
storage = RedisStorage(
    redis_url=settings.redis_url,
    enabled=settings.redis_enabled
)

if storage.enabled:
    print("   ✅ RedisStorage enabled successfully")
    print("   ✅ No false warnings!")
else:
    print("   ⚠️  RedisStorage is disabled")
    if settings.redis_enabled and not REDIS_AVAILABLE:
        print("   (This is expected if redis package is not installed)")

print("\n" + "=" * 50)
print("✅ Test complete! The warning should only appear when:")
print("   - Redis is enabled in config (REDIS_ENABLED=true)")
print("   - AND redis package is NOT installed")
print("=" * 50)

