"""Test cases for Telegram notification service."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import httpx

from app.services.notifier import (
    TelegramNotifier,
    NotificationService,
    NotificationType,
    NotificationLevel,
)
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams


@pytest.fixture
def mock_strategy_summary():
    """Create a mock StrategySummary for testing."""
    return StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
        last_signal=None,
        entry_price=50000.0,
        current_price=50100.0,
        position_size=0.1,
        position_side="LONG",
        unrealized_pnl=10.0,
    )


@pytest.fixture
def telegram_notifier():
    """Create a TelegramNotifier instance for testing."""
    return TelegramNotifier(
        bot_token="test_token_123",
        chat_id="test_chat_456",
        enabled=True,
    )


@pytest.fixture
def disabled_telegram_notifier():
    """Create a disabled TelegramNotifier instance for testing."""
    return TelegramNotifier(
        bot_token=None,
        chat_id=None,
        enabled=False,
    )


class TestTelegramNotifier:
    """Test cases for TelegramNotifier class."""
    
    def test_initialization_enabled(self):
        """Test that TelegramNotifier initializes correctly when enabled."""
        notifier = TelegramNotifier(
            bot_token="test_token",
            chat_id="test_chat",
            enabled=True,
        )
        assert notifier.enabled is True
        assert notifier.bot_token == "test_token"
        assert notifier.chat_id == "test_chat"
        assert notifier.base_url == "https://api.telegram.org/bottest_token"
    
    def test_initialization_disabled_missing_token(self):
        """Test that TelegramNotifier is disabled when token is missing."""
        notifier = TelegramNotifier(
            bot_token=None,
            chat_id="test_chat",
            enabled=True,
        )
        assert notifier.enabled is False
    
    def test_initialization_disabled_missing_chat_id(self):
        """Test that TelegramNotifier is disabled when chat_id is missing."""
        notifier = TelegramNotifier(
            bot_token="test_token",
            chat_id=None,
            enabled=True,
        )
        assert notifier.enabled is False
    
    def test_initialization_explicitly_disabled(self):
        """Test that TelegramNotifier is disabled when enabled=False."""
        notifier = TelegramNotifier(
            bot_token="test_token",
            chat_id="test_chat",
            enabled=False,
        )
        assert notifier.enabled is False
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, telegram_notifier):
        """Test successful message sending."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 123}}
        mock_response.raise_for_status = MagicMock()
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            result = await telegram_notifier.send_message("Test message")
            assert result is True
            mock_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_message_api_error(self, telegram_notifier):
        """Test message sending when Telegram API returns error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": False, "description": "Invalid token"}
        mock_response.raise_for_status = MagicMock()
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            result = await telegram_notifier.send_message("Test message")
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_timeout(self, telegram_notifier):
        """Test message sending when timeout occurs."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client
            
            result = await telegram_notifier.send_message("Test message")
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_disabled(self, disabled_telegram_notifier):
        """Test that message sending is skipped when notifier is disabled."""
        result = await disabled_telegram_notifier.send_message("Test message")
        assert result is False
    
    def test_format_strategy_message_started(self, telegram_notifier, mock_strategy_summary):
        """Test formatting strategy started notification."""
        message = telegram_notifier.format_strategy_message(
            NotificationType.STRATEGY_STARTED,
            mock_strategy_summary,
            {"reason": "Strategy started manually"},
        )
        
        assert "Strategy: Test Strategy" in message
        assert "BTCUSDT" in message
        assert "scalping" in message
        assert "5x" in message
        assert "Strategy Started" in message
        assert "Strategy started manually" in message
        assert "LONG" in message
        assert "$50,000.00" in message
    
    def test_format_strategy_message_stopped(self, telegram_notifier, mock_strategy_summary):
        """Test formatting strategy stopped notification."""
        message = telegram_notifier.format_strategy_message(
            NotificationType.STRATEGY_STOPPED,
            mock_strategy_summary,
            {"reason": "Strategy stopped manually", "final_pnl": 25.5},
        )
        
        assert "Strategy Stopped" in message
        assert "Strategy stopped manually" in message
        assert "$25.50" in message  # Final PnL
    
    def test_format_strategy_message_error(self, telegram_notifier, mock_strategy_summary):
        """Test formatting strategy error notification."""
        message = telegram_notifier.format_strategy_message(
            NotificationType.STRATEGY_ERROR,
            mock_strategy_summary,
            {"error": "Connection timeout", "error_type": "BinanceNetworkError"},
        )
        
        assert "Strategy Error" in message
        assert "Connection timeout" in message
        assert "BinanceNetworkError" in message
    
    def test_format_strategy_message_pnl_threshold(self, telegram_notifier, mock_strategy_summary):
        """Test formatting PnL threshold notification."""
        message = telegram_notifier.format_strategy_message(
            NotificationType.PNL_THRESHOLD,
            mock_strategy_summary,
            {"pnl": 100.0, "threshold": 100.0},
        )
        
        assert "Profit Threshold Reached" in message
        assert "$100.00" in message
    
    @pytest.mark.asyncio
    async def test_notify_strategy_started(self, telegram_notifier, mock_strategy_summary):
        """Test strategy started notification."""
        with patch.object(telegram_notifier, 'send_message', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            result = await telegram_notifier.notify_strategy_started(
                mock_strategy_summary,
                reason="Strategy started manually"
            )
            
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            message = call_args[0][0]
            assert "Strategy Started" in message
            assert "Strategy started manually" in message
    
    @pytest.mark.asyncio
    async def test_notify_strategy_stopped(self, telegram_notifier, mock_strategy_summary):
        """Test strategy stopped notification."""
        with patch.object(telegram_notifier, 'send_message', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            result = await telegram_notifier.notify_strategy_stopped(
                mock_strategy_summary,
                reason="Strategy stopped manually",
                final_pnl=50.0,
            )
            
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            message = call_args[0][0]
            assert "Strategy Stopped" in message
            assert "$50.00" in message
    
    @pytest.mark.asyncio
    async def test_notify_strategy_error(self, telegram_notifier, mock_strategy_summary):
        """Test strategy error notification."""
        with patch.object(telegram_notifier, 'send_message', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            error = Exception("Test error")
            result = await telegram_notifier.notify_strategy_error(
                mock_strategy_summary,
                error,
                error_type="TestError",
            )
            
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            message = call_args[0][0]
            assert "Strategy Error" in message
            assert "Test error" in message


class TestNotificationService:
    """Test cases for NotificationService class."""
    
    def test_initialization_with_notifier(self, telegram_notifier):
        """Test NotificationService initialization with TelegramNotifier."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            profit_threshold_usd=100.0,
            loss_threshold_usd=-50.0,
        )
        
        assert service.telegram is not None
        assert service.profit_threshold == 100.0
        assert service.loss_threshold == -50.0
    
    def test_initialization_without_notifier(self):
        """Test NotificationService initialization without notifier."""
        service = NotificationService(
            telegram_notifier=None,
            profit_threshold_usd=None,
            loss_threshold_usd=None,
        )
        
        assert service.telegram is None
        assert service.profit_threshold is None
        assert service.loss_threshold is None
    
    @pytest.mark.asyncio
    async def test_notify_strategy_started(self, telegram_notifier, mock_strategy_summary):
        """Test strategy started notification through service."""
        service = NotificationService(telegram_notifier=telegram_notifier)
        
        with patch.object(telegram_notifier, 'notify_strategy_started', new_callable=AsyncMock) as mock_notify:
            await service.notify_strategy_started(mock_strategy_summary, reason="Test")
            
            mock_notify.assert_called_once_with(mock_strategy_summary, "Test")
    
    @pytest.mark.asyncio
    async def test_notify_strategy_started_no_notifier(self, mock_strategy_summary):
        """Test that notification is skipped when no notifier is configured."""
        service = NotificationService(telegram_notifier=None)
        
        # Should not raise any error
        await service.notify_strategy_started(mock_strategy_summary, reason="Test")
    
    @pytest.mark.asyncio
    async def test_notify_strategy_stopped(self, telegram_notifier, mock_strategy_summary):
        """Test strategy stopped notification through service."""
        service = NotificationService(telegram_notifier=telegram_notifier)
        
        with patch.object(telegram_notifier, 'notify_strategy_stopped', new_callable=AsyncMock) as mock_notify:
            await service.notify_strategy_stopped(
                mock_strategy_summary,
                reason="Test",
                final_pnl=25.0,
            )
            
            mock_notify.assert_called_once_with(
                mock_strategy_summary,
                "Test",
                25.0,
            )
    
    @pytest.mark.asyncio
    async def test_notify_strategy_error(self, telegram_notifier, mock_strategy_summary):
        """Test strategy error notification through service."""
        service = NotificationService(telegram_notifier=telegram_notifier)
        
        error = Exception("Test error")
        with patch.object(telegram_notifier, 'notify_strategy_error', new_callable=AsyncMock) as mock_notify:
            await service.notify_strategy_error(
                mock_strategy_summary,
                error,
                error_type="TestError",
            )
            
            mock_notify.assert_called_once_with(
                mock_strategy_summary,
                error,
                "TestError",
            )
    
    @pytest.mark.asyncio
    async def test_check_and_notify_pnl_threshold_profit(self, telegram_notifier, mock_strategy_summary):
        """Test PnL threshold notification for profit."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            profit_threshold_usd=100.0,
        )
        
        # Set PnL above threshold
        mock_strategy_summary.unrealized_pnl = 150.0
        
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock) as mock_notify:
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 150.0)
            
            mock_notify.assert_called_once_with(
                mock_strategy_summary,
                150.0,
                100.0,
            )
    
    @pytest.mark.asyncio
    async def test_check_and_notify_pnl_threshold_loss(self, telegram_notifier, mock_strategy_summary):
        """Test PnL threshold notification for loss."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            loss_threshold_usd=-50.0,
        )
        
        # Set PnL below threshold
        mock_strategy_summary.unrealized_pnl = -75.0
        
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock) as mock_notify:
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, -75.0)
            
            mock_notify.assert_called_once_with(
                mock_strategy_summary,
                -75.0,
                -50.0,
            )
    
    @pytest.mark.asyncio
    async def test_check_and_notify_pnl_threshold_no_notification_below_threshold(self, telegram_notifier, mock_strategy_summary):
        """Test that no notification is sent when PnL is below profit threshold."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            profit_threshold_usd=100.0,
        )
        
        # Set PnL below threshold
        mock_strategy_summary.unrealized_pnl = 50.0
        
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock) as mock_notify:
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 50.0)
            
            mock_notify.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_check_and_notify_pnl_threshold_no_notification_above_loss_threshold(self, telegram_notifier, mock_strategy_summary):
        """Test that no notification is sent when PnL is above loss threshold."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            loss_threshold_usd=-50.0,
        )
        
        # Set PnL above threshold (smaller loss)
        mock_strategy_summary.unrealized_pnl = -25.0
        
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock) as mock_notify:
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, -25.0)
            
            mock_notify.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_check_and_notify_pnl_threshold_spam_prevention(self, telegram_notifier, mock_strategy_summary):
        """Test that threshold notifications are not sent repeatedly (spam prevention)."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            profit_threshold_usd=100.0,
        )
        
        mock_strategy_summary.unrealized_pnl = 150.0
        
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock) as mock_notify:
            # First notification should be sent
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 150.0)
            assert mock_notify.call_count == 1
            
            # Second call with same PnL should not send another notification
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 150.0)
            assert mock_notify.call_count == 1
            
            # But higher PnL should trigger a new notification
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 200.0)
            assert mock_notify.call_count == 2
    
    @pytest.mark.asyncio
    async def test_check_and_notify_pnl_threshold_different_directions(self, telegram_notifier, mock_strategy_summary):
        """Test that profit and loss thresholds are tracked separately."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            profit_threshold_usd=100.0,
            loss_threshold_usd=-50.0,
        )
        
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock) as mock_notify:
            # Profit threshold
            mock_strategy_summary.unrealized_pnl = 150.0
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 150.0)
            
            # Loss threshold (different direction)
            mock_strategy_summary.unrealized_pnl = -75.0
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, -75.0)
            
            # Both should be called
            assert mock_notify.call_count == 2
    
    @pytest.mark.asyncio
    async def test_check_and_notify_pnl_threshold_reset_on_strategy_start(self, telegram_notifier, mock_strategy_summary):
        """Test that threshold tracking is reset when strategy starts."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            profit_threshold_usd=100.0,
        )
        
        # Trigger profit threshold
        mock_strategy_summary.unrealized_pnl = 150.0
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock):
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 150.0)
        
        # Start strategy (should reset threshold tracking)
        with patch.object(telegram_notifier, 'notify_strategy_started', new_callable=AsyncMock):
            await service.notify_strategy_started(mock_strategy_summary)
        
        # Threshold tracking should be reset, so notification should be sent again
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock) as mock_notify:
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 150.0)
            mock_notify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_and_notify_pnl_threshold_reset_on_strategy_stop(self, telegram_notifier, mock_strategy_summary):
        """Test that threshold tracking is cleared when strategy stops."""
        service = NotificationService(
            telegram_notifier=telegram_notifier,
            profit_threshold_usd=100.0,
        )
        
        # Trigger profit threshold
        mock_strategy_summary.unrealized_pnl = 150.0
        with patch.object(telegram_notifier, 'notify_pnl_threshold', new_callable=AsyncMock):
            await service.check_and_notify_pnl_threshold(mock_strategy_summary, 150.0)
        
        # Stop strategy (should clear threshold tracking)
        with patch.object(telegram_notifier, 'notify_strategy_stopped', new_callable=AsyncMock):
            await service.notify_strategy_stopped(mock_strategy_summary)
        
        # Threshold tracking should be cleared
        assert mock_strategy_summary.id not in service._notified_thresholds
    
    @pytest.mark.asyncio
    async def test_notify_critical_error(self, telegram_notifier):
        """Test critical error notification."""
        service = NotificationService(telegram_notifier=telegram_notifier)
        
        error = Exception("Critical system error")
        with patch.object(telegram_notifier, 'notify_critical_error', new_callable=AsyncMock) as mock_notify:
            await service.notify_critical_error(
                summary=None,
                error=error,
                context="System initialization",
            )
            
            mock_notify.assert_called_once_with(
                None,
                error,
                "System initialization",
            )
    
    @pytest.mark.asyncio
    async def test_notify_critical_error_with_strategy(self, telegram_notifier, mock_strategy_summary):
        """Test critical error notification with strategy context."""
        service = NotificationService(telegram_notifier=telegram_notifier)
        
        error = Exception("Order execution failed")
        with patch.object(telegram_notifier, 'notify_critical_error', new_callable=AsyncMock) as mock_notify:
            await service.notify_critical_error(
                summary=mock_strategy_summary,
                error=error,
                context="Order execution",
            )
            
            mock_notify.assert_called_once_with(
                mock_strategy_summary,
                error,
                "Order execution",
            )


