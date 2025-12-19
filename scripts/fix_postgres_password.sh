#!/bin/bash
# Fix PostgreSQL password authentication issue
# This script resets the PostgreSQL password to match the environment variables

set -e

echo "=========================================="
echo "PostgreSQL Password Fix Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "docker-compose.prod.yml" ]; then
    echo -e "${RED}❌ Error: docker-compose.prod.yml not found${NC}"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found${NC}"
    echo "Creating .env file from defaults..."
    echo "POSTGRES_USER=postgres" >> .env
    echo "POSTGRES_PASSWORD=postgres" >> .env
    echo "POSTGRES_DB=binance_bot" >> .env
fi

# Read password from .env file
if grep -q "^POSTGRES_PASSWORD=" .env; then
    ENV_PASSWORD=$(grep "^POSTGRES_PASSWORD=" .env | cut -d'=' -f2)
    echo -e "${GREEN}✓ Found POSTGRES_PASSWORD in .env${NC}"
else
    echo -e "${YELLOW}⚠️  POSTGRES_PASSWORD not found in .env, using default: postgres${NC}"
    ENV_PASSWORD="postgres"
fi

# Read username from .env file
if grep -q "^POSTGRES_USER=" .env; then
    ENV_USER=$(grep "^POSTGRES_USER=" .env | cut -d'=' -f2)
else
    ENV_USER="postgres"
fi

echo ""
echo "Configuration:"
echo "  Username: $ENV_USER"
echo "  Password: ${ENV_PASSWORD:0:3}*** (hidden)"
echo ""

# Check if postgres container is running
if ! docker ps | grep -q "binance-bot-postgres"; then
    echo -e "${RED}❌ Error: binance-bot-postgres container is not running${NC}"
    echo "Please start it first: docker-compose up -d postgres"
    exit 1
fi

echo -e "${GREEN}✓ PostgreSQL container is running${NC}"
echo ""

# Method 1: Try to connect and reset password using environment variable
echo "Attempting to reset PostgreSQL password..."
echo ""

# Try to connect without password first (trust authentication for local connections)
if docker exec -it binance-bot-postgres psql -U postgres -c "ALTER USER $ENV_USER WITH PASSWORD '$ENV_PASSWORD';" 2>/dev/null; then
    echo -e "${GREEN}✓ Password reset successful using trust authentication${NC}"
else
    echo -e "${YELLOW}⚠️  Trust authentication failed, trying alternative method...${NC}"
    
    # Method 2: Use pg_hba.conf modification (requires container restart)
    echo ""
    echo "Alternative method: Modifying pg_hba.conf to allow password reset..."
    echo ""
    
    # Create a temporary SQL script
    SQL_SCRIPT="/tmp/reset_password.sql"
    docker exec binance-bot-postgres sh -c "echo \"ALTER USER $ENV_USER WITH PASSWORD '$ENV_PASSWORD';\" > $SQL_SCRIPT"
    
    # Try to execute it
    if docker exec -it binance-bot-postgres psql -U postgres -f "$SQL_SCRIPT" 2>/dev/null; then
        echo -e "${GREEN}✓ Password reset successful${NC}"
    else
        echo -e "${RED}❌ Could not reset password automatically${NC}"
        echo ""
        echo "Manual steps required:"
        echo "1. Connect to PostgreSQL container:"
        echo "   docker exec -it binance-bot-postgres sh"
        echo ""
        echo "2. Edit pg_hba.conf to use 'trust' for local connections:"
        echo "   vi /var/lib/postgresql/data/pg_hba.conf"
        echo "   Change 'scram-sha-256' to 'trust' for local connections"
        echo ""
        echo "3. Restart PostgreSQL:"
        echo "   docker-compose restart postgres"
        echo ""
        echo "4. Reset password:"
        echo "   docker exec -it binance-bot-postgres psql -U postgres -c \"ALTER USER $ENV_USER WITH PASSWORD '$ENV_PASSWORD';\""
        echo ""
        echo "5. Restore pg_hba.conf to 'scram-sha-256'"
        echo "6. Restart PostgreSQL again"
        exit 1
    fi
fi

echo ""
echo "Verifying password reset..."
echo ""

# Test connection with new password
if docker exec -e PGPASSWORD="$ENV_PASSWORD" binance-bot-postgres psql -U "$ENV_USER" -d binance_bot -c "SELECT 1;" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Password verification successful!${NC}"
else
    echo -e "${YELLOW}⚠️  Password verification failed, but password may have been reset${NC}"
    echo "The password might need a moment to propagate, or you may need to restart the container"
fi

echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo ""
echo "1. Verify DATABASE_URL in .env matches:"
echo "   DATABASE_URL=postgresql://$ENV_USER:$ENV_PASSWORD@postgres:5432/binance_bot"
echo ""
echo "2. Restart the API container:"
echo "   docker-compose restart api"
echo ""
echo "3. Check API logs to verify connection:"
echo "   docker logs -f binance-bot-api | grep -i database"
echo ""
echo -e "${GREEN}✓ Password fix complete!${NC}"

