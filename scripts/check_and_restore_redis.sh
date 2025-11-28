#!/bin/bash
# Check Redis data and restore from backup if needed
# Usage: ./check_and_restore_redis.sh

set -e

echo "🔍 Checking Redis Data Status"
echo "============================="
echo ""

# Check current Redis data
echo "1️⃣  Current Redis Status:"
if docker ps | grep -q binance-bot-redis; then
    echo "   ✅ Redis container is running"
    
    KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
    echo "   📊 Current keys in Redis: $KEY_COUNT"
    
    if [ "$KEY_COUNT" -eq "0" ]; then
        echo "   ⚠️  WARNING: No data in Redis!"
    else
        echo "   ✅ Data found in Redis"
        echo ""
        echo "   Sample keys:"
        docker exec binance-bot-redis redis-cli --scan --pattern "*" | head -10 | sed 's/^/      /' || echo "      No keys found"
    fi
else
    echo "   ❌ Redis container is not running"
    exit 1
fi

echo ""
echo "2️⃣  Checking for backups:"
BACKUP_DIR="${BACKUP_DIR:-/home/jenkins-deploy/redis-backups}"

if [ -d "$BACKUP_DIR" ]; then
    echo "   ✅ Backup directory exists: $BACKUP_DIR"
    
    # Count backups
    RDB_COUNT=$(ls -1 "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | wc -l || echo "0")
    echo "   📦 Available RDB backups: $RDB_COUNT"
    
    if [ "$RDB_COUNT" -gt 0 ]; then
        echo ""
        echo "   Available backups:"
        ls -lh "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | tail -5 | awk '{print "      " $9 " (" $5 ")"}'
        
        if [ "$KEY_COUNT" -eq "0" ]; then
            echo ""
            echo "   💡 You have backups available. Would you like to restore?"
            echo ""
            LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | head -1)
            if [ -n "$LATEST_BACKUP" ]; then
                echo "   Latest backup: $LATEST_BACKUP"
                echo ""
                echo "   To restore, run:"
                echo "   bash scripts/restore_redis.sh $LATEST_BACKUP"
            fi
        fi
    else
        echo "   ⚠️  No RDB backups found"
    fi
else
    echo "   ⚠️  Backup directory not found: $BACKUP_DIR"
fi

echo ""
echo "3️⃣  Checking Redis volume:"
if docker volume ls | grep -q redis-data; then
    echo "   ✅ redis-data volume exists"
    VOLUME_PATH=$(docker volume inspect redis-data --format '{{ .Mountpoint }}' 2>/dev/null || echo "unknown")
    echo "   Volume path: $VOLUME_PATH"
    
    # Check if volume has data files
    echo ""
    echo "   Files in volume:"
    docker run --rm -v redis-data:/data alpine ls -lah /data 2>/dev/null | sed 's/^/      /' || echo "      Could not list volume contents"
else
    echo "   ⚠️  redis-data volume not found"
fi

echo ""
echo "============================="
echo "✅ Check complete!"
echo ""

if [ "$KEY_COUNT" -eq "0" ]; then
    echo "⚠️  IMPORTANT: Redis has no data!"
    echo ""
    echo "Possible causes:"
    echo "  1. Volume was recreated during deployment"
    echo "  2. Data wasn't persisted before restart"
    echo "  3. Different Redis instance is being used"
    echo ""
    echo "💡 Solution: Restore from backup"
    echo "  bash scripts/restore_redis.sh <backup-file.rdb>"
    echo ""
fi

