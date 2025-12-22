#!/bin/bash
# Fix Nginx configuration to use Binance Bot API instead of default page

set -euo pipefail

echo "🔧 Fixing Nginx configuration..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Error: This script must be run as root (use sudo)"
    exit 1
fi

# Check if Nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "❌ Error: Nginx is not installed"
    exit 1
fi

NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
BINANCE_CONFIG="$NGINX_SITES_AVAILABLE/binance-bot"
DEFAULT_CONFIG="$NGINX_SITES_AVAILABLE/default"

echo "📋 Checking current Nginx configuration..."

# List enabled sites
echo "Currently enabled sites:"
ls -la "$NGINX_SITES_ENABLED" || echo "  (none)"

# Check if binance-bot config exists
if [ ! -f "$BINANCE_CONFIG" ]; then
    echo "❌ Error: Binance Bot config not found at $BINANCE_CONFIG"
    echo ""
    echo "Please copy the config file first:"
    echo "  sudo cp nginx/binance-bot.conf $BINANCE_CONFIG"
    exit 1
fi

echo "✅ Found Binance Bot config at $BINANCE_CONFIG"

# Disable default site if it exists
if [ -L "$NGINX_SITES_ENABLED/default" ]; then
    echo "🔒 Disabling default Nginx site..."
    rm -f "$NGINX_SITES_ENABLED/default"
    echo "✅ Default site disabled"
elif [ -f "$NGINX_SITES_ENABLED/default" ]; then
    echo "🔒 Removing default Nginx site..."
    rm -f "$NGINX_SITES_ENABLED/default"
    echo "✅ Default site removed"
fi

# Enable binance-bot site
if [ ! -L "$NGINX_SITES_ENABLED/binance-bot" ]; then
    echo "🔗 Creating symlink for Binance Bot config..."
    ln -s "$BINANCE_CONFIG" "$NGINX_SITES_ENABLED/binance-bot"
    echo "✅ Symlink created"
else
    echo "ℹ️  Symlink already exists"
fi

# Test Nginx configuration
echo "🧪 Testing Nginx configuration..."
if nginx -t; then
    echo "✅ Nginx configuration is valid"
else
    echo "❌ Error: Nginx configuration test failed"
    echo "Please check the error messages above"
    exit 1
fi

# Reload Nginx
echo "🔄 Reloading Nginx..."
if systemctl reload nginx; then
    echo "✅ Nginx reloaded successfully"
else
    echo "⚠️  Warning: Failed to reload Nginx, trying restart..."
    systemctl restart nginx
    echo "✅ Nginx restarted"
fi

# Verify Nginx is running
if systemctl is-active --quiet nginx; then
    echo "✅ Nginx is running"
else
    echo "⚠️  Warning: Nginx is not running. Starting it..."
    systemctl start nginx
    echo "✅ Nginx started"
fi

echo ""
echo "✅ Nginx configuration fixed!"
echo ""
echo "📋 Next steps:"
echo "   1. Test the API: curl http://95.216.216.26/health"
echo "   2. Check logs if needed: sudo tail -f /var/log/nginx/binance-bot-error.log"
echo ""
echo "🔍 Verify configuration:"
echo "   Enabled sites: ls -la $NGINX_SITES_ENABLED"

