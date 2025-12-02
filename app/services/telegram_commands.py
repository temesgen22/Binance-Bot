"""Telegram command handler for receiving and processing user commands."""

from __future__ import annotations

import asyncio
from typing import Optional, Dict, Any
import httpx
from loguru import logger

from app.models.strategy import StrategySummary, StrategyState
from app.services.strategy_runner import StrategyRunner
from app.core.exceptions import (
    StrategyNotFoundError,
    StrategyAlreadyRunningError,
    StrategyNotRunningError,
)


class TelegramCommandHandler:
    """Handle incoming Telegram commands and messages."""
    
    def __init__(
        self,
        bot_token: str,
        strategy_runner: StrategyRunner,
        enabled: bool = True,
    ) -> None:
        """Initialize Telegram command handler.
        
        Args:
            bot_token: Telegram bot token
            strategy_runner: StrategyRunner instance for executing commands
            enabled: Whether command handling is enabled
        """
        self.bot_token = bot_token
        self.strategy_runner = strategy_runner
        self.enabled = enabled and bool(bot_token)
        
        if self.enabled:
            self.base_url = f"https://api.telegram.org/bot{bot_token}"
            self._running = False
            self._task: Optional[asyncio.Task] = None
            logger.info("Telegram command handler enabled")
        else:
            self.base_url = None
            logger.info("Telegram command handler disabled")
    
    async def get_updates(self, offset: Optional[int] = None, timeout: int = 30) -> Dict[str, Any]:
        """Get updates from Telegram.
        
        Args:
            offset: Offset for pagination
            timeout: Long polling timeout in seconds
            
        Returns:
            Updates response from Telegram API
        """
        if not self.enabled or not self.base_url:
            return {"ok": False, "result": []}
        
        url = f"{self.base_url}/getUpdates"
        params = {
            "timeout": timeout,
        }
        if offset:
            params["offset"] = offset
        
        try:
            async with httpx.AsyncClient(timeout=timeout + 5) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error getting Telegram updates: {e}")
            return {"ok": False, "result": []}
    
    async def send_message(
        self,
        chat_id: str,
        message: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """Send a message to a Telegram chat.
        
        Args:
            chat_id: Chat ID to send message to
            message: Message text
            parse_mode: Message parsing mode (HTML or Markdown)
            
        Returns:
            True if message was sent successfully
        """
        if not self.enabled or not self.base_url:
            return False
        
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json().get("ok", False)
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    async def process_command(self, chat_id: str, command: str, args: list[str]) -> str:
        """Process a Telegram command.
        
        Args:
            chat_id: Chat ID of the user
            command: Command name (without /)
            args: Command arguments
            
        Returns:
            Response message to send to user
        """
        command = command.lower().strip()
        
        if command == "start" or command == "help":
            return self._format_help_message()
        
        elif command == "status" or command == "stats":
            return await self._handle_status()
        
        elif command == "list" or command == "strategies":
            return await self._handle_list_strategies()
        
        elif command == "start_strategy" or command == "start":
            if not args:
                return "❌ Usage: /start_strategy <strategy_id>\nExample: /start_strategy abc123"
            strategy_id = args[0]
            return await self._handle_start_strategy(chat_id, strategy_id)
        
        elif command == "stop_strategy" or command == "stop":
            if not args:
                return "❌ Usage: /stop_strategy <strategy_id>\nExample: /stop_strategy abc123"
            strategy_id = args[0]
            return await self._handle_stop_strategy(chat_id, strategy_id)
        
        elif command == "info" or command == "strategy":
            if not args:
                return "❌ Usage: /info <strategy_id>\nExample: /info abc123"
            strategy_id = args[0]
            return await self._handle_strategy_info(strategy_id)
        
        elif command == "balance" or command == "bal":
            return await self._handle_balance()
        
        elif command == "trades":
            strategy_id = args[0] if args else None
            return await self._handle_trades(strategy_id)
        
        else:
            return f"❌ Unknown command: /{command}\n\nType /help to see available commands."
    
    def _format_help_message(self) -> str:
        """Format help message with available commands."""
        return """🤖 <b>Binance Trading Bot Commands</b>

📊 <b>Information Commands:</b>
/help - Show this help message
/status - Show overall bot status
/list - List all strategies
/info &lt;strategy_id&gt; - Get strategy details
/balance - Show account balance

🎮 <b>Strategy Control:</b>
/start_strategy &lt;strategy_id&gt; - Start a strategy
/stop_strategy &lt;strategy_id&gt; - Stop a strategy

📈 <b>Trade Information:</b>
/trades [strategy_id] - Show recent trades

💡 <b>Examples:</b>
/info abc12345
/start_strategy abc12345
/stop_strategy abc12345
/trades abc12345

📝 <b>Note:</b> Use /list to get strategy IDs"""
    
    async def _handle_status(self) -> str:
        """Handle /status command."""
        try:
            strategies = self.strategy_runner.list_strategies()
            running = [s for s in strategies if s.status == StrategyState.running]
            stopped = [s for s in strategies if s.status == StrategyState.stopped]
            error = [s for s in strategies if s.status == StrategyState.error]
            
            total_pnl = sum(
                self.strategy_runner.calculate_strategy_stats(s.id).total_pnl
                for s in strategies
            )
            
            message = "📊 <b>Bot Status</b>\n\n"
            message += f"🟢 Running: {len(running)}\n"
            message += f"🔴 Stopped: {len(stopped)}\n"
            message += f"❌ Error: {len(error)}\n"
            message += f"📈 Total PnL: ${total_pnl:,.2f}\n"
            message += f"📋 Total Strategies: {len(strategies)}"
            
            return message
        except Exception as e:
            logger.exception("Error handling status command")
            return f"❌ Error getting status: {str(e)}"
    
    async def _handle_list_strategies(self) -> str:
        """Handle /list command."""
        try:
            strategies = self.strategy_runner.list_strategies()
            
            if not strategies:
                return "📋 No strategies registered."
            
            message = f"📋 <b>Strategies ({len(strategies)})</b>\n\n"
            
            for strategy in strategies[:10]:  # Limit to 10 for readability
                status_emoji = {
                    StrategyState.running: "🟢",
                    StrategyState.stopped: "🔴",
                    StrategyState.error: "❌",
                }.get(strategy.status, "⚪")
                
                pnl = self.strategy_runner.calculate_strategy_stats(strategy.id).total_pnl
                pnl_emoji = "📈" if pnl >= 0 else "📉"
                
                message += f"{status_emoji} <b>{strategy.name}</b>\n"
                message += f"   ID: <code>{strategy.id[:8]}...</code>\n"
                message += f"   Symbol: {strategy.symbol}\n"
                message += f"   {pnl_emoji} PnL: ${pnl:,.2f}\n\n"
            
            if len(strategies) > 10:
                message += f"... and {len(strategies) - 10} more"
            
            return message
        except Exception as e:
            logger.exception("Error handling list command")
            return f"❌ Error listing strategies: {str(e)}"
    
    async def _handle_start_strategy(self, chat_id: str, strategy_id: str) -> str:
        """Handle /start_strategy command."""
        try:
            summary = await self.strategy_runner.start(strategy_id)
            return f"✅ <b>Strategy Started</b>\n\n{self._format_strategy_summary(summary)}"
        except StrategyNotFoundError:
            return f"❌ Strategy not found: {strategy_id}"
        except StrategyAlreadyRunningError:
            return f"⚠️ Strategy is already running: {strategy_id}"
        except Exception as e:
            logger.exception("Error starting strategy via Telegram")
            return f"❌ Error starting strategy: {str(e)}"
    
    async def _handle_stop_strategy(self, chat_id: str, strategy_id: str) -> str:
        """Handle /stop_strategy command."""
        try:
            summary = await self.strategy_runner.stop(strategy_id)
            stats = self.strategy_runner.calculate_strategy_stats(strategy_id)
            return (
                f"⏹️ <b>Strategy Stopped</b>\n\n"
                f"{self._format_strategy_summary(summary)}\n\n"
                f"📊 Final PnL: ${stats.total_pnl:,.2f}"
            )
        except StrategyNotFoundError:
            return f"❌ Strategy not found: {strategy_id}"
        except StrategyNotRunningError:
            return f"⚠️ Strategy is not running: {strategy_id}"
        except Exception as e:
            logger.exception("Error stopping strategy via Telegram")
            return f"❌ Error stopping strategy: {str(e)}"
    
    async def _handle_strategy_info(self, strategy_id: str) -> str:
        """Handle /info command."""
        try:
            # Get strategy from list (same as API route)
            strategies = self.strategy_runner.list_strategies()
            summary = None
            for s in strategies:
                if s.id == strategy_id:
                    summary = s
                    break
            
            if not summary:
                raise StrategyNotFoundError(strategy_id)
            
            stats = self.strategy_runner.calculate_strategy_stats(strategy_id)
            
            message = f"📊 <b>Strategy Info</b>\n\n"
            message += self._format_strategy_summary(summary)
            message += "\n\n📈 <b>Statistics:</b>\n"
            message += f"Total PnL: ${stats.total_pnl:,.2f}\n"
            message += f"Total Trades: {stats.total_trades}\n"
            message += f"Win Rate: {stats.win_rate*100:.1f}%\n"
            message += f"Avg Profit: ${stats.avg_profit:,.2f}"
            
            return message
        except StrategyNotFoundError:
            return f"❌ Strategy not found: {strategy_id}"
        except Exception as e:
            logger.exception("Error getting strategy info")
            return f"❌ Error: {str(e)}"
    
    async def _handle_balance(self) -> str:
        """Handle /balance command."""
        try:
            # Get balance from BinanceClient via StrategyRunner
            client = self.strategy_runner.client
            balance = client.futures_account_balance()
            
            return (
                f"💰 <b>Account Balance</b>\n\n"
                f"Available: ${balance:,.2f} USDT"
            )
        except Exception as e:
            logger.exception("Error getting balance")
            return f"❌ Error getting balance: {str(e)}"
    
    async def _handle_trades(self, strategy_id: Optional[str]) -> str:
        """Handle /trades command."""
        try:
            if strategy_id:
                trades = self.strategy_runner.get_trades(strategy_id)
                if not trades:
                    return f"📋 No trades for strategy: {strategy_id}"
                
                message = f"📋 <b>Recent Trades</b> ({strategy_id[:8]}...)\n\n"
                for trade in trades[-5:]:  # Last 5 trades
                    pnl_emoji = "📈" if trade.realized_pnl and trade.realized_pnl >= 0 else "📉"
                    pnl_str = f"${trade.realized_pnl:,.2f}" if trade.realized_pnl else "N/A"
                    message += (
                        f"{pnl_emoji} {trade.side} {trade.quantity} @ ${trade.price:,.2f}\n"
                        f"   PnL: {pnl_str}\n\n"
                    )
                return message
            else:
                # Get all trades
                all_trades = []
                for strategy in self.strategy_runner.list_strategies():
                    trades = self.strategy_runner.get_trades(strategy.id)
                    all_trades.extend(trades)
                
                if not all_trades:
                    return "📋 No trades found."
                
                message = f"📋 <b>All Trades</b> ({len(all_trades)} total)\n\n"
                for trade in sorted(all_trades, key=lambda t: t.timestamp, reverse=True)[:10]:
                    pnl_emoji = "📈" if trade.realized_pnl and trade.realized_pnl >= 0 else "📉"
                    pnl_str = f"${trade.realized_pnl:,.2f}" if trade.realized_pnl else "N/A"
                    message += (
                        f"{pnl_emoji} {trade.symbol} {trade.side} @ ${trade.price:,.2f}\n"
                        f"   PnL: {pnl_str}\n\n"
                    )
                return message
        except Exception as e:
            logger.exception("Error getting trades")
            return f"❌ Error: {str(e)}"
    
    def _format_strategy_summary(self, summary: StrategySummary) -> str:
        """Format strategy summary for display."""
        status_emoji = {
            StrategyState.running: "🟢",
            StrategyState.stopped: "🔴",
            StrategyState.error: "❌",
        }.get(summary.status, "⚪")
        
        message = f"{status_emoji} <b>{summary.name}</b>\n"
        message += f"ID: <code>{summary.id}</code>\n"
        message += f"Symbol: {summary.symbol}\n"
        message += f"Type: {summary.strategy_type.value}\n"
        message += f"Leverage: {summary.leverage}x\n"
        
        if summary.position_side:
            position_emoji = "⬆️" if summary.position_side == "LONG" else "⬇️"
            message += f"Position: {position_emoji} {summary.position_side}\n"
            if summary.entry_price:
                message += f"Entry: ${summary.entry_price:,.2f}\n"
            if summary.unrealized_pnl is not None:
                pnl_emoji = "📈" if summary.unrealized_pnl >= 0 else "📉"
                message += f"{pnl_emoji} Unrealized PnL: ${summary.unrealized_pnl:,.2f}\n"
        
        return message
    
    async def process_updates(self) -> None:
        """Process incoming Telegram updates (long polling)."""
        if not self.enabled:
            return
        
        offset = None
        
        while self._running:
            try:
                updates = await self.get_updates(offset=offset, timeout=30)
                
                if not updates.get("ok"):
                    await asyncio.sleep(5)
                    continue
                
                for update in updates.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    
                    message = update.get("message")
                    if not message:
                        continue
                    
                    chat_id = str(message.get("chat", {}).get("id"))
                    text = message.get("text", "").strip()
                    
                    if not text.startswith("/"):
                        # Not a command, ignore
                        continue
                    
                    # Parse command
                    parts = text[1:].split(maxsplit=1)
                    command = parts[0] if parts else ""
                    args = parts[1].split() if len(parts) > 1 else []
                    
                    logger.info(f"Received Telegram command: /{command} from chat {chat_id}")
                    
                    # Process command
                    response = await self.process_command(chat_id, command, args)
                    
                    # Send response
                    await self.send_message(chat_id, response)
                    
            except asyncio.CancelledError:
                logger.info("Telegram command handler stopped")
                break
            except Exception as e:
                logger.exception("Error processing Telegram updates")
                await asyncio.sleep(5)
    
    def start(self) -> None:
        """Start the command handler (begin polling for updates)."""
        if not self.enabled:
            logger.warning("Telegram command handler is disabled")
            return
        
        if self._running:
            logger.warning("Telegram command handler is already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self.process_updates())
        logger.info("Telegram command handler started")
    
    def stop(self) -> None:
        """Stop the command handler."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Telegram command handler stopped")

