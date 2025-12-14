from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from uuid import UUID

from loguru import logger

from app.api.deps import get_strategy_runner, get_current_user, get_database_service, get_db_session_dependency
from app.models.order import OrderResponse
from app.models.strategy import CreateStrategyRequest, StrategySummary, StrategyStats, OverallStats
from app.models.db_models import User
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_service import StrategyService
from app.core.redis_storage import RedisStorage
from app.core.config import get_settings
from sqlalchemy.orm import Session
from app.core.exceptions import (
    StrategyNotFoundError,
    StrategyAlreadyRunningError,
    MaxConcurrentStrategiesError,
    InvalidLeverageError,
    PositionSizingError,
    OrderExecutionError,
    BinanceAPIError,
)


router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/list", response_model=list[StrategySummary])
def list_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
    runner: StrategyRunner = Depends(get_strategy_runner)
) -> list[StrategySummary]:
    """List all registered strategies for the current user.
    
    Note: Changed from GET / to GET /list to avoid conflict with GUI route at /strategies
    """
    # If runner has StrategyService, it will automatically filter by user_id
    # Otherwise, return all strategies (backward compatibility)
    return runner.list_strategies()


@router.get("/{strategy_id}", response_model=StrategySummary)
def get_strategy(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategySummary:
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
    runner: StrategyRunner = Depends(get_strategy_runner)
) -> StrategySummary:
    """Register a new trading strategy.
    
    Raises:
        InvalidLeverageError: If leverage is invalid or not provided
        ValidationError: If request data is invalid
    """
    try:
        # Get account UUID from account_id
        account_id = payload.account_id.lower() if payload.account_id else "default"
        db_service = get_database_service(db)
        
        # Find account in database
        account_uuid = None
        if runner.strategy_service and runner.user_id:
            # Multi-user mode: get account from database
            accounts = db_service.get_user_accounts(current_user.id)
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
def get_strategy_trades(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> list[OrderResponse]:
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


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
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
    await runner.delete(strategy_id)
