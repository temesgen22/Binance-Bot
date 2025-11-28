#!/bin/bash
# Diagnose Redis container issues
# Usage: ./diagnose_redis.sh

set -e

echo "🔍 Redis Container Diagnostics"
echo "=============================="
echo ""

# Check if container exists
echo "1️⃣  Checking Redis container status..."
if docker ps -a | grep -q binance-bot-redis; then
    echo "   ✅ Container exists"
    docker ps -a | grep binance-bot-redis
else
    echo "   ❌ Container not found"
    exit 1
fi

echo ""
echo "2️⃣  Checking container logs (last 50 lines)..."
echo "   ==========================================="
docker logs --tail 50 binance-bot-redis 2>&1 || echo "   ⚠️  Could not read logs"

echo ""
echo "3️⃣  Checking Redis configuration file..."
if [ -f "redis.conf" ]; then
    echo "   ✅ redis.conf exists locally"
    echo "   File size: $(wc -l < redis.conf) lines"
else
    echo "   ❌ redis.conf NOT FOUND in current directory"
    echo "   This might be the problem!"
fi

echo ""
echo "4️⃣  Checking if redis.conf is mounted in container..."
if docker exec binance-bot-redis test -f /usr/local/etc/redis/redis.conf 2>/dev/null; then
    echo "   ✅ redis.conf is mounted in container"
    echo "   Checking content..."
    docker exec binance-bot-redis cat /usr/local/etc/redis/redis.conf | head -10
else
    echo "   ❌ redis.conf NOT FOUND in container at /usr/local/etc/redis/redis.conf"
    echo "   This is likely the problem!"
fi

echo ""
echo "5️⃣  Checking Redis data directory permissions..."
if docker exec binance-bot-redis test -d /data 2>/dev/null; then
    echo "   ✅ /data directory exists"
    docker exec binance-bot-redis ls -la /data || echo "   ⚠️  Cannot list /data"
else
    echo "   ❌ /data directory NOT FOUND"
fi

echo ""
echo "6️⃣  Checking Redis volume..."
if docker volume ls | grep -q redis-data; then
    echo "   ✅ redis-data volume exists"
    VOLUME_PATH=$(docker volume inspect redis-data --format '{{ .Mountpoint }}' 2>/dev/null || echo "unknown")
    echo "   Volume path: $VOLUME_PATH"
else
    echo "   ❌ redis-data volume NOT FOUND"
fi

echo ""
echo "7️⃣  Testing Redis configuration syntax..."
if [ -f "redis.conf" ]; then
    # Try to validate config by starting a temporary Redis instance
    echo "   Testing config syntax..."
    docker run --rm -v "$(pwd)/redis.conf:/tmp/redis.conf:ro" redis:7-alpine redis-server /tmp/redis.conf --test-memory 1 2>&1 | head -20 || echo "   ⚠️  Config test failed"
fi

echo ""
echo "8️⃣  Checking Docker Compose file..."
if [ -f "docker-compose.yml" ]; then
    echo "   ✅ docker-compose.yml exists"
    echo "   Redis service configuration:"
    grep -A 10 "^  redis:" docker-compose.yml || echo "   ⚠️  Redis service not found"
else
    echo "   ❌ docker-compose.yml NOT FOUND"
fi

echo ""
echo "=============================="
echo "✅ Diagnostics complete!"
echo ""
echo "💡 Common fixes:"
echo "   1. If redis.conf is missing: Copy it to deployment directory"
echo "   2. If container keeps restarting: Check logs above for errors"
echo "   3. If permissions issue: Fix /data directory permissions"
echo ""

