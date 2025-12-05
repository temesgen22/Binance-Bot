"""Comprehensive test script to verify Telegram notifier and command handler functionality."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.telegram_commands import TelegramCommandHandler
from app.services.notifier import TelegramNotifier, NotificationService
from app.services.strategy_runner import StrategyRunner
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from datetime import datetime, timezone


def test_telegram_notifier_initialization():
    """Test TelegramNotifier initialization."""
    print("=" * 60)
    print("TEST 1: TelegramNotifier Initialization")
    print("=" * 60)
    
    # Test enabled
    notifier = TelegramNotifier(
        bot_token="test_token",
        chat_id="123456",
        enabled=True
    )
    assert notifier.enabled is True
    assert notifier.base_url == "https://api.telegram.org/bottest_token"
    print("✅ Notifier enabled correctly")
    
    # Test disabled
    notifier_disabled = TelegramNotifier(
        bot_token="test_token",
        chat_id="123456",
        enabled=False
    )
    assert notifier_disabled.enabled is False
    assert notifier_disabled.base_url is None
    print("✅ Notifier disabled correctly")
    
    # Test missing token
    notifier_no_token = TelegramNotifier(
        bot_token=None,
        chat_id="123456",
        enabled=True
    )
    assert notifier_no_token.enabled is False
    print("✅ Notifier handles missing token correctly")
    
    print("✅ All initialization tests passed!\n")


def test_telegram_command_handler_initialization():
    """Test TelegramCommandHandler initialization."""
    print("=" * 60)
    print("TEST 2: TelegramCommandHandler Initialization")
    print("=" * 60)
    
    mock_runner = MagicMock(spec=StrategyRunner)
    
    # Test enabled
    handler = TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=mock_runner,
        enabled=True
    )
    assert handler.enabled is True
    assert handler.base_url == "https://api.telegram.org/bottest_token"
    print("✅ Handler enabled correctly")
    
    # Test disabled
    handler_disabled = TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=mock_runner,
        enabled=False
    )
    assert handler_disabled.enabled is False
    assert handler_disabled.base_url is None
    print("✅ Handler disabled correctly")
    
    # Test missing token
    handler_no_token = TelegramCommandHandler(
        bot_token=None,
        strategy_runner=mock_runner,
        enabled=True
    )
    assert handler_no_token.enabled is False
    print("✅ Handler handles missing token correctly")
    
    print("✅ All initialization tests passed!\n")


async def test_command_parsing():
    """Test command parsing."""
    print("=" * 60)
    print("TEST 3: Command Parsing")
    print("=" * 60)
    
    mock_runner = MagicMock(spec=StrategyRunner)
    handler = TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=mock_runner,
        enabled=True
    )
    
    # Test help command
    response = await handler.process_command("123", "help", [])
    assert "Binance Trading Bot Commands" in response
    print("✅ Help command works")
    
    # Test start command (without args = help)
    response = await handler.process_command("123", "start", [])
    assert "Binance Trading Bot Commands" in response
    print("✅ Start command (help) works")
    
    # Test unknown command
    response = await handler.process_command("123", "unknown", [])
    assert "Unknown command" in response
    print("✅ Unknown command handling works")
    
    print("✅ All command parsing tests passed!\n")


async def test_status_command():
    """Test /status command."""
    print("=" * 60)
    print("TEST 4: Status Command")
    print("=" * 60)
    
    mock_runner = MagicMock(spec=StrategyRunner)
    
    # Create mock strategies
    running_strategy = StrategySummary(
        id="test-1",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
    )
    
    stopped_strategy = StrategySummary(
        id="test-2",
        name="Stopped Strategy",
        symbol="ETHUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.stopped,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
    )
    
    mock_runner.list_strategies.return_value = [running_strategy, stopped_strategy]
    
    def mock_stats(strategy_id):
        stats = MagicMock()
        stats.total_pnl = 25.0 if strategy_id == "test-1" else 0.0
        return stats
    
    mock_runner.calculate_strategy_stats = mock_stats
    
    handler = TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=mock_runner,
        enabled=True
    )
    
    response = await handler.process_command("123", "status", [])
    
    assert "Bot Status" in response
    assert "Running: 1" in response
    assert "Stopped: 1" in response
    assert "Total PnL" in response
    print("✅ Status command works correctly")
    print(f"Response preview: {response[:100]}...\n")


async def test_list_command():
    """Test /list command."""
    print("=" * 60)
    print("TEST 5: List Command")
    print("=" * 60)
    
    mock_runner = MagicMock(spec=StrategyRunner)
    
    strategy = StrategySummary(
        id="test-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
    )
    
    mock_runner.list_strategies.return_value = [strategy]
    
    def mock_stats(strategy_id):
        stats = MagicMock()
        stats.total_pnl = 50.25
        return stats
    
    mock_runner.calculate_strategy_stats = mock_stats
    
    handler = TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=mock_runner,
        enabled=True
    )
    
    response = await handler.process_command("123", "list", [])
    
    assert "Strategies" in response
    assert "Test Strategy" in response
    assert "BTCUSDT" in response
    assert "$50.25" in response
    print("✅ List command works correctly")
    print(f"Response preview: {response[:150]}...\n")


async def test_message_sending():
    """Test message sending functionality."""
    print("=" * 60)
    print("TEST 6: Message Sending")
    print("=" * 60)
    
    handler = TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=MagicMock(),
        enabled=True
    )
    
    # Mock httpx
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        result = await handler.send_message("123", "Test message")
        assert result is True
        print("✅ Message sending works correctly")
    
    # Test disabled handler
    handler_disabled = TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=MagicMock(),
        enabled=False
    )
    result = await handler_disabled.send_message("123", "Test message")
    assert result is False
    print("✅ Disabled handler correctly skips sending\n")


async def test_notification_service():
    """Test NotificationService."""
    print("=" * 60)
    print("TEST 7: Notification Service")
    print("=" * 60)
    
    mock_notifier = MagicMock(spec=TelegramNotifier)
    mock_notifier.send_message = AsyncMock(return_value=True)
    mock_notifier.notify_strategy_started = AsyncMock(return_value=True)
    mock_notifier.notify_strategy_stopped = AsyncMock(return_value=True)
    
    service = NotificationService(
        telegram_notifier=mock_notifier,
        profit_threshold_usd=100.0,
        loss_threshold_usd=-50.0
    )
    
    strategy = StrategySummary(
        id="test-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
    )
    
    # Test strategy started notification
    await service.notify_strategy_started(strategy, reason="Manual start")
    mock_notifier.notify_strategy_started.assert_called_once()
    print("✅ Strategy started notification works")
    
    # Test strategy stopped notification
    await service.notify_strategy_stopped(strategy, reason="Manual stop", final_pnl=25.0)
    mock_notifier.notify_strategy_stopped.assert_called_once()
    print("✅ Strategy stopped notification works")
    
    print("✅ All notification service tests passed!\n")


def test_integration_check():
    """Check integration points."""
    print("=" * 60)
    print("TEST 8: Integration Check")
    print("=" * 60)
    
    # Check if StrategyRunner has client attribute
    mock_client = MagicMock()
    mock_client_manager = MagicMock()
    mock_client_manager.get_default_client.return_value = mock_client
    
    runner = StrategyRunner(
        client_manager=mock_client_manager,
        client=mock_client,
        max_concurrent=3
    )
    
    assert hasattr(runner, 'client')
    assert runner.client is not None
    print("✅ StrategyRunner has client attribute for balance command")
    
    # Check if balance command can access client
    handler = TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=runner,
        enabled=True
    )
    
    # The balance command accesses runner.client, which should exist
    assert handler.strategy_runner.client is not None
    print("✅ Telegram command handler can access StrategyRunner client")
    
    print("✅ All integration checks passed!\n")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("TELEGRAM NOTIFIER & COMMAND HANDLER COMPREHENSIVE TEST")
    print("=" * 60 + "\n")
    
    try:
        # Run synchronous tests
        test_telegram_notifier_initialization()
        test_telegram_command_handler_initialization()
        test_integration_check()
        
        # Run async tests
        await test_command_parsing()
        await test_status_command()
        await test_list_command()
        await test_message_sending()
        await test_notification_service()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSummary:")
        print("- TelegramNotifier: ✅ Working correctly")
        print("- TelegramCommandHandler: ✅ Working correctly")
        print("- Command Parsing: ✅ Working correctly")
        print("- Status/List Commands: ✅ Working correctly")
        print("- Message Sending: ✅ Working correctly")
        print("- Notification Service: ✅ Working correctly")
        print("- Integration: ✅ Working correctly")
        print("\n💡 To test with real Telegram bot:")
        print("   1. Set TELEGRAM_BOT_TOKEN in .env")
        print("   2. Set TELEGRAM_CHAT_ID in .env")
        print("   3. Set TELEGRAM_ENABLED=true in .env")
        print("   4. Start the application")
        print("   5. Send /help to your bot in Telegram")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


