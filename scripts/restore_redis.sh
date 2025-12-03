#!/bin/bash
# Restore Redis data from backup after deployment
# Usage: ./restore_redis.sh [backup-file.rdb]

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
    echo "Example: $0 $BACKUP_DIR/redis-backup-20251128-120000.rdb"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔄 Restoring Redis from backup: $BACKUP_FILE"

# Check if Redis container is running
if ! docker ps | grep -q binance-bot-redis; then
    echo "⚠️  Redis container is not running. Starting it..."
    docker-compose up -d redis
    sleep 3
fi

# Stop Redis to restore data safely
echo "🛑 Stopping Redis container..."
docker-compose stop redis

# Find the correct Redis volume name
echo "🔍 Finding Redis volume..."
REDIS_VOLUME=$(docker volume ls | grep redis-data | awk '{print $2}' | head -1)

if [ -z "$REDIS_VOLUME" ]; then
    echo "❌ Error: Redis volume not found!"
    echo "   Available volumes:"
    docker volume ls | sed 's/^/      /'
    exit 1
fi

echo "   ✅ Found volume: $REDIS_VOLUME"

# Copy backup file into container's data directory
echo "📥 Copying backup file to Redis data directory..."
echo "   Removing ALL AOF files and directories (critical for RDB-only restore)..."
docker run --rm \
    -v "$REDIS_VOLUME":/data \
    -v "$(dirname "$BACKUP_FILE")":/backup:ro \
    alpine sh -c "
        cd /data
        echo 'Removing all AOF-related files...'
        # Remove ALL AOF files and directories (Redis will recreate if needed)
        rm -rf appendonly.aof appendonlydir appendonly.aof.* *.aof
        # Remove old RDB
        rm -f dump.rdb
        echo 'Copying RDB backup...'
        # Copy new RDB backup
        cp /backup/$(basename "$BACKUP_FILE") dump.rdb
        # Set correct permissions (Redis runs as user 999)
        chmod 644 dump.rdb
        echo ''
        echo 'Files in /data after restore:'
        ls -lah /data
        echo ''
        echo 'RDB file details:'
        ls -lh dump.rdb
        echo ''
        echo 'Verifying RDB file is not empty:'
        [ -s dump.rdb ] && echo '  ✅ RDB file has content' || echo '  ❌ RDB file is empty!'
    "

# Start Redis with AOF disabled to force RDB load
echo "🚀 Starting Redis with AOF disabled (to force RDB load)..."
echo "   Using temporary config with appendonly=no"

# Create a temporary Redis container with AOF disabled
docker run -d --name redis-temp-restore \
    -v "$REDIS_VOLUME":/data \
    redis:7-alpine \
    redis-server --appendonly no --dir /data --dbfilename dump.rdb 2>/dev/null || {
    echo "   ⚠️  Could not start temp Redis"
    docker rm -f redis-temp-restore 2>/dev/null || true
    echo "   Trying normal Redis start instead..."
    docker-compose start redis
    sleep 8
    KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
    if [ "$KEY_COUNT" -gt 0 ]; then
        echo "   ✅ Keys loaded: $KEY_COUNT"
    else
        echo "   ❌ No keys loaded"
    fi
    exit 0
}

# Wait for Redis to start and load RDB
echo "⏳ Waiting for Redis to load RDB file..."
sleep 8

