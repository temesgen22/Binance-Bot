from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from uuid import UUID

from loguru import logger

from app.api.deps import (
    get_strategy_runner, get_current_user, get_current_user_async,
    get_database_service, get_database_service_async,
    get_db_session_dependency, get_async_db
)
from app.models.order import OrderResponse
from app.models.strategy import CreateStrategyRequest, StrategySummary, StrategyStats, OverallStats
from app.models.db_models import User
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_service import StrategyService
from app.core.redis_storage import RedisStorage
from app.core.config import get_settings
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import (
    StrategyNotFoundError,
    StrategyAlreadyRunningError,
    MaxConcurrentStrategiesError,
    InvalidLeverageError,
    PositionSizingError,
    OrderExecutionError,
    BinanceAPIError,
)


router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("/list", response_model=list[StrategySummary])
async def list_strategies(
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
    runner: StrategyRunner = Depends(get_strategy_runner)
) -> list[StrategySummary]:
    """List all registered strategies for the current user.
    
    Note: Changed from GET / to GET /list to avoid conflict with GUI route at /strategies
    
    Strategies are automatically restored on server startup via lifespan events.
    This endpoint returns all strategies currently in memory.
    """
    # If runner has StrategyService, it will automatically filter by user_id
    # Otherwise, return all strategies (backward compatibility)
    return runner.list_strategies()


@router.get("/{strategy_id}", response_model=StrategySummary)
async def get_strategy(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategySummary:
    """Get details of a specific strategy by ID.
    
    Raises:
        StrategyNotFoundError: If strategy does not exist
    """
    strategies = runner.list_strategies()
    for strategy in strategies:
        if strategy.id == strategy_id:
            return strategy
    raise StrategyNotFoundError(strategy_id)


@router.post("/", response_model=StrategySummary, status_code=status.HTTP_201_CREATED)
async def register_strategy(
    payload: CreateStrategyRequest,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
    runner: StrategyRunner = Depends(get_strategy_runner)
) -> StrategySummary:
    """Register a new trading strategy.
    
    Raises:
        InvalidLeverageError: If leverage is invalid or not provided
        ValidationError: If request data is invalid
    """
    # Restore running strategies if needed (lazy restoration)
    if hasattr(runner, '_needs_restore') and runner._needs_restore:
        try:
            await runner.restore_running_strategies()
            runner._needs_restore = False
        except Exception as exc:
            logger.warning(f"Failed to restore running strategies for user {current_user.id}: {exc}")
    
    try:
        # Get account UUID from account_id
        account_id = payload.account_id.lower() if payload.account_id else "default"
        db_service = await get_database_service_async(db)
        
        # Find account in database (async)
        account_uuid = None
        if runner.strategy_service and runner.user_id:
            # Multi-user mode: get account from database
            accounts = await db_service.async_get_user_accounts(current_user.id)
            account = next((acc for acc in accounts if acc.account_id == account_id), None)
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Account '{account_id}' not found for user"
                )
            account_uuid = account.id
        
        summary = runner.register(payload, account_uuid=account_uuid)
        if payload.auto_start:
            await runner.start(summary.id)
        return summary
    except (InvalidLeverageError, ValidationError):
        # These will be handled by exception handlers
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Unexpected error registering strategy: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register strategy: {exc}"
        ) from exc


