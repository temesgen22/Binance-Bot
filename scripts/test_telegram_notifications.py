#!/usr/bin/env python3
"""Test script for Telegram notifications.

This script tests if Telegram notifications are working correctly by sending
various test messages to your configured Telegram chat.

Usage:
    python scripts/test_telegram_notifications.py
    
    Or with environment variables:
    TELEGRAM_BOT_TOKEN=your_token TELEGRAM_CHAT_ID=your_chat_id python scripts/test_telegram_notifications.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.notifier import TelegramNotifier, NotificationService, NotificationType
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.core.config import get_settings


def print_header(text: str) -> None:
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_success(text: str) -> None:
    """Print success message."""
    print(f"✅ {text}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"❌ {text}")


def print_info(text: str) -> None:
    """Print info message."""
    print(f"ℹ️  {text}")


async def test_basic_message(notifier: TelegramNotifier) -> bool:
    """Test sending a basic message."""
    print_header("Test 1: Basic Message")
    
    test_message = (
        "🧪 <b>Telegram Notification Test</b>\n\n"
        "This is a test message to verify your Telegram bot is working correctly.\n\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    
    print_info("Sending basic test message...")
    result = await notifier.send_message(test_message)
    
    if result:
        print_success("Basic message sent successfully!")
        print_info("Check your Telegram chat to confirm you received the message.")
        return True
    else:
        print_error("Failed to send basic message.")
        return False


async def test_strategy_started(notifier: TelegramNotifier) -> bool:
    """Test strategy started notification."""
    print_header("Test 2: Strategy Started Notification")
    
    # Create a mock strategy summary
    summary = StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
    )
    
    print_info("Sending strategy started notification...")
    result = await notifier.notify_strategy_started(
        summary,
        reason="Test notification - strategy started"
    )
    
    if result:
        print_success("Strategy started notification sent!")
        return True
    else:
        print_error("Failed to send strategy started notification.")
        return False


async def test_strategy_stopped(notifier: TelegramNotifier) -> bool:
    """Test strategy stopped notification."""
    print_header("Test 3: Strategy Stopped Notification")
    
    summary = StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.stopped,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
        entry_price=50000.0,
        current_price=50100.0,
        position_size=0.1,
        position_side="LONG",
        unrealized_pnl=10.0,
    )
    
    print_info("Sending strategy stopped notification...")
    result = await notifier.notify_strategy_stopped(
        summary,
        reason="Test notification - strategy stopped",
        final_pnl=25.50
    )
    
    if result:
        print_success("Strategy stopped notification sent!")
        return True
    else:
        print_error("Failed to send strategy stopped notification.")
        return False


async def test_strategy_error(notifier: TelegramNotifier) -> bool:
    """Test strategy error notification."""
    print_header("Test 4: Strategy Error Notification")
    
    summary = StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.error,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
    )
    
    test_error = Exception("Test error: This is a simulated error for testing purposes")
    
    print_info("Sending strategy error notification...")
    result = await notifier.notify_strategy_error(
        summary,
        test_error,
        error_type="TestError"
    )
    
    if result:
        print_success("Strategy error notification sent!")
        return True
    else:
        print_error("Failed to send strategy error notification.")
        return False


async def test_pnl_threshold(notifier: TelegramNotifier) -> bool:
    """Test PnL threshold notification."""
    print_header("Test 5: PnL Threshold Notification")
    
    summary = StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
        entry_price=50000.0,
        current_price=50500.0,
        position_size=0.1,
        position_side="LONG",
        unrealized_pnl=50.0,
    )
    
    print_info("Sending PnL threshold notification (profit)...")
    result = await notifier.notify_pnl_threshold(
        summary,
        pnl=100.0,
        threshold=50.0
    )
    
    if result:
        print_success("PnL threshold notification sent!")
        return True
    else:
        print_error("Failed to send PnL threshold notification.")
        return False


async def test_critical_error(notifier: TelegramNotifier) -> bool:
    """Test critical error notification."""
    print_header("Test 6: Critical Error Notification")
    
    test_error = Exception("Test critical error: System failure simulation")
    
    print_info("Sending critical error notification...")
    result = await notifier.notify_critical_error(
        summary=None,
        error=test_error,
        context="Test notification system"
    )
    
    if result:
        print_success("Critical error notification sent!")
        return True
    else:
        print_error("Failed to send critical error notification.")
        return False


async def run_all_tests() -> None:
    """Run all notification tests."""
    print_header("Telegram Notification Test Suite")
    
    # Load settings
    settings = get_settings()
    
    # Check configuration
    print_info("Checking configuration...")
    
    if not settings.telegram_enabled:
        print_error("Telegram notifications are disabled in settings.")
        print_info("Set TELEGRAM_ENABLED=true in your .env file")
        return
    
    if not settings.telegram_bot_token:
        print_error("TELEGRAM_BOT_TOKEN is not set.")
        print_info("Get your bot token from @BotFather on Telegram")
        return
    
    if not settings.telegram_chat_id:
        print_error("TELEGRAM_CHAT_ID is not set.")
        print_info("Get your chat ID by messaging @userinfobot on Telegram")
        return
    
    print_success("Configuration looks good!")
    print_info(f"Bot Token: {settings.telegram_bot_token[:10]}...")
    print_info(f"Chat ID: {settings.telegram_chat_id}")
    print()
    
    # Create notifier
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        enabled=settings.telegram_enabled,
    )
    
    if not notifier.enabled:
        print_error("Telegram notifier is not enabled.")
        return
    
    # Run tests
    results = []
    
    # Test 1: Basic message
    results.append(await test_basic_message(notifier))
    await asyncio.sleep(1)  # Small delay between messages
    
    # Test 2: Strategy started
    results.append(await test_strategy_started(notifier))
    await asyncio.sleep(1)
    
    # Test 3: Strategy stopped
    results.append(await test_strategy_stopped(notifier))
    await asyncio.sleep(1)
    
    # Test 4: Strategy error
    results.append(await test_strategy_error(notifier))
    await asyncio.sleep(1)
    
    # Test 5: PnL threshold
    results.append(await test_pnl_threshold(notifier))
    await asyncio.sleep(1)
    
    # Test 6: Critical error
    results.append(await test_critical_error(notifier))
    
    # Summary
    print_header("Test Summary")
    total = len(results)
    passed = sum(results)
    failed = total - passed
    
    print(f"Total tests: {total}")
    print_success(f"Passed: {passed}")
    if failed > 0:
        print_error(f"Failed: {failed}")
    
    if all(results):
        print()
        print_success("🎉 All tests passed! Your Telegram notifications are working correctly.")
        print_info("Check your Telegram chat to see all the test messages.")
    else:
        print()
        print_error("Some tests failed. Check the error messages above and verify your configuration.")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

