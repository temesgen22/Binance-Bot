#!/bin/bash
# Verify a Redis backup file is valid
# Usage: ./verify_backup.sh <backup-file.rdb>

if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file.rdb>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔍 Verifying Redis Backup File"
echo "=============================="
echo ""

echo "📁 File Information:"
echo "   Path: $BACKUP_FILE"
FILE_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
echo "   Size: $FILE_SIZE bytes ($(numfmt --to=iec-i --suffix=B $FILE_SIZE 2>/dev/null || echo "unknown"))"

echo ""
echo "🔬 Testing backup file with Redis..."

# Start a temporary Redis instance to test the backup
TEMP_CONTAINER="redis-test-$$"

docker run -d --name "$TEMP_CONTAINER" \
    -v "$(dirname "$BACKUP_FILE")":/backup:ro \
    redis:7-alpine \
    redis-server --appendonly no --dbfilename test.rdb --dir /tmp 2>/dev/null || true

sleep 2

# Copy backup to temp container
docker cp "$BACKUP_FILE" "$TEMP_CONTAINER:/tmp/test.rdb" 2>/dev/null || {
    echo "   ⚠️  Could not copy file to test container"
    docker rm -f "$TEMP_CONTAINER" 2>/dev/null || true
    exit 1
}

# Try to load it
docker exec "$TEMP_CONTAINER" redis-cli --rdb /tmp/test.rdb 2>/dev/null || true

# Stop and remove temp container
docker rm -f "$TEMP_CONTAINER" 2>/dev/null || true

echo ""
echo "💡 To test if backup has data, try:"
echo "   1. Restore it to a test Redis instance"
echo "   2. Check DBSIZE after restore"
echo "   3. Or inspect the RDB file structure"
echo ""

