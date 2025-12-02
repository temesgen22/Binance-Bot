"""Tests for Telegram command handler."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.telegram_commands import TelegramCommandHandler
from app.services.strategy_runner import StrategyRunner
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.core.exceptions import (
    StrategyNotFoundError,
    StrategyAlreadyRunningError,
    StrategyNotRunningError,
)


@pytest.fixture
def mock_strategy_runner():
    """Create a mock StrategyRunner."""
    runner = MagicMock(spec=StrategyRunner)
    runner.client = MagicMock()
    runner.client.futures_account_balance = MagicMock(return_value=10000.0)
    return runner


@pytest.fixture
def mock_strategy_summary():
    """Create a mock StrategySummary."""
    return StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        fixed_amount=None,
        params=StrategyParams(
            ema_fast=8,
            ema_slow=21,
            take_profit_pct=0.004,
            stop_loss_pct=0.002,
            interval_seconds=10,
            kline_interval="1m",
            enable_short=True,
            min_ema_separation=0.0002,
            enable_htf_bias=True,
            cooldown_candles=2,
            trailing_stop_enabled=False,
            trailing_stop_activation_pct=0.0,
            lookback_period=150,
            buy_zone_pct=0.2,
            sell_zone_pct=0.2,
            ema_fast_period=20,
            ema_slow_period=50,
            max_ema_spread_pct=0.005,
            max_atr_multiplier=2.0,
            rsi_period=14,
            rsi_oversold=40,
            rsi_overbought=60,
            tp_buffer_pct=0.001,
            sl_buffer_pct=0.002,
        ),
        created_at=datetime.now(timezone.utc),
        last_signal=None,
        entry_price=50000.0,
        current_price=50100.0,
        position_size=0.1,
        position_side="LONG",
        unrealized_pnl=10.0,
        meta={},
    )


@pytest.fixture
def mock_strategy_stats():
    """Create mock strategy statistics."""
    stats = MagicMock()
    stats.total_pnl = 50.25
    stats.total_trades = 10
    stats.win_rate = 0.7
    stats.avg_profit = 5.03
    return stats


@pytest.fixture
def command_handler(mock_strategy_runner):
    """Create a TelegramCommandHandler instance."""
    return TelegramCommandHandler(
        bot_token="test_token",
        strategy_runner=mock_strategy_runner,
        enabled=True,
    )


class TestTelegramCommandHandlerInitialization:
    """Test command handler initialization."""
    
    def test_initialization_enabled(self, mock_strategy_runner):
        """Test handler initialization when enabled."""
        handler = TelegramCommandHandler(
            bot_token="test_token",
            strategy_runner=mock_strategy_runner,
            enabled=True,
        )
        assert handler.enabled is True
        assert handler.bot_token == "test_token"
        assert handler.base_url == "https://api.telegram.org/bottest_token"
        assert handler._running is False
    
    def test_initialization_disabled(self, mock_strategy_runner):
        """Test handler initialization when disabled."""
        handler = TelegramCommandHandler(
            bot_token="test_token",
            strategy_runner=mock_strategy_runner,
            enabled=False,
        )
        assert handler.enabled is False
        assert handler.base_url is None
    
    def test_initialization_missing_token(self, mock_strategy_runner):
        """Test handler initialization with missing token."""
        handler = TelegramCommandHandler(
            bot_token=None,
            strategy_runner=mock_strategy_runner,
            enabled=True,
        )
        assert handler.enabled is False
        assert handler.base_url is None


class TestCommandParsing:
    """Test command parsing and routing."""
    
    @pytest.mark.asyncio
    async def test_help_command(self, command_handler):
        """Test /help command."""
        response = await command_handler.process_command("123", "help", [])
        assert "Binance Trading Bot Commands" in response
        assert "/help" in response
        assert "/status" in response
        assert "/list" in response
    
    @pytest.mark.asyncio
    async def test_start_command(self, command_handler):
        """Test /start command (same as help)."""
        response = await command_handler.process_command("123", "start", [])
        assert "Binance Trading Bot Commands" in response
    
    @pytest.mark.asyncio
    async def test_unknown_command(self, command_handler):
        """Test unknown command handling."""
        response = await command_handler.process_command("123", "unknown", [])
        assert "Unknown command" in response
        assert "/unknown" in response
        assert "/help" in response


class TestStatusCommand:
    """Test /status command."""
    
    @pytest.mark.asyncio
    async def test_status_command_success(self, command_handler, mock_strategy_runner, mock_strategy_summary):
        """Test /status command with strategies."""
        # Setup mock strategies
        running_strategy = mock_strategy_summary
        stopped_strategy = StrategySummary(**{**mock_strategy_summary.model_dump(), "id": "stopped-123", "status": StrategyState.stopped})
        
        mock_strategy_runner.list_strategies.return_value = [running_strategy, stopped_strategy]
        
        # Mock calculate_strategy_stats
        def mock_stats(strategy_id):
            stats = MagicMock()
            stats.total_pnl = 25.0 if strategy_id == "test-strategy-123" else 0.0
            return stats
        
        mock_strategy_runner.calculate_strategy_stats = mock_stats
        
        response = await command_handler.process_command("123", "status", [])
        
        assert "Bot Status" in response
        assert "Running: 1" in response
        assert "Stopped: 1" in response
        assert "Total PnL" in response
    
    @pytest.mark.asyncio
    async def test_status_command_error(self, command_handler, mock_strategy_runner):
        """Test /status command with error."""
        mock_strategy_runner.list_strategies.side_effect = Exception("Database error")
        
        response = await command_handler.process_command("123", "status", [])
        
        assert "Error getting status" in response


class TestListCommand:
    """Test /list command."""
    
    @pytest.mark.asyncio
    async def test_list_command_success(self, command_handler, mock_strategy_runner, mock_strategy_summary):
        """Test /list command with strategies."""
        mock_strategy_runner.list_strategies.return_value = [mock_strategy_summary]
        
        def mock_stats(strategy_id):
            stats = MagicMock()
            stats.total_pnl = 50.25
            return stats
        
        mock_strategy_runner.calculate_strategy_stats = mock_stats
        
        response = await command_handler.process_command("123", "list", [])
        
        assert "Strategies" in response
        assert "Test Strategy" in response
        assert "BTCUSDT" in response
        assert "$50.25" in response
    
    @pytest.mark.asyncio
    async def test_list_command_empty(self, command_handler, mock_strategy_runner):
        """Test /list command with no strategies."""
        mock_strategy_runner.list_strategies.return_value = []
        
        response = await command_handler.process_command("123", "list", [])
        
        assert "No strategies registered" in response
    
    @pytest.mark.asyncio
    async def test_list_command_many_strategies(self, command_handler, mock_strategy_runner, mock_strategy_summary):
        """Test /list command with many strategies (should limit to 10)."""
        strategies = [
            StrategySummary(**{**mock_strategy_summary.model_dump(), "id": f"strategy-{i}"})
            for i in range(15)
        ]
        mock_strategy_runner.list_strategies.return_value = strategies
        
        def mock_stats(strategy_id):
            stats = MagicMock()
            stats.total_pnl = 0.0
            return stats
        
        mock_strategy_runner.calculate_strategy_stats = mock_stats
        
        response = await command_handler.process_command("123", "list", [])
        
        assert "and 5 more" in response


class TestStartStrategyCommand:
    """Test /start_strategy command."""
    
    @pytest.mark.asyncio
    async def test_start_strategy_success(self, command_handler, mock_strategy_runner, mock_strategy_summary):
        """Test /start_strategy command success."""
        mock_strategy_runner.start = AsyncMock(return_value=mock_strategy_summary)
        
        response = await command_handler.process_command("123", "start_strategy", ["test-strategy-123"])
        
        assert "Strategy Started" in response
        assert "Test Strategy" in response
        mock_strategy_runner.start.assert_called_once_with("test-strategy-123")
    
    @pytest.mark.asyncio
    async def test_start_strategy_not_found(self, command_handler, mock_strategy_runner):
        """Test /start_strategy with non-existent strategy."""
        mock_strategy_runner.start = AsyncMock(side_effect=StrategyNotFoundError("test-strategy-123"))
        
        response = await command_handler.process_command("123", "start_strategy", ["test-strategy-123"])
        
        assert "Strategy not found" in response
        assert "test-strategy-123" in response
    
    @pytest.mark.asyncio
    async def test_start_strategy_already_running(self, command_handler, mock_strategy_runner):
        """Test /start_strategy with already running strategy."""
        mock_strategy_runner.start = AsyncMock(side_effect=StrategyAlreadyRunningError("test-strategy-123"))
        
        response = await command_handler.process_command("123", "start_strategy", ["test-strategy-123"])
        
        assert "already running" in response
    
    @pytest.mark.asyncio
    async def test_start_strategy_no_args(self, command_handler):
        """Test /start_strategy without arguments."""
        response = await command_handler.process_command("123", "start_strategy", [])
        
        assert "Usage" in response
        assert "/start_strategy" in response
    
    @pytest.mark.asyncio
    async def test_start_command_alias(self, command_handler, mock_strategy_runner, mock_strategy_summary):
        """Test /start command alias for start_strategy."""
        mock_strategy_runner.start = AsyncMock(return_value=mock_strategy_summary)
        
        response = await command_handler.process_command("123", "start", ["test-strategy-123"])
        
        assert "Strategy Started" in response
        mock_strategy_runner.start.assert_called_once_with("test-strategy-123")


class TestStopStrategyCommand:
    """Test /stop_strategy command."""
    
    @pytest.mark.asyncio
    async def test_stop_strategy_success(self, command_handler, mock_strategy_runner, mock_strategy_summary, mock_strategy_stats):
        """Test /stop_strategy command success."""
        mock_strategy_runner.stop = AsyncMock(return_value=mock_strategy_summary)
        mock_strategy_runner.calculate_strategy_stats.return_value = mock_strategy_stats
        
        response = await command_handler.process_command("123", "stop_strategy", ["test-strategy-123"])
        
        assert "Strategy Stopped" in response
        assert "Final PnL" in response
        assert "$50.25" in response
        mock_strategy_runner.stop.assert_called_once_with("test-strategy-123")
    
    @pytest.mark.asyncio
    async def test_stop_strategy_not_found(self, command_handler, mock_strategy_runner):
        """Test /stop_strategy with non-existent strategy."""
        mock_strategy_runner.stop = AsyncMock(side_effect=StrategyNotFoundError("test-strategy-123"))
        
        response = await command_handler.process_command("123", "stop_strategy", ["test-strategy-123"])
        
        assert "Strategy not found" in response
    
    @pytest.mark.asyncio
    async def test_stop_strategy_not_running(self, command_handler, mock_strategy_runner):
        """Test /stop_strategy with not running strategy."""
        mock_strategy_runner.stop = AsyncMock(side_effect=StrategyNotRunningError("test-strategy-123"))
        
        response = await command_handler.process_command("123", "stop_strategy", ["test-strategy-123"])
        
        assert "not running" in response
    
    @pytest.mark.asyncio
    async def test_stop_strategy_no_args(self, command_handler):
        """Test /stop_strategy without arguments."""
        response = await command_handler.process_command("123", "stop_strategy", [])
        
        assert "Usage" in response
        assert "/stop_strategy" in response


class TestInfoCommand:
    """Test /info command."""
    
    @pytest.mark.asyncio
    async def test_info_command_success(self, command_handler, mock_strategy_runner, mock_strategy_summary, mock_strategy_stats):
        """Test /info command success."""
        mock_strategy_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_strategy_runner.calculate_strategy_stats.return_value = mock_strategy_stats
        
        response = await command_handler.process_command("123", "info", ["test-strategy-123"])
        
        assert "Strategy Info" in response
        assert "Test Strategy" in response
        assert "BTCUSDT" in response
        assert "Total PnL" in response
        assert "$50.25" in response
        assert "Total Trades: 10" in response
        assert "Win Rate: 70.0%" in response
    
    @pytest.mark.asyncio
    async def test_info_command_not_found(self, command_handler, mock_strategy_runner):
        """Test /info command with non-existent strategy."""
        mock_strategy_runner.list_strategies.return_value = []
        
        response = await command_handler.process_command("123", "info", ["non-existent"])
        
        assert "Strategy not found" in response
    
    @pytest.mark.asyncio
    async def test_info_command_no_args(self, command_handler):
        """Test /info command without arguments."""
        response = await command_handler.process_command("123", "info", [])
        
        assert "Usage" in response
        assert "/info" in response


class TestBalanceCommand:
    """Test /balance command."""
    
    @pytest.mark.asyncio
    async def test_balance_command_success(self, command_handler, mock_strategy_runner):
        """Test /balance command success."""
        mock_strategy_runner.client.futures_account_balance.return_value = 10000.0
        
        response = await command_handler.process_command("123", "balance", [])
        
        assert "Account Balance" in response
        assert "$10,000.00" in response
    
    @pytest.mark.asyncio
    async def test_balance_command_error(self, command_handler, mock_strategy_runner):
        """Test /balance command with error."""
        mock_strategy_runner.client.futures_account_balance.side_effect = Exception("API error")
        
        response = await command_handler.process_command("123", "balance", [])
        
        assert "Error getting balance" in response
    
    @pytest.mark.asyncio
    async def test_bal_command_alias(self, command_handler, mock_strategy_runner):
        """Test /bal command alias."""
        mock_strategy_runner.client.futures_account_balance.return_value = 5000.0
        
        response = await command_handler.process_command("123", "bal", [])
        
        assert "Account Balance" in response
        assert "$5,000.00" in response


class TestTradesCommand:
    """Test /trades command."""
    
    @pytest.mark.asyncio
    async def test_trades_command_with_strategy_id(self, command_handler, mock_strategy_runner):
        """Test /trades command with strategy ID."""
        from app.models.order import OrderResponse
        
        mock_trades = [
            OrderResponse(
                order_id="order1",
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.1,
                price=50000.0,
                realized_pnl=25.0,
                timestamp=datetime.now(timezone.utc),
            ),
            OrderResponse(
                order_id="order2",
                symbol="BTCUSDT",
                side="SELL",
                quantity=0.1,
                price=50100.0,
                realized_pnl=-5.0,
                timestamp=datetime.now(timezone.utc),
            ),
        ]
        
        mock_strategy_runner.get_trades.return_value = mock_trades
        
        response = await command_handler.process_command("123", "trades", ["test-strategy-123"])
        
        assert "Recent Trades" in response
        assert "BUY" in response
        assert "SELL" in response
        assert "$25.00" in response
    
    @pytest.mark.asyncio
    async def test_trades_command_all_trades(self, command_handler, mock_strategy_runner, mock_strategy_summary):
        """Test /trades command without strategy ID (all trades)."""
        from app.models.order import OrderResponse
        
        mock_strategy_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_strategy_runner.get_trades.return_value = [
            OrderResponse(
                order_id="order1",
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.1,
                price=50000.0,
                realized_pnl=25.0,
                timestamp=datetime.now(timezone.utc),
            ),
        ]
        
        response = await command_handler.process_command("123", "trades", [])
        
        assert "All Trades" in response
        assert "BTCUSDT" in response
    
    @pytest.mark.asyncio
    async def test_trades_command_no_trades(self, command_handler, mock_strategy_runner):
        """Test /trades command with no trades."""
        mock_strategy_runner.get_trades.return_value = []
        
        response = await command_handler.process_command("123", "trades", ["test-strategy-123"])
        
        assert "No trades" in response


class TestMessageSending:
    """Test message sending functionality."""
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, command_handler):
        """Test successful message sending."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await command_handler.send_message("123", "Test message")
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_send_message_disabled(self):
        """Test message sending when handler is disabled."""
        handler = TelegramCommandHandler(
            bot_token="test_token",
            strategy_runner=MagicMock(),
            enabled=False,
        )
        
        result = await handler.send_message("123", "Test message")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_message_error(self, command_handler):
        """Test message sending with error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Network error"))
            
            result = await command_handler.send_message("123", "Test message")
            
            assert result is False


class TestUpdateProcessing:
    """Test update processing and long polling."""
    
    @pytest.mark.asyncio
    async def test_get_updates_success(self, command_handler):
        """Test getting updates from Telegram."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "ok": True,
                "result": [
                    {
                        "update_id": 1,
                        "message": {
                            "chat": {"id": 123},
                            "text": "/help",
                        },
                    },
                ],
            }
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            updates = await command_handler.get_updates()
            
            assert updates["ok"] is True
            assert len(updates["result"]) == 1
    
    @pytest.mark.asyncio
    async def test_get_updates_error(self, command_handler):
        """Test getting updates with error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("Network error"))
            
            updates = await command_handler.get_updates()
            
            assert updates["ok"] is False
    
    @pytest.mark.asyncio
    async def test_process_updates_with_command(self, command_handler):
        """Test processing updates with a command."""
        with patch.object(command_handler, "get_updates") as mock_get_updates, \
             patch.object(command_handler, "send_message") as mock_send_message:
            
            mock_get_updates.return_value = {
                "ok": True,
                "result": [
                    {
                        "update_id": 1,
                        "message": {
                            "chat": {"id": "123"},
                            "text": "/help",
                        },
                    },
                ],
            }
            mock_send_message.return_value = True
            
            command_handler._running = True
            # Run for a short time then stop
            import asyncio
            task = asyncio.create_task(command_handler.process_updates())
            await asyncio.sleep(0.1)
            command_handler._running = False
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # Verify send_message was called
            assert mock_send_message.called


class TestHandlerLifecycle:
    """Test handler start/stop lifecycle."""
    
    def test_start_handler(self, command_handler):
        """Test starting the handler."""
        assert command_handler._running is False
        command_handler.start()
        assert command_handler._running is True
        assert command_handler._task is not None
    
    def test_start_handler_already_running(self, command_handler):
        """Test starting handler when already running."""
        command_handler.start()
        assert command_handler._running is True
        
        # Should not raise error
        command_handler.start()
        assert command_handler._running is True
    
    def test_stop_handler(self, command_handler):
        """Test stopping the handler."""
        command_handler.start()
        assert command_handler._running is True
        
        command_handler.stop()
        assert command_handler._running is False
    
    def test_stop_handler_not_running(self, command_handler):
        """Test stopping handler when not running."""
        assert command_handler._running is False
        # Should not raise error
        command_handler.stop()
        assert command_handler._running is False


class TestCommandFormatting:
    """Test message formatting."""
    
    def test_format_strategy_summary(self, command_handler, mock_strategy_summary):
        """Test strategy summary formatting."""
        formatted = command_handler._format_strategy_summary(mock_strategy_summary)
        
        assert "Test Strategy" in formatted
        assert "BTCUSDT" in formatted
        assert "scalping" in formatted
        assert "5x" in formatted
        assert "LONG" in formatted
        assert "$50,000.00" in formatted
        assert "$10.00" in formatted
    
    def test_format_strategy_summary_no_position(self, command_handler):
        """Test strategy summary formatting without position."""
        summary = StrategySummary(
            id="test-123",
            name="Test",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=None,
            params=StrategyParams(
                ema_fast=8,
                ema_slow=21,
                take_profit_pct=0.004,
                stop_loss_pct=0.002,
                interval_seconds=10,
                kline_interval="1m",
                enable_short=True,
                min_ema_separation=0.0002,
                enable_htf_bias=True,
                cooldown_candles=2,
                trailing_stop_enabled=False,
                trailing_stop_activation_pct=0.0,
                lookback_period=150,
                buy_zone_pct=0.2,
                sell_zone_pct=0.2,
                ema_fast_period=20,
                ema_slow_period=50,
                max_ema_spread_pct=0.005,
                max_atr_multiplier=2.0,
                rsi_period=14,
                rsi_oversold=40,
                rsi_overbought=60,
                tp_buffer_pct=0.001,
                sl_buffer_pct=0.002,
            ),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
            entry_price=None,
            current_price=None,
            position_size=None,
            position_side=None,
            unrealized_pnl=None,
            meta={},
        )
        
        formatted = command_handler._format_strategy_summary(summary)
        
        assert "Test" in formatted
        assert "BTCUSDT" in formatted
        # Should not have position info
        assert "Position:" not in formatted or "None" in formatted


