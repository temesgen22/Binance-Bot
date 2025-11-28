#!/bin/bash
# Quick script to check Redis logs and status
# Usage: ./check_redis_logs.sh

echo "🔍 Redis Container Status & Logs"
echo "================================="
echo ""

# Check container status
echo "1️⃣  Container Status:"
docker ps -a | grep binance-bot-redis || echo "   ❌ Container not found"
echo ""

# Check if container is running
if docker ps | grep -q binance-bot-redis; then
    echo "   ✅ Container is RUNNING"
else
    echo "   ❌ Container is NOT running"
    echo ""
    echo "2️⃣  Last 50 lines of logs (showing why it's not running):"
    echo "   ======================================================"
    docker logs --tail 50 binance-bot-redis 2>&1 | sed 's/^/   /'
fi

echo ""
echo "3️⃣  Checking redis.conf in deployment:"
if [ -f "redis.conf" ]; then
    echo "   ✅ redis.conf exists in current directory"
    echo "   File size: $(wc -l < redis.conf) lines"
    echo ""
    echo "   First 10 lines:"
    head -10 redis.conf | sed 's/^/      /'
else
    echo "   ❌ redis.conf NOT FOUND in current directory"
fi

echo ""
echo "4️⃣  Checking if redis.conf is mounted in container:"
if docker exec binance-bot-redis test -f /usr/local/etc/redis/redis.conf 2>/dev/null; then
    echo "   ✅ redis.conf is mounted in container"
    echo ""
    echo "   Content (first 10 lines):"
    docker exec binance-bot-redis cat /usr/local/etc/redis/redis.conf 2>/dev/null | head -10 | sed 's/^/      /' || echo "      Could not read file"
else
    echo "   ❌ redis.conf NOT FOUND in container"
    echo "   This is likely the problem!"
fi

echo ""
echo "5️⃣  Checking /data directory in container:"
if docker exec binance-bot-redis test -d /data 2>/dev/null; then
    echo "   ✅ /data directory exists"
    docker exec binance-bot-redis ls -la /data 2>/dev/null | sed 's/^/      /' || echo "      Could not list directory"
else
    echo "   ❌ /data directory NOT FOUND"
fi

echo ""
echo "6️⃣  Testing Redis config syntax:"
if [ -f "redis.conf" ]; then
    # Try to validate by checking if Redis can start with this config
    echo "   Testing config..."
    docker run --rm -v "$(pwd)/redis.conf:/tmp/redis.conf:ro" redis:7-alpine redis-server /tmp/redis.conf --test-memory 1 2>&1 | head -10 | sed 's/^/      /' || echo "      Config test completed"
fi

echo ""
echo "================================="
echo "✅ Check complete!"
echo ""
echo "💡 If Redis is restarting, the logs above will show the error."
echo "   Common issues:"
echo "   - redis.conf not found in container"
echo "   - Syntax error in redis.conf"
echo "   - Permission issues with /data directory"
echo ""

