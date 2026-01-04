"""Notification service for sending alerts via Telegram."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
import httpx
from loguru import logger

from app.models.strategy import StrategySummary, StrategyState
from app.models.order import OrderResponse


class NotificationLevel(str, Enum):
    """Notification priority levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class NotificationType(str, Enum):
    """Types of notifications."""
    STRATEGY_STARTED = "STRATEGY_STARTED"
    STRATEGY_STOPPED = "STRATEGY_STOPPED"
    STRATEGY_ERROR = "STRATEGY_ERROR"
    PNL_THRESHOLD = "PNL_THRESHOLD"
    ORDER_EXECUTED = "ORDER_EXECUTED"
    CRITICAL_ERROR = "CRITICAL_ERROR"
    SERVER_RESTART = "SERVER_RESTART"
    DATABASE_CONNECTION_FAILED = "DATABASE_CONNECTION_FAILED"
    DATABASE_CONNECTION_RESTORED = "DATABASE_CONNECTION_RESTORED"


class TelegramNotifier:
    """Telegram bot notifier for trading strategy alerts."""
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        """Initialize Telegram notifier.
        
        Args:
            bot_token: Telegram bot token (from @BotFather)
            chat_id: Telegram chat ID to send messages to
            enabled: Whether notifications are enabled
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id)
        
        if self.enabled:
            self.base_url = f"https://api.telegram.org/bot{bot_token}"
            logger.info("Telegram notifications enabled")
        else:
            logger.info("Telegram notifications disabled (missing token or chat_id)")
            self.base_url = None
    
    async def send_message(
        self,
        message: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> bool:
        """Send a message to Telegram.
        
        Args:
            message: Message text to send
            parse_mode: Message parsing mode (HTML or Markdown)
            disable_notification: If True, send silently
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.enabled or not self.base_url:
            logger.debug("Telegram notifications disabled, skipping message")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_notification": disable_notification,
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                if result.get("ok"):
                    logger.debug(f"Telegram message sent successfully")
                    return True
                else:
                    logger.error(f"Telegram API error: {result.get('description', 'Unknown error')}")
                    return False
                    
        except httpx.TimeoutException:
            logger.error("Telegram API timeout while sending message")
            return False
        except httpx.HTTPError as e:
            logger.error(f"Telegram API HTTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False
    
    def format_strategy_message(
        self,
        notification_type: NotificationType,
        summary: StrategySummary,
        additional_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format a strategy notification message.
        
        Args:
            notification_type: Type of notification
            summary: Strategy summary
            additional_info: Additional information dict
            
        Returns:
            Formatted HTML message
        """
        additional_info = additional_info or {}
        
        # Base strategy info
        status_emoji = {
            StrategyState.running: "🟢",
            StrategyState.stopped: "🔴",
            StrategyState.error: "🔴",
        }.get(summary.status, "⚪")
        
        message = f"<b>{status_emoji} Strategy: {summary.name}</b>\n"
        message += f"<code>{summary.id[:8]}...</code>\n\n"
        
        message += f"📊 Symbol: <b>{summary.symbol}</b>\n"
        message += f"⚙️ Type: {summary.strategy_type.value}\n"
        message += f"📈 Leverage: {summary.leverage}x\n"
        
        # Add position info if available
        if summary.position_side:
            position_emoji = "⬆️" if summary.position_side == "LONG" else "⬇️"
            message += f"🎯 Position: {position_emoji} {summary.position_side}\n"
            if summary.entry_price:
                message += f"💰 Entry Price: ${summary.entry_price:,.4f}\n"
            if summary.current_price:
                message += f"💵 Current Price: ${summary.current_price:,.4f}\n"
            if summary.unrealized_pnl is not None:
                pnl_emoji = "📈" if summary.unrealized_pnl >= 0 else "📉"
                message += f"{pnl_emoji} Unrealized PnL: ${summary.unrealized_pnl:,.2f}\n"
        
        # Notification-specific content
        if notification_type == NotificationType.STRATEGY_STARTED:
            message += "\n✅ <b>Strategy Started</b>\n"
            if additional_info.get("reason"):
                message += f"Reason: {additional_info['reason']}\n"
        
        elif notification_type == NotificationType.STRATEGY_STOPPED:
            message += "\n⏹️ <b>Strategy Stopped</b>\n"
            if additional_info.get("reason"):
                message += f"Reason: {additional_info['reason']}\n"
            if additional_info.get("final_pnl") is not None:
                pnl = additional_info['final_pnl']
                pnl_emoji = "📈" if pnl >= 0 else "📉"
                message += f"{pnl_emoji} Final PnL: ${pnl:,.2f}\n"
        
        elif notification_type == NotificationType.STRATEGY_ERROR:
            message += "\n❌ <b>Strategy Error</b>\n"
            if additional_info.get("error"):
                error_msg = str(additional_info['error'])[:200]  # Truncate long errors
                message += f"Error: <code>{error_msg}</code>\n"
            if additional_info.get("error_type"):
                message += f"Type: {additional_info['error_type']}\n"
        
        elif notification_type == NotificationType.PNL_THRESHOLD:
            pnl = additional_info.get("pnl", 0)
            threshold = additional_info.get("threshold", 0)
            is_profit = pnl >= threshold
            pnl_emoji = "📈" if is_profit else "📉"
            direction = "Profit" if is_profit else "Loss"
            
            message += f"\n{pnl_emoji} <b>{direction} Threshold Reached</b>\n"
            message += f"Current PnL: <b>${pnl:,.2f}</b>\n"
            message += f"Threshold: ${threshold:,.2f}\n"
        
        elif notification_type == NotificationType.CRITICAL_ERROR:
            message += "\n🚨 <b>CRITICAL ERROR</b>\n"
            if additional_info.get("error"):
                error_msg = str(additional_info['error'])[:200]
                message += f"<code>{error_msg}</code>\n"
        
        elif notification_type == NotificationType.ORDER_EXECUTED:
            order_side = additional_info.get("side", "UNKNOWN")
            order_emoji = "🟢" if order_side == "BUY" else "🔴" if order_side == "SELL" else "📊"
            position_action = additional_info.get("position_action", "TRADE")  # OPEN, CLOSE, or TRADE
            executed_qty = additional_info.get("executed_qty", 0)
            price = additional_info.get("price", 0)
            exit_reason = additional_info.get("exit_reason")
            
            if position_action == "OPEN":
                position_type = "LONG" if order_side == "BUY" else "SHORT"
                message += f"\n{order_emoji} <b>OPEN {position_type} Position</b>\n"
            elif position_action == "CLOSE":
                message += f"\n{order_emoji} <b>CLOSE Position</b>\n"
                if exit_reason:
                    message += f"Reason: {exit_reason}\n"
            else:
                message += f"\n{order_emoji} <b>Trade Executed</b>\n"
            
            message += f"Side: <b>{order_side}</b>\n"
            message += f"Quantity: {executed_qty:.8f}\n"
            message += f"Price: ${price:,.8f}\n"
            if additional_info.get("notional"):
                message += f"Notional: ${additional_info['notional']:,.2f}\n"
            if additional_info.get("leverage"):
                message += f"Leverage: {additional_info['leverage']}x\n"
        
        # Add timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message += f"\n⏰ {timestamp}"
        
        return message
    
    async def notify_strategy_started(
        self,
        summary: StrategySummary,
        reason: Optional[str] = None,
    ) -> bool:
        """Send notification when a strategy starts.
        
        Args:
            summary: Strategy summary
            reason: Optional reason for starting
            
        Returns:
            True if notification was sent successfully
        """
        additional_info = {}
        if reason:
            additional_info["reason"] = reason
        
        message = self.format_strategy_message(
            NotificationType.STRATEGY_STARTED,
            summary,
            additional_info,
        )
        
        return await self.send_message(message)
    
    async def notify_strategy_stopped(
        self,
        summary: StrategySummary,
        reason: Optional[str] = None,
        final_pnl: Optional[float] = None,
    ) -> bool:
        """Send notification when a strategy stops.
        
        Args:
            summary: Strategy summary
            reason: Optional reason for stopping
            final_pnl: Final profit/loss if available
            
        Returns:
            True if notification was sent successfully
        """
        additional_info = {}
        if reason:
            additional_info["reason"] = reason
        if final_pnl is not None:
            additional_info["final_pnl"] = final_pnl
        
        message = self.format_strategy_message(
            NotificationType.STRATEGY_STOPPED,
            summary,
            additional_info,
        )
        
        return await self.send_message(message)
    
    async def notify_strategy_error(
        self,
        summary: StrategySummary,
        error: Exception,
        error_type: Optional[str] = None,
    ) -> bool:
        """Send notification when a strategy encounters an error.
        
        Args:
            summary: Strategy summary
            error: The exception that occurred
            error_type: Optional error type string
            
        Returns:
            True if notification was sent successfully
        """
        additional_info = {
            "error": str(error),
            "error_type": error_type or type(error).__name__,
        }
        
        message = self.format_strategy_message(
            NotificationType.STRATEGY_ERROR,
            summary,
            additional_info,
        )
        
        # Error notifications are more urgent
        return await self.send_message(message, disable_notification=False)
    
    async def notify_pnl_threshold(
        self,
        summary: StrategySummary,
        pnl: float,
        threshold: float,
    ) -> bool:
        """Send notification when PnL reaches a threshold.
        
        Args:
            summary: Strategy summary
            pnl: Current profit/loss
            threshold: Threshold that was reached
            
        Returns:
            True if notification was sent successfully
        """
        additional_info = {
            "pnl": pnl,
            "threshold": threshold,
        }
        
        message = self.format_strategy_message(
            NotificationType.PNL_THRESHOLD,
            summary,
            additional_info,
        )
        
        return await self.send_message(message)
    
    async def notify_critical_error(
        self,
        summary: Optional[StrategySummary],
        error: Exception,
        context: Optional[str] = None,
    ) -> bool:
        """Send notification for a critical error.
        
        Args:
            summary: Optional strategy summary (if error is strategy-specific)
            error: The exception that occurred
            context: Optional context about where the error occurred
            
        Returns:
            True if notification was sent successfully
        """
        if summary:
            message = self.format_strategy_message(
                NotificationType.CRITICAL_ERROR,
                summary,
                {"error": str(error), "context": context},
            )
        else:
            # System-level critical error
            message = f"🚨 <b>CRITICAL SYSTEM ERROR</b>\n\n"
            if context:
                message += f"Context: {context}\n\n"
            message += f"Error: <code>{str(error)[:200]}</code>\n"
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"\n⏰ {timestamp}"
        
        return await self.send_message(message, disable_notification=False)
    
    async def notify_server_restart(
        self,
        restored_strategies_count: int = 0,
        startup_errors: Optional[list[str]] = None,
    ) -> bool:
        """Send notification when server restarts.
        
        Args:
            restored_strategies_count: Number of strategies restored after restart
            startup_errors: Optional list of startup errors
            
        Returns:
            True if notification was sent successfully
        """
        message = f"🔄 <b>Server Restarted</b>\n\n"
        
        # Add restored strategies info
        if restored_strategies_count > 0:
            message += f"✅ Restored {restored_strategies_count} running strateg{'y' if restored_strategies_count == 1 else 'ies'}\n\n"
        else:
            message += f"ℹ️ No running strategies to restore\n\n"
        
        # Add startup errors if any
        if startup_errors:
            message += f"⚠️ <b>Startup Warnings:</b>\n"
            for error in startup_errors[:5]:  # Limit to 5 errors
                message += f"• {error[:100]}\n"  # Truncate long errors
            if len(startup_errors) > 5:
                message += f"• ... and {len(startup_errors) - 5} more\n"
            message += "\n"
        
        # Add timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message += f"⏰ {timestamp}"
        
        return await self.send_message(message, disable_notification=False)
    
    async def notify_database_connection_failed(
        self,
        error: Exception,
        retry_count: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> bool:
        """Send notification when database connection fails.
        
        Args:
            error: The database connection error
            retry_count: Current retry attempt number
            max_retries: Maximum number of retries
            
        Returns:
            True if notification was sent successfully
        """
        message = f"🚨 <b>Database Connection Failed</b>\n\n"
        
        # Add error details
        error_msg = str(error)[:300]  # Truncate long errors
        message += f"Error: <code>{error_msg}</code>\n\n"
        
        # Add retry info if available
        if retry_count is not None and max_retries is not None:
            message += f"Retry: {retry_count}/{max_retries}\n"
            if retry_count >= max_retries:
                message += f"⚠️ <b>Maximum retries reached!</b>\n"
        elif retry_count is not None:
            message += f"Retry attempt: {retry_count}\n"
        
        message += "\n⚠️ <b>Server may be operating in degraded mode</b>\n"
        message += "Some features may be unavailable until connection is restored.\n"
        
        # Add timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message += f"\n⏰ {timestamp}"
        
        return await self.send_message(message, disable_notification=False)
    
    async def notify_database_connection_restored(
        self,
        downtime_seconds: Optional[float] = None,
    ) -> bool:
        """Send notification when database connection is restored.
        
        Args:
            downtime_seconds: Optional downtime duration in seconds
            
        Returns:
            True if notification was sent successfully
        """
        message = f"✅ <b>Database Connection Restored</b>\n\n"
        
        if downtime_seconds is not None:
            if downtime_seconds < 60:
                downtime_str = f"{downtime_seconds:.1f} seconds"
            elif downtime_seconds < 3600:
                downtime_str = f"{downtime_seconds / 60:.1f} minutes"
            else:
                downtime_str = f"{downtime_seconds / 3600:.1f} hours"
            message += f"Downtime: {downtime_str}\n\n"
        
        message += "✅ All database features are now available.\n"
        
        # Add timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message += f"\n⏰ {timestamp}"
        
        return await self.send_message(message, disable_notification=False)
    
    async def notify_order_executed(
        self,
        summary: StrategySummary,
        order_response: OrderResponse,
        position_action: str = "TRADE",  # OPEN, CLOSE, or TRADE
        exit_reason: Optional[str] = None,
    ) -> bool:
        """Send notification when an order is successfully executed.
        
        Args:
            summary: Strategy summary
            order_response: OrderResponse from executed order
            position_action: Whether this opens, closes, or modifies a position
            exit_reason: Optional exit reason if closing position
            
        Returns:
            True if notification was sent successfully
        """
        additional_info = {
            "side": order_response.side,
            "executed_qty": order_response.executed_qty,
            "price": order_response.avg_price or order_response.price,
            "position_action": position_action,
            "exit_reason": exit_reason,
        }
        
        # Add optional fields if available
        if hasattr(order_response, 'notional_value') and order_response.notional_value:
            additional_info["notional"] = order_response.notional_value
        if hasattr(order_response, 'leverage') and order_response.leverage:
            additional_info["leverage"] = order_response.leverage
        
        message = self.format_strategy_message(
            NotificationType.ORDER_EXECUTED,
            summary,
            additional_info,
        )
        
        return await self.send_message(message)


class NotificationService:
    """High-level notification service that manages notifiers and thresholds."""
    
    def __init__(
        self,
        telegram_notifier: Optional[TelegramNotifier] = None,
        profit_threshold_usd: Optional[float] = None,
        loss_threshold_usd: Optional[float] = None,
    ) -> None:
        """Initialize notification service.
        
        Args:
            telegram_notifier: Telegram notifier instance
            profit_threshold_usd: Profit threshold in USD to trigger notification
            loss_threshold_usd: Loss threshold in USD to trigger notification (negative value)
        """
        self.telegram = telegram_notifier
        self.profit_threshold = profit_threshold_usd
        self.loss_threshold = loss_threshold_usd
        
        # Track notified thresholds per strategy to avoid spam
        self._notified_thresholds: Dict[str, Dict[str, float]] = {}
    
    async def notify_strategy_started(
        self,
        summary: StrategySummary,
        reason: Optional[str] = None,
    ) -> None:
        """Notify that a strategy started."""
        if self.telegram:
            await self.telegram.notify_strategy_started(summary, reason)
        # Reset threshold tracking for this strategy
        self._notified_thresholds.pop(summary.id, None)
    
    async def notify_strategy_stopped(
        self,
        summary: StrategySummary,
        reason: Optional[str] = None,
        final_pnl: Optional[float] = None,
    ) -> None:
        """Notify that a strategy stopped."""
        if self.telegram:
            await self.telegram.notify_strategy_stopped(summary, reason, final_pnl)
        # Clear threshold tracking
        self._notified_thresholds.pop(summary.id, None)
    
    async def notify_strategy_error(
        self,
        summary: StrategySummary,
        error: Exception,
        error_type: Optional[str] = None,
    ) -> None:
        """Notify that a strategy encountered an error."""
        if self.telegram:
            await self.telegram.notify_strategy_error(summary, error, error_type)
    
    async def notify_critical_error(
        self,
        summary: Optional[StrategySummary],
        error: Exception,
        context: Optional[str] = None,
    ) -> None:
        """Notify about a critical system error."""
        if self.telegram:
            await self.telegram.notify_critical_error(summary, error, context)
    
    async def check_and_notify_pnl_threshold(
        self,
        summary: StrategySummary,
        pnl: float,
    ) -> None:
        """Check PnL against thresholds and notify if reached.
        
        Only notifies once per threshold to avoid spam.
        
        Args:
            summary: Strategy summary
            pnl: Current profit/loss
        """
        strategy_id = summary.id
        
        # Track notified thresholds
        if strategy_id not in self._notified_thresholds:
            self._notified_thresholds[strategy_id] = {}
        
        notified = self._notified_thresholds[strategy_id]
        
        # Check profit threshold
        if self.profit_threshold and pnl >= self.profit_threshold:
            # Check if we already notified for this threshold
            last_notified_profit = notified.get("profit", float('-inf'))
            if pnl > last_notified_profit:
                if self.telegram:
                    await self.telegram.notify_pnl_threshold(
                        summary,
                        pnl,
                        self.profit_threshold,
                    )
                notified["profit"] = pnl
        
        # Check loss threshold (loss_threshold should be negative)
        if self.loss_threshold and pnl <= self.loss_threshold:
            # Check if we already notified for this threshold
            last_notified_loss = notified.get("loss", float('inf'))
            if pnl < last_notified_loss:
                if self.telegram:
                    await self.telegram.notify_pnl_threshold(
                        summary,
                        pnl,
                        self.loss_threshold,
                    )
                notified["loss"] = pnl
    
    async def notify_server_restart(
        self,
        restored_strategies_count: int = 0,
        startup_errors: Optional[list[str]] = None,
    ) -> None:
        """Notify that the server has restarted."""
        if self.telegram:
            await self.telegram.notify_server_restart(restored_strategies_count, startup_errors)
    
    async def notify_database_connection_failed(
        self,
        error: Exception,
        retry_count: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        """Notify that database connection has failed."""
        if self.telegram:
            await self.telegram.notify_database_connection_failed(error, retry_count, max_retries)
    
    async def notify_database_connection_restored(
        self,
        downtime_seconds: Optional[float] = None,
    ) -> None:
        """Notify that database connection has been restored."""
        if self.telegram:
            await self.telegram.notify_database_connection_restored(downtime_seconds)
    
    async def notify_order_executed(
        self,
        summary: StrategySummary,
        order_response: OrderResponse,
        position_action: str = "TRADE",  # OPEN, CLOSE, or TRADE
        exit_reason: Optional[str] = None,
    ) -> None:
        """Notify that an order was successfully executed.
        
        Args:
            summary: Strategy summary
            order_response: OrderResponse from executed order
            position_action: Whether this opens, closes, or modifies a position
            exit_reason: Optional exit reason if closing position
        """
        if self.telegram:
            await self.telegram.notify_order_executed(
                summary,
                order_response,
                position_action,
                exit_reason,
            )

