from __future__ import annotations

import json
from typing import Optional

from loguru import logger

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    # Only log warning if Redis is actually enabled in config
    # This prevents false warnings during module import


class RedisStorage:
    """Redis storage for strategies and trades persistence."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0", enabled: bool = True):
        self.enabled = enabled and REDIS_AVAILABLE
        self._client: Optional[redis.Redis] = None
        
        if enabled and not REDIS_AVAILABLE:
            # Only log warning if Redis was requested but package is not available
            logger.warning("redis package not installed. Redis storage will be disabled. Install with: pip install redis>=5.0.0")
        
        if self.enabled:
            try:
                self._client = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self._client.ping()
                logger.info(f"Connected to Redis at {redis_url}")
            except Exception as exc:
                logger.warning(f"Failed to connect to Redis: {exc}. Falling back to in-memory only.")
                self.enabled = False
                self._client = None
        elif enabled:
            # Redis was enabled but is not available
            logger.info("Redis storage is disabled (package not installed)")
        else:
            logger.debug("Redis storage is disabled (configuration)")
    
    def _key(self, prefix: str, strategy_id: str) -> str:
        """Generate Redis key for a strategy."""
        return f"binance_bot:{prefix}:{strategy_id}"
    
    def save_strategy(self, strategy_id: str, strategy_data: dict) -> bool:
        """Save strategy to Redis."""
        if not self.enabled or not self._client:
            return False
        
        try:
            key = self._key("strategy", strategy_id)
            # Convert datetime and other non-serializable types
            serializable_data = self._make_serializable(strategy_data)
            self._client.set(key, json.dumps(serializable_data))
            return True
        except Exception as exc:
            logger.error(f"Failed to save strategy {strategy_id} to Redis: {exc}")
            return False
    
    def get_strategy(self, strategy_id: str) -> Optional[dict]:
        """Get strategy from Redis."""
        if not self.enabled or not self._client:
            return None
        
        try:
            key = self._key("strategy", strategy_id)
            data = self._client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as exc:
            logger.error(f"Failed to get strategy {strategy_id} from Redis: {exc}")
            return None
    
    def get_all_strategies(self) -> dict[str, dict]:
        """Get all strategies from Redis."""
        if not self.enabled or not self._client:
            return {}
        
        try:
            pattern = self._key("strategy", "*")
            keys = self._client.keys(pattern)
            strategies = {}
            for key in keys:
                strategy_id = key.split(":")[-1]
                data = self._client.get(key)
                if data:
                    strategies[strategy_id] = json.loads(data)
            return strategies
        except Exception as exc:
            logger.error(f"Failed to get all strategies from Redis: {exc}")
            return {}
    
    def delete_strategy(self, strategy_id: str) -> bool:
        """Delete strategy from Redis."""
        if not self.enabled or not self._client:
            return False
        
        try:
            key = self._key("strategy", strategy_id)
            self._client.delete(key)
            # Also delete associated trades
            self.delete_trades(strategy_id)
            return True
        except Exception as exc:
            logger.error(f"Failed to delete strategy {strategy_id} from Redis: {exc}")
            return False
    
    def save_trades(self, strategy_id: str, trades: list[dict]) -> bool:
        """Save trades for a strategy to Redis."""
        if not self.enabled or not self._client:
            return False
        
        try:
            key = self._key("trades", strategy_id)
            serializable_trades = [self._make_serializable(trade) for trade in trades]
            self._client.set(key, json.dumps(serializable_trades))
            return True
        except Exception as exc:
            logger.error(f"Failed to save trades for {strategy_id} to Redis: {exc}")
            return False
    
    def get_trades(self, strategy_id: str) -> list[dict]:
        """Get trades for a strategy from Redis."""
        if not self.enabled or not self._client:
            return []
        
        try:
            key = self._key("trades", strategy_id)
            data = self._client.get(key)
            if data:
                return json.loads(data)
            return []
        except Exception as exc:
            logger.error(f"Failed to get trades for {strategy_id} from Redis: {exc}")
            return []
    
    def delete_trades(self, strategy_id: str) -> bool:
        """Delete trades for a strategy from Redis."""
        if not self.enabled or not self._client:
            return False
        
        try:
            key = self._key("trades", strategy_id)
            self._client.delete(key)
            return True
        except Exception as exc:
            logger.error(f"Failed to delete trades for {strategy_id} from Redis: {exc}")
            return False
    
    def _make_serializable(self, obj: dict) -> dict:
        """Convert non-serializable types to JSON-compatible formats."""
        import datetime
        from decimal import Decimal
        
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif hasattr(obj, 'model_dump'):
            # Pydantic models
            return self._make_serializable(obj.model_dump())
        else:
            return obj

