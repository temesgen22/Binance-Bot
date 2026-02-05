"""API routes for strategy performance tracking and ranking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api.deps import get_strategy_runner, get_current_user, get_database_service
from app.models.strategy_performance import StrategyPerformance, StrategyPerformanceList
from app.services.strategy_runner import StrategyRunner
from app.services.database_service import DatabaseService
from app.models.db_models import User
from app.core.exceptions import StrategyNotFoundError


router = APIRouter(prefix="/api/strategies/performance", tags=["strategy-performance"])


@router.get("", response_model=StrategyPerformanceList)
@router.get("/", response_model=StrategyPerformanceList)
def get_strategy_performance(
    strategy_name: Optional[str] = Query(default=None, description="Filter by strategy name"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    status: Optional[str] = Query(default=None, description="Filter by status (running/stopped/error)"),
    rank_by: Optional[str] = Query(default="total_pnl", description="Rank by field (total_pnl, win_rate, completed_trades)"),
    start_date: Optional[str] = Query(default=None, description="Filter from date/time (ISO datetime)"),
    end_date: Optional[str] = Query(default=None, description="Filter to date/time (ISO datetime)"),
    account_id: Optional[str] = Query(default=None, description="Filter by Binance account ID"),
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner),
    db_service: DatabaseService = Depends(get_database_service),
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
        if account_id and strategy.account_id != account_id:
            continue
        
        try:
            # Parse date filters if provided
            start_datetime: Optional[datetime] = None
            end_datetime: Optional[datetime] = None
            
            if start_date:
                try:
                    # Check if it's date-only format (YYYY-MM-DD) or includes time
                    if 'T' in start_date or '+' in start_date or start_date.count(':') >= 2:
                        # ISO format with time: parse as-is
                        start_datetime = date_parser.parse(start_date)
                    else:
                        # Date-only format: set to start of day (00:00:00)
                        start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                    
                    if start_datetime.tzinfo is None:
                        start_datetime = start_datetime.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError) as exc:
                    logger.warning(f"Invalid start_date format: {start_date}, error: {exc}")
                    start_datetime = None
            
            if end_date:
                try:
                    # Check if it's date-only format (YYYY-MM-DD) or includes time
                    if 'T' in end_date or '+' in end_date or end_date.count(':') >= 2:
                        # ISO format with time: parse as-is
                        end_datetime = date_parser.parse(end_date)
                    else:
                        # Date-only format: set to end of day (23:59:59.999999)
                        end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                        end_datetime = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
                    
                    if end_datetime.tzinfo is None:
                        end_datetime = end_datetime.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError) as exc:
                    logger.warning(f"Invalid end_date format: {end_date}, error: {exc}")
                    end_datetime = None
            
            # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
            # This is much faster than on-demand matching
            from app.api.routes.reports import _get_completed_trades_from_database, _match_trades_to_completed_positions
            from app.services.trade_service import TradeService
            from app.core.redis_storage import RedisStorage
            from app.core.config import get_settings
            from uuid import UUID
            
            completed_trades_list = []
            
            # Get strategy UUID from database
            db_strategy = None
            if runner.strategy_service and runner.user_id:
                try:
                    db_strategy = runner.strategy_service.db_service.get_strategy(current_user.id, strategy.id)
                except Exception as e:
                    logger.debug(f"Could not get strategy from database: {e}")
            
            if db_strategy:
                try:
                    # Query from CompletedTrade table
                    completed_trades_list = _get_completed_trades_from_database(
                        db_service=db_service,
                        user_id=current_user.id,
                        strategy_uuid=db_strategy.id,
                        strategy_id=strategy.id,
                        start_datetime=start_datetime,
                        end_datetime=end_datetime
                    )
                except Exception as e:
                    logger.debug(f"Could not get completed trades from database for strategy {strategy.id}: {e}")
            
            # ✅ FALLBACK: If no completed trades from database, use on-demand matching
            if not completed_trades_list:
                logger.debug(f"No completed trades from database for strategy {strategy.id}, falling back to trades table")
                # Use existing calculate_strategy_stats which uses trades table
                stats = runner.calculate_strategy_stats(
                    strategy.id,
                    start_date=start_datetime,
                    end_date=end_datetime
                )
            else:
                # Calculate stats from completed trades (TradeReport objects)
                from app.models.strategy import StrategyStats
                
                total_pnl = sum(trade.pnl_usd for trade in completed_trades_list)
                winning_trades = len([t for t in completed_trades_list if t.pnl_usd > 0])
                losing_trades = len([t for t in completed_trades_list if t.pnl_usd < 0])
                completed_count = len(completed_trades_list)
                win_rate = (winning_trades / completed_count * 100) if completed_count > 0 else 0.0
                avg_profit_per_trade = total_pnl / completed_count if completed_count > 0 else 0.0
                largest_win = max((t.pnl_usd for t in completed_trades_list), default=0.0)
                largest_loss = min((t.pnl_usd for t in completed_trades_list), default=0.0)
                
                # Calculate total fees from completed trades
                total_trade_fees = sum(trade.fee_paid for trade in completed_trades_list)
                total_funding_fees = sum(trade.funding_fee for trade in completed_trades_list)
                
                # Get last trade timestamp from completed trades
                last_trade_at = None
                if completed_trades_list:
                    exit_times = [t.exit_time for t in completed_trades_list if t.exit_time]
                    if exit_times:
                        last_trade_at = max(exit_times)
                
                # Get total trades count from runner (includes open positions)
                all_trades = runner.get_trades(strategy.id)
                total_trades_count = len(all_trades) if all_trades else completed_count
                
                stats = StrategyStats(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    symbol=strategy.symbol,
                    total_trades=total_trades_count,
                    completed_trades=completed_count,
                    total_pnl=round(total_pnl, 4),
                    win_rate=round(win_rate, 2),
                    winning_trades=winning_trades,
                    losing_trades=losing_trades,
                    avg_profit_per_trade=round(avg_profit_per_trade, 4),
                    largest_win=round(largest_win, 4),
                    largest_loss=round(largest_loss, 4),
                    created_at=strategy.created_at,
                    last_trade_at=last_trade_at
                )
            
            # Get current unrealized PnL from strategy summary
            unrealized_pnl = strategy.unrealized_pnl or 0.0
            
            # Calculate total PnL (realized + unrealized)
            total_pnl = stats.total_pnl + unrealized_pnl
            
            # Calculate percentile (will be set after ranking)
            # Get account information if available
            account_info = None
            if strategy.account_id and strategy.account_id != "default":
                try:
                    account_config = runner.client_manager.get_account_config(strategy.account_id)
                    if account_config:
                        account_info = {
                            "account_id": strategy.account_id,
                            "account_name": account_config.name or strategy.account_id,
                            "testnet": account_config.testnet
                        }
                except Exception:
                    # Fallback if account not found in manager
                    account_info = {
                        "account_id": strategy.account_id,
                        "account_name": strategy.account_id,
                        "testnet": None
                    }
            
            # Calculate fees for this strategy from completed trades
            strategy_total_trade_fees = None
            strategy_total_funding_fees = None
            if completed_trades_list:
                strategy_total_trade_fees = sum(trade.fee_paid for trade in completed_trades_list)
                strategy_total_funding_fees = sum(trade.funding_fee for trade in completed_trades_list)
            
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
                started_at=strategy.started_at,
                stopped_at=strategy.stopped_at,
                last_trade_at=stats.last_trade_at,
                last_signal=strategy.last_signal,
                account_id=strategy.account_id,
                account_info=account_info,
                auto_tuning_enabled=getattr(strategy, 'auto_tuning_enabled', False),
                total_trade_fees=round(strategy_total_trade_fees, 4) if strategy_total_trade_fees is not None else None,
                total_funding_fees=round(strategy_total_funding_fees, 4) if strategy_total_funding_fees is not None else None,
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
            "total_trades": total_trades_sum,  # Total of all trades (completed + open positions)
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
        started_at=strategy.started_at,
        stopped_at=strategy.stopped_at,
        last_trade_at=stats.last_trade_at,
        last_signal=strategy.last_signal,
        auto_tuning_enabled=getattr(strategy, 'auto_tuning_enabled', False),
    )
    
    return performance

