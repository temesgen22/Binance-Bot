from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.core.my_binance_client import BinanceClient


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
        
        if fixed_amount is not None:
            # Use fixed amount
            at_risk = fixed_amount
            
            # Check if fixed amount meets minimum notional
            if at_risk < min_notional:
                raise ValueError(
                    f"Fixed amount {at_risk} USDT is below Binance minimum notional of {min_notional} USDT "
                    f"for {symbol}. Please increase fixed_amount to at least {min_notional} USDT."
                )
            
            quantity = max(at_risk / price, 0.001)
            rounded_quantity = self.client.round_quantity(symbol, quantity)
            notional = rounded_quantity * price
            
            # Double-check notional meets minimum (after rounding)
            if notional < min_notional:
                # Adjust quantity to meet minimum
                adjusted_quantity = min_notional / price
                rounded_quantity = self.client.round_quantity(symbol, adjusted_quantity)
                notional = rounded_quantity * price
                logger.warning(
                    f"Adjusted quantity for {symbol} to meet minimum notional: "
                    f"qty={rounded_quantity} notional={notional:.2f} USDT (min={min_notional} USDT)"
                )
            
            logger.info(f"Fixed amount sizing for {symbol}: fixed={fixed_amount} USDT qty={rounded_quantity} notional={notional:.2f} USDT")
        else:
            # Use percentage of balance
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
            notional = rounded_quantity * price
            
            # Double-check notional meets minimum (after rounding)
            if notional < min_notional:
                # Adjust quantity to meet minimum
                adjusted_quantity = min_notional / price
                rounded_quantity = self.client.round_quantity(symbol, adjusted_quantity)
                notional = rounded_quantity * price
                logger.warning(
                    f"Adjusted quantity for {symbol} to meet minimum notional: "
                    f"qty={rounded_quantity} notional={notional:.2f} USDT (min={min_notional} USDT)"
                )
            
            logger.info(f"Risk sizing for {symbol}: balance={balance} risk={at_risk:.2f} qty={rounded_quantity} notional={notional:.2f} USDT")
        
        return PositionSizingResult(quantity=rounded_quantity, notional=notional)

