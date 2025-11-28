#!/bin/bash
# Force restore Redis from RDB backup by temporarily disabling AOF
# Usage: ./restore_redis_force_rdb.sh <backup-file.rdb>

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file.rdb>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔄 Force Restoring Redis from RDB (AOF will be disabled temporarily)"
echo "====================================================================="
echo ""

# Check backup file
BACKUP_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
echo "📦 Backup file: $BACKUP_FILE"
echo "   Size: $BACKUP_SIZE bytes"

if [ "$BACKUP_SIZE" -lt 100 ]; then
    echo "   ⚠️  Warning: Backup file is very small, might be empty"
    read -p "   Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Stop Redis
echo ""
echo "🛑 Stopping Redis..."
docker-compose stop redis

# Find volume
REDIS_VOLUME=$(docker volume ls | grep redis-data | awk '{print $2}' | head -1)
if [ -z "$REDIS_VOLUME" ]; then
    echo "❌ Error: Redis volume not found!"
    exit 1
fi

echo "   ✅ Found volume: $REDIS_VOLUME"

# Remove ALL persistence files and restore RDB
echo ""
echo "📥 Restoring RDB backup (removing all AOF files)..."
docker run --rm \
    -v "$REDIS_VOLUME":/data \
    -v "$(dirname "$BACKUP_FILE")":/backup:ro \
    alpine sh -c "
        cd /data
        echo 'Removing all persistence files...'
        rm -rf dump.rdb appendonly.aof appendonlydir
        
        echo 'Copying RDB backup...'
        cp /backup/$(basename "$BACKUP_FILE") dump.rdb
        
        echo 'Setting permissions...'
        chmod 644 dump.rdb
        
        echo ''
        echo 'Files in /data:'
        ls -lah /data
        echo ''
        echo 'RDB file info:'
        ls -lh dump.rdb
    "

# Create a temporary redis.conf that disables AOF
echo ""
echo "📝 Creating temporary redis.conf (AOF disabled)..."
TEMP_CONF=$(mktemp)
cat > "$TEMP_CONF" << 'EOF'
# Temporary config for RDB-only restore
appendonly no
dir /data
dbfilename dump.rdb
protected-mode no
EOF

# Copy temp config to volume
docker run --rm \
    -v "$REDIS_VOLUME":/data \
    -v "$TEMP_CONF":/tmp/redis.conf:ro \
    alpine sh -c "cp /tmp/redis.conf /data/redis-temp.conf && cat /data/redis-temp.conf"

# Start Redis with AOF disabled
echo ""
echo "🚀 Starting Redis with AOF disabled (to force RDB load)..."
docker run -d --name redis-temp-restore \
    -v "$REDIS_VOLUME":/data \
    redis:7-alpine \
    redis-server /data/redis-temp.conf 2>/dev/null || {
    echo "   ⚠️  Could not start temp Redis, trying normal start..."
    docker rm -f redis-temp-restore 2>/dev/null || true
}

# Wait and check
sleep 5

if docker ps | grep -q redis-temp-restore; then
    KEY_COUNT=$(docker exec redis-temp-restore redis-cli DBSIZE 2>/dev/null || echo "0")
    echo "   📊 Keys loaded: $KEY_COUNT"
    
    if [ "$KEY_COUNT" -gt 0 ]; then
        echo "   ✅ Data loaded successfully!"
        echo ""
        echo "   Sample keys:"
        docker exec redis-temp-restore redis-cli --scan --pattern "*" | head -10 | sed 's/^/      /'
        
        # Stop temp Redis
        docker stop redis-temp-restore
        docker rm redis-temp-restore
        
        # Now start normal Redis (it will use the RDB we just verified)
        echo ""
        echo "🔄 Starting normal Redis container..."
        docker-compose up -d redis
        sleep 5
        
        # Verify
        KEY_COUNT_FINAL=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
        echo "   📊 Final key count: $KEY_COUNT_FINAL"
        
        if [ "$KEY_COUNT_FINAL" -gt 0 ]; then
            echo "   ✅ Restore successful!"
        else
            echo "   ⚠️  Keys lost during normal Redis start"
        fi
    else
        echo "   ❌ No keys loaded - backup file might be empty"
        docker stop redis-temp-restore
        docker rm redis-temp-restore
    fi
else
    echo "   ⚠️  Temp Redis didn't start, trying normal restore..."
    docker rm -f redis-temp-restore 2>/dev/null || true
    docker-compose up -d redis
    sleep 5
    KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
    echo "   📊 Keys: $KEY_COUNT"
fi

# Cleanup
rm -f "$TEMP_CONF"

echo ""
echo "✅ Restore process completed!"

