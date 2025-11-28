#!/bin/bash
# Pre-deployment backup script
# Run this BEFORE Jenkins deployment to preserve Redis data

set -e

echo "🚀 Pre-Deployment Redis Backup"
echo "================================"
echo ""

# Check if we're on the production server
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: docker-compose.yml not found"
    echo "   Please run this script from the project root directory"
    exit 1
fi

# Set backup directory (use home directory for persistence)
BACKUP_DIR="${HOME}/redis-backups"
mkdir -p "$BACKUP_DIR"

echo "📁 Backup directory: $BACKUP_DIR"
echo ""

# Run the backup
if [ -f "scripts/backup_redis.sh" ]; then
    BACKUP_DIR="$BACKUP_DIR" bash scripts/backup_redis.sh
else
    echo "⚠️  backup_redis.sh not found, using inline backup..."
    
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/redis-backup-$TIMESTAMP.rdb"
    
    # Create RDB snapshot
    docker exec -it binance-bot-redis redis-cli BGSAVE
    sleep 3
    
    # Copy RDB file
    docker cp binance-bot-redis:/data/dump.rdb "$BACKUP_FILE" 2>/dev/null || {
        echo "⚠️  Could not copy dump.rdb, trying alternative method..."
        docker exec -it binance-bot-redis redis-cli --rdb /tmp/backup.rdb
        docker cp binance-bot-redis:/tmp/backup.rdb "$BACKUP_FILE"
    }
    
    echo "✅ Backup saved to: $BACKUP_FILE"
fi

echo ""
echo "✅ Pre-deployment backup completed!"
echo ""
echo "📋 Backup Behavior:"
echo "   ✅ Each run creates a NEW backup with unique timestamp"
echo "   ✅ Previous backups are NOT overwritten"
echo "   ✅ All backups are kept in: $BACKUP_DIR"
echo ""
echo "💡 To clean old backups (keep last 10), run:"
echo "   CLEANUP_OLD_BACKUPS=true bash scripts/backup_redis.sh"
echo ""
echo "📋 Next steps:"
echo "   1. Deploy with Jenkins"
echo "   2. After deployment, verify Redis persistence is working"
echo "   3. If data is missing, restore using:"
echo "      ./scripts/restore_redis.sh $BACKUP_DIR/redis-backup-*.rdb"
echo ""

