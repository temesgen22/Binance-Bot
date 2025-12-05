#!/bin/bash
# Simplified Redis restore script (RDB-only)
# Usage: ./restore_redis_simple.sh [backup-file.rdb]

set -e

BACKUP_DIR="${BACKUP_DIR:-/home/jenkins-deploy/redis-backups}"
DEPLOY_PATH="${DEPLOY_PATH:-/home/jenkins-deploy/binance-bot}"

if [ -z "$1" ]; then
    echo "📦 Available backups:"
    ls -lh "$BACKUP_DIR"/*.rdb 2>/dev/null || {
        echo "   No RDB backups found in $BACKUP_DIR"
        exit 1
    }
    echo ""
    echo "Usage: $0 <backup-file.rdb>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔄 Restoring Redis from backup: $BACKUP_FILE"

# Find deploy directory
DEPLOY_DIR="$DEPLOY_PATH"
if [ ! -d "$DEPLOY_DIR" ] || [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
    DEPLOY_DIR="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd || echo "$DEPLOY_DIR")"
fi
if [ ! -d "$DEPLOY_DIR" ] || [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
    DEPLOY_DIR="$(pwd)"
fi

echo "📁 Using deploy directory: $DEPLOY_DIR"
cd "$DEPLOY_DIR"

# Stop Redis
echo "🛑 Stopping Redis..."
docker-compose stop redis 2>/dev/null || true
docker rm -f binance-bot-redis 2>/dev/null || true

# Find Redis volume
echo "🔍 Finding Redis volume..."
REDIS_VOLUME=$(docker volume ls | grep redis-data | awk '{print $2}' | head -1)

if [ -z "$REDIS_VOLUME" ]; then
    echo "❌ Error: Redis volume not found!"
    exit 1
fi

echo "   ✅ Found volume: $REDIS_VOLUME"

# Remove AOF + old RDB and copy new RDB
echo "🧹 Removing ALL AOF files and old RDB, then copying backup..."
docker run --rm \
    -v "$REDIS_VOLUME":/data \
    -v "$(dirname "$BACKUP_FILE")":/backup:ro \
    alpine sh -c "
        cd /data
        echo 'Removing AOF files and directories...'
        rm -rf appendonly.aof appendonlydir appendonly.aof.* *.aof 2>/dev/null || true
        echo 'Removing old RDB...'
        rm -f dump.rdb
        echo 'Copying backup RDB...'
        cp /backup/$(basename "$BACKUP_FILE") dump.rdb
        chmod 644 dump.rdb
        chown 999:1000 dump.rdb 2>/dev/null || true
        echo ''
        echo 'Files in /data:'
        ls -lah /data
        echo ''
        echo 'Verifying RDB file:'
        [ -s dump.rdb ] && echo '  ✅ RDB file has content' || echo '  ❌ RDB file is empty!'
    "

# Ensure AOF is disabled in redis.conf
REDIS_CONF="$DEPLOY_DIR/redis.conf"
if [ -f "$REDIS_CONF" ]; then
    echo "🔧 Ensuring appendonly no in redis.conf..."
    # Remove any appendonly lines and set appendonly no
    sed -i '/^appendonly /d' "$REDIS_CONF"
    echo "appendonly no" >> "$REDIS_CONF"
else
    echo "⚠️  redis.conf not found - make sure Redis is not started with appendonly yes via docker-compose"
fi

# Start Redis (RDB-only)
echo "🚀 Starting Redis to load RDB..."
docker-compose up -d redis

echo "⏳ Waiting for Redis to load RDB file..."
sleep 10

KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
echo "📊 Keys loaded: $KEY_COUNT"

if [ "$KEY_COUNT" -gt 0 ]; then
    echo "✅ Redis data restored successfully (RDB-only, AOF disabled)."
    echo ""
    echo "🔑 Sample keys:"
    docker exec binance-bot-redis redis-cli --scan --pattern "*" | head -10 | sed 's/^/   /'
else
    echo "❌ No keys loaded - backup might be empty or corrupted."
    BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
    echo "   Backup file size: $BACKUP_SIZE bytes"
fi

echo ""
echo "📋 Redis logs (last 20 lines):"
docker logs --tail 20 binance-bot-redis 2>&1 | grep -E "(Loading|DB loaded|Ready|Error)" | sed 's/^/   /' || echo "   No relevant logs found"
