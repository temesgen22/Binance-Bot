#!/bin/bash
# Script to update production .env file with secure JWT_SECRET_KEY
# Usage: ./scripts/update_production_env.sh [SSH_HOST] [SSH_USER] [DEPLOY_PATH]

set -euo pipefail

SSH_HOST="${1:-${DEPLOY_SSH_HOST:-}}"
SSH_USER="${2:-${DEPLOY_SSH_USER:-jenkins-deploy}}"
DEPLOY_PATH="${3:-${DEPLOY_PATH:-~/binance-bot}}"
SSH_KEY="${SSH_KEY:-}"

if [ -z "$SSH_HOST" ]; then
    echo "❌ Error: SSH_HOST not provided"
    echo "Usage: $0 [SSH_HOST] [SSH_USER] [DEPLOY_PATH]"
    echo "   Or set: DEPLOY_SSH_HOST, DEPLOY_SSH_USER, DEPLOY_PATH"
    exit 1
fi

if [ -z "$SSH_KEY" ]; then
    echo "⚠️  Warning: SSH_KEY not set. Using default SSH key."
fi

echo "🔐 Generating secure JWT secret key..."
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

if [ -z "$JWT_SECRET" ]; then
    echo "❌ Error: Failed to generate JWT secret"
    exit 1
fi

echo "📝 Updating .env file on $SSH_USER@$SSH_HOST:$DEPLOY_PATH/.env"

# SSH command to update .env file
if [ -n "$SSH_KEY" ]; then
    SSH_CMD="ssh -i \"$SSH_KEY\" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
else
    SSH_CMD="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
fi

$SSH_CMD "$SSH_USER@$SSH_HOST" bash <<EOF
set -euo pipefail

ENV_FILE="$DEPLOY_PATH/.env"

if [ ! -f "\$ENV_FILE" ]; then
    echo "❌ Error: .env file not found at \$ENV_FILE"
    exit 1
fi

# Backup .env file
ENV_BACKUP="\${ENV_FILE}.backup.\$(date +%s)"
cp "\$ENV_FILE" "\$ENV_BACKUP"
echo "💾 Backed up .env to \$ENV_BACKUP"

# Update or add JWT_SECRET_KEY
if grep -q "^JWT_SECRET_KEY=" "\$ENV_FILE"; then
    # Update existing
    sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|" "\$ENV_FILE"
    echo "✅ Updated JWT_SECRET_KEY in \$ENV_FILE"
else
    # Append new
    echo "" >> "\$ENV_FILE"
    echo "# JWT Secret Key (auto-generated)" >> "\$ENV_FILE"
    echo "JWT_SECRET_KEY=$JWT_SECRET" >> "\$ENV_FILE"
    echo "✅ Added JWT_SECRET_KEY to \$ENV_FILE"
fi

echo ""
echo "✅ JWT secret key has been updated"
echo "   Restart the application: docker compose -f docker-compose.prod.yml restart api"
EOF

echo ""
echo "✅ Production .env file updated successfully!"
echo "   The application will need to be restarted for changes to take effect."



