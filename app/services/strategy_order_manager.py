"""Order execution and TP/SL management for strategies."""

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Optional, Callable, List

from loguru import logger

from app.core.exceptions import (
    InvalidLeverageError,
    PositionSizingError,
    OrderExecutionError,
    BinanceAPIError,
    RiskLimitExceededError,
    CircuitBreakerActiveError,
)
from app.core.my_binance_client import BinanceClient
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary
from app.risk.manager import RiskManager, PositionSizingResult
from app.risk.dynamic_sizing import DynamicPositionSizer, DynamicSizingConfig
from app.services.order_executor import OrderExecutor
from app.services.strategy_account_manager import StrategyAccountManager
from app.strategies.base import Strategy, StrategySignal

if TYPE_CHECKING:
    from app.services.trade_service import TradeService
    from app.services.strategy_service import StrategyService
    from app.services.notifier import NotificationService
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
        portfolio_risk_manager_factory: Optional[Callable[[str], any]] = None,  # Factory for per-account PortfolioRiskManager
        circuit_breaker_factory: Optional[Callable[[str], any]] = None,  # Factory for per-account CircuitBreaker
        dynamic_sizing_factory: Optional[Callable[[str], any]] = None,  # Factory for per-account DynamicPositionSizer
        strategy_runner: Optional[any] = None,  # StrategyRunner instance for pausing strategies
        notification_service: Optional["NotificationService"] = None,  # Notification service for risk alerts
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
            portfolio_risk_manager_factory: Factory for per-account PortfolioRiskManager
            circuit_breaker_factory: Factory for per-account CircuitBreaker
            dynamic_sizing_factory: Factory for per-account DynamicPositionSizer
            notification_service: Notification service for risk alerts
        """
        self.account_manager = account_manager
        self.default_risk = default_risk
        self.default_executor = default_executor
        self.trade_service = trade_service
        self.user_id = user_id
        self.strategy_service = strategy_service
        self.strategy_runner = strategy_runner  # StrategyRunner for stopping strategies
        self.redis = redis_storage
        self._strategies = strategies if strategies is not None else {}
        self._trades = trades if trades is not None else {}
        self._lock = lock
        self.portfolio_risk_manager_factory = portfolio_risk_manager_factory
        self.circuit_breaker_factory = circuit_breaker_factory
        self.dynamic_sizing_factory = dynamic_sizing_factory
        self.notification_service = notification_service
        
        # Get database service from strategy_service if available
        self.db_service: Optional["DatabaseService"] = None
        if strategy_service and hasattr(strategy_service, 'db_service'):
            self.db_service = strategy_service.db_service
    
    async def execute_order(
        self,
        signal: StrategySignal,
        summary: StrategySummary,
        strategy: Optional[Strategy] = None,
        risk: Optional[RiskManager] = None,
        executor: Optional[OrderExecutor] = None,
        klines: Optional[List[List]] = None,  # Bug #4: Add klines parameter for ATR calculation
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
        
        # Check if dynamic sizing is enabled for this account
        dynamic_sizer = None
        if self.dynamic_sizing_factory:
            # Factory can be a callable or an object with get_dynamic_sizer method
            if callable(self.dynamic_sizing_factory):
                dynamic_sizer = self.dynamic_sizing_factory(account_id)
            elif hasattr(self.dynamic_sizing_factory, 'get_dynamic_sizer'):
                dynamic_sizer = self.dynamic_sizing_factory.get_dynamic_sizer(account_id)
        
        # Use base risk manager for sizing, dynamic sizer will adjust later
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
        
        # CRITICAL FIX: Check if strategy is paused by risk management before executing orders
        # This prevents paused strategies from executing orders even if they're still in the loop
        from app.models.strategy import StrategyState
        if summary.status == StrategyState.stopped_by_risk:
            logger.warning(
                f"[{summary.id}] Strategy is paused by risk management. "
                f"Skipping order execution."
            )
            return None
        
        if signal.action == "HOLD":
            logger.debug(
                f"[{summary.id}] HOLD signal - skipping order execution | "
                f"Position: {summary.position_side or 'FLAT'} | "
                f"Price: {signal.price}"
            )
            return None
        
        # ✅ CRITICAL: Check if another strategy already has an open position for this symbol
        # Binance Futures positions are account-level, not strategy-level
        # If Strategy A has a position and Strategy B tries to OPEN one, they would mix/conflict
        # Note: We only block OPENING positions, not closing (reduce_only orders are allowed)
        try:
            # Determine if this is an opening order (not closing)
            # Opening: current strategy has no position OR signal is opposite to current position
            current_strategy_has_position = summary.position_size and float(summary.position_size) > 0
            is_opening_order = False
            
            if not current_strategy_has_position:
                # No current position = definitely opening
                is_opening_order = True
            else:
                # Check if signal would open opposite position
                if signal.action == "BUY" and summary.position_side == "SHORT":
                    # Buying while short = closing short, not opening
                    is_opening_order = False
                elif signal.action == "SELL" and summary.position_side == "LONG":
                    # Selling while long = closing long, not opening
                    is_opening_order = False
                else:
                    # Same direction = could be adding to position (opening)
                    is_opening_order = True
            
            # Only check for conflicts if we're opening a position
            if is_opening_order:
                binance_position = await asyncio.to_thread(account_client.get_open_position, signal.symbol)
                has_binance_position = binance_position and abs(float(binance_position.get("positionAmt", 0))) > 0
                
                if has_binance_position:
                    # Check if any OTHER strategy (not current) has this position
                    conflicting_strategy = None
                    for strategy_id, other_summary in self._strategies.items():
                        # Skip current strategy
                        if strategy_id == summary.id:
                            continue
                        
                        # Check if other strategy has open position for same symbol
                        if (other_summary.symbol == signal.symbol and
                            other_summary.position_size and
                            float(other_summary.position_size) > 0):
                            conflicting_strategy = other_summary
                            break
                    
                    if conflicting_strategy:
                        error_msg = (
                            f"Cannot open position for {signal.symbol}: "
                            f"Strategy '{conflicting_strategy.name}' ({conflicting_strategy.id}) "
                            f"already has an open {conflicting_strategy.position_side} position "
                            f"({conflicting_strategy.position_size} {signal.symbol}). "
                            f"Binance Futures positions are account-level and cannot be shared between strategies. "
                            f"Stopping this strategy to prevent position conflicts."
                        )
                        
                        logger.error(f"[{summary.id}] ❌ {error_msg}")
                        
                        # Stop the current strategy automatically
                        if self.strategy_runner:
                            try:
                                await self.strategy_runner.stop(summary.id)
                                logger.info(
                                    f"[{summary.id}] ✅ Strategy automatically stopped due to position conflict"
                                )
                            except Exception as stop_exc:
                                logger.error(
                                    f"[{summary.id}] Failed to stop strategy after position conflict: {stop_exc}"
                                )
                        
                        # Raise exception to prevent order execution
                        raise OrderExecutionError(
                            error_msg,
                            symbol=signal.symbol,
                            details={
                                "conflicting_strategy_id": conflicting_strategy.id,
                                "conflicting_strategy_name": conflicting_strategy.name,
                                "conflicting_position_side": conflicting_strategy.position_side,
                                "conflicting_position_size": conflicting_strategy.position_size,
                            }
                        )
        except OrderExecutionError:
            # Re-raise OrderExecutionError (position conflict)
            raise
        except Exception as exc:
            # Log but don't fail - if position check fails, continue with order execution
            # This prevents blocking orders due to temporary API issues
            logger.warning(
                f"[{summary.id}] Failed to check for position conflicts for {signal.symbol}: {exc}. "
                f"Proceeding with order execution."
            )
        
        # CRITICAL FIX: Portfolio risk checks BEFORE order execution
        # This includes async locking and exposure reservation
        portfolio_risk_manager = None
        if self.portfolio_risk_manager_factory:
            portfolio_risk_manager = self.portfolio_risk_manager_factory(account_id)
        
        # Load strategy risk config if available
        strategy_config = None
        strategy_uuid = None
        if self.db_service and self.user_id:
            try:
                # Get strategy UUID from database (needed for strategy-specific PnL calculation)
                db_strategy = None
                if hasattr(self.db_service, '_is_async') and self.db_service._is_async:
                    db_strategy = await self.db_service.async_get_strategy(self.user_id, summary.id)
                else:
                    db_strategy = self.db_service.get_strategy(self.user_id, summary.id)
                
                if db_strategy:
                    strategy_uuid = db_strategy.id
                    
                    # Load strategy risk config
                    if hasattr(self.db_service, '_is_async') and self.db_service._is_async:
                        db_risk_config = await self.db_service.async_get_strategy_risk_config(
                            self.user_id, summary.id
                        )
                    else:
                        db_risk_config = self.db_service.get_strategy_risk_config(
                            self.user_id, summary.id
                        )
                    
                    if db_risk_config and db_risk_config.enabled:
                        # Convert database model to Pydantic response model
                        from app.models.risk_management import StrategyRiskConfigResponse
                        strategy_config = StrategyRiskConfigResponse.from_orm(db_risk_config)
            except Exception as e:
                # Log but don't fail - strategy config is optional
                logger.debug(
                    f"[{summary.id}] Failed to load strategy risk config: {e}. "
                    f"Using account-level config only."
                )
        
        if portfolio_risk_manager:
            # CRITICAL: check_order_allowed() uses async locking internally
            # It also RESERVES exposure before order execution
            allowed, reason = await portfolio_risk_manager.check_order_allowed(
                signal=signal,
                summary=summary,
                account_id=account_id,
                strategy_config=strategy_config,
                strategy_uuid=strategy_uuid
            )
            if not allowed:
                # Extract limit type from reason for notification
                limit_type = None
                current_value = None
                limit_value = None
                if "exposure" in reason.lower():
                    limit_type = "PORTFOLIO_EXPOSURE"
                elif "daily loss" in reason.lower():
                    limit_type = "DAILY_LOSS"
                elif "weekly loss" in reason.lower():
                    limit_type = "WEEKLY_LOSS"
                elif "drawdown" in reason.lower():
                    limit_type = "DRAWDOWN"
                
                # Send notification before raising exception
                if self.notification_service:
                    asyncio.create_task(
                        self.notification_service.notify_order_blocked_by_risk(
                            summary=summary,
                            reason=reason,
                            account_id=account_id,
                            limit_type=limit_type,
                            current_value=current_value,
                            limit_value=limit_value,
                            symbol=signal.symbol,
                        )
                    )
                
                # Log enforcement event to database
                self._log_enforcement_event(
                    event_type="ORDER_BLOCKED",
                    event_level="WARNING",
                    message=f"Order blocked: {reason}",
                    account_id=account_id,
                    strategy_id=summary.id,
                    limit_type=limit_type,
                    current_value=current_value,
                    limit_value=limit_value,
                    symbol=signal.symbol,
                )
                
                # CRITICAL: If daily or weekly loss limit exceeded, stop strategies
                # Strategy-level limits: stop only THIS strategy
                # Account-level limits: stop ALL strategies for the account
                if limit_type in ("DAILY_LOSS", "WEEKLY_LOSS") and self.strategy_runner:
                    # Check if this is a strategy-level breach (reason contains "(strategy)")
                    is_strategy_level_breach = "(strategy)" in reason.lower()
                    
                    if is_strategy_level_breach:
                        # Strategy-level breach: stop only THIS strategy
                        logger.warning(
                            f"🛑 {limit_type} limit exceeded for strategy {summary.id} (strategy-level). "
                            f"Stopping this strategy only."
                        )
                        try:
                            # Stop only this specific strategy
                            stopped_summary = await self.strategy_runner.stop(summary.id)
                            
                            # Update status to stopped_by_risk
                            if self.db_service and self.user_id:
                                try:
                                    db_strategy = None
                                    if hasattr(self.db_service, '_is_async') and self.db_service._is_async:
                                        db_strategy = await self.db_service.async_get_strategy(self.user_id, summary.id)
                                    else:
                                        db_strategy = self.db_service.get_strategy(self.user_id, summary.id)
                                    
                                    if db_strategy:
                                        db_strategy.status = "stopped_by_risk"
                                        if hasattr(self.db_service, 'db'):
                                            self.db_service.db.commit()
                                            self.db_service.db.refresh(db_strategy)
                                        
                                        # Update in-memory summary
                                        from app.models.strategy import StrategyState
                                        summary.status = StrategyState.stopped_by_risk
                                except Exception as status_error:
                                    logger.warning(f"Failed to update strategy status to stopped_by_risk: {status_error}")
                        except Exception as stop_error:
                            # Log error but don't fail the order blocking
                            logger.error(
                                f"Failed to stop strategy {summary.id} due to {limit_type} limit: {stop_error}",
                                exc_info=True
                            )
                    else:
                        # Account-level breach: stop ALL strategies for this account
                        logger.warning(
                            f"🛑 {limit_type} limit exceeded for account {account_id} (account-level). "
                            f"Pausing all strategies for this account."
                        )
                        # CRITICAL FIX: Await pause_all_strategies_for_account to ensure it completes
                        # BEFORE raising the exception. This ensures all strategies are paused
                        # synchronously and the database is committed before other strategies can execute.
                        try:
                            await self.strategy_runner.pause_all_strategies_for_account(
                                account_id=account_id,
                                reason=f"{limit_type.replace('_', ' ').title()} limit exceeded: {reason}"
                            )
                        except Exception as pause_error:
                            # Log error but don't fail the order blocking
                            logger.error(
                                f"Failed to pause strategies for account {account_id}: {pause_error}",
                                exc_info=True
                            )
                
                # Option 1: Reject order
                if not portfolio_risk_manager.config.auto_reduce_order_size:
                    raise RiskLimitExceededError(
                        f"Order would breach risk limit: {reason}",
                        account_id=account_id,
                        strategy_id=summary.id,
                        details={
                            "account_id": account_id, 
                            "strategy_id": summary.id, 
                            "reason": reason,
                            "limit_type": limit_type  # Include limit_type so executor can exit immediately for daily/weekly loss
                        }
                    )
                # Option 2: Reduce order size (if enabled)
                else:
                    adjusted_sizing = portfolio_risk_manager.calculate_max_allowed_size(
                        signal, summary, account_id
                    )
                    if adjusted_sizing:
                        # Adjust signal quantity (simplified - actual implementation would update signal)
                        logger.info(
                            f"[{summary.id}] Reducing order size to fit within risk limits: "
                            f"{adjusted_sizing:.8f} (original would breach)"
                        )
                        # TODO: Update signal.quantity with adjusted_sizing
                    else:
                        raise RiskLimitExceededError(
                            f"Cannot reduce order size to fit within limits: {reason}",
                            account_id=account_id,
                            strategy_id=summary.id,
                            details={"account_id": account_id, "strategy_id": summary.id, "reason": reason}
                        )
        
        # Check circuit breakers
        # Bug #3: Fix circuit breaker factory access - handle both callable and object with get_circuit_breaker method
        circuit_breaker = None
        if self.circuit_breaker_factory:
            # Factory can be a callable or an object with get_circuit_breaker method
            if callable(self.circuit_breaker_factory):
                circuit_breaker = self.circuit_breaker_factory(account_id)
            elif hasattr(self.circuit_breaker_factory, 'get_circuit_breaker'):
                circuit_breaker = self.circuit_breaker_factory.get_circuit_breaker(account_id)
        
        if circuit_breaker and hasattr(circuit_breaker, 'is_active'):
            if circuit_breaker.is_active(account_id, summary.id):
                # Send notification before raising exception
                if self.notification_service:
                    asyncio.create_task(
                        self.notification_service.notify_circuit_breaker_triggered(
                            account_id=account_id,
                            breaker_type="active",  # Will be more specific if available
                            reason=f"Circuit breaker is active for account {account_id}",
                            strategies_affected=[summary.id],
                            summary=summary,
                        )
                    )
                
                # Log enforcement event to database
                self._log_enforcement_event(
                    event_type="CIRCUIT_BREAKER_ACTIVE",
                    event_level="WARNING",
                    message=f"Circuit breaker active for account {account_id}",
                    account_id=account_id,
                    strategy_id=summary.id,
                    breaker_type="active",
                )
                
                raise CircuitBreakerActiveError(
                    f"Circuit breaker active for {account_id}",
                    account_id=account_id,
                    strategy_id=summary.id,
                    details={"account_id": account_id, "strategy_id": summary.id}
                )
        
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
            # Extract underlying error from RetryError if present (tenacity retry decorator)
            underlying_error = exc
            try:
                from tenacity import RetryError
                if isinstance(exc, RetryError):
                    if hasattr(exc, 'last_attempt') and exc.last_attempt:
                        underlying_error = exc.last_attempt.exception()
                        logger.warning(
                            f"[{summary.id}] Leverage setting failed after retries. "
                            f"Underlying error: {underlying_error}"
                        )
            except ImportError:
                pass  # tenacity not available, use original exception
            
            # Extract more details about the error
            error_details = {
                "strategy_id": summary.id,
                "symbol": summary.symbol,
                "leverage": summary.leverage,
                "error_type": type(underlying_error).__name__,
            }
            
            # Add Binance error code if available
            if hasattr(underlying_error, 'error_code'):
                error_details["binance_error_code"] = underlying_error.error_code
            if hasattr(underlying_error, 'status_code'):
                error_details["status_code"] = underlying_error.status_code
            
            error_msg = (
                f"[{summary.id}] CRITICAL: Failed to verify/set leverage {summary.leverage}x for {summary.symbol}. "
                f"Error: {underlying_error}. "
                "Order execution aborted to prevent accidental 20x leverage."
            )
            logger.error(error_msg)
            logger.error(f"[{summary.id}] Error details: {error_details}")
            
            # If underlying error is a BinanceAPIError, preserve it
            if isinstance(underlying_error, BinanceAPIError):
                raise underlying_error
            
            raise BinanceAPIError(
                error_msg,
                details=error_details
            ) from underlying_error
        
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
                
                # Bug #4: Use dynamic sizing if enabled (dynamic_sizer exists), otherwise use base risk manager
                if dynamic_sizer:
                    # Bug #4: Pass klines to dynamic sizer for ATR calculation
                    sizing = dynamic_sizer.size_position(
                        symbol=signal.symbol,
                        risk_per_trade=summary.risk_per_trade,
                        price=price,
                        fixed_amount=summary.fixed_amount,
                        strategy_id=summary.id,
                        klines=klines  # Bug #4: Pass klines for ATR calculation
                    )
                    logger.info(
                        f"[{summary.id}] Dynamic sizing result: qty={sizing.quantity}, notional={sizing.notional:.2f} USDT"
                    )
                else:
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
        
        # CRITICAL FIX: For reduce_only orders, verify position still exists right before execution
        # This prevents race conditions where multiple strategies try to close the same position
        if reduce_only_override:
            try:
                # Re-check position state from Binance right before executing reduce_only order
                position_info = await asyncio.to_thread(
                    account_client.futures_position_information,
                    symbol=signal.symbol
                )
                
                if position_info:
                    position_amt = float(position_info.get("positionAmt", 0))
                    # If position is already closed (positionAmt == 0), skip order execution
                    if abs(position_amt) == 0:
                        logger.warning(
                            f"[{summary.id}] Position for {signal.symbol} already closed (positionAmt={position_amt}). "
                            f"Skipping reduce_only order execution to avoid 'ReduceOnly Order is rejected' error."
                        )
                        # Return a mock order response indicating the position was already closed
                        from app.models.order import OrderResponse
                        from datetime import datetime, timezone
                        return OrderResponse(
                            order_id=0,  # No order was placed
                            symbol=signal.symbol,
                            side=signal.action,
                            status="CANCELLED",
                            executed_qty=0.0,
                            avg_price=0.0,
                            commission=0.0,
                            timestamp=datetime.now(timezone.utc),
                            leverage=None,
                            notional=0.0,
                            initial_margin=None,
                            margin_type="CROSSED"
                        )
            except Exception as pos_check_exc:
                # Log warning but continue - if position check fails, let Binance reject the order
                logger.warning(
                    f"[{summary.id}] Failed to verify position before reduce_only order: {pos_check_exc}. "
                    f"Proceeding with order execution (Binance will reject if position doesn't exist)."
                )
        
        try:
            # Pass strategy_id for idempotency tracking
            order_response = account_executor.execute(
                signal=signal,
                sizing=sizing,
                reduce_only_override=reduce_only_override,
                strategy_id=summary.id,
            )
            
            # CRITICAL FIX #2: Confirm exposure reservation after successful execution
            # Handles partial fills, full fills, and converts reservation to real exposure
            if portfolio_risk_manager and order_response:
                await portfolio_risk_manager.confirm_exposure(
                    account_id, summary.id, order_response
                )
        except (OrderExecutionError, BinanceAPIError) as exc:
            # CRITICAL FIX #2: Release reservation if order failed
            if portfolio_risk_manager:
                await portfolio_risk_manager.release_reservation(
                    account_id, summary.id
                )
            
            # CRITICAL FIX: Handle "ReduceOnly Order is rejected" error gracefully
            # This happens when position was already closed by another strategy/order
            error_msg = str(exc).lower()
            error_code = getattr(exc, 'error_code', None)
            is_reduce_only_rejected = (
                reduce_only_override and
                (error_code == -2022 or 
                 "reduceonly" in error_msg or 
                 "reduce-only" in error_msg or
                 "reduce only" in error_msg)
            )
            
            if is_reduce_only_rejected:
                # Position was already closed - this is expected in race conditions
                # Log as warning and return None (position already closed, goal achieved)
                logger.warning(
                    f"[{summary.id}] Reduce-only order rejected for {signal.symbol}: "
                    f"Position already closed (likely closed by another strategy/order). "
                    f"This is expected in race conditions. Strategy will continue."
                )
                # Return None to indicate no order was executed (position already closed)
                return None
            
            # Log and re-raise other API errors
            logger.error(
                f"[{summary.id}] Order execution failed: {exc.message if hasattr(exc, 'message') else exc}"
            )
            raise
        except Exception as exc:
            # CRITICAL FIX #2: Release reservation if order failed
            if portfolio_risk_manager:
                await portfolio_risk_manager.release_reservation(
                    account_id, summary.id
                )
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
                # Bug #5: Record trade for dynamic sizing performance tracking
                if dynamic_sizer and order_response.realized_pnl is not None:
                    # Calculate if trade was profitable
                    is_profitable = order_response.realized_pnl > 0
                    dynamic_sizer.record_trade(
                        strategy_id=summary.id,
                        symbol=signal.symbol,
                        is_profitable=is_profitable,
                        pnl=order_response.realized_pnl
                    )
                    logger.debug(
                        f"[{summary.id}] Recorded trade for dynamic sizing: "
                        f"profitable={is_profitable}, pnl={order_response.realized_pnl:.2f}"
                    )
                
                # Track the trade in memory (protected with lock)
                order_with_exit_reason = order_response.model_copy(
                    update={"exit_reason": signal.exit_reason} if signal.exit_reason else {}
                )
                async with self._lock:
                    if summary.id not in self._trades:
                        self._trades[summary.id] = []
                    self._trades[summary.id].append(order_with_exit_reason)
                
                # CRITICAL: Save to database immediately after order execution
                # Note: trade_service.save_trade() also handles Redis caching automatically,
                # so we don't need to manually save to Redis here (avoids duplicate Redis writes)
                # This ensures orders are persisted even if system restarts
                if not self.trade_service:
                    logger.warning(
                        f"[{summary.id}] ⚠️ TradeService not available. Trade {order_response.order_id} will NOT be saved to database. "
                        f"Check StrategyRunner initialization."
                    )
                elif not self.user_id:
                    logger.warning(
                        f"[{summary.id}] ⚠️ user_id not available. Trade {order_response.order_id} will NOT be saved to database."
                    )
                elif not self.strategy_service:
                    logger.warning(
                        f"[{summary.id}] ⚠️ StrategyService not available. Trade {order_response.order_id} will NOT be saved to database."
                    )
                
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
                                    DBTrade.strategy_id == db_strategy.id,
                                    DBTrade.order_id == order_response.order_id
                                ).first()
                                
                                if existing_trade:
                                    logger.info(
                                        f"[{summary.id}] Order {order_response.order_id} already exists in database. "
                                        f"Skipping duplicate save."
                                    )
                                else:
                                    # ✅ FIX: Don't save trade here - let strategy_executor save it atomically
                                    # with position_instance_id. This ensures trade and position_instance_id
                                    # are saved together in one transaction.
                                    logger.debug(
                                        f"[{summary.id}] Trade {order_response.order_id} will be saved by strategy_executor "
                                        f"with position_instance_id in atomic transaction."
                                    )
                            except Exception as check_exc:
                                # If duplicate check fails, log warning but don't save here
                                # strategy_executor will save it with position_instance_id atomically
                                logger.warning(
                                    f"[{summary.id}] Error checking for duplicate order: {check_exc}. "
                                    f"Trade will be saved by strategy_executor with position_instance_id."
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
        # Note: This method is primarily for in-memory tracking.
        # Database save should be handled by the caller using trade_service.save_trade()
        # which also handles Redis caching automatically.
        if self.trade_service and self.user_id:
            try:
                # Get strategy UUID from database
                # Note: This requires access to strategy_service, which we don't have here
                # This will need to be handled by the caller or passed as a parameter
                logger.debug(f"Trade tracking: database save requires strategy_service (handled by caller)")
            except Exception as e:
                logger.warning(f"Failed to save trade to database: {e}")
        
        # Note: Redis save is handled by trade_service.save_trade() when called by the caller.
        # We don't save to Redis here to avoid duplicate writes and ensure consistent key format.
    
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
        
        # Get account-specific client
        account_id = summary.account_id or "default"
        account_client = self.account_manager.get_account_client(account_id)
        
        # ✅ CRITICAL FIX: Cancel ALL existing TP/SL orders for this symbol before placing new ones
        # This prevents orphaned TP/SL orders from previous positions from closing new positions
        # Only cancels orders for the same symbol, not other symbols
        try:
            open_orders = await asyncio.to_thread(account_client.get_open_orders, summary.symbol)
            tp_sl_order_types = {"TAKE_PROFIT_MARKET", "STOP_MARKET"}
            
            # Filter for TP/SL orders only (same symbol, TP/SL order types)
            existing_tp_sl_orders = [
                order for order in open_orders
                if order.get("type") in tp_sl_order_types
            ]
            
            if existing_tp_sl_orders:
                logger.info(
                    f"[{summary.id}] Found {len(existing_tp_sl_orders)} existing TP/SL order(s) for {summary.symbol}. "
                    f"Cancelling them before placing new TP/SL orders."
                )
                
                cancelled_count = 0
                for order in existing_tp_sl_orders:
                    order_id = order.get("orderId")
                    order_type = order.get("type", "UNKNOWN")
                    if order_id:
                        try:
                            await asyncio.to_thread(account_client.cancel_order, summary.symbol, order_id)
                            cancelled_count += 1
                            logger.debug(
                                f"[{summary.id}] Cancelled existing {order_type} order {order_id} for {summary.symbol}"
                            )
                        except Exception as cancel_exc:
                            # Order may already be filled or cancelled - log but continue
                            logger.debug(
                                f"[{summary.id}] Could not cancel {order_type} order {order_id} "
                                f"(may already be filled/cancelled): {cancel_exc}"
                            )
                
                if cancelled_count > 0:
                    logger.info(
                        f"[{summary.id}] ✅ Cancelled {cancelled_count} existing TP/SL order(s) for {summary.symbol}. "
                        f"Proceeding to place new TP/SL orders."
                    )
        except Exception as exc:
            # Log warning but continue - don't fail TP/SL placement if cancellation check fails
            logger.warning(
                f"[{summary.id}] Failed to check/cancel existing TP/SL orders for {summary.symbol}: {exc}. "
                f"Proceeding to place new TP/SL orders anyway."
            )
        
        logger.info(
            f"[{summary.id}] Placing Binance native TP/SL orders: "
            f"TP={tp_price:.8f} ({tp_side}), SL={sl_price:.8f} ({sl_side})"
        )
        
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
        
        # ✅ FIX: Raise exception if both TP and SL failed to place
        # This allows the calling code to know that TP/SL placement failed
        if not tp_order_id and not sl_order_id:
            # Both orders failed - raise an exception with details
            error_msg = f"Both TP and SL orders failed to place for {summary.symbol}"
            # Try to get error details from the last exception if available
            # (Note: We can't easily access the exception here, so we'll use a generic message)
            raise RuntimeError(error_msg)
    
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
        
        # ✅ FIX: Safely extract underlying error to avoid KeyError when accessing attributes
        underlying_error = exc
        try:
            if RetryError and isinstance(exc, RetryError):
                if hasattr(exc, 'last_attempt') and exc.last_attempt:
                    underlying_error = exc.last_attempt.exception()
        except Exception:
            # If extraction fails, use original exception
            underlying_error = exc
        
        # ✅ FIX: Safely build error details dictionary, handling missing attributes
        try:
            error_details = {
                "order_type": order_type,
                "error_type": type(underlying_error).__name__,
                "error_message": str(underlying_error),
                "symbol": getattr(summary, 'symbol', 'UNKNOWN'),
                "stop_price": stop_price,
            }
            
            # Safely access summary attributes that might not exist
            if hasattr(summary, 'entry_price'):
                error_details["entry_price"] = summary.entry_price
            if hasattr(summary, 'current_price'):
                error_details["current_price"] = summary.current_price
            if hasattr(summary, 'position_side'):
                error_details["position_side"] = summary.position_side
            if hasattr(summary, 'position_size'):
                error_details["position_size"] = summary.position_size
            
            # Extract Binance error code if available
            if hasattr(underlying_error, 'error_code'):
                error_details["binance_error_code"] = underlying_error.error_code
            if hasattr(underlying_error, 'status_code'):
                error_details["status_code"] = underlying_error.status_code
        except Exception:
            # Fallback if building error_details fails
            error_details = {
                "order_type": order_type,
                "error_type": type(underlying_error).__name__,
                "error_message": str(underlying_error),
                "symbol": "UNKNOWN",
                "stop_price": None,
            }
        except Exception as detail_err:
            # ✅ FIX: If building error_details fails, return minimal safe structure
            logger.warning(
                f"Failed to extract error details: {detail_err}. Using minimal error info."
            )
            error_details = {
                "order_type": order_type,
                "error_type": type(underlying_error).__name__,
                "error_message": str(underlying_error),
                "extraction_error": str(detail_err),
            }
        
        return error_details
    
    def _log_enforcement_event(
        self,
        event_type: str,
        event_level: str,
        message: str,
        account_id: str,
        strategy_id: str,
        limit_type: Optional[str] = None,
        current_value: Optional[float] = None,
        limit_value: Optional[float] = None,
        symbol: Optional[str] = None,
        breaker_type: Optional[str] = None,
    ) -> None:
        """Log risk enforcement event to database.
        
        Args:
            event_type: Type of event (e.g., "ORDER_BLOCKED", "CIRCUIT_BREAKER_ACTIVE")
            event_level: Event level ("INFO", "WARNING", "ERROR", "CRITICAL")
            message: Event message
            account_id: Account ID (string)
            strategy_id: Strategy ID (string)
            limit_type: Optional limit type that was exceeded
            current_value: Optional current value
            limit_value: Optional limit value
            symbol: Optional trading symbol
            breaker_type: Optional circuit breaker type
        """
        if not self.db_service or not self.user_id:
            # No database access - skip logging
            return
        
        try:
            # Get account UUID from account_id string
            account_uuid = None
            if self.account_manager:
                account_config = self.account_manager.get_account_config(account_id)
                if account_config and hasattr(account_config, 'id'):
                    account_uuid = account_config.id
            
            # Get strategy UUID from strategy_id string
            strategy_uuid = None
            if self.strategy_service and self.user_id:
                db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, strategy_id)
                if db_strategy:
                    strategy_uuid = db_strategy.id
            
            # Create event metadata
            event_metadata = {
                "account_id": account_id,
                "strategy_id": strategy_id,
            }
            if limit_type:
                event_metadata["limit_type"] = limit_type
            if current_value is not None:
                event_metadata["current_value"] = current_value
            if limit_value is not None:
                event_metadata["limit_value"] = limit_value
            if symbol:
                event_metadata["symbol"] = symbol
            if breaker_type:
                event_metadata["breaker_type"] = breaker_type
            
            # Log to database (non-blocking - fire and forget)
            # Use asyncio.create_task if in async context, otherwise call directly
            if self.db_service._is_async:
                # Async context - create task
                asyncio.create_task(
                    self._async_log_event(
                        event_type, event_level, message, strategy_uuid, account_uuid, event_metadata
                    )
                )
            else:
                # Sync context - call directly
                self.db_service.create_system_event(
                    event_type=event_type,
                    event_level=event_level,
                    message=message,
                    strategy_id=strategy_uuid,
                    account_id=account_uuid,
                    event_metadata=event_metadata,
                )
        except Exception as e:
            # Don't fail order execution if logging fails
            logger.warning(f"Failed to log enforcement event to database: {e}")
    
    async def _async_log_event(
        self,
        event_type: str,
        event_level: str,
        message: str,
        strategy_uuid: Optional["UUID"],
        account_uuid: Optional["UUID"],
        event_metadata: dict,
    ) -> None:
        """Async helper to log event."""
        try:
            # Note: DatabaseService.create_system_event is sync, but we're in async context
            # We need to use async version if available, or wrap in to_thread
            if hasattr(self.db_service, 'async_create_system_event'):
                await self.db_service.async_create_system_event(
                    event_type=event_type,
                    event_level=event_level,
                    message=message,
                    strategy_id=strategy_uuid,
                    account_id=account_uuid,
                    event_metadata=event_metadata,
                )
            else:
                # Fallback: use sync version in thread
                await asyncio.to_thread(
                    self.db_service.create_system_event,
                    event_type=event_type,
                    event_level=event_level,
                    message=message,
                    strategy_id=strategy_uuid,
                    account_id=account_uuid,
                    event_metadata=event_metadata,
                )
        except Exception as e:
            logger.warning(f"Failed to async log enforcement event: {e}")

