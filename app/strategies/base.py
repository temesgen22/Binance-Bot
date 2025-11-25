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


class StrategyFactory(Protocol):
    def __call__(self, context: StrategyContext, client: BinanceClient) -> Strategy: ...

