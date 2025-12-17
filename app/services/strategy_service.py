"""
Strategy service with cache-aside pattern (PostgreSQL + Redis).
Handles strategy CRUD operations with Redis caching.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from loguru import logger

from app.core.redis_storage import RedisStorage
from app.services.base_cache_service import BaseCacheService
from app.models.strategy import StrategySummary, StrategyState, StrategyType
from app.models.db_models import Strategy as DBStrategy


class StrategyService(BaseCacheService):
    """Service for managing strategies with database + Redis cache-aside pattern."""
    
    def __init__(self, db: Session, redis_storage: Optional[RedisStorage] = None):
        super().__init__(db, redis_storage, cache_ttl=3600)
    
    def _redis_key(self, user_id: UUID, strategy_id: str) -> str:
        """Generate Redis key for strategy with user_id."""
        return super()._redis_key(user_id, strategy_id, "strategy")
    
    def _redis_state_key(self, user_id: UUID, strategy_id: str) -> str:
        """Generate Redis key for strategy runtime state."""
        return f"binance_bot:user:{user_id}:state:strategy:{strategy_id}"
    
    def _strategy_summary_to_dict(self, summary: StrategySummary) -> dict:
        """Convert StrategySummary to dictionary for Redis storage."""
        return {
            "id": summary.id,
            "name": summary.name,
            "symbol": summary.symbol,
            "strategy_type": summary.strategy_type.value if isinstance(summary.strategy_type, StrategyType) else summary.strategy_type,
            "status": summary.status.value if isinstance(summary.status, StrategyState) else summary.status,
            "leverage": summary.leverage,
            "risk_per_trade": float(summary.risk_per_trade) if summary.risk_per_trade else None,
            "fixed_amount": float(summary.fixed_amount) if summary.fixed_amount else None,
            "params": summary.params.model_dump() if hasattr(summary.params, 'model_dump') else summary.params,
            "created_at": summary.created_at.isoformat() if summary.created_at else None,
            "account_id": summary.account_id,
            "last_signal": summary.last_signal,
            "entry_price": float(summary.entry_price) if summary.entry_price else None,
            "current_price": float(summary.current_price) if summary.current_price else None,
            "position_size": float(summary.position_size) if summary.position_size else None,
            "position_side": summary.position_side,
            "unrealized_pnl": float(summary.unrealized_pnl) if summary.unrealized_pnl else None,
            "meta": summary.meta or {},
        }
    
    def _dict_to_strategy_summary(self, data: dict) -> StrategySummary:
        """Convert dictionary to StrategySummary."""
        from app.models.strategy import StrategyParams
        
        # Parse params
        params_dict = data.get("params", {})
        if isinstance(params_dict, dict):
            params = StrategyParams(**params_dict)
        else:
            params = params_dict
        
        return StrategySummary(
            id=data["id"],
            name=data["name"],
            symbol=data["symbol"],
            strategy_type=StrategyType(data["strategy_type"]),
            status=StrategyState(data["status"]),
            leverage=data["leverage"],
            risk_per_trade=data.get("risk_per_trade"),
            fixed_amount=data.get("fixed_amount"),
            params=params,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            account_id=data.get("account_id", "default"),
            last_signal=data.get("last_signal"),
            entry_price=data.get("entry_price"),
            current_price=data.get("current_price"),
            position_size=data.get("position_size"),
            position_side=data.get("position_side"),
            unrealized_pnl=data.get("unrealized_pnl"),
            meta=data.get("meta", {}),
        )
    
    def _db_strategy_to_summary(self, db_strategy: DBStrategy) -> StrategySummary:
        """Convert database Strategy model to StrategySummary."""
        from app.models.strategy import StrategyParams
        
        # Parse params from JSONB
        params_dict = db_strategy.params if isinstance(db_strategy.params, dict) else {}
        params = StrategyParams(**params_dict)
        
        # Get account's string identifier (account_id) from the account UUID
        # The database stores account_id as UUID, but we need the string identifier
        account_id_str = "default"  # Default fallback
        if db_strategy.account_id:
            # Look up the account to get its string identifier
            # Use the relationship if available, otherwise query
            if hasattr(db_strategy, 'account') and db_strategy.account:
                account_id_str = db_strategy.account.account_id  # This is the string identifier
            else:
                # Fallback: query the account
                from app.models.db_models import Account
                account = self.db_service.db.query(Account).filter(Account.id == db_strategy.account_id).first()
                if account:
                    account_id_str = account.account_id
                else:
                    # Last fallback: use UUID as string if account not found
                    account_id_str = str(db_strategy.account_id)
        
        return StrategySummary(
            id=db_strategy.strategy_id,  # Use strategy_id (string identifier) not id (database UUID)
            name=db_strategy.name,
            symbol=db_strategy.symbol,
            strategy_type=StrategyType(db_strategy.strategy_type),
            status=StrategyState(db_strategy.status),
            leverage=db_strategy.leverage,
            risk_per_trade=float(db_strategy.risk_per_trade),
            fixed_amount=float(db_strategy.fixed_amount) if db_strategy.fixed_amount else None,
            params=params,
            created_at=db_strategy.created_at,
            account_id=account_id_str,
            last_signal=db_strategy.last_signal,
            entry_price=float(db_strategy.entry_price) if db_strategy.entry_price else None,
            current_price=float(db_strategy.current_price) if db_strategy.current_price else None,
            position_size=float(db_strategy.position_size) if db_strategy.position_size else None,
            position_side=db_strategy.position_side,
            unrealized_pnl=float(db_strategy.unrealized_pnl) if db_strategy.unrealized_pnl else None,
            meta=db_strategy.meta or {},
        )
    
    def get_strategy(
        self,
        user_id: UUID,
        strategy_id: str
    ) -> Optional[StrategySummary]:
        """Get strategy using cache-aside pattern.
        
        1. Check Redis cache
        2. If not found, check database
        3. Cache the result in Redis
        """
        key = self._redis_key(user_id, strategy_id)
        
        # Try Redis first
        cached_data = self._get_from_cache(key)
        if cached_data:
            logger.debug(f"Cache HIT for strategy {strategy_id}")
            return self._dict_to_strategy_summary(cached_data)
        
        # Cache miss - check database
        logger.debug(f"Cache MISS for strategy {strategy_id}, checking database")
        db_strategy = self.db_service.get_strategy(user_id, strategy_id)
        
        if not db_strategy:
            return None
        
        # Convert to summary
        summary = self._db_strategy_to_summary(db_strategy)
        
        # Cache in Redis
        data = self._strategy_summary_to_dict(summary)
        self._save_to_cache(key, data)
        
        return summary
    
    def list_strategies(self, user_id: UUID) -> list[StrategySummary]:
        """List all strategies for a user."""
        db_strategies = self.db_service.get_user_strategies(user_id)
        summaries = [self._db_strategy_to_summary(s) for s in db_strategies]
        return summaries
    
    def create_strategy(
        self,
        user_id: UUID,
        strategy_id: str,
        name: str,
        symbol: str,
        strategy_type: str,
        account_id: UUID,
        leverage: int,
        risk_per_trade: float,
        params: dict,
        fixed_amount: Optional[float] = None,
        max_positions: int = 1
    ) -> StrategySummary:
        """Create a new strategy in database and cache."""
        # Create in database
        db_strategy = self.db_service.create_strategy(
            user_id=user_id,
            strategy_id=strategy_id,
            name=name,
            symbol=symbol,
            strategy_type=strategy_type,
            account_id=account_id,
            leverage=leverage,
            risk_per_trade=risk_per_trade,
            params=params,
            fixed_amount=fixed_amount,
            max_positions=max_positions
        )
        
        # Convert to summary
        summary = self._db_strategy_to_summary(db_strategy)
        
        # Cache in Redis
        key = self._redis_key(user_id, strategy_id)
        data = self._strategy_summary_to_dict(summary)
        self._save_to_cache(key, data)
        
        return summary
    
    def update_strategy(
        self,
        user_id: UUID,
        strategy_id: str,
        **updates
    ) -> Optional[StrategySummary]:
        """Update strategy in database and invalidate cache."""
        # Update in database
        db_strategy = self.db_service.update_strategy(user_id, strategy_id, **updates)
        
        if not db_strategy:
            return None
        
        # Convert to summary
        summary = self._db_strategy_to_summary(db_strategy)
        
        # Invalidate cache (will be refreshed on next read)
        key = self._redis_key(user_id, strategy_id)
        self._invalidate_cache(key)
        
        return summary
    
    def update_strategy_runtime_state(
        self,
        user_id: UUID,
        strategy_id: str,
        **state_updates
    ) -> None:
        """Update strategy runtime state (Redis only, not database).
        
        Runtime state includes:
        - entry_price, current_price, position_size, position_side
        - unrealized_pnl, last_signal
        - cooldown_left, prev_fast_ema, prev_slow_ema, last_kline_open_time
        """
        if not self.redis or not self.redis.enabled:
            return
        
        try:
            state_key = self._redis_state_key(user_id, strategy_id)
            if self.redis._client:
                # Use Redis hash for partial updates
                updates = {k: str(v) if v is not None else "" for k, v in state_updates.items()}
                self.redis._client.hset(state_key, mapping=updates)
                self.redis._client.expire(state_key, self._cache_ttl)
        except Exception as e:
            logger.warning(f"Redis state update error for strategy {strategy_id}: {e}")
    
    def get_strategy_runtime_state(
        self,
        user_id: UUID,
        strategy_id: str
    ) -> dict:
        """Get strategy runtime state from Redis."""
        if not self.redis or not self.redis.enabled:
            return {}
        
        try:
            state_key = self._redis_state_key(user_id, strategy_id)
            if self.redis._client:
                state = self.redis._client.hgetall(state_key)
                # Convert string values back to appropriate types
                result = {}
                for k, v in state.items():
                    if v == "":
                        result[k] = None
                    elif k in ["entry_price", "current_price", "position_size", "unrealized_pnl"]:
                        try:
                            result[k] = float(v) if v else None
                        except (ValueError, TypeError):
                            result[k] = None
                    elif k in ["cooldown_left"]:
                        try:
                            result[k] = float(v) if v else None
                        except (ValueError, TypeError):
                            result[k] = None
                    else:
                        result[k] = v
                return result
        except Exception as e:
            logger.warning(f"Redis state read error for strategy {strategy_id}: {e}")
        
        return {}
    
    def delete_strategy(self, user_id: UUID, strategy_id: str) -> bool:
        """Delete strategy from database and cache."""
        # Delete from database
        success = self.db_service.delete_strategy(user_id, strategy_id)
        
        if success:
            # Delete from cache
            key = self._redis_key(user_id, strategy_id)
            state_key = self._redis_state_key(user_id, strategy_id)
            self._invalidate_cache(key, state_key)
        
        return success

