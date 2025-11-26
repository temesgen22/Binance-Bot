from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.core.exceptions import PositionSizingError


@dataclass
class PositionSizingResult:
    quantity: float
    notional: float


class RiskManager:
    def __init__(self, client: BinanceClient) -> None:
        self.client = client

    def size_position(
        self, 
        symbol: str, 
        risk_per_trade: float, 
        price: float,
        fixed_amount: float | None = None
    ) -> PositionSizingResult:
        """
        Calculate position size based on either fixed amount or percentage of balance.
        Automatically adjusts to meet Binance minimum notional requirements.
        
        Args:
            symbol: Trading symbol
            risk_per_trade: Percentage of balance to risk (0.01 = 1%)
            price: Current price of the asset
            fixed_amount: Fixed USDT amount to trade (overrides risk_per_trade if set)
        
        Returns:
            PositionSizingResult with quantity and notional value
        
        Raises:
            ValueError: If fixed_amount is set but below minimum notional
        """
        # Get minimum notional from Binance
        min_notional = self.client.get_min_notional(symbol)
        
        # Determine which sizing method to use
        use_fixed_amount = fixed_amount is not None and fixed_amount > 0
        
        if use_fixed_amount:
            # Use FIXED AMOUNT - completely ignore risk_per_trade
            at_risk = fixed_amount
            logger.info(
                f"Using FIXED AMOUNT sizing for {symbol}: {fixed_amount} USDT "
                f"(risk_per_trade={risk_per_trade} is COMPLETELY IGNORED)"
            )
            
            # Check if fixed amount meets minimum notional
            if at_risk < min_notional:
                raise PositionSizingError(
                    f"Fixed amount {at_risk} USDT is below Binance minimum notional of {min_notional} USDT "
                    f"for {symbol}. Please increase fixed_amount to at least {min_notional} USDT.",
                    symbol=symbol,
                    details={"fixed_amount": fixed_amount, "min_notional": min_notional}
                )
            
            # Calculate quantity based on fixed amount
            quantity = at_risk / price
            rounded_quantity = self.client.round_quantity(symbol, quantity)
            # Recalculate notional from rounded quantity (may differ slightly due to rounding)
            actual_notional = rounded_quantity * price
            
            # Double-check actual notional meets minimum (after rounding)
            if actual_notional < min_notional:
                # Adjust quantity to meet minimum
                adjusted_quantity = min_notional / price
                rounded_quantity = self.client.round_quantity(symbol, adjusted_quantity)
                actual_notional = rounded_quantity * price
                logger.warning(
                    f"Adjusted quantity for {symbol} to meet minimum notional: "
                    f"qty={rounded_quantity} notional={actual_notional:.2f} USDT (min={min_notional} USDT, requested={fixed_amount} USDT)"
                )
            
            # Log the actual values being used (may differ from fixed_amount due to rounding)
            if abs(actual_notional - fixed_amount) > 0.01:  # More than 1 cent difference
                logger.warning(
                    f"Actual notional ({actual_notional:.2f} USDT) differs from requested fixed_amount "
                    f"({fixed_amount} USDT) due to quantity rounding for {symbol}"
                )
            
            logger.info(
                f"Fixed amount sizing RESULT for {symbol}: "
                f"requested={fixed_amount} USDT, actual={actual_notional:.2f} USDT, "
                f"qty={rounded_quantity}"
            )
            
            return PositionSizingResult(quantity=rounded_quantity, notional=actual_notional)
        
        else:
            # Use RISK PER TRADE (percentage of balance) - fixed_amount is None or <= 0
            if fixed_amount is not None and fixed_amount <= 0:
                logger.warning(
                    f"Fixed amount is set but invalid ({fixed_amount}), using risk_per_trade={risk_per_trade} for {symbol}"
                )
            
            logger.info(
                f"Using RISK PER TRADE sizing for {symbol}: {risk_per_trade} ({risk_per_trade*100:.2f}% of balance) "
                f"(fixed_amount={fixed_amount} is NOT used)"
            )
            
            balance = self.client.futures_account_balance()
            at_risk = balance * risk_per_trade
            
            # Check if calculated amount meets minimum notional
            if at_risk < min_notional:
                logger.warning(
                    f"Calculated risk amount {at_risk:.2f} USDT is below minimum notional {min_notional} USDT "
                    f"for {symbol}. Adjusting to minimum."
                )
                at_risk = min_notional
            
            quantity = max(at_risk / price, 0.001)
            rounded_quantity = self.client.round_quantity(symbol, quantity)
            actual_notional = rounded_quantity * price
            
            # Double-check notional meets minimum (after rounding)
            if actual_notional < min_notional:
                # Adjust quantity to meet minimum
                adjusted_quantity = min_notional / price
                rounded_quantity = self.client.round_quantity(symbol, adjusted_quantity)
                actual_notional = rounded_quantity * price
                logger.warning(
                    f"Adjusted quantity for {symbol} to meet minimum notional: "
                    f"qty={rounded_quantity} notional={actual_notional:.2f} USDT (min={min_notional} USDT)"
                )
            
            logger.info(
                f"Risk sizing RESULT for {symbol}: balance={balance:.2f} USDT, "
                f"risk_pct={risk_per_trade*100:.2f}%, calculated={at_risk:.2f} USDT, "
                f"actual={actual_notional:.2f} USDT, qty={rounded_quantity}"
            )
            
            return PositionSizingResult(quantity=rounded_quantity, notional=actual_notional)

