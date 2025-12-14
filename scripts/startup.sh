#!/bin/bash
# Startup script for Binance Bot API container
# Optionally runs database migrations before starting the API

set -e

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
until pg_isready -h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}" 2>/dev/null; do
    echo "   PostgreSQL is unavailable - sleeping..."
    sleep 2
done
echo "✅ PostgreSQL is ready"

# Optionally run migrations (set RUN_MIGRATIONS=true in .env to enable)
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "🔄 Running database migrations..."
    alembic upgrade head
    echo "✅ Migrations completed"
fi

# Start the API server
echo "🚀 Starting API server..."
exec uvicorn app.main:create_app --host 0.0.0.0 --port 8000 --factory

