#!/bin/bash
# Backup Redis data before deployment
# This script saves all Redis data to a backup file

set -e

BACKUP_DIR="${BACKUP_DIR:-/tmp/redis-backups}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/redis-backup-$TIMESTAMP.rdb"
BACKUP_JSON="$BACKUP_DIR/redis-backup-$TIMESTAMP.json"

echo "📦 Starting Redis backup..."

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Check if Redis container is running
if ! docker ps | grep -q binance-bot-redis; then
    echo "⚠️  Warning: Redis container is not running"
    echo "   Starting Redis container..."
    docker-compose up -d redis
    sleep 2
fi

# Method 1: Save RDB snapshot (binary format, faster)
echo "💾 Creating RDB snapshot..."
docker exec binance-bot-redis redis-cli --rdb /tmp/redis-backup.rdb || {
    echo "⚠️  RDB snapshot failed, trying BGSAVE..."
    docker exec binance-bot-redis redis-cli BGSAVE
    sleep 2
    docker exec binance-bot-redis redis-cli --rdb /tmp/redis-backup.rdb || true
}

# Copy RDB file from container
if docker exec -it binance-bot-redis test -f /tmp/redis-backup.rdb; then
    docker cp binance-bot-redis:/tmp/redis-backup.rdb "$BACKUP_FILE"
    echo "✅ RDB backup saved to: $BACKUP_FILE"
else
    echo "⚠️  RDB backup file not found in container"
fi

# Method 2: Export all keys as JSON (human-readable, complete)
echo "📋 Exporting all keys to JSON..."
docker exec binance-bot-redis redis-cli --scan --pattern "*" > /tmp/redis-keys.txt || true

if [ -s /tmp/redis-keys.txt ]; then
    echo "{" > "$BACKUP_JSON"
    FIRST=true
    while IFS= read -r key; do
        if [ -n "$key" ]; then
            if [ "$FIRST" = true ]; then
                FIRST=false
            else
                echo "," >> "$BACKUP_JSON"
            fi
            value=$(docker exec binance-bot-redis redis-cli GET "$key" | sed 's/"/\\"/g')
            echo -n "  \"$key\": \"$value\"" >> "$BACKUP_JSON"
        fi
    done < /tmp/redis-keys.txt
    echo "" >> "$BACKUP_JSON"
    echo "}" >> "$BACKUP_JSON"
    echo "✅ JSON backup saved to: $BACKUP_JSON"
else
    echo "⚠️  No keys found in Redis"
fi

# Method 3: Backup the entire volume (most reliable)
echo "💿 Backing up Redis volume..."
docker run --rm \
    -v binance-bot_redis-data:/data:ro \
    -v "$BACKUP_DIR":/backup \
    alpine tar czf "/backup/redis-volume-backup-$TIMESTAMP.tar.gz" -C /data . 2>/dev/null || {
    echo "⚠️  Volume backup failed (volume might not exist yet)"
}

# List all backups
echo ""
echo "📁 Backup files created:"
ls -lh "$BACKUP_DIR"/*-$TIMESTAMP* 2>/dev/null || echo "   No backup files found"

# Optional: Clean up old backups (keep last 10)
if [ "${CLEANUP_OLD_BACKUPS:-false}" = "true" ]; then
    echo ""
    echo "🧹 Cleaning up old backups (keeping last 10)..."
    # Keep only the 10 most recent backups
    ls -t "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
    ls -t "$BACKUP_DIR"/redis-backup-*.json 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
    ls -t "$BACKUP_DIR"/redis-volume-backup-*.tar.gz 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
    echo "✅ Old backups cleaned up"
fi

# Show backup summary
echo ""
echo "✅ Backup completed!"
echo "   Backup location: $BACKUP_DIR"
echo "   Timestamp: $TIMESTAMP"
echo ""
echo "📊 Total backups in directory:"
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | wc -l || echo "0")
echo "   RDB backups: $BACKUP_COUNT"
echo ""
echo "💡 Note: Each backup creates a NEW file with unique timestamp"
echo "   Previous backups are NOT overwritten"
echo "   To clean old backups, set CLEANUP_OLD_BACKUPS=true"
echo ""
echo "📊 Current Redis data:"
KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
echo "   Total keys: $KEY_COUNT"

# Show sample keys
echo ""
echo "🔑 Sample keys (first 10):"
docker exec binance-bot-redis redis-cli --scan --pattern "*" | head -10 || echo "   No keys found"

