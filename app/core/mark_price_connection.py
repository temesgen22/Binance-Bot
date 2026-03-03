"""
Single-symbol Binance Futures mark price WebSocket connection.

Connects to wss://fstream.binance.com/ws/<symbol>@markPrice@1s (or testnet),
parses markPriceUpdate events, and calls on_mark_price(symbol, data) with
data containing mark_price (float) and raw payload.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets
from loguru import logger


class MarkPriceConnection:
    """One WebSocket connection to Binance mark price stream for a single symbol."""

    def __init__(
        self,
        symbol: str,
        testnet: bool = True,
        on_mark_price: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    ):
        self.symbol = symbol.upper()
        self.testnet = testnet
        self.on_mark_price = on_mark_price
        if testnet:
            self.url = f"wss://testnet.binancefuture.com/ws/{symbol.lower()}@markPrice@1s"
        else:
            self.url = f"wss://fstream.binance.com/ws/{symbol.lower()}@markPrice@1s"
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

    async def connect(self) -> None:
        """Start WebSocket connection and listen loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.debug(f"[MarkPrice] Connection started: {self.symbol}")

    async def disconnect(self) -> None:
        """Stop WebSocket connection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        logger.debug(f"[MarkPrice] Connection stopped: {self.symbol}")

    async def _run(self) -> None:
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                self._reconnect_attempts += 1
                wait_time = min(2 ** self._reconnect_attempts, 60)
                logger.warning(
                    f"[MarkPrice] {self.symbol} error (attempt {self._reconnect_attempts}): {e}. "
                    f"Reconnecting in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
        self._ws = None

    async def _connect_and_listen(self) -> None:
        async with websockets.connect(
            self.url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10,
        ) as ws:
            self._ws = ws
            self._reconnect_attempts = 0
            logger.debug(f"[MarkPrice] Connected: {self.symbol}")
            async for message in ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    if data.get("e") != "markPriceUpdate":
                        continue
                    s = data.get("s", "").upper()
                    p_str = data.get("p")
                    if p_str is None:
                        continue
                    try:
                        mark_price = float(p_str)
                    except (TypeError, ValueError):
                        continue
                    payload = {"mark_price": mark_price, **data}
                    if self.on_mark_price:
                        await self.on_mark_price(s, payload)
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.debug(f"[MarkPrice] {self.symbol} message error: {e}")
        self._ws = None
