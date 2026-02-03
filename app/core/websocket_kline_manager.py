"""
WebSocket Kline Manager - Singleton manager for WebSocket kline streams.

This manager handles all WebSocket connections for kline data, providing
a centralized way for strategies to access real-time market data.
"""

import asyncio
import threading
from typing import Dict, Optional, List
from loguru import logger

from app.core.websocket_connection import WebSocketConnection
from app.core.kline_buffer import KlineBuffer
from app.core.public_market_data_client import PublicMarketDataClient


class WebSocketKlineManager:
    """Singleton manager for WebSocket kline streams."""
    
    _instance: Optional['WebSocketKlineManager'] = None
    _thread_lock = threading.Lock()  # Use threading.Lock for __new__
    _lock = asyncio.Lock()  # For async operations
    
    def __new__(cls, testnet: bool = True):
        """Singleton pattern (thread-safe).
        
        Args:
            testnet: Whether to use testnet endpoints
            
        Returns:
            Singleton instance of WebSocketKlineManager
        """
        if cls._instance is None:
            # Use threading.Lock for thread-safe singleton
            with cls._thread_lock:
                if cls._instance is None:  # Double-check pattern
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, testnet: bool = True):
        """Initialize manager (only once due to singleton).
        
        Args:
            testnet: Whether to use testnet endpoints
        """
        if self._initialized:
            # Already initialized - don't log again (singleton pattern)
            return
        
        self.testnet = testnet
        self.connections: Dict[str, WebSocketConnection] = {}
        self.buffers: Dict[str, KlineBuffer] = {}
        self.subscription_counts: Dict[str, int] = {}
        # Event-based notification for new candles (key: symbol_interval)
        self.new_candle_events: Dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        # Pass testnet parameter to PublicMarketDataClient
        self._public_client = PublicMarketDataClient(testnet=testnet, timeout=10.0)
        self._initialized = True
        
        # Only log on first initialization (singleton pattern)
        logger.info(f"WebSocketKlineManager initialized (testnet={testnet})")
    
    async def subscribe(self, symbol: str, interval: str) -> None:
        """Subscribe to kline stream for symbol/interval (idempotent).
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            interval: Kline interval (e.g., '1m', '5m')
        """
        key = f"{symbol.upper()}_{interval}"
        
        async with self._lock:
            # Increment subscription count
            self.subscription_counts[key] = self.subscription_counts.get(key, 0) + 1
            
            # If already subscribed, just increment count
            if key in self.connections:
                logger.debug(f"WebSocket already subscribed: {symbol} {interval} (count: {self.subscription_counts[key]})")
                return
            
            # Create buffer
            self.buffers[key] = KlineBuffer(max_size=1000)
            
            # Create event for new candle notifications
            self.new_candle_events[key] = asyncio.Event()
            
            # Create connection
            connection = WebSocketConnection(
                symbol=symbol,
                interval=interval,
                testnet=self.testnet,
                on_kline_update=self._on_kline_update_factory(key)
            )
            
            self.connections[key] = connection
            
            # Start connection
            await connection.connect()
            
            # Wait for connection (with timeout)
            connected = await connection.wait_until_connected(timeout=10.0)
            if not connected:
                logger.warning(
                    f"WebSocket connection timeout for {symbol} {interval}. "
                    f"Strategies will use REST API fallback for this symbol/interval."
                )
                # Don't fail - strategies will use REST API fallback
                # Keep the connection object so retries can continue in background
            else:
                logger.info(f"WebSocket subscribed: {symbol} {interval}")
    
    async def unsubscribe(self, symbol: str, interval: str) -> None:
        """Unsubscribe from kline stream (decrements count, closes if count reaches 0).
        
        Args:
            symbol: Trading symbol
            interval: Kline interval
        """
        key = f"{symbol.upper()}_{interval}"
        
        async with self._lock:
            if key not in self.subscription_counts:
                return
            
            # Decrement subscription count
            self.subscription_counts[key] -= 1
            
            if self.subscription_counts[key] <= 0:
                # No more subscribers, close connection
                if key in self.connections:
                    await self.connections[key].disconnect()
                    del self.connections[key]
                
                if key in self.buffers:
                    await self.buffers[key].clear()
                    del self.buffers[key]
                
                # Clean up event
                if key in self.new_candle_events:
                    del self.new_candle_events[key]
                
                del self.subscription_counts[key]
                
                logger.info(f"WebSocket unsubscribed: {symbol} {interval}")
            else:
                logger.debug(f"WebSocket subscription decremented: {symbol} {interval} (count: {self.subscription_counts[key]})")
    
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100
    ) -> List[List]:
        """Get klines for symbol/interval (from buffer or fetch initial from REST).
        
        Args:
            symbol: Trading symbol
            interval: Kline interval
            limit: Maximum number of klines to return
            
        Returns:
            List of klines in Binance format
            
        Raises:
            Exception: If REST API fetch fails (strategy should handle fallback)
        """
        key = f"{symbol.upper()}_{interval}"
        
        # Ensure subscribed
        await self.subscribe(symbol, interval)
        
        # Get from buffer if available
        if key in self.buffers:
            buffer_size = await self.buffers[key].size()
            if buffer_size >= limit:
                klines = await self.buffers[key].get_klines(limit=limit)
                logger.debug(f"Got {len(klines)} klines from WebSocket buffer: {symbol} {interval}")
                return klines
        
        # Buffer doesn't have enough data, fetch initial from REST API
        logger.info(f"Fetching initial {limit} klines from REST API: {symbol} {interval}")
        try:
            klines = self._public_client.get_klines(symbol, interval, limit)
            
            # Store in buffer
            if key in self.buffers:
                for kline in klines:
                    # Convert to WebSocket format for buffer
                    ws_format = self._convert_to_websocket_format(kline, symbol, interval)
                    await self.buffers[key].add_kline(ws_format)
            
            return klines
        except Exception as e:
            logger.error(f"Failed to fetch initial klines from REST API: {e}")
            raise  # Re-raise to let strategy handle fallback
    
    def _on_kline_update_factory(self, key: str):
        """Factory function to create kline update handler.
        
        Args:
            key: Buffer key (symbol_interval)
            
        Returns:
            Async function to handle kline updates
        """
        async def on_kline_update(data: Dict) -> None:
            """Handle kline update from WebSocket."""
            if key in self.buffers:
                await self.buffers[key].add_kline(data)
                logger.debug(f"Kline update received: {key}")
                
                # Notify strategies when a new closed candle arrives
                # Check if this is a closed candle (x=True means candle is closed)
                kline_data = data.get("k", {})
                is_closed = kline_data.get("x", False)
                if is_closed and key in self.new_candle_events:
                    # CRITICAL: Ensure all waiting strategies are notified of the new candle
                    # Strategy: Set event (notify waiters), then clear (reset for next candle)
                    # This ensures:
                    # 1. All current waiters are notified (event.set() wakes them up)
                    # 2. Event is cleared for the next candle (so wait_for_new_candle() will block until next candle)
                    # 
                    # Note: If event is already set, setting it again is idempotent (no-op)
                    # This handles the case where a new candle arrives while previous one's event is still set
                    self.new_candle_events[key].set()  # Notify all current waiters
                    # Clear immediately - this is safe because:
                    # - All waiters that were waiting have been notified (they're now running)
                    # - New waiters will wait on the cleared event until next candle arrives
                    # - If a new candle arrives very quickly, the event will be set again (handled above)
                    self.new_candle_events[key].clear()
                    logger.debug(f"New closed candle event set for {key} (notified waiters, cleared for next candle)")
        
        return on_kline_update
    
    def _convert_to_websocket_format(self, kline: List, symbol: str, interval: str) -> Dict:
        """Convert Binance REST format to WebSocket format.
        
        Args:
            kline: Kline in Binance REST format
            symbol: Trading symbol
            interval: Kline interval
            
        Returns:
            Kline in WebSocket format
        """
        return {
            "e": "kline",
            "k": {
                "t": kline[0],      # Open time
                "T": kline[6],      # Close time
                "s": symbol.upper(),  # Symbol
                "i": interval,      # Interval
                "o": str(kline[1]),  # Open
                "c": str(kline[4]),  # Close
                "h": str(kline[2]),  # High
                "l": str(kline[3]),  # Low
                "v": str(kline[5]), # Volume
                "n": kline[8],       # Number of trades
                "x": True,          # Is closed
                "q": str(kline[7]),  # Quote asset volume
                "V": str(kline[9]), # Taker buy base asset volume
                "Q": str(kline[10]), # Taker buy quote asset volume
                "B": "0"
            }
        }
    
    async def get_latest_kline(self, symbol: str, interval: str) -> Optional[List]:
        """Get the latest kline for symbol/interval.
        
        Args:
            symbol: Trading symbol
            interval: Kline interval
            
        Returns:
            Latest kline in Binance format, or None if not available
        """
        key = f"{symbol.upper()}_{interval}"
        
        if key in self.buffers:
            return await self.buffers[key].get_latest_kline()
        
        return None
    
    async def is_subscribed(self, symbol: str, interval: str) -> bool:
        """Check if symbol/interval is subscribed.
        
        Args:
            symbol: Trading symbol
            interval: Kline interval
            
        Returns:
            True if subscribed, False otherwise
        """
        key = f"{symbol.upper()}_{interval}"
        return key in self.connections
    
    async def wait_for_new_candle(self, symbol: str, interval: str, timeout: Optional[float] = None) -> bool:
        """Wait for a new closed candle to arrive.
        
        This method allows multiple strategies to wait on the same event.
        When a new candle arrives, all waiting strategies will be notified simultaneously.
        
        Args:
            symbol: Trading symbol
            interval: Kline interval
            timeout: Maximum time to wait (None = wait indefinitely)
            
        Returns:
            True if new candle arrived, False if timeout
        """
        key = f"{symbol.upper()}_{interval}"
        
        # Ensure subscribed
        await self.subscribe(symbol, interval)
        
        if key not in self.new_candle_events:
            return False
        
        try:
            # Wait for event to be set (all strategies waiting on this event will be notified)
            await asyncio.wait_for(self.new_candle_events[key].wait(), timeout=timeout)
            # Event is cleared by the on_kline_update handler when next candle arrives
            return True
        except asyncio.TimeoutError:
            return False
    
    async def get_connection_status(self) -> Dict[str, Dict]:
        """Get status of all connections.
        
        Returns:
            Dictionary mapping connection keys to status info
        """
        status = {}
        async with self._lock:
            for key, connection in self.connections.items():
                status[key] = {
                    "connected": connection.is_connected(),
                    "subscriptions": self.subscription_counts.get(key, 0)
                }
        return status
    
    async def shutdown(self) -> None:
        """Shutdown all connections."""
        async with self._lock:
            for key, connection in list(self.connections.items()):
                await connection.disconnect()
            
            self.connections.clear()
            self.buffers.clear()
            self.subscription_counts.clear()
            self.new_candle_events.clear()
            
            logger.info("WebSocketKlineManager shut down")

