#!/usr/bin/env python3
"""Diagnose why Redis warning appears when app starts."""

import sys
import os

print("=" * 60)
print("Redis Installation Diagnostic")
print("=" * 60)

# 1. Check Python executable
print(f"\n1. Python Executable: {sys.executable}")
print(f"   Python Version: {sys.version}")

# 2. Check if redis is in path
print("\n2. Checking Python path...")
print(f"   Site-packages locations:")
for path in sys.path:
    if 'site-packages' in path or 'dist-packages' in path:
        print(f"     - {path}")

# 3. Try importing redis
print("\n3. Testing redis import...")
try:
    import redis
    print(f"   ✅ redis imported successfully")
    print(f"   ✅ redis version: {redis.__version__}")
    print(f"   ✅ redis location: {redis.__file__}")
except ImportError as e:
    print(f"   ❌ Failed to import redis: {e}")
    print(f"   ❌ This is why you see the warning!")

# 4. Check if redis is installed via pip
print("\n4. Checking pip installation...")
import subprocess
try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", "redis"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.returncode == 0:
        print("   ✅ redis is installed via pip:")
        for line in result.stdout.split('\n')[:5]:
            if line.strip():
                print(f"      {line}")
    else:
        print("   ❌ redis not found via pip")
        print(f"      Error: {result.stderr}")
except Exception as e:
    print(f"   ⚠️  Could not check pip: {e}")

# 5. Test the actual module import
print("\n5. Testing app.core.redis_storage import...")
try:
    # Clear any cached imports
    if 'app.core.redis_storage' in sys.modules:
        del sys.modules['app.core.redis_storage']
    
    from app.core.redis_storage import REDIS_AVAILABLE
    print(f"   REDIS_AVAILABLE = {REDIS_AVAILABLE}")
    
    if REDIS_AVAILABLE:
        print("   ✅ Redis should work in your app!")
    else:
        print("   ❌ Redis is NOT available - this is the problem!")
        print("   Solution: Install redis with: pip install redis>=5.0.0")
except Exception as e:
    print(f"   ❌ Error importing module: {e}")
    import traceback
    traceback.print_exc()

# 6. Check environment variables
print("\n6. Checking environment variables...")
redis_url = os.getenv("REDIS_URL", "not set")
redis_enabled = os.getenv("REDIS_ENABLED", "not set")
print(f"   REDIS_URL: {redis_url}")
print(f"   REDIS_ENABLED: {redis_enabled}")

print("\n" + "=" * 60)
print("Diagnostic Complete")
print("=" * 60)

