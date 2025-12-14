#!/bin/bash
# Deployment script for Binance Bot
# Handles Redis backup, container restart, and restore if needed

set -e

DEPLOY_PATH="${1:-/home/jenkins-deploy/binance-bot}"
BACKUP_DIR="${BACKUP_DIR:-/home/jenkins-deploy/redis-backups}"

echo "🚀 Starting deployment..."
echo "📁 Deployment path: $DEPLOY_PATH"
echo "📁 Backup directory: $BACKUP_DIR"

cd "$DEPLOY_PATH" || {
    echo "❌ Error: Cannot cd to $DEPLOY_PATH"
    exit 1
}

if [ ! -f docker-compose.yml ]; then
    echo "⚠️  docker-compose.yml not found. Skipping restart."
    exit 0
fi

# Verify Redis volume exists
echo '📦 Checking Redis volume...'
docker volume ls | grep redis-data || echo '⚠️  Warning: redis-data volume not found'

# Create backup BEFORE stopping containers
echo ''
echo '💾 Creating backup before deployment...'
mkdir -p "$BACKUP_DIR"

# Ensure backup directory is writable
if [ ! -w "$BACKUP_DIR" ]; then
    echo "⚠️  Warning: Backup directory is not writable: $BACKUP_DIR"
    echo "   Attempting to fix permissions..."
    chmod 755 "$BACKUP_DIR" 2>/dev/null || echo "   Could not fix permissions"
fi

echo "📁 Backup directory: $BACKUP_DIR"

# Check if Redis container is running and has data
if docker ps | grep -q binance-bot-redis; then
    KEY_COUNT_BEFORE=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo '0')
    echo "📊 Redis keys before backup: $KEY_COUNT_BEFORE"
    
    if [ "$KEY_COUNT_BEFORE" -gt "0" ]; then
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        BACKUP_FILE="$BACKUP_DIR/redis-backup-$TIMESTAMP.rdb"
        
        echo '💾 Creating RDB snapshot...'
        docker exec binance-bot-redis redis-cli BGSAVE
        sleep 3
        
        REDIS_VOLUME=$(docker volume ls | grep redis-data | awk '{print $2}' | head -1)
        BACKUP_BASENAME=$(basename "$BACKUP_FILE")
        
        if [ -n "$REDIS_VOLUME" ]; then
            TEMP_FILE="$BACKUP_DIR/temp-backup.rdb"
            if docker run --rm -v "$REDIS_VOLUME":/data:ro -v "$BACKUP_DIR":/backup alpine sh -c 'cp /data/dump.rdb /backup/temp-backup.rdb 2>/dev/null && chmod 644 /backup/temp-backup.rdb'; then
                # Verify backup file has content before moving
                if [ -f "$TEMP_FILE" ] && [ -s "$TEMP_FILE" ]; then
                    BACKUP_SIZE=$(stat -c%s "$TEMP_FILE" 2>/dev/null || stat -f%z "$TEMP_FILE" 2>/dev/null || echo "0")
                    if [ "$BACKUP_SIZE" -gt 100 ]; then
                        mv "$TEMP_FILE" "$BACKUP_FILE" && echo "✅ Backup saved to: $BACKUP_FILE ($BACKUP_SIZE bytes)"
                    else
                        echo "⚠️  Backup file is too small ($BACKUP_SIZE bytes) - might be empty"
                        rm -f "$TEMP_FILE"
                        echo '⚠️  Trying redis-cli --rdb method...'
                        docker exec binance-bot-redis redis-cli --rdb /tmp/redis-backup.rdb 2>/dev/null || true
                        sleep 2
                        docker cp binance-bot-redis:/tmp/redis-backup.rdb "$BACKUP_FILE" 2>/dev/null && {
                            BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
                            echo "✅ Backup saved to: $BACKUP_FILE ($BACKUP_SIZE bytes)"
                        } || echo '⚠️  Backup failed'
                    fi
                else
                    echo '⚠️  Volume backup file is empty or missing'
                    rm -f "$TEMP_FILE"
                    echo '⚠️  Trying redis-cli --rdb method...'
                    docker exec binance-bot-redis redis-cli --rdb /tmp/redis-backup.rdb 2>/dev/null || true
                    sleep 2
                    docker cp binance-bot-redis:/tmp/redis-backup.rdb "$BACKUP_FILE" 2>/dev/null && {
                        BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
                        echo "✅ Backup saved to: $BACKUP_FILE ($BACKUP_SIZE bytes)"
                    } || echo '⚠️  Backup failed'
                fi
            else
                echo '⚠️  Volume backup failed, trying redis-cli --rdb method...'
                docker exec binance-bot-redis redis-cli --rdb /tmp/redis-backup.rdb 2>/dev/null || true
                sleep 2
                docker cp binance-bot-redis:/tmp/redis-backup.rdb "$BACKUP_FILE" 2>/dev/null && {
                    BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
                    echo "✅ Backup saved to: $BACKUP_FILE ($BACKUP_SIZE bytes)"
                } || echo '⚠️  Backup failed'
            fi
        else
            echo '⚠️  Redis volume not found, using redis-cli --rdb method...'
            docker exec binance-bot-redis redis-cli --rdb /tmp/redis-backup.rdb 2>/dev/null || true
            sleep 2
            docker cp binance-bot-redis:/tmp/redis-backup.rdb "$BACKUP_FILE" 2>/dev/null && {
                BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
                echo "✅ Backup saved to: $BACKUP_FILE ($BACKUP_SIZE bytes)"
            } || echo '⚠️  Backup failed'
        fi
        
        if [ -f "$BACKUP_FILE" ]; then
            BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
            echo "✅ Backup created successfully: $BACKUP_FILE ($BACKUP_SIZE)"
        else
            echo '⚠️  Warning: Backup file was not created'
        fi
    else
        echo '⚠️  Redis is empty - skipping backup'
    fi
