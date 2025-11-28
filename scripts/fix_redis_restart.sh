#!/bin/bash
# Fix Redis container restart issue
# This script checks and fixes common Redis startup problems

set -e

echo "🔧 Fixing Redis Container Restart Issue"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ] && [ ! -f "docker-compose.prod.yml" ]; then
    echo "❌ Error: docker-compose.yml not found in current directory"
    echo "   Please run this script from the project root directory"
    exit 1
fi

COMPOSE_FILE="docker-compose.yml"
if [ -f "docker-compose.prod.yml" ]; then
    COMPOSE_FILE="docker-compose.prod.yml"
fi

echo "📋 Using compose file: $COMPOSE_FILE"
echo ""

# Check if redis.conf exists
if [ ! -f "redis.conf" ]; then
    echo "❌ Error: redis.conf not found!"
    echo ""
    echo "Creating default redis.conf..."
    cat > redis.conf << 'EOF'
# Redis configuration for persistence
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
    echo "✅ Created redis.conf"
else
    echo "✅ redis.conf exists"
fi

# Check Redis container status
echo ""
echo "📊 Checking Redis container status..."
if docker ps -a | grep -q binance-bot-redis; then
    STATUS=$(docker ps -a | grep binance-bot-redis | awk '{print $7}')
    echo "   Container status: $STATUS"
    
    if [ "$STATUS" = "Restarting" ] || [ "$STATUS" = "Exited" ]; then
        echo "   ⚠️  Container is not running properly"
        
        # Show logs
        echo ""
        echo "📋 Last 30 lines of Redis logs:"
        echo "   ============================="
        docker logs --tail 30 binance-bot-redis 2>&1 | sed 's/^/   /' || echo "   Could not read logs"
        
        # Stop container
        echo ""
        echo "🛑 Stopping Redis container..."
        docker-compose -f "$COMPOSE_FILE" stop redis || docker stop binance-bot-redis || true
        sleep 2
    fi
else
    echo "   ℹ️  Redis container not found (will be created)"
fi

# Verify redis.conf is accessible
echo ""
echo "🔍 Verifying redis.conf configuration..."
if [ -f "redis.conf" ]; then
    echo "   ✅ redis.conf exists locally"
    
    # Check if config is valid (basic check)
    if grep -q "dir /data" redis.conf; then
        echo "   ✅ Config looks valid"
    else
        echo "   ⚠️  Warning: Config might be incomplete"
    fi
else
    echo "   ❌ redis.conf not found!"
    exit 1
fi

# Verify redis.conf path is correct in docker-compose
echo ""
echo "🔍 Verifying docker-compose configuration..."
if grep -q "redis.conf" "$COMPOSE_FILE"; then
    echo "   ✅ redis.conf is referenced in $COMPOSE_FILE"
    grep "redis.conf" "$COMPOSE_FILE" | sed 's/^/      /'
else
    echo "   ❌ redis.conf not found in $COMPOSE_FILE!"
    exit 1
fi

# Restart Redis
echo ""
echo "🚀 Starting Redis container..."
docker-compose -f "$COMPOSE_FILE" up -d redis

# Wait for Redis to start
echo ""
echo "⏳ Waiting for Redis to start (10 seconds)..."
sleep 10

# Check if Redis is running
echo ""
echo "📊 Checking Redis status..."
if docker ps | grep -q binance-bot-redis; then
    echo "   ✅ Redis container is running!"
    
    # Test Redis connection
    echo ""
    echo "🧪 Testing Redis connection..."
    if docker exec binance-bot-redis redis-cli ping 2>/dev/null | grep -q PONG; then
        echo "   ✅ Redis is responding to PING"
        
        # Check keys
        KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
        echo "   📊 Total keys in Redis: $KEY_COUNT"
        
        if [ "$KEY_COUNT" -gt 0 ]; then
            echo "   ✅ Data found in Redis!"
        else
            echo "   ⚠️  No data in Redis (this might be expected if it's a fresh start)"
        fi
    else
        echo "   ❌ Redis is not responding to PING"
        echo "   Check logs: docker logs binance-bot-redis"
    fi
else
    echo "   ❌ Redis container is not running!"
    echo ""
    echo "📋 Container logs:"
    docker logs --tail 50 binance-bot-redis 2>&1 | sed 's/^/   /' || echo "   Could not read logs"
    echo ""
    echo "💡 Try running: docker logs binance-bot-redis"
    exit 1
fi

echo ""
echo "✅ Redis fix completed!"
echo ""
echo "💡 If Redis is still restarting, check:"
echo "   1. redis.conf exists in deployment directory"
echo "   2. redis.conf is mounted correctly in docker-compose.yml"
echo "   3. /data directory has correct permissions"
echo "   4. Check logs: docker logs binance-bot-redis"
echo ""

