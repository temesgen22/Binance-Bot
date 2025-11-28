#!/bin/bash
# Restore Redis data from backup after deployment
# Usage: ./restore_redis.sh [backup-file.rdb]

set -e

BACKUP_DIR="${BACKUP_DIR:-/home/jenkins-deploy/redis-backups}"

if [ -z "$1" ]; then
    echo "📦 Available backups:"
    ls -lh "$BACKUP_DIR"/*.rdb 2>/dev/null || {
        echo "   No RDB backups found in $BACKUP_DIR"
        exit 1
    }
    echo ""
    echo "Usage: $0 <backup-file.rdb>"
    echo "Example: $0 $BACKUP_DIR/redis-backup-20251128-120000.rdb"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔄 Restoring Redis from backup: $BACKUP_FILE"

# Check if Redis container is running
if ! docker ps | grep -q binance-bot-redis; then
    echo "⚠️  Redis container is not running. Starting it..."
    docker-compose up -d redis
    sleep 3
fi

# Stop Redis to restore data safely
echo "🛑 Stopping Redis container..."
docker-compose stop redis

# Find the correct Redis volume name
echo "🔍 Finding Redis volume..."
REDIS_VOLUME=$(docker volume ls | grep redis-data | awk '{print $2}' | head -1)

if [ -z "$REDIS_VOLUME" ]; then
    echo "❌ Error: Redis volume not found!"
    echo "   Available volumes:"
    docker volume ls | sed 's/^/      /'
    exit 1
fi

echo "   ✅ Found volume: $REDIS_VOLUME"

# Copy backup file into container's data directory
echo "📥 Copying backup file to Redis data directory..."
echo "   Removing old AOF files and directories..."
docker run --rm \
    -v "$REDIS_VOLUME":/data \
    -v "$(dirname "$BACKUP_FILE")":/backup:ro \
    alpine sh -c "
        cd /data
        # Remove all AOF files and directories (Redis will recreate if needed)
        rm -rf appendonly.aof appendonlydir
        # Remove old RDB
        rm -f dump.rdb
        # Copy new RDB backup
        cp /backup/$(basename "$BACKUP_FILE") dump.rdb
        # Set correct permissions
        chmod 644 dump.rdb
        echo 'Files in /data after restore:'
        ls -la /data
        echo ''
        echo 'RDB file size:'
        ls -lh dump.rdb
    "

# Start Redis (it will automatically load dump.rdb)
# Note: With AOF disabled temporarily, Redis will load from RDB
echo "🚀 Starting Redis container..."
docker-compose start redis

# Give Redis time to load the RDB file
echo "⏳ Waiting for Redis to load RDB file..."
sleep 8

# Check Redis logs for loading messages
echo ""
echo "📋 Checking Redis startup logs..."
echo "   Looking for RDB loading messages..."
docker logs --tail 30 binance-bot-redis 2>&1 | grep -E "(Loading|DB loaded|Ready to accept|Error|Fatal|RDB)" | sed 's/^/   /' || echo "   No loading messages found"

# Check if Redis is responding
echo ""
echo "🧪 Testing Redis connection..."
if docker exec binance-bot-redis redis-cli ping 2>/dev/null | grep -q PONG; then
    echo "   ✅ Redis is responding"
else
    echo "   ❌ Redis is not responding"
    echo "   Check logs: docker logs binance-bot-redis"
fi

# Verify data was restored
echo "✅ Verifying restored data..."
KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
echo "   Total keys restored: $KEY_COUNT"

if [ "$KEY_COUNT" -gt 0 ]; then
    echo "✅ Redis data restored successfully!"
    echo ""
    echo "🔑 Sample restored keys:"
    docker exec binance-bot-redis redis-cli --scan --pattern "*" | head -10
else
    echo "⚠️  Warning: No keys found after restore"
    echo "   The backup file might be empty or corrupted"
fi

