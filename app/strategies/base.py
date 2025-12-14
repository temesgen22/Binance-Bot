from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Protocol

from loguru import logger

from app.core.my_binance_client import BinanceClient


SignalAction = Literal["BUY", "SELL", "HOLD", "CLOSE"]


@dataclass
class StrategySignal:
    action: SignalAction
    symbol: str
    confidence: float
    price: float | None = None
    exit_reason: str | None = None  # Reason for exit: "TP", "SL", "EMA_CROSS", "MANUAL", etc.
    position_side: Literal["LONG", "SHORT"] | None = None  # Position direction when signal is generated


@dataclass
class StrategyContext:
    id: str
    name: str
    symbol: str
    leverage: int
    risk_per_trade: float
    params: dict[str, float | int | str]
    interval_seconds: int
    metadata: dict[str, str | float | int] = field(default_factory=dict)


class Strategy(ABC):
    def __init__(self, context: StrategyContext, client: BinanceClient) -> None:
        self.context = context
        self.client = client
        self._stopped = asyncio.Event()

    @staticmethod
    def parse_bool_param(value: bool | int | str | None, default: bool = False) -> bool:
        """Safely parse a boolean parameter from various input types.
        
        Handles values from JSON/DB/.env which often come as strings.
        This prevents silent bugs where bool("false") == True.
        
        Args:
            value: The value to parse (can be bool, int, str, or None)
            default: Default value if value is None or cannot be parsed
            
        Returns:
            bool: Parsed boolean value
            
        Examples:
            >>> Strategy.parse_bool_param(True)  # True
            >>> Strategy.parse_bool_param("true")  # True
            >>> Strategy.parse_bool_param("false")  # False (not True!)
            >>> Strategy.parse_bool_param("0")  # False (not True!)
            >>> Strategy.parse_bool_param(1)  # True
            >>> Strategy.parse_bool_param(0)  # False
            >>> Strategy.parse_bool_param(None)  # default
        """
        if value is None:
            return default
        
        # Already a boolean
        if isinstance(value, bool):
            return value
        
        # Integer: 0 = False, anything else = True
        if isinstance(value, int):
            return value != 0
        
        # String: parse common boolean representations
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ("true", "1", "yes", "on", "enabled"):
                return True
            if value_lower in ("false", "0", "no", "off", "disabled", ""):
                return False
            # Unknown string value - log warning and use default
            logger.warning(f"Unknown boolean string value: {value!r}, using default: {default}")
            return default
        
        # Fallback: convert to bool (for other types)
        return bool(value)

    @abstractmethod
    async def evaluate(self) -> StrategySignal:
        ...

    async def teardown(self) -> None:
        logger.info(f"Tearing down strategy {self.context.id}")

    def stop(self) -> None:
        self._stopped.set()

    @property
    def is_stopped(self) -> bool:
        return self._stopped.is_set()
    
    def sync_position_state(
        self,
        *,
        position_side: Literal["LONG", "SHORT"] | None,
        entry_price: float | None,
    ) -> None:
        """Sync strategy's internal position state with Binance reality.
        
        Called by StrategyRunner after detecting that Binance position changed
        (e.g., via native TP/SL orders filling) to keep strategy state in sync.
        
        Args:
            position_side: Current position side from Binance (None if flat)
            entry_price: Current entry price from Binance (None if flat)
        
        Default implementation does nothing. Strategies should override this
        if they maintain internal position state.
        """
        # Default: no-op. Strategies with internal state should override.
        pass


class StrategyFactory(Protocol):
    def __call__(self, context: StrategyContext, client: BinanceClient) -> Strategy: ...

