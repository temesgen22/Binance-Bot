"""Telegram command handler for receiving and processing user commands."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
                
                # Handle 409 Conflict specifically
                if response.status_code == 409:
                    logger.warning(
                        "Telegram API 409 Conflict: Another instance may be polling for updates. "
                        "This usually means multiple bot instances are running. "
                        "Only one instance should poll for updates at a time. "
                        "Will retry after a delay."
                    )
                    # Try to get updates with offset=-1 to clear pending updates
                    # This helps resolve conflicts
                    try:
                        clear_params = {"timeout": 1, "offset": -1}
                        await client.get(url, params=clear_params)
                        logger.info("Cleared pending Telegram updates to resolve conflict")
                    except Exception:
                        pass  # Ignore errors when clearing
                    return {"ok": False, "result": [], "error": "409 Conflict"}
                
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                logger.warning(
                    "Telegram API 409 Conflict detected. "
                    "Another bot instance may be running. "
                    "Ensure only one instance of the bot is polling for updates."
                )
                return {"ok": False, "result": [], "error": "409 Conflict"}
            else:
                logger.error(f"Telegram API HTTP error {e.response.status_code}: {e}")
                return {"ok": False, "result": [], "error": f"HTTP {e.response.status_code}"}
        except httpx.TimeoutException:
            logger.warning("Telegram API request timeout (this is normal for long polling)")
            return {"ok": False, "result": [], "error": "Timeout"}
        except httpx.RequestError as e:
            logger.error(f"Telegram API request error: {e}")
            return {"ok": False, "result": [], "error": "RequestError"}
        except Exception as e:
            logger.error(f"Unexpected error getting Telegram updates: {e}")
            return {"ok": False, "result": [], "error": str(e)}
    
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
        
        # Handle /start command - check if it's start_strategy with args, otherwise show help
        if command == "start":
            if args:
                # /start with args is treated as start_strategy
                strategy_id = args[0]
                return await self._handle_start_strategy(chat_id, strategy_id)
            else:
                # /start without args shows help
                return self._format_help_message()
        
        elif command == "help":
            return self._format_help_message()
        
        elif command == "status" or command == "stats":
            return await self._handle_status()
        
        elif command == "list" or command == "strategies":
            return await self._handle_list_strategies()
        
        elif command == "start_strategy":
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
            account_id = args[0] if args else None
            return await self._handle_balance(account_id)
        
        elif command == "trades":
            strategy_id = args[0] if args else None
            return await self._handle_trades(strategy_id)
        
        else:
            return f"❌ Unknown command: /{command}\n\nType /help to see available commands."
    
    def _add_timestamp(self, message: str) -> str:
        """Add timestamp to message."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"{message}\n\n⏰ {timestamp}"
    
    def _format_help_message(self) -> str:
        """Format help message with available commands."""
        return """🤖 <b>Binance Trading Bot Commands</b>

📊 <b>Status & Information:</b>
/status, /stats - Show complete bot dashboard
/balance [account_id] - Show account balance
/list, /strategies - List all strategies with status & PnL
/info &lt;strategy_id&gt; - Get complete strategy details
/trades [strategy_id] - Show trade history with summaries

🎮 <b>Strategy Control:</b>
/start_strategy &lt;strategy_id&gt; - Start a strategy
/stop_strategy &lt;strategy_id&gt;, /stop &lt;strategy_id&gt; - Stop a strategy

💡 <b>Examples:</b>
/status - View complete dashboard
/balance - View account balance
/list - List all strategies
/info abc12345-def6-7890-ghij-klmnopqrstuv - Get strategy details
/trades abc12345-def6-7890-ghij-klmnopqrstuv - View strategy trades

📝 <b>Tips:</b>
• Use /list to get full strategy IDs
• Strategy IDs can be partial (first 8+ chars)
• All commands show timestamps
• Use /help to see this message"""
    
    async def _handle_status(self) -> str:
        """Handle /status command - Main dashboard view."""
        try:
            strategies = self.strategy_runner.list_strategies()
            running = [s for s in strategies if s.status == StrategyState.running]
            stopped = [s for s in strategies if s.status == StrategyState.stopped]
            error = [s for s in strategies if s.status == StrategyState.error]
            
            # Calculate comprehensive performance metrics
            total_pnl = 0.0
            total_realized = 0.0
            total_unrealized = 0.0
            total_trades = 0
            completed_trades = 0
            winning_trades = 0
            losing_trades = 0
            
            for s in strategies:
                stats = self.strategy_runner.calculate_strategy_stats(s.id)
                total_pnl += stats.total_pnl
                total_realized += stats.total_pnl  # Realized PnL from stats
                if s.unrealized_pnl:
                    total_unrealized += s.unrealized_pnl
                total_trades += stats.total_trades
                completed_trades += stats.completed_trades
                winning_trades += stats.winning_trades
                losing_trades += stats.losing_trades
            
            # Get account information
            account_info = "N/A"
            account_balance = None
            try:
                if hasattr(self.strategy_runner, 'client_manager'):
                    client = self.strategy_runner.client_manager.get_default_client()
                else:
                    client = self.strategy_runner.client
                
                if client:
                    account_id = getattr(client, 'account_id', 'default')
                    is_paper = getattr(client, 'paper_trading', False)
                    is_testnet = getattr(client, 'testnet', False)
                    
                    if is_paper:
                        account_type = "📝 Paper Trading"
                    elif is_testnet:
                        account_type = "🧪 Testnet"
                    else:
                        account_type = "💰 Live Trading"
                    
                    account_info = f"{account_id} ({account_type})"
                    
                    # Get balance
                    try:
                        balance = client.futures_account_balance()
                        account_balance = balance
                    except:
                        pass
            except:
                pass
            
            # Calculate win rate
            win_rate = (winning_trades / completed_trades * 100) if completed_trades > 0 else 0
            
            # Get risk status summary
            risk_summary = ""
            blocked_count = 0
            circuit_breaker_count = 0
            try:
                if hasattr(self.strategy_runner, 'risk_manager'):
                    for s in strategies:
                        risk_status = self.strategy_runner.risk_manager.get_strategy_risk_status(s.id)
                        if risk_status:
                            if not risk_status.can_trade:
                                blocked_count += 1
                            if risk_status.circuit_breaker_active:
                                circuit_breaker_count += 1
                    
                    if blocked_count > 0 or circuit_breaker_count > 0:
                        risk_summary = f"\n🛡️ <b>Risk Status:</b>\n"
                        if blocked_count > 0:
                            risk_summary += f"   🚫 Blocked: {blocked_count} strategies\n"
                        if circuit_breaker_count > 0:
                            risk_summary += f"   ⛔ Circuit Breakers: {circuit_breaker_count}\n"
            except:
                pass
            
            # Build comprehensive status message
            message = "📊 <b>Bot Status Dashboard</b>\n\n"
            
            # Account Section
            message += "👤 <b>Account:</b>\n"
            message += f"   {account_info}\n"
            if account_balance is not None:
                message += f"   Balance: <b>${account_balance:,.2f} USDT</b>\n"
            message += "\n"
            
            # Strategy Section
            message += "📈 <b>Strategies:</b>\n"
            message += f"   🟢 Running: <b>{len(running)}</b>\n"
            message += f"   🔴 Stopped: <b>{len(stopped)}</b>\n"
            if len(error) > 0:
                message += f"   ❌ Error: <b>{len(error)}</b>\n"
            message += f"   📋 Total: <b>{len(strategies)}</b>\n"
            message += "\n"
            
            # Performance Section
            message += "💰 <b>Performance:</b>\n"
            message += f"   Total PnL: <b>${total_pnl:,.2f}</b>\n"
            if total_realized != 0:
                realized_emoji = "📈" if total_realized >= 0 else "📉"
                message += f"   {realized_emoji} Realized: ${total_realized:,.2f}\n"
            if total_unrealized != 0:
                unrealized_emoji = "📈" if total_unrealized >= 0 else "📉"
                message += f"   {unrealized_emoji} Unrealized: ${total_unrealized:,.2f}\n"
            message += "\n"
            
            # Trade Statistics Section
            message += "📊 <b>Trade Statistics:</b>\n"
            message += f"   Total Trades: <b>{total_trades}</b>\n"
            message += f"   Completed: <b>{completed_trades}</b>\n"
            if completed_trades > 0:
                message += f"   Wins: <b>{winning_trades}</b> | Losses: <b>{losing_trades}</b>\n"
                message += f"   Win Rate: <b>{win_rate:.1f}%</b>\n"
            message += "\n"
            
            # Risk Status Section (if applicable)
            if risk_summary:
                message += risk_summary
            
            return self._add_timestamp(message)
        except Exception as e:
            logger.exception("Error handling status command")
            return f"❌ Error getting status: {str(e)}"
    
    async def _handle_list_strategies(self) -> str:
        """Handle /list command with enhanced formatting."""
        try:
            strategies = self.strategy_runner.list_strategies()
            
            if not strategies:
                return "📋 No strategies registered.\n\nUse the web interface to create strategies."
            
            # Sort by status (running first) then by name
            sorted_strategies = sorted(
                strategies,
                key=lambda s: (s.status != StrategyState.running, s.name.lower())
            )
            
            message = f"📋 <b>Strategies ({len(strategies)})</b>\n\n"
            
            # Group by status
            running = [s for s in sorted_strategies if s.status == StrategyState.running]
            stopped = [s for s in sorted_strategies if s.status == StrategyState.stopped]
            error = [s for s in sorted_strategies if s.status == StrategyState.error]
            
            if running:
                message += f"🟢 <b>Running ({len(running)})</b>\n"
                for strategy in running[:5]:
                    stats = self.strategy_runner.calculate_strategy_stats(strategy.id)
                    pnl_emoji = "📈" if stats.total_pnl >= 0 else "📉"
                    message += f"  • <b>{strategy.name}</b>\n"
                    message += f"    <code>{strategy.id}</code>\n"
                    message += f"    {strategy.symbol} | {pnl_emoji} ${stats.total_pnl:,.2f}\n\n"
                if len(running) > 5:
                    message += f"  ... and {len(running) - 5} more\n\n"
            
            if stopped:
                message += f"🔴 <b>Stopped ({len(stopped)})</b>\n"
                for strategy in stopped[:3]:
                    stats = self.strategy_runner.calculate_strategy_stats(strategy.id)
                    pnl_emoji = "📈" if stats.total_pnl >= 0 else "📉"
                    message += f"  • <b>{strategy.name}</b>\n"
                    message += f"    <code>{strategy.id}</code>\n"
                    message += f"    {pnl_emoji} ${stats.total_pnl:,.2f}\n\n"
                if len(stopped) > 3:
                    message += f"  ... and {len(stopped) - 3} more\n\n"
            
            if error:
                message += f"❌ <b>Error ({len(error)})</b>\n"
                for strategy in error[:3]:
                    message += f"  • <b>{strategy.name}</b>\n"
                    message += f"    <code>{strategy.id}</code>\n\n"
                if len(error) > 3:
                    message += f"  ... and {len(error) - 3} more\n\n"
            
            message += "\n💡 <b>Tip:</b> Use /info &lt;strategy_id&gt; for details"
            
            return self._add_timestamp(message)
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
        """Handle /info command with enhanced details."""
        try:
            strategies = self.strategy_runner.list_strategies()
            summary = None
            
            # Try exact match first
            for s in strategies:
                if s.id == strategy_id:
                    summary = s
                    break
            
            # Try partial match if exact match failed
            if not summary:
                matches = [s for s in strategies if s.id.startswith(strategy_id)]
                if len(matches) == 1:
                    summary = matches[0]
                elif len(matches) > 1:
                    message = f"❌ Multiple strategies match '{strategy_id}'. Use full ID:\n\n"
                    for s in matches[:5]:
                        message += f"  • <code>{s.id}</code> - {s.name}\n"
                    if len(matches) > 5:
                        message += f"  ... and {len(matches) - 5} more\n"
                    return message
                else:
                    raise StrategyNotFoundError(strategy_id)
            
            stats = self.strategy_runner.calculate_strategy_stats(summary.id)
            
            message = f"📊 <b>Strategy Info</b>\n\n"
            message += self._format_strategy_summary(summary)
            
            # Add account info
            if summary.account_id:
                message += f"👤 Account: {summary.account_id}\n"
            
            message += "\n📈 <b>Performance:</b>\n"
            message += f"Total PnL: <b>${stats.total_pnl:,.2f}</b>\n"
            if summary.unrealized_pnl is not None:
                message += f"Unrealized: ${summary.unrealized_pnl:,.2f}\n"
                realized = stats.total_pnl - summary.unrealized_pnl
                message += f"Realized: ${realized:,.2f}\n"
            message += f"Total Trades: {stats.total_trades}\n"
            message += f"Completed: {stats.completed_trades}\n"
            message += f"Win Rate: <b>{stats.win_rate*100:.1f}%</b>\n"
            message += f"Avg Profit: ${stats.avg_profit_per_trade:,.2f}\n"
            
            if stats.largest_win:
                message += f"Best Trade: +${stats.largest_win:,.2f}\n"
            if stats.largest_loss:
                message += f"Worst Trade: ${stats.largest_loss:,.2f}\n"
            
            if stats.last_trade_at:
                try:
                    last_trade = stats.last_trade_at
                    if isinstance(last_trade, str):
                        last_trade = datetime.fromisoformat(last_trade.replace('Z', '+00:00'))
                    message += f"Last Trade: {last_trade.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                except:
                    pass
            
            # Add risk status if available
            try:
                if hasattr(self.strategy_runner, 'risk_manager'):
                    risk_status = self.strategy_runner.risk_manager.get_strategy_risk_status(summary.id)
                    if risk_status:
                        message += "\n🛡️ <b>Risk Status:</b>\n"
                        message += f"Can Trade: {'✅ Yes' if risk_status.can_trade else '❌ No'}\n"
                        if risk_status.blocked_reasons:
                            message += f"Blocked: {', '.join(risk_status.blocked_reasons)}\n"
                        message += f"Circuit Breaker: {'🔴 Active' if risk_status.circuit_breaker_active else '🟢 Inactive'}\n"
                        message += f"Risk Checks: {'✅ Allowed' if risk_status.risk_checks_allowed else '❌ Blocked'}\n"
            except:
                pass
            
            return self._add_timestamp(message)
        except StrategyNotFoundError:
            return f"❌ Strategy not found: {strategy_id}\n\nUse /list to see all strategies."
        except Exception as e:
            logger.exception("Error getting strategy info")
            return f"❌ Error: {str(e)}"
    
    async def _handle_balance(self, account_id: Optional[str] = None) -> str:
        """Handle /balance command with account support."""
        try:
            # Get client manager or single client
            client = None
            if hasattr(self.strategy_runner, 'client_manager'):
                if account_id:
                    client = self.strategy_runner.client_manager.get_client(account_id)
                else:
                    # Get default client
                    client = self.strategy_runner.client_manager.get_default_client()
            else:
                client = self.strategy_runner.client
            
            if not client:
                return "❌ No account available.\n\nUse /list to see available accounts or check your configuration."
            
            # Get account info
            account_id_display = account_id or getattr(client, 'account_id', 'default')
            is_paper = getattr(client, 'paper_trading', False)
            is_testnet = getattr(client, 'testnet', False)
            
            if is_paper:
                account_type = "📝 Paper Trading"
            elif is_testnet:
                account_type = "🧪 Testnet"
            else:
                account_type = "💰 Live Trading"
            
            # Get balance from Binance
            try:
                # Try to get account info for more details
                rest = client._ensure()
                account_info = rest.futures_account()
                assets = account_info.get("assets", [])
                
                # Find USDT balance
                usdt_balance = None
                total_balance = None
                for asset in assets:
                    if asset.get("asset") == "USDT":
                        usdt_balance = float(asset.get("availableBalance", 0))
                        total_balance = float(asset.get("balance", 0))
                        break
                
                if usdt_balance is None:
                    # Fallback to simple balance method
                    balance = client.futures_account_balance()
                    usdt_balance = balance
                    total_balance = balance
            except Exception as e:
                logger.debug(f"Could not get detailed balance info: {e}")
                # Fallback to simple balance method
                try:
                    balance = client.futures_account_balance()
                    usdt_balance = balance
                    total_balance = balance
                except Exception as e2:
                    logger.exception("Error getting balance")
                    return f"❌ Error getting balance: {str(e2)}\n\nUse /accounts to list available accounts."
            
            message = "💰 <b>Account Balance</b>\n\n"
            message += f"Account: <b>{account_id_display}</b>\n"
            message += f"Type: {account_type}\n\n"
            message += f"Available: <b>${usdt_balance:,.2f} USDT</b>\n"
            if total_balance and total_balance != usdt_balance:
                message += f"Total: ${total_balance:,.2f} USDT\n"
                in_use = total_balance - usdt_balance
                if in_use > 0:
                    message += f"In Use: ${in_use:,.2f} USDT\n"
            
            return self._add_timestamp(message)
        except Exception as e:
            logger.exception("Error getting balance")
            return f"❌ Error getting balance: {str(e)}\n\nUse /accounts to list available accounts."
    
    async def _handle_trades(self, strategy_id: Optional[str], limit: int = 10) -> str:
        """Handle /trades command with enhanced formatting."""
        try:
            if strategy_id:
                trades = self.strategy_runner.get_trades(strategy_id)
                if not trades:
                    return f"📋 No trades for strategy: <code>{strategy_id}</code>"
                
                # Get strategy name
                strategy_name = strategy_id
                strategies = self.strategy_runner.list_strategies()
                for s in strategies:
                    if s.id == strategy_id:
                        strategy_name = s.name
                        break
                
                message = f"📋 <b>Recent Trades</b>\n\n"
                message += f"Strategy: <b>{strategy_name}</b>\n"
                message += f"ID: <code>{strategy_id}</code>\n\n"
                
                # Calculate summary
                total_pnl = sum(t.realized_pnl or 0 for t in trades)
                winning = sum(1 for t in trades if t.realized_pnl and t.realized_pnl > 0)
                losing = sum(1 for t in trades if t.realized_pnl and t.realized_pnl < 0)
                
                message += f"📊 <b>Summary:</b>\n"
                message += f"Total Trades: {len(trades)}\n"
                message += f"Total PnL: <b>${total_pnl:,.2f}</b>\n"
                message += f"Wins: {winning} | Losses: {losing}\n\n"
                
                # Show recent trades
                recent_trades = sorted(trades, key=lambda t: t.timestamp, reverse=True)[:limit]
                message += f"📈 <b>Last {len(recent_trades)} Trades:</b>\n\n"
                
                for trade in recent_trades:
                    pnl_emoji = "📈" if (trade.realized_pnl and trade.realized_pnl >= 0) else "📉"
                    pnl_str = f"${trade.realized_pnl:,.2f}" if trade.realized_pnl else "N/A"
                    
                    # Format timestamp
                    try:
                        if isinstance(trade.timestamp, str):
                            ts = datetime.fromisoformat(trade.timestamp.replace('Z', '+00:00'))
                        else:
                            ts = trade.timestamp
                        time_str = ts.strftime('%Y-%m-%d %H:%M')
                    except:
                        time_str = "N/A"
                    
                    message += f"{pnl_emoji} <b>{trade.side}</b> {trade.executed_qty:.8f} @ ${trade.price:,.8f}\n"
                    message += f"   PnL: {pnl_str} | {time_str}\n\n"
                
                if len(trades) > limit:
                    message += f"... and {len(trades) - limit} more trades"
                
                return self._add_timestamp(message)
            else:
                # All trades
                all_trades = []
                for strategy in self.strategy_runner.list_strategies():
                    trades = self.strategy_runner.get_trades(strategy.id)
                    for trade in trades:
                        # Add strategy context
                        trade.strategy_name = strategy.name
                        trade.strategy_id = strategy.id
                    all_trades.extend(trades)
                
                if not all_trades:
                    return "📋 No trades found."
                
                # Sort by timestamp
                all_trades.sort(key=lambda t: t.timestamp, reverse=True)
                
                message = f"📋 <b>All Trades</b> ({len(all_trades)} total)\n\n"
                
                # Summary
                total_pnl = sum(t.realized_pnl or 0 for t in all_trades)
                message += f"📊 Total PnL: <b>${total_pnl:,.2f}</b>\n\n"
                
                # Show recent trades
                for trade in all_trades[:limit]:
                    pnl_emoji = "📈" if (trade.realized_pnl and trade.realized_pnl >= 0) else "📉"
                    pnl_str = f"${trade.realized_pnl:,.2f}" if trade.realized_pnl else "N/A"
                    
                    strategy_name = getattr(trade, 'strategy_name', 'Unknown')
                    
                    message += f"{pnl_emoji} <b>{strategy_name}</b>\n"
                    message += f"   {trade.side} {trade.executed_qty:.8f} @ ${trade.price:,.8f}\n"
                    message += f"   PnL: {pnl_str}\n\n"
                
                if len(all_trades) > limit:
                    message += f"... and {len(all_trades) - limit} more"
                
                return self._add_timestamp(message)
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
                message += f"Entry: ${summary.entry_price:,.4f}\n"
            if summary.current_price:
                message += f"Current: ${summary.current_price:,.4f}\n"
            if summary.unrealized_pnl is not None:
                pnl_emoji = "📈" if summary.unrealized_pnl >= 0 else "📉"
                message += f"{pnl_emoji} Unrealized PnL: ${summary.unrealized_pnl:,.2f}\n"
        
        return message
    
    async def process_updates(self) -> None:
        """Process incoming Telegram updates (long polling)."""
        if not self.enabled:
            return
        
        offset = None
        conflict_retry_count = 0
        max_conflict_retries = 3
        
        while self._running:
            try:
                updates = await self.get_updates(offset=offset, timeout=30)
                
                if not updates.get("ok"):
                    error_type = updates.get("error", "Unknown")
                    
                    # Handle 409 Conflict with exponential backoff
                    if error_type == "409 Conflict":
                        conflict_retry_count += 1
                        if conflict_retry_count <= max_conflict_retries:
                            wait_time = min(5 * (2 ** (conflict_retry_count - 1)), 60)  # Exponential backoff, max 60s
                            logger.warning(
                                f"Telegram conflict detected (attempt {conflict_retry_count}/{max_conflict_retries}). "
                                f"Waiting {wait_time}s before retry. "
                                f"Ensure only one bot instance is running."
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(
                                f"Telegram conflict persists after {max_conflict_retries} retries. "
                                f"Stopping update polling. Please ensure only one bot instance is running."
                            )
                            # Stop polling but don't crash - just log the issue
                            await asyncio.sleep(60)  # Wait 1 minute before trying again
                            conflict_retry_count = 0  # Reset counter
                            continue
                    else:
                        # Reset conflict counter on other errors
                        conflict_retry_count = 0
                        await asyncio.sleep(5)
                        continue
                
                # Reset conflict counter on successful update
                conflict_retry_count = 0
                
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

