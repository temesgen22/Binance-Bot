from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional
import sys


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


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True) -> None:
        if Client is None:
            logger.warning("python-binance not installed; BinanceClient running in stub mode")
            self._rest = None
        else:
            # python-binance uses testnet parameter
            self._rest = Client(api_key=api_key, api_secret=api_secret, testnet=testnet)
        # Cache for symbol precision info
        self._precision_cache: Dict[str, int] = {}
        # Cache for minimum notional values
        self._min_notional_cache: Dict[str, float] = {}

    def _ensure(self):
        if self._rest is None:
            raise RuntimeError(
                "python-binance package is required for live trading. Install via pip."
            )
        return self._rest

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def adjust_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        logger.info(f"Setting leverage={leverage} for {symbol}")
        rest = self._ensure()
        return rest.futures_change_leverage(symbol=symbol, leverage=leverage)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_price(self, symbol: str) -> float:
        rest = self._ensure()
        ticker = rest.futures_symbol_ticker(symbol=symbol)
        return float(ticker["price"])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> list[list[Any]]:
        """Get klines (candlestick data) from Binance futures.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            interval: Kline interval (1m, 5m, 15m, 1h, etc.)
            limit: Number of klines to retrieve (max 1500)
            
        Returns:
            List of klines where each kline is [open_time, open, high, low, close, volume, ...]
        """
        rest = self._ensure()
        klines = rest.futures_klines(symbol=symbol, interval=interval, limit=limit)
        return klines

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
        rest = self._ensure()
        account = rest.futures_account()
        assets = account.get("assets", [])
        usdt = next((bal for bal in assets if bal["asset"] == "USDT"), None)
        if not usdt:
            raise ValueError("USDT balance not found in futures account")
        return float(usdt["walletBalance"])

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
    ) -> OrderResponse:
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
        if order_type == "LIMIT":
            if price is None:
                raise ValueError("Price required for limit order")
            params["price"] = price
            params["timeInForce"] = "GTC"
        rest = self._ensure()
        try:
            # python-binance uses futures_create_order
            response = rest.futures_create_order(**params)
        except ClientError as exc:
            logger.error(f"Binance order failed: {exc}")
            raise

        return OrderResponse(
            symbol=response["symbol"],
            order_id=response["orderId"],
            status=response["status"],
            side=response["side"],
            price=float(response.get("price") or 0.0),
            avg_price=float(response.get("avgPrice")) if response.get("avgPrice") else None,
            executed_qty=float(response.get("executedQty") or 0.0),
        )

    def cancel_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        rest = self._ensure()
        logger.info(f"Cancelling open orders for {symbol}")
        return rest.futures_cancel_all_open_orders(symbol=symbol)

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

