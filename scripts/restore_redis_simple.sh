#!/bin/bash
# Simplified Redis restore script that properly handles AOF/RDB priority
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

# CRITICAL: Remove ALL AOF files first (Redis prioritizes AOF over RDB)
echo "🧹 Removing ALL AOF files (critical for RDB restore)..."
docker run --rm -v "$REDIS_VOLUME":/data alpine sh -c "
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
" -v "$(dirname "$BACKUP_FILE")":/backup:ro

# Temporarily disable AOF in redis.conf
REDIS_CONF="$DEPLOY_DIR/redis.conf"
if [ -f "$REDIS_CONF" ]; then
    echo "🔧 Temporarily disabling AOF in redis.conf..."
    cp "$REDIS_CONF" "$REDIS_CONF.backup"
    sed -i 's/^appendonly yes/appendonly no/' "$REDIS_CONF" 2>/dev/null || \
    sed -i 's/appendonly yes/appendonly no/' "$REDIS_CONF" 2>/dev/null || true
    
    # Ensure AOF is disabled
    if ! grep -q "^appendonly no" "$REDIS_CONF"; then
        # Remove any appendonly line and add new one
        sed -i '/^appendonly/d' "$REDIS_CONF"
        echo "appendonly no" >> "$REDIS_CONF"
    fi
else
    echo "⚠️  redis.conf not found, will use command override"
fi

# Start Redis (will load from RDB since AOF is disabled and AOF files are removed)
echo "🚀 Starting Redis to load RDB..."
docker-compose up -d redis

# Wait for Redis to start and load RDB
echo "⏳ Waiting for Redis to load RDB file..."
sleep 10

# Check if data loaded
KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
echo "📊 Keys loaded: $KEY_COUNT"

if [ "$KEY_COUNT" -gt 0 ]; then
    echo "✅ Data loaded successfully!"
    echo ""
    echo "🔑 Sample keys:"
    docker exec binance-bot-redis redis-cli --scan --pattern "*" | head -10 | sed 's/^/   /'
    
    # Restore original redis.conf
    if [ -f "$REDIS_CONF.backup" ]; then
        echo ""
        echo "🔄 Re-enabling AOF in redis.conf..."
        mv "$REDIS_CONF.backup" "$REDIS_CONF"
        
        # CRITICAL: Remove any AOF files that might have been created
        # before restarting with AOF enabled
        echo "🧹 Removing any AOF files before re-enabling AOF..."
        docker run --rm -v "$REDIS_VOLUME":/data alpine sh -c "
            cd /data
            rm -rf appendonly.aof appendonlydir appendonly.aof.* *.aof 2>/dev/null || true
            echo 'Files in /data before restart:'
            ls -lah /data
        "
        
        # Restart Redis with AOF enabled (data is already in memory, will be saved to AOF)
        echo "🔄 Restarting Redis with AOF enabled..."
        docker-compose restart redis
        sleep 8
        
        # Final verification
        KEY_COUNT_FINAL=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
        echo "📊 Final key count: $KEY_COUNT_FINAL"
        
        if [ "$KEY_COUNT_FINAL" -gt 0 ]; then
            echo "✅ Redis data restored successfully with AOF enabled!"
        else
            echo "⚠️  Warning: Keys lost after enabling AOF"
        fi
    fi
else
    echo "❌ No keys loaded - backup might be empty or corrupted"
    echo ""
    echo "Checking backup file..."
    BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
    echo "   Backup file size: $BACKUP_SIZE bytes"
    
    # Restore original config
    if [ -f "$REDIS_CONF.backup" ]; then
        mv "$REDIS_CONF.backup" "$REDIS_CONF"
    fi
fi

echo ""
echo "📋 Redis logs (last 20 lines):"
docker logs --tail 20 binance-bot-redis 2>&1 | grep -E "(Loading|DB loaded|Ready|Error)" | sed 's/^/   /' || echo "   No relevant logs found"

