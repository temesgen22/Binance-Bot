#!/bin/bash
# Script to fix migration issues where Alembic version is at head but tables don't exist
# This can happen if a migration was marked as applied but failed partway through

set -euo pipefail

echo "🔧 Fixing migration table mismatch..."

# Check if we're in Docker or local
if [ -f /.dockerenv ] || [ -n "${DOCKER_CONTAINER:-}" ]; then
    # Running inside Docker container
    ALEMBIC_CMD="alembic"
    DB_CHECK_CMD="psql -U postgres -d binance_bot -tAc"
else
    # Running locally, need to use docker exec
    ALEMBIC_CMD="docker exec -e ALEMBIC_MIGRATION=true binance-bot-api alembic"
    DB_CHECK_CMD="docker exec binance-bot-postgres psql -U postgres -d binance_bot -tAc"
fi

EXPECTED_HEAD="f1a2b3c4d5e6"

# Check current Alembic version
echo "📋 Checking current Alembic version..."
CURRENT_VERSION=$($ALEMBIC_CMD current 2>&1 | grep -oE '[a-f0-9]{12}' || echo "")
echo "   Current version: ${CURRENT_VERSION:-unknown}"

# Check if risk management tables exist
echo "🔍 Checking risk management tables..."
RISK_TABLES=$($DB_CHECK_CMD "
  SELECT COUNT(*) FROM information_schema.tables 
  WHERE table_schema = 'public' 
  AND table_name IN ('risk_management_config', 'risk_metrics', 'circuit_breaker_events');
" 2>/dev/null || echo "0")
echo "   Found $RISK_TABLES/3 risk management tables"

# Check database version directly
DB_VERSION=$($DB_CHECK_CMD "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null || echo "")
echo "   Database version: ${DB_VERSION:-unknown}"

if [ "$RISK_TABLES" = "3" ]; then
    echo "✅ All tables exist. No fix needed."
    exit 0
fi

if [ "$CURRENT_VERSION" = "$EXPECTED_HEAD" ] && [ "$RISK_TABLES" != "3" ]; then
    echo "⚠️  Mismatch detected: Version is at head but tables are missing"
    echo "   This indicates a previous migration failure"
    echo ""
    echo "🔧 Fixing by downgrading and re-running migration..."
    
    # Get the previous revision
    PREV_REV="a1b2c3d4e5f6"
    echo "   Step 1: Downgrading to previous revision: $PREV_REV"
    $ALEMBIC_CMD downgrade "$PREV_REV" || {
        echo "   ⚠️  Downgrade failed, trying downgrade -1..."
        $ALEMBIC_CMD downgrade -1 || {
            echo "   ❌ Downgrade failed. Manual intervention may be required."
            echo "   You may need to manually update alembic_version table:"
            echo "   UPDATE alembic_version SET version_num = '$PREV_REV';"
            exit 1
        }
    }
    
    echo "   Step 2: Re-running upgrade to head..."
    $ALEMBIC_CMD upgrade head || {
        echo "   ❌ Upgrade failed. Check logs for details."
        exit 1
    }
    
    # Verify tables were created
    echo "🔍 Verifying tables were created..."
    RISK_TABLES_AFTER=$($DB_CHECK_CMD "
      SELECT COUNT(*) FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_name IN ('risk_management_config', 'risk_metrics', 'circuit_breaker_events');
    " 2>/dev/null || echo "0")
    
    if [ "$RISK_TABLES_AFTER" = "3" ]; then
        echo "✅ All tables created successfully (3/3)"
        exit 0
    else
        echo "❌ Tables still missing ($RISK_TABLES_AFTER/3 found)"
        echo "   Manual intervention required. Check migration logs."
        exit 1
    fi
else
    echo "ℹ️  No mismatch detected or version is not at head"
    echo "   Current version: $CURRENT_VERSION"
    echo "   Expected head: $EXPECTED_HEAD"
    echo "   Tables found: $RISK_TABLES/3"
    echo ""
    echo "   If tables are missing, try running:"
    echo "   $ALEMBIC_CMD upgrade head"
    exit 0
fi

