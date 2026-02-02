"""
Public Market Data Client - Fetches market data without authentication.

This client is used for:
- Klines (candlestick data)
- Current prices
- Exchange info
- Ticker data

No API keys required - uses Binance public endpoints.
"""

import requests
import time
from typing import List, Any, Dict, Optional
from loguru import logger

from app.core.exceptions import (
    BinanceAPIError,
    BinanceNetworkError,
    BinanceRateLimitError
)


class PublicMarketDataClient:
    """Client for fetching public market data from Binance (no authentication required)."""
    
    BASE_URL = "https://fapi.binance.com/fapi/v1"
    
    def __init__(self, timeout: float = 10.0):
        """Initialize public market data client.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._exchange_info_cache: Optional[Dict] = None
    
    def _fetch_public_data(
        self, 
        endpoint: str, 
        params: dict, 
        max_retries: int = 3
    ) -> Any:
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
        url = f"{self.BASE_URL}/{endpoint}"
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=self.timeout)
                
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
                    raise BinanceAPIError(
                        f"Invalid symbol: {params.get('symbol', 'unknown')}", 
                        error_code=error_code
                    )
                else:
                    raise BinanceAPIError(
                        f"API error fetching {endpoint}: {e}", 
                        error_code=error_code
                    )
        
        raise BinanceAPIError(f"Failed to fetch {endpoint} after {max_retries} attempts")
    
    def get_klines(
        self, 
        symbol: str, 
        interval: str = "1m", 
        limit: int = 100
    ) -> List[List[Any]]:
        """Get candlestick data from Binance public API.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            interval: Kline interval (1m, 5m, 15m, 1h, etc.)
            limit: Number of klines to retrieve (max 1500)
            
        Returns:
            List of klines where each kline is [open_time, open, high, low, close, volume, ...]
        """
        symbol = symbol.strip().upper()
        limit = min(limit, 1500)  # Binance max limit
        
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
        symbol = symbol.strip().upper()
        data = self._fetch_public_data("ticker/price", {"symbol": symbol})
        price = float(data["price"])
        if price <= 0:
            raise BinanceAPIError(f"Invalid price returned for {symbol}: {price}")
        return price
    
    def get_exchange_info(self) -> Dict:
        """Get exchange information (cached).
        
        Returns:
            Exchange info dictionary
        """
        if self._exchange_info_cache is None:
            self._exchange_info_cache = self._fetch_public_data("exchangeInfo", {})
        return self._exchange_info_cache

