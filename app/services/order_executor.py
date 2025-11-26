from __future__ import annotations

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.models.order import OrderResponse
from app.risk.manager import PositionSizingResult
from app.strategies.base import StrategySignal


class OrderExecutor:
    def __init__(self, client: BinanceClient) -> None:
        self.client = client

    def execute(
        self,
        *,
        signal: StrategySignal,
        sizing: PositionSizingResult,
        reduce_only_override: bool | None = None,
    ) -> OrderResponse | None:
        if signal.action == "HOLD":
            logger.info(f"HOLD signal for {signal.symbol}, skipping order")
            return None

        # Binance Futures One-Way Mode semantics:
        # - BUY when flat = open long
        # - SELL when flat = open short  
        # - BUY when short = cover short (close short)
        # - SELL when long = close long
        # - reduce_only=True forces closing only (safety)
        # 
        # The strategy tracks position state internally, so signals are correct:
        # - Strategy returns "SELL" to open short (when flat) or close long
        # - Strategy returns "BUY" to open long (when flat) or cover short
        # Binance automatically handles position opening/closing based on current position
        
        side = "BUY" if signal.action == "BUY" else "SELL"
        reduce_only = signal.action == "CLOSE"
        if reduce_only_override is not None:
            reduce_only = reduce_only_override
        return self.client.place_order(
            symbol=signal.symbol,
            side=side,
            quantity=sizing.quantity,
            order_type="MARKET",
            reduce_only=reduce_only,
        )

