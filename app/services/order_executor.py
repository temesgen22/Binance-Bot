from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.models.order import OrderResponse
from app.risk.manager import PositionSizingResult
from app.strategies.base import StrategySignal


class OrderExecutor:
    def __init__(
        self,
        client: BinanceClient,
        trade_service: Optional[Any] = None,
        user_id: Optional[Any] = None,
    ) -> None:
        self.client = client
        self.trade_service = trade_service  # For database duplicate checking
        self.user_id = user_id  # For database duplicate checking
        # Track recent orders for idempotency (in-memory cache)
        # Format: {idempotency_key: (order_id, timestamp)}
        self._recent_orders: dict[str, tuple[int, float]] = {}
        # Cleanup old entries after 1 hour
        self._order_cache_ttl = 3600  # 1 hour

    def _generate_idempotency_key(
        self,
        signal: StrategySignal,
        sizing: PositionSizingResult,
        reduce_only: bool,
    ) -> str:
        """Generate a unique idempotency key for an order.
        
        The key is based on:
        - Strategy signal (symbol, action, price)
        - Position sizing (quantity)
        - Reduce-only flag
        - Timestamp (rounded to nearest second to allow retries within same second)
        
        This ensures that the same order parameters within the same second
        will generate the same key, preventing duplicate orders.
        
        Args:
            signal: Strategy signal
            sizing: Position sizing result
            reduce_only: Whether order is reduce-only
            
        Returns:
            Unique idempotency key (hex string)
        """
        # Round timestamp to nearest second to allow retries within same second
        timestamp_sec = int(time.time())
        
        # Create deterministic key from order parameters
        key_data = (
            f"{signal.symbol}:{signal.action}:{sizing.quantity:.8f}:"
            f"{reduce_only}:{timestamp_sec}"
        )
        
        # Add price if available (for limit orders or price-based idempotency)
        if signal.price:
            key_data += f":{signal.price:.8f}"
        
        # Generate hash
        idempotency_key = hashlib.sha256(key_data.encode()).hexdigest()[:32]  # 32 chars
        
        return idempotency_key

    def _check_duplicate_order(
        self,
        idempotency_key: str,
        symbol: str,
    ) -> Optional[int]:
        """Check if an order with the same idempotency key was recently executed.
        
        Args:
            idempotency_key: The idempotency key to check
            symbol: Trading symbol (for logging)
            
        Returns:
            Order ID if duplicate found, None otherwise
        """
        # Cleanup old entries
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._recent_orders.items()
            if current_time - timestamp > self._order_cache_ttl
        ]
        for key in expired_keys:
            self._recent_orders.pop(key, None)
        
        # Check for duplicate
        if idempotency_key in self._recent_orders:
            order_id, timestamp = self._recent_orders[idempotency_key]
            age_seconds = current_time - timestamp
            logger.warning(
                f"Duplicate order detected for {symbol} (idempotency_key={idempotency_key[:8]}...). "
                f"Previous order_id={order_id} was executed {age_seconds:.1f}s ago. "
                f"Skipping duplicate order execution."
            )
            return order_id
        
        return None

    def _check_duplicate_in_database(
        self,
        order_id: int,
        symbol: str,
        trade_service: Optional[Any] = None,
        user_id: Optional[Any] = None,
        strategy_id: Optional[Any] = None,
    ) -> bool:
        """Check if order already exists in database (for idempotency).
        
        Args:
            order_id: Order ID to check
            symbol: Trading symbol
            trade_service: TradeService instance (optional, for database check)
            user_id: User ID (optional, for database check)
            strategy_id: Strategy UUID (optional, for database check)
            
        Returns:
            True if duplicate found in database, False otherwise
        """
        if not trade_service or not user_id or not strategy_id:
            return False  # Can't check database without service
        
        try:
            # Check if order with this order_id already exists
            # This is a simple check - in production, you might want to check by client_order_id too
            from app.core.database import get_db_session
            with get_db_session() as db:
                from app.models.db_models import Trade
                existing_trade = db.query(Trade).filter(
                    Trade.order_id == order_id,
                    Trade.symbol == symbol
                ).first()
                
                if existing_trade:
                    logger.warning(
                        f"Order {order_id} for {symbol} already exists in database "
                        f"(trade_id={existing_trade.id}). Duplicate order detected."
                    )
                    return True
        except Exception as exc:
            logger.warning(f"Error checking database for duplicate order {order_id}: {exc}")
            # Don't fail on database check errors - continue with execution
        
        return False

    def _verify_order_state(
        self,
        order_id: int,
        symbol: str,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> Optional[OrderResponse]:
        """Verify order state after execution by polling Binance.
        
        This ensures the order was actually filled and gets accurate fill data.
        
        Args:
            order_id: Order ID to verify
            symbol: Trading symbol
            max_retries: Maximum number of polling attempts
            retry_delay: Delay between polling attempts (seconds)
            
        Returns:
            OrderResponse with verified state, or None if order not found/not filled
        """
        for attempt in range(1, max_retries + 1):
            try:
                # Wait before polling (give order time to process)
                if attempt > 1:
                    self.client._non_blocking_sleep(retry_delay * attempt)  # Exponential backoff
                
                # Get order status from Binance
                order_status = self.client.get_order_status(symbol, order_id)
                
                if not order_status:
                    logger.warning(f"Order {order_id} not found on Binance (attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        continue
                    return None
                
                status = order_status.get("status", "UNKNOWN")
                executed_qty = float(order_status.get("executedQty", 0) or 0)
                
                # If order is filled or partially filled, return verified order
                if status in ("FILLED", "PARTIALLY_FILLED") and executed_qty > 0:
                    logger.debug(
                        f"Order {order_id} verified: status={status}, executed_qty={executed_qty}"
                    )
                    # Convert to OrderResponse
                    return self.client._parse_order_response(order_status, symbol)
                
                # If order is still NEW or PENDING, continue polling
                if status in ("NEW", "PENDING_NEW"):
                    logger.debug(
                        f"Order {order_id} still {status} (attempt {attempt}/{max_retries}), "
                        f"will retry..."
                    )
                    if attempt < max_retries:
                        continue
                    # Last attempt - return order even if not filled (caller can handle)
                    return self.client._parse_order_response(order_status, symbol)
                
                # Order was cancelled or rejected
                logger.warning(
                    f"Order {order_id} has status {status}, executed_qty={executed_qty}. "
                    f"Order may not have been filled."
                )
                return self.client._parse_order_response(order_status, symbol)
                
            except Exception as exc:
                logger.warning(
                    f"Error verifying order {order_id} (attempt {attempt}/{max_retries}): {exc}"
                )
                if attempt < max_retries:
                    continue
                # Last attempt failed - return None to indicate verification failed
                return None
        
        return None

    def execute(
        self,
        *,
        signal: StrategySignal,
        sizing: PositionSizingResult,
        reduce_only_override: bool | None = None,
        strategy_id: Optional[str] = None,  # For idempotency tracking
    ) -> OrderResponse | None:
        if signal.action == "HOLD":
            # Use debug level to reduce log noise (HOLD is very repetitive)
            logger.debug(f"HOLD signal for {signal.symbol}, skipping order")
            return None

        # Binance Futures One-Way Mode semantics:
        # - BUY when flat = open long
        # - SELL when flat = open short  
        # - BUY when short = cover short (close short)
        # - SELL when long = close long
        # - reduce_only=True forces closing only (safety)
        # 
        # The strategy tracks position state internally, so signals are correct:
        # - Strategy returns "SELL" to open short (when flat) or close long
        # - Strategy returns "BUY" to open long (when flat) or cover short
        # Binance automatically handles position opening/closing based on current position
        
        side = "BUY" if signal.action == "BUY" else "SELL"
        reduce_only = signal.action == "CLOSE"
        if reduce_only_override is not None:
            reduce_only = reduce_only_override
        
        # CRITICAL: Generate idempotency key to prevent duplicate orders
        idempotency_key = self._generate_idempotency_key(signal, sizing, reduce_only)
        
        # Check for duplicate order before execution
        duplicate_order_id = self._check_duplicate_order(idempotency_key, signal.symbol)
        if duplicate_order_id:
            logger.warning(
                f"Duplicate order detected for {signal.symbol}. "
                f"Previous order_id={duplicate_order_id} was executed recently. "
                f"Skipping duplicate order execution."
            )
            # Try to get the duplicate order details from Binance
            try:
                order_status = self.client.get_order_status(signal.symbol, duplicate_order_id)
                if order_status:
                    # Return the existing order as OrderResponse
                    return self.client._parse_order_response(order_status, signal.symbol)
            except Exception as exc:
                logger.warning(f"Could not retrieve duplicate order {duplicate_order_id}: {exc}")
            # Return None to indicate duplicate was skipped
            return None
        
        logger.info(
            f"Executing order: {side} {sizing.quantity} {signal.symbol} "
            f"(reduce_only={reduce_only}, price={signal.price}, idempotency_key={idempotency_key[:8]}...)"
        )
        
        try:
            # Generate client_order_id from idempotency key for Binance
            # Binance client_order_id format: max 32 chars, alphanumeric
            client_order_id = f"IDEMP_{idempotency_key[:26]}"  # 32 chars total (IDEMP_ + 26 chars)
            
            # Place order with idempotency key as client_order_id
            # Note: Binance will reject orders with duplicate client_order_id within 24 hours
            order_response = self.client.place_order(
                symbol=signal.symbol,
                side=side,
                quantity=sizing.quantity,
                order_type="MARKET",
                reduce_only=reduce_only,
                client_order_id=client_order_id,  # Pass idempotency key as client_order_id
            )
            
            if order_response:
                # CRITICAL: Check database for duplicate order (additional safety)
                # This catches duplicates even if in-memory cache was cleared
                if self.trade_service and self.user_id and strategy_id:
                    # Note: We need strategy UUID, not strategy_id string
                    # For now, we'll check by order_id only (simpler)
                    is_duplicate = self._check_duplicate_in_database(
                        order_response.order_id,
                        signal.symbol,
                        self.trade_service,
                        self.user_id,
                        strategy_id,
                    )
                    if is_duplicate:
                        logger.error(
                            f"CRITICAL: Order {order_response.order_id} already exists in database! "
                            f"This should not happen with proper idempotency. "
                            f"Returning existing order response."
                        )
                        # Return the order response anyway (it's already in database)
                        return order_response
                
                # Track order for idempotency
                self._recent_orders[idempotency_key] = (
                    order_response.order_id,
                    time.time()
                )
                
                logger.info(
                    f"Order created successfully: {order_response.order_id} | "
                    f"Status: {order_response.status} | "
                    f"Executed Qty: {order_response.executed_qty} | "
                    f"Idempotency Key: {idempotency_key[:8]}..."
                )
                
                # CRITICAL: Verify order state after execution
                # This ensures order was actually filled and gets accurate fill data
                if order_response.status == "NEW" or order_response.executed_qty == 0:
                    logger.debug(
                        f"Order {order_response.order_id} returned as NEW or with zero execution. "
                        f"Verifying order state..."
                    )
                    verified_order = self._verify_order_state(
                        order_response.order_id,
                        signal.symbol,
                        max_retries=3,
                        retry_delay=0.5,
                    )
                    if verified_order:
                        # Update tracked order with verified data
                        self._recent_orders[idempotency_key] = (
                            verified_order.order_id,
                            time.time()
                        )
                        return verified_order
                    else:
                        logger.warning(
                            f"Order {order_response.order_id} verification failed. "
                            f"Returning original order response."
                        )
                
                return order_response
            return None
        except Exception as exc:
            logger.error(
                f"Failed to create order: {side} {sizing.quantity} {signal.symbol} | "
                f"Error: {type(exc).__name__}: {exc}"
            )
            raise

