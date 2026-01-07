#!/bin/bash
# Script to verify database migrations and create missing tables if needed
# This is useful for ensuring all migrations have been applied correctly

set -euo pipefail

echo "🔍 Verifying database migrations..."

# Check if we're in Docker or local
if [ -f /.dockerenv ] || [ -n "${DOCKER_CONTAINER:-}" ]; then
    # Running inside Docker container
    DB_CHECK_CMD="psql -U postgres -d binance_bot -tAc"
else
    # Running locally, need to use docker exec
    DB_CHECK_CMD="docker exec binance-bot-postgres psql -U postgres -d binance_bot -tAc"
fi

# List of critical tables that should exist after migrations
CRITICAL_TABLES=(
    "risk_management_config"
    "risk_metrics"
    "circuit_breaker_events"
)

echo "📋 Checking critical tables..."
MISSING_TABLES=()

for table in "${CRITICAL_TABLES[@]}"; do
    if $DB_CHECK_CMD "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '$table';" 2>/dev/null | grep -q "1"; then
        echo "  ✅ $table exists"
    else
        echo "  ❌ $table MISSING"
        MISSING_TABLES+=("$table")
    fi
done

if [ ${#MISSING_TABLES[@]} -eq 0 ]; then
    echo "✅ All critical tables verified"
    exit 0
else
    echo "⚠️  Missing tables detected: ${MISSING_TABLES[*]}"
    echo "🔄 Attempting to run migrations..."
    
    # Run migrations
    if [ -f /.dockerenv ] || [ -n "${DOCKER_CONTAINER:-}" ]; then
        alembic upgrade head
    else
        docker exec -e ALEMBIC_MIGRATION=true binance-bot-api alembic upgrade head
    fi
    
    # Verify again
    echo "🔍 Re-verifying after migration..."
    STILL_MISSING=()
    for table in "${MISSING_TABLES[@]}"; do
        if $DB_CHECK_CMD "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '$table';" 2>/dev/null | grep -q "1"; then
            echo "  ✅ $table now exists"
        else
            echo "  ❌ $table still MISSING"
            STILL_MISSING+=("$table")
        fi
    done
    
    if [ ${#STILL_MISSING[@]} -eq 0 ]; then
        echo "✅ All tables created successfully"
        exit 0
    else
        echo "❌ Some tables are still missing: ${STILL_MISSING[*]}"
        echo "   Please check migration logs and database connection"
        exit 1
    fi
fi

