"""Paper Trading Binance Client - Simulates order execution with real market data.

This client provides a drop-in replacement for BinanceClient that:
- Uses real market data from Binance public API (no authentication required)
- Simulates order execution (no trading API calls)
- Tracks virtual positions and balance in memory
- Persists balance to Account.paper_balance in database
"""
from __future__ import annotations

import time
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Literal, Callable
from decimal import Decimal

import requests
from loguru import logger

from app.models.order import OrderResponse
from app.core.exceptions import (
    BinanceAPIError,
    BinanceRateLimitError,
    BinanceNetworkError,
)


# Constants for paper trading simulation (same as backtesting)
SPREAD_OFFSET = 0.0001  # 0.01% spread (bid/ask difference)
AVERAGE_FEE_RATE = 0.0004  # 0.04% average fee (maker/taker average)


@dataclass
class VirtualPosition:
    """Represents a virtual position in paper trading."""
    symbol: str
    side: str  # LONG or SHORT
    size: float
    entry_price: float
    leverage: int
    unrealized_pnl: float = 0.0
    position_instance_id: Optional[str] = None


@dataclass
class VirtualOrder:
    """Represents a virtual order (TP/SL) in paper trading."""
    order_id: int
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    status: str  # NEW, FILLED, CANCELLED
    reduce_only: bool = False
    stop_price: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary matching Binance order format."""
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "price": str(self.price),
            "origQty": str(self.quantity),
            "executedQty": str(self.quantity) if self.status == "FILLED" else "0",
            "status": self.status,
            "reduceOnly": self.reduce_only,
            "stopPrice": str(self.stop_price) if self.stop_price else None,
        }


class PaperBinanceClient:
    """Simulated Binance client for paper trading.
    
    Uses real market data from Binance public API but simulates all order execution.
    Tracks virtual positions and balance in memory, with balance persisted to database.
    """
    
    def __init__(self, account_id: str, initial_balance: float = 10000.0, balance_persistence_callback: Optional[Callable[[str, float], None]] = None):
        """Initialize paper trading client.
        
        Args:
            account_id: Account identifier
            initial_balance: Initial virtual balance (default: 10000 USDT)
            balance_persistence_callback: Optional callback function(account_id: str, balance: float) to persist balance to database
        """
        self.account_id = account_id
        self.balance = float(initial_balance)
        self.positions: Dict[str, VirtualPosition] = {}  # symbol -> VirtualPosition
        self.orders: Dict[int, VirtualOrder] = {}  # order_id -> VirtualOrder
        self._order_id_counter = int(time.time() * 1000)  # Start with timestamp-based ID
        self._balance_persistence_callback = balance_persistence_callback
        
        # Binance public API base URL (no authentication required)
        self.market_data_base_url = "https://fapi.binance.com/fapi/v1"
        
        # Cache for exchange info (precision, min notional, etc.)
        self._exchange_info_cache: Optional[Dict] = None
        self._precision_cache: Dict[str, int] = {}
        self._min_notional_cache: Dict[str, float] = {}
        
        # Track leverage per symbol (default: 1x)
        self._leverage_cache: Dict[str, int] = {}
        
        logger.info(f"Initialized PaperBinanceClient for account '{account_id}' with balance ${initial_balance:.2f}")
    
    def restore_positions_from_database(self, db_service) -> None:
        """Restore paper trading positions from database using position_instance_id.
        
        This method queries the database for all strategies with open positions
        (position_instance_id != None) for this account and restores them in memory.
        
        Args:
            db_service: DatabaseService instance with database session
        """
        try:
            from app.models.db_models import Strategy, Account
            from uuid import UUID
            
            # Get account UUID from account_id (could be UUID string or account name)
            account = None
            try:
                # Try as UUID first
                account_uuid = UUID(self.account_id) if self.account_id else None
                if account_uuid:
                    account = db_service.db.query(Account).filter(Account.id == account_uuid).first()
            except (ValueError, TypeError):
                # Not a UUID, will try by name below
                pass
            
            if not account:
                # Try to find account by name only (don't try to cast non-UUID string to UUID)
                account = db_service.db.query(Account).filter(Account.name == self.account_id).first()
            
            if not account or not account.paper_trading:
                logger.debug(f"Account '{self.account_id}' not found or not a paper trading account, skipping position restoration")
                return
            
            # Get all strategies with open positions (position_instance_id != None) for this account
            open_strategies = db_service.db.query(Strategy).filter(
                Strategy.account_id == account.id,
                Strategy.position_instance_id.isnot(None),  # Position is open
                Strategy.position_size > 0  # Has position size
            ).all()
            
            restored_count = 0
            for strategy in open_strategies:
                try:
                    # Restore position
                    self.positions[strategy.symbol] = VirtualPosition(
                        symbol=strategy.symbol,
                        side=strategy.position_side or "LONG",
                        size=float(strategy.position_size),
                        entry_price=float(strategy.entry_price) if strategy.entry_price else 0.0,
                        leverage=strategy.leverage or 1,
                        position_instance_id=str(strategy.position_instance_id)  # Match with strategy
                    )
                    
                    # Restore leverage setting
                    self._leverage_cache[strategy.symbol] = strategy.leverage or 1
                    
                    restored_count += 1
                    logger.info(
                        f"Restored paper position: {strategy.symbol} {strategy.position_side} "
                        f"@ {strategy.entry_price} (size={strategy.position_size}, "
                        f"instance_id={strategy.position_instance_id})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to restore position for strategy {strategy.id} ({strategy.symbol}): {e}"
                    )
            
            if restored_count > 0:
                logger.info(f"Restored {restored_count} paper trading position(s) for account '{self.account_id}'")
            else:
                logger.debug(f"No open positions to restore for account '{self.account_id}'")
                
        except Exception as e:
            logger.warning(f"Failed to restore positions from database for account '{self.account_id}': {e}")
            # Don't raise - position restoration failure shouldn't prevent client initialization
    
    def _fetch_public_data(self, endpoint: str, params: dict, max_retries: int = 3) -> Any:
        """Fetch data from Binance public API with error handling and retries.
        
        Args:
            endpoint: API endpoint (e.g., "klines", "ticker/price")
            params: Query parameters
            max_retries: Maximum number of retry attempts
            
        Returns:
            JSON response data
            
        Raises:
            BinanceNetworkError: On network errors
            BinanceRateLimitError: On rate limiting
            BinanceAPIError: On other API errors
        """
        url = f"{self.market_data_base_url}/{endpoint}"
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=10)
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited, waiting {retry_after}s before retry")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Timeout fetching {endpoint}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                raise BinanceNetworkError(f"Timeout fetching {endpoint} after {max_retries} attempts")
                
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Connection error fetching {endpoint}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                raise BinanceNetworkError(f"Connection error fetching {endpoint}: {e}")
                
            except requests.exceptions.HTTPError as e:
                error_code = None
                if hasattr(e.response, 'json'):
                    try:
                        error_data = e.response.json()
                        error_code = error_data.get('code')
                    except:
                        pass
                
                if error_code == -1121:  # Invalid symbol
                    raise BinanceAPIError(f"Invalid symbol: {params.get('symbol', 'unknown')}", error_code=error_code)
                else:
                    raise BinanceAPIError(f"API error fetching {endpoint}: {e}", error_code=error_code)
        
        raise BinanceAPIError(f"Failed to fetch {endpoint} after {max_retries} attempts")
    
    def _generate_order_id(self) -> int:
        """Generate unique order ID for paper trading.
        
        Uses timestamp-based ID with random component to ensure uniqueness.
        """
        self._order_id_counter += 1
        random_component = random.randint(1000, 9999)
        return self._order_id_counter * 10000 + random_component
    
    def _get_exchange_info(self) -> Dict:
        """Get and cache exchange info from Binance."""
        if self._exchange_info_cache is None:
            self._exchange_info_cache = self._fetch_public_data("exchangeInfo", {})
        return self._exchange_info_cache
    
    # Market Data Methods (use real Binance public API)
    
    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[List[Any]]:
        """Get candlestick data from Binance public API.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            interval: Kline interval (1m, 5m, 15m, 1h, etc.)
            limit: Number of klines to retrieve (max 1500)
            
        Returns:
            List of klines where each kline is [open_time, open, high, low, close, volume, ...]
        """
        return self._fetch_public_data("klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        })
    
    def get_price(self, symbol: str) -> float:
        """Get current price from Binance public API.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current price as float
        """
        data = self._fetch_public_data("ticker/price", {"symbol": symbol})
        price = float(data["price"])
        if price <= 0:
            raise BinanceAPIError(f"Invalid price returned for {symbol}: {price}")
        return price
    
    def get_quantity_precision(self, symbol: str) -> int:
        """Get quantity precision for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Number of decimal places for quantity
        """
        if symbol in self._precision_cache:
            return self._precision_cache[symbol]
        
        try:
            exchange_info = self._get_exchange_info()
            for s in exchange_info.get("symbols", []):
                if s["symbol"] == symbol:
                    for f in s.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            step_size = float(f.get("stepSize", "1.0"))
                            if step_size >= 1.0:
                                precision = 0
                            else:
                                step_str = f"{step_size:.10f}".rstrip("0").rstrip(".")
                                if "." in step_str:
                                    precision = len(step_str.split(".")[1])
                                else:
                                    precision = 0
                            self._precision_cache[symbol] = precision
                            return precision
        except Exception as exc:
            logger.warning(f"Error fetching precision for {symbol}: {exc}, defaulting to 3")
        
        # Default to 3 decimals if not found
        self._precision_cache[symbol] = 3
        return 3
    
    def get_min_notional(self, symbol: str) -> float:
        """Get minimum notional value for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Minimum notional value in USDT (default: 5.0)
        """
        if symbol in self._min_notional_cache:
            return self._min_notional_cache[symbol]
        
        try:
            exchange_info = self._get_exchange_info()
            for s in exchange_info.get("symbols", []):
                if s["symbol"] == symbol:
                    for f in s.get("filters", []):
                        if f.get("filterType") == "MIN_NOTIONAL":
                            min_notional = float(f.get("notional", "5.0"))
                            self._min_notional_cache[symbol] = min_notional
                            return min_notional
        except Exception as exc:
            logger.warning(f"Error fetching min notional for {symbol}: {exc}, defaulting to 5.0")
        
        # Default to 5 USDT if not found
        self._min_notional_cache[symbol] = 5.0
        return 5.0
    
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
    
    def get_current_leverage(self, symbol: str) -> int:
        """Get current leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current leverage (default: 1x if not set)
        """
        return self._leverage_cache.get(symbol, 1)
    
    def adjust_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set leverage for a symbol in paper trading.
        
        Simulates leverage adjustment without making API calls.
        Leverage affects PnL calculations for positions.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage multiplier (1-50)
            
        Returns:
            Dictionary matching Binance API response format
            
        Raises:
            BinanceAPIError: If leverage value is invalid
        """
        from app.core.exceptions import InvalidLeverageError
        
        if not (1 <= leverage <= 50):
            raise InvalidLeverageError(
                leverage=leverage,
                reason=f"Leverage must be between 1 and 50 for {symbol}"
            )
        
        # Store leverage for this symbol
        old_leverage = self._leverage_cache.get(symbol, 1)
        self._leverage_cache[symbol] = leverage
        
        # Update leverage in existing position if any
        if symbol in self.positions:
            self.positions[symbol].leverage = leverage
        
        logger.info(f"Paper trading: Set leverage={leverage}x for {symbol} (was {old_leverage}x)")
        
        # Return response matching Binance API format
        return {
            "leverage": leverage,
            "maxNotionalValue": "1000000",  # Simulated max notional
            "symbol": symbol
        }
    
    def futures_account_balance(self) -> float:
        """Get virtual account balance.
        
        Returns:
            Current virtual balance in USDT
        """
        return self.balance
    
    # Position Management Methods
    
    def get_open_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get virtual open position for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position dict matching Binance format, or None if no position
        """
        position = self.positions.get(symbol)
        if not position:
            return None
        
        # Calculate unrealized PnL based on current price (with leverage)
        current_price = self.get_price(symbol)
        leverage = position.leverage
        if position.side == "LONG":
            unrealized_pnl = (current_price - position.entry_price) * position.size * leverage
        else:  # SHORT
            unrealized_pnl = (position.entry_price - current_price) * position.size * leverage
        
        position.unrealized_pnl = unrealized_pnl
        
        return {
            "symbol": symbol,
            "positionAmt": str(position.size) if position.side == "LONG" else f"-{position.size}",
            "entryPrice": str(position.entry_price),
            "unRealizedProfit": str(unrealized_pnl),
            "markPrice": str(current_price),
            "leverage": position.leverage,
        }
    
    def futures_position_information(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all virtual positions (for compatibility with BinanceClient).
        
        Args:
            symbol: Optional symbol filter (if None, returns all positions)
            
        Returns:
            List of position dicts matching Binance format
        """
        positions_list = []
        
        # If symbol is specified, return only that position
        if symbol:
            position = self.get_open_position(symbol)
            if position:
                positions_list.append(position)
            return positions_list
        
        # Return all positions
        for symbol_key, position in self.positions.items():
            pos_dict = self.get_open_position(symbol_key)
            if pos_dict:
                positions_list.append(pos_dict)
        
        return positions_list
    
    # Order Execution Methods (simulated)
    
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
        position_instance_id: Optional[str] = None,
    ) -> OrderResponse:
        """Place a simulated order.
        
        Simulates order execution with realistic slippage and fees.
        Updates virtual balance and positions.
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Order quantity
            order_type: MARKET or LIMIT (default: MARKET)
            reduce_only: Whether order is reduce-only
            price: Limit price (required for LIMIT orders)
            client_order_id: Client order ID (optional)
            
        Returns:
            OrderResponse with simulated execution details
        """
        # Round quantity to correct precision
        rounded_quantity = self.round_quantity(symbol, quantity)
        
        # Get current price
        current_price = self.get_price(symbol)
        
        # Calculate fill price with slippage
        if order_type == "MARKET":
            if side == "BUY":
                fill_price = current_price * (1 + SPREAD_OFFSET)  # Pay ask price
            else:  # SELL
                fill_price = current_price * (1 - SPREAD_OFFSET)  # Sell at bid price
        else:  # LIMIT
            if price is None:
                raise ValueError("Price is required for LIMIT orders")
            fill_price = price
        
        # Calculate fees
        notional = fill_price * rounded_quantity
        fee = notional * AVERAGE_FEE_RATE
        
        # Generate order ID
        order_id = self._generate_order_id()
        
        # Update virtual position
        # For new positions, pass position_instance_id; for existing positions, preserve it
        existing_position = self.positions.get(symbol)
        if existing_position and existing_position.position_instance_id:
            # Preserve existing position_instance_id when adding to position
            position_instance_id = existing_position.position_instance_id
        elif not reduce_only:
            # New position - use provided position_instance_id
            pass  # Use the parameter value
        else:
            # Closing position - preserve existing ID if available
            position_instance_id = existing_position.position_instance_id if existing_position else None
        
        pnl = self._update_position(symbol, side, rounded_quantity, fill_price, reduce_only, position_instance_id)
        
        # Update virtual balance (subtract fee, add PnL if closing position)
        old_balance = self.balance
        self.balance = self.balance - fee + pnl
        
        # Persist balance to database if callback is set
        if self._balance_persistence_callback:
            try:
                self._balance_persistence_callback(self.account_id, self.balance)
            except Exception as e:
                logger.warning(f"Failed to persist paper trading balance for account {self.account_id}: {e}")
        
        # Create OrderResponse
        order_response = OrderResponse(
            symbol=symbol,
            order_id=order_id,
            status="FILLED",
            side=side,
            price=fill_price,
            avg_price=fill_price,
            executed_qty=rounded_quantity,
            orig_qty=rounded_quantity,
            remaining_qty=0.0,
            notional_value=notional,
            cummulative_quote_qty=notional,
            commission=fee,
            commission_asset="USDT",
            realized_pnl=pnl if pnl != 0 else None,
            timestamp=datetime.now(timezone.utc),
            order_type=order_type,
            client_order_id=client_order_id,
        )
        
        logger.info(
            f"Paper trade executed: {side} {rounded_quantity} {symbol} @ ${fill_price:.8f} "
            f"(fee: ${fee:.2f}, balance: ${old_balance:.2f} -> ${self.balance:.2f})"
        )
        
        return order_response
    
    def _update_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        reduce_only: bool = False,
        position_instance_id: Optional[str] = None
    ) -> float:
        """Update virtual position after order execution.
        
        Returns:
            Realized PnL if position was closed, 0.0 otherwise (with leverage applied)
        """
        position = self.positions.get(symbol)
        pnl = 0.0
        leverage = self.get_current_leverage(symbol)  # Get leverage for this symbol
        
        if side == "BUY":
            if position and position.side == "SHORT":
                # Closing short position
                if quantity >= position.size:
                    # Fully closed - use position's leverage (from when it was opened)
                    pnl = (position.entry_price - price) * position.size * position.leverage
                    del self.positions[symbol]
                    logger.debug(f"Closed SHORT position for {symbol}, PnL: ${pnl:.2f} (leverage: {position.leverage}x)")
                else:
                    # Partially closed
                    pnl = (position.entry_price - price) * quantity * position.leverage
                    position.size -= quantity
                    logger.debug(f"Partially closed SHORT position for {symbol}, PnL: ${pnl:.2f} (leverage: {position.leverage}x)")
            else:
                # Opening/increasing long position
                if position and position.side == "LONG":
                    # Average entry price
                    total_cost = (position.entry_price * position.size) + (price * quantity)
                    position.size += quantity
                    position.entry_price = total_cost / position.size
                    # Update leverage if it changed
                    position.leverage = leverage
                    logger.debug(f"Increased LONG position for {symbol} to {position.size} (leverage: {leverage}x)")
                else:
                    # New position - use current leverage
                    self.positions[symbol] = VirtualPosition(
                        symbol=symbol,
                        side="LONG",
                        size=quantity,
                        entry_price=price,
                        leverage=leverage,
                        position_instance_id=position_instance_id,  # Store position_instance_id
                    )
                    logger.debug(
                        f"Opened LONG position for {symbol}: {quantity} @ ${price:.8f} "
                        f"(leverage: {leverage}x, instance_id={position_instance_id})"
                    )
        
        else:  # SELL
            if position and position.side == "LONG":
                # Closing long position
                if quantity >= position.size:
                    # Fully closed - use position's leverage
                    pnl = (price - position.entry_price) * position.size * position.leverage
                    del self.positions[symbol]
                    logger.debug(f"Closed LONG position for {symbol}, PnL: ${pnl:.2f} (leverage: {position.leverage}x)")
                else:
                    # Partially closed
                    pnl = (price - position.entry_price) * quantity * position.leverage
                    position.size -= quantity
                    logger.debug(f"Partially closed LONG position for {symbol}, PnL: ${pnl:.2f} (leverage: {position.leverage}x)")
            else:
                # Opening/increasing short position
                if position and position.side == "SHORT":
                    # Average entry price
                    total_cost = (position.entry_price * position.size) + (price * quantity)
                    position.size += quantity
                    position.entry_price = total_cost / position.size
                    # Update leverage if it changed
                    position.leverage = leverage
                    logger.debug(f"Increased SHORT position for {symbol} to {position.size} (leverage: {leverage}x)")
                else:
                    # New position - use current leverage
                    self.positions[symbol] = VirtualPosition(
                        symbol=symbol,
                        side="SHORT",
                        size=quantity,
                        entry_price=price,
                        leverage=leverage,
                        position_instance_id=position_instance_id,  # Store position_instance_id
                    )
                    logger.debug(
                        f"Opened SHORT position for {symbol}: {quantity} @ ${price:.8f} "
                        f"(leverage: {leverage}x, instance_id={position_instance_id})"
                    )
        
        return pnl
    
    # Order Management Methods
    
    def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Get virtual open orders (TP/SL orders) for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of order dictionaries
        """
        return [
            order.to_dict() for order in self.orders.values()
            if order.symbol == symbol and order.status == "NEW"
        ]
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel a virtual order.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel
            
        Returns:
            Cancelled order dictionary
        """
        if order_id in self.orders:
            self.orders[order_id].status = "CANCELLED"
            return self.orders[order_id].to_dict()
        return {"orderId": order_id, "status": "CANCELLED"}
    
    def cancel_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Cancel all open orders for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of cancelled order dictionaries
        """
        cancelled = []
        for order_id, order in self.orders.items():
            if order.symbol == symbol and order.status == "NEW":
                order.status = "CANCELLED"
                cancelled.append(order.to_dict())
        return cancelled
    
    def place_stop_loss_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        close_position: bool = False,
    ) -> Dict[str, Any]:
        """Place a virtual stop loss order.
        
        Stores order and checks on price updates (not implemented in MVP).
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Order quantity (ignored if close_position=True)
            stop_price: Stop price
            close_position: If True, closes entire position (quantity ignored)
            
        Returns:
            Dictionary matching Binance API response format
        """
        order_id = self._generate_order_id()
        order = VirtualOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type="STOP_MARKET",
            price=stop_price,
            quantity=quantity if not close_position else 0.0,
            status="NEW",
            reduce_only=True,
            stop_price=stop_price,
        )
        self.orders[order_id] = order
        
        # Return dictionary matching Binance API response format (same as BinanceClient)
        result = {
            "orderId": order_id,
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "stopPrice": str(stop_price),
            "status": "NEW",
            "reduceOnly": True,
        }
        if close_position:
            result["closePosition"] = True
        else:
            result["origQty"] = str(quantity)
            result["executedQty"] = "0"
        return result
    
    def place_take_profit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        close_position: bool = False,
    ) -> Dict[str, Any]:
        """Place a virtual take profit order.
        
        Stores order and checks on price updates (not implemented in MVP).
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Order quantity (ignored if close_position=True)
            stop_price: Take profit price (trigger price)
            close_position: If True, closes entire position (quantity ignored)
            
        Returns:
            Dictionary matching Binance API response format
        """
        order_id = self._generate_order_id()
        order = VirtualOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type="TAKE_PROFIT_MARKET",
            price=stop_price,
            quantity=quantity if not close_position else 0.0,
            status="NEW",
            reduce_only=True,
        )
        self.orders[order_id] = order
        
        # Return dictionary matching Binance API response format (same as BinanceClient)
        result = {
            "orderId": order_id,
            "symbol": symbol,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": str(stop_price),
            "status": "NEW",
            "reduceOnly": True,
        }
        if close_position:
            result["closePosition"] = True
        else:
            result["origQty"] = str(quantity)
            result["executedQty"] = "0"
        return result
    
    def get_order_status(self, symbol: str, order_id: int) -> Optional[Dict[str, Any]]:
        """Get virtual order status.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID
            
        Returns:
            Order dictionary or None if not found
        """
        if order_id in self.orders:
            return self.orders[order_id].to_dict()
        return None
    
    def get_funding_fees(self, symbol: str, start_time: Optional[int] = None, end_time: Optional[int] = None) -> float:
        """Get funding fees (returns 0.0 for paper trading).
        
        Paper trading doesn't simulate funding fees in MVP.
        """
        return 0.0
    
    def get_time_offset(self) -> int:
        """Get time offset (returns 0 for paper trading).
        
        Paper trading doesn't need time synchronization.
        """
        return 0

