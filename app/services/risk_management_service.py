"""
Risk management service with cache-aside pattern (PostgreSQL + Redis).
Handles risk management configuration CRUD operations with Redis caching.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timezone
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.core.redis_storage import RedisStorage
from app.services.base_cache_service import BaseCacheService
from app.models.db_models import (
    RiskManagementConfig as DBRiskConfig,
    RiskMetrics as DBRiskMetrics,
    CircuitBreakerEvent as DBCircuitBreakerEvent,
    Account
)
from app.models.risk_management import (
    RiskManagementConfigCreate,
    RiskManagementConfigUpdate,
    RiskManagementConfigResponse,
)


class RiskManagementService(BaseCacheService):
    """Service for managing risk management configuration with database + Redis cache-aside pattern.
    
    Supports both sync (Session) and async (AsyncSession) database operations.
    """
    
    def __init__(self, db: Session | AsyncSession, redis_storage: Optional[RedisStorage] = None):
        super().__init__(db, redis_storage, cache_ttl=3600)  # 1 hour cache
        self._is_async = isinstance(db, AsyncSession)
    
    def _redis_key(self, user_id: UUID, account_id: str) -> str:
        """Generate Redis key for risk config with user_id and account_id."""
        return f"risk_config:{user_id}:{account_id}"
    
    def get_risk_config(
        self, 
        user_id: UUID, 
        account_id: str
    ) -> Optional[RiskManagementConfigResponse]:
        """Get risk management configuration for an account.
        
        Args:
            user_id: User UUID
            account_id: Account ID string
            
        Returns:
            RiskManagementConfigResponse if found, None otherwise
        """
        # Try cache first
        cache_key = self._redis_key(user_id, account_id)
        if self.redis and self.redis.enabled:
            cached = self.redis.get(cache_key)
            if cached:
                try:
                    data = json.loads(cached)
                    logger.debug(f"Cache HIT for risk config: {cache_key}")
                    return RiskManagementConfigResponse(**data)
                except Exception as e:
                    logger.warning(f"Failed to deserialize cached risk config: {e}")
        
        # Cache miss - query database
        logger.debug(f"Cache MISS for risk config: {cache_key}, querying database")
        
        # Get account UUID first
        account = self.db_service.get_account_by_id(user_id, account_id)
        if not account:
            logger.warning(f"Account not found: user_id={user_id}, account_id={account_id}")
            return None
        
        if self._is_async:
            # For async, we need to use asyncio.run or make this method async
            # For now, raise an error - async support should be handled at the API level
            raise RuntimeError("Async get_risk_config not supported. Use async method directly.")
        else:
            return self._get_risk_config_sync(user_id, account.id, account_id, cache_key)
    
    def _get_risk_config_sync(
        self, 
        user_id: UUID, 
        account_uuid: UUID, 
        account_id: str,
        cache_key: str
    ) -> Optional[RiskManagementConfigResponse]:
        """Get risk config (sync version)."""
        db_config = self.db_service.db.query(DBRiskConfig).filter(
            DBRiskConfig.user_id == user_id,
            DBRiskConfig.account_id == account_uuid
        ).first()
        
        if not db_config:
            return None
        
        # Convert to response model
        response = self._db_to_response(db_config, account_id)
        
        # Cache the result
        if self.redis and self.redis.enabled:
            try:
                self.redis.set(cache_key, json.dumps(response.model_dump(), default=str), ex=self.cache_ttl)
            except Exception as e:
                logger.warning(f"Failed to cache risk config: {e}")
        
        return response
    
    async def _get_risk_config_async(
        self, 
        user_id: UUID, 
        account_uuid: UUID, 
        account_id: str,
        cache_key: str
    ) -> Optional[RiskManagementConfigResponse]:
        """Get risk config (async version)."""
        stmt = select(DBRiskConfig).where(
            DBRiskConfig.user_id == user_id,
            DBRiskConfig.account_id == account_uuid
        )
        result = await self.db_service.db.execute(stmt)
        db_config = result.scalar_one_or_none()
        
        if not db_config:
            return None
        
        # Convert to response model
        response = self._db_to_response(db_config, account_id)
        
        # Cache the result
        if self.redis and self.redis.enabled:
            try:
                self.redis.set(cache_key, json.dumps(response.model_dump(), default=str), ex=self.cache_ttl)
            except Exception as e:
                logger.warning(f"Failed to cache risk config: {e}")
        
        return response
    
    def create_risk_config(
        self,
        user_id: UUID,
        config_data: RiskManagementConfigCreate
    ) -> RiskManagementConfigResponse:
        """Create risk management configuration.
        
        Args:
            user_id: User UUID
            config_data: Configuration data
            
        Returns:
            RiskManagementConfigResponse
            
        Raises:
            ValueError: If account not found or config already exists
        """
        # Get account UUID
        account = self.db_service.get_account_by_id(user_id, config_data.account_id)
        if not account:
            raise ValueError(f"Account not found: {config_data.account_id}")
        
        # Check if config already exists
        existing = self.get_risk_config(user_id, config_data.account_id)
        if existing:
            raise ValueError(f"Risk config already exists for account: {config_data.account_id}")
        
        # Create new config
        db_config = DBRiskConfig(
            id=uuid4(),
            user_id=user_id,
            account_id=account.id,
            **config_data.model_dump(exclude={"account_id"})
        )
        
        if self._is_async:
            # For async, we need to use asyncio.run or make this method async
            # For now, raise an error - async support should be handled at the API level
            raise RuntimeError("Async create_risk_config not supported. Use async method directly.")
        else:
            return self._create_risk_config_sync(db_config, config_data.account_id)
    
    def _create_risk_config_sync(
        self,
        db_config: DBRiskConfig,
        account_id: str
    ) -> RiskManagementConfigResponse:
        """Create risk config (sync version)."""
        self.db_service.db.add(db_config)
        self.db_service.db.commit()
        self.db_service.db.refresh(db_config)
        
        # Invalidate cache
        cache_key = self._redis_key(db_config.user_id, account_id)
        if self.redis and self.redis.enabled:
            self.redis.delete(cache_key)
        
        return self._db_to_response(db_config, account_id)
    
    async def _create_risk_config_async(
        self,
        db_config: DBRiskConfig,
        account_id: str
    ) -> RiskManagementConfigResponse:
        """Create risk config (async version)."""
        self.db_service.db.add(db_config)
        await self.db_service.db.commit()
        await self.db_service.db.refresh(db_config)
        
        # Invalidate cache
        cache_key = self._redis_key(db_config.user_id, account_id)
        if self.redis and self.redis.enabled:
            self.redis.delete(cache_key)
        
        return self._db_to_response(db_config, account_id)
    
    def update_risk_config(
        self,
        user_id: UUID,
        account_id: str,
        config_data: RiskManagementConfigUpdate
    ) -> Optional[RiskManagementConfigResponse]:
        """Update risk management configuration.
        
        Args:
            user_id: User UUID
            account_id: Account ID string
            config_data: Update data (only provided fields will be updated)
            
        Returns:
            Updated RiskManagementConfigResponse if found, None otherwise
        """
        # Get account UUID
        account = self.db_service.get_account_by_id(user_id, account_id)
        if not account:
            return None
        
        if self._is_async:
            # For async, we need to use asyncio.run or make this method async
            # For now, raise an error - async support should be handled at the API level
            raise RuntimeError("Async update_risk_config not supported. Use async method directly.")
        else:
            return self._update_risk_config_sync(user_id, account.id, account_id, config_data)
    
    def _update_risk_config_sync(
        self,
        user_id: UUID,
        account_uuid: UUID,
        account_id: str,
        config_data: RiskManagementConfigUpdate
    ) -> Optional[RiskManagementConfigResponse]:
        """Update risk config (sync version)."""
        db_config = self.db_service.db.query(DBRiskConfig).filter(
            DBRiskConfig.user_id == user_id,
            DBRiskConfig.account_id == account_uuid
        ).first()
        
        if not db_config:
            return None
        
        # Update fields (only non-None values)
        update_data = config_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(db_config, key):
                setattr(db_config, key, value)
        
        db_config.updated_at = datetime.now(timezone.utc)
        self.db_service.db.commit()
        self.db_service.db.refresh(db_config)
        
        # Invalidate cache
        cache_key = self._redis_key(user_id, account_id)
        if self.redis and self.redis.enabled:
            self.redis.delete(cache_key)
        
        return self._db_to_response(db_config, account_id)
    
    async def _update_risk_config_async(
        self,
        user_id: UUID,
        account_uuid: UUID,
        account_id: str,
        config_data: RiskManagementConfigUpdate
    ) -> Optional[RiskManagementConfigResponse]:
        """Update risk config (async version)."""
        stmt = select(DBRiskConfig).where(
            DBRiskConfig.user_id == user_id,
            DBRiskConfig.account_id == account_uuid
        )
        result = await self.db_service.db.execute(stmt)
        db_config = result.scalar_one_or_none()
        
        if not db_config:
            return None
        
        # Update fields (only non-None values)
        update_data = config_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(db_config, key):
                setattr(db_config, key, value)
        
        db_config.updated_at = datetime.now(timezone.utc)
        await self.db_service.db.commit()
        await self.db_service.db.refresh(db_config)
        
        # Invalidate cache
        cache_key = self._redis_key(user_id, account_id)
        if self.redis and self.redis.enabled:
            self.redis.delete(cache_key)
        
        return self._db_to_response(db_config, account_id)
    
    def delete_risk_config(
        self,
        user_id: UUID,
        account_id: str
    ) -> bool:
        """Delete risk management configuration.
        
        Args:
            user_id: User UUID
            account_id: Account ID string
            
        Returns:
            True if deleted, False if not found
        """
        # Get account UUID
        account = self.db_service.get_account_by_id(user_id, account_id)
        if not account:
            return False
        
        if self._is_async:
            # For async, we need to use asyncio.run or make this method async
            # For now, raise an error - async support should be handled at the API level
            raise RuntimeError("Async delete_risk_config not supported. Use async method directly.")
        else:
            return self._delete_risk_config_sync(user_id, account.id, account_id)
    
    def _delete_risk_config_sync(
        self,
        user_id: UUID,
        account_uuid: UUID,
        account_id: str
    ) -> bool:
        """Delete risk config (sync version)."""
        db_config = self.db_service.db.query(DBRiskConfig).filter(
            DBRiskConfig.user_id == user_id,
            DBRiskConfig.account_id == account_uuid
        ).first()
        
        if not db_config:
            return False
        
        self.db_service.db.delete(db_config)
        self.db_service.db.commit()
        
        # Invalidate cache
        cache_key = self._redis_key(user_id, account_id)
        if self.redis and self.redis.enabled:
            self.redis.delete(cache_key)
        
        return True
    
    async def _delete_risk_config_async(
        self,
        user_id: UUID,
        account_uuid: UUID,
        account_id: str
    ) -> bool:
        """Delete risk config (async version)."""
        stmt = select(DBRiskConfig).where(
            DBRiskConfig.user_id == user_id,
            DBRiskConfig.account_id == account_uuid
        )
        result = await self.db_service.db.execute(stmt)
        db_config = result.scalar_one_or_none()
        
        if not db_config:
            return False
        
        await self.db_service.db.delete(db_config)
        await self.db_service.db.commit()
        
        # Invalidate cache
        cache_key = self._redis_key(user_id, account_id)
        if self.redis and self.redis.enabled:
            self.redis.delete(cache_key)
        
        return True
    
    def _db_to_response(
        self,
        db_config: DBRiskConfig,
        account_id: str
    ) -> RiskManagementConfigResponse:
        """Convert database model to response model."""
        # Convert daily_loss_reset_time from datetime to time if needed
        daily_reset_time = None
        if db_config.daily_loss_reset_time:
            if isinstance(db_config.daily_loss_reset_time, datetime):
                daily_reset_time = db_config.daily_loss_reset_time.time()
            elif isinstance(db_config.daily_loss_reset_time, time):
                daily_reset_time = db_config.daily_loss_reset_time
        
        return RiskManagementConfigResponse(
            id=str(db_config.id),
            user_id=str(db_config.user_id),
            account_id=account_id,
            max_portfolio_exposure_usdt=float(db_config.max_portfolio_exposure_usdt) if db_config.max_portfolio_exposure_usdt else None,
            max_portfolio_exposure_pct=float(db_config.max_portfolio_exposure_pct) if db_config.max_portfolio_exposure_pct else None,
            max_daily_loss_usdt=float(db_config.max_daily_loss_usdt) if db_config.max_daily_loss_usdt else None,
            max_daily_loss_pct=float(db_config.max_daily_loss_pct) if db_config.max_daily_loss_pct else None,
            max_weekly_loss_usdt=float(db_config.max_weekly_loss_usdt) if db_config.max_weekly_loss_usdt else None,
            max_weekly_loss_pct=float(db_config.max_weekly_loss_pct) if db_config.max_weekly_loss_pct else None,
            max_drawdown_pct=float(db_config.max_drawdown_pct) if db_config.max_drawdown_pct else None,
            daily_loss_reset_time=daily_reset_time,
            weekly_loss_reset_day=db_config.weekly_loss_reset_day,
            timezone=db_config.timezone,
            circuit_breaker_enabled=db_config.circuit_breaker_enabled,
            max_consecutive_losses=db_config.max_consecutive_losses,
            rapid_loss_threshold_pct=float(db_config.rapid_loss_threshold_pct),
            rapid_loss_timeframe_minutes=db_config.rapid_loss_timeframe_minutes,
            circuit_breaker_cooldown_minutes=db_config.circuit_breaker_cooldown_minutes,
            volatility_based_sizing_enabled=db_config.volatility_based_sizing_enabled,
            performance_based_adjustment_enabled=db_config.performance_based_adjustment_enabled,
            kelly_criterion_enabled=db_config.kelly_criterion_enabled,
            kelly_fraction=float(db_config.kelly_fraction),
            correlation_limits_enabled=db_config.correlation_limits_enabled,
            max_correlation_exposure_pct=float(db_config.max_correlation_exposure_pct),
            margin_call_protection_enabled=db_config.margin_call_protection_enabled,
            min_margin_ratio=float(db_config.min_margin_ratio),
            max_trades_per_day_per_strategy=db_config.max_trades_per_day_per_strategy,
            max_trades_per_day_total=db_config.max_trades_per_day_total,
            auto_reduce_order_size=db_config.auto_reduce_order_size,
            created_at=db_config.created_at,
            updated_at=db_config.updated_at,
        )

