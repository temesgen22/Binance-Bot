"""Statistics calculation for strategies."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional
from uuid import UUID

from loguru import logger

from app.core.exceptions import StrategyNotFoundError
from app.core.redis_storage import RedisStorage
from app.models.order import OrderResponse
from app.models.strategy import OverallStats, StrategyState, StrategyStats, StrategySummary

if TYPE_CHECKING:
    from app.services.trade_service import TradeService
    from app.services.strategy_service import StrategyService


class StrategyStatistics:
    """Calculates statistics for strategies and overall performance."""
    
    def __init__(
        self,
        strategies: Dict[str, StrategySummary],
        trades: Dict[str, List[OrderResponse]],
        redis_storage: Optional[RedisStorage] = None,
        trade_service: Optional["TradeService"] = None,
        strategy_service: Optional["StrategyService"] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Initialize the statistics calculator.
        
        Args:
            strategies: Reference to strategies dictionary
            trades: Reference to trades dictionary
            redis_storage: Redis storage for loading trades (optional)
            trade_service: TradeService for loading trades from database (optional, for multi-user mode)
            strategy_service: StrategyService for looking up strategy UUID (optional, for multi-user mode)
            user_id: User ID for database queries (optional, for multi-user mode)
        """
        self._strategies = strategies
        self._trades = trades
        self.redis = redis_storage
        self.trade_service = trade_service
        self.strategy_service = strategy_service
        self.user_id = user_id
        self._overall_stats_cache: Optional[tuple] = None
    
    def calculate_strategy_stats(self, strategy_id: str) -> StrategyStats:
        """Calculate statistics for a specific strategy.
        
        Args:
            strategy_id: Strategy ID to calculate stats for
            
        Returns:
            StrategyStats with calculated statistics
            
        Raises:
            StrategyNotFoundError: If strategy does not exist
        """
        if strategy_id not in self._strategies:
            raise StrategyNotFoundError(strategy_id)
        
        strategy = self._strategies[strategy_id]
        
        # Ensure trades are loaded (from Redis if available, otherwise from memory)
        self._ensure_trades_loaded(strategy_id)
        
        trades = self._trades.get(strategy_id, [])
        
        # Log data source for transparency
        redis_status = "Redis" if (self.redis and self.redis.enabled) else "in-memory only"
        logger.debug(
            f"Calculating stats for {strategy_id} using {len(trades)} trades from {redis_status}"
        )
        
        # Calculate basic stats
        total_trades = len(trades)
        
        # Track positions to calculate PnL correctly for both LONG and SHORT
        # In One-Way mode: net position can be LONG (positive), SHORT (negative), or flat (zero)
        completed_trades = []
        position_queue = []  # List of (quantity, entry_price, side) tuples
        
        for trade in trades:
            entry_price = trade.avg_price or trade.price
            quantity = trade.executed_qty
            side = trade.side
            
            if side == "BUY":
                if position_queue and position_queue[0][2] == "SHORT":
                    # Closing or reducing SHORT position
                    remaining_qty = quantity
                    while remaining_qty > 0 and position_queue and position_queue[0][2] == "SHORT":
                        short_entry = position_queue[0]
                        short_qty = short_entry[0]
                        short_price = short_entry[1]
                        
                        if short_qty <= remaining_qty:
                            # Close entire SHORT position
                            close_qty = short_qty
                            position_queue.pop(0)
                        else:
                            # Partial close
                            close_qty = remaining_qty
                            position_queue[0] = (short_qty - remaining_qty, short_price, "SHORT")
                        
                        # PnL for SHORT: entry_price - exit_price (profit when price drops)
                        pnl = (short_price - entry_price) * close_qty
                        completed_trades.append({
                            "pnl": pnl,
                            "quantity": close_qty,
                            "side": "SHORT"
                        })
                        remaining_qty -= close_qty
                    
                    # If remaining quantity after closing SHORT, open LONG
                    if remaining_qty > 0:
                        position_queue.append((remaining_qty, entry_price, "LONG"))
                else:
                    # Opening or adding to LONG position
                    position_queue.append((quantity, entry_price, "LONG"))
            
            elif side == "SELL":
                if position_queue and position_queue[0][2] == "LONG":
                    # Closing or reducing LONG position
                    remaining_qty = quantity
                    while remaining_qty > 0 and position_queue and position_queue[0][2] == "LONG":
                        long_entry = position_queue[0]
                        long_qty = long_entry[0]
                        long_price = long_entry[1]
                        
                        if long_qty <= remaining_qty:
                            # Close entire LONG position
                            close_qty = long_qty
                            position_queue.pop(0)
                        else:
                            # Partial close
                            close_qty = remaining_qty
                            position_queue[0] = (long_qty - remaining_qty, long_price, "LONG")
                        
                        # PnL for LONG: exit_price - entry_price
                        pnl = (entry_price - long_price) * close_qty
                        completed_trades.append({
                            "pnl": pnl,
                            "quantity": close_qty,
                            "side": "LONG"
                        })
                        remaining_qty -= close_qty
                    
                    # If remaining quantity after closing LONG, open SHORT
                    if remaining_qty > 0:
                        position_queue.append((remaining_qty, entry_price, "SHORT"))
                else:
                    # Opening or adding to SHORT position
                    position_queue.append((quantity, entry_price, "SHORT"))
        
        # Calculate PnL statistics
        total_pnl = sum(t["pnl"] for t in completed_trades)
        winning_trades = len([t for t in completed_trades if t["pnl"] > 0])
        losing_trades = len([t for t in completed_trades if t["pnl"] < 0])
        win_rate = (winning_trades / len(completed_trades) * 100) if completed_trades else 0
        avg_profit_per_trade = total_pnl / len(completed_trades) if completed_trades else 0
        
        largest_win = max((t["pnl"] for t in completed_trades), default=0)
        largest_loss = min((t["pnl"] for t in completed_trades), default=0)
        
        # Get last trade timestamp - try to get from order_id or use current time
        last_trade_at = None
        if trades:
            # If trades have timestamps, use the latest; otherwise use current time
            last_trade_at = datetime.now(timezone.utc)
        
        logger.debug(
            f"Stats for {strategy_id}: {len(completed_trades)} completed trades, "
            f"total_pnl={total_pnl:.4f}, win_rate={win_rate:.2f}%"
        )
        
        return StrategyStats(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            symbol=strategy.symbol,
            total_trades=total_trades,
            completed_trades=len(completed_trades),
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
    
    def _ensure_trades_loaded(self, strategy_id: str) -> None:
        """Ensure trades for a strategy are available.
        
        Trades are always stored in memory (self._trades). This method tries multiple sources:
        1. In-memory trades (current session)
        2. Redis cache (if enabled)
        3. Database (if trade_service, strategy_service, and user_id are available)
        
        Args:
            strategy_id: Strategy ID (string) to ensure trades are loaded for
        """
        # Check if trades are already in memory
        if strategy_id in self._trades and len(self._trades[strategy_id]) > 0:
            trades_count = len(self._trades[strategy_id])
            logger.debug(
                f"Using {trades_count} in-memory trades for {strategy_id} "
                f"(Redis: {'enabled' if self.redis and self.redis.enabled else 'disabled'})"
            )
            return
        
        # Try to load from Redis (e.g., after server restart)
        if self.redis and self.redis.enabled:
            try:
                trades_data = self.redis.get_trades(strategy_id)
                if trades_data:
                    trades = []
                    for trade_data in trades_data:
                        try:
                            trade = OrderResponse(**trade_data)
                            # Filter out invalid trades (status NEW with zero execution)
                            if trade.status == "NEW" and trade.executed_qty == 0:
                                logger.debug(
                                    f"Skipping invalid trade {trade.order_id} for {strategy_id}: "
                                    f"status=NEW with zero execution"
                                )
                                continue
                            trades.append(trade)
                        except Exception as exc:
                            logger.warning(
                                f"Failed to parse trade data for {strategy_id}: {exc}, "
                                f"data: {trade_data}"
                            )
                            continue
                    if trades:
                        self._trades[strategy_id] = trades
                        logger.info(f"Loaded {len(trades)} trades for {strategy_id} from Redis")
                        return
            except Exception as exc:
                logger.warning(f"Failed to load trades for {strategy_id} from Redis: {exc}")
        
        # Try to load from database (if trade_service, strategy_service, and user_id are available)
        if self.trade_service and self.strategy_service and self.user_id:
            try:
                # Look up strategy UUID from database using strategy_id (string)
                db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, strategy_id)
                if db_strategy:
                    strategy_uuid = db_strategy.id  # UUID primary key
                    # Fetch trades from database
                    db_trades = self.trade_service.get_strategy_trades(self.user_id, strategy_uuid, limit=10000)
                    if db_trades:
                        self._trades[strategy_id] = db_trades
                        logger.info(f"Loaded {len(db_trades)} trades for {strategy_id} from database")
                        return
                    else:
                        logger.debug(f"No trades found in database for {strategy_id} (UUID: {strategy_uuid})")
                else:
                    logger.debug(f"Strategy {strategy_id} not found in database")
            except Exception as exc:
                logger.warning(f"Failed to load trades for {strategy_id} from database: {exc}")
        
        # No trades found in any source
        if strategy_id not in self._trades:
            self._trades[strategy_id] = []  # Initialize empty list to avoid repeated lookups
            logger.debug(
                f"No trades found for {strategy_id} in memory, Redis, or database. "
                f"Statistics will show zero values."
            )
    
    def calculate_overall_stats(self, use_cache: bool = True) -> OverallStats:
        """Calculate overall statistics across all strategies.
        
        Args:
            use_cache: If True, cache results for 30 seconds to avoid recalculating
            
        Returns:
            OverallStats with aggregate statistics
        """
        # Check cache if enabled
        if use_cache and self._overall_stats_cache:
            cached_time, cached_stats = self._overall_stats_cache
            cache_age = (datetime.now(timezone.utc) - cached_time).total_seconds()
            if cache_age < 30:  # Cache for 30 seconds
                logger.debug(f"Using cached overall stats (age: {cache_age:.1f}s)")
                return cached_stats
        
        # CRITICAL FIX: Create a copy of strategy IDs and values to avoid "dictionary changed size during iteration"
        # This prevents race conditions with async tasks modifying the dict
        strategy_ids = list(self._strategies.keys())
        strategy_values = list(self._strategies.values())
        
        # Calculate stats
        all_stats = []
        for strategy_id in strategy_ids:
            try:
                stats = self.calculate_strategy_stats(strategy_id)
                all_stats.append(stats)
            except Exception as exc:
                logger.warning(f"Error calculating stats for strategy {strategy_id}: {exc}")
                continue
        
        total_strategies = len(strategy_ids)
        active_strategies = len([s for s in strategy_values if s.status == StrategyState.running])
        
        total_trades = sum(s.total_trades for s in all_stats)
        completed_trades = sum(s.completed_trades for s in all_stats)
        total_pnl = sum(s.total_pnl for s in all_stats)
        
        all_winning = sum(s.winning_trades for s in all_stats)
        all_losing = sum(s.losing_trades for s in all_stats)
        win_rate = (all_winning / (all_winning + all_losing) * 100) if (all_winning + all_losing) > 0 else 0.0
        
        # Calculate average profit per trade
        avg_profit_per_trade = total_pnl / completed_trades if completed_trades > 0 else 0.0
        
        # Find best and worst performing strategies
        best_strategy = None
        worst_strategy = None
        if all_stats:
            best_stats = max(all_stats, key=lambda s: s.total_pnl)
            worst_stats = min(all_stats, key=lambda s: s.total_pnl)
            best_strategy = best_stats.strategy_id if best_stats.total_pnl > 0 else None
            worst_strategy = worst_stats.strategy_id if worst_stats.total_pnl < 0 else None
        
        result = OverallStats(
            total_strategies=total_strategies,
            active_strategies=active_strategies,
            total_trades=total_trades,
            completed_trades=completed_trades,
            total_pnl=round(total_pnl, 4),
            win_rate=round(win_rate, 2),
            winning_trades=all_winning,
            losing_trades=all_losing,
            avg_profit_per_trade=round(avg_profit_per_trade, 4),
            best_performing_strategy=best_strategy,
            worst_performing_strategy=worst_strategy,
        )
        
        # Cache result
        if use_cache:
            self._overall_stats_cache = (datetime.now(timezone.utc), result)
        
        return result


