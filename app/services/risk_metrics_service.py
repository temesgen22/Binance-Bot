"""
Service for managing risk metrics updates and real-time monitoring.

Phase 4 Week 8: Real-time Metrics Updates
- Periodic metrics calculation
- Real-time updates
- Metrics caching
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from uuid import UUID

from loguru import logger

from app.risk.metrics_calculator import RiskMetricsCalculator, RiskMetrics
from app.services.trade_service import TradeService
from app.services.strategy_service import StrategyService


class RiskMetricsService:
    """Service for managing risk metrics updates."""
    
    def __init__(
        self,
        trade_service: TradeService,
        strategy_service: StrategyService,
        update_interval_seconds: int = 60,  # Update every minute
    ):
        """Initialize risk metrics service.
        
        Args:
            trade_service: Trade service for fetching trades
            strategy_service: Strategy service for fetching strategies
            update_interval_seconds: Update interval in seconds
        """
        self.trade_service = trade_service
        self.strategy_service = strategy_service
        self.update_interval = update_interval_seconds
        
        # Cache for metrics: {strategy_id: (metrics, timestamp)}
        self._metrics_cache: Dict[str, tuple[RiskMetrics, datetime]] = {}
        
        # Background task
        self._update_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start background metrics update task."""
        if self._running:
            return
        
        self._running = True
        self._update_task = asyncio.create_task(self._update_loop())
        logger.info("Risk metrics service started")
    
    async def stop(self) -> None:
        """Stop background metrics update task."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Risk metrics service stopped")
    
    async def _update_loop(self) -> None:
        """Background loop for updating metrics."""
        while self._running:
            try:
                await self.update_all_metrics()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics update loop: {e}")
                await asyncio.sleep(self.update_interval)
    
    async def update_all_metrics(self) -> None:
        """Update metrics for all active strategies."""
        try:
            # Get all active strategies
            # This would fetch from database in production
            # For now, update cached strategies
            
            for strategy_id in list(self._metrics_cache.keys()):
                try:
                    await self.update_strategy_metrics(strategy_id)
                except Exception as e:
                    logger.warning(f"Failed to update metrics for {strategy_id}: {e}")
        except Exception as e:
            logger.error(f"Error updating all metrics: {e}")
    
    async def update_strategy_metrics(
        self,
        strategy_id: str,
        user_id: Optional[UUID] = None,
        force: bool = False
    ) -> Optional[RiskMetrics]:
        """Update metrics for a specific strategy.
        
        Args:
            strategy_id: Strategy ID
            user_id: User ID (optional)
            force: Force update even if cached
            
        Returns:
            Updated RiskMetrics or None
        """
        try:
            # Check cache
            if not force and strategy_id in self._metrics_cache:
                metrics, cached_at = self._metrics_cache[strategy_id]
                if datetime.now(timezone.utc) - cached_at < timedelta(seconds=self.update_interval):
                    return metrics
            
            # Get trades for strategy
            if not user_id:
                # Try to get from strategy
                # This is simplified - in production would fetch from database
                return None
            
            trades = self.trade_service.get_trades_by_strategy(user_id, UUID(strategy_id))
            
            if not trades:
                return None
            
            # CRITICAL: Match trades to completed positions (same logic as reports page)
            # This ensures we calculate metrics from completed trade cycles, not individual trades
            from app.services.trade_matcher import match_trades_to_completed_positions
            from app.models.order import OrderResponse
            
            # Convert database trades to OrderResponse format
            order_responses = []
            for db_trade in trades:
                order_responses.append(OrderResponse(
                    symbol=db_trade.symbol or "",
                    order_id=db_trade.order_id or 0,
                    status=db_trade.status or "FILLED",
                    side=db_trade.side or "BUY",
                    price=float(db_trade.price or 0),
                    avg_price=float(db_trade.avg_price or db_trade.price or 0),
                    executed_qty=float(db_trade.executed_qty or 0),
                    timestamp=db_trade.timestamp or db_trade.created_at,
                    commission=float(db_trade.commission) if db_trade.commission else None,
                    commission_asset=db_trade.commission_asset,
                    leverage=db_trade.leverage,
                    position_side=db_trade.position_side,
                    update_time=db_trade.update_time,
                    time_in_force=db_trade.time_in_force,
                    order_type=db_trade.order_type,
                    notional_value=float(db_trade.notional_value) if db_trade.notional_value else None,
                    cummulative_quote_qty=float(db_trade.cummulative_quote_qty) if db_trade.cummulative_quote_qty else None,
                    initial_margin=float(db_trade.initial_margin) if db_trade.initial_margin else None,
                    margin_type=db_trade.margin_type,
                ))
            
            # Match trades to completed positions
            try:
                completed_trades = match_trades_to_completed_positions(
                    order_responses,
                    include_fees=True
                )
            except Exception as e:
                logger.warning(f"Error matching trades for metrics: {e}, using raw trades")
                completed_trades = []
                # Fallback: use realized_pnl from database if matching fails
                for db_trade in trades:
                    if db_trade.realized_pnl:
                        completed_trades.append(type('obj', (object,), {
                            'net_pnl': float(db_trade.realized_pnl),
                            'exit_time': db_trade.timestamp or db_trade.created_at,
                        })())
            
            # Convert completed trades to format expected by calculator
            trade_data = []
            for completed_trade in completed_trades:
                # Completed trades from matcher use net_pnl
                pnl_value = getattr(completed_trade, 'net_pnl', getattr(completed_trade, 'pnl_usd', getattr(completed_trade, 'realized_pnl', 0)))
                trade_data.append({
                    "pnl": float(pnl_value or 0),
                    "timestamp": getattr(completed_trade, 'exit_time', None) or 
                                getattr(completed_trade, 'timestamp', None) or 
                                datetime.now(timezone.utc),
                })
            
            # Get balances (simplified - would fetch from account)
            initial_balance = 10000.0
            current_balance = 10000.0
            
            # Calculate metrics
            calculator = RiskMetricsCalculator(lookback_days=90)
            metrics = calculator.calculate_metrics(
                trades=trade_data,
                initial_balance=initial_balance,
                current_balance=current_balance,
            )
            
            # Cache the result
            self._metrics_cache[strategy_id] = (metrics, datetime.now(timezone.utc))
            
            return metrics
        except Exception as e:
            logger.error(f"Error updating metrics for strategy {strategy_id}: {e}")
            return None
    
    def get_cached_metrics(self, strategy_id: str) -> Optional[RiskMetrics]:
        """Get cached metrics for a strategy.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            Cached RiskMetrics or None
        """
        if strategy_id in self._metrics_cache:
            metrics, _ = self._metrics_cache[strategy_id]
            return metrics
        return None
    
    def clear_cache(self, strategy_id: Optional[str] = None) -> None:
        """Clear metrics cache.
        
        Args:
            strategy_id: Strategy ID to clear (None = clear all)
        """
        if strategy_id:
            self._metrics_cache.pop(strategy_id, None)
        else:
            self._metrics_cache.clear()
        logger.info(f"Cleared metrics cache for {strategy_id or 'all strategies'}")