else
    echo '⚠️  Redis container is not running - skipping backup'
fi

# Stop containers WITHOUT removing volumes (volumes persist data)
echo ''
echo '🛑 Stopping containers (volumes will be preserved)...'
docker-compose down --remove-orphans || true

# Pull latest images (for images from registry)
echo '📥 Pulling latest images from registry (if any)...'
docker-compose pull || true

# Rebuild and start services with latest code
echo '🔨 Rebuilding Docker image with latest code...'
echo '🚀 Starting services (will rebuild if needed)...'
docker-compose up -d --build

# Wait for PostgreSQL to be ready
echo ''
echo '⏳ Waiting for PostgreSQL to be ready...'
sleep 5

# Run database migrations
echo ''
echo '🔄 Running database migrations...'
if docker exec binance-bot-api alembic upgrade head 2>/dev/null; then
    echo '✅ Database migrations completed successfully'
else
    echo '⚠️  Warning: Database migrations failed or alembic not available in container'
    echo '   You may need to run migrations manually:'
    echo '   docker exec binance-bot-api alembic upgrade head'
fi

# Seed default roles (if needed)
echo ''
echo '🌱 Seeding default roles...'
if docker exec binance-bot-api python scripts/seed_default_roles.py 2>/dev/null; then
    echo '✅ Default roles seeded successfully'
else
    echo '⚠️  Warning: Role seeding failed or script not available'
    echo '   You may need to run manually:'
    echo '   docker exec binance-bot-api python scripts/seed_default_roles.py'
fi

# Verify Redis volume still exists
echo '✅ Verifying Redis volume after restart...'
docker volume ls | grep redis-data && echo '✅ Redis volume preserved' || echo '⚠️  Warning: Redis volume not found'

# Wait for Redis to start and check if data exists
echo ''
echo '⏳ Waiting for Redis to start...'
sleep 5

# Check if Redis has data
KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo '0')
echo "📊 Redis keys after restart: $KEY_COUNT"

