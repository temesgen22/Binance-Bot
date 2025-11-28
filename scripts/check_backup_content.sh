#!/bin/bash
# Check if a Redis backup file actually contains data
# Usage: ./check_backup_content.sh <backup-file.rdb>

if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file.rdb>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔍 Checking Redis Backup File Content"
echo "====================================="
echo ""

# File info
FILE_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
echo "📁 File: $BACKUP_FILE"
echo "   Size: $FILE_SIZE bytes"

# RDB files typically have a magic header
echo ""
echo "🔬 Analyzing RDB file structure..."
HEADER=$(head -c 5 "$BACKUP_FILE" 2>/dev/null | od -An -tx1 | tr -d ' \n' || echo "unknown")
echo "   First 5 bytes (hex): $HEADER"

# RDB files should start with "REDIS"
if echo "$HEADER" | grep -q "5245444953"; then
    echo "   ✅ Valid RDB header found (REDIS)"
else
    echo "   ⚠️  RDB header not found - file might be corrupted or empty"
fi

# Try to extract readable strings (keys might be visible)
echo ""
echo "📋 Searching for readable strings (potential keys)..."
STRINGS=$(strings "$BACKUP_FILE" 2>/dev/null | head -20 | grep -E "(binance|strategy|trade)" || echo "   No obvious key patterns found")
if [ -n "$STRINGS" ] && [ "$STRINGS" != "   No obvious key patterns found" ]; then
    echo "   Found potential keys:"
    echo "$STRINGS" | sed 's/^/      /'
else
    echo "   $STRINGS"
fi

# Try to load in a test Redis instance
echo ""
echo "🧪 Testing backup by loading into temporary Redis..."
TEMP_CONTAINER="redis-backup-test-$$"

# Start temp Redis
docker run -d --name "$TEMP_CONTAINER" \
    -v "$(dirname "$BACKUP_FILE")":/backup:ro \
    redis:7-alpine \
    redis-server --appendonly no --dbfilename test.rdb --dir /tmp 2>/dev/null || {
    echo "   ⚠️  Could not start test Redis"
    exit 1
}

sleep 2

# Copy and load backup
echo "   Copying backup to test Redis..."
docker cp "$BACKUP_FILE" "$TEMP_CONTAINER:/tmp/test.rdb" 2>/dev/null || {
    echo "   ⚠️  Could not copy backup"
    docker rm -f "$TEMP_CONTAINER" 2>/dev/null || true
    exit 1
}

# Stop and restart with the backup
docker stop "$TEMP_CONTAINER" 2>/dev/null || true
docker rm "$TEMP_CONTAINER" 2>/dev/null || true

# Start fresh with backup as dump.rdb
docker run -d --name "$TEMP_CONTAINER" \
    -v "$(dirname "$BACKUP_FILE")":/backup:ro \
    redis:7-alpine \
    sh -c "cp /backup/$(basename "$BACKUP_FILE") /tmp/dump.rdb && redis-server --appendonly no --dbfilename dump.rdb --dir /tmp" 2>/dev/null || {
    echo "   ⚠️  Could not start Redis with backup"
    exit 1
}

sleep 3

# Check keys
KEY_COUNT=$(docker exec "$TEMP_CONTAINER" redis-cli DBSIZE 2>/dev/null || echo "0")
echo "   📊 Keys in backup: $KEY_COUNT"

if [ "$KEY_COUNT" -gt 0 ]; then
    echo "   ✅ Backup contains data!"
    echo ""
    echo "   Sample keys:"
    docker exec "$TEMP_CONTAINER" redis-cli --scan --pattern "*" | head -10 | sed 's/^/      /'
else
    echo "   ❌ Backup appears to be empty"
fi

# Cleanup
docker stop "$TEMP_CONTAINER" 2>/dev/null || true
docker rm -f "$TEMP_CONTAINER" 2>/dev/null || true

echo ""
echo "✅ Analysis complete!"

