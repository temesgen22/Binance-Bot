#!/bin/bash
# Generate a secure JWT secret key and update .env file

set -euo pipefail

ENV_FILE="${1:-.env}"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env file not found at $ENV_FILE"
    exit 1
fi

echo "🔐 Generating secure JWT secret key..."
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

if [ -z "$JWT_SECRET" ]; then
    echo "❌ Error: Failed to generate JWT secret"
    exit 1
fi

echo "✅ Generated JWT secret key: ${JWT_SECRET:0:20}..."

# Check if JWT_SECRET_KEY already exists in .env
if grep -q "^JWT_SECRET_KEY=" "$ENV_FILE"; then
    echo "⚠️  JWT_SECRET_KEY already exists in $ENV_FILE"
    echo "   Current value: $(grep "^JWT_SECRET_KEY=" "$ENV_FILE" | cut -d'=' -f2 | head -c 20)..."
    read -p "   Do you want to update it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "   Skipping update."
        exit 0
    fi
    # Update existing JWT_SECRET_KEY
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|" "$ENV_FILE"
    else
        # Linux
        sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|" "$ENV_FILE"
    fi
    echo "✅ Updated JWT_SECRET_KEY in $ENV_FILE"
else
    # Append JWT_SECRET_KEY to .env
    echo "" >> "$ENV_FILE"
    echo "# JWT Secret Key (auto-generated)" >> "$ENV_FILE"
    echo "JWT_SECRET_KEY=$JWT_SECRET" >> "$ENV_FILE"
    echo "✅ Added JWT_SECRET_KEY to $ENV_FILE"
fi

echo ""
echo "✅ JWT secret key has been set in $ENV_FILE"
echo "   Restart the application for changes to take effect."



