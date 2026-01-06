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
        
        Args:
            strategy_id: Strategy ID
            recent_trades: Recent trades (most recent first)
            
        Returns:
            CircuitBreakerState if triggered, None otherwise
        """
        if not self.config or not self.config.circuit_breaker_enabled:
            return None
        
        max_consecutive = self.config.max_consecutive_losses or 5
        
        # Count consecutive losses from most recent trades
        consecutive_losses = 0
        for trade in recent_trades:
            # Determine if trade was a loss
            # For completed trades, check net_pnl
            if hasattr(trade, 'net_pnl'):
                if trade.net_pnl < 0:
                    consecutive_losses += 1
                else:
                    break  # Win breaks the streak
            elif hasattr(trade, 'realized_pnl'):
                if trade.realized_pnl < 0:
                    consecutive_losses += 1
                else:
                    break
            else:
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
        """Pause a strategy.
        
        Args:
            strategy_id: Strategy ID
            reason: Reason for pausing
        """
        if not self.strategy_runner:
            return
        
        try:
            # Update strategy status to paused_by_risk
            if hasattr(self.strategy_runner, 'state_manager'):
                self.strategy_runner.state_manager.update_strategy_in_db(
                    strategy_id,
                    save_to_redis=True,
                    status='paused_by_risk',
                    meta={'pause_reason': reason, 'paused_at': datetime.now(timezone.utc).isoformat()}
                )
            logger.info(f"Paused strategy {strategy_id} due to circuit breaker: {reason}")
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
        """Resume a strategy.
        
        Args:
            strategy_id: Strategy ID
        """
        if not self.strategy_runner:
            return
        
        try:
            # Update strategy status back to running
            if hasattr(self.strategy_runner, 'state_manager'):
                self.strategy_runner.state_manager.update_strategy_in_db(
                    strategy_id,
                    save_to_redis=True,
                    status='running'
                )
            logger.info(f"Resumed strategy {strategy_id}")
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
        """Get realized PnL from closed trades since start_time."""
        if not self.trade_service or not self.user_id:
            return 0.0
        
        # TODO: Query trades from database filtered by:
        # - account_id
        # - timestamp >= start_time
        # - closed trades only
        # - Sum PnL from closed trades
        
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



