from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.core.binance_client_manager import BinanceClientManager
from app.models.order import OrderResponse
from app.core.redis_storage import RedisStorage
from app.core.exceptions import (
    StrategyNotFoundError,
    StrategyAlreadyRunningError,
    StrategyNotRunningError,
    MaxConcurrentStrategiesError,
    InvalidLeverageError,
    PositionSizingError,
    OrderExecutionError,
    BinanceAPIError,
)
from app.risk.manager import RiskManager, PositionSizingResult
from app.models.strategy import CreateStrategyRequest, StrategyState, StrategySummary, StrategyType, StrategyStats, OverallStats
from app.services.order_executor import OrderExecutor
from app.services.notifier import NotificationService
from app.strategies.base import Strategy, StrategyContext, StrategySignal
from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.range_mean_reversion import RangeMeanReversionStrategy
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from uuid import UUID
    from app.services.strategy_service import StrategyService
    from app.services.trade_service import TradeService


class StrategyRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, type[Strategy]] = {
            StrategyType.scalping.value: EmaScalpingStrategy,
            # ema_crossover is now an alias for scalping with default 5/20 EMA
            # Users can achieve the same by setting ema_fast=5, ema_slow=20 in params
            StrategyType.ema_crossover.value: EmaScalpingStrategy,
            StrategyType.range_mean_reversion.value: RangeMeanReversionStrategy,
        }

    def build(self, strategy_type: StrategyType, context: StrategyContext, client: BinanceClient) -> Strategy:
        """Build a strategy instance from type.
        
        Raises:
            ValueError: If strategy type is not supported or initialization fails
        """
        try:
            implementation = self._registry[strategy_type.value]
        except KeyError as exc:
            available = list(self._registry.keys())
            raise ValueError(
                f"Unsupported strategy type: {strategy_type}. "
                f"Available types: {', '.join(available)}"
            ) from exc
        try:
            return implementation(context, client)
        except Exception as exc:
            logger.exception(f"Failed to build strategy {strategy_type}: {exc}")
            raise ValueError(f"Failed to initialize strategy {strategy_type}: {exc}") from exc