@router.post("/{strategy_id}/start", response_model=StrategySummary)
async def start_strategy(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategySummary:
    """Start a trading strategy.
    
    Raises:
        StrategyNotFoundError: If strategy does not exist
        StrategyAlreadyRunningError: If strategy is already running
        MaxConcurrentStrategiesError: If maximum concurrent strategies limit is reached
    """
    # Custom exceptions will be handled by exception handlers
    return await runner.start(strategy_id)


@router.post("/{strategy_id}/stop", response_model=StrategySummary)
async def stop_strategy(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategySummary:
    """Stop a trading strategy and close any open positions.
    
    Raises:
        StrategyNotFoundError: If strategy does not exist
    """
    # Custom exceptions will be handled by exception handlers
    return await runner.stop(strategy_id)


@router.get("/{strategy_id}/trades", response_model=list[OrderResponse])
async def get_strategy_trades(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> list[OrderResponse]:
    """Get all executed trades for a specific strategy.
    
    Raises:
        StrategyNotFoundError: If strategy does not exist
    """
    # Verify strategy exists
    strategies = runner.list_strategies()
    if not any(s.id == strategy_id for s in strategies):
        raise StrategyNotFoundError(strategy_id)
    return runner.get_trades(strategy_id)


@router.get("/{strategy_id}/stats", response_model=StrategyStats)
def get_strategy_stats(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategyStats:
    """Get statistics for a specific strategy including trade count and PnL.
    
    Raises:
        StrategyNotFoundError: If strategy does not exist
    """
    return runner.calculate_strategy_stats(strategy_id)


@router.get("/stats", response_model=OverallStats)
def get_overall_stats(runner: StrategyRunner = Depends(get_strategy_runner)) -> OverallStats:
    """Get overall statistics across all strategies."""
    return runner.calculate_overall_stats()


@router.get("/{strategy_id}/activity", response_model=list[dict])
async def get_strategy_activity(
    strategy_id: str,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
    runner: StrategyRunner = Depends(get_strategy_runner),
    limit: int = 50
) -> list[dict]:
    """Get activity history for a strategy (start/stop events).
    
    Returns a list of activity events ordered by most recent first.
    
    Raises:
        StrategyNotFoundError: If strategy does not exist
    """
    # Verify strategy exists
    strategies = runner.list_strategies()
    if not any(s.id == strategy_id for s in strategies):
        raise StrategyNotFoundError(strategy_id)
    
    # Get strategy UUID from database (async)
    db_service = await get_database_service_async(db)
    db_strategy = await db_service.async_get_strategy(current_user.id, strategy_id)
    if not db_strategy:
        raise StrategyNotFoundError(strategy_id)
    
    # Get activity events (async)
    events = await db_service.async_get_strategy_events(
        strategy_id=db_strategy.id,
        event_type=None,  # Get all event types
        limit=limit
    )
    
    # Convert to response format
    activity_list = []
    for event in events:
        activity_list.append({
            "event_type": event.event_type,
            "event_level": event.event_level,
            "message": event.message,
            "created_at": event.created_at.isoformat(),
            "metadata": event.event_metadata or {}
        })
    
    return activity_list


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user_async),
    runner: StrategyRunner = Depends(get_strategy_runner)
) -> None:
    """Delete a strategy permanently.
    
    This endpoint will:
    1. Check if strategy is running and stop it if necessary
    2. Delete from database (if using StrategyService)
    3. Delete from Redis
    4. Remove from in-memory cache
    
    Raises:
        StrategyNotFoundError: If strategy does not exist
    """
    logger.info(f"DELETE /strategies/{strategy_id} - User: {current_user.id}, Strategy ID: {strategy_id}")
    try:
        await runner.delete(strategy_id)
        logger.info(f"Successfully deleted strategy {strategy_id}")
    except StrategyNotFoundError as e:
        logger.warning(f"Strategy {strategy_id} not found for deletion: {e}")
        raise
    except Exception as e:
        logger.error(f"Error deleting strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete strategy: {str(e)}"
        )


@router.get("/{strategy_id}/health")
async def get_strategy_health(
    strategy_id: str,
    current_user: User = Depends(get_current_user_async),
    runner: StrategyRunner = Depends(get_strategy_runner),
    db: Session = Depends(get_db_session_dependency),
) -> dict:
    """Get health status for a strategy.
    
    This endpoint verifies that a "running" strategy is actually:
    1. Has an active execution task (not dead)
    2. Is executing its loop (last_execution_time is recent)
    3. Is placing orders on Binance (has recent trades)
    
    Returns:
        Health status with detailed information about strategy execution
    """
    from datetime import datetime, timezone, timedelta
    from app.models.strategy import StrategyState
    
    try:
        strategies = runner.list_strategies()
        strategy = next((s for s in strategies if s.id == strategy_id), None)
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        # Check 1: Is task actually running?
        task_running = False
        task_done = True
        if strategy_id in runner._tasks:
            task = runner._tasks[strategy_id]
            task_running = not task.done()
            task_done = task.done()
        
        # Check 2: Last execution time (from meta)
        last_execution_time = None
        last_execution_age_seconds = None
        execution_stale = False
        if isinstance(strategy.meta, dict):
            last_exec_time_str = strategy.meta.get('last_execution_time')
            last_exec_timestamp = strategy.meta.get('last_execution_timestamp')
            
            if last_exec_time_str:
                try:
                    last_execution_time = datetime.fromisoformat(last_exec_time_str.replace('Z', '+00:00'))
                except:
                    pass
            elif last_exec_timestamp:
                last_execution_time = datetime.fromtimestamp(last_exec_timestamp, tz=timezone.utc)
            
            if last_execution_time:
                age = (datetime.now(timezone.utc) - last_execution_time).total_seconds()
                last_execution_age_seconds = age
                # Consider stale if > 5x the interval (strategy should execute every interval_seconds)
                interval = strategy.params.interval_seconds if hasattr(strategy.params, 'interval_seconds') else strategy.params.get('interval_seconds', 60)
                execution_stale = age > (interval * 5)
        
        # Check 3: Recent orders (check database for recent trades)
        from app.services.trade_service import TradeService
        from app.services.database_service import DatabaseService
        
        user_id = current_user.id if hasattr(current_user, 'id') else current_user
        db_service = DatabaseService(db=db)
        trade_service = TradeService(db=db)
        
        # Get strategy UUID
        db_strategy = db_service.get_strategy(user_id, strategy_id)
        recent_orders_count = 0
        last_order_time = None
        last_order_id = None
        
        if db_strategy:
            # Get trades from last hour
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            trades = trade_service.get_strategy_trades(user_id, db_strategy.id, limit=100)
            recent_trades = [t for t in trades if t.timestamp and t.timestamp >= one_hour_ago]
            recent_orders_count = len(recent_trades)
            
            if recent_trades:
                last_trade = max(recent_trades, key=lambda t: t.timestamp or datetime.min.replace(tzinfo=timezone.utc))
                last_order_time = last_trade.timestamp
                last_order_id = last_trade.order_id
        
        # Also check meta for last order info
        if isinstance(strategy.meta, dict):
            last_order_meta_time = strategy.meta.get('last_order_time')
            if last_order_meta_time and (not last_order_time or last_order_meta_time > last_order_time.isoformat() if last_order_time else True):
                try:
                    last_order_time = datetime.fromisoformat(last_order_meta_time.replace('Z', '+00:00'))
                except:
                    pass
            last_order_id = strategy.meta.get('last_order_id') or last_order_id
        
        # Determine overall health
        is_healthy = True
        health_status = "healthy"
        issues = []
        
        if strategy.status != StrategyState.running:
            is_healthy = False
            health_status = "not_running"
            issues.append(f"Strategy status is '{strategy.status.value}', not 'running'")
        elif not task_running:
            is_healthy = False
            health_status = "task_dead"
            issues.append("Strategy has 'running' status but execution task is not active (task is done/dead)")
        elif execution_stale:
            is_healthy = False
            health_status = "execution_stale"
            issues.append(f"Last execution was {last_execution_age_seconds:.0f} seconds ago (stale)")
        elif last_execution_time is None:
            is_healthy = False
            health_status = "no_execution_tracking"
            issues.append("No execution time tracking found (strategy may not have executed yet)")
        
        # Check if orders are being placed (optional warning, not error)
        orders_healthy = True
        if strategy.status == StrategyState.running:
            # For running strategies, check if orders are being placed
            if isinstance(strategy.meta, dict):
                orders_executed = strategy.meta.get('orders_executed_count', 0)
                orders_skipped = strategy.meta.get('orders_skipped_count', 0)
                
                # If strategy has been running for a while but no orders executed, it's suspicious
                if strategy.started_at:
                    running_duration = (datetime.now(timezone.utc) - strategy.started_at).total_seconds()
                    if running_duration > 3600 and orders_executed == 0:  # Running > 1 hour, no orders
                        orders_healthy = False
                        issues.append(f"Strategy has been running for {running_duration/3600:.1f} hours but no orders executed")
        
        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy.name,
            "status": strategy.status.value,
            "health_status": health_status,
            "is_healthy": is_healthy,
            "issues": issues,
            "task_status": {
                "has_task": strategy_id in runner._tasks,
                "task_running": task_running,
                "task_done": task_done,
            },
            "execution_status": {
                "last_execution_time": last_execution_time.isoformat() if last_execution_time else None,
                "last_execution_age_seconds": last_execution_age_seconds,
                "execution_stale": execution_stale,
            },
            "order_status": {
                "recent_orders_count": recent_orders_count,
                "last_order_time": last_order_time.isoformat() if last_order_time else None,
                "last_order_id": last_order_id,
                "orders_healthy": orders_healthy,
            },
            "meta": {
                "orders_executed_count": strategy.meta.get('orders_executed_count', 0) if isinstance(strategy.meta, dict) else 0,
                "orders_skipped_count": strategy.meta.get('orders_skipped_count', 0) if isinstance(strategy.meta, dict) else 0,
            } if isinstance(strategy.meta, dict) else {},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking strategy health for {strategy_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check strategy health: {str(e)}"
        )
