"""API routes for strategy performance tracking and ranking."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api.deps import get_strategy_runner
from app.models.strategy_performance import StrategyPerformance, StrategyPerformanceList
from app.services.strategy_runner import StrategyRunner
from app.core.exceptions import StrategyNotFoundError


router = APIRouter(prefix="/strategies/performance", tags=["strategy-performance"])


@router.get("/", response_model=StrategyPerformanceList)
def get_strategy_performance(
    strategy_name: Optional[str] = Query(default=None, description="Filter by strategy name"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    status: Optional[str] = Query(default=None, description="Filter by status (running/stopped/error)"),
    rank_by: Optional[str] = Query(default="total_pnl", description="Rank by field (total_pnl, win_rate, completed_trades)"),
    start_date: Optional[str] = Query(default=None, description="Filter from date/time (ISO datetime) - not yet implemented"),
    end_date: Optional[str] = Query(default=None, description="Filter to date/time (ISO datetime) - not yet implemented"),
    runner: StrategyRunner = Depends(get_strategy_runner),
) -> StrategyPerformanceList:
    """Get performance metrics for all strategies, ranked by profitability.
    
    Returns strategies sorted by total PnL (best performing first) with detailed
    performance metrics including realized/unrealized PnL, win rate, and trade statistics.
    """
    strategies = runner.list_strategies()
    
    # Collect performance data for each strategy
    performance_list: List[StrategyPerformance] = []
    
    for strategy in strategies:
        # Apply filters
        if strategy_name and strategy_name.lower() not in strategy.name.lower():
            continue
        if symbol and strategy.symbol.upper() != symbol.upper():
            continue
        if status and strategy.status.value.lower() != status.lower():
            continue
        
        try:
            # Get strategy stats (includes realized PnL)
            stats = runner.calculate_strategy_stats(strategy.id)
            
            # Get current unrealized PnL from strategy summary
            unrealized_pnl = strategy.unrealized_pnl or 0.0
            
            # Calculate total PnL (realized + unrealized)
            total_pnl = stats.total_pnl + unrealized_pnl
            
            # Calculate percentile (will be set after ranking)
            performance = StrategyPerformance(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                symbol=strategy.symbol,
                strategy_type=strategy.strategy_type,
                status=strategy.status,
                total_realized_pnl=round(stats.total_pnl, 4),
                total_unrealized_pnl=round(unrealized_pnl, 4),
                total_pnl=round(total_pnl, 4),
                total_trades=stats.total_trades,
                completed_trades=stats.completed_trades,
                win_rate=stats.win_rate,
                winning_trades=stats.winning_trades,
                losing_trades=stats.losing_trades,
                avg_profit_per_trade=stats.avg_profit_per_trade,
                largest_win=stats.largest_win,
                largest_loss=stats.largest_loss,
                position_size=strategy.position_size,
                position_side=strategy.position_side,
                entry_price=strategy.entry_price,
                current_price=strategy.current_price,
                leverage=strategy.leverage,
                risk_per_trade=strategy.risk_per_trade,
                fixed_amount=strategy.fixed_amount,
                params=strategy.params.model_dump() if hasattr(strategy.params, 'model_dump') else strategy.params,
                created_at=strategy.created_at,
                last_trade_at=stats.last_trade_at,
                last_signal=strategy.last_signal,
            )
            performance_list.append(performance)
        except StrategyNotFoundError:
            logger.warning(f"Strategy {strategy.id} not found when calculating stats")
            continue
        except Exception as exc:
            logger.error(f"Error calculating performance for strategy {strategy.id}: {exc}")
            continue
    
    # Rank strategies based on selected field
    rank_field_map = {
        "total_pnl": "total_pnl",
        "win_rate": "win_rate",
        "completed_trades": "completed_trades",
        "realized_pnl": "total_realized_pnl",
        "unrealized_pnl": "total_unrealized_pnl",
    }
    
    rank_field = rank_field_map.get(rank_by.lower(), "total_pnl")
    
    # Sort by rank field (descending for most fields)
    reverse = True  # Higher is better for PnL, win_rate, etc.
    performance_list.sort(key=lambda x: getattr(x, rank_field, 0), reverse=reverse)
    
    # Assign ranks and percentiles
    total = len(performance_list)
    for idx, perf in enumerate(performance_list):
        perf.rank = idx + 1
        if total > 1:
            # Calculate percentile: 0-100, higher percentile = better performance
            percentile = ((total - idx) / total) * 100
            perf.percentile = round(percentile, 2)
        else:
            perf.percentile = 100.0
    
    # Calculate summary statistics
    if performance_list:
        total_pnl_sum = sum(p.total_pnl for p in performance_list)
        total_realized_sum = sum(p.total_realized_pnl for p in performance_list)
        total_unrealized_sum = sum(p.total_unrealized_pnl for p in performance_list)
        total_trades_sum = sum(p.total_trades for p in performance_list)
        total_completed_sum = sum(p.completed_trades for p in performance_list)
        total_winning = sum(p.winning_trades for p in performance_list)
        total_losing = sum(p.losing_trades for p in performance_list)
        overall_win_rate = (total_winning / total_completed_sum * 100) if total_completed_sum > 0 else 0
        
        active_count = len([p for p in performance_list if p.status.value == "running"])
        
        summary = {
            "total_pnl": round(total_pnl_sum, 4),
            "total_realized_pnl": round(total_realized_sum, 4),
            "total_unrealized_pnl": round(total_unrealized_sum, 4),
            "total_trades": total_trades_sum,
            "completed_trades": total_completed_sum,
            "overall_win_rate": round(overall_win_rate, 2),
            "winning_trades": total_winning,
            "losing_trades": total_losing,
            "active_strategies": active_count,
            "best_performing": performance_list[0].strategy_name if performance_list else None,
            "worst_performing": performance_list[-1].strategy_name if performance_list else None,
        }
    else:
        summary = {}
    
    logger.info(f"Returning performance data for {len(performance_list)} strategies, ranked by {rank_field}")
    
    return StrategyPerformanceList(
        strategies=performance_list,
        total_strategies=len(performance_list),
        ranked_by=rank_field,
        summary=summary,
    )


@router.get("/{strategy_id}", response_model=StrategyPerformance)
def get_strategy_performance_detail(
    strategy_id: str,
    runner: StrategyRunner = Depends(get_strategy_runner),
) -> StrategyPerformance:
    """Get detailed performance metrics for a specific strategy."""
    strategies = runner.list_strategies()
    strategy = next((s for s in strategies if s.id == strategy_id), None)
    
    if not strategy:
        raise StrategyNotFoundError(strategy_id)
    
    # Get strategy stats
    stats = runner.calculate_strategy_stats(strategy_id)
    
    # Get unrealized PnL
    unrealized_pnl = strategy.unrealized_pnl or 0.0
    total_pnl = stats.total_pnl + unrealized_pnl
    
    performance = StrategyPerformance(
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        symbol=strategy.symbol,
        strategy_type=strategy.strategy_type,
        status=strategy.status,
        total_realized_pnl=round(stats.total_pnl, 4),
        total_unrealized_pnl=round(unrealized_pnl, 4),
        total_pnl=round(total_pnl, 4),
        total_trades=stats.total_trades,
        completed_trades=stats.completed_trades,
        win_rate=stats.win_rate,
        winning_trades=stats.winning_trades,
        losing_trades=stats.losing_trades,
        avg_profit_per_trade=stats.avg_profit_per_trade,
        largest_win=stats.largest_win,
        largest_loss=stats.largest_loss,
        position_size=strategy.position_size,
        position_side=strategy.position_side,
        entry_price=strategy.entry_price,
        current_price=strategy.current_price,
        leverage=strategy.leverage,
        risk_per_trade=strategy.risk_per_trade,
        fixed_amount=strategy.fixed_amount,
        params=strategy.params.model_dump() if hasattr(strategy.params, 'model_dump') else strategy.params,
        created_at=strategy.created_at,
        last_trade_at=stats.last_trade_at,
        last_signal=strategy.last_signal,
    )
    
    return performance