class StrategyRunner:
    def __init__(
        self,
        *,
        client: Optional[BinanceClient] = None,
        client_manager: Optional[BinanceClientManager] = None,
        risk: Optional[RiskManager] = None,
        executor: Optional[OrderExecutor] = None,
        max_concurrent: int = 3,
        redis_storage: Optional[RedisStorage] = None,
        notification_service: Optional[NotificationService] = None,
        strategy_service: Optional["StrategyService"] = None,
        user_id: Optional["UUID"] = None,
    ) -> None:
        """Initialize StrategyRunner.
        
        Args:
            client: Single BinanceClient (for backward compatibility)
            client_manager: BinanceClientManager for multi-account support (preferred)
            risk: RiskManager (for backward compatibility, will be created per account if using client_manager)
            executor: OrderExecutor (for backward compatibility, will be created per account if using client_manager)
            max_concurrent: Maximum concurrent strategies
            redis_storage: Redis storage for persistence
            notification_service: Notification service
            strategy_service: StrategyService for database persistence (optional, for multi-user mode)
            user_id: User ID for multi-user mode (required if strategy_service is provided)
        """
        # Support both single client (backward compatibility) and client manager (multi-account)
        if client_manager:
            self.client_manager = client_manager
            self.client = client_manager.get_default_client()  # Default client for backward compatibility
        elif client:
            self.client = client
            # Create a simple client manager with just the provided client
            # This ensures mock clients in tests are always used instead of real clients from settings
            from app.core.config import get_settings
            settings = get_settings()
            self.client_manager = BinanceClientManager(settings)
            # CRITICAL: Replace all clients with just the provided client
            # This ensures mock clients in tests are always used instead of real clients
            self.client_manager._clients = {"default": client}
            # For test mode with mock client, create a mock account config
            from app.core.config import BinanceAccountConfig
            self.client_manager._accounts = {
                "default": BinanceAccountConfig(
                    account_id="default",
                    api_key="mock",
                    api_secret="mock",
                    testnet=True,
                    name="Mock Account"
                )
            }
        else:
            raise ValueError("Either client or client_manager must be provided")
        
        # For backward compatibility, use provided risk/executor if available
        # Otherwise, they'll be created per strategy based on account_id
        self.default_risk = risk
        self.default_executor = executor
        
        self.registry = StrategyRegistry()
        self.max_concurrent = max_concurrent
        self.redis = redis_storage
        self.notifications = notification_service
        self.strategy_service = strategy_service
        self.user_id = user_id
        self.trade_service: Optional["TradeService"] = None  # Will be set by dependency injection
        self._strategies: Dict[str, StrategySummary] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._trades: Dict[str, List[OrderResponse]] = {}  # Track trades per strategy
        
        # Track if we're using a directly provided client (for tests with mock clients)
        self._has_direct_client = client is not None and client_manager is None
        
        # Validate: if strategy_service is provided, user_id must be provided
        if strategy_service is not None and user_id is None:
            raise ValueError("user_id must be provided when strategy_service is provided")
        
        # Load strategies on startup
        if strategy_service and user_id:
            # Multi-user mode: load from database via StrategyService
            self._load_from_database()
        else:
            # Single-user mode: load from Redis (backward compatibility)
            self._load_from_redis()
    
    def _get_account_client(self, account_id: str) -> BinanceClient:
        """Get client for an account, preferring directly provided client for default account.
        
        This ensures mock clients in tests are always used instead of real clients.
        """
        account_id = account_id or "default"
        
        # If we have a directly provided client and account_id is "default", use it
        # This ensures mock clients in tests override real clients from manager
        if account_id == "default" and self._has_direct_client and self.client:
            return self.client
        
        # Otherwise, get from manager or fall back to directly provided client
        return self.client_manager.get_client(account_id) or self.client

    def _cleanup_dead_tasks(self) -> None:
        """Remove completed/cancelled tasks from _tasks dictionary.
        
        This ensures dead tasks don't count toward the concurrent limit.
        """
        dead_tasks = []
        for strategy_id, task in list(self._tasks.items()):
            if task.done():
                dead_tasks.append(strategy_id)
                # Update strategy status if it's still marked as running
                if strategy_id in self._strategies:
                    summary = self._strategies[strategy_id]
                    if summary.status == StrategyState.running:
                        summary.status = StrategyState.error
                        # Update database FIRST (source of truth), then Redis
                        if self.strategy_service and self.user_id:
                            try:
                                self.strategy_service.update_strategy(
                                    user_id=self.user_id,
                                    strategy_id=strategy_id,
                                    status=StrategyState.error.value
                                )
                                # Only save to Redis after database update succeeds
                                self._save_to_redis(strategy_id, summary)
                            except Exception as e:
                                logger.error(f"Failed to update strategy {strategy_id} status to 'error' in database: {e}")
                                # Still save to Redis for backward compatibility if database fails
                                self._save_to_redis(strategy_id, summary)
                        else:
                            # No database mode - save to Redis only
                            self._save_to_redis(strategy_id, summary)
                        logger.warning(
                            f"Strategy {strategy_id} task completed unexpectedly. "
                            f"Marking as error status."
                        )
        
        # Remove dead tasks
        for strategy_id in dead_tasks:
            self._tasks.pop(strategy_id, None)
            logger.debug(f"Cleaned up dead task for strategy {strategy_id}")
        
        if dead_tasks:
            logger.info(f"Cleaned up {len(dead_tasks)} dead task(s) from active tasks")

    def _extract_error_details(self, exc: Exception, order_type: str, summary: StrategySummary, stop_price: float) -> dict:
        """Extract detailed error information from exception for better debugging.
        
        Args:
            exc: The exception that was raised
            order_type: "TP" or "SL" for logging
            summary: Strategy summary for context
            stop_price: The stop price that was attempted
        
        Returns:
            Dictionary with error details
        """
        try:
            from tenacity import RetryError
        except ImportError:
            RetryError = None
        
        # Extract underlying error from RetryError if present
        underlying_error = exc
        if RetryError and isinstance(exc, RetryError):
            if hasattr(exc, 'last_attempt') and exc.last_attempt:
                underlying_error = exc.last_attempt.exception()
        
        # Get error details
        error_details = {
            "order_type": order_type,
            "error_type": type(underlying_error).__name__,
            "error_message": str(underlying_error),
            "symbol": summary.symbol,
            "stop_price": stop_price,
            "entry_price": summary.entry_price,
            "current_price": summary.current_price,
            "position_side": summary.position_side,
            "position_size": summary.position_size,
        }
        
        # Extract Binance error code if available
        if hasattr(underlying_error, 'error_code'):
            error_details["binance_error_code"] = underlying_error.error_code
        if hasattr(underlying_error, 'status_code'):
            error_details["status_code"] = underlying_error.status_code
        
        return error_details

    def register(self, payload: CreateStrategyRequest, account_uuid: Optional["UUID"] = None) -> StrategySummary:
        """Register a new strategy.
        
        Args:
            payload: Strategy creation request
            account_uuid: UUID of the account in database (required for multi-user mode)
        
        Returns:
            StrategySummary of the created strategy
        """
        # Validate leverage is explicitly provided (Pydantic should catch this, but double-check)
        if payload.leverage is None:
            raise InvalidLeverageError(
                leverage=0,
                reason="leverage is REQUIRED and must be explicitly provided to prevent Binance default 20x"
            )
        if not (1 <= payload.leverage <= 50):
            raise InvalidLeverageError(
                leverage=payload.leverage,
                reason="Must be between 1 and 50. Binance futures default is 20x - ensure you explicitly set your desired leverage."
            )
        
        # Validate account_id exists
        account_id = payload.account_id.lower() if payload.account_id else "default"
        
        # Load accounts from database if we have a user_id and they're not already loaded
        if self.user_id and not self.client_manager.account_exists(account_id):
            from app.services.account_service import AccountService
            from app.core.redis_storage import RedisStorage
            from app.core.config import get_settings
            
            settings = get_settings()
            redis_storage = None
            if settings.redis_enabled:
                redis_storage = RedisStorage(
                    redis_url=settings.redis_url,
                    enabled=settings.redis_enabled
                )
            
            # Get database session from strategy_service if available
            if self.strategy_service:
                # Access db through db_service
                db = self.strategy_service.db_service.db
                account_service = AccountService(db, redis_storage)
                accounts = account_service.list_accounts(self.user_id)
                
                # Load accounts into client manager
                for account_config in accounts:
                    self.client_manager.add_client(account_config.account_id, account_config)
        
        # Check again after loading
        if not self.client_manager.account_exists(account_id):
            available_accounts = list(self.client_manager.list_accounts().keys())
            raise ValueError(
                f"Binance account '{account_id}' not found. "
                f"Available accounts: {', '.join(available_accounts) if available_accounts else 'none'}"
            )
        
        strategy_id = str(uuid.uuid4())
        
        # Multi-user mode: use StrategyService to save to database
        if self.strategy_service and self.user_id and account_uuid:
            summary = self.strategy_service.create_strategy(
                user_id=self.user_id,
                strategy_id=strategy_id,
                name=payload.name,
                symbol=payload.symbol,
                strategy_type=payload.strategy_type.value if isinstance(payload.strategy_type, StrategyType) else payload.strategy_type,
                account_id=account_uuid,
                leverage=payload.leverage,
                risk_per_trade=payload.risk_per_trade,
                params=payload.params.model_dump() if hasattr(payload.params, 'model_dump') else payload.params,
                fixed_amount=payload.fixed_amount,
                max_positions=1
            )
            # Also keep in memory for fast access
            self._strategies[strategy_id] = summary
        else:
            # Single-user mode: save to Redis only (backward compatibility)
            summary = StrategySummary(
                id=strategy_id,
                name=payload.name,
                symbol=payload.symbol,
                strategy_type=payload.strategy_type,
                status=StrategyState.stopped,
                leverage=payload.leverage,
                risk_per_trade=payload.risk_per_trade,
                fixed_amount=payload.fixed_amount,
                params=payload.params,
                created_at=datetime.now(timezone.utc),
                account_id=account_id,
                last_signal=None,
                entry_price=None,
                current_price=None,
                position_size=None,
                unrealized_pnl=None,
                meta={},
            )
            self._strategies[strategy_id] = summary
        self._save_to_redis(strategy_id, summary)
        
        account_name = self.client_manager.get_account_config(account_id)
        account_display = account_name.name if account_name else account_id
        logger.info(
            f"Registered strategy {strategy_id} ({payload.strategy_type}) "
            f"with explicit leverage={payload.leverage}x for {payload.symbol} "
            f"using account '{account_id}' ({account_display})"
        )
        # auto_start is handled by the API layer to avoid double-starting the same strategy.
        return summary

    def _cleanup_dead_tasks(self) -> None:
        """Remove completed/cancelled tasks from _tasks dictionary.
        
        This ensures dead tasks don't count toward the concurrent limit.
        """
        dead_tasks = []
        for strategy_id, task in list(self._tasks.items()):
            if task.done():
                dead_tasks.append(strategy_id)
                # Update strategy status if it's still marked as running
                if strategy_id in self._strategies:
                    summary = self._strategies[strategy_id]
                    if summary.status == StrategyState.running:
                        summary.status = StrategyState.error
                        # Update database FIRST (source of truth), then Redis
                        if self.strategy_service and self.user_id:
                            try:
                                self.strategy_service.update_strategy(
                                    user_id=self.user_id,
                                    strategy_id=strategy_id,
                                    status=StrategyState.error.value
                                )
                                # Only save to Redis after database update succeeds
                                self._save_to_redis(strategy_id, summary)
                            except Exception as e:
                                logger.error(f"Failed to update strategy {strategy_id} status to 'error' in database: {e}")
                                # Still save to Redis for backward compatibility if database fails
                                self._save_to_redis(strategy_id, summary)
                        else:
                            # No database mode - save to Redis only
                            self._save_to_redis(strategy_id, summary)
                        logger.warning(
                            f"Strategy {strategy_id} task completed unexpectedly. "
                            f"Marking as error status."
                        )
        
        # Remove dead tasks
        for strategy_id in dead_tasks:
            self._tasks.pop(strategy_id, None)
            logger.debug(f"Cleaned up dead task for strategy {strategy_id}")
        
        if dead_tasks:
            logger.info(f"Cleaned up {len(dead_tasks)} dead task(s) from active tasks")

    async def start(self, strategy_id: str) -> StrategySummary:
        # BUG FIX: Load strategy from database if not in memory
        if strategy_id not in self._strategies:
            if self.strategy_service and self.user_id:
                try:
                    # Try to load from database
                    strategies = self.strategy_service.list_strategies(self.user_id)
                    for summary in strategies:
                        self._strategies[summary.id] = summary
                    # Check again after loading
                    if strategy_id not in self._strategies:
                        raise StrategyNotFoundError(strategy_id)
                except Exception as exc:
                    logger.warning(f"Failed to load strategy {strategy_id} from database: {exc}")
                    raise StrategyNotFoundError(strategy_id) from exc
            else:
                raise StrategyNotFoundError(strategy_id)
        
        # Get the strategy summary (must be done early as it's used in checks below)
        summary = self._strategies[strategy_id]
        
        # Clean up any dead/completed tasks before checking limit
        # This prevents dead tasks from counting toward concurrent limit
        self._cleanup_dead_tasks()
        
        if len(self._tasks) >= self.max_concurrent:
            raise MaxConcurrentStrategiesError(
                current=len(self._tasks),
                max_allowed=self.max_concurrent
            )
        # Check if strategy is already running
        # If task exists and is not done, strategy is actually running
        if strategy_id in self._tasks:
            task = self._tasks[strategy_id]
            if not task.done():
                raise StrategyAlreadyRunningError(strategy_id)
            else:
                # Task exists but is done (crashed/completed), remove it
                logger.warning(f"Strategy {strategy_id} has a dead task, cleaning up and restarting")
                del self._tasks[strategy_id]
        
        # Also check if status says running but no task exists (restore scenario)
        if summary.status == StrategyState.running and strategy_id not in self._tasks:
            logger.info(f"Strategy {strategy_id} has status 'running' but no active task, will start it now")
        
        # Get account-specific client, risk manager, and executor
        account_id = getattr(summary, 'account_id', 'default') or 'default'
        account_client = self._get_account_client(account_id)
        if not account_client:
            raise ValueError(f"Binance client not found for account '{account_id}'")
        
        # Create account-specific risk manager and executor
        account_risk = RiskManager(client=account_client)
        account_executor = OrderExecutor(client=account_client)
        
        # For backward compatibility: if ema_crossover type, set default 5/20 EMA
        params = summary.params.model_dump()
        if summary.strategy_type == StrategyType.ema_crossover:
            if "ema_fast" not in params or params.get("ema_fast") == 8:
                params["ema_fast"] = 5
            if "ema_slow" not in params or params.get("ema_slow") == 21:
                params["ema_slow"] = 20
            # Also set default TP/SL if not specified
            if "take_profit_pct" not in params:
                params["take_profit_pct"] = 0.005  # 0.5%
            if "stop_loss_pct" not in params:
                params["stop_loss_pct"] = 0.003  # 0.3%
        
        context = StrategyContext(
            id=summary.id,
            name=summary.name,
            symbol=summary.symbol,
            leverage=summary.leverage,
            risk_per_trade=summary.risk_per_trade,
            params=params,
            interval_seconds=summary.params.interval_seconds,
            metadata={},
        )
        strategy = self.registry.build(summary.strategy_type, context, account_client)
        task = asyncio.create_task(self._run_loop(strategy, summary, account_risk, account_executor))
        self._tasks[strategy_id] = task
        summary.status = StrategyState.running
        
        # Update database FIRST (source of truth), then Redis
        # This prevents data loss if database update fails
        if self.strategy_service and self.user_id:
            try:
                self.strategy_service.update_strategy(
                    user_id=self.user_id,
                    strategy_id=strategy_id,
                    status=StrategyState.running.value
                )
                logger.debug(f"Updated strategy {strategy_id} status to 'running' in database")
                # Only save to Redis after database update succeeds
                self._save_to_redis(strategy_id, summary)
            except Exception as e:
                logger.error(f"Failed to update strategy status in database: {e}. Redis not updated to prevent data loss.")
                # Don't update Redis if database update failed - prevents inconsistency
                # The strategy will still run in memory, but status won't persist
                raise  # Re-raise to prevent strategy from appearing started
        else:
            # No database mode - save to Redis only (backward compatibility)
            self._save_to_redis(strategy_id, summary)
        
        # Log strategy start
        account_name = self.client_manager.get_account_config(account_id)
        account_display = account_name.name if account_name else account_id
        logger.info(
            f"✅ Strategy STARTED: {summary.id} ({summary.name}) | "
            f"Symbol: {summary.symbol} | Type: {summary.strategy_type.value} | "
            f"Leverage: {summary.leverage}x | Account: {account_id} ({account_display})"
        )
        
        # Send notification that strategy started
        if self.notifications:
            asyncio.create_task(
                self.notifications.notify_strategy_started(summary, reason="Strategy started manually")
            )
        
        return summary

    async def stop(self, strategy_id: str) -> StrategySummary:
        # BUG FIX: Load strategy from database if not in memory
        if strategy_id not in self._strategies:
            if self.strategy_service and self.user_id:
                try:
                    # Try to load from database
                    strategies = self.strategy_service.list_strategies(self.user_id)
                    for summary in strategies:
                        self._strategies[summary.id] = summary
                    # Check again after loading
                    if strategy_id not in self._strategies:
                        raise StrategyNotFoundError(strategy_id)
                except Exception as exc:
                    logger.warning(f"Failed to load strategy {strategy_id} from database: {exc}")
                    raise StrategyNotFoundError(strategy_id) from exc
            else:
                raise StrategyNotFoundError(strategy_id)
        summary = self._strategies[strategy_id]
        
        # Cancel any open TP/SL orders first
        try:
            await self._cancel_tp_sl_orders(summary)
        except Exception as exc:
            logger.warning(f"Error cancelling TP/SL orders for strategy {strategy_id}: {exc}")
        
        # Check for open positions and close them
        try:
            account_id = summary.account_id or "default"
            account_client = self._get_account_client(account_id)
            position = account_client.get_open_position(summary.symbol)
            if position:
                position_side = "LONG" if float(position['positionAmt']) > 0 else "SHORT"
                logger.info(
                    f"🔴 MANUAL CLOSE: Closing {position_side} position for strategy {strategy_id}: "
                    f"{position['positionAmt']} {summary.symbol} @ {position['entryPrice']} "
                    f"(Unrealized PnL: {position['unRealizedProfit']:.2f} USDT)"
                )
                close_order = account_client.close_position(summary.symbol)
                if close_order:
                    logger.info(
                        f"[{strategy_id}] 🔴 Position CLOSED (reason: MANUAL/STOP): "
                        f"{close_order.side} {close_order.symbol} qty={close_order.executed_qty} @ {close_order.avg_price or close_order.price:.8f} "
                        f"(was {position_side} @ {position['entryPrice']})"
                    )
                    # Track the closing trade
                    if strategy_id not in self._trades:
                        self._trades[strategy_id] = []
                    self._trades[strategy_id].append(close_order)
                    
                    # Save to database if TradeService is available (multi-user mode)
                    if self.trade_service and self.user_id:
                        try:
                            # Get strategy UUID from database
                            if self.strategy_service:
                                db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, strategy_id)
                                if db_strategy:
                                    self.trade_service.save_trade(
                                        user_id=self.user_id,
                                        strategy_id=db_strategy.id,
                                        order=close_order
                                    )
                                    logger.debug(f"Saved closing trade {close_order.order_id} to database")
                        except Exception as e:
                            logger.warning(f"Failed to save closing trade to database: {e}")
        except Exception as exc:
            logger.warning(f"Error closing position for strategy {strategy_id}: {exc}")
            # Continue with stopping even if position close fails
        
        # Stop the strategy task
        task = self._tasks.pop(strategy_id, None)
        if task:
            task.cancel()
        summary.status = StrategyState.stopped
        
        # Update database FIRST (source of truth), then Redis
        # This prevents data loss if database update fails
        if self.strategy_service and self.user_id:
            try:
                self.strategy_service.update_strategy(
                    user_id=self.user_id,
                    strategy_id=strategy_id,
                    status=StrategyState.stopped.value
                )
                logger.debug(f"Updated strategy {strategy_id} status to 'stopped' in database")
                # Only save to Redis after database update succeeds
                self._save_to_redis(strategy_id, summary)
            except Exception as e:
                logger.error(f"Failed to update strategy status in database: {e}. Redis not updated to prevent data loss.")
                # Don't update Redis if database update failed - prevents inconsistency
        else:
            # No database mode - save to Redis only (backward compatibility)
            self._save_to_redis(strategy_id, summary)
        
        # Get final PnL before sending notification
        final_pnl = None
        if summary.unrealized_pnl is not None:
            final_pnl = summary.unrealized_pnl
        
        # Log strategy stop
        account_id = summary.account_id or "default"
        account_name = self.client_manager.get_account_config(account_id)
        account_display = account_name.name if account_name else account_id
        pnl_str = f" | Final PnL: ${final_pnl:.2f}" if final_pnl is not None else ""
        logger.info(
            f"⏹️ Strategy STOPPED: {summary.id} ({summary.name}) | "
            f"Symbol: {summary.symbol} | Account: {account_id} ({account_display})"
            f"{pnl_str} | Reason: Manual stop"
        )
        
        # Send notification that strategy stopped
        if self.notifications:
            asyncio.create_task(
                self.notifications.notify_strategy_stopped(
                    summary, 
                    reason="Strategy stopped manually",
                    final_pnl=final_pnl,
                )
            )
        
        return summary

    async def delete(self, strategy_id: str) -> None:
        """Delete a strategy permanently.
        
        This method will:
        1. Check if strategy is running and stop it if necessary
        2. Delete from database (if using StrategyService)
        3. Delete from Redis
        4. Remove from in-memory cache
        
        Args:
            strategy_id: Strategy ID to delete
            
        Raises:
            StrategyNotFoundError: If strategy does not exist
        """
        if strategy_id not in self._strategies:
            raise StrategyNotFoundError(strategy_id)
        
        summary = self._strategies[strategy_id]
        
        # Step 1: Stop strategy if it's running
        if summary.status == StrategyState.running:
            logger.info(f"Stopping strategy {strategy_id} before deletion...")
            try:
                await self.stop(strategy_id)
            except Exception as exc:
                logger.warning(f"Error stopping strategy {strategy_id} before deletion: {exc}")
                # Continue with deletion even if stop fails
        
        # Step 2: Delete from database (if using StrategyService)
        if self.strategy_service and self.user_id:
            try:
                success = self.strategy_service.delete_strategy(self.user_id, strategy_id)
                if not success:
                    logger.warning(f"Failed to delete strategy {strategy_id} from database")
            except Exception as exc:
                logger.warning(f"Error deleting strategy {strategy_id} from database: {exc}")
        
        # Step 3: Delete from Redis
        if self.redis and self.redis.enabled:
            try:
                self.redis.delete_strategy(strategy_id)
                self.redis.delete_trades(strategy_id)
            except Exception as exc:
                logger.warning(f"Error deleting strategy {strategy_id} from Redis: {exc}")
        
        # Step 4: Remove from in-memory cache
        self._strategies.pop(strategy_id, None)
        self._trades.pop(strategy_id, None)
        self._tasks.pop(strategy_id, None)  # Should already be removed by stop(), but just in case
        
        logger.info(f"✅ Strategy {strategy_id} ({summary.name}) deleted permanently")

    def list_strategies(self) -> list[StrategySummary]:
        """List all strategies.
        
        In multi-user mode, loads from database via StrategyService.
        In single-user mode, returns in-memory strategies.
        """
        # Multi-user mode: load from database if available
        if self.strategy_service and self.user_id:
            try:
                strategies = self.strategy_service.list_strategies(self.user_id)
                # Update in-memory cache
                for summary in strategies:
                    self._strategies[summary.id] = summary
                return strategies
            except Exception as exc:
                logger.warning(f"Failed to load strategies from database: {exc}, falling back to in-memory")
        
        # Single-user mode or fallback: return in-memory strategies
        return list(self._strategies.values())
    
    def get_trades(self, strategy_id: str) -> List[OrderResponse]:
        """Get all executed trades for a strategy.
        
        In multi-user mode, loads from database via TradeService.
        In single-user mode, returns in-memory trades.
        """
        # Multi-user mode: load from database if available
        if self.trade_service and self.user_id and self.strategy_service:
            try:
                # Get strategy UUID from database
                db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, strategy_id)
                if db_strategy:
                    trades = self.trade_service.get_strategy_trades(
                        user_id=self.user_id,
                        strategy_id=db_strategy.id,
                        limit=1000
                    )
                    # Update in-memory cache
                    self._trades[strategy_id] = trades
                    return trades
            except Exception as e:
                logger.warning(f"Failed to load trades from database: {e}, falling back to in-memory")
        
        # Single-user mode or fallback: return in-memory trades
        return self._trades.get(strategy_id, [])

    def calculate_strategy_stats(self, strategy_id: str) -> StrategyStats:
        """Calculate statistics for a specific strategy.
        
        Raises:
            StrategyNotFoundError: If strategy does not exist
        """
        if strategy_id not in self._strategies:
            raise StrategyNotFoundError(strategy_id)
        
        strategy = self._strategies[strategy_id]
        
        # Ensure trades are loaded (from Redis if available, otherwise from memory)
        self._ensure_trades_loaded(strategy_id)
        
        trades = self._trades.get(strategy_id, [])
        
        # Log data source for transparency
        redis_status = "Redis" if (self.redis and self.redis.enabled) else "in-memory only"
        logger.debug(
            f"Calculating stats for {strategy_id} using {len(trades)} trades from {redis_status}"
        )
        
        # Calculate basic stats
        total_trades = len(trades)
        
        # Track positions to calculate PnL correctly for both LONG and SHORT
        # In One-Way mode: net position can be LONG (positive), SHORT (negative), or flat (zero)
        completed_trades = []
        position_queue = []  # List of (quantity, entry_price, side) tuples
        
        for trade in trades:
            entry_price = trade.avg_price or trade.price
            quantity = trade.executed_qty
            side = trade.side
            
            if side == "BUY":
                if position_queue and position_queue[0][2] == "SHORT":
                    # Closing or reducing SHORT position
                    remaining_qty = quantity
                    while remaining_qty > 0 and position_queue and position_queue[0][2] == "SHORT":
                        short_entry = position_queue[0]
                        short_qty = short_entry[0]
                        short_price = short_entry[1]
                        
                        if short_qty <= remaining_qty:
                            # Close entire SHORT position
                            close_qty = short_qty
                            position_queue.pop(0)
                        else:
                            # Partial close
                            close_qty = remaining_qty
                            position_queue[0] = (short_qty - remaining_qty, short_price, "SHORT")
                        
                        # PnL for SHORT: entry_price - exit_price (profit when price drops)
                        pnl = (short_price - entry_price) * close_qty
                        completed_trades.append({
                            "pnl": pnl,
                            "quantity": close_qty,
                            "side": "SHORT"
                        })
                        remaining_qty -= close_qty
                    
                    # If remaining quantity after closing SHORT, open LONG
                    if remaining_qty > 0:
                        position_queue.append((remaining_qty, entry_price, "LONG"))
                else:
                    # Opening or adding to LONG position
                    position_queue.append((quantity, entry_price, "LONG"))
            
            elif side == "SELL":
                if position_queue and position_queue[0][2] == "LONG":
                    # Closing or reducing LONG position
                    remaining_qty = quantity
                    while remaining_qty > 0 and position_queue and position_queue[0][2] == "LONG":
                        long_entry = position_queue[0]
                        long_qty = long_entry[0]
                        long_price = long_entry[1]
                        
                        if long_qty <= remaining_qty:
                            # Close entire LONG position
                            close_qty = long_qty
                            position_queue.pop(0)
                        else:
                            # Partial close
                            close_qty = remaining_qty
                            position_queue[0] = (long_qty - remaining_qty, long_price, "LONG")
                        
                        # PnL for LONG: exit_price - entry_price
                        pnl = (entry_price - long_price) * close_qty
                        completed_trades.append({
                            "pnl": pnl,
                            "quantity": close_qty,
                            "side": "LONG"
                        })
                        remaining_qty -= close_qty
                    
                    # If remaining quantity after closing LONG, open SHORT
                    if remaining_qty > 0:
                        position_queue.append((remaining_qty, entry_price, "SHORT"))
                else:
                    # Opening or adding to SHORT position
                    position_queue.append((quantity, entry_price, "SHORT"))
        
        # Calculate PnL statistics
        total_pnl = sum(t["pnl"] for t in completed_trades)
        winning_trades = len([t for t in completed_trades if t["pnl"] > 0])
        losing_trades = len([t for t in completed_trades if t["pnl"] < 0])
        win_rate = (winning_trades / len(completed_trades) * 100) if completed_trades else 0
        avg_profit_per_trade = total_pnl / len(completed_trades) if completed_trades else 0
        
        largest_win = max((t["pnl"] for t in completed_trades), default=0)
        largest_loss = min((t["pnl"] for t in completed_trades), default=0)
        
        # Get last trade timestamp - try to get from order_id or use current time
        last_trade_at = None
        if trades:
            # If trades have timestamps, use the latest; otherwise use current time
            last_trade_at = datetime.now(timezone.utc)
        
        logger.debug(
            f"Stats for {strategy_id}: {len(completed_trades)} completed trades, "
            f"total_pnl={total_pnl:.4f}, win_rate={win_rate:.2f}%"
        )
        
        return StrategyStats(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            symbol=strategy.symbol,
            total_trades=total_trades,
            completed_trades=len(completed_trades),
            total_pnl=round(total_pnl, 4),
            win_rate=round(win_rate, 2),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_profit_per_trade=round(avg_profit_per_trade, 4),
            largest_win=round(largest_win, 4),
            largest_loss=round(largest_loss, 4),
            created_at=strategy.created_at,
            last_trade_at=last_trade_at
        )
    
    def _ensure_trades_loaded(self, strategy_id: str) -> None:
        """Ensure trades for a strategy are available.
        
        Trades are always stored in memory (self._trades). If Redis is enabled,
        this method will attempt to load trades from Redis if they're not already
        in memory (e.g., after server restart). If Redis is disabled, trades are
        only available in memory during the current server session.
        """
        # Check if trades are already in memory
        if strategy_id in self._trades:
            trades_count = len(self._trades[strategy_id])
            logger.debug(
                f"Using {trades_count} in-memory trades for {strategy_id} "
                f"(Redis: {'enabled' if self.redis and self.redis.enabled else 'disabled'})"
            )
            return
        
        # If Redis is disabled, trades are only in memory (will be empty after restart)
        if not self.redis or not self.redis.enabled:
            logger.debug(
                f"No trades in memory for {strategy_id} and Redis is disabled. "
                f"Trades will only be available during current server session."
            )
            return
        
        # Try to load from Redis (e.g., after server restart)
        try:
            trades_data = self.redis.get_trades(strategy_id)
            if trades_data:
                trades = []
                for trade_data in trades_data:
                    try:
                        trade = OrderResponse(**trade_data)
                        # Filter out invalid trades (status NEW with zero execution)
                        if trade.status == "NEW" and trade.executed_qty == 0:
                            logger.debug(
                                f"Skipping invalid trade {trade.order_id} for {strategy_id}: "
                                f"status=NEW with zero execution"
                            )
                            continue
                        trades.append(trade)
                    except Exception as exc:
                        logger.warning(
                            f"Failed to parse trade data for {strategy_id}: {exc}, "
                            f"data: {trade_data}"
                        )
                        continue
                if trades:
                    self._trades[strategy_id] = trades
                    logger.info(f"Loaded {len(trades)} trades for {strategy_id} from Redis")
            else:
                logger.debug(f"No trades found in Redis for {strategy_id}")
        except Exception as exc:
            logger.warning(f"Failed to load trades for {strategy_id} from Redis: {exc}")

    def calculate_overall_stats(self) -> OverallStats:
        """Calculate overall statistics across all strategies."""
        all_stats = []
        for strategy_id in self._strategies.keys():
            try:
                stats = self.calculate_strategy_stats(strategy_id)
                all_stats.append(stats)
            except Exception as exc:
                logger.warning(f"Error calculating stats for strategy {strategy_id}: {exc}")
                continue
        
        total_strategies = len(self._strategies)
        active_strategies = len([s for s in self._strategies.values() if s.status == StrategyState.running])
        
        total_trades = sum(s.total_trades for s in all_stats)
        completed_trades = sum(s.completed_trades for s in all_stats)
        total_pnl = sum(s.total_pnl for s in all_stats)
        
        all_winning = sum(s.winning_trades for s in all_stats)
        all_losing = sum(s.losing_trades for s in all_stats)
        win_rate = (all_winning / (all_winning + all_losing) * 100) if (all_winning + all_losing) > 0 else 0
        avg_profit_per_trade = total_pnl / completed_trades if completed_trades > 0 else 0
        
        # Find best and worst performing strategies
        best_strategy = max(all_stats, key=lambda s: s.total_pnl, default=None)
        worst_strategy = min(all_stats, key=lambda s: s.total_pnl, default=None)
        
        return OverallStats(
            total_strategies=total_strategies,
            active_strategies=active_strategies,
            total_trades=total_trades,
            completed_trades=completed_trades,
            total_pnl=round(total_pnl, 4),
            win_rate=round(win_rate, 2),
            winning_trades=all_winning,
            losing_trades=all_losing,
            avg_profit_per_trade=round(avg_profit_per_trade, 4),
            best_performing_strategy=best_strategy.strategy_name if best_strategy else None,
            worst_performing_strategy=worst_strategy.strategy_name if worst_strategy else None
        )

    async def _run_loop(
        self, 
        strategy: Strategy, 
        summary: StrategySummary,
        risk: Optional[RiskManager] = None,
        executor: Optional[OrderExecutor] = None
    ) -> None:
        # Use account-specific risk/executor if provided, otherwise fall back to defaults
        account_id = summary.account_id or "default"
        account_client = self._get_account_client(account_id)
        account_risk = risk or self.default_risk or RiskManager(client=account_client)
        account_executor = executor or self.default_executor or OrderExecutor(client=account_client)
        logger.info(f"Starting loop for {summary.id} (account: {account_id})")
        try:
            while True:
                # CRITICAL ORDER: Sync with Binance BEFORE evaluating strategy
                # This ensures strategy.evaluate() uses correct state, not stale state
                # 
                # Flow: Binance → summary → strategy → evaluate → execute
                # 
                # 1) First: Sync summary from Binance reality
                await self._update_position_info(summary)
                
                # 2) Then: Sync strategy internal state from summary/Binance
                # BUG FIX 1: This prevents desync when Binance native TP/SL orders close positions
                try:
                    strategy.sync_position_state(
                        position_side=summary.position_side,
                        entry_price=summary.entry_price,
                    )
                except Exception as exc:
                    logger.warning(
                        f"[{summary.id}] Failed to sync strategy position state: {exc}. "
                        f"This may cause strategy state desync."
                    )
                
                # 3) Now evaluate using **correct synced state**
                # Strategy now knows the real Binance position before making decisions
                signal = await strategy.evaluate()
                summary.last_signal = signal.action  # type: ignore[assignment]
                
                # Log all signals for debugging
                logger.info(
                    f"[{summary.id}] Signal: {signal.action} | "
                    f"Symbol: {signal.symbol} | "
                    f"Price: {signal.price} | "
                    f"Confidence: {signal.confidence} | "
                    f"Exit Reason: {signal.exit_reason or 'N/A'}"
                )
                
                # 4) Update current price for UI/stats (not critical to logic)
                try:
                    summary.current_price = account_client.get_price(summary.symbol)
                except Exception as exc:
                    logger.warning(f"Failed to get current price for {summary.symbol}: {exc}")
                
                # 5) Check PnL thresholds and notify if reached
                if self.notifications and summary.unrealized_pnl is not None:
                    await self.notifications.check_and_notify_pnl_threshold(
                        summary,
                        summary.unrealized_pnl,
                    )
                
                # 6) Execute order based on synced state + fresh signal
                # CRITICAL: Pass account-specific risk and executor to ensure orders go to correct account
                # Also pass strategy instance so we can sync state immediately after order execution
                await self._execute(signal, summary, strategy=strategy, risk=account_risk, executor=account_executor)
                await asyncio.sleep(strategy.context.interval_seconds)
        except asyncio.CancelledError:
            # Get final PnL before sending notification
            final_pnl = None
            if summary.unrealized_pnl is not None:
                final_pnl = summary.unrealized_pnl
            
            # Log strategy cancellation
            account_id = summary.account_id or "default"
            account_name = self.client_manager.get_account_config(account_id)
            account_display = account_name.name if account_name else account_id
            pnl_str = f" | Final PnL: ${final_pnl:.2f}" if final_pnl is not None else ""
            logger.info(
                f"⏹️ Strategy CANCELLED: {summary.id} ({summary.name}) | "
                f"Symbol: {summary.symbol} | Account: {account_id} ({account_display})"
                f"{pnl_str} | Reason: Task cancelled"
            )
            
            # Send notification that strategy stopped
            if self.notifications:
                asyncio.create_task(
                    self.notifications.notify_strategy_stopped(
                        summary,
                        reason="Strategy cancelled",
                        final_pnl=final_pnl,
                    )
                )
            
            await strategy.teardown()
            raise
        except Exception as exc:
            summary.status = StrategyState.error
            self._save_to_redis(summary.id, summary)
            
            # Log strategy failure with details
            account_id = summary.account_id or "default"
            account_name = self.client_manager.get_account_config(account_id)
            account_display = account_name.name if account_name else account_id
            logger.error(
                f"❌ Strategy FAILED: {summary.id} ({summary.name}) | "
                f"Symbol: {summary.symbol} | Account: {account_id} ({account_display}) | "
                f"Error: {type(exc).__name__}: {exc}"
            )
            logger.exception(f"Strategy {summary.id} failed: {exc}")
            
            # Send notification about strategy error
            if self.notifications:
                asyncio.create_task(
                    self.notifications.notify_strategy_error(
                        summary,
                        exc,
                        error_type=type(exc).__name__,
                    )
                )
        finally:
            # CRITICAL: Always remove task from _tasks when loop exits
            # This prevents dead tasks from counting toward concurrent limit
            self._tasks.pop(summary.id, None)
            logger.debug(f"Removed strategy {summary.id} from active tasks")
    
    def _load_from_database(self) -> None:
        """Load all strategies from database via StrategyService (multi-user mode)."""
        if not self.strategy_service or not self.user_id:
            return
        
        try:
            strategies = self.strategy_service.list_strategies(self.user_id)
            logger.info(f"Loading {len(strategies)} strategies from database for user {self.user_id}")
            
            for summary in strategies:
                self._strategies[summary.id] = summary
                # Also cache in Redis for fast access
                if self.redis:
                    self._save_to_redis(summary.id, summary)
            
            running_count = len([s for s in self._strategies.values() if s.status == StrategyState.running])
            logger.info(
                f"Successfully loaded {len(strategies)} strategies from database. "
                f"Strategies in memory: {len(self._strategies)}, "
                f"Running strategies (to be restored): {running_count}"
            )
        except Exception as exc:
            logger.error(f"Failed to load strategies from database: {exc}", exc_info=True)
    
    def _load_from_redis(self) -> None:
        """Load all strategies and trades from Redis on startup."""
        if not self.redis or not self.redis.enabled:
            logger.info("Redis not enabled, skipping load from Redis")
            return
        
        try:
            # Load all strategies
            strategies_data = self.redis.get_all_strategies()
            logger.info(f"Loading {len(strategies_data)} strategies from Redis")
            
            loaded_count = 0
            trades_loaded_count = 0
            for strategy_id, data in strategies_data.items():
                try:
                    # Convert datetime strings back to datetime objects
                    if "created_at" in data and isinstance(data["created_at"], str):
                        data["created_at"] = datetime.fromisoformat(data["created_at"])
                    if "last_trade_at" in data and isinstance(data["last_trade_at"], str):
                        data["last_trade_at"] = datetime.fromisoformat(data["last_trade_at"])
                    
                    # Ensure account_id exists (for backward compatibility with old strategies)
                    if "account_id" not in data or data.get("account_id") is None:
                        data["account_id"] = "default"
                    
                    # Reconstruct StrategySummary from dict
                    summary = StrategySummary(**data)
                    self._strategies[strategy_id] = summary
                    loaded_count += 1
                    
                    # Load trades for this strategy
                    trades_data = self.redis.get_trades(strategy_id)
                    if trades_data:
                        trades = []
                        for trade_data in trades_data:
                            try:
                                # Handle any datetime fields if present
                                if "created_at" in trade_data and isinstance(trade_data["created_at"], str):
                                    trade_data["created_at"] = datetime.fromisoformat(trade_data["created_at"])
                                if "timestamp" in trade_data and isinstance(trade_data["timestamp"], str):
                                    trade_data["timestamp"] = datetime.fromisoformat(trade_data["timestamp"])
                                if "update_time" in trade_data and isinstance(trade_data["update_time"], str):
                                    trade_data["update_time"] = datetime.fromisoformat(trade_data["update_time"])
                                trades.append(OrderResponse(**trade_data))
                            except Exception as trade_exc:
                                logger.warning(f"Failed to load trade for strategy {strategy_id}: {trade_exc}")
                                continue
                        if trades:
                            self._trades[strategy_id] = trades
                            trades_loaded_count += len(trades)
                            logger.debug(f"Loaded {len(trades)} trades for strategy {strategy_id} from Redis")
                    
                    logger.debug(f"Loaded strategy {strategy_id} from Redis (status: {summary.status.value})")
                except Exception as exc:
                    logger.warning(f"Failed to load strategy {strategy_id} from Redis: {exc}", exc_info=True)
                    continue
            
            running_count = len([s for s in self._strategies.values() if s.status == StrategyState.running])
            logger.info(
                f"Successfully loaded {loaded_count} strategies and {trades_loaded_count} trades from Redis. "
                f"Strategies in memory: {len(self._strategies)}, "
                f"Running strategies (to be restored): {running_count}"
            )
        except Exception as exc:
            logger.error(f"Failed to load strategies from Redis: {exc}", exc_info=True)
    
    async def restore_running_strategies(self) -> None:
        """Restore and start all strategies that were running before server restart.
        
        This should be called after strategies are loaded from Redis/database.
        It will automatically start any strategy that has status == StrategyState.running
        but doesn't have an active asyncio task.
        """
        from app.core.exceptions import StrategyNotFoundError, StrategyAlreadyRunningError, MaxConcurrentStrategiesError
        
        running_strategies = [
            (strategy_id, summary)
            for strategy_id, summary in self._strategies.items()
            if summary.status == StrategyState.running and strategy_id not in self._tasks
        ]
        
        if not running_strategies:
            logger.info("No running strategies to restore")
            return
        
        logger.info(f"Restoring {len(running_strategies)} running strategies after server restart...")
        
        restored_count = 0
        failed_count = 0
        
        for strategy_id, summary in running_strategies:
            try:
                # Clean up any dead tasks before checking limit
                self._cleanup_dead_tasks()
                
                # Check concurrent limit
                if len(self._tasks) >= self.max_concurrent:
                    logger.warning(
                        f"Cannot restore strategy {strategy_id}: max concurrent strategies ({self.max_concurrent}) reached. "
                        f"Please stop some strategies and restart manually."
                    )
                    # Mark as stopped since we can't start it
                    summary.status = StrategyState.stopped
                    # Update database FIRST (source of truth), then Redis
                    if self.strategy_service and self.user_id:
                        try:
                            self.strategy_service.update_strategy(
                                user_id=self.user_id,
                                strategy_id=strategy_id,
                                status=StrategyState.stopped.value
                            )
                            # Only save to Redis after database update succeeds
                            self._save_to_redis(strategy_id, summary)
                        except Exception as e:
                            logger.error(f"Failed to update strategy {strategy_id} status in database: {e}")
                            # Don't update Redis if database update failed
                    else:
                        # No database mode - save to Redis only
                        self._save_to_redis(strategy_id, summary)
                    failed_count += 1
                    continue
                
                # Get account-specific client
                account_id = getattr(summary, 'account_id', 'default') or 'default'
                account_client = self._get_account_client(account_id)
                if not account_client:
                    logger.error(f"Cannot restore strategy {strategy_id}: Binance client not found for account '{account_id}'")
                    summary.status = StrategyState.stopped
                    # Update database FIRST (source of truth), then Redis
                    if self.strategy_service and self.user_id:
                        try:
                            self.strategy_service.update_strategy(
                                user_id=self.user_id,
                                strategy_id=strategy_id,
                                status=StrategyState.stopped.value
                            )
                            # Only save to Redis after database update succeeds
                            self._save_to_redis(strategy_id, summary)
                        except Exception as e:
                            logger.error(f"Failed to update strategy {strategy_id} status in database: {e}")
                            # Don't update Redis if database update failed
                    else:
                        # No database mode - save to Redis only
                        self._save_to_redis(strategy_id, summary)
                    failed_count += 1
                    continue
                
                # Create account-specific risk manager and executor
                account_risk = RiskManager(client=account_client)
                account_executor = OrderExecutor(client=account_client)
                
                # For backward compatibility: if ema_crossover type, set default 5/20 EMA
                params = summary.params.model_dump()
                if summary.strategy_type == StrategyType.ema_crossover:
                    if "ema_fast" not in params or params.get("ema_fast") == 8:
                        params["ema_fast"] = 5
                    if "ema_slow" not in params or params.get("ema_slow") == 21:
                        params["ema_slow"] = 20
                    # Also set default TP/SL if not specified
                    if "take_profit_pct" not in params:
                        params["take_profit_pct"] = 0.005  # 0.5%
                    if "stop_loss_pct" not in params:
                        params["stop_loss_pct"] = 0.003  # 0.3%
                
                context = StrategyContext(
                    id=summary.id,
                    name=summary.name,
                    symbol=summary.symbol,
                    leverage=summary.leverage,
                    risk_per_trade=summary.risk_per_trade,
                    params=params,
                    interval_seconds=summary.params.interval_seconds,
                    metadata={},
                )
                strategy = self.registry.build(summary.strategy_type, context, account_client)
                task = asyncio.create_task(self._run_loop(strategy, summary, account_risk, account_executor))
                self._tasks[strategy_id] = task
                
                # Status is already "running", ensure it's saved to database FIRST, then Redis
                # Update database FIRST (source of truth), then Redis
                if self.strategy_service and self.user_id:
                    try:
                        self.strategy_service.update_strategy(
                            user_id=self.user_id,
                            strategy_id=strategy_id,
                            status=StrategyState.running.value
                        )
                        # Only save to Redis after database update succeeds
                        self._save_to_redis(strategy_id, summary)
                    except Exception as e:
                        logger.error(f"Failed to update strategy {strategy_id} status in database: {e}")
                        # Don't update Redis if database update failed - prevents inconsistency
                else:
                    # No database mode - save to Redis only (backward compatibility)
                    self._save_to_redis(strategy_id, summary)
                
                account_name = self.client_manager.get_account_config(account_id)
                account_display = account_name.name if account_name else account_id
                logger.info(
                    f"✅ Strategy RESTORED: {summary.id} ({summary.name}) | "
                    f"Symbol: {summary.symbol} | Type: {summary.strategy_type.value} | "
                    f"Leverage: {summary.leverage}x | Account: {account_id} ({account_display})"
                )
                restored_count += 1
                
            except Exception as exc:
                logger.error(f"Failed to restore strategy {strategy_id}: {exc}", exc_info=True)
                # Mark as stopped since restoration failed
                summary.status = StrategyState.stopped
                # Update database FIRST (source of truth), then Redis
                if self.strategy_service and self.user_id:
                    try:
                        self.strategy_service.update_strategy(
                            user_id=self.user_id,
                            strategy_id=strategy_id,
                            status=StrategyState.stopped.value
                        )
                        # Only save to Redis after database update succeeds
                        self._save_to_redis(strategy_id, summary)
                    except Exception as e:
                        logger.error(f"Failed to update strategy {strategy_id} status in database: {e}")
                        # Don't update Redis if database update failed
                else:
                    # No database mode - save to Redis only
                    self._save_to_redis(strategy_id, summary)
                failed_count += 1
        
        logger.info(
            f"Strategy restoration complete: {restored_count} restored, {failed_count} failed. "
            f"Total running strategies: {len(self._tasks)}"
        )
    
    def _save_to_redis(self, strategy_id: str, summary: StrategySummary) -> None:
        """Save strategy to Redis."""
        if not self.redis or not self.redis.enabled:
            return
        
        try:
            # Convert StrategySummary to dict
            strategy_data = summary.model_dump(mode='json')
            self.redis.save_strategy(strategy_id, strategy_data)
        except Exception as exc:
            logger.warning(f"Failed to save strategy {strategy_id} to Redis: {exc}")
    
    def _save_trades_to_redis(self, strategy_id: str) -> None:
        """Save trades for a strategy to Redis."""
        if not self.redis or not self.redis.enabled:
            return
        
        try:
            trades = self._trades.get(strategy_id, [])
            # Convert OrderResponse to dict
            trades_data = [trade.model_dump(mode='json') for trade in trades]
            self.redis.save_trades(strategy_id, trades_data)
        except Exception as exc:
            logger.warning(f"Failed to save trades for {strategy_id} to Redis: {exc}")

    async def _execute(
        self, 
        signal: StrategySignal, 
        summary: StrategySummary,
        strategy: Optional[Strategy] = None,
        risk: Optional[RiskManager] = None,
        executor: Optional[OrderExecutor] = None
    ) -> None:
        # Use account-specific risk/executor if provided, otherwise fall back to defaults
        account_id = summary.account_id or "default"
        account_client = self._get_account_client(account_id)
        account_risk = risk or self.default_risk or RiskManager(client=account_client)
        account_executor = executor or self.default_executor or OrderExecutor(client=account_client)
        
        # Log account being used for order execution (critical for multi-account debugging)
        logger.debug(
            f"[{summary.id}] Executing order using account: {account_id} "
            f"(strategy account_id: {summary.account_id})"
        )
        
        if signal.action == "HOLD":
            logger.debug(
                f"[{summary.id}] HOLD signal - skipping order execution | "
                f"Position: {summary.position_side or 'FLAT'} | "
                f"Price: {signal.price}"
            )
            return
        
        # CRITICAL: Leverage in Binance is PER SYMBOL, not per strategy.
        # Binance defaults to 20x leverage if not explicitly set.
        # We MUST ensure leverage is explicitly set before every order to avoid accidental 20x.
        
        # Validate leverage is present and valid (should never be None due to model validation)
        if summary.leverage is None or not (1 <= summary.leverage <= 50):
            logger.error(
                f"[{summary.id}] CRITICAL: Invalid or missing leverage for {summary.symbol}: {summary.leverage}"
            )
            raise InvalidLeverageError(
                leverage=summary.leverage or 0,
                reason=f"Leverage must be explicitly set (1-50) to avoid Binance's default 20x leverage for {summary.symbol}"
            )
        
        try:
            current_leverage = account_client.get_current_leverage(summary.symbol)
            if current_leverage != summary.leverage:
                logger.warning(
                    f"[{summary.id}] Leverage mismatch detected for {summary.symbol}: "
                    f"current={current_leverage}x (may be Binance default), target={summary.leverage}x. "
                    f"Resetting to {summary.leverage}x"
                )
                account_client.adjust_leverage(summary.symbol, summary.leverage)
            elif current_leverage is None:
                # No position yet, set leverage proactively to prevent Binance default
                logger.info(
                    f"[{summary.id}] Setting leverage {summary.leverage}x for {summary.symbol} "
                    f"(no existing position - preventing Binance 20x default)"
                )
                account_client.adjust_leverage(summary.symbol, summary.leverage)
            else:
                logger.debug(
                    f"[{summary.id}] Leverage already correct: {current_leverage}x for {summary.symbol}"
                )
        except BinanceAPIError as exc:
            # Re-raise Binance API errors as-is
            raise
        except Exception as exc:
            error_msg = (
                f"[{summary.id}] CRITICAL: Failed to verify/set leverage {summary.leverage}x for {summary.symbol}: {exc}. "
                "Order execution aborted to prevent accidental 20x leverage."
            )
            logger.error(error_msg)
            raise BinanceAPIError(
                error_msg,
                details={"strategy_id": summary.id, "symbol": summary.symbol, "leverage": summary.leverage}
            ) from exc
        
        # Get current position from Binance to ensure accurate size for closing
        current_position = account_client.get_open_position(summary.symbol)
        current_side = summary.position_side
        current_size = float(summary.position_size or 0)
        
        # If Binance has a position, use that size (more accurate than our tracking)
        if current_position and abs(float(current_position["positionAmt"])) > 0:
            position_amt = float(current_position["positionAmt"])
            current_size = abs(position_amt)
            current_side = "LONG" if position_amt > 0 else "SHORT"
        
        is_closing_long = current_side == "LONG" and current_size > 0 and signal.action == "SELL"
        is_closing_short = current_side == "SHORT" and current_size > 0 and signal.action == "BUY"
        force_close_quantity = None
        reduce_only_override: bool | None = None

        try:
            if is_closing_long or is_closing_short:
                price = signal.price or account_client.get_price(signal.symbol)
                force_close_quantity = current_size
                sizing = PositionSizingResult(
                    quantity=force_close_quantity,
                    notional=force_close_quantity * price,
                )
                reduce_only_override = True
                logger.info(
                    f"[{summary.id}] Closing entire position: {current_side} {current_size} {summary.symbol} "
                    f"(reduce_only=True)"
                )
            else:
                # Log sizing parameters for debugging
                price = signal.price or account_client.get_price(signal.symbol)
                logger.info(
                    f"[{summary.id}] Calculating position size: "
                    f"fixed_amount={summary.fixed_amount}, risk_per_trade={summary.risk_per_trade}, "
                    f"price={price}, symbol={signal.symbol}"
                )
                sizing = account_risk.size_position(
                    symbol=signal.symbol, 
                    risk_per_trade=summary.risk_per_trade, 
                    price=price,
                    fixed_amount=summary.fixed_amount
                )
                logger.info(
                    f"[{summary.id}] Position sizing result: qty={sizing.quantity}, notional={sizing.notional:.2f} USDT"
                )
        except (ValueError, PositionSizingError) as exc:
            # Handle position sizing errors gracefully
            error_msg = f"[{summary.id}] Position sizing failed: {exc}"
            logger.error(error_msg)
            logger.error(f"[{summary.id}] Strategy will skip this signal. Please update strategy configuration.")
            # Convert ValueError to PositionSizingError if not already
            if isinstance(exc, ValueError):
                raise PositionSizingError(
                    str(exc),
                    symbol=signal.symbol,
                    details={"strategy_id": summary.id, "fixed_amount": summary.fixed_amount, "risk_per_trade": summary.risk_per_trade}
                ) from exc
            raise
        
        try:
            order_response = account_executor.execute(
                signal=signal,
                sizing=sizing,
                reduce_only_override=reduce_only_override,
            )
        except (OrderExecutionError, BinanceAPIError) as exc:
            # Log and re-raise API errors - they should be handled by exception handlers
            logger.error(
                f"[{summary.id}] Order execution failed: {exc.message if hasattr(exc, 'message') else exc}"
            )
            raise
        except Exception as exc:
            # Wrap unexpected errors
            logger.exception(f"[{summary.id}] Unexpected error during order execution: {exc}")
            raise OrderExecutionError(
                f"Unexpected error executing order: {exc}",
                symbol=signal.symbol,
                details={"strategy_id": summary.id, "signal_action": signal.action}
            ) from exc
        
        if order_response:
            # Only track filled orders (or orders with execution data)
            # Orders with status "NEW" and zero execution data shouldn't be tracked
            if order_response.status == "NEW" and order_response.executed_qty == 0:
                logger.warning(
                    f"[{summary.id}] Order {order_response.order_id} status is NEW with zero execution. "
                    f"Skipping trade tracking. Order may not be filled yet."
                )
            else:
                # Track the executed trade in memory (always, regardless of Redis)
                if summary.id not in self._trades:
                    self._trades[summary.id] = []
                
                # Store exit_reason from signal in the order response
                # Create a copy with exit_reason to preserve the original data
                order_with_exit_reason = order_response.model_copy(
                    update={"exit_reason": signal.exit_reason} if signal.exit_reason else {}
                )
                self._trades[summary.id].append(order_with_exit_reason)
                
                # Save to database if TradeService is available (multi-user mode)
                if self.trade_service and self.user_id:
                    try:
                        # Get strategy UUID from database
                        if self.strategy_service:
                            db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, summary.id)
                            if db_strategy:
                                self.trade_service.save_trade(
                                    user_id=self.user_id,
                                    strategy_id=db_strategy.id,
                                    order=order_with_exit_reason
                                )
                                logger.debug(f"Saved trade {order_with_exit_reason.order_id} to database")
                    except Exception as e:
                        logger.warning(f"Failed to save trade to database: {e}")
                
                # Log trade tracking with position direction and exit reason
                trades_count = len(self._trades[summary.id])
                redis_status = "enabled" if (self.redis and self.redis.enabled) else "disabled"
                db_status = "enabled" if (self.trade_service and self.user_id) else "disabled"
                exit_reason = signal.exit_reason or "N/A"
                position_direction = summary.position_side or "FLAT"
                logger.info(
                    f"[{summary.id}] 📝 Tracked trade: {order_response.side} {order_response.symbol} "
                    f"order_id={order_response.order_id} status={order_response.status} "
                    f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price:.8f} "
                    f"(position: {position_direction}, exit_reason: {exit_reason}, "
                    f"total trades: {trades_count}, Redis: {redis_status}, DB: {db_status})"
                )
                
                # Optionally save to Redis if enabled (for persistence across server restarts)
                self._save_trades_to_redis(summary.id)
            
            # Update entry price and position size
            if order_response.side == "BUY":
                if summary.position_side == "SHORT":
                    remaining = max(0.0, (summary.position_size or 0.0) - order_response.executed_qty)
                    summary.position_size = remaining
                    if remaining == 0:
                        summary.entry_price = None
                        summary.position_side = None
                else:
                    summary.entry_price = order_response.avg_price or order_response.price
                    summary.position_size = order_response.executed_qty
                    summary.position_side = "LONG"
            elif order_response.side == "SELL":
                if summary.position_side == "LONG":
                    remaining = max(0.0, (summary.position_size or 0.0) - order_response.executed_qty)
                    summary.position_size = remaining
                    if remaining == 0:
                        summary.entry_price = None
                        summary.position_side = None
                else:
                    summary.entry_price = order_response.avg_price or order_response.price
                    summary.position_size = order_response.executed_qty
                    summary.position_side = "SHORT"
            
            # Determine position direction and exit reason for logging
            position_direction = summary.position_side  # Current position before order
            exit_reason = signal.exit_reason or "UNKNOWN"
            
            # Determine if this is opening or closing
            is_opening_order = (
                (order_response.side == "BUY" and position_direction is None) or
                (order_response.side == "SELL" and position_direction is None)
            )
            is_closing_order = (
                (order_response.side == "SELL" and position_direction == "LONG") or
                (order_response.side == "BUY" and position_direction == "SHORT")
            )
            
            if is_opening_order:
                new_position = "LONG" if order_response.side == "BUY" else "SHORT"
                logger.info(
                    f"[{summary.id}] 🟢 OPEN {new_position} position: "
                    f"{order_response.side} {order_response.symbol} "
                    f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price:.8f}"
                )
            elif is_closing_order:
                logger.info(
                    f"[{summary.id}] 🔴 CLOSE {position_direction} position (reason: {exit_reason}): "
                    f"{order_response.side} {order_response.symbol} "
                    f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price:.8f}"
                )
            else:
                logger.info(
                    f"[{summary.id}] 📊 Trade executed: "
                    f"{order_response.side} {order_response.symbol} "
                    f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price:.8f} "
                    f"(position: {position_direction}, exit_reason: {exit_reason})"
                )
            
            # Place Binance native TP/SL orders when opening a new position
            # This ensures Binance handles exits even if bot crashes/hangs
            # BUG FIX 2: Check if existing TP/SL orders are actually still open on Binance
            # If they're already filled/cancelled, we should clear the meta and place new ones
            has_position = summary.position_size and summary.position_size > 0
            has_entry_price = summary.entry_price is not None
            tp_sl_meta = summary.meta.get("tp_sl_orders", {})
            tp_order_id = tp_sl_meta.get("tp_order_id")
            sl_order_id = tp_sl_meta.get("sl_order_id")
            
            # Check if stored order IDs are still valid (orders still exist on Binance)
            has_valid_orders = False
            if tp_order_id or sl_order_id:
                try:
                    # Use account-specific client to check orders
                    account_id = summary.account_id or "default"
                    account_client = self._get_account_client(account_id)
                    open_orders = account_client.get_open_orders(summary.symbol)
                    open_order_ids = {o.get("orderId") for o in open_orders}
                    has_valid_orders = (tp_order_id in open_order_ids) or (sl_order_id in open_order_ids)
                    
                    # If orders don't exist anymore, clear the stale metadata
                    if not has_valid_orders:
                        logger.info(
                            f"[{summary.id}] Stale TP/SL order IDs detected (orders no longer exist). "
                            f"Clearing metadata."
                        )
                        summary.meta["tp_sl_orders"] = {}
                        self._save_to_redis(summary.id, summary)
                except Exception as exc:
                    logger.warning(
                        f"[{summary.id}] Failed to verify TP/SL orders exist: {exc}. "
                        f"Assuming they exist for safety."
                    )
                    has_valid_orders = True  # Assume they exist if we can't verify
            
            is_opening = has_position and has_entry_price and not has_valid_orders and not reduce_only_override
            
            if is_opening:
                try:
                    await self._place_tp_sl_orders(summary, order_response)
                except Exception as exc:
                    logger.warning(
                        f"[{summary.id}] Failed to place TP/SL orders on Binance: {exc}. "
                        f"Strategy will still monitor TP/SL, but Binance native orders not active."
                    )
            
            # Cancel existing TP/SL orders if position was closed via our own order
            # Note: If position closed via Binance native TP/SL, cleanup is handled in _update_position_info()
            position_closed = summary.position_size == 0 or summary.position_side is None
            has_order_ids = bool(tp_order_id or sl_order_id)
            if position_closed and has_order_ids:
                try:
                    await self._cancel_tp_sl_orders(summary)
                except Exception as exc:
                    logger.warning(f"[{summary.id}] Failed to cancel TP/SL orders: {exc}")
            
            # CRITICAL: Sync strategy's internal state immediately after order execution
            # This ensures the strategy knows about position changes (especially for cooldown)
            # Without this, the strategy might not set cooldown until the next loop iteration
            if strategy:
                try:
                    # Update position info from Binance to ensure summary is accurate
                    await self._update_position_info(summary)
                    # Sync strategy's internal state with updated summary
                    # This is critical for cooldown - if position was closed, strategy needs to know immediately
                    strategy.sync_position_state(
                        position_side=summary.position_side,
                        entry_price=summary.entry_price,
                    )
                    
                    # CRITICAL: For range mean reversion, set entry_candle_time after successful order execution
                    # This ensures entry candle protection uses correct candle time, matching backtesting behavior
                    # Strategy may have set it when generating signal, but we update it after order execution
                    # to ensure it matches when position actually opened
                    if summary.position_side is not None and summary.entry_price is not None:
                        # Position was opened - ensure entry_candle_time is set correctly
                        if hasattr(strategy, 'last_closed_candle_time') and strategy.last_closed_candle_time is not None:
                            strategy.entry_candle_time = strategy.last_closed_candle_time
                            logger.debug(
                                f"[{summary.id}] Set entry_candle_time={strategy.entry_candle_time} "
                                f"after order execution (matches backtesting behavior)"
                            )
                        # If last_closed_candle_time is None, strategy will set it on next evaluation
                        # This is acceptable - entry candle protection will work from next candle
                    
                    # For range mean reversion, verify range state is preserved (for debugging)
                    from app.strategies.range_mean_reversion import RangeMeanReversionStrategy
                    if isinstance(strategy, RangeMeanReversionStrategy):
                        if hasattr(strategy, 'range_valid') and strategy.range_valid:
                            logger.debug(
                                f"[{summary.id}] Range state preserved after order execution: "
                                f"high={strategy.range_high}, low={strategy.range_low}, mid={strategy.range_mid}"
                            )
                    
                    logger.debug(
                        f"[{summary.id}] Synced strategy state after order execution: "
                        f"position={summary.position_side}, entry_price={summary.entry_price}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"[{summary.id}] Failed to sync strategy state after order execution: {exc}. "
                        f"Will sync at start of next loop iteration."
                    )
            else:
                # Fallback: update position info, strategy will sync at start of next loop
                try:
                    await self._update_position_info(summary)
                except Exception as exc:
                    logger.debug(f"[{summary.id}] Failed to update position info after order execution: {exc}")

    async def _place_tp_sl_orders(self, summary: StrategySummary, entry_order: OrderResponse) -> None:
        """Place Binance native TP/SL orders when opening a position.
        
        Args:
            summary: Strategy summary with position info
            entry_order: The entry order that opened the position
        """
        if not summary.entry_price or not summary.position_size or not summary.position_side:
            logger.debug(f"[{summary.id}] Cannot place TP/SL: missing position info")
            return
        
        # Get TP/SL percentages from strategy params
        take_profit_pct = summary.params.take_profit_pct
        stop_loss_pct = summary.params.stop_loss_pct
        
        # Calculate TP/SL prices
        if summary.position_side == "LONG":
            tp_price = summary.entry_price * (1 + take_profit_pct)
            sl_price = summary.entry_price * (1 - stop_loss_pct)
            tp_side = "SELL"  # Sell to close long
            sl_side = "SELL"  # Sell to close long
        else:  # SHORT
            tp_price = summary.entry_price * (1 - take_profit_pct)  # Inverted
            sl_price = summary.entry_price * (1 + stop_loss_pct)  # Inverted
            tp_side = "BUY"  # Buy to close short
            sl_side = "BUY"  # Buy to close short
        
        # Skip if trailing stop enabled (we'll handle it differently)
        if summary.params.trailing_stop_enabled:
            logger.info(
                f"[{summary.id}] Trailing stop enabled - skipping Binance native TP/SL orders. "
                f"Strategy will manage exits dynamically."
            )
            return
        
        logger.info(
            f"[{summary.id}] Placing Binance native TP/SL orders: "
            f"TP={tp_price:.8f} ({tp_side}), SL={sl_price:.8f} ({sl_side})"
        )
        
        # Get account-specific client
        account_id = summary.account_id or "default"
        account_client = self._get_account_client(account_id)
        
        tp_order_id = None
        sl_order_id = None
        
        try:
            # Place take profit order
            tp_response = account_client.place_take_profit_order(
                symbol=summary.symbol,
                side=tp_side,
                quantity=summary.position_size,
                stop_price=tp_price,
                close_position=True  # Close entire position
            )
            tp_order_id = tp_response.get("orderId")
            logger.info(f"[{summary.id}] TP order placed: orderId={tp_order_id}")
        except Exception as exc:
            # Extract underlying error details for better debugging
            error_details = self._extract_error_details(exc, "TP", summary, tp_price)
            logger.error(
                f"[{summary.id}] Failed to place TP order: {error_details}",
                exc_info=True
            )
        
        try:
            # Place stop loss order
            sl_response = account_client.place_stop_loss_order(
                symbol=summary.symbol,
                side=sl_side,
                quantity=summary.position_size,
                stop_price=sl_price,
                close_position=True  # Close entire position
            )
            sl_order_id = sl_response.get("orderId")
            logger.info(f"[{summary.id}] SL order placed: orderId={sl_order_id}")
        except Exception as exc:
            # Extract underlying error details for better debugging
            error_details = self._extract_error_details(exc, "SL", summary, sl_price)
            logger.error(
                f"[{summary.id}] Failed to place SL order: {error_details}",
                exc_info=True
            )
        
        # Store order IDs in meta for later cancellation
        if "tp_sl_orders" not in summary.meta:
            summary.meta["tp_sl_orders"] = {}
        summary.meta["tp_sl_orders"] = {
            "tp_order_id": tp_order_id,
            "sl_order_id": sl_order_id,
        }
        self._save_to_redis(summary.id, summary)
    
    async def _cancel_tp_sl_orders(self, summary: StrategySummary) -> None:
        """Cancel existing TP/SL orders when position is closed."""
        tp_sl_orders = summary.meta.get("tp_sl_orders", {})
        tp_order_id = tp_sl_orders.get("tp_order_id")
        sl_order_id = tp_sl_orders.get("sl_order_id")
        
        if not tp_order_id and not sl_order_id:
            return  # No orders to cancel
        
        logger.info(
            f"[{summary.id}] Cancelling TP/SL orders: TP={tp_order_id}, SL={sl_order_id}"
        )
        
        account_id = summary.account_id or "default"
        account_client = self._get_account_client(account_id)
        
        if tp_order_id:
            try:
                account_client.cancel_order(summary.symbol, tp_order_id)
                logger.info(f"[{summary.id}] Cancelled TP order: {tp_order_id}")
            except Exception as exc:
                logger.warning(f"[{summary.id}] Failed to cancel TP order {tp_order_id}: {exc}")
        
        if sl_order_id:
            try:
                account_client.cancel_order(summary.symbol, sl_order_id)
                logger.info(f"[{summary.id}] Cancelled SL order: {sl_order_id}")
            except Exception as exc:
                logger.warning(f"[{summary.id}] Failed to cancel SL order {sl_order_id}: {exc}")
        
        # Clear order IDs from meta
        if "tp_sl_orders" in summary.meta:
            summary.meta["tp_sl_orders"] = {}
            self._save_to_redis(summary.id, summary)
    
    async def _update_position_info(self, summary: StrategySummary) -> None:
        """Update position information and unrealized PnL for a strategy."""
        try:
            # Get account-specific client
            account_id = summary.account_id or "default"
            account_client = self._get_account_client(account_id)
            # Get current position from Binance
            position = account_client.get_open_position(summary.symbol)
            
            if position and abs(float(position["positionAmt"])) > 0:
                # Update position info from Binance
                position_amt = float(position["positionAmt"])
                summary.position_size = abs(position_amt)
                summary.entry_price = float(position["entryPrice"])
                summary.unrealized_pnl = float(position["unRealizedProfit"])
                summary.position_side = "LONG" if position_amt > 0 else "SHORT"
                # Update current price from mark price for consistency
                if "markPrice" in position:
                    summary.current_price = float(position["markPrice"])
                else:
                    # Fallback to getting current price if markPrice not available
                    try:
                        summary.current_price = account_client.get_price(summary.symbol)
                    except Exception:
                        pass  # Keep existing current_price if update fails
            else:
                # No open position
                position_was_closed = summary.position_size != 0  # Position was closed
                if position_was_closed:
                    summary.entry_price = None
                    summary.position_size = 0
                    summary.unrealized_pnl = 0
                    summary.position_side = None
                    
                    # BUG FIX 2: Clear TP/SL order IDs when position closes (even if via Binance native orders)
                    # This prevents TP/SL meta from getting stuck after exchange-side exit
                    has_existing_orders = bool(summary.meta.get("tp_sl_orders", {}).get("tp_order_id") or 
                                              summary.meta.get("tp_sl_orders", {}).get("sl_order_id"))
                    if has_existing_orders:
                        # Check if any TP/SL orders were filled (by checking if they're still open)
                        try:
                            open_orders = account_client.get_open_orders(summary.symbol)
                            open_order_ids = {o.get("orderId") for o in open_orders}
                            tp_order_id = summary.meta.get("tp_sl_orders", {}).get("tp_order_id")
                            sl_order_id = summary.meta.get("tp_sl_orders", {}).get("sl_order_id")
                            
                            tp_filled = tp_order_id and tp_order_id not in open_order_ids
                            sl_filled = sl_order_id and sl_order_id not in open_order_ids
                            
                            exit_reason = "TP" if tp_filled else ("SL" if sl_filled else "UNKNOWN")
                            logger.info(
                                f"[{summary.id}] 🔴 Position CLOSED via Binance native {exit_reason} order "
                                f"(TP_filled: {tp_filled}, SL_filled: {sl_filled}). "
                                f"Clearing TP/SL order metadata."
                            )
                        except Exception as exc:
                            logger.info(
                                f"[{summary.id}] 🔴 Position CLOSED (possibly via native TP/SL, unable to verify): {exc}. "
                                f"Clearing TP/SL order metadata."
                            )
                        # Try to cancel orders (they may already be filled/executed)
                        try:
                            await self._cancel_tp_sl_orders(summary)
                        except Exception as exc:
                            # Even if cancellation fails (orders already filled), clear the metadata
                            logger.debug(f"[{summary.id}] Error cancelling TP/SL orders (may already be filled): {exc}")
                            # Clear metadata regardless
                            if "tp_sl_orders" in summary.meta:
                                summary.meta["tp_sl_orders"] = {}
                                self._save_to_redis(summary.id, summary)
        except Exception as exc:
            logger.debug(f"Failed to update position info for {summary.symbol}: {exc}")
            # Calculate unrealized PnL manually if we have entry price and current price
            if summary.entry_price and summary.current_price and summary.position_size:
                # Update current price for manual calculation
                try:
                    summary.current_price = account_client.get_price(summary.symbol)
                except Exception as price_exc:
                    logger.debug(f"Failed to get current price for {summary.symbol}: {price_exc}")
                
                # Calculate unrealized PnL based on position side
                # LONG: profit when current_price > entry_price
                # SHORT: profit when current_price < entry_price
                if summary.position_side == "SHORT":
                    # For SHORT: (entry_price - current_price) * position_size
                    summary.unrealized_pnl = (summary.entry_price - summary.current_price) * summary.position_size
                else:
                    # For LONG: (current_price - entry_price) * position_size
                    summary.unrealized_pnl = (summary.current_price - summary.entry_price) * summary.position_size
            
            # Save updated summary to Redis (periodically, not every loop)
            # We'll save on state changes instead to reduce Redis writes

