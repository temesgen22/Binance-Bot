#!/bin/bash
# Check what's in the Redis volume
# Usage: ./check_redis_volume.sh

echo "🔍 Checking Redis Volume Contents"
echo "================================="
echo ""

# Find the volume
REDIS_VOLUME=$(docker volume ls | grep redis-data | awk '{print $2}' | head -1)

if [ -z "$REDIS_VOLUME" ]; then
    echo "❌ No Redis volume found!"
    exit 1
fi

echo "📦 Volume: $REDIS_VOLUME"
echo ""

# Check volume size
VOLUME_SIZE=$(docker system df -v | grep "$REDIS_VOLUME" | awk '{print $3}')
echo "   Size: $VOLUME_SIZE"
echo ""

# List files in volume
echo "📁 Files in volume:"
docker run --rm -v "$REDIS_VOLUME":/data alpine ls -lah /data 2>/dev/null | sed 's/^/   /' || echo "   Could not list files"
echo ""

# Check if Redis is running
if docker ps | grep -q binance-bot-redis; then
    echo "✅ Redis container is running"
    echo ""
    echo "📊 Keys in Redis:"
    KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
    echo "   Total keys: $KEY_COUNT"
    
    if [ "$KEY_COUNT" -gt 0 ]; then
        echo ""
        echo "   Sample keys:"
        docker exec binance-bot-redis redis-cli --scan --pattern "*" | head -10 | sed 's/^/      /'
    else
        echo "   ⚠️  Volume is empty - no data found"
    fi
else
    echo "⚠️  Redis container is not running"
fi

echo ""
echo "💡 To restore from backup, run:"
echo "   bash scripts/restore_redis.sh /home/jenkins-deploy/redis-backups/redis-backup-*.rdb"
echo ""

