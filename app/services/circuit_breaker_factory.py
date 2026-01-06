"""
Factory for creating CircuitBreaker instances based on risk configuration.

This factory creates CircuitBreaker instances per account when circuit breaker
features are enabled in the risk management configuration.
"""

from __future__ import annotations

from typing import Optional, Dict
from uuid import UUID

from loguru import logger

from app.risk.circuit_breaker import CircuitBreaker
from app.models.risk_management import RiskManagementConfigResponse
from app.services.risk_management_service import RiskManagementService


class CircuitBreakerFactory:
    """Factory for creating CircuitBreaker instances per account."""
    
    def __init__(
        self,
        risk_config_service: Optional[RiskManagementService] = None,
        user_id: Optional[UUID] = None,
        db_service: Optional[any] = None,
        strategy_runner: Optional[any] = None,
        trade_service: Optional[any] = None,
    ):
        """Initialize the factory.
        
        Args:
            risk_config_service: Service for getting risk configuration
            user_id: User ID for multi-user mode
            db_service: Database service for persisting breaker events
            strategy_runner: StrategyRunner for pausing strategies
            trade_service: TradeService for querying trades
        """
        self.risk_config_service = risk_config_service
        self.user_id = user_id
        self.db_service = db_service
        self.strategy_runner = strategy_runner
        self.trade_service = trade_service
        
        # Cache CircuitBreaker instances per account
        self._breakers: Dict[str, CircuitBreaker] = {}
    
    def get_circuit_breaker(self, account_id: str) -> Optional[CircuitBreaker]:
        """Get or create CircuitBreaker for an account.
        
        Args:
            account_id: Account ID
            
        Returns:
            CircuitBreaker if circuit breakers are enabled, None otherwise
        """
        # Check cache first
        if account_id in self._breakers:
            return self._breakers[account_id]
        
        # Get risk configuration
        if not self.risk_config_service or not self.user_id:
            return None
        
        risk_config = self.risk_config_service.get_risk_config(self.user_id, account_id)
        if not risk_config:
            return None
        
        # Check if circuit breakers are enabled
        if not risk_config.circuit_breaker_enabled:
            return None
        
        # Bug #3: Create CircuitBreaker with RiskManagementConfigResponse
        circuit_breaker = CircuitBreaker(
            account_id=account_id,
            config=risk_config,  # Bug #3: Pass RiskManagementConfigResponse
            db_service=self.db_service,
            user_id=self.user_id,
            strategy_runner=self.strategy_runner,
            trade_service=self.trade_service,
        )
        
        # Cache it
        self._breakers[account_id] = circuit_breaker
        
        logger.info(
            f"Created CircuitBreaker for account {account_id}: "
            f"enabled={risk_config.circuit_breaker_enabled}, "
            f"max_consecutive_losses={risk_config.max_consecutive_losses}"
        )
        
        return circuit_breaker
    
    def clear_cache(self, account_id: Optional[str] = None) -> None:
        """Clear cached breakers.
        
        Args:
            account_id: Account ID to clear (None = clear all)
        """
        if account_id:
            self._breakers.pop(account_id, None)
        else:
            self._breakers.clear()