@pytest.mark.slow
class TestNotificationIntegration:
    """Integration tests for notification service with StrategySummary."""
    
    def test_message_formatting_with_various_states(self, telegram_notifier):
        """Test message formatting with different strategy states."""
        # Test with stopped state
        stopped_summary = StrategySummary(
            id="test-1",
            name="Stopped Strategy",
            symbol="ETHUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=10,
            risk_per_trade=0.02,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
        )
        
        message = telegram_notifier.format_strategy_message(
            NotificationType.STRATEGY_STOPPED,
            stopped_summary,
        )
        
        assert "Stopped Strategy" in message
        assert "ETHUSDT" in message
        assert "10x" in message
        assert "Strategy Stopped" in message
    
    def test_message_formatting_with_short_position(self, telegram_notifier):
        """Test message formatting with SHORT position."""
        short_summary = StrategySummary(
            id="test-2",
            name="Short Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
            entry_price=50000.0,
            current_price=49500.0,
            position_size=0.1,
            position_side="SHORT",
            unrealized_pnl=50.0,  # Profit on short when price goes down
        )
        
        message = telegram_notifier.format_strategy_message(
            NotificationType.STRATEGY_STARTED,
            short_summary,
        )
        
        assert "SHORT" in message
        assert "⬇️" in message  # Short position emoji
        assert "$50.00" in message  # PnL

