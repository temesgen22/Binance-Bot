#!/bin/bash
# Setup Nginx reverse proxy for Binance Bot API
# This script configures Nginx to proxy requests from port 80 to the Docker container on port 8000

set -euo pipefail

NGINX_CONFIG_SOURCE="nginx/binance-bot.conf"
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available/binance-bot"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled/binance-bot"
NGINX_LOG_DIR="/var/log/nginx"

echo "🔧 Setting up Nginx reverse proxy for Binance Bot API..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Error: This script must be run as root (use sudo)"
    exit 1
fi

# Check if Nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "❌ Error: Nginx is not installed"
    echo "   Install it with: sudo apt-get update && sudo apt-get install -y nginx"
    exit 1
fi

# Check if config file exists
if [ ! -f "$NGINX_CONFIG_SOURCE" ]; then
    echo "❌ Error: Nginx config file not found at $NGINX_CONFIG_SOURCE"
    echo "   Make sure you're running this from the project root directory"
    exit 1
fi

# Create log directory if it doesn't exist
if [ ! -d "$NGINX_LOG_DIR" ]; then
    mkdir -p "$NGINX_LOG_DIR"
    echo "✅ Created log directory: $NGINX_LOG_DIR"
fi

# Copy config file
echo "📝 Copying Nginx configuration..."
cp "$NGINX_CONFIG_SOURCE" "$NGINX_SITES_AVAILABLE"
echo "✅ Configuration copied to $NGINX_SITES_AVAILABLE"

# Create symlink if it doesn't exist
if [ ! -L "$NGINX_SITES_ENABLED" ]; then
    ln -s "$NGINX_SITES_AVAILABLE" "$NGINX_SITES_ENABLED"
    echo "✅ Created symlink: $NGINX_SITES_ENABLED -> $NGINX_SITES_AVAILABLE"
else
    echo "ℹ️  Symlink already exists: $NGINX_SITES_ENABLED"
fi

# Test Nginx configuration
echo "🧪 Testing Nginx configuration..."
if nginx -t; then
    echo "✅ Nginx configuration is valid"
else
    echo "❌ Error: Nginx configuration test failed"
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

# Check if Nginx is running
if systemctl is-active --quiet nginx; then
    echo "✅ Nginx is running"
else
    echo "⚠️  Warning: Nginx is not running. Starting it..."
    systemctl start nginx
    echo "✅ Nginx started"
fi

# Enable Nginx to start on boot
systemctl enable nginx

echo ""
echo "✅ Nginx reverse proxy setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Update docker-compose.prod.yml to remove port 8000 from public exposure"
echo "   2. Restart your Docker containers: docker compose -f docker-compose.prod.yml restart api"
echo "   3. Test the setup: curl http://95.216.216.26/health"
echo ""
echo "🔒 Security note:"
echo "   - Port 8000 is now only accessible internally (localhost)"
echo "   - External access is only through Nginx on port 80"
echo "   - Consider setting up a firewall rule to block direct access to port 8000"

