"""Notification service for sending alerts via Telegram."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, TYPE_CHECKING
from uuid import UUID
import httpx
from loguru import logger

from app.models.strategy import StrategySummary, StrategyState
from app.models.order import OrderResponse

if TYPE_CHECKING:
    from app.services.fcm_notifier import FCMNotifier


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
    # Risk enforcement notifications
    RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"
    ORDER_BLOCKED_BY_RISK = "ORDER_BLOCKED_BY_RISK"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    ORDER_SIZE_REDUCED = "ORDER_SIZE_REDUCED"
    # Risk warnings (approaching limits - 80% threshold)
    DAILY_LOSS_LIMIT_WARNING = "DAILY_LOSS_LIMIT_WARNING"
    WEEKLY_LOSS_LIMIT_WARNING = "WEEKLY_LOSS_LIMIT_WARNING"
    DRAWDOWN_LIMIT_WARNING = "DRAWDOWN_LIMIT_WARNING"
    EXPOSURE_LIMIT_WARNING = "EXPOSURE_LIMIT_WARNING"
    # Risk breaches (limits exceeded)
    DAILY_LOSS_LIMIT_BREACH = "DAILY_LOSS_LIMIT_BREACH"
    WEEKLY_LOSS_LIMIT_BREACH = "WEEKLY_LOSS_LIMIT_BREACH"
    DRAWDOWN_LIMIT_BREACH = "DRAWDOWN_LIMIT_BREACH"
    EXPOSURE_LIMIT_BREACH = "EXPOSURE_LIMIT_BREACH"


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
        
        elif notification_type == NotificationType.ORDER_BLOCKED_BY_RISK:
            message += "\n🚫 <b>Order BLOCKED by Risk</b>\n"
            if additional_info.get("reason"):
                message += f"Reason: {additional_info['reason']}\n"
            if additional_info.get("limit_type"):
                message += f"Limit Type: {additional_info['limit_type']}\n"
            if additional_info.get("current_value") is not None and additional_info.get("limit_value") is not None:
                message += f"Current: ${additional_info['current_value']:,.2f}\n"
                message += f"Limit: ${additional_info['limit_value']:,.2f}\n"
            if additional_info.get("symbol"):
                message += f"Symbol: {additional_info['symbol']}\n"
            if additional_info.get("account_id"):
                message += f"Account: {additional_info['account_id']}\n"
        
        elif notification_type == NotificationType.CIRCUIT_BREAKER_TRIGGERED:
            message += "\n⛔ <b>Circuit Breaker TRIGGERED</b>\n"
            if additional_info.get("breaker_type"):
                message += f"Type: {additional_info['breaker_type']}\n"
            if additional_info.get("reason"):
                message += f"Reason: {additional_info['reason']}\n"
            if additional_info.get("account_id"):
                message += f"Account: {additional_info['account_id']}\n"
            if additional_info.get("strategies_affected"):
                message += f"Strategies Affected: {additional_info['strategies_affected']}\n"
        
        elif notification_type == NotificationType.ORDER_SIZE_REDUCED:
            message += "\n⚠️ <b>Order Size REDUCED</b>\n"
            if additional_info.get("original_size") and additional_info.get("reduced_size"):
                message += f"Original: {additional_info['original_size']:.8f}\n"
                message += f"Reduced: {additional_info['reduced_size']:.8f}\n"
            if additional_info.get("reason"):
                message += f"Reason: {additional_info['reason']}\n"
        
        elif notification_type in [
            NotificationType.DAILY_LOSS_LIMIT_WARNING,
            NotificationType.WEEKLY_LOSS_LIMIT_WARNING,
            NotificationType.DRAWDOWN_LIMIT_WARNING,
            NotificationType.EXPOSURE_LIMIT_WARNING
        ]:
            limit_name = notification_type.value.replace("_LIMIT_WARNING", "").replace("_", " ").title()
            message += f"\n⚠️ <b>{limit_name} Warning</b>\n"
            message += "Approaching limit threshold (80%)\n\n"
            
            if additional_info.get("current_value") is not None and additional_info.get("limit_value") is not None:
                current = abs(additional_info['current_value'])
                limit = abs(additional_info['limit_value'])
                percentage = (current / limit * 100) if limit != 0 else 0
                remaining = limit - current
                
                if "LOSS" in notification_type.value:
                    message += f"Current Loss: <b>${current:,.2f}</b> ({percentage:.1f}%)\n"
                    message += f"Limit: ${limit:,.2f}\n"
                    message += f"Remaining: ${remaining:,.2f} before breach\n"
                elif "DRAWDOWN" in notification_type.value:
                    message += f"Current Drawdown: <b>{current:.2f}%</b> ({percentage:.1f}%)\n"
                    message += f"Limit: {limit:.2f}%\n"
                    message += f"Remaining: {remaining:.2f}% before breach\n"
                else:  # EXPOSURE
                    message += f"Current Exposure: <b>${current:,.2f}</b> ({percentage:.1f}%)\n"
                    message += f"Limit: ${limit:,.2f}\n"
                    message += f"Remaining: ${remaining:,.2f} before breach\n"
            
            if additional_info.get("account_id"):
                message += f"\nAccount: {additional_info['account_id']}\n"
            if additional_info.get("strategy_id"):
                message += f"Strategy: {additional_info.get('strategy_name', additional_info['strategy_id'][:8])}...\n"
            
            message += "\n⚠️ <b>Action Required:</b> Monitor closely. Limit may be breached soon."
        
        elif notification_type in [
            NotificationType.DAILY_LOSS_LIMIT_BREACH,
            NotificationType.WEEKLY_LOSS_LIMIT_BREACH,
            NotificationType.DRAWDOWN_LIMIT_BREACH,
            NotificationType.EXPOSURE_LIMIT_BREACH
        ]:
            limit_name = notification_type.value.replace("_LIMIT_BREACH", "").replace("_", " ").title()
            message += f"\n🚨 <b>{limit_name} BREACHED</b>\n"
            message += "Risk limit has been exceeded!\n\n"
            
            if additional_info.get("current_value") is not None and additional_info.get("limit_value") is not None:
                current = abs(additional_info['current_value'])
                limit = abs(additional_info['limit_value'])
                exceeded_by = current - limit
                percentage = (current / limit * 100) if limit != 0 else 0
                
                if "LOSS" in notification_type.value:
                    message += f"Current Loss: <b>${current:,.2f}</b> ({percentage:.1f}%)\n"
                    message += f"Limit: ${limit:,.2f}\n"
                    message += f"Exceeded by: <b>${exceeded_by:,.2f}</b>\n"
                elif "DRAWDOWN" in notification_type.value:
                    message += f"Current Drawdown: <b>{current:.2f}%</b> ({percentage:.1f}%)\n"
                    message += f"Limit: {limit:.2f}%\n"
                    message += f"Exceeded by: <b>{exceeded_by:.2f}%</b>\n"
                else:  # EXPOSURE
                    message += f"Current Exposure: <b>${current:,.2f}</b> ({percentage:.1f}%)\n"
                    message += f"Limit: ${limit:,.2f}\n"
                    message += f"Exceeded by: <b>${exceeded_by:,.2f}</b>\n"
            
            if additional_info.get("account_id"):
                message += f"\nAccount: <b>{additional_info['account_id']}</b>\n"
            if additional_info.get("strategy_id"):
                strategy_name = additional_info.get('strategy_name', 'Unknown')
                message += f"Strategy: <b>{strategy_name}</b>\n"
                message += f"Strategy ID: <code>{additional_info['strategy_id']}</code>\n"
            
            action_taken = additional_info.get("action_taken", "Trading blocked")
            message += f"\n🛑 <b>Action Taken:</b> {action_taken}\n"
            
            if additional_info.get("breach_type"):
                breach_type = additional_info['breach_type']
                if breach_type == "(account)":
                    message += "⚠️ <b>Account-level breach:</b> All strategies on this account are affected.\n"
                elif breach_type == "(strategy)":
                    message += "⚠️ <b>Strategy-level breach:</b> Only this strategy is affected.\n"
        
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
    
    async def notify_order_blocked_by_risk(
        self,
        summary: StrategySummary,
        reason: str,
        account_id: str,
        limit_type: Optional[str] = None,
        current_value: Optional[float] = None,
        limit_value: Optional[float] = None,
        symbol: Optional[str] = None,
    ) -> bool:
        """Send notification when an order is blocked by risk limits.
        
        Args:
            summary: Strategy summary
            reason: Reason why order was blocked
            account_id: Account ID
            limit_type: Type of limit that was exceeded (e.g., "PORTFOLIO_EXPOSURE")
            current_value: Current value that exceeded limit
            limit_value: Limit value that was exceeded
            symbol: Trading symbol
            
        Returns:
            True if notification was sent successfully
        """
        additional_info = {
            "reason": reason,
            "account_id": account_id,
            "limit_type": limit_type,
            "current_value": current_value,
            "limit_value": limit_value,
            "symbol": symbol or summary.symbol,
        }
        
        message = self.format_strategy_message(
            NotificationType.ORDER_BLOCKED_BY_RISK,
            summary,
            additional_info,
        )
        
        return await self.send_message(message, disable_notification=False)
    
    async def notify_circuit_breaker_triggered(
        self,
        account_id: str,
        breaker_type: str,
        reason: str,
        strategies_affected: Optional[list[str]] = None,
        summary: Optional[StrategySummary] = None,
    ) -> bool:
        """Send notification when circuit breaker is triggered.
        
        Args:
            account_id: Account ID
            breaker_type: Type of circuit breaker (e.g., "consecutive_losses")
            reason: Reason why circuit breaker triggered
            strategies_affected: List of strategy IDs affected
            summary: Optional strategy summary if single strategy affected
            
        Returns:
            True if notification was sent successfully
        """
        if summary:
            # Single strategy affected
            additional_info = {
                "breaker_type": breaker_type,
                "reason": reason,
                "account_id": account_id,
            }
            message = self.format_strategy_message(
                NotificationType.CIRCUIT_BREAKER_TRIGGERED,
                summary,
                additional_info,
            )
        else:
            # Account-level or multiple strategies
            message = f"⛔ <b>Circuit Breaker TRIGGERED</b>\n\n"
            message += f"Account: <b>{account_id}</b>\n"
            message += f"Type: {breaker_type}\n"
            message += f"Reason: {reason}\n"
            if strategies_affected:
                message += f"Strategies Affected: {len(strategies_affected)}\n"
                if len(strategies_affected) <= 5:
                    for sid in strategies_affected:
                        message += f"• {sid[:8]}...\n"
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"\n⏰ {timestamp}"
        
        return await self.send_message(message, disable_notification=False)
    
    async def notify_order_size_reduced(
        self,
        summary: StrategySummary,
        original_size: float,
        reduced_size: float,
        reason: str,
    ) -> bool:
        """Send notification when order size is reduced due to risk limits.
        
        Args:
            summary: Strategy summary
            original_size: Original order size
            reduced_size: Reduced order size
            reason: Reason why size was reduced
            
        Returns:
            True if notification was sent successfully
        """
        additional_info = {
            "original_size": original_size,
            "reduced_size": reduced_size,
            "reason": reason,
        }
        
        message = self.format_strategy_message(
            NotificationType.ORDER_SIZE_REDUCED,
            summary,
            additional_info,
        )
        
        return await self.send_message(message)
    
    async def notify_risk_warning(
        self,
        warning_type: NotificationType,
        account_id: str,
        current_value: float,
        limit_value: float,
        strategy_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
        summary: Optional[StrategySummary] = None,
    ) -> bool:
        """Send notification for a risk warning (approaching limit).
        
        Args:
            warning_type: Type of warning (e.g., DAILY_LOSS_LIMIT_WARNING)
            account_id: Account ID
            current_value: Current value
            limit_value: Limit value
            strategy_id: Optional strategy ID
            strategy_name: Optional strategy name
            summary: Optional strategy summary
            
        Returns:
            True if notification was sent successfully
        """
        if summary:
            additional_info = {
                "current_value": current_value,
                "limit_value": limit_value,
                "account_id": account_id,
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
            }
            message = self.format_strategy_message(warning_type, summary, additional_info)
        else:
            # Account-level warning
            limit_name = warning_type.value.replace("_LIMIT_WARNING", "").replace("_", " ").title()
            message = f"⚠️ <b>{limit_name} Warning</b>\n\n"
            message += f"Account: <b>{account_id}</b>\n"
            message += f"Approaching limit threshold (80%)\n\n"
            
            current = abs(current_value)
            limit = abs(limit_value)
            percentage = (current / limit * 100) if limit != 0 else 0
            remaining = limit - current
            
            if "LOSS" in warning_type.value:
                message += f"Current Loss: <b>${current:,.2f}</b> ({percentage:.1f}%)\n"
                message += f"Limit: ${limit:,.2f}\n"
                message += f"Remaining: ${remaining:,.2f} before breach\n"
            elif "DRAWDOWN" in warning_type.value:
                message += f"Current Drawdown: <b>{current:.2f}%</b> ({percentage:.1f}%)\n"
                message += f"Limit: {limit:.2f}%\n"
                message += f"Remaining: {remaining:.2f}% before breach\n"
            else:  # EXPOSURE
                message += f"Current Exposure: <b>${current:,.2f}</b> ({percentage:.1f}%)\n"
                message += f"Limit: ${limit:,.2f}\n"
                message += f"Remaining: ${remaining:,.2f} before breach\n"
            
            if strategy_id:
                message += f"\nStrategy: {strategy_name or strategy_id[:8]}...\n"
            
            message += "\n⚠️ <b>Action Required:</b> Monitor closely. Limit may be breached soon."
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"\n\n⏰ {timestamp}"
        
        return await self.send_message(message)
    
    async def notify_risk_breach(
        self,
        breach_type: NotificationType,
        account_id: str,
        current_value: float,
        limit_value: float,
        breach_level: str = "account",
        strategy_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
        action_taken: str = "Trading blocked",
        summary: Optional[StrategySummary] = None,
    ) -> bool:
        """Send notification for a risk breach (limit exceeded).
        
        Args:
            breach_type: Type of breach (e.g., DAILY_LOSS_LIMIT_BREACH)
            account_id: Account ID
            current_value: Current value that exceeded limit
            limit_value: Limit value
            breach_level: "account" or "strategy"
            strategy_id: Optional strategy ID
            strategy_name: Optional strategy name
            action_taken: Action taken
            summary: Optional strategy summary
            
        Returns:
            True if notification was sent successfully
        """
        if summary:
            additional_info = {
                "current_value": current_value,
                "limit_value": limit_value,
                "account_id": account_id,
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "action_taken": action_taken,
                "breach_type": f"({breach_level})",
            }
            message = self.format_strategy_message(breach_type, summary, additional_info)
        else:
            # Account-level breach
            limit_name = breach_type.value.replace("_LIMIT_BREACH", "").replace("_", " ").title()
            message = f"🚨 <b>{limit_name} BREACHED</b>\n\n"
            message += f"Account: <b>{account_id}</b>\n"
            message += f"Risk limit has been exceeded!\n\n"
            
            current = abs(current_value)
            limit = abs(limit_value)
            exceeded_by = current - limit
            percentage = (current / limit * 100) if limit != 0 else 0
            
            if "LOSS" in breach_type.value:
                message += f"Current Loss: <b>${current:,.2f}</b> ({percentage:.1f}%)\n"
                message += f"Limit: ${limit:,.2f}\n"
                message += f"Exceeded by: <b>${exceeded_by:,.2f}</b>\n"
            elif "DRAWDOWN" in breach_type.value:
                message += f"Current Drawdown: <b>{current:.2f}%</b> ({percentage:.1f}%)\n"
                message += f"Limit: {limit:.2f}%\n"
                message += f"Exceeded by: <b>{exceeded_by:.2f}%</b>\n"
            else:  # EXPOSURE
                message += f"Current Exposure: <b>${current:,.2f}</b> ({percentage:.1f}%)\n"
                message += f"Limit: ${limit:,.2f}\n"
                message += f"Exceeded by: <b>${exceeded_by:,.2f}</b>\n"
            
            if strategy_id:
                message += f"\nStrategy: <b>{strategy_name or 'Unknown'}</b>\n"
                message += f"Strategy ID: <code>{strategy_id}</code>\n"
            
            message += f"\n🛑 <b>Action Taken:</b> {action_taken}\n"
            
            if breach_level == "account":
                message += "⚠️ <b>Account-level breach:</b> All strategies on this account are affected.\n"
            elif breach_level == "strategy":
                message += "⚠️ <b>Strategy-level breach:</b> Only this strategy is affected.\n"
            
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"\n⏰ {timestamp}"
        
        return await self.send_message(message, disable_notification=False)


class NotificationService:
    """High-level notification service that manages notifiers and thresholds."""
    
    def __init__(
        self,
        telegram_notifier: Optional[TelegramNotifier] = None,
        fcm_notifier: Optional["FCMNotifier"] = None,
        profit_threshold_usd: Optional[float] = None,
        loss_threshold_usd: Optional[float] = None,
    ) -> None:
        """Initialize notification service.
        
        Args:
            telegram_notifier: Telegram notifier instance
            fcm_notifier: FCM notifier instance for mobile push notifications
            profit_threshold_usd: Profit threshold in USD to trigger notification
            loss_threshold_usd: Loss threshold in USD to trigger notification (negative value)
        """
        self.telegram = telegram_notifier
        self.fcm = fcm_notifier
        self.profit_threshold = profit_threshold_usd
        self.loss_threshold = loss_threshold_usd
        
        # Track notified thresholds per strategy to avoid spam
        self._notified_thresholds: Dict[str, Dict[str, float]] = {}
    
    async def _send_fcm_notification(
        self,
        user_id: Optional["UUID"],
        notification_method: str,
        *args,
        **kwargs,
    ) -> None:
        """Helper to send FCM notifications with fresh async session.
        
        Args:
            user_id: User UUID
            notification_method: Name of the FCM notifier method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
        """
        if not self.fcm or not user_id:
            return
        
        try:
            from app.core.database import get_async_db
            
            async for db in get_async_db():
                try:
                    method = getattr(self.fcm, notification_method)
                    await method(user_id, *args, db=db, **kwargs)
                except Exception as e:
                    logger.error(f"Failed to send FCM notification ({notification_method}): {e}")
                finally:
                    break
        except Exception as e:
            logger.error(f"Failed to get async session for FCM notification: {e}")
    
    async def notify_strategy_started(
        self,
        summary: StrategySummary,
        reason: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify that a strategy started."""
        if self.telegram:
            await self.telegram.notify_strategy_started(summary, reason)
        
        # FCM notification
        if self.fcm and user_id:
            asyncio.create_task(
                self._send_fcm_notification(user_id, "notify_strategy_started", summary, reason=reason)
            )
        
        # Reset threshold tracking for this strategy
        self._notified_thresholds.pop(summary.id, None)
    
    async def notify_strategy_stopped(
        self,
        summary: StrategySummary,
        reason: Optional[str] = None,
        final_pnl: Optional[float] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify that a strategy stopped."""
        if self.telegram:
            await self.telegram.notify_strategy_stopped(summary, reason, final_pnl)
        
        # FCM notification
        if self.fcm and user_id:
            asyncio.create_task(
                self._send_fcm_notification(
                    user_id, "notify_strategy_stopped", summary, 
                    reason=reason, final_pnl=final_pnl
                )
            )
        
        # Clear threshold tracking
        self._notified_thresholds.pop(summary.id, None)
    
    async def notify_strategy_error(
        self,
        summary: StrategySummary,
        error: Exception,
        error_type: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify that a strategy encountered an error."""
        if self.telegram:
            await self.telegram.notify_strategy_error(summary, error, error_type)
        
        # FCM notification
        if self.fcm and user_id:
            asyncio.create_task(
                self._send_fcm_notification(user_id, "notify_strategy_error", summary, error)
            )
    
    async def notify_critical_error(
        self,
        summary: Optional[StrategySummary],
        error: Exception,
        context: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify about a critical system error."""
        if self.telegram:
            await self.telegram.notify_critical_error(summary, error, context)
        
        # FCM notification for critical errors
        if self.fcm and user_id and summary:
            asyncio.create_task(
                self._send_fcm_notification(user_id, "notify_strategy_error", summary, error)
            )
    
    async def check_and_notify_pnl_threshold(
        self,
        summary: StrategySummary,
        pnl: float,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Check PnL against thresholds and notify if reached.
        
        Only notifies once per threshold to avoid spam.
        
        Args:
            summary: Strategy summary
            pnl: Current profit/loss
            user_id: User UUID for FCM notifications
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
                # FCM notification
                if self.fcm and user_id:
                    asyncio.create_task(
                        self._send_fcm_notification(
                            user_id, "notify_pnl_threshold", summary, pnl, self.profit_threshold
                        )
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
                # FCM notification
                if self.fcm and user_id:
                    asyncio.create_task(
                        self._send_fcm_notification(
                            user_id, "notify_pnl_threshold", summary, pnl, self.loss_threshold
                        )
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
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify that an order was successfully executed.
        
        Args:
            summary: Strategy summary
            order_response: OrderResponse from executed order
            position_action: Whether this opens, closes, or modifies a position
            exit_reason: Optional exit reason if closing position
            user_id: User UUID for FCM notifications
        """
        if self.telegram:
            await self.telegram.notify_order_executed(
                summary,
                order_response,
                position_action,
                exit_reason,
            )
        
        # FCM notification for trade execution
        if self.fcm and user_id:
            pnl = float(order_response.realized_pnl) if order_response.realized_pnl else None
            asyncio.create_task(
                self._send_fcm_notification(
                    user_id, "notify_trade_executed",
                    trade_id=str(order_response.order_id),
                    strategy_id=summary.id,
                    strategy_name=summary.name,
                    symbol=order_response.symbol,
                    side=order_response.side,
                    quantity=str(order_response.executed_qty),
                    price=str(order_response.avg_price or order_response.price),
                    pnl=pnl,
                )
            )
    
    async def notify_order_blocked_by_risk(
        self,
        summary: StrategySummary,
        reason: str,
        account_id: str,
        limit_type: Optional[str] = None,
        current_value: Optional[float] = None,
        limit_value: Optional[float] = None,
        symbol: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify that an order was blocked by risk limits.
        
        Args:
            summary: Strategy summary
            reason: Reason why order was blocked
            account_id: Account ID
            limit_type: Type of limit that was exceeded
            current_value: Current value that exceeded limit
            limit_value: Limit value that was exceeded
            symbol: Trading symbol
            user_id: User UUID for FCM notifications
        """
        if self.telegram:
            await self.telegram.notify_order_blocked_by_risk(
                summary, reason, account_id, limit_type, current_value, limit_value, symbol
            )
        
        # FCM notification for risk alert
        if self.fcm and user_id:
            asyncio.create_task(
                self._send_fcm_notification(
                    user_id, "notify_risk_alert",
                    alert_type=limit_type or "order_blocked",
                    account_id=account_id,
                    message=reason,
                    current_value=current_value,
                    limit_value=limit_value,
                )
            )
    
    async def notify_circuit_breaker_triggered(
        self,
        account_id: str,
        breaker_type: str,
        reason: str,
        strategies_affected: Optional[list[str]] = None,
        summary: Optional[StrategySummary] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify that a circuit breaker was triggered.
        
        Args:
            account_id: Account ID
            breaker_type: Type of circuit breaker
            reason: Reason why circuit breaker triggered
            strategies_affected: List of strategy IDs affected
            summary: Optional strategy summary if single strategy affected
            user_id: User UUID for FCM notifications
        """
        if self.telegram:
            await self.telegram.notify_circuit_breaker_triggered(
                account_id, breaker_type, reason, strategies_affected, summary
            )
        
        # FCM notification for circuit breaker
        if self.fcm and user_id:
            asyncio.create_task(
                self._send_fcm_notification(
                    user_id, "notify_risk_alert",
                    alert_type="circuit_breaker",
                    account_id=account_id,
                    message=f"Circuit breaker triggered: {reason}",
                )
            )
    
    async def notify_risk_warning(
        self,
        warning_type: NotificationType,
        account_id: str,
        current_value: float,
        limit_value: float,
        strategy_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
        summary: Optional[StrategySummary] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify about risk warning (approaching limit).
        
        Args:
            warning_type: Type of warning
            account_id: Account ID
            current_value: Current value
            limit_value: Limit value
            strategy_id: Optional strategy ID
            strategy_name: Optional strategy name
            summary: Optional strategy summary
            user_id: User UUID for FCM notifications
        """
        if self.telegram:
            await self.telegram.notify_risk_warning(
                warning_type, account_id, current_value, limit_value,
                strategy_id, strategy_name, summary
            )
        
        # FCM notification for risk warning
        if self.fcm and user_id:
            asyncio.create_task(
                self._send_fcm_notification(
                    user_id, "notify_risk_alert",
                    alert_type=warning_type.value.lower(),
                    account_id=account_id,
                    message=f"Risk warning: {warning_type.value}",
                    current_value=current_value,
                    limit_value=limit_value,
                )
            )
    
    async def notify_risk_breach(
        self,
        breach_type: NotificationType,
        account_id: str,
        current_value: float,
        limit_value: float,
        breach_level: str = "account",
        strategy_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
        action_taken: str = "Trading blocked",
        summary: Optional[StrategySummary] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Notify about risk breach (limit exceeded).
        
        Args:
            breach_type: Type of breach
            account_id: Account ID
            current_value: Current value that exceeded limit
            limit_value: Limit value
            breach_level: "account" or "strategy"
            strategy_id: Optional strategy ID
            strategy_name: Optional strategy name
            action_taken: Action taken
            summary: Optional strategy summary
            user_id: User UUID for FCM notifications
        """
        if self.telegram:
            await self.telegram.notify_risk_breach(
                breach_type, account_id, current_value, limit_value,
                breach_level, strategy_id, strategy_name, action_taken, summary
            )
        
        # FCM notification for risk breach
        if self.fcm and user_id:
            asyncio.create_task(
                self._send_fcm_notification(
                    user_id, "notify_risk_alert",
                    alert_type=breach_type.value.lower(),
                    account_id=account_id,
                    message=f"Risk limit breached: {action_taken}",
                    current_value=current_value,
                    limit_value=limit_value,
                )
            )