# Check if temp Redis loaded data
if docker ps | grep -q redis-temp-restore; then
    KEY_COUNT=$(docker exec redis-temp-restore redis-cli DBSIZE 2>/dev/null || echo "0")
    echo "   📊 Keys loaded in temp Redis: $KEY_COUNT"
    
    if [ "$KEY_COUNT" -gt 0 ]; then
        echo "   ✅ Data loaded successfully!"
        echo ""
        echo "   Sample keys:"
        docker exec redis-temp-restore redis-cli --scan --pattern "*" | head -10 | sed 's/^/      /'
        
        # Save the data to RDB before stopping (so normal Redis can load it)
        echo ""
        echo "💾 Saving data to RDB for normal Redis..."
        docker exec redis-temp-restore redis-cli BGSAVE
        
        # Wait for BGSAVE to complete
        echo "⏳ Waiting for BGSAVE to complete..."
        while [ "$(docker exec redis-temp-restore redis-cli LASTSAVE)" = "$(docker exec redis-temp-restore redis-cli LASTSAVE)" ]; do
            sleep 1
        done
        
        # Check if save is in progress
        SAVE_IN_PROGRESS=$(docker exec redis-temp-restore redis-cli INFO persistence | grep -o "rdb_bgsave_in_progress:1" || echo "")
        while [ -n "$SAVE_IN_PROGRESS" ]; do
            echo "   Still saving... waiting..."
            sleep 1
            SAVE_IN_PROGRESS=$(docker exec redis-temp-restore redis-cli INFO persistence | grep -o "rdb_bgsave_in_progress:1" || echo "")
        done
        
        echo "✅ BGSAVE completed"
        sleep 2
        
        # Stop temp Redis
        echo "🛑 Stopping temp Redis..."
        docker stop redis-temp-restore
        docker rm redis-temp-restore
        
        # CRITICAL: Remove AOF files again before starting normal Redis
        # Normal Redis has appendonly=yes in redis.conf, so if AOF files exist,
        # Redis will load from empty AOF instead of the RDB we just saved
        echo "🧹 Removing AOF files before starting normal Redis (to force RDB load)..."
        docker run --rm -v "$REDIS_VOLUME":/data alpine sh -c "
            cd /data
            echo 'Removing all AOF files to force RDB load...'
            rm -rf appendonly.aof appendonlydir appendonly.aof.* *.aof 2>/dev/null || true
            echo 'Verifying RDB file exists and has content:'
            ls -lh dump.rdb
            [ -s dump.rdb ] && echo '  ✅ RDB file has content' || echo '  ❌ RDB file is empty!'
        "
        
        # CRITICAL FIX: Start normal Redis with AOF DISABLED via command override
        # This forces Redis to load from RDB instead of creating a new empty AOF
        echo "🚀 Starting normal Redis with AOF disabled (to force RDB load)..."
        
        # Find deploy directory (where docker-compose.yml and redis.conf are)
        DEPLOY_DIR="$DEPLOY_PATH"
        if [ ! -d "$DEPLOY_DIR" ] || [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
            DEPLOY_DIR="$(dirname "$0")/.."
            DEPLOY_DIR="$(cd "$DEPLOY_DIR" 2>/dev/null && pwd || echo "$DEPLOY_DIR")"
        fi
        if [ ! -d "$DEPLOY_DIR" ] || [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
            DEPLOY_DIR="/home/jenkins-deploy/binance-bot"
        fi
        if [ ! -d "$DEPLOY_DIR" ] || [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
            # Last resort: find it from current directory
            DEPLOY_DIR="$(pwd)"
        fi
        
        echo "   📁 Using deploy directory: $DEPLOY_DIR"
        
        # Change to deploy directory
        cd "$DEPLOY_DIR" 2>/dev/null || {
            echo "   ⚠️  Cannot cd to $DEPLOY_DIR, continuing from current directory"
        }
        
        # Stop any existing Redis
        docker-compose stop redis 2>/dev/null || true
        docker rm -f binance-bot-redis binance-bot-redis-load 2>/dev/null || true
        
        # Get Redis volume
        REDIS_VOLUME=$(docker volume ls | grep redis-data | awk '{print $2}' | head -1)
        
        if [ -n "$REDIS_VOLUME" ]; then
            # Start Redis with AOF disabled via command override
            # This will load from RDB, then we'll restart with normal config
            echo "   Starting Redis with AOF disabled to load RDB..."
            docker run -d --name binance-bot-redis-load \
                -v "$REDIS_VOLUME":/data \
                -p 6379:6379 \
                redis:7-alpine \
                redis-server --appendonly no --dir /data --dbfilename dump.rdb 2>/dev/null || {
                echo "   ⚠️  Could not start Redis with override"
                docker rm -f binance-bot-redis-load 2>/dev/null || true
                docker-compose up -d redis
                sleep 8
                exit 1
            }
            
            # Check if data loaded
            sleep 5
            KEY_COUNT_LOAD=$(docker exec binance-bot-redis-load redis-cli DBSIZE 2>/dev/null || echo "0")
            echo "   📊 Keys loaded with AOF disabled: $KEY_COUNT_LOAD"
            
            if [ "$KEY_COUNT_LOAD" -gt "0" ]; then
                echo "   ✅ RDB loaded successfully!"
                echo "   🔄 Now restarting with normal Redis config..."
                
                # Stop the load container
                docker stop binance-bot-redis-load
                docker rm binance-bot-redis-load
                
                # CRITICAL: Remove AOF files and start Redis with AOF disabled via docker-compose override
                echo "   🧹 Removing AOF files and starting Redis with AOF disabled..."
                docker run --rm -v "$REDIS_VOLUME":/data alpine sh -c "
                    cd /data
                    rm -rf appendonly.aof appendonlydir appendonly.aof.* *.aof 2>/dev/null || true
                    echo 'Files in /data before starting:'
                    ls -lah /data
                "
                
                # Start Redis using docker-compose but override command to disable AOF
                # This ensures it loads from RDB first
                REDIS_CONF=""
                # Try to find redis.conf in multiple locations
                for test_path in "$DEPLOY_DIR/redis.conf" "$(pwd)/redis.conf" "./redis.conf" "/home/jenkins-deploy/binance-bot/redis.conf"; do
                    if [ -f "$test_path" ]; then
                        REDIS_CONF="$test_path"
                        echo "   ✅ Found redis.conf at: $REDIS_CONF"
                        break
                    fi
                done
                
                if [ -n "$REDIS_CONF" ]; then
                    echo "   🔧 Temporarily disabling AOF in redis.conf..."
                    REDIS_CONF_DIR="$(dirname "$REDIS_CONF")"
                    # Backup original config
                    cp "$REDIS_CONF" "$REDIS_CONF_DIR/redis.conf.backup"
                    # Temporarily disable AOF
                    sed -i 's/^appendonly yes/appendonly no/' "$REDIS_CONF" 2>/dev/null || \
                    sed -i 's/appendonly yes/appendonly no/' "$REDIS_CONF" 2>/dev/null || true
                    
                    # Start Redis with AOF disabled (will load from RDB)
                    docker-compose up -d redis
                    sleep 8
                    
                    # Verify data loaded
                    KEY_COUNT_TEMP=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
                    echo "   📊 Keys after starting with AOF disabled: $KEY_COUNT_TEMP"
                    
                    if [ "$KEY_COUNT_TEMP" -gt "0" ]; then
                        echo "   ✅ Data loaded from RDB!"
                        # Restore original config
                        mv "$REDIS_CONF_DIR/redis.conf.backup" "$REDIS_CONF"
                        # CRITICAL: Remove any AOF files that might have been created
                        # before restarting with AOF enabled
                        echo "   🧹 Removing any AOF files before re-enabling AOF..."
                        docker run --rm -v "$REDIS_VOLUME":/data alpine sh -c "
                            cd /data
                            rm -rf appendonly.aof appendonlydir appendonly.aof.* *.aof 2>/dev/null || true
                            echo 'Files in /data before restart:'
                            ls -lah /data
                        "
                        # Restart Redis with AOF enabled (data is already in RDB, so it will persist)
                        echo "   🔄 Re-enabling AOF and restarting..."
                        docker-compose restart redis
                        sleep 8
                        
                        # Final verification
                        KEY_COUNT_FINAL=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
                        echo "   📊 Final key count after enabling AOF: $KEY_COUNT_FINAL"
                        
                        if [ "$KEY_COUNT_FINAL" -gt "0" ]; then
                            echo "   ✅ Data successfully restored and persisted with AOF enabled!"
                        else
                            echo "   ⚠️  Data lost after enabling AOF"
                            echo "   This is unexpected - data should persist in RDB"
                        fi
                    else
                        echo "   ⚠️  Data not loaded, restoring original config"
                        mv "$REDIS_CONF_DIR/redis.conf.backup" "$REDIS_CONF"
                    fi
                else
                    echo "   ⚠️  redis.conf not found in any expected location"
                    echo "   Searched: $DEPLOY_DIR/redis.conf, $(pwd)/redis.conf, ./redis.conf"
                    echo "   Using alternative method: starting Redis with command override..."
                    
                    # Alternative: Start Redis with command override directly
                    # Get the redis.conf path from docker-compose (it's mounted)
                    # We'll start Redis manually with AOF disabled
                    docker stop binance-bot-redis 2>/dev/null || true
                    docker rm binance-bot-redis 2>/dev/null || true
                    
                    # Start Redis with AOF disabled using the same volume and config mount as docker-compose
                    # Find redis.conf location from docker-compose
                    REDIS_CONF_MOUNT=$(docker-compose config 2>/dev/null | grep -A 5 "redis:" | grep "redis.conf" | awk '{print $2}' | cut -d: -f1 | head -1)
                    if [ -z "$REDIS_CONF_MOUNT" ] || [ ! -f "$REDIS_CONF_MOUNT" ]; then
                        # Try common locations
                        for test_path in "$DEPLOY_DIR/redis.conf" "$(pwd)/redis.conf" "./redis.conf"; do
                            if [ -f "$test_path" ]; then
                                REDIS_CONF_MOUNT="$test_path"
                                break
                            fi
                        done
                    fi
                    
                    if [ -n "$REDIS_CONF_MOUNT" ] && [ -f "$REDIS_CONF_MOUNT" ]; then
                        echo "   Using redis.conf at: $REDIS_CONF_MOUNT"
                        # Start with AOF disabled
                        docker run -d --name binance-bot-redis \
                            -v "$REDIS_VOLUME":/data \
                            -v "$REDIS_CONF_MOUNT":/usr/local/etc/redis/redis.conf:ro \
                            -p 6379:6379 \
                            redis:7-alpine \
                            redis-server /usr/local/etc/redis/redis.conf --appendonly no
                        sleep 8
                        
                        KEY_COUNT_TEMP=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
                        echo "   📊 Keys with AOF disabled: $KEY_COUNT_TEMP"
                        
                        if [ "$KEY_COUNT_TEMP" -gt "0" ]; then
                            echo "   ✅ Data loaded! Now restarting with docker-compose..."
                            docker stop binance-bot-redis
                            docker rm binance-bot-redis
                            docker-compose up -d redis
                            sleep 8
                            KEY_COUNT_FINAL=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
                            echo "   📊 Final key count: $KEY_COUNT_FINAL"
                        else
                            echo "   ⚠️  Data not loaded"
                            docker stop binance-bot-redis 2>/dev/null || true
                            docker rm binance-bot-redis 2>/dev/null || true
                            docker-compose up -d redis
                        fi
                    else
                        echo "   ⚠️  Cannot find redis.conf, starting Redis normally (may not work)"
                        docker-compose up -d redis
                        sleep 8
                    fi
                fi
            else
                echo "   ⚠️  No keys loaded even with AOF disabled"
                docker stop binance-bot-redis-load 2>/dev/null || true
                docker rm binance-bot-redis-load 2>/dev/null || true
                docker-compose up -d redis
            fi
        else
            echo "   ⚠️  Redis volume not found"
            docker-compose up -d redis
            sleep 8
        fi
        
        # Verify normal Redis has the data
        KEY_COUNT_FINAL=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
        echo "   📊 Final key count in normal Redis: $KEY_COUNT_FINAL"
        
        if [ "$KEY_COUNT_FINAL" -gt 0 ]; then
            echo "   ✅ Data successfully restored to normal Redis!"
            echo ""
            echo "   Sample keys:"
            docker exec binance-bot-redis redis-cli --scan --pattern "*" | head -10 | sed 's/^/      /'
        else
            echo "   ⚠️  Keys lost when starting normal Redis"
            echo "   This might be because AOF is enabled and Redis is loading from empty AOF"
            echo "   Try running the restore again or check Redis logs"
        fi
    else
        echo "   ❌ No keys loaded - backup file might be empty or corrupted"
        echo ""
        echo "   Checking backup file..."
        BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "0")
        echo "   Backup file size: $BACKUP_SIZE bytes"
        
        docker stop redis-temp-restore
        docker rm redis-temp-restore
    fi
else
    echo "   ⚠️  Temp Redis didn't start properly"
    docker rm -f redis-temp-restore 2>/dev/null || true
    echo "   Starting normal Redis..."
    docker-compose start redis
fi

# Give Redis time to load the RDB file
echo "⏳ Waiting for Redis to load RDB file..."
sleep 8

# Check Redis logs for loading messages
echo ""
echo "📋 Checking Redis startup logs..."
echo "   Looking for RDB loading messages..."
docker logs --tail 30 binance-bot-redis 2>&1 | grep -E "(Loading|DB loaded|Ready to accept|Error|Fatal|RDB)" | sed 's/^/   /' || echo "   No loading messages found"

# Check if Redis is responding
echo ""
echo "🧪 Testing Redis connection..."
if docker exec binance-bot-redis redis-cli ping 2>/dev/null | grep -q PONG; then
    echo "   ✅ Redis is responding"
else
    echo "   ❌ Redis is not responding"
    echo "   Check logs: docker logs binance-bot-redis"
fi

# Verify data was restored
echo "✅ Verifying restored data..."
KEY_COUNT=$(docker exec binance-bot-redis redis-cli DBSIZE 2>/dev/null || echo "0")
echo "   Total keys restored: $KEY_COUNT"

if [ "$KEY_COUNT" -gt 0 ]; then
    echo "✅ Redis data restored successfully!"
    echo ""
    echo "🔑 Sample restored keys:"
    docker exec binance-bot-redis redis-cli --scan --pattern "*" | head -10
else
    echo "⚠️  Warning: No keys found after restore"
    echo "   The backup file might be empty or corrupted"
fi

