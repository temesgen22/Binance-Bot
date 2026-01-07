"""
Circuit breaker system for automatic trading pause on adverse conditions.

Phase 3: Advanced Protection
- Consecutive loss detection
- Rapid loss detection
- Cooldown period management
- Automatic strategy pausing
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
from uuid import UUID

from loguru import logger

from app.core.exceptions import CircuitBreakerActiveError
from app.models.risk_management import RiskManagementConfigResponse


@dataclass
class CircuitBreakerState:
    """State of a circuit breaker."""
    breaker_type: str  # 'consecutive_losses', 'rapid_loss', 'drawdown', etc.
    scope: str  # 'account' or 'strategy'
    triggered_at: datetime
    trigger_value: float
    threshold_value: float
    status: str  # 'active', 'resolved', 'manual_override'
    cooldown_until: Optional[datetime] = None
    strategy_id: Optional[str] = None  # For strategy-level breakers


class CircuitBreaker:
    """Circuit breaker for automatic trading pause on adverse conditions.
    
    Features:
    - Consecutive loss detection
    - Rapid loss detection (time-windowed)
    - Cooldown period management
    - Automatic strategy pausing
    """
    
    def __init__(
        self,
        account_id: str,
        config: Optional[RiskManagementConfigResponse],
        db_service: Optional[any] = None,
        user_id: Optional[UUID] = None,
        strategy_runner: Optional[any] = None,
        trade_service: Optional[any] = None,
    ):
        """Initialize circuit breaker.
        
        Args:
            account_id: Binance account ID
            config: Risk management configuration
            db_service: Database service for persisting breaker events
            user_id: User UUID
            strategy_runner: StrategyRunner for pausing strategies
            trade_service: TradeService for querying trades
        """
        self.account_id = account_id
        self.config = config
        self.db_service = db_service
        self.user_id = user_id
        self.strategy_runner = strategy_runner
        self.trade_service = trade_service
        
        # Track active breakers per scope
        self._active_breakers: Dict[str, Dict[str, CircuitBreakerState]] = {}
        # Format: {scope: {breaker_type: CircuitBreakerState}}
        # scope = 'account' or 'strategy_id'
    
    def is_active(
        self,
        account_id: str,
        strategy_id: Optional[str] = None
    ) -> bool:
        """Check if any circuit breaker is active.
        
        Args:
            account_id: Account ID
            strategy_id: Strategy ID (optional, for strategy-level check)
            
        Returns:
            True if any breaker is active, False otherwise
        """
        # Check account-level breakers
        account_breakers = self._active_breakers.get('account', {})
        for breaker_state in account_breakers.values():
            if breaker_state.status == 'active':
                # Check cooldown
                if breaker_state.cooldown_until and datetime.now(timezone.utc) < breaker_state.cooldown_until:
                    return True
                # Cooldown expired - resolve breaker
                breaker_state.status = 'resolved'
        
        # Check strategy-level breakers
        if strategy_id:
            strategy_breakers = self._active_breakers.get(strategy_id, {})
            for breaker_state in strategy_breakers.values():
                if breaker_state.status == 'active':
                    # Check cooldown
                    if breaker_state.cooldown_until and datetime.now(timezone.utc) < breaker_state.cooldown_until:
                        return True
                    # Cooldown expired - resolve breaker
                    breaker_state.status = 'resolved'
        
        return False
    
    def check_consecutive_losses(
        self,
        strategy_id: str,
        recent_trades: List[any]  # List of OrderResponse or completed trades
    ) -> Optional[CircuitBreakerState]:
        """Check for consecutive loss circuit breaker.
        
        CRITICAL: Uses trade matching to count completed trade cycles, not individual trades.
        This ensures we count wins/losses correctly (entry+exit pairs).
        
        Args:
            strategy_id: Strategy ID
            recent_trades: Recent trades (OrderResponse objects - will be matched to completed positions)
            
        Returns:
            CircuitBreakerState if triggered, None otherwise
        """
        if not self.config or not self.config.circuit_breaker_enabled:
            return None
        
        max_consecutive = self.config.max_consecutive_losses or 5
        
        # CRITICAL: Match trades to completed positions (same logic as reports page)
        # This ensures we count completed trade cycles, not individual entry/exit trades
        from app.services.trade_matcher import match_trades_to_completed_positions
        from app.models.order import OrderResponse
        
        # Filter to only OrderResponse objects (raw trades)
        order_responses = [t for t in recent_trades if isinstance(t, OrderResponse)]
        
        if not order_responses:
            # If already completed trades, use them directly
            completed_trades = [t for t in recent_trades if hasattr(t, 'net_pnl') or hasattr(t, 'pnl_usd')]
        else:
            # Match raw trades to completed positions
            try:
                completed_trades = match_trades_to_completed_positions(
                    order_responses,
                    include_fees=True
                )
            except Exception as e:
                logger.warning(f"Error matching trades for consecutive loss check: {e}")
                # Fallback: use raw trades if matching fails
                completed_trades = order_responses
        
        # Count consecutive losses from most recent completed trades (most recent first)
        # Sort by exit time (most recent first)
        if completed_trades:
            from app.risk.utils import get_timestamp_from_completed_trade
            # Use get_timestamp_from_completed_trade for consistent timestamp extraction
            # Ensure we always get a datetime object, not a Mock
            def get_sort_key(trade):
                timestamp = get_timestamp_from_completed_trade(trade, fallback=datetime.min.replace(tzinfo=timezone.utc))
                # If timestamp is not a datetime (e.g., Mock), use fallback
                if not isinstance(timestamp, datetime):
                    return datetime.min.replace(tzinfo=timezone.utc)
                return timestamp
            
            completed_trades.sort(key=get_sort_key, reverse=True)
        
        consecutive_losses = 0
        for trade in completed_trades:
            # Determine if trade was a loss using shared utility function
            from app.risk.utils import get_pnl_from_completed_trade
            pnl = get_pnl_from_completed_trade(trade)
            if pnl < 0:
                consecutive_losses += 1
            else:
                break  # Win breaks the streak
                # Can't determine - skip
                continue
        
        if consecutive_losses >= max_consecutive:
            # Trigger breaker
            breaker_state = CircuitBreakerState(
                breaker_type='consecutive_losses',
                scope='strategy',
                triggered_at=datetime.now(timezone.utc),
                trigger_value=consecutive_losses,
                threshold_value=max_consecutive,
                status='active',
                strategy_id=strategy_id,
                cooldown_until=datetime.now(timezone.utc) + timedelta(hours=1)  # 1 hour cooldown
            )
            
            # Store breaker
            if strategy_id not in self._active_breakers:
                self._active_breakers[strategy_id] = {}
            self._active_breakers[strategy_id]['consecutive_losses'] = breaker_state
            
            # Pause strategy
            self._pause_strategy(strategy_id, 'consecutive_losses')
            
            # Persist to database
            self._persist_breaker_event(breaker_state)
            
            logger.warning(
                f"Circuit breaker triggered for {strategy_id}: "
                f"{consecutive_losses} consecutive losses (threshold: {max_consecutive})"
            )
            
            return breaker_state
        
        return None
    
    def check_rapid_loss(
        self,
        account_id: str,
        time_window_minutes: int = 60
    ) -> Optional[CircuitBreakerState]:
        """Check for rapid loss circuit breaker.
        
        Args:
            account_id: Account ID
            time_window_minutes: Time window in minutes (default 60)
            
        Returns:
            CircuitBreakerState if triggered, None otherwise
        """
        if not self.config or not self.config.circuit_breaker_enabled:
            return None
        
        rapid_loss_threshold = self.config.rapid_loss_threshold_pct or 0.05  # 5%
        
        # Get realized PnL for time window
        window_start = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        realized_pnl = self._get_realized_pnl(account_id, window_start)
        
        # Get account balance
        balance = self._get_account_balance(account_id)
        if not balance or balance <= 0:
            return None
        
        # Calculate loss percentage
        loss_pct = abs(realized_pnl) / balance if realized_pnl < 0 else 0
        
        if loss_pct >= rapid_loss_threshold:
            # Trigger breaker
            breaker_state = CircuitBreakerState(
                breaker_type='rapid_loss',
                scope='account',
                triggered_at=datetime.now(timezone.utc),
                trigger_value=loss_pct,
                threshold_value=rapid_loss_threshold,
                status='active',
                cooldown_until=datetime.now(timezone.utc) + timedelta(hours=2)  # 2 hour cooldown
            )
            
            # Store breaker
            if 'account' not in self._active_breakers:
                self._active_breakers['account'] = {}
            self._active_breakers['account']['rapid_loss'] = breaker_state
            
            # Pause all strategies for this account
            self._pause_all_strategies(account_id, 'rapid_loss')
            
            # Persist to database
            self._persist_breaker_event(breaker_state)
            
            logger.warning(
                f"Rapid loss circuit breaker triggered for {account_id}: "
                f"{loss_pct:.2%} loss in {time_window_minutes} minutes (threshold: {rapid_loss_threshold:.2%})"
            )
            
            return breaker_state
        
        return None
    
    def resolve_breaker(
        self,
        breaker_type: str,
        scope: str,
        strategy_id: Optional[str] = None,
        manual: bool = False
    ) -> bool:
        """Manually resolve a circuit breaker.
        
        Args:
            breaker_type: Type of breaker ('consecutive_losses', 'rapid_loss', etc.)
            scope: Scope ('account' or 'strategy')
            strategy_id: Strategy ID (for strategy-level breakers)
            manual: True if manually resolved, False if auto-resolved
            
        Returns:
            True if breaker was resolved, False if not found
        """
        scope_key = scope if scope == 'account' else (strategy_id or 'unknown')
        breakers = self._active_breakers.get(scope_key, {})
        
        if breaker_type not in breakers:
            return False
        
        breaker_state = breakers[breaker_type]
        breaker_state.status = 'manual_override' if manual else 'resolved'
        breaker_state.cooldown_until = None
        
        # Resume strategies
        if scope == 'account':
            self._resume_all_strategies(scope_key)
        elif strategy_id:
            self._resume_strategy(strategy_id)
        
        # Update database
        self._update_breaker_event(breaker_state)
        
        logger.info(
            f"Circuit breaker resolved: {breaker_type} for {scope_key} "
            f"({'manual' if manual else 'auto'})"
        )
        
        return True
    
    def _pause_strategy(self, strategy_id: str, reason: str) -> None:
        """Pause a strategy by stopping it and setting status to paused_by_risk.
        
        This actually STOPS the strategy (cancels the running task), not just pauses it.
        The status 'paused_by_risk' indicates it was stopped by risk management,
        not manually by the user.
        
        Args:
            strategy_id: Strategy ID
            reason: Reason for pausing
        """
        if not self.strategy_runner:
            return
        
        try:
            # Actually stop the strategy if it's running
            # Cancel the running task (similar to StrategyRunner.stop())
            if hasattr(self.strategy_runner, '_tasks') and strategy_id in self.strategy_runner._tasks:
                task = self.strategy_runner._tasks.get(strategy_id)
                if task and not task.done():
                    # Cancel the running task - this will cause the strategy loop to exit
                    task.cancel()
                    # Remove from tasks dict
                    self.strategy_runner._tasks.pop(strategy_id, None)
                    logger.info(f"Cancelled running task for strategy {strategy_id} due to circuit breaker")
            
            # Update strategy status to paused_by_risk (which is effectively "stopped" but with reason)
            from app.models.strategy import StrategyState
            if hasattr(self.strategy_runner, 'state_manager'):
                self.strategy_runner.state_manager.update_strategy_in_db(
                    strategy_id,
                    save_to_redis=True,
                    status=StrategyState.paused_by_risk.value,  # Use enum value
                    meta={'pause_reason': reason, 'paused_at': datetime.now(timezone.utc).isoformat()}
                )
            
            # Also update in-memory status if strategy is in memory
            if hasattr(self.strategy_runner, '_strategies') and strategy_id in self.strategy_runner._strategies:
                self.strategy_runner._strategies[strategy_id].status = StrategyState.paused_by_risk
            
            logger.info(f"Paused (stopped) strategy {strategy_id} due to circuit breaker: {reason}")
        except Exception as e:
            logger.error(f"Failed to pause strategy {strategy_id}: {e}")
    
    def _pause_all_strategies(self, account_id: str, reason: str) -> None:
        """Pause all strategies for an account.
        
        Args:
            account_id: Account ID
            reason: Reason for pausing
        """
        if not self.strategy_runner:
            return
        
        try:
            # Get all strategies for this account
            strategies = self.strategy_runner._strategies.values()
            account_strategies = [s for s in strategies if s.account_id == account_id]
            
            for strategy in account_strategies:
                self._pause_strategy(strategy.id, reason)
        except Exception as e:
            logger.error(f"Failed to pause strategies for account {account_id}: {e}")
    
    def _resume_strategy(self, strategy_id: str) -> None:
        """Resume a strategy that was paused by risk management.
        
        This changes status from 'paused_by_risk' back to 'stopped'.
        The strategy will need to be manually started via StrategyRunner.start().
        This is safer than auto-resuming.
        
        Args:
            strategy_id: Strategy ID
        """
        if not self.strategy_runner:
            return
        
        try:
            # Update strategy status back to stopped (user can start it manually)
            # This is safer than auto-resuming
            if hasattr(self.strategy_runner, 'state_manager'):
                from app.models.strategy import StrategyState
                self.strategy_runner.state_manager.update_strategy_in_db(
                    strategy_id,
                    save_to_redis=True,
                    status=StrategyState.stopped.value
                )
            logger.info(f"Resumed strategy {strategy_id} from paused_by_risk (status set to stopped, can be started manually)")
        except Exception as e:
            logger.error(f"Failed to resume strategy {strategy_id}: {e}")
    
    def _resume_all_strategies(self, account_id: str) -> None:
        """Resume all strategies for an account.
        
        Args:
            account_id: Account ID
        """
        if not self.strategy_runner:
            return
        
        try:
            # Get all strategies for this account
            strategies = self.strategy_runner._strategies.values()
            account_strategies = [s for s in strategies if s.account_id == account_id]
            
            for strategy in account_strategies:
                self._resume_strategy(strategy.id)
        except Exception as e:
            logger.error(f"Failed to resume strategies for account {account_id}: {e}")
    
    def _get_realized_pnl(
        self,
        account_id: str,
        start_time: datetime
    ) -> float:
        """Get realized PnL from closed trades since start_time.
        
        CRITICAL: Uses trade matching to calculate PnL from completed trade cycles,
        not individual entry/exit trades. This ensures accurate loss calculations.
        """
        if not self.trade_service or not self.user_id:
            return 0.0
        
        try:
            # Get all trades for this account since start_time
            trades = self.trade_service.get_trades_by_account(self.user_id, account_id)
            
            # Filter by timestamp
            filtered_trades = [
                t for t in trades
                if t.timestamp and t.timestamp >= start_time
            ]
            
            if not filtered_trades:
                return 0.0
            
            # CRITICAL: Match trades to completed positions (same logic as reports page)
            from app.services.trade_matcher import match_trades_to_completed_positions
            from app.models.order import OrderResponse
            
            # Convert database trades to OrderResponse format
            order_responses = []
            for db_trade in filtered_trades:
                order_responses.append(OrderResponse(
                    symbol=db_trade.symbol or "",
                    order_id=db_trade.order_id or 0,
                    status=db_trade.status or "FILLED",
                    side=db_trade.side or "BUY",
                    price=float(db_trade.price or 0),
                    avg_price=float(db_trade.avg_price or db_trade.price or 0),
                    executed_qty=float(db_trade.executed_qty or 0),
                    timestamp=db_trade.timestamp,
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
            completed_trades = match_trades_to_completed_positions(
                order_responses,
                include_fees=True
            )
            
            # Sum net PnL from completed trades
            total_pnl = sum(completed.net_pnl for completed in completed_trades)
            
            return total_pnl
        except Exception as e:
            logger.warning(f"Error calculating realized PnL for account {account_id}: {e}")
            return 0.0
    
    def _get_account_balance(self, account_id: str) -> Optional[float]:
        """Get account balance in USDT."""
        if not self.strategy_runner:
            return None
        
        try:
            # Get client for this account
            if hasattr(self.strategy_runner, 'client_manager'):
                client = self.strategy_runner.client_manager.get_client(account_id)
            elif hasattr(self.strategy_runner, 'client'):
                client = self.strategy_runner.client
            else:
                return None
            
            if not client:
                return None
            
            # Get balance from Binance
            balance = client.futures_account_balance()
            return balance
        except Exception as e:
            logger.warning(f"Failed to get account balance for {account_id}: {e}")
            return None
    
    def _persist_breaker_event(self, breaker_state: CircuitBreakerState) -> None:
        """Persist circuit breaker event to database.
        
        Args:
            breaker_state: Breaker state to persist
        """
        if not self.db_service or not self.user_id:
            return
        
        try:
            from app.models.db_models import CircuitBreakerEvent as DBCircuitBreakerEvent
            from uuid import uuid4
            
            # Get account UUID
            account_uuid = None
            if self.db_service:
                from app.models.db_models import Account
                account = self.db_service.db.query(Account).filter(
                    Account.user_id == self.user_id,
                    Account.account_id.ilike(breaker_state.scope if breaker_state.scope == 'account' else self.account_id)
                ).first()
                if account:
                    account_uuid = account.id
            
            # Get strategy UUID if strategy-level
            strategy_uuid = None
            if breaker_state.strategy_id and self.db_service:
                from app.models.db_models import Strategy
                strategy = self.db_service.db.query(Strategy).filter(
                    Strategy.user_id == self.user_id,
                    Strategy.strategy_id == breaker_state.strategy_id
                ).first()
                if strategy:
                    strategy_uuid = strategy.id
            
            db_event = DBCircuitBreakerEvent(
                id=uuid4(),
                user_id=self.user_id,
                account_id=account_uuid,
                strategy_id=strategy_uuid,
                breaker_type=breaker_state.breaker_type,
                breaker_scope=breaker_state.scope,
                trigger_value=breaker_state.trigger_value,
                threshold_value=breaker_state.threshold_value,
                triggered_at=breaker_state.triggered_at,
                status=breaker_state.status,
                meta_data={}
            )
            
            self.db_service.db.add(db_event)
            self.db_service.db.commit()
        except Exception as e:
            logger.error(f"Failed to persist circuit breaker event: {e}")
    
    def _update_breaker_event(self, breaker_state: CircuitBreakerState) -> None:
        """Update circuit breaker event in database.
        
        Args:
            breaker_state: Breaker state to update
        """
        if not self.db_service or not self.user_id:
            return
        
        try:
            from app.models.db_models import CircuitBreakerEvent as DBCircuitBreakerEvent
            
            # Find the event
            # This is simplified - in production, you'd track the event ID
            # For now, we'll find the most recent active event of this type
            event = self.db_service.db.query(DBCircuitBreakerEvent).filter(
                DBCircuitBreakerEvent.user_id == self.user_id,
                DBCircuitBreakerEvent.breaker_type == breaker_state.breaker_type,
                DBCircuitBreakerEvent.status == 'active'
            ).order_by(DBCircuitBreakerEvent.triggered_at.desc()).first()
            
            if event:
                event.status = breaker_state.status
                event.resolved_at = datetime.now(timezone.utc)
                self.db_service.db.commit()
        except Exception as e:
            logger.error(f"Failed to update circuit breaker event: {e}")
    
    def get_active_breakers(
        self,
        account_id: Optional[str] = None,
        strategy_id: Optional[str] = None
    ) -> List[CircuitBreakerState]:
        """Get all active circuit breakers.
        
        Args:
            account_id: Account ID (optional)
            strategy_id: Strategy ID (optional)
            
        Returns:
            List of active breaker states
        """
        active = []
        
        # Account-level breakers
        if account_id:
            account_breakers = self._active_breakers.get('account', {})
            for breaker_state in account_breakers.values():
                if breaker_state.status == 'active':
                    active.append(breaker_state)
        
        # Strategy-level breakers
        if strategy_id:
            strategy_breakers = self._active_breakers.get(strategy_id, {})
            for breaker_state in strategy_breakers.values():
                if breaker_state.status == 'active':
                    active.append(breaker_state)
        
        return active





