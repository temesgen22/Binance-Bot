#!/bin/bash
# Script to check database connection from within the API container
# Usage: docker exec binance-bot-api bash scripts/check_database_connection.sh

set -e

echo "🔍 Checking database connection..."
echo ""

# Check if we're in a container
if [ ! -f /.dockerenv ]; then
    echo "⚠️  Warning: This script is designed to run inside a Docker container"
fi

# Check environment variables
echo "📋 Environment Variables:"
echo "   DATABASE_URL: ${DATABASE_URL:-NOT SET}"
echo ""

# Try to connect to database using Python
echo "🔌 Testing database connection..."
python3 << 'EOF'
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

database_url = os.getenv("DATABASE_URL", "")
if not database_url:
    print("❌ DATABASE_URL environment variable is not set")
    sys.exit(1)

print(f"   Connecting to: {database_url.split('@')[-1] if '@' in database_url else '***'}")

try:
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print(f"✅ Database connection successful!")
        print(f"   PostgreSQL version: {version[:50]}...")
        
        # Check if database exists
        result = conn.execute(text("SELECT current_database()"))
        db_name = result.fetchone()[0]
        print(f"   Current database: {db_name}")
        
        # Check if tables exist
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]
        print(f"   Tables found: {len(tables)}")
        if tables:
            print(f"   Sample tables: {', '.join(tables[:5])}")
        else:
            print("   ⚠️  No tables found - migrations may not have run")
            
except OperationalError as e:
    print(f"❌ Database connection failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
EOF

echo ""
echo "✅ Database connection check completed"

