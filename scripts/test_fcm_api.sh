#!/bin/bash
#
# FCM API Endpoint Test Script
#
# Usage: 
#   ./scripts/test_fcm_api.sh <API_URL> <AUTH_TOKEN>
#
# Example:
#   ./scripts/test_fcm_api.sh http://95.216.216.26 "eyJhbGciOiJIUzI1NiIsInR5cCI6..."
#

set -e

API_URL="${1:-http://localhost:8000}"
AUTH_TOKEN="${2:-}"

if [ -z "$AUTH_TOKEN" ]; then
    echo "Usage: $0 <API_URL> <AUTH_TOKEN>"
    echo ""
    echo "Example:"
    echo "  $0 http://95.216.216.26 'your-jwt-token'"
    exit 1
fi

echo "=============================================="
echo " FCM API Endpoint Tests"
echo "=============================================="
echo ""
echo "API URL: $API_URL"
echo ""

# Test 1: List FCM tokens
echo "Test 1: List FCM Tokens"
echo "------------------------"
RESPONSE=$(curl -s -X GET "$API_URL/api/notifications/fcm/tokens" \
    -H "Authorization: Bearer $AUTH_TOKEN" \
    -H "Content-Type: application/json")

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""

# Test 2: Get FCM token summary
echo "Test 2: FCM Token Summary"
echo "--------------------------"
RESPONSE=$(curl -s -X GET "$API_URL/api/notifications/fcm/summary" \
    -H "Authorization: Bearer $AUTH_TOKEN" \
    -H "Content-Type: application/json")

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""

# Test 3: Register a test FCM token (if needed)
echo "Test 3: Register FCM Token (simulated)"
echo "----------------------------------------"
echo "POST /api/notifications/fcm/register"
echo "Body:"
cat << 'EOF'
{
    "token": "test-fcm-token-12345",
    "device_id": "test-device-001",
    "device_type": "android",
    "client_type": "android_app",
    "device_name": "Test Device",
    "app_version": "1.0.0"
}
EOF
echo ""
echo "(Not executing to avoid creating test data)"
echo ""

# Test 4: Check health endpoint
echo "Test 4: Health Check"
echo "---------------------"
RESPONSE=$(curl -s -X GET "$API_URL/health")
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""

echo "=============================================="
echo " FCM API Tests Complete"
echo "=============================================="
echo ""
echo "To trigger a real FCM notification:"
echo "1. Start a strategy from the Android app"
echo "2. Stop the strategy"
echo "3. Check the backend logs for:"
echo "   'Sent FCM notification to X/Y devices'"
echo ""
