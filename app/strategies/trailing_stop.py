"""
Dynamic Trailing Stop Loss Manager

A reusable component that dynamically adjusts take profit and stop loss levels
as price moves favorably, maintaining constant risk/reward percentages.

Example (Long Position):
- Entry: 100,000
- Initial TP: 105,000 (+5%)
- Initial SL: 98,000 (-2%)
- When price moves to 101,100 (+1.1%):
  - New SL: 99,078 (101,100 * 0.98 = -2% from current)
  - New TP: 106,155 (101,100 * 1.05 = +5% from current)
- Trails up as price moves favorably, never moves down
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple
from loguru import logger


@dataclass
class TrailUpdateEvent:
    """Emitted when TrailingStopManager actually updates TP/SL levels (for DB recording)."""
    best_price: float
    tp_price: float
    sl_price: float
    position_side: Literal["LONG", "SHORT"]


class TrailingStopManager:
    """
    Dynamic trailing stop loss manager that adjusts TP/SL levels as price moves favorably.
    
    Maintains constant risk/reward percentages by trailing both TP and SL together
    when price moves in the favorable direction.
    
    For LONG positions:
    - Trails up when price moves up
    - Never trails down (locks in profits)
    
    For SHORT positions:
    - Trails down when price moves down
    - Never trails up (locks in profits)
    """
    
    def __init__(
        self,
        entry_price: float,
        take_profit_pct: float,
        stop_loss_pct: float,
        position_type: Literal["LONG", "SHORT"],
        enabled: bool = True,
        activation_pct: float = 0.0,
    ) -> None:
        """
        Initialize trailing stop manager.
        
        Args:
            entry_price: Entry price of the position
            take_profit_pct: Take profit percentage (e.g., 0.05 for 5%)
            stop_loss_pct: Stop loss percentage (e.g., 0.02 for 2%)
            position_type: "LONG" or "SHORT"
            enabled: Whether trailing stop is enabled (default: True)
            activation_pct: Percentage price must move before trailing activates (e.g., 0.01 = 1%)
                           If 0, trailing starts immediately. Default: 0.0
        """
        self.entry_price = entry_price
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.position_type = position_type
        self.enabled = enabled
        self.activation_pct = activation_pct
        
        # Calculate activation threshold price
        if position_type == "LONG":
            self.activation_price = entry_price * (1 + activation_pct)
        else:  # SHORT
            self.activation_price = entry_price * (1 - activation_pct)
        
        # Track if activation threshold has been reached
        self.activated = activation_pct == 0.0  # If 0, activate immediately
        
        # Initialize TP/SL from entry price
        if position_type == "LONG":
            self.current_tp = entry_price * (1 + take_profit_pct)
            self.current_sl = entry_price * (1 - stop_loss_pct)
        else:  # SHORT
            self.current_tp = entry_price * (1 - take_profit_pct)  # Inverted
            self.current_sl = entry_price * (1 + stop_loss_pct)  # Inverted
        
        # Track highest price (for long) or lowest price (for short) to prevent trailing back
        self.best_price = entry_price
        
        logger.debug(
            f"TrailingStop initialized: entry={entry_price:.8f}, "
            f"tp={self.current_tp:.8f}, sl={self.current_sl:.8f}, "
            f"type={position_type}, enabled={enabled}, "
            f"activation_pct={activation_pct:.4f} ({activation_pct*100:.2f}%), "
            f"activation_price={self.activation_price:.8f}, activated={self.activated}"
        )
    
    def update(self, current_price: float) -> Tuple[float, float, Optional[TrailUpdateEvent]]:
        """
        Update trailing stop levels based on current price.
        
        Only trails in the favorable direction:
        - LONG: Only trails up (when price > best_price)
        - SHORT: Only trails down (when price < best_price)
        
        Trailing only starts after activation threshold is reached:
        - LONG: Price must reach entry * (1 + activation_pct)
        - SHORT: Price must reach entry * (1 - activation_pct)
        
        Args:
            current_price: Current market price
            
        Returns:
            Tuple of (updated_tp_price, updated_sl_price, optional TrailUpdateEvent when levels were updated)
        """
        if not self.enabled:
            return (self.current_tp, self.current_sl, None)
        
        # Check if activation threshold is reached
        if not self.activated:
            if self.position_type == "LONG":
                if current_price >= self.activation_price:
                    self.activated = True
                    # Trailing stop activation - use DEBUG to reduce backtest log noise
                    logger.debug(
                        f"TrailingStop activated for LONG: price {current_price:.8f} >= "
                        f"activation {self.activation_price:.8f} ({self.activation_pct*100:.2f}% from entry)"
                    )
            else:  # SHORT
                if current_price <= self.activation_price:
                    self.activated = True
                    # Trailing stop activation - use DEBUG to reduce backtest log noise
                    logger.debug(
                        f"TrailingStop activated for SHORT: price {current_price:.8f} <= "
                        f"activation {self.activation_price:.8f} ({self.activation_pct*100:.2f}% from entry)"
                    )
        
        # Only trail if activated
        if not self.activated:
            return (self.current_tp, self.current_sl, None)
        
        should_update = False
        
        if self.position_type == "LONG":
            # For long positions, trail up when price moves up
            if current_price > self.best_price:
                self.best_price = current_price
                should_update = True
        else:  # SHORT
            # For short positions, trail down when price moves down
            if current_price < self.best_price:
                self.best_price = current_price
                should_update = True
        
        trail_event: Optional[TrailUpdateEvent] = None
        if should_update:
            # Recalculate TP/SL based on best price, maintaining percentages
            if self.position_type == "LONG":
                new_tp = self.best_price * (1 + self.take_profit_pct)
                new_sl = self.best_price * (1 - self.stop_loss_pct)
            else:  # SHORT
                new_tp = self.best_price * (1 - self.take_profit_pct)
                new_sl = self.best_price * (1 + self.stop_loss_pct)
            
            # Only update if trailing improves TP/SL
            # For LONG: TP should increase, SL should increase (but never below entry SL)
            # For SHORT: TP should decrease, SL should decrease (but never above entry SL)
            if self.position_type == "LONG":
                if new_tp > self.current_tp and new_sl > self.current_sl:
                    self.current_tp = new_tp
                    self.current_sl = new_sl
                    trail_event = TrailUpdateEvent(
                        best_price=self.best_price,
                        tp_price=self.current_tp,
                        sl_price=self.current_sl,
                        position_side="LONG",
                    )
                    logger.debug(
                        f"TrailingStop LONG updated: best={self.best_price:.8f}, "
                        f"tp={self.current_tp:.8f}, sl={self.current_sl:.8f}"
                    )
            else:  # SHORT
                if new_tp < self.current_tp and new_sl < self.current_sl:
                    self.current_tp = new_tp
                    self.current_sl = new_sl
                    trail_event = TrailUpdateEvent(
                        best_price=self.best_price,
                        tp_price=self.current_tp,
                        sl_price=self.current_sl,
                        position_side="SHORT",
                    )
                    logger.debug(
                        f"TrailingStop SHORT updated: best={self.best_price:.8f}, "
                        f"tp={self.current_tp:.8f}, sl={self.current_sl:.8f}"
                    )
        
        return (self.current_tp, self.current_sl, trail_event)
    
    def check_exit(self, current_price: float) -> Optional[Literal["TP", "SL"]]:
        """
        Check if current price triggers TP or SL exit.
        
        Args:
            current_price: Current market price
            
        Returns:
            "TP" if take profit hit, "SL" if stop loss hit, None otherwise
        """
        if self.position_type == "LONG":
            if current_price >= self.current_tp:
                return "TP"
            if current_price <= self.current_sl:
                return "SL"
        else:  # SHORT
            if current_price <= self.current_tp:
                return "TP"
            if current_price >= self.current_sl:
                return "SL"
        
        return None
    
    def get_levels(self) -> tuple[float, float]:
        """Get current TP and SL levels."""
        return (self.current_tp, self.current_sl)
    
    def get_best_price(self) -> float:
        """Get the best price reached (highest for long, lowest for short)."""
        return self.best_price
    
    def reset(self, entry_price: float) -> None:
        """
        Reset trailing stop with new entry price (for new position).
        
        Args:
            entry_price: New entry price
        """
        self.entry_price = entry_price
        self.best_price = entry_price
        
        # Recalculate activation threshold
        if self.position_type == "LONG":
            self.activation_price = entry_price * (1 + self.activation_pct)
        else:  # SHORT
            self.activation_price = entry_price * (1 - self.activation_pct)
        
        # Reset activation status
        self.activated = self.activation_pct == 0.0
        
        if self.position_type == "LONG":
            self.current_tp = entry_price * (1 + self.take_profit_pct)
            self.current_sl = entry_price * (1 - self.stop_loss_pct)
        else:  # SHORT
            self.current_tp = entry_price * (1 - self.take_profit_pct)
            self.current_sl = entry_price * (1 + self.stop_loss_pct)
        
        logger.debug(
            f"TrailingStop reset: entry={entry_price:.8f}, "
            f"tp={self.current_tp:.8f}, sl={self.current_sl:.8f}, "
            f"activation_pct={self.activation_pct:.4f}, activated={self.activated}"
        )

