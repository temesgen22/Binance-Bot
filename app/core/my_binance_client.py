from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional
import sys
import os
import time
import asyncio


def _prefer_global_python_binance() -> None:
    """Ensure the python-binance distribution (with client.py) is ahead on sys.path."""
    exe = Path(sys.executable)
    global_site = exe.parent / "Lib" / "site-packages"
    client_file = global_site / "binance" / "client.py"
    if client_file.exists():
        site_str = str(global_site)
        if site_str in sys.path:
            sys.path.remove(site_str)
        sys.path.insert(0, site_str)


_prefer_global_python_binance()

try:  # pragma: no cover - optional dependency
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    ClientError = BinanceAPIException
except ImportError:  # pragma: no cover - executed in CI without dependency
    ClientError = Exception  # type: ignore[assignment]
    Client = None  # type: ignore[assignment]
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models.order import OrderResponse
from app.core.exceptions import (
    BinanceAPIError,
    BinanceRateLimitError,
    BinanceNetworkError,
    BinanceAuthenticationError,
    OrderExecutionError,
    OrderNotFilledError,
)
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError
from app.core.metrics import track_api_request


def _is_test_environment() -> bool:
    """Check if we're running in a test environment."""
    return (
        "pytest" in sys.modules or
        "PYTEST_CURRENT_TEST" in os.environ or
        os.getenv("ENVIRONMENT", "").lower() == "test" or
        os.getenv("TESTING", "").lower() in ("true", "1", "yes")
    )


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True) -> None:
        if Client is None:
            logger.warning("python-binance not installed; BinanceClient running in stub mode")
            self._rest = None
        else:
            # Check if we're in a test environment
            is_test_env = _is_test_environment()
            
            if is_test_env:
                # In test environment, create Client but catch connection errors
                # The Client.__init__ calls ping() which will fail without network
                try:
                    self._rest = Client(
                        api_key=api_key, 
                        api_secret=api_secret, 
                        testnet=testnet,
                        requests_params={'timeout': 10}
                    )
                    # Skip time sync in test environment to avoid network calls
                    logger.debug("BinanceClient initialized in test mode (skipping time sync)")
                except Exception as e:
                    # If connection fails in test mode, log and continue with None
                    logger.debug(f"BinanceClient connection failed in test mode (expected): {e}")
                    self._rest = None
            else:
                # Normal initialization with network calls
                self._rest = Client(
                    api_key=api_key, 
                    api_secret=api_secret, 
                    testnet=testnet,
                    requests_params={'timeout': 10}
                )
                # Sync time with Binance server on initialization
                # This helps prevent -1021 timestamp errors
                self._sync_time_with_binance()
        # Cache for symbol precision info
        self._precision_cache: Dict[str, int] = {}
        # Cache for minimum notional values
        self._min_notional_cache: Dict[str, float] = {}
        # Time offset cache (difference between local time and Binance server time)
        self._time_offset_ms: int = 0
        
        # Circuit breaker for Binance API calls
        # Protects against cascading failures when Binance API is down
        self._circuit_breaker = CircuitBreaker(
            name="binance_api",
            component="binance",
            config=CircuitBreakerConfig(
                failure_threshold=5,  # Open after 5 failures
                success_threshold=2,  # Close after 2 successes in half-open
                timeout=60.0,  # Wait 60s before attempting half-open
                expected_exception=(BinanceAPIError, BinanceRateLimitError, BinanceNetworkError)
            )
        )
    
    def _non_blocking_sleep(self, seconds: float) -> None:
        """Sleep that minimizes event loop blocking when called from async context.
        
        Note: This is a sync method, so we can't use asyncio.sleep() directly.
        When called from async code, time.sleep() blocks the event loop.
        The proper fix is to call BinanceClient methods via asyncio.to_thread()
        from async contexts, or make these methods async.
        
        For now, we use time.sleep() but log a warning in async contexts.
        """
        try:
            # Check if we're in an async context
            asyncio.get_running_loop()
            # In async context - time.sleep() will block, but we can't avoid it in sync method
            # Log a debug message for monitoring
            logger.debug(f"Blocking sleep in async context: {seconds}s (consider using asyncio.to_thread())")
            time.sleep(seconds)
        except RuntimeError:
            # No event loop running, safe to use time.sleep()
            time.sleep(seconds)

    def _ensure(self):
        if self._rest is None:
            from app.core.exceptions import ConfigurationError
            raise ConfigurationError(
                "python-binance package is required for live trading. Install with: pip install python-binance",
                config_key="binance_client"
            )
        return self._rest
    
    def _sync_time_with_binance(self) -> None:
        """Synchronize local time with Binance server time.
        
        This helps prevent -1021 timestamp errors by calculating the offset
        between local time and Binance server time.
        
        Note: This only calculates the offset - it does NOT adjust your system clock.
        The python-binance library uses your system clock directly, so if your clock
        is out of sync, you must sync it at the OS level.
        """
        if self._rest is None:
            return
        
        # Skip time sync in test environment to avoid network calls
        if _is_test_environment():
            logger.debug("Skipping Binance time sync in test environment")
            return
        
        try:
            # Get Binance server time
            server_time = self._rest.get_server_time()
            server_timestamp_ms = server_time.get('serverTime', 0)
            
            # Get local time in milliseconds
            local_timestamp_ms = int(time.time() * 1000)
            
            # Calculate offset (positive means local time is ahead)
            self._time_offset_ms = local_timestamp_ms - server_timestamp_ms
            
            if abs(self._time_offset_ms) > 1000:  # More than 1 second difference
                logger.error(
                    f"⚠️  CRITICAL: System clock is {abs(self._time_offset_ms)}ms "
                    f"{'AHEAD' if self._time_offset_ms > 0 else 'BEHIND'} Binance server time!\n"
                    f"   This will cause API requests to fail with error -1021.\n"
                    f"   Your system clock MUST be synced for Binance API to work.\n"
                    f"   Windows: Settings > Time & Language > Date & Time > 'Set time automatically'\n"
                    f"   Or run as Admin: w32tm /resync"
                )
            elif abs(self._time_offset_ms) > 500:  # More than 500ms difference
                logger.warning(
                    f"Time offset detected: {self._time_offset_ms}ms "
                    f"{'ahead' if self._time_offset_ms > 0 else 'behind'} Binance server time. "
                    f"Consider syncing your system clock to prevent future errors."
                )
            else:
                logger.debug(f"Time synchronized with Binance: offset={self._time_offset_ms}ms")
        except Exception as exc:
            logger.warning(f"Could not sync time with Binance server: {exc}. Continuing anyway.")
            self._time_offset_ms = 0
    
    def get_time_offset(self) -> int:
        """Get the current time offset between local system and Binance server.
        
        Returns:
            Offset in milliseconds (positive = local time ahead, negative = local time behind)
        """
        return self._time_offset_ms

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_current_leverage(self, symbol: str) -> int | None:
        """Get current leverage setting for a symbol from Binance.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Current leverage as integer, or None if not found
        """
        rest = self._ensure()
        try:
            positions = rest.futures_position_information(symbol=symbol)
            if positions and len(positions) > 0:
                # Position information includes leverage
                leverage = int(float(positions[0].get("leverage", "0")))
                return leverage if leverage > 0 else None
            return None
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            # Handle timestamp synchronization error (-1021)
            if error_code == -1021:
                logger.warning(
                    f"Timestamp synchronization error for {symbol} leverage check: {exc}. "
                    f"Your system clock is ahead of Binance server time. Waiting and retrying..."
                )
                # Resync time to get current offset
                self._sync_time_with_binance()
                
                # Wait for clock to catch up (non-blocking if in async context)
                wait_time = max(1.5, (abs(self._time_offset_ms) / 1000.0) + 0.5)
                self._non_blocking_sleep(wait_time)
                
                try:
                    positions = rest.futures_position_information(symbol=symbol)
                    if positions and len(positions) > 0:
                        leverage = int(float(positions[0].get("leverage", "0")))
                        return leverage if leverage > 0 else None
                    return None
                except Exception as retry_exc:
                    logger.warning(
                        f"Could not get current leverage for {symbol} after time sync retry: {retry_exc}"
                    )
                    return None
            elif error_code == -1121:  # Invalid symbol
                logger.warning(f"Invalid symbol for leverage check: {symbol}")
            else:
                logger.warning(f"Could not get current leverage for {symbol}: {exc}")
            return None
        except Exception as exc:
            logger.warning(f"Unexpected error getting leverage for {symbol}: {exc}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def adjust_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set leverage for a symbol. Always sets even if already at target (since leverage is per-symbol).
        
        Raises:
            BinanceAPIError: If leverage adjustment fails
            InvalidLeverageError: If leverage value is invalid
        """
        from app.core.exceptions import InvalidLeverageError
        
        if not (1 <= leverage <= 50):
            raise InvalidLeverageError(
                leverage=leverage,
                reason=f"Leverage must be between 1 and 50 for {symbol}"
            )
        
        logger.info(f"Setting leverage={leverage}x for {symbol}")
        rest = self._ensure()
        try:
            return rest.futures_change_leverage(symbol=symbol, leverage=leverage)
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to set leverage {leverage}x for {symbol}: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(error_msg, retry_after=10, details={"symbol": symbol, "leverage": leverage}) from exc
            elif error_code == -4174:  # Invalid leverage
                raise InvalidLeverageError(
                    leverage=leverage,
                    reason=f"Binance rejected leverage {leverage}x for {symbol}: {exc}"
                ) from exc
            else:
                raise BinanceAPIError(error_msg, status_code=status_code, error_code=error_code, details={"symbol": symbol, "leverage": leverage}) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BinanceNetworkError(f"Network error setting leverage for {symbol}: {exc}", details={"symbol": symbol}) from exc

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_price(self, symbol: str) -> float:
        """Get current market price for a symbol with circuit breaker protection.
        
        Raises:
            BinanceAPIError: If API call fails or circuit breaker is open
            BinanceNetworkError: If network error occurs
        """
        with track_api_request("binance", "get_price"):
            try:
                return self._circuit_breaker.call_sync(
                    self._get_price_impl,
                    symbol
                )
            except CircuitBreakerOpenError as exc:
                # Convert circuit breaker error to BinanceAPIError
                raise BinanceAPIError(
                    f"Binance API circuit breaker is OPEN: {exc}",
                    details={"symbol": symbol, "operation": "get_price"}
                ) from exc
    
    def _get_price_impl(self, symbol: str) -> float:
        """Internal implementation of get_price (without circuit breaker)."""
        rest = self._ensure()
        try:
            ticker = rest.futures_symbol_ticker(symbol=symbol)
            price = float(ticker["price"])
            if price <= 0:
                raise BinanceAPIError(
                    f"Invalid price returned for {symbol}: {price}",
                    details={"symbol": symbol}
                )
            return price
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to get price for {symbol}: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(error_msg, retry_after=10, details={"symbol": symbol}) from exc
            elif error_code == -1121:  # Invalid symbol
                raise BinanceAPIError(f"Invalid symbol: {symbol}", error_code=error_code, details={"symbol": symbol}) from exc
            else:
                raise BinanceAPIError(error_msg, status_code=status_code, error_code=error_code, details={"symbol": symbol}) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BinanceNetworkError(f"Network error getting price for {symbol}: {exc}", details={"symbol": symbol}) from exc

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> list[list[Any]]:
        """Get klines (candlestick data) from Binance futures.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            interval: Kline interval (1m, 5m, 15m, 1h, etc.)
            limit: Number of klines to retrieve (max 1500)
            
        Returns:
            List of klines where each kline is [open_time, open, high, low, close, volume, ...]
            
        Raises:
            BinanceAPIError: If API call fails
            BinanceNetworkError: If network error occurs
        """
        rest = self._ensure()
        try:
            klines = rest.futures_klines(symbol=symbol, interval=interval, limit=limit)
            if not klines:
                logger.warning(f"No klines returned for {symbol} with interval {interval}")
            return klines
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to get klines for {symbol}: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(error_msg, retry_after=10, details={"symbol": symbol, "interval": interval}) from exc
            elif error_code == -1121:  # Invalid symbol
                raise BinanceAPIError(f"Invalid symbol: {symbol}", error_code=error_code, details={"symbol": symbol}) from exc
            else:
                raise BinanceAPIError(error_msg, status_code=status_code, error_code=error_code, details={"symbol": symbol, "interval": interval}) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BinanceNetworkError(f"Network error getting klines for {symbol}: {exc}", details={"symbol": symbol}) from exc

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_quantity_precision(self, symbol: str) -> int:
        """Get the quantity precision (number of decimal places) for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Number of decimal places allowed for quantity
        """
        if symbol in self._precision_cache:
            return self._precision_cache[symbol]
        
        rest = self._ensure()
        try:
            exchange_info = rest.futures_exchange_info()
            for s in exchange_info.get("symbols", []):
                if s["symbol"] == symbol:
                    # Find the stepSize filter
                    for f in s.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            step_size = float(f.get("stepSize", "1.0"))
                            # Calculate decimal places from stepSize
                            # e.g., stepSize=0.1 -> 1 decimal, stepSize=0.01 -> 2 decimals, stepSize=1 -> 0 decimals
                            if step_size >= 1.0:
                                precision = 0
                            else:
                                # Count decimal places by converting to string and counting digits after decimal
                                step_str = f"{step_size:.10f}".rstrip("0").rstrip(".")
                                if "." in step_str:
                                    precision = len(step_str.split(".")[1])
                                else:
                                    precision = 0
                            self._precision_cache[symbol] = precision
                            logger.debug(f"Quantity precision for {symbol}: {precision} (stepSize={step_size})")
                            return precision
            # Default to 3 decimals if not found
            logger.warning(f"Could not find precision for {symbol}, defaulting to 3 decimals")
            self._precision_cache[symbol] = 3
            return 3
        except Exception as exc:
            logger.warning(f"Error fetching precision for {symbol}: {exc}, defaulting to 3 decimals")
            self._precision_cache[symbol] = 3
            return 3

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to the correct precision for the symbol.
        
        Args:
            symbol: Trading symbol
            quantity: Raw quantity value
            
        Returns:
            Quantity rounded to symbol's precision
        """
        precision = self.get_quantity_precision(symbol)
        return round(quantity, precision)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_min_notional(self, symbol: str) -> float:
        """Get the minimum notional value (order size in USDT) for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Minimum notional value in USDT (default: 5.0 if not found)
        """
        if symbol in self._min_notional_cache:
            return self._min_notional_cache[symbol]
        
        rest = self._ensure()
        try:
            exchange_info = rest.futures_exchange_info()
            for s in exchange_info.get("symbols", []):
                if s["symbol"] == symbol:
                    # Find the MIN_NOTIONAL filter
                    for f in s.get("filters", []):
                        if f.get("filterType") == "MIN_NOTIONAL":
                            min_notional = float(f.get("notional", "5.0"))
                            self._min_notional_cache[symbol] = min_notional
                            logger.debug(f"Min notional for {symbol}: {min_notional} USDT")
                            return min_notional
            # Default to 5 USDT if not found (Binance standard minimum)
            logger.warning(f"Could not find min notional for {symbol}, defaulting to 5.0 USDT")
            self._min_notional_cache[symbol] = 5.0
            return 5.0
        except Exception as exc:
            logger.warning(f"Error fetching min notional for {symbol}: {exc}, defaulting to 5.0 USDT")
            self._min_notional_cache[symbol] = 5.0
            return 5.0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def futures_account_balance(self) -> float:
        """Get USDT balance from futures account.
        
        Raises:
            BinanceAPIError: If API call fails
            ValueError: If USDT balance not found
        """
        rest = self._ensure()
        try:
            account = rest.futures_account()
            assets = account.get("assets", [])
            usdt = next((bal for bal in assets if bal["asset"] == "USDT"), None)
            if not usdt:
                raise ValueError("USDT balance not found in futures account")
            balance = float(usdt["walletBalance"])
            if balance < 0:
                logger.warning(f"Negative USDT balance detected: {balance}")
            return balance
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to get account balance: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(error_msg, retry_after=10) from exc
            elif status_code == 401:
                raise BinanceAuthenticationError(error_msg, error_code=error_code) from exc
            else:
                raise BinanceAPIError(error_msg, status_code=status_code, error_code=error_code) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BinanceNetworkError(f"Network error getting account balance: {exc}") from exc
        except ValueError:
            # Re-raise ValueError as-is (USDT not found)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_order_status(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Get current status of an order from Binance.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID from Binance
            
        Returns:
            Order status dict with filled price, quantity, etc.
        """
        rest = self._ensure()
        return rest.futures_get_order(symbol=symbol, orderId=order_id)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def place_order(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        quantity: float,
        order_type: Literal["MARKET", "LIMIT"] = "MARKET",
        reduce_only: bool = False,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> OrderResponse:
        """Place an order with circuit breaker protection."""
        with track_api_request("binance", "place_order"):
            try:
                return self._circuit_breaker.call_sync(
                    self._place_order_impl,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    order_type=order_type,
                    reduce_only=reduce_only,
                    price=price,
                    client_order_id=client_order_id
                )
            except CircuitBreakerOpenError as exc:
                # Convert circuit breaker error to BinanceAPIError
                raise BinanceAPIError(
                    f"Binance API circuit breaker is OPEN: {exc}",
                    details={"symbol": symbol, "operation": "place_order", "side": side}
                ) from exc
    
    def _place_order_impl(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        quantity: float,
        order_type: Literal["MARKET", "LIMIT"] = "MARKET",
        reduce_only: bool = False,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> OrderResponse:
        """Internal implementation of place_order (without circuit breaker)."""
        # Round quantity to correct precision for the symbol
        rounded_quantity = self.round_quantity(symbol, quantity)
        logger.info(
            f"Submitting order {order_type} {side} {symbol} qty={rounded_quantity} (original={quantity}) reduce_only={reduce_only}"
        )
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": rounded_quantity,
            "reduceOnly": reduce_only,  # python-binance expects boolean
        }
        # Add client_order_id for idempotency (Binance will reject duplicates within 24 hours)
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        if order_type == "LIMIT":
            if price is None:
                raise OrderExecutionError(
                    "Price is required for LIMIT orders",
                    symbol=symbol,
                    details={"order_type": order_type, "side": side}
                )
            params["price"] = price
            params["timeInForce"] = "GTC"
        rest = self._ensure()
        try:
            # python-binance uses futures_create_order
            response = rest.futures_create_order(**params)
            logger.debug(f"Binance order response keys: {list(response.keys())}, status: {response.get('status')}")
        except ClientError as exc:
            error_msg = str(exc)
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            
            # Handle specific Binance error codes
            if status_code == 429:
                retry_after = getattr(exc, 'retry_after', None) or 10
                logger.error(f"Binance rate limit exceeded: {error_msg}. Retry after {retry_after}s")
                raise BinanceRateLimitError(
                    f"Binance API rate limit exceeded: {error_msg}",
                    retry_after=retry_after,
                    details={"symbol": symbol, "side": side, "error_code": error_code}
                ) from exc
            elif status_code == 401 or error_code == -2015:
                logger.error(f"Binance authentication failed: {error_msg}")
                raise BinanceAuthenticationError(
                    f"Binance API authentication failed: {error_msg}",
                    error_code=error_code,
                    details={"symbol": symbol, "error_code": error_code}
                ) from exc
            elif error_code == -1013:  # Invalid quantity
                logger.error(f"Binance invalid quantity: {error_msg}")
                raise OrderExecutionError(
                    f"Invalid order quantity: {error_msg}. Check order size and symbol precision.",
                    symbol=symbol,
                    details={"error_code": error_code, "quantity": rounded_quantity}
                ) from exc
            elif error_code == -1121:  # Invalid symbol
                logger.error(f"Binance invalid symbol: {error_msg}")
                raise OrderExecutionError(
                    f"Invalid trading symbol: {symbol}. {error_msg}",
                    symbol=symbol,
                    details={"error_code": error_code}
                ) from exc
            elif error_code == -4164:  # Reduce-only order rejected
                logger.error(f"Binance reduce-only order rejected: {error_msg}")
                raise OrderExecutionError(
                    f"Reduce-only order rejected: {error_msg}. No position to reduce.",
                    symbol=symbol,
                    details={"error_code": error_code, "reduce_only": reduce_only}
                ) from exc
            else:
                # Generic API error
                logger.error(f"Binance API error: {error_msg} (code: {error_code}, status: {status_code})")
                raise BinanceAPIError(
                    f"Binance API error: {error_msg}",
                    status_code=status_code,
                    error_code=error_code,
                    details={"symbol": symbol, "side": side, "error_code": error_code}
                ) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.error(f"Network error connecting to Binance: {exc}")
            raise BinanceNetworkError(
                f"Network error: {exc}",
                details={"symbol": symbol, "side": side}
            ) from exc
        except Exception as exc:
            logger.exception(f"Unexpected error placing order: {exc}")
            raise OrderExecutionError(
                f"Unexpected error placing order: {exc}",
                symbol=symbol,
                details={"error": str(exc)}
            ) from exc

        # Parse response - handle different field name variations
        # Binance may return price/avgPrice/executedQty in different formats
        price_str = response.get("price", "0") or response.get("price", "0") or "0"
        avg_price_str = response.get("avgPrice") or response.get("avgPrice") or None
        executed_qty_str = response.get("executedQty", "0") or response.get("executedQty", "0") or "0"
        status = response.get("status", "UNKNOWN")
        
        # Convert to float, handling various formats
        try:
            price = float(price_str) if price_str and str(price_str).strip() and str(price_str) != "0" else 0.0
        except (ValueError, TypeError):
            price = 0.0
        
        try:
            # avgPrice can be "0", "", None, or a valid number
            if avg_price_str and str(avg_price_str).strip() and str(avg_price_str).strip() != "0":
                avg_price = float(avg_price_str)
            else:
                avg_price = None
        except (ValueError, TypeError):
            avg_price = None
        
        try:
            executed_qty = float(executed_qty_str) if executed_qty_str and str(executed_qty_str).strip() else 0.0
        except (ValueError, TypeError):
            executed_qty = 0.0
        
        # For market orders that return immediately with "NEW" status but are actually filled,
        # query the order status to get actual fill data
        order_id = response.get("orderId")
        final_response = response  # Use final_response for parsing Binance data
        
        if status == "NEW" and order_type == "MARKET" and executed_qty == 0.0:
            logger.debug(f"Order {order_id} returned as NEW, querying status to get fill data...")
            try:
                # Wait a moment and query order status (non-blocking if in async context)
                self._non_blocking_sleep(0.1)  # Brief delay for order to process
                status_response = self.get_order_status(symbol, order_id)
                logger.debug(f"Order status query response: {status_response}")
                
                # Update final_response with order status data (has more complete info)
                final_response = status_response
                
                # Update with actual fill data
                status = status_response.get("status", status)
                if status_response.get("avgPrice"):
                    avg_price_str = status_response.get("avgPrice")
                    try:
                        avg_price = float(avg_price_str) if avg_price_str and str(avg_price_str).strip() != "0" else None
                    except (ValueError, TypeError):
                        pass
                
                if status_response.get("executedQty"):
                    executed_qty_str = status_response.get("executedQty")
                    try:
                        executed_qty = float(executed_qty_str) if executed_qty_str else 0.0
                    except (ValueError, TypeError):
                        pass
            except Exception as exc:
                logger.warning(f"Failed to query order status for {order_id}: {exc}")
        
        # Parse actual Binance trade data from response
        # Timestamp parsing (Binance returns milliseconds)
        timestamp = None
        update_time = None
        try:
            if final_response.get("time"):
                timestamp_ms = int(final_response.get("time", 0))
                if timestamp_ms > 0:
                    from datetime import datetime, timezone
                    timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        except (ValueError, TypeError) as exc:
            logger.debug(f"Could not parse order time: {exc}")
        
        try:
            if final_response.get("updateTime"):
                update_time_ms = int(final_response.get("updateTime", 0))
                if update_time_ms > 0:
                    from datetime import datetime, timezone
                    update_time = datetime.fromtimestamp(update_time_ms / 1000.0, tz=timezone.utc)
        except (ValueError, TypeError) as exc:
            logger.debug(f"Could not parse order updateTime: {exc}")
        
        # Commission parsing (actual fee from Binance)
        commission = None
        commission_asset = None
        try:
            commission_str = final_response.get("commission") or final_response.get("commissionFee")
            if commission_str:
                commission = float(commission_str)
            commission_asset = final_response.get("commissionAsset")
        except (ValueError, TypeError) as exc:
            logger.debug(f"Could not parse commission: {exc}")
        
        # Position side (for one-way mode, might not be present)
        position_side = None
        pos_side = final_response.get("positionSide")
        if pos_side and pos_side in ["LONG", "SHORT"]:
            position_side = pos_side
        
        # Leverage - try to get from position info (not always in order response)
        leverage = None
        try:
            # Try to get leverage from current position using existing method
            leverage = self.get_current_leverage(symbol)
        except Exception as exc:
            logger.debug(f"Could not get leverage from position info: {exc}")
        
        # Order type and time in force
        order_type_from_response = final_response.get("type")
        time_in_force = final_response.get("timeInForce")
        
        # Additional Binance trade parameters
        notional_value = None
        cummulative_quote_qty = None
        try:
            # Notional value: quantity * avg_price (if available)
            if avg_price and executed_qty > 0:
                notional_value = avg_price * executed_qty
            
            # Cummulative quote quantity (total cost in quote currency)
            cumm_quote_str = final_response.get("cummulativeQuoteQty") or final_response.get("cummQuoteQty")
            if cumm_quote_str:
                cummulative_quote_qty = float(cumm_quote_str)
            elif notional_value:
                # Fallback to calculated notional if cummulative not available
                cummulative_quote_qty = notional_value
        except (ValueError, TypeError) as exc:
            logger.debug(f"Could not parse notional/cummulative quote qty: {exc}")
        
        # Client order ID
        client_order_id = final_response.get("clientOrderId") or final_response.get("newClientOrderId")
        
        # Working type (for conditional orders)
        working_type = final_response.get("workingType")
        
        # Stop price (for stop-loss/take-profit orders)
        stop_price = None
        try:
            stop_price_str = final_response.get("stopPrice") or final_response.get("activatePrice")
            if stop_price_str:
                stop_price = float(stop_price_str)
        except (ValueError, TypeError):
            pass
        
        # Initial margin and margin type - get from position information
        initial_margin = None
        margin_type = None
        try:
            # Get position info to extract initial margin and margin type
            rest_client = self._ensure()
            positions = rest_client.futures_position_information(symbol=symbol)
            if positions and len(positions) > 0:
                # Find the position with non-zero amount or use first position for margin type
                for pos in positions:
                    position_amt = float(pos.get("positionAmt", 0))
                    if abs(position_amt) > 0 or pos.get("marginType"):
                        # Initial margin (initial margin required)
                        initial_margin_str = pos.get("initialMargin")
                        if initial_margin_str:
                            initial_margin = float(initial_margin_str)
                        
                        # Margin type (ISOLATED/CROSSED)
                        pos_margin_type = pos.get("marginType")
                        if pos_margin_type in ["ISOLATED", "CROSSED"]:
                            margin_type = pos_margin_type
                        
                        # If we found a position with margin info, we can break
                        if initial_margin is not None or margin_type:
                            break
                
                # If no position found, try to get margin type from first position
                if not margin_type and positions:
                    pos_margin_type = positions[0].get("marginType")
                    if pos_margin_type in ["ISOLATED", "CROSSED"]:
                        margin_type = pos_margin_type
        except Exception as exc:
            logger.debug(f"Could not get initial margin/margin type from position info: {exc}")
        
        # Realized PnL - this is typically available from user trades endpoint, not order response
        # We'll leave it None for now as it requires querying a different endpoint
        realized_pnl = None
        
        # Log warning if order still doesn't have execution data
        if status != "FILLED" and executed_qty == 0.0:
            logger.warning(
                f"Order {order_id} status is '{status}', executed_qty={executed_qty}, "
                f"avg_price={avg_price}. Order may not be filled yet or response format unexpected."
            )
        
        order_response = OrderResponse(
            symbol=response["symbol"],
            order_id=order_id,
            status=status,
            side=response["side"],
            price=price,
            avg_price=avg_price,
            executed_qty=executed_qty,
            timestamp=timestamp,
            commission=commission,
            commission_asset=commission_asset,
            leverage=leverage,
            position_side=position_side,
            update_time=update_time,
            time_in_force=time_in_force,
            order_type=order_type_from_response,
            notional_value=notional_value,
            cummulative_quote_qty=cummulative_quote_qty,
            initial_margin=initial_margin,
            margin_type=margin_type,
            client_order_id=client_order_id,
            working_type=working_type,
            realized_pnl=realized_pnl,
            stop_price=stop_price,
        )
        
        logger.info(
            f"Order response: {order_response.side} {order_response.symbol} "
            f"order_id={order_response.order_id} status={order_response.status} "
            f"executed_qty={order_response.executed_qty} avg_price={order_response.avg_price} "
            f"commission={commission} {commission_asset} timestamp={timestamp} leverage={leverage}x "
            f"notional={notional_value} initial_margin={initial_margin} margin_type={margin_type}"
        )
        
        return order_response

    def _parse_order_response(self, response: Dict[str, Any], symbol: str) -> OrderResponse:
        """Parse Binance order response into OrderResponse model.
        
        This is a helper method for converting Binance API responses to OrderResponse.
        Used for order verification and idempotency checks.
        
        Args:
            response: Binance API response dictionary
            symbol: Trading symbol
            
        Returns:
            OrderResponse model instance
        """
        # Parse response fields (similar to place_order method)
        price_str = response.get("price", "0") or response.get("price", "0") or "0"
        avg_price_str = response.get("avgPrice") or response.get("avgPrice") or None
        executed_qty_str = response.get("executedQty", "0") or response.get("executedQty", "0") or "0"
        status = response.get("status", "UNKNOWN")
        order_id = response.get("orderId")
        
        # Convert to float
        try:
            price = float(price_str) if price_str and str(price_str).strip() and str(price_str) != "0" else 0.0
        except (ValueError, TypeError):
            price = 0.0
        
        try:
            if avg_price_str and str(avg_price_str).strip() and str(avg_price_str).strip() != "0":
                avg_price = float(avg_price_str)
            else:
                avg_price = None
        except (ValueError, TypeError):
            avg_price = None
        
        try:
            executed_qty = float(executed_qty_str) if executed_qty_str and str(executed_qty_str).strip() else 0.0
        except (ValueError, TypeError):
            executed_qty = 0.0
        
        # Parse timestamps
        timestamp = None
        update_time = None
        try:
            if response.get("time"):
                timestamp_ms = int(response.get("time", 0))
                if timestamp_ms > 0:
                    from datetime import datetime, timezone
                    timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        except (ValueError, TypeError):
            pass
        
        try:
            if response.get("updateTime"):
                update_time_ms = int(response.get("updateTime", 0))
                if update_time_ms > 0:
                    from datetime import datetime, timezone
                    update_time = datetime.fromtimestamp(update_time_ms / 1000.0, tz=timezone.utc)
        except (ValueError, TypeError):
            pass
        
        # Parse commission
        commission = None
        commission_asset = None
        try:
            commission_str = response.get("commission") or response.get("commissionFee")
            if commission_str:
                commission = float(commission_str)
            commission_asset = response.get("commissionAsset")
        except (ValueError, TypeError):
            pass
        
        # Position side
        position_side = None
        pos_side = response.get("positionSide")
        if pos_side and pos_side in ["LONG", "SHORT"]:
            position_side = pos_side
        
        # Leverage
        leverage = None
        try:
            leverage = self.get_current_leverage(symbol)
        except Exception:
            pass
        
        # Additional fields
        order_type_from_response = response.get("type")
        time_in_force = response.get("timeInForce")
        client_order_id = response.get("clientOrderId") or response.get("newClientOrderId")
        working_type = response.get("workingType")
        
        # Stop price
        stop_price = None
        try:
            stop_price_str = response.get("stopPrice") or response.get("activatePrice")
            if stop_price_str:
                stop_price = float(stop_price_str)
        except (ValueError, TypeError):
            pass
        
        # Notional value
        notional_value = None
        cummulative_quote_qty = None
        try:
            if avg_price and executed_qty > 0:
                notional_value = avg_price * executed_qty
            cumm_quote_str = response.get("cummulativeQuoteQty") or response.get("cummQuoteQty")
            if cumm_quote_str:
                cummulative_quote_qty = float(cumm_quote_str)
            elif notional_value:
                cummulative_quote_qty = notional_value
        except (ValueError, TypeError):
            pass
        
        # Initial margin and margin type
        initial_margin = None
        margin_type = None
        try:
            rest_client = self._ensure()
            positions = rest_client.futures_position_information(symbol=symbol)
            if positions and len(positions) > 0:
                for pos in positions:
                    position_amt = float(pos.get("positionAmt", 0))
                    if abs(position_amt) > 0 or pos.get("marginType"):
                        initial_margin_str = pos.get("initialMargin")
                        if initial_margin_str:
                            initial_margin = float(initial_margin_str)
                        pos_margin_type = pos.get("marginType")
                        if pos_margin_type in ["ISOLATED", "CROSSED"]:
                            margin_type = pos_margin_type
                        if initial_margin is not None or margin_type:
                            break
                if not margin_type and positions:
                    pos_margin_type = positions[0].get("marginType")
                    if pos_margin_type in ["ISOLATED", "CROSSED"]:
                        margin_type = pos_margin_type
        except Exception:
            pass
        
        realized_pnl = None
        
        return OrderResponse(
            symbol=symbol,
            order_id=order_id,
            status=status,
            side=response["side"],
            price=price,
            avg_price=avg_price,
            executed_qty=executed_qty,
            timestamp=timestamp,
            commission=commission,
            commission_asset=commission_asset,
            leverage=leverage,
            position_side=position_side,
            update_time=update_time,
            time_in_force=time_in_force,
            order_type=order_type_from_response,
            notional_value=notional_value,
            cummulative_quote_qty=cummulative_quote_qty,
            initial_margin=initial_margin,
            margin_type=margin_type,
            client_order_id=client_order_id,
            working_type=working_type,
            realized_pnl=realized_pnl,
            stop_price=stop_price,
        )

    def cancel_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        rest = self._ensure()
        logger.info(f"Cancelling open orders for {symbol}")
        return rest.futures_cancel_all_open_orders(symbol=symbol)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def place_stop_loss_order(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        quantity: float,
        stop_price: float,
        close_position: bool = False,
    ) -> Dict[str, Any]:
        """Place a STOP_MARKET order (stop-loss) on Binance.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            side: "BUY" to close short, "SELL" to close long
            quantity: Order quantity (ignored if close_position=True)
            stop_price: Trigger price for stop-loss
            close_position: If True, closes entire position (quantity ignored)
            
        Returns:
            Order response dict with orderId, etc.
        """
        rest = self._ensure()
        
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "stopPrice": stop_price,
            "reduceOnly": True,  # Stop-loss always reduces position
        }
        
        if close_position:
            params["closePosition"] = True
        else:
            rounded_quantity = self.round_quantity(symbol, quantity)
            params["quantity"] = rounded_quantity
        
        logger.info(
            f"Placing STOP_MARKET order: {side} {symbol} stop_price={stop_price} "
            f"quantity={params.get('quantity', 'CLOSE_POSITION')}"
        )
        
        try:
            response = rest.futures_create_order(**params)
            logger.info(f"STOP_MARKET order placed: orderId={response.get('orderId')}")
            return response
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to place STOP_MARKET order for {symbol}: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(
                    error_msg, retry_after=10,
                    details={"symbol": symbol, "order_type": "STOP_MARKET"}
                ) from exc
            else:
                raise BinanceAPIError(
                    error_msg, status_code=status_code, error_code=error_code,
                    details={"symbol": symbol, "order_type": "STOP_MARKET"}
                ) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BinanceNetworkError(
                f"Network error placing STOP_MARKET order: {exc}",
                details={"symbol": symbol}
            ) from exc
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def place_take_profit_order(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        quantity: float,
        stop_price: float,
        close_position: bool = False,
    ) -> Dict[str, Any]:
        """Place a TAKE_PROFIT_MARKET order on Binance.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            side: "BUY" to close short, "SELL" to close long
            quantity: Order quantity (ignored if close_position=True)
            stop_price: Trigger price for take-profit
            close_position: If True, closes entire position (quantity ignored)
            
        Returns:
            Order response dict with orderId, etc.
        """
        rest = self._ensure()
        
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": stop_price,
            "reduceOnly": True,  # Take-profit always reduces position
        }
        
        if close_position:
            params["closePosition"] = True
        else:
            rounded_quantity = self.round_quantity(symbol, quantity)
            params["quantity"] = rounded_quantity
        
        logger.info(
            f"Placing TAKE_PROFIT_MARKET order: {side} {symbol} stop_price={stop_price} "
            f"quantity={params.get('quantity', 'CLOSE_POSITION')}"
        )
        
        try:
            response = rest.futures_create_order(**params)
            logger.info(f"TAKE_PROFIT_MARKET order placed: orderId={response.get('orderId')}")
            return response
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to place TAKE_PROFIT_MARKET order for {symbol}: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(
                    error_msg, retry_after=10,
                    details={"symbol": symbol, "order_type": "TAKE_PROFIT_MARKET"}
                ) from exc
            else:
                raise BinanceAPIError(
                    error_msg, status_code=status_code, error_code=error_code,
                    details={"symbol": symbol, "order_type": "TAKE_PROFIT_MARKET"}
                ) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BinanceNetworkError(
                f"Network error placing TAKE_PROFIT_MARKET order: {exc}",
                details={"symbol": symbol}
            ) from exc
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel a specific order by order ID.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel
            
        Returns:
            Cancellation response dict
        """
        rest = self._ensure()
        logger.info(f"Cancelling order {order_id} for {symbol}")
        try:
            return rest.futures_cancel_order(symbol=symbol, orderId=order_id)
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to cancel order {order_id} for {symbol}: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(
                    error_msg, retry_after=10,
                    details={"symbol": symbol, "order_id": order_id}
                ) from exc
            else:
                raise BinanceAPIError(
                    error_msg, status_code=status_code, error_code=error_code,
                    details={"symbol": symbol, "order_id": order_id}
                ) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BinanceNetworkError(
                f"Network error cancelling order: {exc}",
                details={"symbol": symbol, "order_id": order_id}
            ) from exc
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_open_orders(self, symbol: str) -> list[Dict[str, Any]]:
        """Get all open orders for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of open order dicts
        """
        rest = self._ensure()
        try:
            return rest.futures_get_open_orders(symbol=symbol)
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to get open orders for {symbol}: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(
                    error_msg, retry_after=10, details={"symbol": symbol}
                ) from exc
            else:
                raise BinanceAPIError(
                    error_msg, status_code=status_code, error_code=error_code,
                    details={"symbol": symbol}
                ) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise BinanceNetworkError(
                f"Network error getting open orders: {exc}",
                details={"symbol": symbol}
            ) from exc

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_funding_fees(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get funding fee income history from Binance.
        
        Args:
            symbol: Trading symbol (optional, None for all symbols)
            start_time: Start timestamp in milliseconds (optional)
            end_time: End timestamp in milliseconds (optional)
            limit: Maximum number of records (default 1000, max 1000)
            
        Returns:
            List of funding fee income records with:
            - symbol: Trading symbol
            - incomeType: "FUNDING_FEE"
            - income: Funding fee amount (negative for paid, positive for received)
            - asset: Asset (usually USDT)
            - time: Timestamp in milliseconds
        """
        rest = self._ensure()
        if rest is None:
            return []
        
        try:
            params: Dict[str, Any] = {
                "incomeType": "FUNDING_FEE",
                "limit": min(limit, 1000),  # Binance max is 1000
            }
            if symbol:
                params["symbol"] = symbol
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time
            
            income_history = rest.futures_income_history(**params)
            return income_history if isinstance(income_history, list) else []
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            status_code = getattr(exc, 'status_code', None)
            error_msg = f"Failed to get funding fees: {exc}"
            if status_code == 429:
                raise BinanceRateLimitError(
                    error_msg, retry_after=10,
                    details={"symbol": symbol, "start_time": start_time, "end_time": end_time}
                ) from exc
            else:
                # Log warning but don't fail - funding fees are optional
                logger.warning(f"Could not fetch funding fees: {exc}")
                return []
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning(f"Network error getting funding fees: {exc}")
            return []
        except Exception as exc:
            logger.warning(f"Unexpected error getting funding fees: {exc}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_open_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get open position for a specific symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Position dict with positionAmt, entryPrice, etc., or None if no position
        """
        rest = self._ensure()
        try:
            positions = rest.futures_position_information(symbol=symbol)
            # Find position with non-zero positionAmt
            for pos in positions:
                position_amt = float(pos.get("positionAmt", 0))
                if abs(position_amt) > 0:
                    return {
                        "symbol": pos.get("symbol"),
                        "positionAmt": position_amt,
                        "entryPrice": float(pos.get("entryPrice", 0)),
                        "markPrice": float(pos.get("markPrice", 0)),
                        "unRealizedProfit": float(pos.get("unRealizedProfit", 0)),
                        "leverage": int(pos.get("leverage", 1)),
                    }
            return None
        except ClientError as exc:
            error_code = getattr(exc, 'code', None)
            # Handle API key format invalid error (-2014)
            if error_code == -2014:
                api_key_preview = self._rest.api_key[:10] + "..." if self._rest and self._rest.api_key else "None"
                logger.error(
                    f"❌ API key format invalid (code -2014) for {symbol}. "
                    f"API key preview: {api_key_preview}. "
                    f"This usually means:\n"
                    f"  1. The API key is invalid or corrupted\n"
                    f"  2. The account is using 'demo' placeholder keys\n"
                    f"  3. The API keys were not properly loaded from the database\n"
                    f"  Please check your account configuration and ensure valid Binance API keys are set."
                )
                return None
            # Handle timestamp synchronization error (-1021)
            elif error_code == -1021:
                logger.warning(
                    f"Timestamp synchronization error for {symbol}: {exc}. "
                    f"Your system clock is ahead of Binance server time. "
                    f"Attempting to wait and retry..."
                )
                # Resync time to get current offset
                self._sync_time_with_binance()
                
                # If local time is ahead, wait for it to catch up
                # Wait slightly longer than the offset to ensure we're within tolerance
                wait_time = max(1.5, (abs(self._time_offset_ms) / 1000.0) + 0.5)
                logger.info(f"Waiting {wait_time:.1f} seconds for clock synchronization...")
                self._non_blocking_sleep(wait_time)
                
                try:
                    # Retry after waiting
                    positions = rest.futures_position_information(symbol=symbol)
                    for pos in positions:
                        position_amt = float(pos.get("positionAmt", 0))
                        if abs(position_amt) > 0:
                            logger.info(f"Successfully retrieved position for {symbol} after time sync wait")
                            return {
                                "symbol": pos.get("symbol"),
                                "positionAmt": position_amt,
                                "entryPrice": float(pos.get("entryPrice", 0)),
                                "markPrice": float(pos.get("markPrice", 0)),
                                "unRealizedProfit": float(pos.get("unRealizedProfit", 0)),
                                "leverage": int(pos.get("leverage", 1)),
                            }
                    return None
                except Exception as retry_exc:
                    error_code_retry = getattr(retry_exc, 'code', None)
                    if error_code_retry == -1021:
                        logger.error(
                            f"Timestamp error persists for {symbol} after wait. "
                            f"Your system clock is {self._time_offset_ms}ms ahead of Binance. "
                            f"Please sync your system clock:\n"
                            f"  Windows: Settings > Time & Language > Date & Time > 'Set time automatically'\n"
                            f"  Or run: w32tm /resync (as Administrator)"
                        )
                    else:
                        logger.error(
                            f"Error getting position for {symbol} after time sync retry: {retry_exc}"
                        )
                    return None
            else:
                logger.error(f"Error getting position for {symbol}: {exc}")
                return None
        except Exception as exc:
            logger.error(f"Error getting position for {symbol}: {exc}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def close_position(self, symbol: str) -> Optional[OrderResponse]:
        """Close an open position for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            OrderResponse if position was closed, None if no position exists
        """
        position = self.get_open_position(symbol)
        if not position:
            logger.info(f"No open position found for {symbol}")
            return None
        
        position_amt = position["positionAmt"]
        # Determine side: if positionAmt is positive, we need to SELL to close
        # if negative, we need to BUY to close
        side = "SELL" if position_amt > 0 else "BUY"
        quantity = abs(position_amt)
        
        logger.info(f"Closing position for {symbol}: {position_amt} @ {position['entryPrice']}")
        
        try:
            return self.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type="MARKET",
                reduce_only=True,  # Important: only reduce position, don't open new one
            )
        except Exception as exc:
            logger.error(f"Error closing position for {symbol}: {exc}")
            raise