# If Redis is empty, try to restore from backup
if [ "$KEY_COUNT" -eq "0" ]; then
    echo ''
    echo '⚠️  WARNING: Redis is empty after restart!'
    echo '🔍 Checking for backups to restore...'
    
    if [ -d "$BACKUP_DIR" ]; then
        LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/redis-backup-*.rdb 2>/dev/null | head -1)
        if [ -n "$LATEST_BACKUP" ] && [ -f "$LATEST_BACKUP" ]; then
            echo "📦 Found latest backup: $LATEST_BACKUP"
            echo "🔄 Attempting to restore from backup..."
            
            # Try simplified restore script first (more reliable)
            RESTORE_SUCCESS=false
            if [ -f "$DEPLOY_PATH/scripts/restore_redis_simple.sh" ]; then
                echo "   Using simplified restore script..."
                if bash "$DEPLOY_PATH/scripts/restore_redis_simple.sh" "$LATEST_BACKUP"; then
                    RESTORE_SUCCESS=true
                else
                    echo '⚠️  Simplified restore script failed, trying original script...'
                    if [ -f "$DEPLOY_PATH/scripts/restore_redis.sh" ]; then
                        if bash "$DEPLOY_PATH/scripts/restore_redis.sh" "$LATEST_BACKUP"; then
                            RESTORE_SUCCESS=true
                        else
                            echo '⚠️  Original restore script also failed, trying manual restore...'
                        fi
                    fi
                fi
            elif [ -f "$DEPLOY_PATH/scripts/restore_redis.sh" ]; then
                echo "   Using original restore script..."
                if bash "$DEPLOY_PATH/scripts/restore_redis.sh" "$LATEST_BACKUP"; then
                    RESTORE_SUCCESS=true
                else
                    echo '⚠️  Restore script failed, trying manual restore...'
                fi
            fi
            
            # If restore scripts failed or don't exist, try manual restore
            if [ "$RESTORE_SUCCESS" = false ]; then
                echo '⚠️  Attempting manual restore...'
                docker-compose stop redis
                sleep 2
                
                REDIS_VOLUME=$(docker volume ls | grep redis-data | awk '{print $2}' | head -1)
                if [ -n "$REDIS_VOLUME" ]; then
                    BACKUP_BASENAME=$(basename "$LATEST_BACKUP")
                    echo "📥 Copying backup and removing AOF files..."
                    docker run --rm -v "$REDIS_VOLUME":/data -v "$BACKUP_DIR":/backup:ro alpine sh -c "
                        cd /data
                        echo 'Removing ALL AOF files and directories...'
                        rm -rf appendonly.aof appendonlydir appendonly.aof.* *.aof
                        echo 'Removing old RDB...'
                        rm -f dump.rdb
                        echo 'Copying RDB backup...'
                        cp /backup/$BACKUP_BASENAME dump.rdb
                        chmod 644 dump.rdb
                        echo ''
                        echo 'Files in /data after restore:'
                        ls -lah /data
                        echo ''
                        echo 'RDB file size:'
                        ls -lh dump.rdb
                        echo ''
                        echo 'Verifying RDB is not empty:'
                        [ -s dump.rdb ] && echo '  ✅ RDB has content' || echo '  ❌ RDB is empty!'
                    "
                    echo '✅ Backup copied to Redis volume'
                    
                    # Start Redis with AOF disabled (RDB-only mode)
                    echo "🚀 Starting Redis with AOF disabled (RDB-only mode)..."
                    docker run -d --name redis-temp-restore \
                        -v "$REDIS_VOLUME":/data \
                        redis:7-alpine \
                        redis-server --appendonly no --dir /data --dbfilename dump.rdb 2>/dev/null || {
                        echo "   ⚠️  Could not start temp Redis, trying normal start..."
                        docker rm -f redis-temp-restore 2>/dev/null || true
                        docker-compose up -d redis
                        sleep 8
                        KEY_COUNT_AFTER=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo '0')
                        if [ "$KEY_COUNT_AFTER" -gt "0" ]; then
                            echo "✅ Redis restored! Keys: $KEY_COUNT_AFTER"
                        else
                            echo "⚠️  Restore completed but Redis still empty"
                            echo "   Check Redis logs: docker logs binance-bot-redis"
                            echo "   Verify redis.conf has 'appendonly no'"
                        fi
                    }
                    
                    # If temp Redis started, check if it loaded data
                    if docker ps | grep -q redis-temp-restore; then
                        sleep 5
                        KEY_COUNT_TEMP=$(docker exec redis-temp-restore redis-cli DBSIZE 2>/dev/null || echo '0')
                        echo "   📊 Keys loaded in temp Redis: $KEY_COUNT_TEMP"
                        
                        if [ "$KEY_COUNT_TEMP" -gt "0" ]; then
                            echo "   ✅ Data loaded successfully!"
                            # Save to RDB before stopping
                            echo "   💾 Saving data to RDB..."
                            docker exec redis-temp-restore redis-cli BGSAVE
                            sleep 3
                            
                            # Stop temp Redis
                            docker stop redis-temp-restore
                            docker rm redis-temp-restore
                            
                            # Remove AOF files before starting normal Redis (RDB-only mode)
                            # Even though redis.conf should have appendonly=no, remove AOF files to be safe
                            echo "🧹 Removing AOF files before starting normal Redis (RDB-only mode)..."
                            docker run --rm -v "$REDIS_VOLUME":/data alpine sh -c "
                                cd /data
                                rm -rf appendonly.aof appendonlydir appendonly.aof.* *.aof 2>/dev/null || true
                                echo 'Files in /data:'
                                ls -lah /data
                            "
                            
                            # Start normal Redis (will load from RDB, AOF disabled in redis.conf)
                            echo "🚀 Starting normal Redis container (RDB-only mode)..."
                            docker-compose up -d redis
                            sleep 8
                            
                            KEY_COUNT_AFTER=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo '0')
                            if [ "$KEY_COUNT_AFTER" -gt "0" ]; then
                                echo "✅ Redis restored! Keys: $KEY_COUNT_AFTER (RDB-only mode)"
                            else
                                echo "⚠️  Restore completed but Redis still empty"
                                echo "   Check Redis logs: docker logs binance-bot-redis | grep -i 'loading\|aof\|rdb'"
                                echo "   Verify redis.conf has 'appendonly no'"
                            fi
                        else
                            echo "   ❌ No keys loaded - backup might be empty or corrupted"
                            docker stop redis-temp-restore 2>/dev/null || true
                            docker rm redis-temp-restore 2>/dev/null || true
                            docker-compose up -d redis
                        fi
                    fi
                else
                    echo "⚠️  Redis volume not found"
                    docker-compose up -d redis
                fi
            fi
        else
            echo "⚠️  No backup files found in $BACKUP_DIR"
        fi
    else
        echo "⚠️  Backup directory not found: $BACKUP_DIR"
    fi
else
    echo '✅ Redis has data - no restore needed'
fi

docker-compose ps

echo ''
echo "✅ Deployment completed!"

