"""
WebSocket Connection - Handles individual WebSocket connection for kline streams.

Each connection manages a single WebSocket stream for a symbol/interval pair,
with automatic reconnection and error handling.
"""

import asyncio
import json
import websockets
from typing import Callable, Optional, Dict, Awaitable
from loguru import logger
# Removed tenacity import - retry logic is handled in _run() method to avoid TypeError issues


class WebSocketConnection:
    """Manages a single WebSocket connection for kline stream."""
    
    def __init__(
        self,
        symbol: str,
        interval: str,
        testnet: bool = True,
        on_kline_update: Optional[Callable[[Dict], Awaitable[None]]] = None
    ):
        """Initialize WebSocket connection.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            interval: Kline interval (e.g., '1m', '5m')
            testnet: Whether to use testnet endpoints (will fallback to mainnet if testnet fails)
            on_kline_update: Callback function for kline updates
        """
        self.symbol = symbol.upper()
        self.interval = interval
        self.testnet = testnet
        self.on_kline_update = on_kline_update
        self._use_mainnet_fallback = False  # Track if we've switched to mainnet fallback
        
        # Construct WebSocket URL
        # Strategy: Try testnet first, but fallback to mainnet if testnet fails
        # This is safe because WebSocket streams are public market data (no authentication)
        if testnet:
            # Testnet WebSocket URL - will try this first
            self.testnet_url = f"wss://testnet.binancefuture.com/ws/{symbol.lower()}@kline_{interval}"
            # Mainnet WebSocket URL - fallback if testnet fails
            self.mainnet_url = f"wss://fstream.binance.com/ws/{symbol.lower()}@kline_{interval}"
            self.url = self.testnet_url  # Start with testnet
        else:
            # Mainnet WebSocket URL
            self.url = f"wss://fstream.binance.com/ws/{symbol.lower()}@kline_{interval}"
            self.testnet_url = None
            self.mainnet_url = self.url
        
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_attempts = 0
        self._testnet_failure_count = 0  # Track testnet failures
        self._max_testnet_failures = 3  # Switch to mainnet after 3 testnet failures
        self._max_reconnect_attempts = 10
        self._task: Optional[asyncio.Task] = None
    
    async def connect(self) -> None:
        """Start WebSocket connection."""
        if self._running:
            logger.warning(f"WebSocket already running for {self.symbol} {self.interval}")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"WebSocket connection started: {self.symbol} {self.interval}")
    
    async def disconnect(self) -> None:
        """Stop WebSocket connection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        logger.info(f"WebSocket connection stopped: {self.symbol} {self.interval}")
    
    async def _run(self) -> None:
        """Main connection loop with reconnection logic and testnet->mainnet fallback."""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                
                # Check if we should switch from testnet to mainnet
                if (self.testnet and 
                    not self._use_mainnet_fallback and 
                    self.testnet_url and 
                    self.mainnet_url):
                    self._testnet_failure_count += 1
                    if self._testnet_failure_count >= self._max_testnet_failures:
                        # Switch to mainnet WebSocket
                        self.url = self.mainnet_url
                        self._use_mainnet_fallback = True
                        logger.info(
                            f"Testnet WebSocket failed {self._testnet_failure_count} times for {self.symbol} {self.interval}. "
                            f"Switching to mainnet WebSocket (safe - market data only, no authentication needed)."
                        )
                        self._reconnect_attempts = 0  # Reset attempts for mainnet
                
                self._reconnect_attempts += 1
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    logger.error(
                        f"WebSocket max reconnection attempts reached for {self.symbol} {self.interval}: {e}. "
                        f"Strategies will continue using REST API fallback."
                    )
                    # Don't break - keep trying in background, but strategies will use REST API
                    # Reset attempts counter to allow periodic retry attempts
                    self._reconnect_attempts = 0
                    wait_time = 300  # Wait 5 minutes before next retry cycle
                else:
                    wait_time = min(2 ** self._reconnect_attempts, 60)  # Exponential backoff, max 60s
                
                url_type = "mainnet" if self._use_mainnet_fallback else ("testnet" if self.testnet else "mainnet")
                logger.warning(
                    f"WebSocket error for {self.symbol} {self.interval} ({url_type}) "
                    f"(attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}): {e}. "
                    f"Reconnecting in {wait_time}s... (Strategies will use REST API in the meantime)"
                )
                await asyncio.sleep(wait_time)
    
    async def _connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for messages.
        
        Note: Retry logic is handled in _run() method, not here.
        This allows better control over testnet->mainnet fallback.
        """
        # Remove @retry decorator - retry logic is in _run() method
        # This prevents TypeError issues with tenacity and async functions
        try:
            # Note: extra_headers/additional_headers not supported in websockets.connect()
            # Headers can be set via create_connection() but that's more complex
            # For now, we'll connect without custom headers (not critical for Binance)
            async with websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            ) as ws:
                self._ws = ws
                self._reconnect_attempts = 0  # Reset on successful connection
                self._testnet_failure_count = 0  # Reset testnet failure count on success
                url_type = "mainnet" if self._use_mainnet_fallback else ("testnet" if self.testnet else "mainnet")
                logger.info(f"WebSocket connected: {self.symbol} {self.interval} ({url_type})")
                
                async for message in ws:
                    if not self._running:
                        break
                    
                    try:
                        data = json.loads(message)
                        await self._handle_message(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse WebSocket message: {e}")
                    except Exception as e:
                        logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
        finally:
            # Clear _ws when connection closes
            self._ws = None
    
    async def _handle_message(self, data: Dict) -> None:
        """Handle incoming WebSocket message.
        
        Args:
            data: Parsed JSON message from WebSocket
        """
        if data.get("e") != "kline":
            return
        
        kline_data = data.get("k", {})
        is_closed = kline_data.get("x", False)
        
        if not is_closed:
            # Candle is still forming, ignore for now
            # (we only process closed candles)
            return
        
        # Call callback if provided
        if self.on_kline_update:
            await self.on_kline_update(data)
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected.
        
        Returns:
            True if connected, False otherwise
        """
        return self._ws is not None and not self._ws.closed
    
    async def wait_until_connected(self, timeout: float = 10.0) -> bool:
        """Wait until WebSocket is connected.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if connected within timeout, False otherwise
        """
        start_time = asyncio.get_event_loop().time()
        while not self.is_connected():
            if asyncio.get_event_loop().time() - start_time > timeout:
                return False
            await asyncio.sleep(0.1)
        return True

