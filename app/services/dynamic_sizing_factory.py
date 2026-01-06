"""
Factory for creating DynamicPositionSizer instances based on risk configuration.

This factory creates DynamicPositionSizer instances per account when dynamic sizing
features are enabled in the risk management configuration.
"""

from __future__ import annotations

from typing import Optional, Dict
from uuid import UUID

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.core.binance_client_manager import BinanceClientManager
from app.risk.manager import RiskManager
from app.risk.dynamic_sizing import DynamicPositionSizer, DynamicSizingConfig
from app.models.risk_management import RiskManagementConfigResponse


class DynamicSizingFactory:
    """Factory for creating DynamicPositionSizer instances per account."""
    
    def __init__(
        self,
        client_manager: BinanceClientManager,
        risk_config_service: Optional[any] = None,  # RiskManagementService
        user_id: Optional[UUID] = None,
    ):
        """Initialize the factory.
        
        Args:
            client_manager: Binance client manager for getting clients
            risk_config_service: Service for getting risk configuration
            user_id: User ID for multi-user mode
        """
        self.client_manager = client_manager
        self.risk_config_service = risk_config_service
        self.user_id = user_id
        
        # Cache DynamicPositionSizer instances per account
        self._sizers: Dict[str, DynamicPositionSizer] = {}
    
    def get_dynamic_sizer(self, account_id: str) -> Optional[DynamicPositionSizer]:
        """Get or create DynamicPositionSizer for an account.
        
        Args:
            account_id: Account ID
            
        Returns:
            DynamicPositionSizer if dynamic sizing is enabled, None otherwise
        """
        # Check cache first
        if account_id in self._sizers:
            return self._sizers[account_id]
        
        # Get risk configuration
        if not self.risk_config_service or not self.user_id:
            return None
        
        risk_config = self.risk_config_service.get_risk_config(self.user_id, account_id)
        if not risk_config:
            return None
        
        # Check if any dynamic sizing feature is enabled
        if not (
            risk_config.volatility_based_sizing_enabled or
            risk_config.performance_based_adjustment_enabled or
            risk_config.kelly_criterion_enabled
        ):
            return None
        
        # Get client for this account
        client = self.client_manager.get_client(account_id)
        if not client:
            logger.warning(f"Cannot create DynamicPositionSizer: client not found for {account_id}")
            return None
        
        # Create base risk manager
        base_risk = RiskManager(client=client)
        
        # Create dynamic sizing config from risk config
        # Note: DynamicSizingConfig uses different field names than RiskManagementConfigResponse
        dynamic_config = DynamicSizingConfig(
            volatility_based_enabled=risk_config.volatility_based_sizing_enabled or False,
            performance_based_enabled=risk_config.performance_based_adjustment_enabled or False,
            kelly_criterion_enabled=risk_config.kelly_criterion_enabled or False,
            kelly_fraction=float(risk_config.kelly_fraction) if risk_config.kelly_fraction else 0.25,
            # Additional config fields with defaults
            atr_period=14,  # Default ATR period
            atr_multiplier=2.0,  # Default multiplier
            win_streak_boost=0.1,  # Default 10% per win
            loss_streak_reduction=0.15,  # Default 15% per loss
            max_win_streak_boost=0.5,  # Default max 50%
            max_loss_streak_reduction=0.5,  # Default max 50%
            min_trades_for_kelly=100,  # Default minimum trades
            max_kelly_position_pct=0.1,  # Default max 10%
        )
        
        # Create dynamic sizer
        dynamic_sizer = DynamicPositionSizer(
            client=client,
            base_risk_manager=base_risk,
            config=dynamic_config
        )
        
        # Cache it
        self._sizers[account_id] = dynamic_sizer
        
        logger.info(
            f"Created DynamicPositionSizer for account {account_id}: "
            f"volatility={dynamic_config.volatility_based_enabled}, "
            f"performance={dynamic_config.performance_based_enabled}, "
            f"kelly={dynamic_config.kelly_criterion_enabled}"
        )
        
        return dynamic_sizer
    
    def clear_cache(self, account_id: Optional[str] = None) -> None:
        """Clear cached sizers.
        
        Args:
            account_id: Account ID to clear (None = clear all)
        """
        if account_id:
            self._sizers.pop(account_id, None)
        else:
            self._sizers.clear()


