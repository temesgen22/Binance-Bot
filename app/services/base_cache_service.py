"""
Base service class for cache-aside pattern (PostgreSQL + Redis).
Provides common caching functionality for StrategyService, AccountService, and TradeService.
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from loguru import logger

from app.core.redis_storage import RedisStorage
from app.services.database_service import DatabaseService


class BaseCacheService:
    """Base class for services using cache-aside pattern.
    
    This class provides common functionality for:
    - Redis connection management
    - Cache key generation
    - Cache read/write/invalidate operations
    
    Subclasses should implement:
    - Resource-specific conversion methods
    - Resource-specific business logic
    """
    
    def __init__(self, db: Session, redis_storage: Optional[RedisStorage] = None, cache_ttl: int = 3600):
        """Initialize base cache service.
        
        Args:
            db: Database session
            redis_storage: Optional Redis storage instance
            cache_ttl: Cache TTL in seconds (default: 1 hour)
        """
        self.db_service = DatabaseService(db)
        self.redis = redis_storage
        self._cache_ttl = cache_ttl
    
    def _redis_key(self, user_id: UUID, resource_id: str, prefix: str) -> str:
        """Generate Redis key for a resource with user_id.
        
        Args:
            user_id: User ID
            resource_id: Resource identifier (strategy_id, account_id, etc.)
            prefix: Resource prefix (e.g., "strategy", "account", "trades")
        
        Returns:
            Redis key string
        """
        return f"binance_bot:user:{user_id}:{prefix}:{resource_id}"
    
    def _get_from_cache(self, key: str) -> Optional[dict]:
        """Get data from Redis cache.
        
        Args:
            key: Redis key
        
        Returns:
            Cached data as dict if found, None otherwise
        """
        if not self.redis or not self.redis.enabled:
            return None
        
        try:
            cached = self.redis._client.get(key) if self.redis._client else None
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis cache read error for key {key}: {e}")
        
        return None
    
    def _save_to_cache(self, key: str, data: dict) -> None:
        """Save data to Redis cache.
        
        Args:
            key: Redis key
            data: Data to cache (will be JSON serialized)
        """
        if not self.redis or not self.redis.enabled:
            return
        
        try:
            if self.redis._client:
                self.redis._client.setex(
                    key,
                    self._cache_ttl,
                    json.dumps(data, default=str)
                )
        except Exception as e:
            logger.warning(f"Redis cache write error for key {key}: {e}")
    
    def _invalidate_cache(self, *keys: str) -> None:
        """Invalidate one or more cache keys.
        
        Args:
            *keys: One or more Redis keys to delete
        """
        if not self.redis or not self.redis.enabled:
            return
        
        if not keys:
            return
        
        try:
            if self.redis._client:
                self.redis._client.delete(*keys)
        except Exception as e:
            logger.warning(f"Redis cache delete error for keys {keys}: {e}")

