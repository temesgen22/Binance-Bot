"""Order execution and TP/SL management for strategies."""

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Optional

from loguru import logger

from app.core.exceptions import (
    InvalidLeverageError,
    PositionSizingError,
    OrderExecutionError,
    BinanceAPIError,
)
from app.core.my_binance_client import BinanceClient
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary
from app.risk.manager import RiskManager, PositionSizingResult
from app.services.order_executor import OrderExecutor
from app.services.strategy_account_manager import StrategyAccountManager
from app.strategies.base import Strategy, StrategySignal

if TYPE_CHECKING:
    from app.services.trade_service import TradeService
    from app.services.strategy_service import StrategyService
    from uuid import UUID


class StrategyOrderManager:
    """Manages order execution and TP/SL orders for strategies."""
    
    def __init__(
        self,
        account_manager: StrategyAccountManager,
        default_risk: Optional[RiskManager] = None,
        default_executor: Optional[OrderExecutor] = None,
        trade_service: Optional["TradeService"] = None,
        user_id: Optional["UUID"] = None,
        strategy_service: Optional["StrategyService"] = None,
        redis_storage=None,  # Optional RedisStorage
        strategies: Optional[dict] = None,  # Reference to strategies dict
        trades: Optional[dict] = None,  # Reference to trades dict
        lock: Optional[asyncio.Lock] = None,  # Lock for thread safety
    ) -> None:
        """Initialize the order manager.
        
        Args:
            account_manager: Account manager for getting clients
            default_risk: Default risk manager (optional)
            default_executor: Default order executor (optional)
            trade_service: Trade service for database persistence
            user_id: User ID for multi-user mode
            strategy_service: Strategy service for looking up strategy UUID
            redis_storage: Redis storage for persistence
            strategies: Reference to strategies dictionary
            trades: Reference to trades dictionary
            lock: Async lock for thread safety
        """
        self.account_manager = account_manager
        self.default_risk = default_risk
        self.default_executor = default_executor
        self.trade_service = trade_service
        self.user_id = user_id
        self.strategy_service = strategy_service
        self.redis = redis_storage
        self._strategies = strategies if strategies is not None else {}
        self._trades = trades if trades is not None else {}
        self._lock = lock
    
    async def execute_order(
        self,
        signal: StrategySignal,
        summary: StrategySummary,
        strategy: Optional[Strategy] = None,
        risk: Optional[RiskManager] = None,
        executor: Optional[OrderExecutor] = None,
    ) -> Optional[OrderResponse]:
        """Execute an order based on a strategy signal.
        
        Args:
            signal: Strategy signal to execute
            summary: Strategy summary
            strategy: Strategy instance (optional, for state sync)
            risk: Risk manager (optional, uses default if not provided)
            executor: Order executor (optional, uses default if not provided)
            
        Returns:
            OrderResponse if order was executed, None if skipped
            
        Raises:
            InvalidLeverageError: If leverage is invalid
            PositionSizingError: If position sizing fails
            OrderExecutionError: If order execution fails
            BinanceAPIError: If Binance API call fails
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
            account_executor = OrderExecutor(
                client=account_client,
                trade_service=self.trade_service,
                user_id=self.user_id,
            )
        
        # Log account being used for order execution
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
            return None
        
        # CRITICAL: Leverage in Binance is PER SYMBOL, not per strategy.
        # Binance defaults to 20x leverage if not explicitly set.
        # We MUST ensure leverage is explicitly set before every order to avoid accidental 20x.
        
        # Validate leverage is present and valid
        if summary.leverage is None or not (1 <= summary.leverage <= 50):
            logger.error(
                f"[{summary.id}] CRITICAL: Invalid or missing leverage for {summary.symbol}: {summary.leverage}"
            )
            raise InvalidLeverageError(
                leverage=summary.leverage or 0,
                reason=f"Leverage must be explicitly set (1-50) to avoid Binance's default 20x leverage for {summary.symbol}"
            )
        
        try:
            # Wrap sync BinanceClient call in to_thread to avoid blocking event loop
            current_leverage = await asyncio.to_thread(account_client.get_current_leverage, summary.symbol)
            # Check None first, then mismatch
            if current_leverage is None:
                # No position yet, set leverage proactively to prevent Binance default
                logger.info(
                    f"[{summary.id}] Setting leverage {summary.leverage}x for {summary.symbol} "
                    f"(no existing position - preventing Binance 20x default)"
                )
                await asyncio.to_thread(account_client.adjust_leverage, summary.symbol, summary.leverage)
            elif current_leverage != summary.leverage:
                logger.warning(
                    f"[{summary.id}] Leverage mismatch detected for {summary.symbol}: "
                    f"current={current_leverage}x (may be Binance default), target={summary.leverage}x. "
                    f"Resetting to {summary.leverage}x"
                )
                await asyncio.to_thread(account_client.adjust_leverage, summary.symbol, summary.leverage)
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
        current_position = await asyncio.to_thread(account_client.get_open_position, summary.symbol)
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
                price = signal.price or await asyncio.to_thread(account_client.get_price, signal.symbol)
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
                price = signal.price or await asyncio.to_thread(account_client.get_price, signal.symbol)
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
            # Pass strategy_id for idempotency tracking
            order_response = account_executor.execute(
                signal=signal,
                sizing=sizing,
                reduce_only_override=reduce_only_override,
                strategy_id=summary.id,
            )
        except (OrderExecutionError, BinanceAPIError) as exc:
            # Log and re-raise API errors
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
        
        # Update summary with order execution results and track trade
        if order_response:
            # Only update if order was filled (not NEW with zero execution)
            if not (order_response.status == "NEW" and order_response.executed_qty == 0):
                # Track the trade in memory (protected with lock)
                order_with_exit_reason = order_response.model_copy(
                    update={"exit_reason": signal.exit_reason} if signal.exit_reason else {}
                )
                async with self._lock:
                    if summary.id not in self._trades:
                        self._trades[summary.id] = []
                    self._trades[summary.id].append(order_with_exit_reason)
                
                # Save to Redis if enabled (via persistence if available)
                if self.redis and self.redis.enabled:
                    try:
                        trades = self._trades.get(summary.id, [])
                        trades_data = [trade.model_dump(mode='json') for trade in trades]
                        self.redis.save_trades(summary.id, trades_data)
                    except Exception as exc:
                        logger.warning(f"Failed to save trades for {summary.id} to Redis: {exc}")
                
                # CRITICAL: Save to database immediately after order execution
                # This ensures orders are persisted even if system restarts
                if self.trade_service and self.user_id and self.strategy_service:
                    try:
                        # Get strategy UUID from database (needed for foreign key)
                        # Use database service directly to get Strategy model (which has UUID id)
                        db_strategy = None
                        if hasattr(self.strategy_service, 'db_service'):
                            try:
                                # DatabaseService.get_strategy returns Strategy model with UUID id
                                db_strategy = self.strategy_service.db_service.get_strategy(
                                    self.user_id, 
                                    summary.id
                                )
                            except RuntimeError as e:
                                # If sync method not available (async mode), log warning
                                logger.warning(
                                    f"[{summary.id}] ⚠️ Cannot get strategy from database (async mode): {e}. "
                                    f"Trade {order_response.order_id} will be saved via background task or reconciliation."
                                )
                                db_strategy = None
                        else:
                            # Fallback: try strategy_service.get_strategy (returns StrategySummary, not Strategy model)
                            # This won't work directly, but we can extract the id if available
                            logger.warning(
                                f"[{summary.id}] ⚠️ Strategy service has no db_service, cannot get strategy UUID. "
                                f"Trade {order_response.order_id} may not be saved to database."
                            )
                        
                        if db_strategy:
                            # Check for duplicate before saving (optimization to avoid IntegrityError)
                            # Note: save_trade() also handles duplicates, but this avoids the error
                            try:
                                from app.models.db_models import Trade as DBTrade
                                existing_trade = self.strategy_service.db_service.db.query(DBTrade).filter(
                                    Trade.strategy_id == db_strategy.id,
                                    Trade.order_id == order_response.order_id
                                ).first()
                                
                                if existing_trade:
                                    logger.info(
                                        f"[{summary.id}] Order {order_response.order_id} already exists in database. "
                                        f"Skipping duplicate save."
                                    )
                                else:
                                    # Save trade to database
                                    self.trade_service.save_trade(
                                        user_id=self.user_id,
                                        strategy_id=db_strategy.id,  # UUID from database
                                        order=order_with_exit_reason
                                    )
                                    logger.info(
                                        f"[{summary.id}] ✅ Saved trade {order_response.order_id} to database "
                                        f"({order_response.side} {order_response.executed_qty} {order_response.symbol})"
                                    )
                            except Exception as check_exc:
                                # If duplicate check fails, still try to save (save_trade handles duplicates)
                                logger.warning(
                                    f"[{summary.id}] Error checking for duplicate order: {check_exc}. "
                                    f"Attempting save anyway (will handle duplicates)."
                                )
                                self.trade_service.save_trade(
                                    user_id=self.user_id,
                                    strategy_id=db_strategy.id,
                                    order=order_with_exit_reason
                                )
                                logger.info(
                                    f"[{summary.id}] ✅ Saved trade {order_response.order_id} to database "
                                    f"({order_response.side} {order_response.executed_qty} {order_response.symbol})"
                                )
                        else:
                            logger.warning(
                                f"[{summary.id}] ⚠️ Could not find strategy in database to save trade {order_response.order_id}. "
                                f"Trade exists in Binance but not recorded in database."
                            )
                    except Exception as e:
                        logger.error(
                            f"[{summary.id}] ❌ CRITICAL: Failed to save trade {order_response.order_id} to database: {e}. "
                            f"Order exists in Binance (order_id={order_response.order_id}) but not recorded in database. "
                            f"This may cause PnL calculation errors and incomplete trade history. "
                            f"Please check database connection and retry manually if needed.",
                            exc_info=True
                        )
                        # Don't raise - order is already in Binance, can't undo
                        # Trade is still tracked in memory/Redis, can be recovered later
                
                # Update entry price and position size based on order side
                if order_response.side == "BUY":
                    if summary.position_side == "SHORT":
                        # Closing short position
                        remaining = max(0.0, (summary.position_size or 0.0) - order_response.executed_qty)
                        summary.position_size = remaining
                        if remaining == 0:
                            summary.entry_price = None
                            summary.position_side = None
                    else:
                        # Opening or adding to long position
                        summary.entry_price = order_response.avg_price or order_response.price
                        summary.position_size = order_response.executed_qty
                        summary.position_side = "LONG"
                elif order_response.side == "SELL":
                    if summary.position_side == "LONG":
                        # Closing long position
                        remaining = max(0.0, (summary.position_size or 0.0) - order_response.executed_qty)
                        summary.position_size = remaining
                        if remaining == 0:
                            summary.entry_price = None
                            summary.position_side = None
                    else:
                        # Opening or adding to short position
                        summary.entry_price = order_response.avg_price or order_response.price
                        summary.position_size = order_response.executed_qty
                        summary.position_side = "SHORT"
        
        return order_response
    
    def track_trade(
        self,
        strategy_id: str,
        order_response: OrderResponse,
        exit_reason: Optional[str] = None,
    ) -> None:
        """Track a trade in memory and persist to database/Redis.
        
        Args:
            strategy_id: Strategy ID
            order_response: Order response to track
            exit_reason: Exit reason for the trade (optional)
        """
        # Only track filled orders (or orders with execution data)
        if order_response.status == "NEW" and order_response.executed_qty == 0:
            logger.warning(
                f"[{strategy_id}] Order {order_response.order_id} status is NEW with zero execution. "
                f"Skipping trade tracking. Order may not be filled yet."
            )
            return
        
        # Track the executed trade in memory
        order_with_exit_reason = order_response.model_copy(
            update={"exit_reason": exit_reason} if exit_reason else {}
        )
        
        if self._lock:
            # Protected with lock to prevent race conditions
            async def _add_trade():
                async with self._lock:
                    if strategy_id not in self._trades:
                        self._trades[strategy_id] = []
                    self._trades[strategy_id].append(order_with_exit_reason)
            
            # Note: This is a sync method, but we need to handle async lock
            # For now, we'll add directly if lock is None, or use a sync approach
            # TODO: Make this method async or use a sync lock
            if strategy_id not in self._trades:
                self._trades[strategy_id] = []
            self._trades[strategy_id].append(order_with_exit_reason)
        else:
            if strategy_id not in self._trades:
                self._trades[strategy_id] = []
            self._trades[strategy_id].append(order_with_exit_reason)
        
        # Save to database if TradeService is available
        if self.trade_service and self.user_id:
            try:
                # Get strategy UUID from database
                # Note: This requires access to strategy_service, which we don't have here
                # This will need to be handled by the caller or passed as a parameter
                logger.debug(f"Trade tracking: database save requires strategy_service (handled by caller)")
            except Exception as e:
                logger.warning(f"Failed to save trade to database: {e}")
        
        # Optionally save to Redis if enabled
        if self.redis and self.redis.enabled:
            try:
                trades = self._trades.get(strategy_id, [])
                trades_data = [trade.model_dump(mode='json') for trade in trades]
                self.redis.save_trades(strategy_id, trades_data)
            except Exception as exc:
                logger.warning(f"Failed to save trades for {strategy_id} to Redis: {exc}")
    
    async def place_tp_sl_orders(self, summary: StrategySummary, entry_order: OrderResponse) -> None:
        """Place Binance native TP/SL orders when opening a position.
        
        Args:
            summary: Strategy summary with position info
            entry_order: The entry order that opened the position
        """
        if not summary.entry_price or not summary.position_size or not summary.position_side:
            logger.debug(f"[{summary.id}] Cannot place TP/SL: missing position info")
            return
        
        # Get TP/SL percentages from strategy params
        if hasattr(summary.params, "take_profit_pct"):
            take_profit_pct = summary.params.take_profit_pct
            stop_loss_pct = summary.params.stop_loss_pct
            trailing_stop_enabled = summary.params.trailing_stop_enabled
        else:
            # params is a dict
            take_profit_pct = summary.params.get("take_profit_pct", 0.005)  # Default 0.5%
            stop_loss_pct = summary.params.get("stop_loss_pct", 0.003)  # Default 0.3%
            trailing_stop_enabled = summary.params.get("trailing_stop_enabled", False)
        
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
        
        # Skip if trailing stop enabled
        if trailing_stop_enabled:
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
        account_client = self.account_manager.get_account_client(account_id)
        
        tp_order_id = None
        sl_order_id = None
        
        try:
            # Place take profit order
            # Wrap sync BinanceClient call in to_thread to avoid blocking event loop
            tp_response = await asyncio.to_thread(
                partial(
                    account_client.place_take_profit_order,
                    symbol=summary.symbol,
                    side=tp_side,
                    quantity=summary.position_size,
                    stop_price=tp_price,
                    close_position=True
                )
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
            sl_response = await asyncio.to_thread(
                partial(
                    account_client.place_stop_loss_order,
                    symbol=summary.symbol,
                    side=sl_side,
                    quantity=summary.position_size,
                    stop_price=sl_price,
                    close_position=True
                )
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
    
    async def cancel_tp_sl_orders(self, summary: StrategySummary) -> None:
        """Cancel existing TP/SL orders when position is closed.
        
        Args:
            summary: Strategy summary
        """
        tp_sl_orders = summary.meta.get("tp_sl_orders", {})
        tp_order_id = tp_sl_orders.get("tp_order_id")
        sl_order_id = tp_sl_orders.get("sl_order_id")
        
        if not tp_order_id and not sl_order_id:
            return  # No orders to cancel
        
        logger.info(
            f"[{summary.id}] Cancelling TP/SL orders: TP={tp_order_id}, SL={sl_order_id}"
        )
        
        account_id = summary.account_id or "default"
        account_client = self.account_manager.get_account_client(account_id)
        
        if tp_order_id:
            try:
                # Wrap sync BinanceClient call in to_thread to avoid blocking event loop
                await asyncio.to_thread(account_client.cancel_order, summary.symbol, tp_order_id)
                logger.info(f"[{summary.id}] Cancelled TP order: {tp_order_id}")
            except Exception as exc:
                logger.warning(f"[{summary.id}] Failed to cancel TP order {tp_order_id}: {exc}")
        
        if sl_order_id:
            try:
                # Wrap sync BinanceClient call in to_thread to avoid blocking event loop
                await asyncio.to_thread(account_client.cancel_order, summary.symbol, sl_order_id)
                logger.info(f"[{summary.id}] Cancelled SL order: {sl_order_id}")
            except Exception as exc:
                logger.warning(f"[{summary.id}] Failed to cancel SL order {sl_order_id}: {exc}")
        
        # Clear order IDs from meta
        if "tp_sl_orders" in summary.meta:
            summary.meta["tp_sl_orders"] = {}
    
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

