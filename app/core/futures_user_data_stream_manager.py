"""
Futures User Data Stream manager: one WebSocket per account, parses ACCOUNT_UPDATE
and invokes on_position_update(account_id, symbol, position_data) for each position entry.
"""

import asyncio
from typing import Any, Callable, Dict, Optional

from loguru import logger

from app.core.futures_user_data_connection import FuturesUserDataConnection

PositionUpdateCallback = Callable[[str, str, Dict[str, Any]], Any]


def _normalize_position_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build normalized position_data from Binance a.P entry (s, pa, ep, up, ps)."""
    pa = entry.get("pa", "0")
    try:
        position_amt = float(pa)
    except (TypeError, ValueError):
        position_amt = 0.0
    ep = entry.get("ep", "0") or "0"
    up = entry.get("up", "0") or "0"
    try:
        entry_price = float(ep)
    except (TypeError, ValueError):
        entry_price = 0.0
    try:
        unrealized_pnl = float(up)
    except (TypeError, ValueError):
        unrealized_pnl = 0.0
    position_side = (entry.get("ps") or "BOTH").upper()
    if position_side not in ("LONG", "SHORT", "BOTH"):
        position_side = "BOTH"
    # Map BOTH to LONG/SHORT from sign of pa for one-way mode (when not flat)
    if position_side == "BOTH" and position_amt != 0:
        position_side = "LONG" if position_amt > 0 else "SHORT"
    return {
        "position_amt": position_amt,
        "entry_price": entry_price,
        "unrealized_pnl": unrealized_pnl,
        "position_side": position_side,
        "mark_price": None,  # ACCOUNT_UPDATE may not include; optional
    }


class FuturesUserDataStreamManager:
    """One User Data Stream per account; parses events and calls on_position_update."""

    def __init__(
        self,
        account_manager: Any,
        on_position_update: PositionUpdateCallback,
    ):
        self._account_manager = account_manager
        self._on_position_update = on_position_update
        self._connections: Dict[str, FuturesUserDataConnection] = {}
        self._keepalive_tasks: Dict[str, asyncio.Task] = {}
        self._listen_keys: Dict[str, str] = {}
        self._clients: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def _on_ws_message(self, account_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        if event_type == "ACCOUNT_UPDATE":
            update_data = payload.get("a") or {}
            positions = update_data.get("P") or []
            for entry in positions:
                symbol = (entry.get("s") or "").strip()
                if not symbol:
                    continue
                position_data = _normalize_position_entry(entry)
                # Log WebSocket position stream for check-up
                pa = position_data.get("position_amt", 0) or 0
                if abs(float(pa)) < 1e-9:
                    logger.info(
                        f"[UserDataStream] ACCOUNT_UPDATE position stream: account={account_id} symbol={symbol} position=FLAT (0)"
                    )
                else:
                    logger.info(
                        f"[UserDataStream] ACCOUNT_UPDATE position stream: account={account_id} symbol={symbol} "
                        f"position_amt={pa} side={position_data.get('position_side')} entry_price={position_data.get('entry_price')} "
                        f"unrealized_pnl={position_data.get('unrealized_pnl')}"
                    )
                try:
                    if asyncio.iscoroutinefunction(self._on_position_update):
                        await self._on_position_update(account_id, symbol, position_data)
                    else:
                        self._on_position_update(account_id, symbol, position_data)
                except Exception as exc:
                    logger.warning(
                        f"[UserDataStream] on_position_update error {account_id} {symbol}: {exc}",
                        exc_info=True,
                    )
        # ORDER_TRADE_UPDATE can be used optionally to trigger refresh; not required for position

    async def _keepalive_loop(self, account_id: str, listen_key: str, client: Any) -> None:
        interval = 30 * 60  # 30 minutes
        while True:
            await asyncio.sleep(interval)
            if account_id not in self._listen_keys or self._listen_keys[account_id] != listen_key:
                break
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda c=client, k=listen_key: c.keepalive_listen_key(k),
                )
                logger.debug(f"[UserDataStream] Keepalive sent for account {account_id}")
            except Exception as exc:
                logger.warning(f"[UserDataStream] Keepalive failed for {account_id}: {exc}")
                break

    async def ensure_stream(self, account_id: str) -> None:
        """Start User Data stream for account if not already running. No-op if already running."""
        account_id = (account_id or "default").lower()
        async with self._lock:
            if account_id in self._connections:
                conn = self._connections[account_id]
                if conn.is_connected():
                    return
                # was running but disconnected; clean up and restart below
                await self._stop_stream_internal(account_id)

            try:
                client = self._account_manager.get_account_client(account_id)
            except Exception as exc:
                logger.debug(f"[UserDataStream] No client for account {account_id}, skip stream: {exc}")
                return

            if not getattr(client, "create_listen_key", None):
                logger.debug(
                    f"[UserDataStream] Client for {account_id} has no create_listen_key (e.g. paper), skip"
                )
                return

            try:
                listen_key = await asyncio.get_event_loop().run_in_executor(
                    None,
                    client.create_listen_key,
                )
            except Exception as exc:
                logger.warning(f"[UserDataStream] Failed to create listenKey for {account_id}: {exc}")
                return

            if not listen_key:
                logger.warning(f"[UserDataStream] Empty listenKey for {account_id}")
                return

            self._listen_keys[account_id] = listen_key
            self._clients[account_id] = client
            testnet = getattr(client, "testnet", True)

            async def on_disconnect(acc_id: str) -> None:
                logger.info(f"[UserDataStream] Disconnected for account {acc_id}")

            conn = FuturesUserDataConnection(
                account_id=account_id,
                listen_key=listen_key,
                testnet=testnet,
                on_message=self._on_ws_message,
                on_disconnect=on_disconnect,
            )
            self._connections[account_id] = conn
            await conn.connect()

            keepalive_task = asyncio.create_task(
                self._keepalive_loop(account_id, listen_key, client),
            )
            self._keepalive_tasks[account_id] = keepalive_task

    async def _stop_stream_internal(self, account_id: str) -> None:
        if account_id in self._keepalive_tasks:
            self._keepalive_tasks[account_id].cancel()
            try:
                await self._keepalive_tasks[account_id]
            except asyncio.CancelledError:
                pass
            del self._keepalive_tasks[account_id]
        if account_id in self._connections:
            await self._connections[account_id].disconnect()
            del self._connections[account_id]
        self._listen_keys.pop(account_id, None)
        self._clients.pop(account_id, None)

    async def stop_stream(self, account_id: str) -> None:
        account_id = (account_id or "default").lower()
        async with self._lock:
            await self._stop_stream_internal(account_id)

    async def stop_all(self) -> None:
        async with self._lock:
            for aid in list(self._connections.keys()):
                await self._stop_stream_internal(aid)
        logger.info("[UserDataStream] All streams stopped")

    def is_connected(self, account_id: str) -> bool:
        account_id = (account_id or "default").lower()
        conn = self._connections.get(account_id)
        return conn is not None and conn.is_connected()
