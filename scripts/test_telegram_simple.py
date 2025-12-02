#!/usr/bin/env python3
"""Simple standalone Telegram notification test.

This is a minimal script that tests Telegram notifications without requiring
the full application setup. Useful for quick testing.

Usage:
    python scripts/test_telegram_simple.py
    
    Or with environment variables:
    TELEGRAM_BOT_TOKEN=your_token TELEGRAM_CHAT_ID=your_chat_id python scripts/test_telegram_simple.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    print("❌ Error: httpx is not installed.")
    print("   Install it with: pip install httpx")
    sys.exit(1)


async def send_test_message(bot_token: str, chat_id: str) -> bool:
    """Send a test message to Telegram."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    message = (
        "🧪 <b>Telegram Notification Test</b>\n\n"
        "This is a test message to verify your Telegram bot is working correctly.\n\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        "✅ If you received this message, your Telegram notifications are configured correctly!"
    )
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            if result.get("ok"):
                print("✅ Message sent successfully!")
                print(f"   Message ID: {result.get('result', {}).get('message_id', 'N/A')}")
                return True
            else:
                error_desc = result.get("description", "Unknown error")
                print(f"❌ Telegram API error: {error_desc}")
                return False
                
    except httpx.TimeoutException:
        print("❌ Timeout: Could not connect to Telegram API")
        return False
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP error: {e.response.status_code}")
        
        # Try to get error details from response
        try:
            error_data = e.response.json()
            error_desc = error_data.get("description", "Unknown error")
            print(f"   Error description: {error_desc}")
        except:
            pass
        
        if e.response.status_code == 401:
            print("   This usually means your bot token is invalid.")
            print("   Verify your token with @BotFather on Telegram")
        elif e.response.status_code == 400:
            print("   This usually means your chat ID is invalid.")
            print("   Make sure you've started a conversation with your bot")
        elif e.response.status_code == 404:
            print("   This usually means:")
            print("   1. Your bot token is invalid or malformed")
            print("   2. The bot was deleted or doesn't exist")
            print("   3. There's a typo in your bot token")
            print()
            print("   Troubleshooting:")
            print("   - Check your bot token format (should be: numbers:letters)")
            print("   - Verify your bot exists by messaging it on Telegram")
            print("   - Get a new token from @BotFather if needed")
        
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


async def main() -> None:
    """Main function."""
    print("=" * 60)
    print("  Telegram Notification Test (Simple)")
    print("=" * 60)
    print()
    
    # Get configuration from environment or .env file
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    # Try to load from .env file if not in environment
    if not bot_token or not chat_id:
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_file):
            print("ℹ️  Loading configuration from .env file...")
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key == "TELEGRAM_BOT_TOKEN" and not bot_token:
                                bot_token = value.strip().strip('"').strip("'")
                            elif key == "TELEGRAM_CHAT_ID" and not chat_id:
                                chat_id = value.strip().strip('"').strip("'")
    
    # Check configuration
    if not bot_token:
        print("❌ Error: TELEGRAM_BOT_TOKEN is not set.")
        print()
        print("   Set it as an environment variable:")
        print("   export TELEGRAM_BOT_TOKEN=your_bot_token")
        print()
        print("   Or add it to your .env file:")
        print("   TELEGRAM_BOT_TOKEN=your_bot_token")
        print()
        print("   Get your bot token from @BotFather on Telegram")
        sys.exit(1)
    
    if not chat_id:
        print("❌ Error: TELEGRAM_CHAT_ID is not set.")
        print()
        print("   Set it as an environment variable:")
        print("   export TELEGRAM_CHAT_ID=your_chat_id")
        print()
        print("   Or add it to your .env file:")
        print("   TELEGRAM_CHAT_ID=your_chat_id")
        print()
        print("   Get your chat ID by messaging @userinfobot on Telegram")
        sys.exit(1)
    
    print("ℹ️  Configuration:")
    print(f"   Bot Token: {bot_token[:10]}...{bot_token[-5:]}")
    print(f"   Bot Token Length: {len(bot_token)} characters")
    print(f"   Chat ID: {chat_id}")
    print()
    
    # Validate bot token format
    if ":" not in bot_token:
        print("⚠️  Warning: Bot token format looks incorrect.")
        print("   Expected format: numbers:letters (e.g., 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)")
        print()
    
    # Test bot token by checking bot info
    print("🔍 Verifying bot token...")
    try:
        verify_url = f"https://api.telegram.org/bot{bot_token}/getMe"
        async with httpx.AsyncClient(timeout=10.0) as client:
            verify_response = await client.get(verify_url)
            verify_result = verify_response.json()
            
            if verify_result.get("ok"):
                bot_info = verify_result.get("result", {})
                bot_username = bot_info.get("username", "Unknown")
                print(f"✅ Bot token is valid! Bot username: @{bot_username}")
            else:
                error_desc = verify_result.get("description", "Unknown error")
                print(f"❌ Bot token verification failed: {error_desc}")
                print()
                print("   Your bot token appears to be invalid.")
                print("   Please check your token with @BotFather on Telegram")
                return
    except Exception as e:
        print(f"⚠️  Could not verify bot token: {e}")
        print("   Continuing with message test anyway...")
    
    print()
    
    print("📤 Sending test message...")
    print()
    
    success = await send_test_message(bot_token, chat_id)
    
    print()
    if success:
        print("✅ Test completed successfully!")
        print("   Check your Telegram chat to confirm you received the message.")
    else:
        print("❌ Test failed. Check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user.")
        sys.exit(1)

