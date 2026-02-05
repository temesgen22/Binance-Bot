"""API routes for dashboard overview and aggregated metrics."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
from dateutil import parser as date_parser

from fastapi import APIRouter, Depends, Query, HTTPException, status
from loguru import logger

from app.api.deps import (
    get_strategy_runner,
    get_current_user,
    get_binance_client,
    get_client_manager,
    get_database_service,
)
from app.models.dashboard import (
    DashboardOverview,
    StrategyComparisonResponse,
    ComparisonSummary,
    ComparisonMetric,
    DateRange,
)
from app.models.strategy_performance import StrategyPerformanceList
from app.models.trade import SymbolPnL
from app.services.strategy_runner import StrategyRunner
from app.services.database_service import DatabaseService
from app.core.my_binance_client import BinanceClient
from app.core.binance_client_manager import BinanceClientManager
from app.models.db_models import User


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
def get_dashboard_overview(
    start_date: Optional[str] = Query(default=None, description="Filter from date (ISO format)"),
    end_date: Optional[str] = Query(default=None, description="Filter to date (ISO format)"),
    account_id: Optional[str] = Query(default=None, description="Filter by Binance account ID"),
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner),
    client: BinanceClient = Depends(get_binance_client),
    client_manager: BinanceClientManager = Depends(get_client_manager),
    db_service: DatabaseService = Depends(get_database_service),
) -> DashboardOverview:
    """Get aggregated dashboard overview data from multiple endpoints.
    
    This endpoint aggregates data from:
    - /strategies/performance/ - for strategy data
    - /trades/pnl/overview - for symbol data
    - Strategy runner for active strategies count
    
    Note: Date range filtering is applied where supported by underlying endpoints.
    Account balance is optional and may not be available.
    """
    try:
        # Parse date filters
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
        
        # Initialize fee totals (will be calculated from all completed trades)
        total_trade_fees = 0.0
        total_funding_fees = 0.0
        
        # Get strategy performance data
        # We'll calculate strategy performance directly using runner to avoid circular imports
        # This duplicates some logic from strategy_performance endpoint but keeps things simple
        try:
            from app.models.strategy_performance import StrategyPerformance, StrategyPerformanceList
            
            strategies = runner.list_strategies()
            performance_list = []
            
            for strategy in strategies:
                # Apply account filter
                if account_id and strategy.account_id != account_id:
                    continue
                
                try:
                    # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
                    # This is much faster than on-demand matching
                    from app.api.routes.reports import _get_completed_trades_from_database, _match_trades_to_completed_positions
                    from app.models.strategy import StrategyStats
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
                        total_pnl = sum(trade.pnl_usd for trade in completed_trades_list)
                        winning_trades = len([t for t in completed_trades_list if t.pnl_usd > 0])
                        losing_trades = len([t for t in completed_trades_list if t.pnl_usd < 0])
                        completed_count = len(completed_trades_list)
                        win_rate = (winning_trades / completed_count * 100) if completed_count > 0 else 0.0
                        avg_profit_per_trade = total_pnl / completed_count if completed_count > 0 else 0.0
                        largest_win = max((t.pnl_usd for t in completed_trades_list), default=0.0)
                        largest_loss = min((t.pnl_usd for t in completed_trades_list), default=0.0)
                        
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
                    
                    # When date filtering is active, only use realized PnL from filtered trades
                    # Unrealized PnL represents current positions and shouldn't be included in date-filtered results
                    if start_datetime or end_datetime:
                        # Date filtering active: only show realized PnL from filtered period
                        total_pnl = stats.total_pnl  # Only realized PnL (already filtered)
                        unrealized_pnl = 0.0  # Exclude current unrealized PnL when filtering by date
                    else:
                        # No date filtering: include both realized and unrealized
                        unrealized_pnl = strategy.unrealized_pnl or 0.0
                        total_pnl = stats.total_pnl + unrealized_pnl
                    
                    perf = StrategyPerformance(
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
                        auto_tuning_enabled=getattr(strategy, 'auto_tuning_enabled', False),
                    )
                    performance_list.append(perf)
                except Exception as exc:
                    logger.warning(f"Error calculating performance for strategy {strategy.id}: {exc}")
                    continue
            
            # Sort by total PnL
            performance_list.sort(key=lambda x: x.total_pnl, reverse=True)
            
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
                    "active_strategies": active_count,
                }
            else:
                summary = {}
            
            strategy_response = type('obj', (object,), {
                'strategies': performance_list,
                'total_strategies': len(performance_list),
                'summary': summary
            })()
        except Exception as exc:
            logger.error(f"Failed to get strategy performance: {exc}")
            strategy_response = None
        
        # Collect all completed trades to calculate total fees
        # Do this after strategy performance to ensure we have all trades
        try:
            all_completed_trades_for_fees = []
            strategies_for_fees = runner.list_strategies()
            for strategy in strategies_for_fees:
                if account_id and strategy.account_id != account_id:
                    continue
                
                try:
                    db_strategy = runner.strategy_service.db_service.get_strategy(current_user.id, strategy.id) if runner.strategy_service else None
                    if db_strategy:
                        try:
                            completed_trades_for_fees = _get_completed_trades_from_database(
                                db_service=db_service,
                                user_id=current_user.id,
                                strategy_uuid=db_strategy.id,
                                strategy_id=strategy.id,
                                start_datetime=start_datetime,
                                end_datetime=end_datetime
                            )
                            all_completed_trades_for_fees.extend(completed_trades_for_fees)
                        except Exception as e:
                            logger.debug(f"Could not get completed trades for fee calculation for strategy {strategy.id}: {e}")
                except Exception:
                    pass
            
            # Calculate total fees from completed trades
            if all_completed_trades_for_fees:
                total_trade_fees = sum(trade.fee_paid for trade in all_completed_trades_for_fees)
                total_funding_fees = sum(trade.funding_fee for trade in all_completed_trades_for_fees)
        except Exception as exc:
            logger.debug(f"Failed to calculate total fees: {exc}")
            # Keep default values (0.0)
        
        # Get symbol PnL data
        # We'll use the trades endpoint logic directly
        try:
            from app.api.routes.trades import get_pnl_overview
            symbol_pnl_list = get_pnl_overview(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date,
                current_user=current_user,
                runner=runner,
                client=client,
                client_manager=client_manager
            )
        except Exception as exc:
            logger.error(f"Failed to get symbol PnL: {exc}")
            symbol_pnl_list = []
        
        # Calculate aggregated metrics
        if strategy_response and strategy_response.strategies:
            total_pnl = strategy_response.summary.get("total_pnl", 0.0)
            realized_pnl = strategy_response.summary.get("total_realized_pnl", 0.0)
            unrealized_pnl = strategy_response.summary.get("total_unrealized_pnl", 0.0)
            total_trades = strategy_response.summary.get("total_trades", 0)
            completed_trades = strategy_response.summary.get("completed_trades", 0)
            overall_win_rate = strategy_response.summary.get("overall_win_rate", 0.0)
            active_strategies = strategy_response.summary.get("active_strategies", 0)
            total_strategies = strategy_response.total_strategies
            
            # Get best and worst strategies
            strategies = strategy_response.strategies
            best_strategy = strategies[0] if strategies else None
            worst_strategy = strategies[-1] if strategies else None
        else:
            # Fallback if strategy performance endpoint fails
            strategies = runner.list_strategies()
            total_strategies = len(strategies)
            active_strategies = len([s for s in strategies if s.status.value == "running"])
            
            # Calculate basic metrics from strategies
            total_pnl = 0.0
            realized_pnl = 0.0
            unrealized_pnl = 0.0
            total_trades = 0
            completed_trades = 0
            overall_win_rate = 0.0
            
            for strategy in strategies:
                if account_id and strategy.account_id != account_id:
                    continue
                try:
                    stats = runner.calculate_strategy_stats(strategy.id)
                    realized_pnl += stats.total_pnl
                    unrealized_pnl += (strategy.unrealized_pnl or 0.0)
                    total_trades += stats.total_trades
                    completed_trades += stats.completed_trades
                except Exception:
                    continue
            
            total_pnl = realized_pnl + unrealized_pnl
            best_strategy = None
            worst_strategy = None
        
        # Get top symbol by PnL
        top_symbol = None
        if symbol_pnl_list:
            sorted_symbols = sorted(symbol_pnl_list, key=lambda x: x.total_pnl, reverse=True)
            top_symbol = sorted_symbols[0] if sorted_symbols else None
        
        # Try to get account balance (optional - may fail)
        account_balance = None
        try:
            account_client = client
            if account_id:
                account_client = client_manager.get_client(account_id) or client
            
            rest = account_client._ensure()
            account_info = rest.futures_account()
            
            # Get USDT balance (or main quote currency)
            assets = account_info.get("assets", [])
            for asset in assets:
                if asset.get("asset") == "USDT":
                    account_balance = float(asset.get("availableBalance", 0))
                    break
        except Exception as exc:
            logger.debug(f"Could not fetch account balance (optional feature): {exc}")
            # Account balance is optional, continue without it
        
        # Calculate PnL changes (24h, 7d, 30d) from historical completed trades
        pnl_change_24h = None
        pnl_change_7d = None
        pnl_change_30d = None
        
        try:
            from app.api.routes.reports import _get_completed_trades_from_database
            from app.models.db_models import Strategy as DBStrategy
            
            now = datetime.now(timezone.utc)
            periods = {
                '24h': now - timedelta(hours=24),
                '7d': now - timedelta(days=7),
                '30d': now - timedelta(days=30),
            }
            
            # Get fresh list of strategies for period calculation
            # Note: 'strategies' variable may have been overwritten with StrategyPerformance objects
            period_strategies = runner.list_strategies()
            
            # Calculate PnL for each period
            for period_name, period_start in periods.items():
                period_pnl = 0.0
                
                # Collect completed trades within this period
                for strategy in period_strategies:
                    if account_id and strategy.account_id != account_id:
                        continue
                    
                    try:
                        db_strategy = db_service.get_strategy(current_user.id, strategy.id)
                        if db_strategy:
                            period_trades = _get_completed_trades_from_database(
                                db_service=db_service,
                                user_id=current_user.id,
                                strategy_uuid=db_strategy.id,
                                strategy_id=strategy.id,
                                start_datetime=period_start,
                                end_datetime=now
                            )
                            period_pnl += sum(trade.pnl_usd for trade in period_trades)
                    except Exception as e:
                        logger.debug(f"Could not get period trades for {period_name} for strategy {strategy.id}: {e}")
                
                # Set the appropriate variable
                if period_name == '24h':
                    pnl_change_24h = round(period_pnl, 4)
                elif period_name == '7d':
                    pnl_change_7d = round(period_pnl, 4)
                elif period_name == '30d':
                    pnl_change_30d = round(period_pnl, 4)
                    
        except Exception as e:
            logger.debug(f"Could not calculate PnL changes: {e}")
            # Keep as None if calculation fails
        
        # Calculate PnL timeline from completed trades (Phase 2)
        # Note: Timeline shows all historical data regardless of date filters
        # (date filters are for summary metrics, but timeline shows full history for context)
        pnl_timeline = []
        try:
            from app.api.routes.reports import _get_completed_trades_from_database
            from app.models.db_models import Strategy as DBStrategy
            
            # Get fresh list of strategies (StrategySummary objects) for timeline calculation
            # Note: 'strategies' variable may have been overwritten with StrategyPerformance objects
            timeline_strategies = runner.list_strategies()
            
            # Collect all completed trades from all strategies (no date filter for timeline)
            # This allows the timeline to show full historical progression
            all_completed_trades_timeline = []
            for strategy in timeline_strategies:
                if account_id and strategy.account_id != account_id:
                    continue
                
                try:
                    db_strategy = db_service.get_strategy(current_user.id, strategy.id)
                    if db_strategy:
                        # Get all completed trades for timeline (ignore date filters)
                        completed_trades_timeline = _get_completed_trades_from_database(
                            db_service=db_service,
                            user_id=current_user.id,
                            strategy_uuid=db_strategy.id,
                            strategy_id=strategy.id,
                            start_datetime=None,  # No date filter - show all history
                            end_datetime=None     # No date filter - show all history
                        )
                        all_completed_trades_timeline.extend(completed_trades_timeline)
                        logger.debug(f"Timeline: Found {len(completed_trades_timeline)} completed trades for strategy {strategy.id}")
                except Exception as e:
                    logger.warning(f"Could not get completed trades for timeline for strategy {strategy.id}: {e}")
            
            logger.info(f"Timeline: Total completed trades collected: {len(all_completed_trades_timeline)}")
            
            # Sort by exit_time (oldest first) to calculate cumulative PnL
            all_completed_trades_timeline.sort(key=lambda t: t.exit_time or datetime.min.replace(tzinfo=timezone.utc))
            
            # Calculate cumulative PnL timeline
            cumulative_pnl = 0.0
            for trade in all_completed_trades_timeline:
                # Ensure exit_time exists and is valid, and pnl_usd is a valid number
                if trade.exit_time and trade.pnl_usd is not None:
                    # Ensure pnl_usd is a valid number (not NaN)
                    try:
                        pnl_value = float(trade.pnl_usd)
                        if not (isinstance(pnl_value, float) and not (pnl_value != pnl_value)):  # Check for NaN
                            raise ValueError("Invalid pnl_usd value")
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid pnl_usd for trade {trade.trade_id}: {trade.pnl_usd}")
                        continue
                    
                    cumulative_pnl += pnl_value
                    
                    # Ensure cumulative_pnl is still valid (not NaN)
                    if cumulative_pnl != cumulative_pnl:  # NaN check
                        logger.error(f"Cumulative PnL became NaN after trade {trade.trade_id}")
                        cumulative_pnl = 0.0  # Reset to prevent propagation
                        continue
                    
                    # Convert datetime to Unix timestamp (seconds)
                    try:
                        if trade.exit_time.tzinfo:
                            timestamp = int(trade.exit_time.timestamp())
                        else:
                            timestamp = int(trade.exit_time.replace(tzinfo=timezone.utc).timestamp())
                        
                        # Ensure timestamp is valid (not negative, not too large)
                        if timestamp > 0 and timestamp < 2e10:  # Valid Unix timestamp range
                            pnl_timeline.append({
                                "timestamp": timestamp,
                                "pnl": round(cumulative_pnl, 4),
                                "trade_pnl": round(pnl_value, 4)
                            })
                        else:
                            logger.warning(f"Invalid timestamp for trade {trade.trade_id}: {timestamp}")
                    except (ValueError, TypeError, OSError) as e:
                        logger.warning(f"Could not convert exit_time to timestamp for trade {trade.trade_id}: {e}")
                else:
                    logger.debug(f"Skipping trade {trade.trade_id}: missing exit_time or pnl_usd")
            
            logger.info(f"Timeline: Generated {len(pnl_timeline)} timeline points")
            
            # If timeline is still empty but we expected data, log a warning
            if len(pnl_timeline) == 0 and completed_trades > 0:
                logger.warning(f"Timeline is empty but {completed_trades} completed trades exist. This may indicate missing exit_time values.")
                
        except Exception as e:
            logger.warning(f"Could not calculate PnL timeline: {e}", exc_info=True)
            pnl_timeline = None
        
        return DashboardOverview(
            total_pnl=round(total_pnl, 4),
            realized_pnl=round(realized_pnl, 4),
            unrealized_pnl=round(unrealized_pnl, 4),
            pnl_change_24h=pnl_change_24h,
            pnl_change_7d=pnl_change_7d,
            pnl_change_30d=pnl_change_30d,
            active_strategies=active_strategies,
            total_strategies=total_strategies,
            total_trades=total_trades,
            completed_trades=completed_trades,
            overall_win_rate=round(overall_win_rate, 2),
            best_strategy=best_strategy,
            worst_strategy=worst_strategy,
            top_symbol=top_symbol,
            account_balance=account_balance,
            total_trade_fees=round(total_trade_fees, 4) if total_trade_fees > 0 else None,
            total_funding_fees=round(total_funding_fees, 4) if total_funding_fees > 0 else None,
            pnl_timeline=pnl_timeline,
        )
    
    except Exception as exc:
        logger.exception(f"Error generating dashboard overview: {exc}")
        # Return minimal valid response on error
        return DashboardOverview(
            total_pnl=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            active_strategies=0,
            total_strategies=0,
            total_trades=0,
            completed_trades=0,
            overall_win_rate=0.0,
        )


@router.get("/strategy-comparison", response_model=StrategyComparisonResponse)
def get_strategy_comparison(
    strategy_ids: str = Query(..., description="Comma-separated list of strategy IDs to compare"),
    start_date: Optional[str] = Query(default=None, description="Filter from date (ISO format)"),
    end_date: Optional[str] = Query(default=None, description="Filter to date (ISO format)"),
    current_user: User = Depends(get_current_user),
    runner: StrategyRunner = Depends(get_strategy_runner),
    db_service: DatabaseService = Depends(get_database_service),
) -> StrategyComparisonResponse:
    """Compare multiple strategies side-by-side with detailed metrics.
    
    Returns performance data for each strategy along with comparison metrics
    highlighting best and worst performers across various dimensions.
    """
    try:
        # Parse strategy IDs
        strategy_id_list = [sid.strip() for sid in strategy_ids.split(',') if sid.strip()]
        if not strategy_id_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one strategy ID is required"
            )
        
        if len(strategy_id_list) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 10 strategies can be compared at once"
            )
        
        # Parse date filters
        start_datetime: Optional[datetime] = None
        end_datetime: Optional[datetime] = None
        
        if start_date:
            try:
                if 'T' in start_date or '+' in start_date or start_date.count(':') >= 2:
                    start_datetime = date_parser.parse(start_date)
                else:
                    start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Invalid start_date format: {start_date}, error: {exc}")
                start_datetime = None
        
        if end_date:
            try:
                if 'T' in end_date or '+' in end_date or end_date.count(':') >= 2:
                    end_datetime = date_parser.parse(end_date)
                else:
                    end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                    end_datetime = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
                if end_datetime.tzinfo is None:
                    end_datetime = end_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning(f"Invalid end_date format: {end_date}, error: {exc}")
                end_datetime = None
        
        # Get strategy performance for each strategy
        from app.models.strategy_performance import StrategyPerformance
        from app.api.routes.reports import _get_completed_trades_from_database
        
        comparison_strategies = []
        
        for strategy_id in strategy_id_list:
            try:
                # Get strategy from runner by listing all strategies and filtering
                strategies = runner.list_strategies()
                strategy = next((s for s in strategies if s.id == strategy_id), None)
                if not strategy:
                    logger.warning(f"Strategy {strategy_id} not found in runner")
                    continue
                
                # Get database strategy for UUID
                db_strategy = None
                if runner.strategy_service:
                    try:
                        db_strategy = runner.strategy_service.db_service.get_strategy(current_user.id, strategy_id)
                    except Exception as e:
                        logger.debug(f"Could not get strategy from database: {e}")
                
                # Get completed trades
                completed_trades_list = []
                if db_strategy:
                    try:
                        completed_trades_list = _get_completed_trades_from_database(
                            db_service=db_service,
                            user_id=current_user.id,
                            strategy_uuid=db_strategy.id,
                            strategy_id=strategy_id,
                            start_datetime=start_datetime,
                            end_datetime=end_datetime
                        )
                    except Exception as e:
                        logger.debug(f"Could not get completed trades for strategy {strategy_id}: {e}")
                
                # Calculate performance metrics
                if completed_trades_list:
                    total_pnl = sum(float(trade.pnl_usd) if trade.pnl_usd is not None else 0.0 for trade in completed_trades_list)
                    winning_trades = len([t for t in completed_trades_list if t.pnl_usd and float(t.pnl_usd) > 0])
                    losing_trades = len([t for t in completed_trades_list if t.pnl_usd and float(t.pnl_usd) < 0])
                    completed_count = len(completed_trades_list)
                    win_rate = (winning_trades / completed_count * 100) if completed_count > 0 else 0.0
                    avg_profit_per_trade = total_pnl / completed_count if completed_count > 0 else 0.0
                    largest_win = max((float(t.pnl_usd) if t.pnl_usd is not None else 0.0 for t in completed_trades_list), default=0.0)
                    largest_loss = min((float(t.pnl_usd) if t.pnl_usd is not None else 0.0 for t in completed_trades_list), default=0.0)
                    
                    # Calculate fees
                    total_trade_fees = sum(float(trade.fee_paid) if trade.fee_paid is not None else 0.0 for trade in completed_trades_list)
                    total_funding_fees = sum(float(trade.funding_fee) if trade.funding_fee is not None else 0.0 for trade in completed_trades_list)
                    
                    # Get last trade timestamp
                    last_trade_at = None
                    if completed_trades_list:
                        exit_times = [t.exit_time for t in completed_trades_list if t.exit_time]
                        if exit_times:
                            last_trade_at = max(exit_times)
                else:
                    # Fallback to runner stats if no completed trades
                    stats = runner.calculate_strategy_stats(strategy_id, start_date=start_datetime, end_date=end_datetime)
                    total_pnl = stats.total_pnl
                    winning_trades = stats.winning_trades
                    losing_trades = stats.losing_trades
                    completed_count = stats.completed_trades
                    win_rate = stats.win_rate
                    avg_profit_per_trade = stats.avg_profit_per_trade
                    largest_win = stats.largest_win
                    largest_loss = stats.largest_loss
                    last_trade_at = stats.last_trade_at
                    total_trade_fees = None
                    total_funding_fees = None
                
                # Get all trades count
                all_trades = runner.get_trades(strategy_id)
                total_trades_count = len(all_trades) if all_trades else completed_count
                
                # Calculate unrealized PnL
                if start_datetime or end_datetime:
                    unrealized_pnl = 0.0  # Exclude unrealized when filtering by date
                else:
                    unrealized_pnl = strategy.unrealized_pnl or 0.0
                
                total_pnl_with_unrealized = total_pnl + unrealized_pnl
                
                # Create StrategyPerformance object
                perf = StrategyPerformance(
                    strategy_id=strategy_id,
                    strategy_name=strategy.name,
                    symbol=strategy.symbol,
                    strategy_type=strategy.strategy_type,
                    status=strategy.status,
                    total_realized_pnl=round(total_pnl, 4),
                    total_unrealized_pnl=round(unrealized_pnl, 4),
                    total_pnl=round(total_pnl_with_unrealized, 4),
                    total_trades=total_trades_count,
                    completed_trades=completed_count,
                    win_rate=round(win_rate, 2),
                    winning_trades=winning_trades,
                    losing_trades=losing_trades,
                    avg_profit_per_trade=round(avg_profit_per_trade, 4),
                    largest_win=round(largest_win, 4),
                    largest_loss=round(largest_loss, 4),
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
                    last_trade_at=last_trade_at,
                    last_signal=strategy.last_signal,
                    account_id=strategy.account_id,
                    auto_tuning_enabled=getattr(strategy, 'auto_tuning_enabled', False),
                    total_trade_fees=round(total_trade_fees, 4) if total_trade_fees is not None else None,
                    total_funding_fees=round(total_funding_fees, 4) if total_funding_fees is not None else None,
                )
                
                comparison_strategies.append(perf)
                
            except Exception as exc:
                logger.error(f"Error processing strategy {strategy_id} for comparison: {exc}", exc_info=True)
                continue
        
        if not comparison_strategies:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No strategies found for comparison after filtering"
            )
        
        # Calculate comparison metrics
        # We need to pass completed trades data for accurate profit factor calculation
        # For now, calculate from StrategyPerformance objects
        comparison_metrics = _calculate_comparison_metrics(comparison_strategies)
        
        # Build date range object
        date_range = None
        if start_datetime or end_datetime:
            date_range = DateRange(start_date=start_datetime, end_date=end_datetime)
        
        return StrategyComparisonResponse(
            strategies=comparison_strategies,
            comparison_metrics=comparison_metrics,
            date_range=date_range,
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Error generating strategy comparison: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare strategies: {str(exc)}"
        )


def _calculate_comparison_metrics(strategies: List[StrategyPerformance]) -> ComparisonSummary:
    """Calculate comparison metrics across strategies."""
    
    if not strategies:
        return ComparisonSummary()
    
    # Calculate Profit Factor (winning trades PnL / losing trades PnL)
    profit_factors = {}
    for s in strategies:
        if s.completed_trades > 0 and s.losing_trades > 0:
            # Calculate from realized PnL and trade counts
            # Profit Factor = Sum of winning trades PnL / Sum of losing trades PnL
            # Approximation: We estimate losing PnL from avg_loss and use total_realized_pnl
            # Better approach would be to recalculate from completed trades, but this works for comparison
            if s.largest_loss < 0 and s.largest_win > 0:
                # Estimate: if we have avg_profit_per_trade, we can estimate
                # For now, use a simple approximation
                total_realized = s.total_realized_pnl
                # Estimate losing trades total (conservative: use largest_loss as proxy)
                # This is an approximation - ideally we'd sum actual losing trades
                estimated_losing_total = abs(s.largest_loss) * s.losing_trades * 0.5  # Conservative estimate
                estimated_winning_total = total_realized + estimated_losing_total
                
                if estimated_losing_total > 0 and estimated_winning_total >= 0:
                    profit_factor = estimated_winning_total / estimated_losing_total
                    if profit_factor > 0:  # Only include valid profit factors
                        profit_factors[s.strategy_id] = profit_factor
    
    # Calculate Risk/Reward (avg win / abs(avg loss))
    risk_rewards = {}
    for s in strategies:
        if s.largest_loss < 0 and s.largest_win > 0:
            risk_reward = s.largest_win / abs(s.largest_loss)
            risk_rewards[s.strategy_id] = risk_reward
    
    # Calculate Trades/Day
    trades_per_day = {}
    for s in strategies:
        try:
            if s.created_at and s.last_trade_at:
                days = (s.last_trade_at - s.created_at).total_seconds() / 86400
                if days > 0 and s.completed_trades > 0:
                    trades_per_day[s.strategy_id] = s.completed_trades / days
            elif s.created_at:
                # Use current time if no last trade
                days = (datetime.now(timezone.utc) - s.created_at).total_seconds() / 86400
                if days > 0 and s.completed_trades > 0:
                    trades_per_day[s.strategy_id] = s.completed_trades / days
        except (TypeError, AttributeError) as e:
            logger.debug(f"Error calculating trades/day for strategy {s.strategy_id}: {e}")
            continue
    
    # Calculate Fee Impact (% of total PnL)
    fee_impacts = {}
    for s in strategies:
        if s.total_trade_fees is not None and s.total_pnl != 0:
            fee_impact = abs(s.total_trade_fees / s.total_pnl * 100) if s.total_pnl != 0 else 0.0
            fee_impacts[s.strategy_id] = fee_impact
    
    # Calculate Uptime % (time running / total time)
    uptime_percents = {}
    for s in strategies:
        try:
            if s.created_at:
                total_time = (datetime.now(timezone.utc) - s.created_at).total_seconds() / 86400
                if total_time > 0:
                    if s.started_at and s.stopped_at:
                        running_time = (s.stopped_at - s.started_at).total_seconds() / 86400
                    elif s.started_at:
                        running_time = (datetime.now(timezone.utc) - s.started_at).total_seconds() / 86400
                    else:
                        running_time = 0.0
                    
                    if running_time >= 0:
                        uptime_percents[s.strategy_id] = min((running_time / total_time) * 100, 100)  # Cap at 100%
        except (TypeError, AttributeError) as e:
            logger.debug(f"Error calculating uptime for strategy {s.strategy_id}: {e}")
            continue
    
    # Find best and worst for each metric
    def find_best_worst(metric_dict: Dict[str, float]) -> Optional[ComparisonMetric]:
        if not metric_dict:
            return None
        
        best_id = max(metric_dict.items(), key=lambda x: x[1])[0]
        worst_id = min(metric_dict.items(), key=lambda x: x[1])[0]
        
        return ComparisonMetric(
            best_strategy_id=best_id,
            worst_strategy_id=worst_id,
            best_value=metric_dict[best_id],
            worst_value=metric_dict[worst_id],
        )
    
    return ComparisonSummary(
        profit_factor=find_best_worst(profit_factors),
        risk_reward=find_best_worst(risk_rewards),
        trades_per_day=find_best_worst(trades_per_day),
        fee_impact=find_best_worst(fee_impacts),
        uptime_percent=find_best_worst(uptime_percents),
    )

