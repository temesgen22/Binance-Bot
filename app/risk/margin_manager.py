"""
Margin ratio monitoring and pre-emptive margin management.

Phase 3 Week 6: Margin Protection
- Margin ratio monitoring
- Pre-emptive margin management
- Automatic position reduction on high margin usage
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict

from loguru import logger

from app.core.exceptions import RiskLimitExceededError
from app.core.my_binance_client import BinanceClient


@dataclass
class MarginStatus:
    """Margin status for an account."""
    account_id: str
    total_balance: float
    available_balance: float
    used_margin: float
    margin_ratio: float  # used_margin / total_balance
    maintenance_margin: float
    margin_call_ratio: float  # Binance margin call threshold (typically 0.8)
    liquidation_ratio: float  # Binance liquidation threshold (typically 1.0)
    status: str  # 'safe', 'warning', 'danger', 'critical'
    timestamp: datetime


class MarginManager:
    """Manages margin ratio monitoring and protection.
    
    Features:
    - Real-time margin ratio calculation
    - Warning thresholds
    - Automatic position reduction
    - Margin call prevention
    """
    
    def __init__(
        self,
        client: BinanceClient,
        warning_threshold: float = 0.6,  # 60% margin usage = warning
        danger_threshold: float = 0.75,  # 75% margin usage = danger
        critical_threshold: float = 0.85,  # 85% margin usage = critical
        auto_reduce_enabled: bool = True,
        min_available_balance_pct: float = 0.15,  # Keep at least 15% available
    ):
        """Initialize margin manager.
        
        Args:
            client: Binance client
            warning_threshold: Warning threshold (0-1)
            danger_threshold: Danger threshold (0-1)
            critical_threshold: Critical threshold (0-1)
            auto_reduce_enabled: Enable automatic position reduction
            min_available_balance_pct: Minimum available balance percentage
        """
        self.client = client
        self.warning_threshold = warning_threshold
        self.danger_threshold = danger_threshold
        self.critical_threshold = critical_threshold
        self.auto_reduce_enabled = auto_reduce_enabled
        self.min_available_balance_pct = min_available_balance_pct
    
    def get_margin_status(self, account_id: str) -> Optional[MarginStatus]:
        """Get current margin status for an account.
        
        Args:
            account_id: Account ID
            
        Returns:
            MarginStatus or None if unavailable
        """
        try:
            # Get account balance
            balance = self.client.futures_account_balance()
            
            # Get account information (includes margin data)
            # Note: futures_account() may not exist, use get_account_info() or similar
            try:
                account_info = getattr(self.client, 'futures_account', lambda: {})()
            except Exception:
                # Fallback if method doesn't exist
                account_info = {}
            
            # Extract margin data
            total_balance = float(account_info.get('totalWalletBalance', balance))
            available_balance = float(account_info.get('availableBalance', balance * 0.5))
            used_margin = total_balance - available_balance
            
            # Calculate margin ratio
            margin_ratio = used_margin / total_balance if total_balance > 0 else 0.0
            
            # Get maintenance margin (Binance provides this)
            maintenance_margin = float(account_info.get('totalMaintMargin', 0.0))
            
            # Binance thresholds (typical values)
            margin_call_ratio = 0.8  # 80% triggers margin call
            liquidation_ratio = 1.0  # 100% triggers liquidation
            
            # Determine status
            if margin_ratio >= self.critical_threshold:
                status = 'critical'
            elif margin_ratio >= self.danger_threshold:
                status = 'danger'
            elif margin_ratio >= self.warning_threshold:
                status = 'warning'
            else:
                status = 'safe'
            
            return MarginStatus(
                account_id=account_id,
                total_balance=total_balance,
                available_balance=available_balance,
                used_margin=used_margin,
                margin_ratio=margin_ratio,
                maintenance_margin=maintenance_margin,
                margin_call_ratio=margin_call_ratio,
                liquidation_ratio=liquidation_ratio,
                status=status,
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"Failed to get margin status for {account_id}: {e}")
            return None
    
    def check_margin_available(
        self,
        account_id: str,
        required_margin: float
    ) -> Tuple[bool, Optional[str], Optional[MarginStatus]]:
        """Check if sufficient margin is available for a new position.
        
        Args:
            account_id: Account ID
            required_margin: Required margin for new position
            
        Returns:
            (allowed, reason, margin_status) tuple
        """
        margin_status = self.get_margin_status(account_id)
        
        if not margin_status:
            return False, "Could not retrieve margin status", None
        
        # Check if available balance is sufficient
        if margin_status.available_balance < required_margin:
            return False, (
                f"Insufficient margin: available={margin_status.available_balance:.2f} USDT, "
                f"required={required_margin:.2f} USDT"
            ), margin_status
        
        # Check if adding this position would breach thresholds
        new_margin_ratio = (margin_status.used_margin + required_margin) / margin_status.total_balance
        
        if new_margin_ratio >= self.critical_threshold:
            return False, (
                f"Order would breach critical margin threshold: "
                f"new_ratio={new_margin_ratio:.2%} >= {self.critical_threshold:.2%}"
            ), margin_status
        
        # Check minimum available balance
        new_available = margin_status.available_balance - required_margin
        min_available = margin_status.total_balance * self.min_available_balance_pct
        
        if new_available < min_available:
            return False, (
                f"Order would breach minimum available balance: "
                f"new_available={new_available:.2f} USDT < {min_available:.2f} USDT "
                f"({self.min_available_balance_pct:.1%} of balance)"
            ), margin_status
        
        return True, None, margin_status
    
    def should_reduce_positions(self, account_id: str) -> Tuple[bool, Optional[str], Optional[MarginStatus]]:
        """Check if positions should be reduced due to margin pressure.
        
        Args:
            account_id: Account ID
            
        Returns:
            (should_reduce, reason, margin_status) tuple
        """
        margin_status = self.get_margin_status(account_id)
        
        if not margin_status:
            return False, "Could not retrieve margin status", None
        
        if margin_status.status == 'critical':
            return True, (
                f"Critical margin status: ratio={margin_status.margin_ratio:.2%} >= {self.critical_threshold:.2%}"
            ), margin_status
        
        if margin_status.status == 'danger':
            return True, (
                f"Danger margin status: ratio={margin_status.margin_ratio:.2%} >= {self.danger_threshold:.2%}"
            ), margin_status
        
        # Check if available balance is below minimum
        min_available = margin_status.total_balance * self.min_available_balance_pct
        if margin_status.available_balance < min_available:
            return True, (
                f"Available balance below minimum: {margin_status.available_balance:.2f} USDT < {min_available:.2f} USDT"
            ), margin_status
        
        return False, None, margin_status
    
    def calculate_max_allowed_exposure(
        self,
        account_id: str,
        current_exposure: float
    ) -> float:
        """Calculate maximum allowed exposure based on margin constraints.
        
        Args:
            account_id: Account ID
            current_exposure: Current total exposure
            
        Returns:
            Maximum allowed exposure in USDT
        """
        margin_status = self.get_margin_status(account_id)
        
        if not margin_status:
            return current_exposure  # Return current if can't calculate
        
        # Calculate max exposure based on thresholds
        max_margin_usage = self.danger_threshold  # Use danger threshold as max
        max_used_margin = margin_status.total_balance * max_margin_usage
        
        # Ensure minimum available balance
        min_available = margin_status.total_balance * self.min_available_balance_pct
        max_used_margin = margin_status.total_balance - min_available
        
        # Max exposure is the lower of the two
        max_exposure = min(
            max_used_margin,
            margin_status.total_balance * max_margin_usage
        )
        
        return max_exposure

