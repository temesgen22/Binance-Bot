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
from app.services.strategy_registry import StrategyRegistry
from app.services.strategy_account_manager import StrategyAccountManager
from app.services.strategy_persistence import StrategyPersistence
from app.services.strategy_order_manager import StrategyOrderManager
from app.services.strategy_executor import StrategyExecutor
from app.services.strategy_statistics import StrategyStatistics
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from uuid import UUID
    from app.services.strategy_service import StrategyService
    from app.services.trade_service import TradeService


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
        
        # Initialize core components
        self.max_concurrent = max_concurrent
        self.redis = redis_storage
        self.notifications = notification_service
        self.strategy_service = strategy_service
        self.user_id = user_id
        self.trade_service: Optional["TradeService"] = None  # Will be set by dependency injection
        self._strategies: Dict[str, StrategySummary] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._trades: Dict[str, List[OrderResponse]] = {}  # Track trades per strategy
        self._cleanup_task: Optional[asyncio.Task] = None  # Periodic cleanup task
        self._cleanup_running: bool = False  # Flag to control cleanup loop
        
        # Hot-swap support: Track parameter versions and per-strategy locks
        self._params_versions: Dict[str, int] = {}  # Track parameter version for each strategy
        self._strategy_locks: Dict[str, asyncio.Lock] = {}  # Per-strategy locks for hot-swap
        
        # Concurrency safety: Lock to protect shared state (_tasks, _strategies, _trades)
        # This prevents race conditions when multiple async tasks access/modify these dictionaries
        self._lock = asyncio.Lock()
        
        # Track if we're using a directly provided client (for tests with mock clients)
        self._has_direct_client = client is not None and client_manager is None
        
        # Validate: if strategy_service is provided, user_id must be provided
        if strategy_service is not None and user_id is None:
            raise ValueError("user_id must be provided when strategy_service is provided")
        
        # Initialize modules
        self.registry = StrategyRegistry()
        
        # Initialize account manager
        self.account_manager = StrategyAccountManager(
            client=client,
            client_manager=self.client_manager,
            strategy_service=strategy_service,
            user_id=user_id,
            has_direct_client=self._has_direct_client,
        )
        
        # Initialize state manager (persistence)
        self.state_manager = StrategyPersistence(
            redis_storage=redis_storage,
            strategy_service=strategy_service,
            user_id=user_id,
            strategies=self._strategies,
            trades=self._trades,
            account_manager=self.account_manager,
        )
        
        # Initialize trade service if strategy_service and user_id are available
        if strategy_service and user_id and hasattr(strategy_service, 'db_service'):
            try:
                from app.services.trade_service import TradeService
                # Get the database session from strategy_service
                db_session = strategy_service.db_service.db
                # Create TradeService with database session and Redis storage
                self.trade_service = TradeService(db_session, redis_storage)
                logger.info(f"Initialized TradeService for user {user_id} - trades will be saved to database")
            except Exception as e:
                logger.warning(f"Failed to initialize TradeService: {e}. Trades will not be saved to database.")
                self.trade_service = None
        else:
            self.trade_service = None
            if strategy_service or user_id:
                logger.warning("TradeService not initialized: strategy_service or user_id missing. Trades will not be saved to database.")
        
        # Initialize order manager
        # Note: Factories will be created when needed (lazy initialization)
        # They can be set later if factories are provided from main.py
        self.order_manager = StrategyOrderManager(
            account_manager=self.account_manager,
            default_risk=risk,
            default_executor=executor,
            trade_service=self.trade_service,  # Pass initialized trade_service
            user_id=user_id,
            strategy_service=strategy_service,  # Pass strategy_service for database lookups
            redis_storage=redis_storage,
            strategies=self._strategies,
            trades=self._trades,
            lock=self._lock,
            notification_service=notification_service,  # Pass notification service for risk alerts
            strategy_runner=self,  # Pass self so order manager can pause strategies
            # Factories can be set later if needed - they're optional
            # portfolio_risk_manager_factory=...,
            # circuit_breaker_factory=...,
            # dynamic_sizing_factory=...,
        )
        
        # Initialize executor
        self.executor = StrategyExecutor(
            account_manager=self.account_manager,
            state_manager=self.state_manager,
            order_manager=self.order_manager,
            client_manager=self.client_manager,
            default_risk=risk,
            default_executor=executor,
            notification_service=notification_service,
            lock=self._lock,
        )
        
        # Initialize statistics
        self.statistics = StrategyStatistics(
            strategies=self._strategies,
            trades=self._trades,
            redis_storage=redis_storage,
            trade_service=self.trade_service,
            strategy_service=strategy_service,
            user_id=user_id,
        )
        
        # Load strategies on startup
        if strategy_service and user_id:
            # Multi-user mode: load from database via StrategyService
            self.state_manager.load_from_database()
        else:
            # Single-user mode: load from Redis (backward compatibility)
            self.state_manager.load_from_redis()
    
    def _get_account_client(self, account_id: str) -> BinanceClient:
        """Get client for an account (delegates to account_manager)."""
        return self.account_manager.get_account_client(account_id)
    
    # _update_strategy_in_db() removed - now handled by state_manager.update_strategy_in_db()

    async def restore_running_strategies(self) -> list[str]:
        """Restore all strategies that have status=running from database.
        
        This is called on startup to restore strategies that were running
        before the server was restarted. It respects max_concurrent limit.
        
        Returns:
            List of strategy IDs that were successfully restored
        """
        if not (self.strategy_service and self.user_id):
            logger.debug("Cannot restore running strategies: no strategy_service or user_id")
            return []
        
        restored_ids = []
        try:
            # Load all strategies from database
            self.state_manager.load_from_database()
            
            # Find all strategies with status=running
            # Use state_manager._strategies which is where load_from_database() puts them
            # They should be the same reference as self._strategies, but use state_manager to be safe
            running_strategies = [
                sid for sid, summary in self.state_manager._strategies.items()
                if summary.status == StrategyState.running
            ]
            # Note: Strategies with status 'stopped_by_risk' are NOT restored (they're effectively stopped)
            
            logger.info(f"Found {len(running_strategies)} strategies with status=running to restore")
            
            # Restore each strategy (respects max_concurrent limit)
            for strategy_id in running_strategies:
                try:
                    await self.start(strategy_id)
                    
                    # CRITICAL: Verify task is actually running after start
                    # Wait a moment for task to start, then check if it's still alive
                    await asyncio.sleep(0.5)  # 500ms to allow task to start
                    
                    # Check if task exists and is running
                    async with self._lock:
                        if strategy_id in self._tasks:
                            task = self._tasks[strategy_id]
                            if task.done():
                                # Task completed immediately - mark as error
                                exception = None
                                try:
                                    exception = task.exception()
                                except Exception:
                                    pass
                                
                                logger.error(
                                    f"Restored strategy {strategy_id} but task died immediately. "
                                    f"Exception: {exception}"
                                )
                                # Remove dead task and mark as error
                                del self._tasks[strategy_id]
                                self._strategies[strategy_id].status = StrategyState.error
                                self.state_manager.update_strategy_in_db(
                                    strategy_id,
                                    save_to_redis=True,
                                    status=StrategyState.error.value
                                )
                                # Don't add to restored_ids - restoration failed
                                continue
                            else:
                                # Task is running - restoration successful
                                logger.info(f"✅ Restored running strategy: {strategy_id} (task is active)")
                                restored_ids.append(strategy_id)
                        else:
                            # Task was never created - mark as error
                            logger.error(
                                f"Restored strategy {strategy_id} but task was not created"
                            )
                            self._strategies[strategy_id].status = StrategyState.error
                            self.state_manager.update_strategy_in_db(
                                strategy_id,
                                save_to_redis=True,
                                status=StrategyState.error.value
                            )
                            # Don't add to restored_ids - restoration failed
                            continue
                except MaxConcurrentStrategiesError:
                    logger.warning(
                        f"Cannot restore strategy {strategy_id}: max_concurrent limit reached. "
                        f"Will retry on next restore cycle."
                    )
                    break  # Stop restoring if limit reached
                except Exception as exc:
                    logger.error(f"Failed to restore strategy {strategy_id}: {exc}", exc_info=True)
                    # Mark as error if restore fails
                    if strategy_id in self._strategies:
                        self._strategies[strategy_id].status = StrategyState.error
                        self.state_manager.update_strategy_in_db(
                            strategy_id,
                            save_to_redis=True,
                            status=StrategyState.error.value
                        )
        except Exception as exc:
            logger.error(f"Failed to restore running strategies: {exc}", exc_info=True)
        
        return restored_ids

    async def _cleanup_dead_tasks(self) -> None:
        """Remove completed/cancelled tasks from _tasks dictionary.
        
        This ensures dead tasks don't count toward the concurrent limit.
        Protected with lock to prevent race conditions.
        
        CRITICAL FIX: Only mutate memory inside lock, perform DB/Redis I/O outside lock
        to avoid blocking other operations.
        """
        to_mark_error: list[str] = []
        
        async with self._lock:
            dead_tasks = []
            for strategy_id, task in list(self._tasks.items()):
                if task.done():
                    dead_tasks.append(strategy_id)
                    # Mark for error status update (do DB/Redis outside lock)
                    if strategy_id in self._strategies:
                        summary = self._strategies[strategy_id]
                        if summary.status == StrategyState.running:
                            summary.status = StrategyState.error
                            to_mark_error.append(strategy_id)
            
            # Remove dead tasks (atomic operation)
            for strategy_id in dead_tasks:
                self._tasks.pop(strategy_id, None)
                logger.debug(f"Cleaned up dead task for strategy {strategy_id}")
            
            if dead_tasks:
                logger.info(f"Cleaned up {len(dead_tasks)} dead task(s) from active tasks")
        
        # Perform DB/Redis updates outside lock to avoid blocking
        for strategy_id in to_mark_error:
            # Update database FIRST (source of truth), then Redis
            self.state_manager.update_strategy_in_db(
                strategy_id,
                save_to_redis=True,
                status=StrategyState.error.value
            )
            # Fallback: save to Redis if database update failed or not available
            if not (self.strategy_service and self.user_id):
                summary = self._strategies.get(strategy_id)
                if summary:
                    self.state_manager.save_to_redis(strategy_id, summary)
            logger.warning(
                f"Strategy {strategy_id} task completed unexpectedly. "
                f"Marking as error status."
            )

    async def _periodic_cleanup_loop(self, interval_seconds: int) -> None:
        """Periodic background task to clean up dead tasks.
        
        This runs continuously in the background, calling _cleanup_dead_tasks()
        at regular intervals. It's designed to be safe and non-blocking.
        
        Args:
            interval_seconds: How often to run cleanup (in seconds)
        """
        logger.info(f"🔄 Starting periodic dead task cleanup (interval: {interval_seconds}s)")
        
        while self._cleanup_running:
            try:
                # Wait for the interval (with early exit if flag changes)
                await asyncio.sleep(interval_seconds)
                
                # Check flag again after sleep (might have changed during sleep)
                if not self._cleanup_running:
                    break
                
                # Run cleanup (already thread-safe and handles exceptions internally)
                await self._cleanup_dead_tasks()
                
            except asyncio.CancelledError:
                # Normal shutdown - exit gracefully
                logger.debug("Periodic cleanup task cancelled (shutdown)")
                break
            except Exception as exc:
                # Log error but continue running (don't crash the cleanup task)
                logger.error(
                    f"Error in periodic dead task cleanup: {exc}. "
                    f"Continuing cleanup loop...",
                    exc_info=True
                )
                # Wait a bit before retrying to avoid rapid error loops
                await asyncio.sleep(5)
        
        logger.info("🛑 Periodic dead task cleanup stopped")

    def start_periodic_cleanup(self, interval_seconds: int) -> None:
        """Start the periodic cleanup task.
        
        Args:
            interval_seconds: How often to run cleanup (in seconds)
        """
        if self._cleanup_task is not None and not self._cleanup_task.done():
            logger.warning("Periodic cleanup task is already running")
            return
        
        self._cleanup_running = True
        self._cleanup_task = asyncio.create_task(
            self._periodic_cleanup_loop(interval_seconds)
        )
        logger.info(f"✅ Started periodic dead task cleanup (interval: {interval_seconds}s)")

    async def stop_periodic_cleanup(self) -> None:
        """Stop the periodic cleanup task gracefully."""
        if self._cleanup_task is None or self._cleanup_task.done():
            return
        
        logger.info("🛑 Stopping periodic dead task cleanup...")
        self._cleanup_running = False
        
        # Cancel the task
        self._cleanup_task.cancel()
        
        try:
            # Wait for task to finish (with timeout)
            await asyncio.wait_for(self._cleanup_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Periodic cleanup task did not stop within timeout")
        except asyncio.CancelledError:
            # Expected - task was cancelled
            pass
        except Exception as exc:
            logger.warning(f"Error stopping periodic cleanup task: {exc}")
        
        self._cleanup_task = None
        logger.info("✅ Periodic dead task cleanup stopped")


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
        # StrategyService.create_strategy handles transaction management:
        # - Database save is atomic (within transaction)
        # - Redis cache is updated after successful database save
        # - If Redis fails, database is kept (database is source of truth)
        if self.strategy_service and self.user_id and account_uuid:
            try:
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
                # CRITICAL FIX: Ensure summary.account_id is the string account_id (not UUID)
                # _db_strategy_to_summary() should convert UUID to string, but ensure consistency
                # This ensures _get_account_client() receives the correct string account_id
                if summary.account_id != account_id:
                    # If conversion failed or returned UUID string, use the original string account_id
                    summary.account_id = account_id
                    logger.debug(f"Set summary.account_id to string '{account_id}' (was '{summary.account_id}')")
                # Also keep in memory for fast access
                # Note: This is a sync method, so we can't use async locks
                # Dictionary writes are protected by GIL in CPython, but not guaranteed
                # TODO: Consider making register() async for better thread safety
                self._strategies[strategy_id] = summary
            except Exception as e:
                logger.error(f"Failed to create strategy {strategy_id} in database: {e}")
                raise  # Re-raise to prevent partial state
        else:
            # Single-user mode: save to Redis only (backward compatibility)
            # No transaction management needed (Redis only)
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
            # Note: This is a sync method, so we can't use async locks
            # Dictionary writes are protected by GIL in CPython, but not guaranteed
            # TODO: Consider making register() async for better thread safety
            self._strategies[strategy_id] = summary
            self.state_manager.save_to_redis(strategy_id, summary)
        
        account_name = self.client_manager.get_account_config(account_id)
        account_display = account_name.name if account_name else account_id
        logger.info(
            f"Registered strategy {strategy_id} ({payload.strategy_type}) "
            f"with explicit leverage={payload.leverage}x for {payload.symbol} "
            f"using account '{account_id}' ({account_display})"
        )
        # auto_start is handled by the API layer to avoid double-starting the same strategy.
        return summary

    async def start(self, strategy_id: str) -> StrategySummary:
        # BUG FIX: Load strategy from database if not in memory
        if strategy_id not in self._strategies:
            if self.strategy_service and self.user_id:
                try:
                    # Try to load from database
                    strategies = self.strategy_service.list_strategies(self.user_id)
                    # BUG FIX: Protect dict writes in async method with lock
                    async with self._lock:
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
        await self._cleanup_dead_tasks()
        
        # CRITICAL: All dictionary access and limit checks must be atomic
        # Use lock to prevent race conditions when multiple strategies start concurrently
        async with self._lock:
            # Check concurrent limit (atomic with task creation)
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
        # Pass trade_service and user_id for database duplicate checking
        account_executor = OrderExecutor(
            client=account_client,
            trade_service=self.trade_service,
            user_id=self.user_id,
        )
        
        # For backward compatibility: if ema_crossover type, set default 5/20 EMA
        # BUG FIX: params may already be a dict (from DB or single-user mode)
        params = summary.params.model_dump() if hasattr(summary.params, "model_dump") else dict(summary.params)
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
        
        # BUG FIX: interval_seconds may be in dict or model attribute
        interval_seconds = (
            summary.params.interval_seconds
            if hasattr(summary.params, "interval_seconds")
            else summary.params.get("interval_seconds", 60)
        )
        
        context = StrategyContext(
            id=summary.id,
            name=summary.name,
            symbol=summary.symbol,
            leverage=summary.leverage,
            risk_per_trade=summary.risk_per_trade,
            params=params,
            interval_seconds=interval_seconds,
            metadata={},
        )
        strategy = self.registry.build(summary.strategy_type, context, account_client)
        task = asyncio.create_task(self.executor.run_loop(strategy, summary, account_risk, account_executor))
        
        # CRITICAL: Atomically add task to dictionary and update status
        # This must be inside the lock to prevent race conditions
        async with self._lock:
            # Double-check limit after acquiring lock (another task might have started)
            if len(self._tasks) >= self.max_concurrent:
                # Cancel the task we just created since we can't run it
                task.cancel()
                raise MaxConcurrentStrategiesError(
                    current=len(self._tasks),
                    max_allowed=self.max_concurrent
                )
            
            # Verify strategy is still not running (another task might have started it)
            if strategy_id in self._tasks:
                existing_task = self._tasks[strategy_id]
                if not existing_task.done():
                    # Cancel the task we just created
                    task.cancel()
                    raise StrategyAlreadyRunningError(strategy_id)
            
            # Atomically add task and update status
            # CRITICAL FIX: Remove nested lock - we're already inside a lock block
            # asyncio.Lock is not re-entrant, so nested acquisition would deadlock
            self._tasks[strategy_id] = task
            summary.status = StrategyState.running
        
        # CRITICAL FIX: Check if task failed immediately after creation
        # Give it a tiny moment to start, then check if it's already done (failed)
        await asyncio.sleep(0.1)  # 100ms to allow task to start
        if task.done():
            # Task completed immediately - check if it's an error
            try:
                # Get the exception if any
                exception = task.exception()
                if exception:
                    # Only raise error if there's an actual exception
                    logger.error(
                        f"Strategy {strategy_id} task failed immediately after start: {exception}",
                        exc_info=exception
                    )
                    # Clean up the dead task
                    async with self._lock:
                        self._tasks.pop(strategy_id, None)
                        summary.status = StrategyState.error
                        # Update database to reflect error status
                        self.state_manager.update_strategy_in_db(
                            strategy_id,
                            save_to_redis=True,
                            status=StrategyState.error.value
                        )
                    
                    raise RuntimeError(
                        f"Strategy {strategy_id} task failed immediately after start. "
                        f"Check logs for details."
                    ) from exception
                else:
                    # Task completed without exception - might be a test mock or intentional completion
                    # Log warning but don't raise error (tests often use mocks that complete immediately)
                    logger.debug(
                        f"Strategy {strategy_id} task completed immediately after start (no exception) - "
                        f"this may be expected in test scenarios"
                    )
            except Exception as exc:
                # If we can't check the exception, log and continue (don't fail the start)
                logger.warning(f"Error checking task exception for {strategy_id}: {exc}")
        
        # Update database FIRST (source of truth), then Redis
        # This prevents data loss if database update fails
        from datetime import datetime, timezone
        started_at = datetime.now(timezone.utc)
        if self.state_manager.update_strategy_in_db(
            strategy_id,
            save_to_redis=True,
            status=StrategyState.running.value,
            started_at=started_at
        ):
            summary.started_at = started_at
            logger.debug(f"Updated strategy {strategy_id} status to 'running' and started_at in database")
        else:
            # No database mode - save to Redis only (backward compatibility)
            self.state_manager.save_to_redis(strategy_id, summary)
        
        # Log strategy start
        account_name = self.client_manager.get_account_config(account_id)
        account_display = account_name.name if account_name else account_id
        logger.info(
            f"✅ Strategy STARTED: {summary.id} ({summary.name}) | "
            f"Symbol: {summary.symbol} | Type: {summary.strategy_type.value} | "
            f"Leverage: {summary.leverage}x | Account: {account_id} ({account_display})"
        )
        
        # Log to SystemEvent for activity history
        if self.strategy_service and self.user_id:
            try:
                db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, strategy_id)
                if db_strategy:
                    account_uuid = None
                    if account_id and account_id != "default":
                        from app.models.db_models import Account
                        account = self.strategy_service.db_service.db.query(Account).filter(
                            Account.user_id == self.user_id,
                            Account.account_id.ilike(account_id.lower())
                        ).first()
                        if account:
                            account_uuid = account.id
                    
                    self.strategy_service.db_service.create_system_event(
                        event_type="strategy_started",
                        event_level="INFO",
                        message=f"Strategy '{summary.name}' ({strategy_id}) started",
                        strategy_id=db_strategy.id,
                        account_id=account_uuid,
                        event_metadata={
                            "strategy_id": strategy_id,
                            "strategy_name": summary.name,
                            "symbol": summary.symbol,
                            "strategy_type": summary.strategy_type.value,
                            "leverage": summary.leverage,
                            "account_id": account_id
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to log strategy start event: {e}")
        
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
                    # BUG FIX: Protect dict writes in async method with lock
                    async with self._lock:
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
            await self.order_manager.cancel_tp_sl_orders(summary)
        except Exception as exc:
            logger.warning(f"Error cancelling TP/SL orders for strategy {strategy_id}: {exc}")
        
        # Check for open positions and close them
        try:
            account_id = summary.account_id or "default"
            account_client = self._get_account_client(account_id)
            # BUG FIX: Wrap sync BinanceClient call in to_thread to avoid blocking event loop
            position = await asyncio.to_thread(account_client.get_open_position, summary.symbol)
            if position:
                position_side = "LONG" if float(position['positionAmt']) > 0 else "SHORT"
                logger.info(
                    f"🔴 MANUAL CLOSE: Closing {position_side} position for strategy {strategy_id}: "
                    f"{position['positionAmt']} {summary.symbol} @ {position['entryPrice']} "
                    f"(Unrealized PnL: {float(position.get('unRealizedProfit', 0)):.2f} USDT)"
                )
                # BUG FIX: Wrap sync BinanceClient call in to_thread to avoid blocking event loop
                close_order = await asyncio.to_thread(account_client.close_position, summary.symbol)
                if close_order:
                    logger.info(
                        f"[{strategy_id}] 🔴 Position CLOSED (reason: MANUAL/STOP): "
                        f"{close_order.side} {close_order.symbol} qty={close_order.executed_qty} @ {close_order.avg_price or close_order.price:.8f} "
                        f"(was {position_side} @ {position['entryPrice']})"
                    )
                    # Track the closing trade (protected with lock)
                    async with self._lock:
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
        
        # Stop the strategy task (protected with lock for atomic operation)
        async with self._lock:
            task = self._tasks.pop(strategy_id, None)
            if task:
                task.cancel()
            summary.status = StrategyState.stopped
        
        # Update database FIRST (source of truth), then Redis
        # This prevents data loss if database update fails
        from datetime import datetime, timezone
        stopped_at = datetime.now(timezone.utc)
        if self.state_manager.update_strategy_in_db(
            strategy_id,
            save_to_redis=True,
            status=StrategyState.stopped.value,
            stopped_at=stopped_at
        ):
            summary.stopped_at = stopped_at
            logger.debug(f"Updated strategy {strategy_id} status to 'stopped' and stopped_at in database")
        else:
            # No database mode - save to Redis only (backward compatibility)
            self.state_manager.save_to_redis(strategy_id, summary)
        
        # Log to SystemEvent for activity history
        if self.strategy_service and self.user_id:
            try:
                db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, strategy_id)
                if db_strategy:
                    account_uuid = None
                    account_id = summary.account_id or "default"
                    if account_id and account_id != "default":
                        from app.models.db_models import Account
                        account = self.strategy_service.db_service.db.query(Account).filter(
                            Account.user_id == self.user_id,
                            Account.account_id.ilike(account_id.lower())
                        ).first()
                        if account:
                            account_uuid = account.id
                    
                    self.strategy_service.db_service.create_system_event(
                        event_type="strategy_stopped",
                        event_level="INFO",
                        message=f"Strategy '{summary.name}' ({strategy_id}) stopped",
                        strategy_id=db_strategy.id,
                        account_id=account_uuid,
                        event_metadata={
                            "strategy_id": strategy_id,
                            "strategy_name": summary.name,
                            "symbol": summary.symbol,
                            "final_pnl": float(summary.unrealized_pnl) if summary.unrealized_pnl else None,
                            "position_size": float(summary.position_size) if summary.position_size else None,
                            "account_id": account_id
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to log strategy stop event: {e}")
        
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

    async def update_strategy_params(
        self,
        strategy_uuid: UUID,
        new_params: dict
    ) -> StrategySummary:
        """Update strategy parameters without stopping (hot-swap).
        
        This method:
        1. Acquires per-strategy lock
        2. Updates params atomically
        3. Bumps params_version for strategy instance
        4. Strategy executor picks up new params on next evaluation
        
        Args:
            strategy_uuid: Strategy UUID (not string ID)
            new_params: New parameter dictionary
            
        Returns:
            Updated StrategySummary
            
        Raises:
            StrategyNotFoundError: If strategy doesn't exist
            RuntimeError: If strategy is stopping/starting
        """
        # Find strategy by UUID (need to search through _strategies)
        strategy_id = None
        for sid, summary in self._strategies.items():
            if summary.id == strategy_uuid:
                strategy_id = sid
                break
        
        if not strategy_id:
            raise StrategyNotFoundError(str(strategy_uuid))
        
        summary = self._strategies[strategy_id]
        
        # Check state machine
        if summary.status in ["stopping", "starting"]:
            raise RuntimeError(f"Strategy {strategy_uuid} is {summary.status}, cannot update params")
        
        # Get or create per-strategy lock
        if strategy_id not in self._strategy_locks:
            async with self._lock:
                if strategy_id not in self._strategy_locks:
                    self._strategy_locks[strategy_id] = asyncio.Lock()
        
        strategy_lock = self._strategy_locks[strategy_id]
        
        async with strategy_lock:
            # Update database first (source of truth)
            updated_summary = await asyncio.to_thread(
                self.strategy_service.update_strategy,
                self.user_id,
                strategy_id,  # Use string ID for service call
                params=new_params
            )
            
            if not updated_summary:
                raise StrategyNotFoundError(str(strategy_uuid))
            
            # Update in-memory summary
            async with self._lock:
                self._strategies[strategy_id] = updated_summary
            
            # Bump params version (strategy executor checks this)
            if strategy_id in self._params_versions:
                self._params_versions[strategy_id] += 1
            else:
                self._params_versions[strategy_id] = 1
            
            logger.info(
                f"Hot-swapped parameters for strategy {strategy_id} ({strategy_uuid}) "
                f"(version {self._params_versions[strategy_id]})"
            )
        
        return updated_summary

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
        # Check if strategy exists in memory first
        if strategy_id not in self._strategies:
            # Strategy not in memory - try to load from database
            logger.debug(f"Strategy {strategy_id} not in memory, checking database...")
            if self.strategy_service and self.user_id:
                try:
                    # Try to load from database - use appropriate method based on service type
                    if self.strategy_service._is_async:
                        summary = await self.strategy_service.async_get_strategy(self.user_id, strategy_id)
                    else:
                        # Use sync method if service is sync
                        summary = self.strategy_service.get_strategy(self.user_id, strategy_id)
                    
                    if summary:
                        # Load into memory for deletion
                        async with self._lock:
                            self._strategies[strategy_id] = summary
                        logger.info(f"Loaded strategy {strategy_id} from database for deletion")
                    else:
                        # Strategy doesn't exist in database either
                        raise StrategyNotFoundError(strategy_id)
                except Exception as exc:
                    logger.warning(f"Failed to load strategy {strategy_id} from database: {exc}")
                    raise StrategyNotFoundError(strategy_id) from exc
            else:
                # No database access - strategy doesn't exist
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

    async def pause_all_strategies_for_account(
        self,
        account_id: str,
        reason: str = "Daily or weekly loss limit exceeded"
    ) -> list[str]:
        """Stop all running strategies for an account when risk limits are exceeded.
        
        This method:
        1. Finds all running strategies for the account
        2. Updates their status to "stopped_by_risk" in database
        3. Cancels their running tasks and closes positions
        4. Logs account-level enforcement event
        
        Args:
            account_id: Account ID string (e.g., "default", "account1")
            reason: Reason for stopping (e.g., "Daily loss limit exceeded")
            
        Returns:
            List of strategy IDs that were stopped
        """
        if not (self.strategy_service and self.user_id):
            logger.warning(
                f"Cannot pause strategies for account {account_id}: "
                f"strategy_service or user_id not available"
            )
            return []
        
        try:
            # Get account UUID
            account = self.strategy_service.db_service.get_account_by_id(
                self.user_id, account_id
            )
            if not account:
                logger.warning(f"Account not found: {account_id}")
                return []
            
            # Get all running strategies for this account
            from app.models.db_models import Strategy
            strategies = self.strategy_service.db_service.db.query(Strategy).filter(
                Strategy.user_id == self.user_id,
                Strategy.account_id == account.id,
                Strategy.status == "running"
            ).all()
            
            if not strategies:
                logger.debug(f"No running strategies found for account {account_id}")
                return []
            
            paused_strategies = []
            for db_strategy in strategies:
                strategy_id = db_strategy.strategy_id
                
                # CRITICAL FIX: Use stop() function to fully stop the strategy
                # This ensures proper cleanup: cancels TP/SL, closes positions, cancels tasks
                # Then we update status to stopped_by_risk instead of stopped
                try:
                    # Call the full stop method for the strategy
                    # This will handle cancelling TP/SL, closing positions, and cancelling the task
                    await self.stop(strategy_id)
                    
                    # After stopping, explicitly set status to stopped_by_risk (override the "stopped" status)
                    db_strategy.status = "stopped_by_risk"
                    self.strategy_service.db_service.db.commit()  # Commit the status change
                    
                    # CRITICAL: Refresh database object to ensure changes are visible
                    self.strategy_service.db_service.db.refresh(db_strategy)
                    
                    # Update in-memory summary IMMEDIATELY to prevent stale status
                    if strategy_id in self._strategies:
                        summary = self._strategies[strategy_id]
                        from app.models.strategy import StrategyState
                        summary.status = StrategyState.stopped_by_risk
                    
                    # Also update in state manager to sync Redis cache
                    self.state_manager.update_strategy_in_db(
                        strategy_id,
                        save_to_redis=True,
                        status=StrategyState.stopped_by_risk.value
                    )
                    
                    # CRITICAL: Force refresh from database in StrategyService cache
                    # This ensures list_strategies() will return updated status
                    if self.strategy_service and hasattr(self.strategy_service, 'db_service'):
                        try:
                            # Invalidate Redis cache if exists
                            if self.strategy_service.redis and self.strategy_service.redis.enabled:
                                cache_key = self.strategy_service._redis_key(self.user_id, strategy_id)
                                self.strategy_service.redis.delete(cache_key)
                        except Exception as cache_exc:
                            logger.debug(f"Failed to invalidate cache for strategy {strategy_id}: {cache_exc}")
                    
                    logger.info(
                        f"✅ Fully stopped and marked as stopped_by_risk strategy {strategy_id} ({db_strategy.name}) "
                        f"for account {account_id}: {reason}"
                    )
                except Exception as stop_exc:
                    logger.error(
                        f"Error stopping strategy {strategy_id} during account-level pause: {stop_exc}",
                        exc_info=True
                    )
                    # If stopping fails, at least mark as stopped_by_risk in DB and cancel task manually
                    db_strategy.status = "stopped_by_risk"
                    self.strategy_service.db_service.db.commit()
                    
                    # Cancel task manually if stop() failed
                    if strategy_id in self._tasks:
                        task = self._tasks[strategy_id]
                        if not task.done():
                            logger.warning(f"Manually cancelling task for strategy {strategy_id} after stop() failed")
                            task.cancel()
                            try:
                                await asyncio.wait_for(task, timeout=2.0)
                            except (asyncio.CancelledError, asyncio.TimeoutError):
                                pass
                            async with self._lock:
                                self._tasks.pop(strategy_id, None)
                    
                    if strategy_id in self._strategies:
                        summary = self._strategies[strategy_id]
                        from app.models.strategy import StrategyState
                        summary.status = StrategyState.stopped_by_risk
                
                paused_strategies.append(strategy_id)
            
            # CRITICAL: Final commit to ensure all status changes are persisted
            self.strategy_service.db_service.db.commit()
            
            # CRITICAL: Force expire all cached objects to ensure fresh queries see updated status
            # This prevents SQLAlchemy from returning stale cached objects with old status
            try:
                self.strategy_service.db_service.db.expire_all()
            except Exception as expire_exc:
                logger.debug(f"Failed to expire database cache: {expire_exc}")
            
            # CRITICAL: Verify all strategies were actually stopped by checking database
            if paused_strategies:
                from app.models.db_models import Strategy
                # Refresh query to ensure we get latest status
                paused_count_verified = self.strategy_service.db_service.db.query(Strategy).filter(
                    Strategy.user_id == self.user_id,
                    Strategy.account_id == account.id,
                    Strategy.strategy_id.in_(paused_strategies),
                    Strategy.status == "stopped_by_risk"
                ).count()
                
                if paused_count_verified != len(paused_strategies):
                    logger.error(
                        f"⚠️ CRITICAL: Only {paused_count_verified}/{len(paused_strategies)} strategies "
                        f"verified as stopped_by_risk in database after pause operation! "
                        f"Some strategies may still be running."
                    )
                else:
                    logger.info(
                        f"✅ Verified: {paused_count_verified}/{len(paused_strategies)} strategies "
                        f"successfully stopped and status set to stopped_by_risk in database"
                    )
            
            # Log account-level enforcement event
            if paused_strategies:
                self.strategy_service.db_service.create_system_event(
                    event_type="ACCOUNT_STRATEGIES_PAUSED",
                    event_level="WARNING",
                    message=f"All strategies paused for account {account_id}: {reason}. "
                           f"Paused {len(paused_strategies)} strategies: {', '.join(paused_strategies)}",
                    account_id=account.id,
                    strategy_id=None,  # Account-level event, not strategy-specific
                    event_metadata={
                        "account_id": account_id,
                        "reason": reason,
                        "paused_strategies": paused_strategies,
                        "paused_count": len(paused_strategies)
                    }
                )
                
                logger.warning(
                    f"🛑 STOPPED {len(paused_strategies)} strategies for account {account_id}: {reason}"
                )
            
            return paused_strategies
            
        except Exception as e:
            logger.error(
                f"Error pausing strategies for account {account_id}: {e}",
                exc_info=True
            )
            return []

    def list_strategies(self) -> list[StrategySummary]:
        """List all strategies.
        
        In multi-user mode, loads from database via StrategyService.
        In single-user mode, returns in-memory strategies.
        
        CRITICAL: Always loads fresh status from database to ensure consistency.
        This prevents stale status showing "running" when strategies are actually stopped_by_risk.
        
        Note: This method is sync, so it doesn't use locks. Dictionary reads are generally
        safe in Python (GIL protection), but for consistency, consider making this async
        if called from async contexts.
        """
        # Multi-user mode: load from database if available
        if self.strategy_service and self.user_id:
            try:
                # CRITICAL: Always load fresh from database to get latest status
                # This ensures stopped_by_risk status is visible immediately
                strategies = self.strategy_service.list_strategies(self.user_id)
                # CRITICAL FIX: Create a copy to avoid race conditions with async tasks modifying the dict
                # Update in-memory cache with fresh status from database
                # This ensures in-memory cache matches database (source of truth)
                strategies_copy = []
                for summary in strategies:
                    # CRITICAL: Update in-memory cache with fresh status from database
                    # This prevents stale "running" status when strategies are actually stopped_by_risk
                    self._strategies[summary.id] = summary
                    strategies_copy.append(summary)
                return strategies_copy
            except Exception as exc:
                logger.warning(f"Failed to load strategies from database: {exc}, falling back to in-memory")
        
        # Single-user mode or fallback: return in-memory strategies
        # CRITICAL FIX: Create a copy to avoid "dictionary changed size during iteration" errors
        # and to prevent race conditions with async tasks modifying the dict
        return list(self._strategies.values()).copy()
    
    def get_trades(self, strategy_id: str) -> List[OrderResponse]:
        """Get all executed trades for a strategy.
        
        In multi-user mode, loads from database via TradeService.
        In single-user mode, returns in-memory trades.
        
        Note: This method is sync, so it doesn't use locks. Dictionary reads are generally
        safe in Python (GIL protection), but for consistency, consider making this async
        if called from async contexts.
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
                    # Update in-memory cache (note: not protected with lock since this is sync method)
                    # For thread safety, consider making this method async
                    self._trades[strategy_id] = trades
                    return trades
            except Exception as e:
                logger.warning(f"Failed to load trades from database: {e}, falling back to in-memory")
        
        # Single-user mode or fallback: return in-memory trades
        # PERFORMANCE FIX: Only copy when necessary (in-memory trades that might be modified)
        # Database-loaded trades are already new lists, so no copy needed
        trades = self._trades.get(strategy_id, [])
        if not trades:
            return []
        # Create a shallow copy to avoid race conditions with async tasks modifying the list
        # Using list() instead of .copy() is slightly more efficient and clearer
        return list(trades)
    
    def get_trades_batch(self, strategy_ids: List[str]) -> Dict[str, List[OrderResponse]]:
        """Get trades for multiple strategies in a single batch query (optimizes N+1 problem).
        
        Args:
            strategy_ids: List of strategy IDs (strings)
        
        Returns:
            Dictionary mapping strategy_id to list of trades
        """
        result: Dict[str, List[OrderResponse]] = {sid: [] for sid in strategy_ids}
        
        # Multi-user mode: batch load from database if available
        if self.trade_service and self.user_id and self.strategy_service:
            try:
                # Get all strategy UUIDs from database in one query
                strategies = self.strategy_service.list_strategies(self.user_id)
                strategy_uuid_map: Dict[str, UUID] = {}
                # CRITICAL FIX: strategy.id is UUID, strategy_ids is List[str]
                # Convert UUID to string for comparison, then map string ID -> UUID
                strategy_ids_set = set(strategy_ids)  # Convert to set for O(1) lookup
                for strategy in strategies:
                    strategy_id_str = str(strategy.id)  # Convert UUID to string
                    if strategy_id_str in strategy_ids_set:
                        strategy_uuid_map[strategy_id_str] = strategy.id  # Map string ID -> UUID
                
                if strategy_uuid_map:
                    # Batch load all trades in one query
                    strategy_uuids = list(strategy_uuid_map.values())
                    trades_by_strategy = self.trade_service.get_trades_batch(
                        user_id=self.user_id,
                        strategy_ids=strategy_uuids,
                        limit_per_strategy=1000
                    )
                    
                    # Map UUIDs back to string IDs and update in-memory cache
                    # Note: This is a sync method, so we can't use async locks
                    # Dictionary writes are protected by GIL in CPython, but not guaranteed
                    uuid_to_str_id = {uuid: sid for sid, uuid in strategy_uuid_map.items()}
                    for strategy_uuid, trades in trades_by_strategy.items():
                        str_id = uuid_to_str_id.get(strategy_uuid)
                        if str_id:
                            # CRITICAL FIX: Return copies, not references, to prevent race conditions and mutation
                            result[str_id] = list(trades) if trades else []  # ✅ Return copy, not reference
                            self._trades[str_id] = trades  # Update cache (can keep reference for cache)
                    
                    # Fill in any missing strategies from in-memory cache
                    # CRITICAL FIX: Return copies, not references, to prevent race conditions and mutation
                    for strategy_id in strategy_ids:
                        if not result[strategy_id] and strategy_id in self._trades:
                            trades = self._trades[strategy_id]
                            result[strategy_id] = list(trades) if trades else []  # ✅ Return copy, not reference
                
                return result
            except Exception as e:
                logger.warning(f"Failed to batch load trades from database: {e}, falling back to in-memory")
        
        # Single-user mode or fallback: return in-memory trades
        # CRITICAL FIX: Return copies, not references, to prevent race conditions and mutation
        for strategy_id in strategy_ids:
            trades = self._trades.get(strategy_id, [])
            result[strategy_id] = list(trades) if trades else []  # ✅ Return copy, not reference
        
        return result

    def calculate_strategy_stats(self, strategy_id: str) -> StrategyStats:
        """Calculate statistics for a specific strategy (delegates to statistics module).
        
        Raises:
            StrategyNotFoundError: If strategy does not exist
        """
        return self.statistics.calculate_strategy_stats(strategy_id)
    
    def calculate_overall_stats(self, use_cache: bool = True) -> OverallStats:
        """Calculate overall statistics across all strategies (delegates to statistics module).
        
        Args:
            use_cache: If True, cache results for 30 seconds to avoid recalculating
        """
        return self.statistics.calculate_overall_stats(use_cache=use_cache)


