#!/bin/bash
# Health Check Script for Binance Bot
# Usage: ./scripts/health_check.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  Binance Bot Health Check"
echo "=========================================="
echo ""

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
    fi
}

# 1. Check Database (PostgreSQL)
echo "1. Database (PostgreSQL):"
if command -v pg_isready > /dev/null 2>&1; then
    if pg_isready -h localhost -U postgres -d binance_bot > /dev/null 2>&1; then
        print_status 0 "Database is accepting connections"
        
        # Get database info
        DB_INFO=$(psql -h localhost -U postgres -d binance_bot -t -c "SELECT version();" 2>/dev/null | head -1)
        if [ ! -z "$DB_INFO" ]; then
            echo "   Version: $(echo $DB_INFO | cut -d' ' -f1-3)"
        fi
        
        # Get connection count
        CONN_COUNT=$(psql -h localhost -U postgres -d binance_bot -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d ' ')
        echo "   Active connections: $CONN_COUNT"
    else
        print_status 1 "Database is not responding"
    fi
else
    echo -e "${YELLOW}⚠${NC} pg_isready not found. Install PostgreSQL client tools."
fi
echo ""

# 2. Check Redis
echo "2. Redis:"
if command -v redis-cli > /dev/null 2>&1; then
    if redis-cli ping > /dev/null 2>&1; then
        print_status 0 "Redis is responding"
        
        # Get Redis version
        REDIS_VERSION=$(redis-cli info server 2>/dev/null | grep "redis_version" | cut -d: -f2 | tr -d '\r')
        if [ ! -z "$REDIS_VERSION" ]; then
            echo "   Version: $REDIS_VERSION"
        fi
        
        # Get memory usage
        MEMORY_USED=$(redis-cli info memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
        if [ ! -z "$MEMORY_USED" ]; then
            echo "   Memory used: $MEMORY_USED"
        fi
        
        # Count application keys
        KEY_COUNT=$(redis-cli keys "binance_bot:*" 2>/dev/null | wc -l)
        echo "   Application keys: $KEY_COUNT"
    else
        print_status 1 "Redis is not responding"
    fi
else
    echo -e "${YELLOW}⚠${NC} redis-cli not found. Install Redis client tools."
fi
echo ""

# 3. Check Application API
echo "3. Application API:"
if command -v curl > /dev/null 2>&1; then
    # Quick health check
    if curl -s -f http://localhost:8000/health/quick > /dev/null 2>&1; then
        print_status 0 "Application is running"
        
        # Detailed health check
        echo "   Fetching detailed health status..."
        HEALTH_JSON=$(curl -s http://localhost:8000/health/detailed 2>/dev/null)
        
        if [ ! -z "$HEALTH_JSON" ]; then
            # Parse status
            STATUS=$(echo "$HEALTH_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "unknown")
            echo "   Overall status: $STATUS"
            
            # Parse service statuses
            if command -v python3 > /dev/null 2>&1; then
                echo "$HEALTH_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    services = data.get('services', {})
    for service, info in services.items():
        status = info.get('status', 'unknown')
        response_time = info.get('response_time_ms')
        if response_time:
            print(f'   {service.capitalize()}: {status} ({response_time}ms)')
        else:
            print(f'   {service.capitalize()}: {status}')
except:
    pass
" 2>/dev/null || true
            fi
        fi
    else
        print_status 1 "Application is not responding on port 8000"
    fi
else
    echo -e "${YELLOW}⚠${NC} curl not found. Install curl."
fi
echo ""

# 4. Check Binance API (optional)
echo "4. Binance API (Direct):"
if command -v curl > /dev/null 2>&1; then
    BINANCE_PING=$(curl -s -o /dev/null -w "%{http_code}" "https://testnet.binance.vision/api/v3/ping" 2>/dev/null || echo "000")
    if [ "$BINANCE_PING" = "200" ]; then
        print_status 0 "Binance testnet API is reachable"
    else
        print_status 1 "Binance testnet API is not reachable (HTTP $BINANCE_PING)"
    fi
else
    echo -e "${YELLOW}⚠${NC} curl not found. Install curl."
fi
echo ""

# 5. Check Application Logs (recent errors)
echo "5. Recent Log Errors:"
if [ -f "logs/bot.log" ]; then
    ERROR_COUNT=$(tail -n 1000 logs/bot.log 2>/dev/null | grep -i "ERROR\|CRITICAL" | wc -l)
    if [ "$ERROR_COUNT" -eq 0 ]; then
        echo -e "${GREEN}✓${NC} No errors in last 1000 log lines"
    else
        echo -e "${YELLOW}⚠${NC} Found $ERROR_COUNT errors in last 1000 log lines"
        echo "   Recent errors:"
        tail -n 1000 logs/bot.log 2>/dev/null | grep -i "ERROR\|CRITICAL" | tail -n 3 | sed 's/^/   /'
    fi
else
    echo -e "${YELLOW}⚠${NC} Log file not found: logs/bot.log"
fi
echo ""

# Summary
echo "=========================================="
echo "  Health Check Complete"
echo "=========================================="

