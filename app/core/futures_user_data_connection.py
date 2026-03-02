"""
Futures User Data WebSocket connection (one per account).

Receives ACCOUNT_UPDATE / ORDER_TRADE_UPDATE from Binance and forwards
the raw payload to the manager. Does not parse position data or know about strategies.
"""

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets
from loguru import logger

Callback = Callable[[str, str, Dict[str, Any]], Awaitable[None]]


class FuturesUserDataConnection:
    """One WebSocket connection for a single account's User Data Stream."""

    def __init__(
        self,
        account_id: str,
        listen_key: str,
        testnet: bool,
        on_message: Callback,
        on_disconnect: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        self.account_id = account_id
        self.listen_key = listen_key
        self.testnet = testnet
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        base = "wss://testnet.binancefuture.com" if testnet else "wss://fstream.binance.com"
        self._url = f"{base}/ws/{listen_key}"
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

    async def connect(self) -> None:
        if self._running:
            logger.warning(f"[UserDataStream] Already running for account {self.account_id}")
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"[UserDataStream] Started for account {self.account_id}")

    async def disconnect(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._on_disconnect:
            try:
                await self._on_disconnect(self.account_id)
            except Exception as exc:
                logger.debug(f"[UserDataStream] on_disconnect error for {self.account_id}: {exc}")
        logger.info(f"[UserDataStream] Stopped for account {self.account_id}")

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
                wait = min(2 ** self._reconnect_attempts, 60)
                logger.warning(
                    f"[UserDataStream] {self.account_id} error (attempt {self._reconnect_attempts}): {e}. "
                    f"Reconnecting in {wait}s..."
                )
                await asyncio.sleep(wait)
        self._ws = None

    async def _connect_and_listen(self) -> None:
        async with websockets.connect(
            self._url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10,
        ) as ws:
            self._ws = ws
            self._reconnect_attempts = 0
            logger.info(f"[UserDataStream] Connected for account {self.account_id}")
            async for message in ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    event_type = data.get("e", "")
                    await self._on_message(self.account_id, event_type, data)
                except json.JSONDecodeError as e:
                    logger.debug(f"[UserDataStream] JSON decode error: {e}")
                except Exception as e:
                    logger.warning(f"[UserDataStream] Message handling error: {e}", exc_info=True)
        self._ws = None

    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed
