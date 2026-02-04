"""Strategy execution loop and signal processing."""

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from loguru import logger

from app.core.binance_client_manager import BinanceClientManager
from app.core.exceptions import RiskLimitExceededError, CircuitBreakerActiveError
from app.models.strategy import StrategyState, StrategySummary
from app.risk.manager import RiskManager
from app.services.notifier import NotificationService
from app.services.order_executor import OrderExecutor
from app.services.strategy_account_manager import StrategyAccountManager
from app.services.strategy_order_manager import StrategyOrderManager
from app.services.strategy_persistence import StrategyPersistence
from app.strategies.base import Strategy

if TYPE_CHECKING:
    pass


class StrategyExecutor:
    """Executes strategy evaluation loops and processes signals."""
    
    def __init__(
        self,
        account_manager: StrategyAccountManager,
        state_manager: StrategyPersistence,
        order_manager: StrategyOrderManager,
        client_manager: BinanceClientManager,
        default_risk: Optional[RiskManager] = None,
        default_executor: Optional[OrderExecutor] = None,
        notification_service: Optional[NotificationService] = None,
        lock: Optional[asyncio.Lock] = None,
    ) -> None:
        """Initialize the strategy executor.
        
        Args:
            account_manager: Account manager for getting clients
            state_manager: State manager for position updates and reconciliation
            order_manager: Order manager for executing orders
            client_manager: Client manager for account config
            default_risk: Default risk manager (optional)
            default_executor: Default order executor (optional)
            notification_service: Notification service for PnL alerts
            lock: Async lock for thread safety
        """
        self.account_manager = account_manager
        self.state_manager = state_manager
        self.order_manager = order_manager
        self.client_manager = client_manager
        self.default_risk = default_risk
        self.default_executor = default_executor
        self.notifications = notification_service
        self._lock = lock
    
    async def run_loop(
        self,
        strategy: Strategy,
        summary: StrategySummary,
        risk: Optional[RiskManager] = None,
        executor: Optional[OrderExecutor] = None,
    ) -> None:
        """Run the main strategy evaluation loop.
        
        This loop:
        1. Syncs position state from Binance
        2. Evaluates the strategy to get signals
        3. Executes orders based on signals
        4. Handles errors and notifications
        
        Args:
            strategy: Strategy instance to run
            summary: Strategy summary
            risk: Risk manager (optional, uses default if not provided)
            executor: Order executor (optional, uses default if not provided)
        """
        # Use account-specific risk/executor if provided, otherwise fall back to defaults
        account_id = summary.account_id or "default"
        account_client = self.account_manager.get_account_client(account_id)
        account_risk = risk or self.default_risk or RiskManager(client=account_client)
        
        # Create executor with trade_service and user_id for idempotency
        if executor:
            account_executor = executor
        elif self.default_executor:
            account_executor = self.default_executor
        else:
            from app.services.order_executor import OrderExecutor
            from app.services.trade_service import TradeService
            # Note: trade_service and user_id need to be passed from StrategyRunner
            # For now, we'll create without them if not available
            account_executor = OrderExecutor(client=account_client)
        
        logger.info(f"Starting loop for {summary.id} (account: {account_id})")
        
        # Track last reconciliation time for periodic position sync
        last_reconciliation = datetime.now(timezone.utc)
        reconciliation_interval = 300  # Reconcile every 5 minutes
        
        try:
            while True:
                # CRITICAL FIX: Refresh strategy status from database to catch pause_by_risk updates
                # This ensures strategies see their paused status even if they're already in the loop
                if self.order_manager.strategy_service and self.order_manager.user_id:
                    try:
                        db_strategy = self.order_manager.strategy_service.db_service.get_strategy(
                            self.order_manager.user_id,
                            summary.id
                        )
                        if db_strategy:
                            # Update summary status from database
                            db_status = StrategyState(db_strategy.status)
                            if summary.status != db_status:
                                logger.info(
                                    f"[{summary.id}] Strategy status changed from {summary.status} to {db_status} "
                                    f"(refreshed from database)"
                                )
                                summary.status = db_status
                    except Exception as refresh_error:
                        # Don't fail the loop if status refresh fails
                        logger.debug(f"[{summary.id}] Failed to refresh status from database: {refresh_error}")
                
                # Check if strategy was paused by risk management
                # If status is stopped_by_risk, exit the loop (strategy is stopped)
                if summary.status == StrategyState.stopped_by_risk:
                    logger.info(f"[{summary.id}] Strategy paused by risk management, exiting loop")
                    break
                
                # CRITICAL ORDER: Sync with Binance BEFORE evaluating strategy
                # This ensures strategy.evaluate() uses correct state, not stale state
                # 
                # Flow: Binance → Database (source of truth) → Redis (cache) → Memory (cache) → Strategy
                # 
                # 1) First: Sync summary from Binance reality to database (source of truth)
                # CRITICAL: Add timeout to prevent getting stuck on position sync
                try:
                    await asyncio.wait_for(
                        self.state_manager.update_position_info(summary),
                        timeout=30.0  # 30 second timeout for position sync
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"[{summary.id}] Position sync TIMED OUT after 30 seconds. "
                        f"Continuing with potentially stale position data."
                    )
                except Exception as sync_exc:
                    logger.warning(
                        f"[{summary.id}] Position sync failed: {sync_exc}. "
                        f"Continuing with potentially stale position data."
                    )
                
                # 2) Periodic position reconciliation (every 5 minutes)
                # This ensures database state matches Binance reality even if updates were missed
                current_time = datetime.now(timezone.utc)
                time_since_reconciliation = (current_time - last_reconciliation).total_seconds()
                
                if time_since_reconciliation >= reconciliation_interval:
                    try:
                        # CRITICAL: Add timeout to prevent getting stuck on reconciliation
                        await asyncio.wait_for(
                            self.state_manager.reconcile_position_state(summary),
                            timeout=30.0  # 30 second timeout for reconciliation
                        )
                        last_reconciliation = current_time
                        logger.debug(
                            f"[{summary.id}] Periodic position reconciliation completed. "
                            f"Next reconciliation in {reconciliation_interval}s"
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"[{summary.id}] Position reconciliation TIMED OUT after 30 seconds. "
                            f"Skipping this reconciliation cycle."
                        )
                        # Update last_reconciliation to prevent immediate retry
                        last_reconciliation = current_time
                    except Exception as recon_exc:
                        logger.warning(
                            f"[{summary.id}] Periodic position reconciliation failed: {recon_exc}"
                        )
                
                # 3) Then: Sync strategy internal state from summary/Binance
                # This prevents desync when Binance native TP/SL orders close positions
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
                
                # 4) Now evaluate using **correct synced state**
                # Strategy now knows the real Binance position before making decisions
                signal = await strategy.evaluate()
                summary.last_signal = signal.action  # type: ignore[assignment]
                
                # CRITICAL: Track last execution time for health monitoring
                # This allows us to detect "zombie" strategies (running but not executing)
                current_time = datetime.now(timezone.utc)
                if not isinstance(summary.meta, dict):
                    summary.meta = {}
                summary.meta['last_execution_time'] = current_time.isoformat()
                summary.meta['last_execution_timestamp'] = current_time.timestamp()
                
                # Periodically save meta to database (every 10 executions to avoid too many DB writes)
                execution_count = summary.meta.get('execution_count', 0) + 1
                summary.meta['execution_count'] = execution_count
                if execution_count % 10 == 0:
                    # Save meta to database every 10 executions
                    try:
                        self.state_manager.update_strategy_in_db(
                            summary.id,
                            save_to_redis=True,
                            meta=summary.meta
                        )
                    except Exception as e:
                        logger.debug(f"Failed to save meta to database: {e}")
                
                # Log signals (skip HOLD to reduce log noise)
                if signal.action != "HOLD":
                    logger.info(
                        f"[{summary.id}] Signal: {signal.action} | "
                        f"Symbol: {signal.symbol} | "
                        f"Price: {signal.price} | "
                        f"Confidence: {signal.confidence} | "
                        f"Exit Reason: {signal.exit_reason or 'N/A'}"
                    )
                else:
                    # Only log HOLD at debug level to reduce noise
                    logger.debug(
                        f"[{summary.id}] Signal: HOLD | "
                        f"Symbol: {signal.symbol} | "
                        f"Price: {signal.price}"
                    )
                
                # 5) Update current price for UI/stats (not critical to logic)
                # Wrap sync BinanceClient call in to_thread to avoid blocking event loop
                # CRITICAL: Add timeout to prevent getting stuck on price fetch
                try:
                    summary.current_price = await asyncio.wait_for(
                        asyncio.to_thread(account_client.get_price, summary.symbol),
                        timeout=10.0  # 10 second timeout for price fetch (not critical)
                    )
                except asyncio.TimeoutError:
                    logger.debug(f"[{summary.id}] Price fetch timed out for {summary.symbol} (non-critical)")
                except Exception as exc:
                    logger.warning(f"Failed to get current price for {summary.symbol}: {exc}")
                
                # 6) Check PnL thresholds and notify if reached
                if self.notifications and summary.unrealized_pnl is not None:
                    await self.notifications.check_and_notify_pnl_threshold(
                        summary,
                        summary.unrealized_pnl,
                    )
                
                # 7) Execute order based on synced state + fresh signal
                # OPTIMIZATION: Skip _execute_order() entirely for HOLD signals to avoid unnecessary overhead
                # HOLD signals don't need order execution, risk checks, or klines fetching
                if signal.action == "HOLD":
                    # HOLD is expected behavior, not a skip - no need to track in meta
                    # Wait for new candle event or timeout (for TP/SL checks)
                    await self._wait_for_next_evaluation(strategy, summary)
                    continue
                
                # CRITICAL: Pass account-specific risk and executor to ensure orders go to correct account
                # Also pass strategy instance so we can sync state immediately after order execution
                # CRITICAL: Add timeout to prevent strategy from getting stuck if order execution hangs
                try:
                    await asyncio.wait_for(
                        self._execute_order(signal, summary, strategy, account_risk, account_executor),
                        timeout=60.0  # 60 second timeout for order execution (prevents infinite hang)
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        f"[{summary.id}] Order execution TIMED OUT after 60 seconds. "
                        f"Strategy loop will continue to prevent getting stuck. "
                        f"Signal: {signal.action} | Symbol: {signal.symbol}"
                    )
                    # Continue loop instead of hanging - strategy will retry on next iteration
                    # Mark in meta that order execution timed out
                    if not isinstance(summary.meta, dict):
                        summary.meta = {}
                    summary.meta['last_order_timeout'] = current_time.isoformat()
                    summary.meta['order_timeout_count'] = summary.meta.get('order_timeout_count', 0) + 1
                except RiskLimitExceededError as risk_exc:
                    # CRITICAL: If daily/weekly loss limit exceeded, the strategy has been paused
                    # Exit the loop IMMEDIATELY - no point continuing if limits are exceeded
                    # Check if it's a daily/weekly loss by examining the error message
                    error_msg = str(risk_exc).lower()
                    limit_type = None
                    if "daily loss" in error_msg:
                        limit_type = "DAILY_LOSS"
                    elif "weekly loss" in error_msg:
                        limit_type = "WEEKLY_LOSS"
                    
                    # Also check details dict if available
                    if not limit_type and isinstance(risk_exc.details, dict):
                        limit_type = risk_exc.details.get('limit_type')
                    
                    if limit_type in ("DAILY_LOSS", "WEEKLY_LOSS"):
                        logger.warning(
                            f"[{summary.id}] {limit_type} limit exceeded - strategy paused. "
                            f"Exiting execution loop immediately."
                        )
                        # Exit the loop immediately - strategy has been paused
                        break
                    else:
                        # Other risk limits (exposure, drawdown) - log but continue
                        logger.error(
                            f"[{summary.id}] Risk limit exceeded (non-daily/weekly): {risk_exc}. "
                            f"Strategy loop will continue."
                        )
                except Exception as order_exc:
                    # Log but don't crash the loop - allow strategy to continue
                    logger.error(
                        f"[{summary.id}] Order execution failed (non-timeout): {type(order_exc).__name__}: {order_exc}. "
                        f"Strategy loop will continue."
                    )
                
                # Wait for new candle event or timeout (for TP/SL checks)
                await self._wait_for_next_evaluation(strategy, summary)
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
        except (RiskLimitExceededError, CircuitBreakerActiveError) as exc:
            # Risk enforcement errors - do NOT mark strategy as error
            # These are expected behaviors when risk limits are enforced
            account_id = summary.account_id or "default"
            account_name = self.client_manager.get_account_config(account_id)
            account_display = account_name.name if account_name else account_id
            logger.warning(
                f"⚠️ Order blocked by risk: {summary.id} ({summary.name}) | "
                f"Symbol: {summary.symbol} | Account: {account_id} ({account_display}) | "
                f"Reason: {exc.message}"
            )
            # Note: Notifications are already sent by StrategyOrderManager
            # Do NOT send error notification - this is expected behavior
        except Exception as exc:
            # Only mark as error for actual errors (not risk enforcement)
            summary.status = StrategyState.error
            self.state_manager.save_to_redis(summary.id, summary)
            
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
            # Note: Task removal is handled by StrategyRunner, not here
            logger.debug(f"Strategy loop ended for {summary.id}")
    
    async def _execute_order(
        self,
        signal,
        summary: StrategySummary,
        strategy: Strategy,
        risk: RiskManager,
        executor: OrderExecutor,
    ) -> None:
        """Execute an order based on a signal.
        
        This is a wrapper that handles post-execution logic like:
        - Updating position state
        - Placing/canceling TP/SL orders
        - Syncing strategy state
        
        Args:
            signal: Strategy signal to execute
            summary: Strategy summary
            strategy: Strategy instance
            risk: Risk manager
            executor: Order executor
        """
        # Execute the order
        # Bug #4: Get klines for dynamic sizing (ATR calculation)
        # Try to get klines from strategy if available, otherwise None
        klines = None
        if hasattr(strategy, 'get_klines'):
            try:
                klines = await strategy.get_klines()
            except Exception as e:
                logger.debug(f"[{summary.id}] Could not get klines from strategy: {e}")
        
        order_response = await self.order_manager.execute_order(
            signal=signal,
            summary=summary,
            strategy=strategy,
            risk=risk,
            executor=executor,
            klines=klines,  # Bug #4: Pass klines for ATR calculation
        )
        
        # CRITICAL: Track order execution for health monitoring
        current_time = datetime.now(timezone.utc)
        if not isinstance(summary.meta, dict):
            summary.meta = {}
        
        if order_response:
            # Order was executed - track it
            summary.meta['last_order_time'] = current_time.isoformat()
            summary.meta['last_order_timestamp'] = current_time.timestamp()
            summary.meta['last_order_id'] = order_response.order_id
            summary.meta['last_order_status'] = order_response.status
            summary.meta['last_order_side'] = order_response.side
            summary.meta['orders_executed_count'] = summary.meta.get('orders_executed_count', 0) + 1
            logger.debug(f"[{summary.id}] Order executed: {order_response.order_id} ({order_response.side})")
            
            # Save meta immediately when order is executed (important for health checks)
            try:
                self.state_manager.update_strategy_in_db(
                    summary.id,
                    save_to_redis=True,
                    meta=summary.meta
                )
            except Exception as e:
                logger.debug(f"Failed to save order execution meta to database: {e}")
        else:
            # Order was skipped (risk blocked, insufficient balance, etc.)
            # NOTE: HOLD signals are now handled earlier in the loop and never reach _execute_order()
            summary.meta['last_skip_time'] = current_time.isoformat()
            summary.meta['orders_skipped_count'] = summary.meta.get('orders_skipped_count', 0) + 1
        
        if not order_response:
            return  # Order was skipped (e.g., risk blocked, insufficient balance)
        
        # ✅ CRITICAL: Capture previous state BEFORE mutation for position_instance_id generation
        prev_side = summary.position_side
        prev_size = summary.position_size
        prev_entry = summary.entry_price
        
        # ✅ FIX: If prev_side is None but we have exit_reason, try to get actual position from Binance
        # This handles stale state where database shows no position but Binance has one
        exit_reason = getattr(order_response, 'exit_reason', None) or getattr(signal, 'exit_reason', None)
        has_exit_reason = exit_reason and exit_reason not in ("UNKNOWN", None)
        
        if has_exit_reason and (prev_side is None or prev_size == 0):
            # Stale state detected - try to get actual position from Binance
            try:
                account_id = summary.account_id or "default"
                account_client = self.order_manager.account_manager.get_account_client(account_id)
                if hasattr(account_client, 'futures_position_information'):
                    position_list = await asyncio.to_thread(
                        account_client.futures_position_information,
                        symbol=order_response.symbol
                    )
                    binance_position = position_list[0] if position_list else None
                else:
                    binance_position = await asyncio.to_thread(
                        account_client.get_open_position,
                        symbol=order_response.symbol
                    )
                
                if binance_position and abs(float(binance_position.get("positionAmt", 0))) > 0:
                    position_amt = float(binance_position.get("positionAmt", 0))
                    prev_size = abs(position_amt)
                    prev_side = "LONG" if position_amt > 0 else "SHORT"
                    logger.info(
                        f"[{summary.id}] ✅ Recovered position state from Binance (stale state fix): "
                        f"prev_side={prev_side}, prev_size={prev_size}"
                    )
            except Exception as e:
                logger.debug(f"[{summary.id}] Could not recover position from Binance: {e}")
        
        # ✅ DEBUG: Log previous state for diagnosis
        logger.debug(
            f"[{summary.id}] Position state before order: prev_side={prev_side}, "
            f"prev_size={prev_size}, prev_entry={prev_entry}, "
            f"order_side={order_response.side}, executed_qty={order_response.executed_qty}, "
            f"exit_reason={exit_reason}"
        )
        
        # ✅ CRITICAL: Get strategy UUID first (summary.id is strategy_id string, not UUID)
        db_strategy = None
        position_instance_id = None
        
        if self.order_manager.strategy_service and self.order_manager.user_id:
            db_strategy = self.order_manager.strategy_service.db_service.get_strategy(
                self.order_manager.user_id,
                summary.id
            )
        
        if db_strategy:
            try:
                # Determine if opening new position (check prev_size, not current)
                # Calculate expected position size after order
                if order_response.side == "BUY":
                    if prev_side == "SHORT":
                        new_position_size = max(0, (prev_size or 0) - order_response.executed_qty)
                    else:
                        new_position_size = (prev_size or 0) + order_response.executed_qty
                else:  # SELL
                    if prev_side == "LONG":
                        new_position_size = max(0, (prev_size or 0) - order_response.executed_qty)
                    else:
                        new_position_size = (prev_size or 0) + order_response.executed_qty
                
                # ✅ CRITICAL FIX: Determine if opening new position
                # For closing trades (reduce_only or will close position), we need to find existing position_instance_id
                # Note: OrderResponse doesn't have reduce_only field, so we infer from position size logic
                # ✅ FIX: Also check exit_reason - if TP/SL, it's definitely a closing trade
                exit_reason = getattr(order_response, 'exit_reason', None) or getattr(signal, 'exit_reason', None)
                has_exit_reason = exit_reason and exit_reason not in ("UNKNOWN", None)
                
                # ✅ CRITICAL FIX: Determine if closing position
                # Priority order:
                # 1. exit_reason exists (most reliable indicator - strategy explicitly says it's closing)
                # 2. Position size logic (prev_side matches order direction and new_size == 0)
                # 3. Fallback: If exit_reason exists but prev_side is None (stale state), infer from order side
                
                # ✅ FIX: If exit_reason exists, it's ALWAYS a closing trade (regardless of prev_side/prev_size)
                # This handles stale state where database shows prev_side=None but exit_reason indicates closing
                if has_exit_reason:
                    # Exit reason exists - this is definitely a closing trade
                    is_closing_position = True
                    logger.debug(
                        f"[{summary.id}] Detected closing position from exit_reason: {exit_reason} "
                        f"(prev_side={prev_side}, prev_size={prev_size}, order_side={order_response.side})"
                    )
                else:
                    # No exit_reason - use position size logic
                    is_closing_position = (
                        (prev_side == "LONG" and order_response.side == "SELL" and new_position_size == 0) or  # Closing LONG
                        (prev_side == "SHORT" and order_response.side == "BUY" and new_position_size == 0)  # Closing SHORT
                    )
                
                # ✅ FIX: More robust check for prev_size (handle 0.0, 0, None, etc.)
                prev_size_is_zero = (
                    prev_size is None or 
                    prev_size == 0 or 
                    (isinstance(prev_size, (int, float)) and abs(float(prev_size)) < 0.0001)
                )
                
                is_opening_new_position = (
                    not is_closing_position and
                    prev_size_is_zero and 
                    order_response.executed_qty > 0 and  # Will have size after order
                    not has_exit_reason  # ✅ FIX: Don't treat TP/SL exits as opening new positions
                )
                
                # ✅ CRITICAL FIX: Force opening detection for clear entry trades
                # This handles two scenarios:
                # 1. prev_size=0 but detection failed (prev_side might be set)
                # 2. prev_size > 0 but stale state (position wasn't cleared after previous close)
                #    - If prev_size matches executed_qty exactly, it's likely stale state
                #    - If no exit_reason, it's definitely an entry trade
                if not is_opening_new_position and not has_exit_reason and order_response.executed_qty > 0:
                    # Check if this looks like stale state (prev_size matches executed_qty exactly)
                    # or if prev_size is 0 (normal entry)
                    prev_size_float = float(prev_size or 0)
                    executed_qty_float = float(order_response.executed_qty)
                    is_stale_state = abs(prev_size_float - executed_qty_float) < 0.0001
                    
                    if prev_size_is_zero or is_stale_state:
                        logger.warning(
                            f"[{summary.id}] ⚠️ Force setting is_opening_new_position=True "
                            f"(prev_size={prev_size}, prev_side={prev_side}, has_exit_reason={has_exit_reason}, "
                            f"executed_qty={order_response.executed_qty}, is_stale_state={is_stale_state}). "
                            f"Detection logic may have failed due to stale state, but this is clearly an entry trade."
                        )
                        is_opening_new_position = True
                
                # ✅ DEBUG: Log position opening detection (changed to INFO for visibility)
                logger.info(
                    f"[{summary.id}] Position detection result: is_opening_new_position={is_opening_new_position}, "
                    f"is_closing_position={is_closing_position}, prev_size={prev_size}, "
                    f"prev_side={prev_side}, has_exit_reason={has_exit_reason}, "
                    f"new_position_size={new_position_size}"
                )
                if is_opening_new_position:
                    logger.info(
                        f"[{summary.id}] ✅ Detected opening new position: "
                        f"prev_side={prev_side}, prev_size={prev_size}, "
                        f"order_side={order_response.side}, executed_qty={order_response.executed_qty}"
                    )
            except Exception as pos_id_exc:
                # Log error but use heuristics instead of defaulting to False
                logger.warning(
                    f"[{summary.id}] Error determining position_instance_id: {pos_id_exc}. "
                    f"Using heuristics to determine position state.",
                    exc_info=True
                )
                # ✅ FIX: Use heuristics instead of defaulting to False
                # Get exit_reason from signal/order_response if available
                exit_reason = getattr(order_response, 'exit_reason', None) or getattr(signal, 'exit_reason', None)
                has_exit_reason = exit_reason and exit_reason not in ("UNKNOWN", None)
                
                # Heuristic: If prev_size is 0 and no exit_reason, likely opening new position
                # If prev_size > 0 and has exit_reason, likely closing position
                try:
                    prev_size_safe = prev_size if prev_size is not None else 0
                    prev_side_safe = prev_side if prev_side else None
                except:
                    prev_size_safe = 0
                    prev_side_safe = None
                
                # Heuristic for closing: has exit_reason OR (prev_side exists and order will close it)
                is_closing_position = (
                    has_exit_reason or
                    (prev_side_safe == "LONG" and order_response.side == "SELL") or
                    (prev_side_safe == "SHORT" and order_response.side == "BUY")
                )
                
                # Heuristic for opening: no exit_reason AND prev_size is 0 AND order has quantity
                is_opening_new_position = (
                    not is_closing_position and
                    prev_size_safe == 0 and
                    order_response.executed_qty > 0
                )
                
                # Calculate new_position_size heuristically
                try:
                    if order_response.side == "BUY":
                        new_position_size = prev_size_safe + order_response.executed_qty
                    else:  # SELL
                        new_position_size = prev_size_safe + order_response.executed_qty
                except:
                    new_position_size = order_response.executed_qty
                
                logger.info(
                    f"[{summary.id}] Using heuristics after exception: "
                    f"is_opening_new_position={is_opening_new_position}, "
                    f"is_closing_position={is_closing_position}, "
                    f"prev_size={prev_size_safe}, prev_side={prev_side_safe}"
                )
            
            # ✅ CRITICAL FIX: For closing trades, try to get position_instance_id from entry trades
            # This handles cases where strategy summary is out of sync
            position_instance_id = None
            try:
                if is_closing_position:
                    from app.models.db_models import Trade
                    # Determine position side from order side (BUY closes SHORT, SELL closes LONG)
                    # If prev_side is None, infer from order side
                    if prev_side:
                        inferred_position_side = prev_side
                    else:
                        # Infer from order side: BUY closes SHORT, SELL closes LONG
                        inferred_position_side = "SHORT" if order_response.side == "BUY" else "LONG"
                    
                    entry_side = "SELL" if inferred_position_side == "SHORT" else "BUY"
                    
                    # Find entry trades for this position to get position_instance_id
                    # ✅ FIX: First try with non-NULL position_instance_id, then fallback to NULL
                    base_query = self.order_manager.strategy_service.db_service.db.query(Trade).filter(
                        Trade.strategy_id == db_strategy.id,
                        Trade.symbol == summary.symbol,
                        Trade.side == entry_side,
                        Trade.status.in_(["FILLED", "PARTIALLY_FILLED"])
                    )
                    
                    # Filter by position_side if we have it
                    if inferred_position_side:
                        base_query = base_query.filter(Trade.position_side == inferred_position_side)
                    
                    # ✅ FIX: First try to find entry trade with non-NULL position_instance_id
                    entry_trade_query = base_query.filter(Trade.position_instance_id.isnot(None))
                    
                    # Ensure entry trades are before exit trade timestamp
                    if hasattr(order_response, 'timestamp') and order_response.timestamp:
                        entry_trade_query = entry_trade_query.filter(Trade.timestamp <= order_response.timestamp)
                    
                    entry_trade = entry_trade_query.order_by(Trade.timestamp.desc()).first()
                    
                    # ✅ FIX: Fallback to NULL position_instance_id if not found
                    if not entry_trade or not entry_trade.position_instance_id:
                        logger.debug(
                            f"[{summary.id}] No entry trade found with non-NULL position_instance_id. "
                            f"Trying fallback to NULL position_instance_id trades."
                        )
                        # Fallback: try with NULL position_instance_id
                        fallback_query = base_query.filter(Trade.position_instance_id.is_(None))
                        if hasattr(order_response, 'timestamp') and order_response.timestamp:
                            fallback_query = fallback_query.filter(Trade.timestamp <= order_response.timestamp)
                        entry_trade = fallback_query.order_by(Trade.timestamp.desc()).first()
                        
                        if entry_trade:
                            logger.info(
                                f"[{summary.id}] ✅ Found entry trade {entry_trade.order_id} with NULL position_instance_id "
                                f"(backward compatibility). Will use strategy's position_instance_id."
                            )
                            # Use strategy's position_instance_id if available
                            if db_strategy.position_instance_id:
                                position_instance_id = db_strategy.position_instance_id
                                logger.info(
                                    f"[{summary.id}] Using strategy's position_instance_id {position_instance_id} "
                                    f"for closing {inferred_position_side} position"
                                )
                    
                    if entry_trade and entry_trade.position_instance_id:
                        position_instance_id = entry_trade.position_instance_id
                        logger.info(
                            f"[{summary.id}] ✅ Using position_instance_id {position_instance_id} from entry trade {entry_trade.order_id} "
                            f"for closing {inferred_position_side} position (prev_side was {prev_side})"
                        )
                    elif not entry_trade:
                        logger.warning(
                            f"[{summary.id}] ⚠️ Could not find entry trade for closing position. "
                            f"Order side: {order_response.side}, inferred position: {inferred_position_side}, prev_side: {prev_side}. "
                            f"Will use strategy's position_instance_id or generate new one."
                        )
                
                # ✅ CRITICAL: Get position_instance_id with retry logic for lock contention
                # If lock is held, retry (similar to "allocation in progress" logic)
                if position_instance_id is None:
                    max_retries = 3
                    retry_delay = 0.1  # 100ms
                    
                    # ✅ FIX: Ensure new_position_size is defined (safety check)
                    try:
                        # Check if new_position_size was set in try/except block above
                        _ = new_position_size
                    except NameError:
                        # new_position_size not defined, calculate it
                        try:
                            prev_size_safe = prev_size if prev_size is not None else 0
                            if order_response.side == "BUY":
                                new_position_size = prev_size_safe + order_response.executed_qty
                            else:  # SELL
                                new_position_size = prev_size_safe + order_response.executed_qty
                        except:
                            new_position_size = order_response.executed_qty
                    
                    # ✅ FIX: Use heuristics if is_opening_new_position is uncertain
                    # If prev_size is 0 and no exit_reason, conservatively assume opening
                    if not is_closing_position:
                        try:
                            prev_size_safe = prev_size if prev_size is not None else 0
                            # Handle floating point near-zero values
                            prev_size_safe_float = abs(float(prev_size_safe)) if prev_size_safe is not None else 0
                            exit_reason = getattr(order_response, 'exit_reason', None) or getattr(signal, 'exit_reason', None)
                            has_exit_reason = exit_reason and exit_reason not in ("UNKNOWN", None)
                            
                            # Heuristic: if prev_size is effectively 0 and no exit_reason, likely opening
                            if prev_size_safe_float < 0.0001 and not has_exit_reason and order_response.executed_qty > 0:
                                if not is_opening_new_position:
                                    logger.info(
                                        f"[{summary.id}] ✅ Heuristic: Treating as opening new position "
                                        f"(prev_size={prev_size_safe}, has_exit_reason={has_exit_reason})"
                                    )
                                    is_opening_new_position = True
                        except Exception as heuristic_exc:
                            logger.debug(
                                f"[{summary.id}] Could not apply heuristic for is_opening_new_position: {heuristic_exc}"
                            )
                    
                    for attempt in range(max_retries):
                        try:
                            from app.services.strategy_persistence import StrategyPersistence
                            old_position_instance_id = db_strategy.position_instance_id
                            position_instance_id = StrategyPersistence._get_or_generate_position_instance_id(
                                self.order_manager.strategy_service.db_service.db,
                                db_strategy.id,  # Strategy UUID
                                is_opening_new_position,
                                new_position_size  # Expected size after order
                            )
                            # ✅ DEBUG: Log position_instance_id generation result
                            logger.debug(
                                f"[{summary.id}] position_instance_id generation result: "
                                f"returned={position_instance_id}, is_opening_new_position={is_opening_new_position}, "
                                f"old_id={old_position_instance_id}, new_position_size={new_position_size}"
                            )
                            # ✅ DEBUG: Log position_instance_id generation
                            if is_opening_new_position and position_instance_id != old_position_instance_id:
                                logger.info(
                                    f"[{summary.id}] ✅ Generated NEW position_instance_id={position_instance_id} "
                                    f"for opening position (old was {old_position_instance_id})"
                                )
                            elif is_opening_new_position and position_instance_id == old_position_instance_id:
                                logger.warning(
                                    f"[{summary.id}] ⚠️ Opening new position but got SAME position_instance_id={position_instance_id} "
                                    f"as previous position. This may cause incorrect trade matching!"
                                )
                            elif not is_opening_new_position and position_instance_id:
                                logger.debug(
                                    f"[{summary.id}] Using existing position_instance_id={position_instance_id} "
                                    f"(not opening new position)"
                                )
                            break  # Success
                        except ValueError as e:
                            if "generation in progress" in str(e) and attempt < max_retries - 1:
                                # Lock contention - retry after delay
                                import time
                                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                                logger.debug(
                                    f"[{summary.id}] Retry {attempt + 1}/{max_retries} for position_instance_id generation"
                                )
                                continue
                            raise  # Re-raise if not retryable or max retries reached
                
                # Update in-memory summary (for quick access)
                summary.position_instance_id = position_instance_id
            except Exception as pos_id_exc:
                # Log error but continue - position_instance_id generation is not critical for completed trade creation
                logger.warning(
                    f"[{summary.id}] Error in position_instance_id logic: {pos_id_exc}. "
                    f"Will continue without it (completed trade creation may still work).",
                    exc_info=True
                )
                # Set to None so code continues
                position_instance_id = None
                # ✅ FIX: Also set is_opening_new_position and is_closing_position for consistency
                # These might be used later even if exception occurred
                if 'is_opening_new_position' not in locals():
                    is_opening_new_position = False
                if 'is_closing_position' not in locals():
                    is_closing_position = False
                if 'new_position_size' not in locals():
                    try:
                        prev_size_safe = prev_size if prev_size is not None else 0
                        new_position_size = prev_size_safe + order_response.executed_qty
                    except:
                        new_position_size = order_response.executed_qty
        
        # ✅ CRITICAL: Save trade with position_instance_id BEFORE updating position state
        # This ensures exit trades get the ID before position is cleared
        if self.order_manager.trade_service and self.order_manager.user_id and db_strategy:
            try:
                # ✅ DEBUG: Log position_instance_id before saving
                logger.info(
                    f"[{summary.id}] Saving trade {order_response.order_id} ({order_response.side} {order_response.executed_qty} {order_response.symbol}) "
                    f"with position_instance_id={position_instance_id}, "
                    f"strategy.position_instance_id={db_strategy.position_instance_id}"
                )
                # ✅ CRITICAL: Copy exit_reason from signal to order_response before saving
                # This ensures position_side is correctly inferred (SELL with exit_reason = LONG, etc.)
                if signal.exit_reason and not order_response.exit_reason:
                    order_response = order_response.model_copy(update={"exit_reason": signal.exit_reason})
                
                # ✅ CRITICAL: Save trade with flush only (commit=False) to ensure atomicity
                # with position_instance_id. Both will be committed together below.
                trade = self.order_manager.trade_service.save_trade(
                    self.order_manager.user_id,
                    db_strategy.id,
                    order_response,
                    position_instance_id=position_instance_id,  # ✅ Pass ID
                    commit=False  # ✅ Flush only - commit together with position_instance_id
                )
                logger.info(
                    f"[{summary.id}] ✅ Saved trade {trade.id} (order_id={trade.order_id}) "
                    f"with position_instance_id={trade.position_instance_id} "
                    f"(passed={position_instance_id})"
                )
                
                # ✅ CRITICAL: Commit after trade is saved (strategy update was flushed, not committed)
                # This ensures both strategy and trade are committed together (atomicity)
                self.order_manager.strategy_service.db_service.db.commit()
            except Exception as e:
                # Rollback both strategy and trade if save fails
                self.order_manager.strategy_service.db_service.db.rollback()
                logger.error(f"[{summary.id}] Failed to save trade with position_instance_id: {e}")
                raise
        
        # Track the trade in memory
        self.order_manager.track_trade(
            strategy_id=summary.id,
            order_response=order_response,
            exit_reason=signal.exit_reason,
        )
        
        # Update position state based on order
        # (Previous state already captured above)
        
        # Log position state before order for debugging
        logger.debug(
            f"[{summary.id}] Position state BEFORE order {order_response.order_id}: "
            f"side={prev_side}, size={prev_size}, entry={prev_entry}"
        )
        
        # Determine position direction and exit reason for logging (BEFORE updating position state)
        # This must be done before mutation to correctly detect position changes
        position_direction = prev_side  # Position before order execution
        exit_reason = signal.exit_reason or "UNKNOWN"
        
        # ✅ CRITICAL FIX #1: If exit_reason is set (not UNKNOWN), we're definitely closing a position
        # This is the most reliable indicator - exit_reason only exists when closing
        if exit_reason and exit_reason != "UNKNOWN":
            # Exit reason means we're closing - infer position side from order side
            if order_response.side == "SELL":
                position_direction = "LONG"  # SELL closes LONG
                logger.info(
                    f"[{summary.id}] ✅ Exit reason detected ({exit_reason}) - inferring closing LONG position "
                    f"from SELL order. prev_side={prev_side}, prev_size={prev_size}"
                )
            elif order_response.side == "BUY":
                position_direction = "SHORT"  # BUY closes SHORT
                logger.info(
                    f"[{summary.id}] ✅ Exit reason detected ({exit_reason}) - inferring closing SHORT position "
                    f"from BUY order. prev_side={prev_side}, prev_size={prev_size}"
                )
        # ✅ CRITICAL FIX #2: If position_side is None but position_size > 0, infer position side from order
        # This handles cases where position_side is out of sync but position_size is correct
        elif position_direction is None and prev_size and prev_size > 0:
            # Infer position side from order side (opposite of what opens)
            # SELL order with position = closing LONG, BUY order with position = closing SHORT
            if order_response.side == "SELL":
                position_direction = "LONG"  # SELL closes LONG
                logger.warning(
                    f"[{summary.id}] Position side was None but position_size={prev_size} > 0. "
                    f"Inferring LONG position from SELL order (closing position)."
                )
            elif order_response.side == "BUY":
                position_direction = "SHORT"  # BUY closes SHORT
                logger.warning(
                    f"[{summary.id}] Position side was None but position_size={prev_size} > 0. "
                    f"Inferring SHORT position from BUY order (closing position)."
                )
        
        # Determine if this is opening or closing (BEFORE updating position state)
        is_opening_order = (
            (order_response.side == "BUY" and position_direction is None) or
            (order_response.side == "SELL" and position_direction is None)
        )
        is_closing_order = (
            (order_response.side == "SELL" and position_direction == "LONG") or
            (order_response.side == "BUY" and position_direction == "SHORT")
        )
        
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
        
        # Log position detection for debugging
        logger.debug(
            f"[{summary.id}] Position detection for order {order_response.order_id}: "
            f"prev_side={prev_side}, position_direction={position_direction}, "
            f"is_opening={is_opening_order}, is_closing={is_closing_order}"
        )
        
        if is_opening_order:
            new_position = "LONG" if order_response.side == "BUY" else "SHORT"
            logger.info(
                f"[{summary.id}] 🟢 OPEN {new_position} position: "
                f"{order_response.side} {order_response.symbol} "
                f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price:.8f}"
            )
            # Send Telegram notification for opening position
            if self.notifications:
                asyncio.create_task(
                    self.notifications.notify_order_executed(
                        summary,
                        order_response,
                        position_action="OPEN",
                        exit_reason=None,
                    )
                )
        elif is_closing_order:
            # ✅ CRITICAL: Ensure position_direction is set correctly for completed trade creation
            if position_direction is None:
                # Fallback: infer from order side if we have exit_reason
                if exit_reason and exit_reason != "UNKNOWN":
                    if order_response.side == "SELL":
                        position_direction = "LONG"  # SELL closes LONG
                    elif order_response.side == "BUY":
                        position_direction = "SHORT"  # BUY closes SHORT
                    logger.warning(
                        f"[{summary.id}] Position direction was None but is_closing_order=True. "
                        f"Inferred {position_direction} from order side {order_response.side} and exit_reason {exit_reason}"
                    )
            logger.info(
                f"[{summary.id}] 🔴 CLOSE {position_direction} position (reason: {exit_reason}): "
                f"{order_response.side} {order_response.symbol} "
                f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price:.8f}"
            )
            
            # ✅ CRITICAL FIX: Clear position_instance_id immediately after position closes
            # This prevents stale ID from being used for next position
            if db_strategy and db_strategy.position_instance_id:
                old_id = db_strategy.position_instance_id
                db_strategy.position_instance_id = None
                summary.position_instance_id = None
                try:
                    self.order_manager.strategy_service.db_service.db.commit()
                    logger.info(
                        f"[{summary.id}] ✅ Cleared position_instance_id={old_id} after position closed "
                        f"(exit_order_id={order_response.order_id})"
                    )
                except Exception as clear_exc:
                    self.order_manager.strategy_service.db_service.db.rollback()
                    logger.error(
                        f"[{summary.id}] Failed to clear position_instance_id after position close: {clear_exc}"
                    )
            
            # ✅ Create completed trades when position closes (ON-WRITE)
            # This pre-computes matched trades for better performance
            if self.order_manager.strategy_service and self.order_manager.user_id:
                try:
                    from app.services.completed_trade_helper import create_completed_trades_on_position_close
                    from app.models.db_models import Trade as DBTrade
                    
                    # Get strategy UUID first (summary.id is strategy_id string, not UUID)
                    db_strategy = self.order_manager.strategy_service.db_service.get_strategy(
                        self.order_manager.user_id,
                        summary.id
                    )
                    
                    if not db_strategy:
                        logger.warning(
                            f"[{summary.id}] Strategy not found in database. Cannot create completed trades."
                        )
                    else:
                        # Get exit trade UUID (just saved)
                        # Use a temporary session to get exit trade ID (needed before background thread)
                        from app.core.database import get_session_factory
                        temp_db = get_session_factory()()
                        try:
                            exit_trade = temp_db.query(DBTrade).filter(
                                DBTrade.strategy_id == db_strategy.id,  # Use UUID, not string
                                DBTrade.order_id == order_response.order_id
                            ).first()
                            
                            if exit_trade:
                                # Create completed trades (non-blocking - fire and forget)
                                # CRITICAL FIX: Don't pass database session - function creates its own (thread-safe)
                                async def create_completed_trades_task():
                                    """Wrapper to catch and log errors from background task."""
                                    try:
                                        # Pass strategy UUID as string for better lookup reliability
                                        completed_trade_ids = await asyncio.to_thread(
                                            create_completed_trades_on_position_close,
                                            self.order_manager.user_id,
                                            str(db_strategy.id),  # Pass UUID as string for better lookup
                                            exit_trade.id,  # Exit trade UUID
                                            order_response.order_id,  # Exit order ID
                                            order_response.executed_qty,  # Exit quantity
                                            float(order_response.avg_price or order_response.price),  # Exit price
                                            position_direction,  # Position side (LONG or SHORT)
                                            exit_reason,  # Exit reason
                                        )
                                        if completed_trade_ids:
                                            logger.info(
                                                f"[{summary.id}] ✅ Completed trade creation task finished successfully: "
                                                f"created {len(completed_trade_ids)} completed trades for exit_order_id={order_response.order_id}"
                                            )
                                        else:
                                            logger.warning(
                                                f"[{summary.id}] ⚠️ Completed trade creation task finished but NO trades were created "
                                                f"for exit_order_id={order_response.order_id}. Check logs above for details."
                                        )
                                    except Exception as task_error:
                                        # Log error but don't fail the main flow
                                        logger.error(
                                            f"[{summary.id}] ❌ CRITICAL: Background task failed to create completed trades "
                                            f"for exit_order_id={order_response.order_id}, position_side={position_direction}: {task_error}",
                                            exc_info=True
                                        )
                                
                                asyncio.create_task(create_completed_trades_task())
                                logger.debug(
                                    f"[{summary.id}] Started background task to create completed trades: "
                                    f"exit_trade_id={exit_trade.id}, exit_order_id={order_response.order_id}, "
                                    f"position_side={position_direction}"
                                )
                            else:
                                logger.warning(
                                    f"[{summary.id}] Exit trade {order_response.order_id} not found in database. "
                                    f"Cannot create completed trades."
                                )
                        finally:
                            temp_db.close()
                except Exception as e:
                    # Don't fail position closing if completed trade creation fails
                    logger.warning(
                        f"[{summary.id}] Failed to create completed trades on position close: {e}",
                        exc_info=True
                    )
            else:
                # ✅ FALLBACK: If is_closing_order was False but we have exit_reason and position_size was > 0,
                # we might still need to create completed trades (position detection failed)
                if exit_reason and exit_reason != "UNKNOWN" and prev_size and prev_size > 0:
                    logger.warning(
                        f"[{summary.id}] ⚠️ Position detection failed (is_closing_order=False) but exit_reason={exit_reason} "
                        f"and prev_size={prev_size} suggest position was closed. Attempting to create completed trades anyway."
                    )
                    # Try to create completed trades with inferred position side
                    inferred_position_side = "LONG" if order_response.side == "SELL" else "SHORT"
                    if self.order_manager.strategy_service and self.order_manager.user_id:
                        try:
                            from app.services.completed_trade_helper import create_completed_trades_on_position_close
                            from app.models.db_models import Trade as DBTrade
                            
                            db_strategy = self.order_manager.strategy_service.db_service.get_strategy(
                                self.order_manager.user_id,
                                summary.id
                            )
                            
                            if db_strategy:
                                from app.core.database import get_session_factory
                                temp_db = get_session_factory()()
                                try:
                                    exit_trade = temp_db.query(DBTrade).filter(
                                        DBTrade.strategy_id == db_strategy.id,
                                        DBTrade.order_id == order_response.order_id
                                    ).first()
                                    
                                    if exit_trade:
                                        async def create_completed_trades_fallback_task():
                                            try:
                                                # Pass strategy UUID as string for better lookup
                                                await asyncio.to_thread(
                                                    create_completed_trades_on_position_close,
                                                    self.order_manager.user_id,
                                                    str(db_strategy.id),  # Pass UUID as string
                                                    exit_trade.id,
                                                    order_response.order_id,
                                                    order_response.executed_qty,
                                                    float(order_response.avg_price or order_response.price),
                                                    inferred_position_side,  # Use inferred position side
                                                    exit_reason,
                                                )
                                                logger.info(
                                                    f"[{summary.id}] ✅ Fallback completed trade creation finished successfully "
                                                    f"for exit_order_id={order_response.order_id}, inferred_position_side={inferred_position_side}"
                                                )
                                            except Exception as task_error:
                                                logger.error(
                                                    f"[{summary.id}] ❌ Fallback completed trade creation failed: {task_error}",
                                                    exc_info=True
                                                )
                                        
                                        asyncio.create_task(create_completed_trades_fallback_task())
                                        logger.info(
                                            f"[{summary.id}] 🔵 Started FALLBACK completed trade creation: "
                                            f"exit_order_id={order_response.order_id}, inferred_position_side={inferred_position_side}"
                                        )
                                finally:
                                    temp_db.close()
                        except Exception as e:
                            logger.warning(
                                f"[{summary.id}] Fallback completed trade creation setup failed: {e}",
                                exc_info=True
                            )
            
            # Send Telegram notification for closing position
            if self.notifications:
                asyncio.create_task(
                    self.notifications.notify_order_executed(
                        summary,
                        order_response,
                        position_action="CLOSE",
                        exit_reason=exit_reason,
                    )
                )
        else:
            logger.info(
                f"[{summary.id}] 📊 Trade executed: "
                f"{order_response.side} {order_response.symbol} "
                f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price:.8f} "
                f"(position: {position_direction}, exit_reason: {exit_reason})"
            )
            # Send Telegram notification for trade execution
            if self.notifications:
                asyncio.create_task(
                    self.notifications.notify_order_executed(
                        summary,
                        order_response,
                        position_action="TRADE",
                        exit_reason=exit_reason,
                    )
                )
        
        # Place Binance native TP/SL orders when opening a new position
        has_position = summary.position_size and summary.position_size > 0
        has_entry_price = summary.entry_price is not None
        tp_sl_meta = summary.meta.get("tp_sl_orders", {})
        tp_order_id = tp_sl_meta.get("tp_order_id")
        sl_order_id = tp_sl_meta.get("sl_order_id")
        
        # Check if stored order IDs are still valid (orders still exist on Binance)
        has_valid_orders = False
        if tp_order_id or sl_order_id:
            try:
                account_id = summary.account_id or "default"
                account_client = self.account_manager.get_account_client(account_id)
                open_orders = await asyncio.to_thread(account_client.get_open_orders, summary.symbol)
                open_order_ids = {o.get("orderId") for o in open_orders}
                has_valid_orders = (tp_order_id in open_order_ids) or (sl_order_id in open_order_ids)
                
                # If orders don't exist anymore, clear the stale metadata
                if not has_valid_orders:
                    logger.info(
                        f"[{summary.id}] Stale TP/SL order IDs detected (orders no longer exist). "
                        f"Clearing metadata."
                    )
                    summary.meta["tp_sl_orders"] = {}
                    self.state_manager.save_to_redis(summary.id, summary)
            except Exception as exc:
                logger.warning(
                    f"[{summary.id}] Failed to verify TP/SL orders exist: {exc}. "
                    f"Assuming they exist for safety."
                )
                has_valid_orders = True  # Assume they exist if we can't verify
        
        # ✅ CRITICAL FIX: Only place TP/SL if we're opening AND position wasn't just closed
        # Check if position was just closed - if so, skip TP/SL placement
        position_was_closed = is_closing_order or (exit_reason and exit_reason != "UNKNOWN")
        
        # Check if we're opening a position (not closing)
        is_opening = (
            has_position and 
            has_entry_price and 
            summary.position_side is not None and  # ✅ Ensure position_side is set
            not has_valid_orders and
            not position_was_closed  # ✅ Don't place TP/SL if position was just closed
        )
        
        if is_opening:
            try:
                # CRITICAL: Add timeout to prevent getting stuck on TP/SL order placement
                await asyncio.wait_for(
                    self.order_manager.place_tp_sl_orders(summary, order_response),
                    timeout=30.0  # 30 second timeout for TP/SL order placement
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[{summary.id}] TP/SL order placement TIMED OUT after 30 seconds. "
                    f"Strategy will still monitor TP/SL, but Binance native orders not active."
                )
            except Exception as exc:
                # Safely extract error message to avoid KeyError when accessing details
                error_msg = str(exc)
                # If it's a RetryError, try to get the underlying exception message
                try:
                    from tenacity import RetryError
                    if isinstance(exc, RetryError) and hasattr(exc, 'last_attempt') and exc.last_attempt:
                        underlying = exc.last_attempt.exception()
                        error_msg = str(underlying)
                except Exception:
                    pass  # Fall back to original error message
                
                logger.warning(
                    f"[{summary.id}] Failed to place TP/SL orders on Binance: {error_msg}. "
                    f"Strategy will still monitor TP/SL, but Binance native orders not active."
                )
        
        # Cancel existing TP/SL orders if position was closed via our own order
        position_closed = summary.position_size == 0 or summary.position_side is None
        has_order_ids = bool(tp_order_id or sl_order_id)
        if position_closed and has_order_ids:
            try:
                # CRITICAL: Add timeout to prevent getting stuck on TP/SL order cancellation
                await asyncio.wait_for(
                    self.order_manager.cancel_tp_sl_orders(summary),
                    timeout=30.0  # 30 second timeout for TP/SL order cancellation
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[{summary.id}] TP/SL order cancellation TIMED OUT after 30 seconds. "
                    f"Orders may still exist on Binance."
                )
            except Exception as exc:
                logger.warning(f"[{summary.id}] Failed to cancel TP/SL orders: {exc}")
        
        # CRITICAL: Sync strategy's internal state immediately after order execution
        # This ensures the strategy knows about position changes (especially for cooldown)
        if strategy:
            try:
                # Update position info from Binance to ensure summary is accurate
                # CRITICAL: Add timeout to prevent getting stuck on position update
                try:
                    await asyncio.wait_for(
                        self.state_manager.update_position_info(summary),
                        timeout=30.0  # 30 second timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"[{summary.id}] Position update after order execution timed out. "
                        f"Continuing with potentially stale position data."
                    )
                # Sync strategy's internal state with updated summary
                strategy.sync_position_state(
                    position_side=summary.position_side,
                    entry_price=summary.entry_price,
                )
                
                # CRITICAL: Only set entry_candle_time for RangeMeanReversionStrategy as fallback
                # Scalping strategy already sets entry_candle_time correctly when generating signal
                from app.strategies.range_mean_reversion import RangeMeanReversionStrategy
                
                if (
                    isinstance(strategy, RangeMeanReversionStrategy)
                    and summary.position_side is not None
                    and summary.entry_price is not None
                ):
                    # Only fill if missing; never overwrite a value set by the strategy at signal time
                    if getattr(strategy, "entry_candle_time", None) is None:
                        lct = getattr(strategy, "last_closed_candle_time", None)
                        if lct is not None:
                            strategy.entry_candle_time = lct
                            logger.debug(
                                f"[{summary.id}] entry_candle_time initialized to {lct} after execution (was None)"
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
                # CRITICAL: Add timeout to prevent getting stuck on fallback position update
                await asyncio.wait_for(
                    self.state_manager.update_position_info(summary),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logger.debug(f"[{summary.id}] Fallback position update timed out (non-critical)")
            except Exception as exc:
                logger.debug(f"[{summary.id}] Failed to update position info after order execution: {exc}")
    
    async def _wait_for_next_evaluation(
        self,
        strategy: Strategy,
        summary: StrategySummary,
    ) -> None:
        """Wait for next evaluation trigger (new candle event or timeout).
        
        This synchronizes strategies so they all evaluate simultaneously when a new candle arrives,
        while still allowing periodic evaluation for TP/SL checks even if no new candle arrives.
        
        Args:
            strategy: Strategy instance
            summary: Strategy summary
        """
        # Try to wait for new candle event if kline_manager is available
        if strategy.kline_manager:
            try:
                # Get kline interval from strategy params
                kline_interval = strategy.context.params.get("kline_interval", "1m")
                
                # Wait for new candle event with timeout (interval_seconds)
                # This ensures strategies evaluate simultaneously when new candle arrives,
                # but still evaluate periodically for TP/SL checks even if no new candle
                new_candle_arrived = await strategy.kline_manager.wait_for_new_candle(
                    symbol=summary.symbol,
                    interval=kline_interval,
                    timeout=strategy.context.interval_seconds
                )
                
                if new_candle_arrived:
                    logger.debug(
                        f"[{summary.id}] New candle event triggered evaluation for {summary.symbol} {kline_interval}"
                    )
                else:
                    # Timeout - no new candle, but still evaluate for TP/SL checks
                    logger.debug(
                        f"[{summary.id}] Evaluation timeout (no new candle) - checking TP/SL for {summary.symbol}"
                    )
            except Exception as e:
                # Fallback to sleep if event waiting fails
                logger.debug(f"[{summary.id}] Event waiting failed, using sleep fallback: {e}")
                await asyncio.sleep(strategy.context.interval_seconds)
        else:
            # No kline_manager - fallback to sleep
            await asyncio.sleep(strategy.context.interval_seconds)


