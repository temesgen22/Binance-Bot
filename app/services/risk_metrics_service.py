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
            
            # Convert trades to format expected by calculator
            trade_data = []
            for trade in trades:
                trade_data.append({
                    "pnl": float(trade.realized_pnl or 0),
                    "timestamp": trade.created_at or datetime.now(timezone.utc),
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







