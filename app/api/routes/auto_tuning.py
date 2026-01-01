"""
Auto-Tuning API endpoints for strategy parameter auto-tuning.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

from app.api.deps import (
    get_binance_client, 
    get_current_user_async, 
    get_async_db,
    get_strategy_runner
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.my_binance_client import BinanceClient
from app.services.auto_tuning_service import (
    AutoTuningService,
    AutoTuningConfig,
    PerformanceSnapshot
)
from app.services.auto_tuning_evaluator import AutoTuningEvaluator
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_service import StrategyService
from app.services.strategy_statistics import StrategyStatistics
from app.services.database_service import DatabaseService
from app.models.db_models import User

router = APIRouter(prefix="/auto-tuning", tags=["auto-tuning"])


# ============================================================================
# Request/Response Models
# ============================================================================

class EnableAutoTuningRequest(BaseModel):
    """Request to enable auto-tuning for a strategy."""
    config: AutoTuningConfig


class TuningStatusResponse(BaseModel):
    """Response with auto-tuning status."""
    strategy_id: str
    enabled: bool
    config: Optional[AutoTuningConfig] = None
    last_tuning_time: Optional[datetime] = None
    last_tuning_result: Optional[dict] = None


class TuningHistoryItem(BaseModel):
    """Single parameter change history item."""
    id: UUID
    strategy_uuid: UUID
    old_params: dict
    new_params: dict
    changed_params: dict
    reason: Optional[str]
    status: str
    created_at: datetime
    performance_before: Optional[dict] = None
    performance_after: Optional[dict] = None


# ============================================================================
# Dependency Injection
# ============================================================================

def get_auto_tuning_service(
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
    client: BinanceClient = Depends(get_binance_client),
    runner: StrategyRunner = Depends(get_strategy_runner),
) -> AutoTuningService:
    """Get AutoTuningService instance."""
    from app.core.redis_storage import RedisStorage
    from app.core.config import get_settings
    
    # Get services from runner and database
    db_service = DatabaseService(db)
    
    # Always create a new StrategyService with AsyncSession to ensure async compatibility
    # Don't use runner.strategy_service as it might be sync
    settings = get_settings()
    redis_storage = None
    if settings.redis_enabled:
        redis_storage = RedisStorage(
            redis_url=settings.redis_url,
            enabled=settings.redis_enabled
        )
    strategy_service = StrategyService(db, redis_storage)
    
    # Create StrategyStatistics from runner
    strategy_statistics = StrategyStatistics(
        strategies=runner._strategies,
        trades=runner._trades,
        redis_storage=runner.redis if hasattr(runner, 'redis') else None
    )
    
    return AutoTuningService(
        strategy_runner=runner,
        strategy_service=strategy_service,
        strategy_statistics=strategy_statistics,
        db_service=db_service,
        client=client,
        user_id=current_user.id
    )


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/strategies/{strategy_id}/enable")
async def enable_auto_tuning(
    strategy_id: str,
    request: EnableAutoTuningRequest,
    current_user: User = Depends(get_current_user_async),
    auto_tuning_service: AutoTuningService = Depends(get_auto_tuning_service)
) -> dict:
    """Enable auto-tuning for a strategy.
    
    Args:
        strategy_id: User's strategy identifier (string)
        request: EnableAutoTuningRequest with configuration
        current_user: Current authenticated user
        auto_tuning_service: AutoTuningService instance
        
    Returns:
        Success message
    """
    try:
        # Update strategy with auto-tuning config
        # StrategyService created with AsyncSession, so use async method
        strategy = await auto_tuning_service.strategy_service.async_get_strategy(
            current_user.id, strategy_id
        )
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        # Update strategy meta with config
        meta = strategy.meta or {}
        meta['auto_tuning_config'] = request.config.model_dump()
        
        # Update strategy using async database operations
        from app.models.db_models import Strategy as DBStrategy
        from sqlalchemy import select, update
        
        db = auto_tuning_service.db_service.db
        if not isinstance(db, AsyncSession):
            raise RuntimeError("Database session must be AsyncSession")
        
        # Get strategy
        result = await db.execute(
            select(DBStrategy).filter(
                DBStrategy.user_id == current_user.id,
                DBStrategy.strategy_id == strategy_id
            )
        )
        db_strategy = result.scalar_one_or_none()
        
        if not db_strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        # Update fields
        db_strategy.auto_tuning_enabled = True
        db_strategy.meta = meta
        
        # Commit
        await db.commit()
        await db.refresh(db_strategy)
        
        # Invalidate cache
        strategy_service = auto_tuning_service.strategy_service
        if strategy_service.redis and strategy_service.redis.enabled:
            key = strategy_service._redis_key(current_user.id, strategy_id)
            await asyncio.to_thread(strategy_service._invalidate_cache, key)
        
        return {
            "status": "success",
            "message": f"Auto-tuning enabled for strategy {strategy_id}",
            "config": request.config.model_dump()
        }
        
    except Exception as e:
        logger.error(f"Error enabling auto-tuning for {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable auto-tuning: {str(e)}"
        )


@router.post("/strategies/{strategy_id}/disable")
async def disable_auto_tuning(
    strategy_id: str,
    current_user: User = Depends(get_current_user_async),
    auto_tuning_service: AutoTuningService = Depends(get_auto_tuning_service)
) -> dict:
    """Disable auto-tuning for a strategy.
    
    Args:
        strategy_id: User's strategy identifier (string)
        current_user: Current authenticated user
        auto_tuning_service: AutoTuningService instance
        
    Returns:
        Success message
    """
    try:
        # Update strategy using async database operations
        from app.models.db_models import Strategy as DBStrategy
        from sqlalchemy import select
        
        db = auto_tuning_service.db_service.db
        if not isinstance(db, AsyncSession):
            raise RuntimeError("Database session must be AsyncSession")
        
        # Get strategy
        result = await db.execute(
            select(DBStrategy).filter(
                DBStrategy.user_id == current_user.id,
                DBStrategy.strategy_id == strategy_id
            )
        )
        db_strategy = result.scalar_one_or_none()
        
        if not db_strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        # Update field
        db_strategy.auto_tuning_enabled = False
        
        # Commit
        await db.commit()
        await db.refresh(db_strategy)
        
        # Invalidate cache
        strategy_service = auto_tuning_service.strategy_service
        if strategy_service.redis and strategy_service.redis.enabled:
            key = strategy_service._redis_key(current_user.id, strategy_id)
            await asyncio.to_thread(strategy_service._invalidate_cache, key)
        
        return {
            "status": "success",
            "message": f"Auto-tuning disabled for strategy {strategy_id}"
        }
        
    except Exception as e:
        logger.error(f"Error disabling auto-tuning for {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable auto-tuning: {str(e)}"
        )


@router.post("/strategies/{strategy_id}/tune-now")
async def trigger_tuning_now(
    strategy_id: str,
    current_user: User = Depends(get_current_user_async),
    auto_tuning_service: AutoTuningService = Depends(get_auto_tuning_service)
) -> dict:
    """Manually trigger tuning for a strategy.
    
    Args:
        strategy_id: User's strategy identifier (string)
        current_user: Current authenticated user
        auto_tuning_service: AutoTuningService instance
        
    Returns:
        Tuning results
    """
    try:
        result = await auto_tuning_service.tune_strategy(strategy_id)
        return result
        
    except Exception as e:
        logger.error(f"Error triggering tuning for {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger tuning: {str(e)}"
        )


@router.get("/strategies/{strategy_id}/status")
async def get_tuning_status(
    strategy_id: str,
    current_user: User = Depends(get_current_user_async),
    auto_tuning_service: AutoTuningService = Depends(get_auto_tuning_service)
) -> TuningStatusResponse:
    """Get auto-tuning status and history.
    
    Args:
        strategy_id: User's strategy identifier (string)
        current_user: Current authenticated user
        auto_tuning_service: AutoTuningService instance
        
    Returns:
        TuningStatusResponse
    """
    try:
        # Get strategy - this may come from cache or database
        strategy = await auto_tuning_service.strategy_service.async_get_strategy(
            current_user.id, strategy_id
        )
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        # Get auto_tuning_enabled - should be in strategy object now (we fixed cache serialization)
        auto_tuning_enabled = getattr(strategy, 'auto_tuning_enabled', False)
        
        # Parse config from meta
        config = None
        if hasattr(strategy, 'meta') and strategy.meta and isinstance(strategy.meta, dict):
            if 'auto_tuning_config' in strategy.meta:
                try:
                    config = AutoTuningConfig(**strategy.meta['auto_tuning_config'])
                except Exception as e:
                    logger.warning(f"Failed to parse auto_tuning_config: {e}")
        
        # TODO: Get last tuning time and result from database
        last_tuning_time = None
        last_tuning_result = None
        
        return TuningStatusResponse(
            strategy_id=strategy_id,
            enabled=auto_tuning_enabled,
            config=config,
            last_tuning_time=last_tuning_time,
            last_tuning_result=last_tuning_result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tuning status for {strategy_id}: {e}", exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tuning status: {str(e)}"
        )


@router.get("/strategies/{strategy_id}/history")
async def get_tuning_history(
    strategy_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user_async),
    auto_tuning_service: AutoTuningService = Depends(get_auto_tuning_service)
) -> dict:
    """Get parameter change history.
    
    Args:
        strategy_id: User's strategy identifier (string)
        limit: Maximum number of records to return
        offset: Number of records to skip
        current_user: Current authenticated user
        auto_tuning_service: AutoTuningService instance
        
    Returns:
        Dictionary with history items and pagination info
    """
    try:
        # Resolve UUID
        strategy_uuid = await auto_tuning_service._resolve_strategy_uuid(strategy_id)
        
        # Query database for parameter history
        history_records, total = await auto_tuning_service.db_service.async_list_parameter_history(
            strategy_uuid=strategy_uuid,
            user_id=current_user.id,
            limit=limit,
            offset=offset
        )
        
        # Convert to response format
        history_items = [
            {
                "id": str(record.id),
                "strategy_uuid": str(record.strategy_uuid),
                "old_params": record.old_params,
                "new_params": record.new_params,
                "changed_params": record.changed_params,
                "reason": record.reason,
                "status": record.status,
                "created_at": record.created_at.isoformat(),
                "performance_before": record.performance_before,
                "performance_after": record.performance_after,
                "failure_reason": record.failure_reason
            }
            for record in history_records
        ]
        
        return {
            "strategy_id": strategy_id,
            "history": history_items,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Error getting tuning history for {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tuning history: {str(e)}"
        )


@router.post("/strategies/{strategy_id}/evaluate")
async def evaluate_strategy_performance(
    strategy_id: str,
    force: bool = False,
    current_user: User = Depends(get_current_user_async),
    auto_tuning_service: AutoTuningService = Depends(get_auto_tuning_service),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """Manually trigger performance evaluation for a strategy.
    
    Args:
        strategy_id: User's strategy identifier (string)
        force: If True, evaluate even if hold period hasn't elapsed
        current_user: Current authenticated user
        auto_tuning_service: AutoTuningService instance
        db: Database session
        
    Returns:
        Evaluation result
    """
    try:
        # Resolve UUID
        strategy_uuid = await auto_tuning_service._resolve_strategy_uuid(strategy_id)
        
        # Create evaluator
        evaluator = AutoTuningEvaluator(
            auto_tuning_service=auto_tuning_service,
            db_service=auto_tuning_service.db_service
        )
        
        # Evaluate
        result = await evaluator.evaluate_strategy(
            strategy_uuid=strategy_uuid,
            force=force
        )
        
        if result is None:
            return {
                "status": "no_records",
                "message": "No parameter changes found to evaluate"
            }
        
        return {
            "status": "success",
            "strategy_id": strategy_id,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error evaluating strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate strategy: {str(e)}"
        )


@router.post("/evaluate-all")
async def evaluate_all_pending(
    current_user: User = Depends(get_current_user_async),
    auto_tuning_service: AutoTuningService = Depends(get_auto_tuning_service),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """Manually trigger evaluation of all pending records.
    
    Args:
        current_user: Current authenticated user
        auto_tuning_service: AutoTuningService instance
        db: Database session
        
    Returns:
        Evaluation summary
    """
    try:
        # Create evaluator
        evaluator = AutoTuningEvaluator(
            auto_tuning_service=auto_tuning_service,
            db_service=auto_tuning_service.db_service
        )
        
        # Evaluate all pending
        count = await evaluator.evaluate_pending_records()
        
        return {
            "status": "success",
            "evaluated_count": count,
            "message": f"Evaluated {count} parameter history records"
        }
        
    except Exception as e:
        logger.error(f"Error evaluating all pending records: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate pending records: {str(e)}"
        )

