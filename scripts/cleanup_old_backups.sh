#!/bin/bash
# Clean up old Redis backups, keeping only the most recent ones
# Usage: ./cleanup_old_backups.sh [number_to_keep]

set -e

BACKUP_DIR="${BACKUP_DIR:-/home/jenkins-deploy/redis-backups}"
KEEP_COUNT="${1:-10}"  # Default: keep last 10 backups

if [ ! -d "$BACKUP_DIR" ]; then
    echo "❌ Backup directory not found: $BACKUP_DIR"
    exit 1
fi

echo "🧹 Cleaning up old Redis backups..."
echo "   Backup directory: $BACKUP_DIR"
echo "   Keeping last: $KEEP_COUNT backups"
echo ""

# Count current backups
RDB_COUNT=$(ls -1 "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | wc -l || echo "0")
JSON_COUNT=$(ls -1 "$BACKUP_DIR"/redis-backup-*.json 2>/dev/null | wc -l || echo "0")
VOLUME_COUNT=$(ls -1 "$BACKUP_DIR"/redis-volume-backup-*.tar.gz 2>/dev/null | wc -l || echo "0")

echo "📊 Current backups:"
echo "   RDB files: $RDB_COUNT"
echo "   JSON files: $JSON_COUNT"
echo "   Volume backups: $VOLUME_COUNT"
echo ""

# Clean up RDB backups
if [ "$RDB_COUNT" -gt "$KEEP_COUNT" ]; then
    REMOVE_COUNT=$((RDB_COUNT - KEEP_COUNT))
    echo "🗑️  Removing $REMOVE_COUNT old RDB backups..."
    ls -t "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | xargs rm -f
    echo "   ✅ Cleaned up RDB backups"
else
    echo "   ℹ️  RDB backups: No cleanup needed (only $RDB_COUNT backups)"
fi

# Clean up JSON backups
if [ "$JSON_COUNT" -gt "$KEEP_COUNT" ]; then
    REMOVE_COUNT=$((JSON_COUNT - KEEP_COUNT))
    echo "🗑️  Removing $REMOVE_COUNT old JSON backups..."
    ls -t "$BACKUP_DIR"/redis-backup-*.json 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | xargs rm -f
    echo "   ✅ Cleaned up JSON backups"
else
    echo "   ℹ️  JSON backups: No cleanup needed (only $JSON_COUNT backups)"
fi

# Clean up volume backups
if [ "$VOLUME_COUNT" -gt "$KEEP_COUNT" ]; then
    REMOVE_COUNT=$((VOLUME_COUNT - KEEP_COUNT))
    echo "🗑️  Removing $REMOVE_COUNT old volume backups..."
    ls -t "$BACKUP_DIR"/redis-volume-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | xargs rm -f
    echo "   ✅ Cleaned up volume backups"
else
    echo "   ℹ️  Volume backups: No cleanup needed (only $VOLUME_COUNT backups)"
fi

# Show remaining backups
echo ""
echo "📁 Remaining backups:"
ls -lh "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | tail -$KEEP_COUNT || echo "   No RDB backups found"
echo ""
echo "✅ Cleanup completed!"

