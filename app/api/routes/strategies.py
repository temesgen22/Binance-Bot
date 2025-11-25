from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_strategy_runner
from app.models.order import OrderResponse
from app.models.strategy import CreateStrategyRequest, StrategySummary, StrategyStats, OverallStats
from app.services.strategy_runner import StrategyRunner


router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/", response_model=list[StrategySummary])
def list_strategies(runner: StrategyRunner = Depends(get_strategy_runner)) -> list[StrategySummary]:
    """List all registered strategies."""
    return runner.list_strategies()


@router.get("/{strategy_id}", response_model=StrategySummary)
def get_strategy(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategySummary:
    """Get details of a specific strategy by ID."""
    strategies = runner.list_strategies()
    for strategy in strategies:
        if strategy.id == strategy_id:
            return strategy
    raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")


@router.post("/", response_model=StrategySummary, status_code=status.HTTP_201_CREATED)
async def register_strategy(
    payload: CreateStrategyRequest, runner: StrategyRunner = Depends(get_strategy_runner)
) -> StrategySummary:
    summary = runner.register(payload)
    if payload.auto_start:
        await runner.start(summary.id)
    return summary


@router.post("/{strategy_id}/start", response_model=StrategySummary)
async def start_strategy(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategySummary:
    try:
        return await runner.start(strategy_id)
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{strategy_id}/stop", response_model=StrategySummary)
async def stop_strategy(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategySummary:
    try:
        return await runner.stop(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{strategy_id}/trades", response_model=list[OrderResponse])
def get_strategy_trades(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> list[OrderResponse]:
    """Get all executed trades for a specific strategy."""
    # Verify strategy exists
    strategies = runner.list_strategies()
    if not any(s.id == strategy_id for s in strategies):
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return runner.get_trades(strategy_id)


@router.get("/{strategy_id}/stats", response_model=StrategyStats)
def get_strategy_stats(strategy_id: str, runner: StrategyRunner = Depends(get_strategy_runner)) -> StrategyStats:
    """Get statistics for a specific strategy including trade count and PnL."""
    try:
        return runner.calculate_strategy_stats(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stats", response_model=OverallStats)
def get_overall_stats(runner: StrategyRunner = Depends(get_strategy_runner)) -> OverallStats:
    """Get overall statistics across all strategies."""
    return runner.calculate_overall_stats()

