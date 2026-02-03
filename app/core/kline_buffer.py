"""
Kline Buffer - Thread-safe buffer for kline data from WebSocket streams.

This buffer stores klines in memory and provides thread-safe access
for multiple strategies sharing the same symbol/interval stream.
"""

from typing import Dict, List, Optional
from collections import deque
import asyncio
from loguru import logger


class KlineBuffer:
    """Thread-safe buffer for kline data."""
    
    def __init__(self, max_size: int = 1000):
        """Initialize kline buffer.
        
        Args:
            max_size: Maximum number of klines to store (default: 1000)
        """
        self.max_size = max_size
        self._buffer: deque = deque(maxlen=max_size)
        self._lock = asyncio.Lock()
        self._last_update_time: Optional[float] = None
    
    async def add_kline(self, kline_data: Dict) -> None:
        """Add a new kline to the buffer.
        
        Args:
            kline_data: WebSocket kline data in format:
                {
                    "e": "kline",
                    "k": {
                        "t": 1234567890,  # Open time
                        "T": 1234567890,  # Close time
                        "o": "100.0",     # Open
                        "c": "101.0",     # Close
                        "h": "102.0",     # High
                        "l": "99.0",      # Low
                        "v": "1000.0",    # Volume
                        "x": True,        # Is closed
                        ...
                    }
                }
        """
        async with self._lock:
            # Convert WebSocket format to Binance format
            binance_kline = self._convert_to_binance_format(kline_data)
            
            # Get 'k' object first, then get 'T' from it
            k = kline_data.get("k", {})
            close_time = int(k.get("T", 0))
            
            if self._buffer and int(self._buffer[-1][6]) == close_time:
                # Update existing kline (in case of updates before close)
                self._buffer[-1] = binance_kline
                logger.debug(f"Updated existing kline with close_time={close_time}")
            else:
                # Add new kline
                self._buffer.append(binance_kline)
                logger.debug(f"Added new kline with close_time={close_time}")
            
            self._last_update_time = asyncio.get_event_loop().time()
    
    async def get_klines(self, limit: int = 100) -> List[List]:
        """Get last N klines from buffer.
        
        Args:
            limit: Maximum number of klines to return
            
        Returns:
            List of klines in Binance format: [[open_time, open, high, low, close, volume, close_time, ...], ...]
        """
        async with self._lock:
            if len(self._buffer) < limit:
                return list(self._buffer)
            return list(self._buffer)[-limit:]
    
    async def get_latest_kline(self) -> Optional[List]:
        """Get the latest kline.
        
        Returns:
            Latest kline in Binance format, or None if buffer is empty
        """
        async with self._lock:
            if not self._buffer:
                return None
            return list(self._buffer)[-1]
    
    def _convert_to_binance_format(self, kline_data: Dict) -> List:
        """Convert WebSocket kline format to Binance REST API format.
        
        Args:
            kline_data: WebSocket kline data
            
        Returns:
            Kline in Binance format: [open_time, open, high, low, close, volume, close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, ignore]
        """
        k = kline_data.get("k", {})
        return [
            int(k.get("t", 0)),           # Open time
            k.get("o", "0"),              # Open
            k.get("h", "0"),              # High
            k.get("l", "0"),              # Low
            k.get("c", "0"),              # Close
            k.get("v", "0"),              # Volume
            int(k.get("T", 0)),           # Close time
            k.get("q", "0"),              # Quote asset volume
            int(k.get("n", 0)),           # Number of trades
            k.get("V", "0"),              # Taker buy base asset volume
            k.get("Q", "0"),              # Taker buy quote asset volume
            "0"                           # Ignore
        ]
    
    async def clear(self) -> None:
        """Clear the buffer."""
        async with self._lock:
            self._buffer.clear()
            self._last_update_time = None
            logger.debug("Kline buffer cleared")
    
    async def size(self) -> int:
        """Get buffer size.
        
        Returns:
            Number of klines in buffer
        """
        async with self._lock:
            return len(self._buffer)
    
    async def get_last_update_time(self) -> Optional[float]:
        """Get timestamp of last update.
        
        Returns:
            Timestamp of last kline update, or None if buffer is empty
        """
        async with self._lock:
            return self._last_update_time


