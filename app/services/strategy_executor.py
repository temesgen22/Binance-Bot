"""Strategy execution loop and signal processing."""

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from loguru import logger

from app.core.binance_client_manager import BinanceClientManager
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
                # CRITICAL ORDER: Sync with Binance BEFORE evaluating strategy
                # This ensures strategy.evaluate() uses correct state, not stale state
                # 
                # Flow: Binance → Database (source of truth) → Redis (cache) → Memory (cache) → Strategy
                # 
                # 1) First: Sync summary from Binance reality to database (source of truth)
                await self.state_manager.update_position_info(summary)
                
                # 2) Periodic position reconciliation (every 5 minutes)
                # This ensures database state matches Binance reality even if updates were missed
                current_time = datetime.now(timezone.utc)
                time_since_reconciliation = (current_time - last_reconciliation).total_seconds()
                
                if time_since_reconciliation >= reconciliation_interval:
                    try:
                        await self.state_manager.reconcile_position_state(summary)
                        last_reconciliation = current_time
                        logger.debug(
                            f"[{summary.id}] Periodic position reconciliation completed. "
                            f"Next reconciliation in {reconciliation_interval}s"
                        )
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
                try:
                    summary.current_price = await asyncio.to_thread(account_client.get_price, summary.symbol)
                except Exception as exc:
                    logger.warning(f"Failed to get current price for {summary.symbol}: {exc}")
                
                # 6) Check PnL thresholds and notify if reached
                if self.notifications and summary.unrealized_pnl is not None:
                    await self.notifications.check_and_notify_pnl_threshold(
                        summary,
                        summary.unrealized_pnl,
                    )
                
                # 7) Execute order based on synced state + fresh signal
                # CRITICAL: Pass account-specific risk and executor to ensure orders go to correct account
                # Also pass strategy instance so we can sync state immediately after order execution
                await self._execute_order(signal, summary, strategy, account_risk, account_executor)
                
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
        order_response = await self.order_manager.execute_order(
            signal=signal,
            summary=summary,
            strategy=strategy,
            risk=risk,
            executor=executor,
        )
        
        if not order_response:
            return  # Order was skipped (e.g., HOLD signal)
        
        # Track the trade
        self.order_manager.track_trade(
            strategy_id=summary.id,
            order_response=order_response,
            exit_reason=signal.exit_reason,
        )
        
        # Update position state based on order
        # Capture previous state BEFORE mutation for correct OPEN/CLOSE detection
        prev_side = summary.position_side
        prev_size = summary.position_size
        prev_entry = summary.entry_price
        
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
        position_direction = prev_side  # Position before order execution
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
            logger.info(
                f"[{summary.id}] 🔴 CLOSE {position_direction} position (reason: {exit_reason}): "
                f"{order_response.side} {order_response.symbol} "
                f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price:.8f}"
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
        
        # Check if we're opening a position (not closing)
        is_opening = has_position and has_entry_price and not has_valid_orders
        
        if is_opening:
            try:
                await self.order_manager.place_tp_sl_orders(summary, order_response)
            except Exception as exc:
                logger.warning(
                    f"[{summary.id}] Failed to place TP/SL orders on Binance: {exc}. "
                    f"Strategy will still monitor TP/SL, but Binance native orders not active."
                )
        
        # Cancel existing TP/SL orders if position was closed via our own order
        position_closed = summary.position_size == 0 or summary.position_side is None
        has_order_ids = bool(tp_order_id or sl_order_id)
        if position_closed and has_order_ids:
            try:
                await self.order_manager.cancel_tp_sl_orders(summary)
            except Exception as exc:
                logger.warning(f"[{summary.id}] Failed to cancel TP/SL orders: {exc}")
        
        # CRITICAL: Sync strategy's internal state immediately after order execution
        # This ensures the strategy knows about position changes (especially for cooldown)
        if strategy:
            try:
                # Update position info from Binance to ensure summary is accurate
                await self.state_manager.update_position_info(summary)
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
                await self.state_manager.update_position_info(summary)
            except Exception as exc:
                logger.debug(f"[{summary.id}] Failed to update position info after order execution: {exc}")


