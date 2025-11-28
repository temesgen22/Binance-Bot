#!/bin/bash
# Quick fix for Redis restart issue
# This script stops Redis, verifies config, and restarts it

set -e

echo "🔧 Quick Redis Fix"
echo "=================="
echo ""

cd /home/jenkins-deploy/binance-bot || {
    echo "❌ Error: Could not change to deployment directory"
    exit 1
}

# Check which compose file to use
COMPOSE_FILE="docker-compose.yml"
if [ -f "docker-compose.prod.yml" ]; then
    COMPOSE_FILE="docker-compose.prod.yml"
fi

echo "📋 Using: $COMPOSE_FILE"
echo ""

# 1. Stop Redis
echo "🛑 Stopping Redis..."
docker-compose -f "$COMPOSE_FILE" stop redis 2>/dev/null || docker stop binance-bot-redis 2>/dev/null || true
sleep 2

# 2. Verify redis.conf exists
echo "🔍 Checking redis.conf..."
if [ ! -f "redis.conf" ]; then
    echo "   ❌ redis.conf not found! Pulling from git..."
    git pull origin main || echo "   ⚠️  Git pull failed"
    
    if [ ! -f "redis.conf" ]; then
        echo "   ❌ Still not found. Creating default..."
        cat > redis.conf << 'EOF'
appendonly yes
appendfsync everysec
save 900 1
save 300 10
save 60 10000
dir /data
dbfilename dump.rdb
appendfilename "appendonly.aof"
protected-mode no
EOF
    fi
fi

if [ -f "redis.conf" ]; then
    echo "   ✅ redis.conf exists"
    echo "   File: $(pwd)/redis.conf"
    ls -lh redis.conf | awk '{print "   Size: " $5}'
else
    echo "   ❌ Could not create/find redis.conf"
    exit 1
fi

# 3. Check if path in docker-compose is correct
echo ""
echo "🔍 Verifying docker-compose mount path..."
if grep -q "./redis.conf" "$COMPOSE_FILE"; then
    echo "   ✅ docker-compose references ./redis.conf"
    echo "   Current directory: $(pwd)"
    echo "   Expected file: $(pwd)/redis.conf"
    
    if [ -f "$(pwd)/redis.conf" ]; then
        echo "   ✅ Path is correct!"
    else
        echo "   ❌ Path mismatch!"
    fi
else
    echo "   ⚠️  Could not find redis.conf reference in $COMPOSE_FILE"
fi

# 4. Show Redis logs before restart
echo ""
echo "📋 Last 20 lines of Redis logs (before restart):"
echo "   ============================================="
docker logs --tail 20 binance-bot-redis 2>&1 | sed 's/^/   /' || echo "   No logs available"

# 5. Start Redis
echo ""
echo "🚀 Starting Redis..."
docker-compose -f "$COMPOSE_FILE" up -d redis

# 6. Wait and check
echo ""
echo "⏳ Waiting 5 seconds for Redis to start..."
sleep 5

# 7. Check status
echo ""
echo "📊 Redis Status:"
if docker ps | grep -q binance-bot-redis; then
    echo "   ✅ Container is RUNNING"
    
    # Test connection
    sleep 2
    if docker exec binance-bot-redis redis-cli ping 2>/dev/null | grep -q PONG; then
        echo "   ✅ Redis is responding!"
        
        KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
        echo "   📊 Keys in Redis: $KEY_COUNT"
        
        if [ "$KEY_COUNT" -gt 0 ]; then
            echo "   ✅ Data found!"
        fi
    else
        echo "   ⚠️  Container running but not responding to PING"
        echo "   Check logs: docker logs binance-bot-redis"
    fi
else
    echo "   ❌ Container is NOT running"
    echo ""
    echo "📋 Latest logs:"
    docker logs --tail 30 binance-bot-redis 2>&1 | sed 's/^/   /'
    echo ""
    echo "💡 Try: docker logs binance-bot-redis"
    exit 1
fi

echo ""
echo "✅ Fix completed!"

