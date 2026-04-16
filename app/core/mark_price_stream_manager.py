"""
Mark price stream manager: subscribe/unsubscribe by symbol, registry of open positions,
and handler that computes PnL and pushes to client WebSockets on each mark price tick.
When WebSocket fails (502/timeout), a REST fallback polls mark price every 15s so PnL still updates.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID

import httpx
from loguru import logger

from app.core.funding_from_mark import parse_funding_from_payload
from app.core.funding_market_cache import get_funding_interval_hours
from app.core.mark_price_connection import MarkPriceConnection
from app.core.position_broadcast import PositionBroadcastService
from app.strategies.pnl_giveback import update_peak_unrealized


def _compute_unrealized_pnl(
    mark_price: float,
    entry_price: float,
    position_size: float,
    position_side: str,
) -> float:
    """LONG: (mark - entry) * size; SHORT: (entry - mark) * size."""
    if position_side == "SHORT":
        return (entry_price - mark_price) * position_size
    return (mark_price - entry_price) * position_size


class MarkPriceStreamManager:
    """Subscribe to Binance mark price per symbol; maintain registry of open positions; on tick, broadcast PnL to clients."""

    def __init__(
        self,
        broadcast_service: PositionBroadcastService,
        testnet: bool = True,
    ) -> None:
        self._broadcast = broadcast_service
        self._testnet = testnet
        self._connections: Dict[str, MarkPriceConnection] = {}
        self._subscription_counts: Dict[str, int] = {}
        self._registry: Dict[str, List[Dict[str, Any]]] = {}  # symbol -> list of position dicts (max_unrealized_pnl updated each tick)
        self._lock = asyncio.Lock()
        self._rest_fallback_tasks: Dict[str, asyncio.Task] = {}
        self._rest_fallback_interval = 15
        self._rest_fallback_logged: set = set()  # keys we've logged "using REST fallback" for
        # One handler per symbol (WS + REST fallback); avoids new closure every REST poll
        self._mark_handlers: Dict[str, Callable[[str, Dict[str, Any]], Awaitable[None]]] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
        self._http_client_lock = asyncio.Lock()

    def register_position(
        self,
        symbol: str,
        strategy_id: str,
        user_id: UUID,
        entry_price: float,
        position_size: float,
        position_side: str,
        account_id: Optional[str] = None,
        leverage: Optional[int] = None,
        initial_margin: Optional[float] = None,
        strategy_name: Optional[str] = None,
        position_instance_id: Optional[UUID] = None,
    ) -> None:
        """Record an open position for this symbol (called when position opens)."""
        key = symbol.upper()
        if key not in self._registry:
            self._registry[key] = []
        new_pid = str(position_instance_id) if position_instance_id is not None else None
        for entry in self._registry[key]:
            if entry["strategy_id"] == strategy_id:
                old_pid = entry.get("position_instance_id")
                if new_pid != old_pid:
                    entry["max_unrealized_pnl"] = None
                entry.update(
                    entry_price=entry_price,
                    position_size=position_size,
                    position_side=position_side,
                    account_id=account_id or "default",
                    leverage=leverage,
                    initial_margin=initial_margin,
                    strategy_name=strategy_name,
                    position_instance_id=new_pid,
                    last_seen_at=time.time(),
                )
                return
        self._registry[key].append(
            {
                "strategy_id": strategy_id,
                "user_id": user_id,
                "entry_price": entry_price,
                "position_size": position_size,
                "position_side": position_side,
                "account_id": account_id or "default",
                "leverage": leverage,
                "initial_margin": initial_margin,
                "strategy_name": strategy_name,
                "position_instance_id": new_pid,
                "max_unrealized_pnl": None,
                "last_seen_at": time.time(),
            }
        )

    def get_max_unrealized_pnl(self, symbol: str, strategy_id: str) -> Optional[float]:
        """Peak open unrealized PnL (USDT) for this registry entry, if any."""
        key = symbol.upper()
        for entry in self._registry.get(key, []):
            if entry.get("strategy_id") == strategy_id:
                return entry.get("max_unrealized_pnl")
        return None

    def unregister_position(self, symbol: str, strategy_id: str) -> None:
        """Remove a position from the registry (called when position closes)."""
        key = symbol.upper()
        if key not in self._registry:
            return
        self._registry[key] = [e for e in self._registry[key] if e["strategy_id"] != strategy_id]
        if not self._registry[key]:
            del self._registry[key]

    async def _ensure_http_client(self) -> httpx.AsyncClient:
        async with self._http_client_lock:
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=10.0)
            return self._http_client

    async def _rest_fallback_loop(self, key: str) -> None:
        """Poll mark price via REST every N seconds and broadcast; used when WebSocket fails."""
        base = "https://testnet.binancefuture.com" if self._testnet else "https://fapi.binance.com"
        url = f"{base}/fapi/v1/premiumIndex"
        while True:
            try:
                await asyncio.sleep(self._rest_fallback_interval)
                if key not in self._registry or not self._registry[key]:
                    continue
                client = await self._ensure_http_client()
                r = await client.get(url, params={"symbol": key})
                r.raise_for_status()
                data = r.json()
                mark_price_str = data.get("markPrice")
                if mark_price_str is None:
                    continue
                mark_price = float(mark_price_str)
                if key not in self._rest_fallback_logged:
                    self._rest_fallback_logged.add(key)
                    logger.info(
                        f"[MarkPrice] {key} using REST fallback (every {self._rest_fallback_interval}s); "
                        "PnL will still update in the app."
                    )
                callback = self._mark_handlers.get(key)
                if callback is None:
                    callback = self._on_mark_price_factory(key)
                    self._mark_handlers[key] = callback
                await callback(key, {"mark_price": mark_price, **data})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[MarkPrice] REST fallback {key}: {e}")

    def _on_mark_price_factory(self, symbol_key: str):
        _tick_count: List[int] = [0]  # use list so closure can mutate

        async def _on_mark_price(_symbol: str, data: Dict[str, Any]) -> None:
            mark_price = data.get("mark_price")
            if mark_price is None:
                return
            entries = list(self._registry.get(symbol_key, []))
            if not entries:
                logger.warning(
                    f"[MarkPrice] Received tick for {symbol_key} but no positions in registry (current_price={mark_price}). "
                    "Position may not be registered yet or was unregistered. Enable mark price after position opens."
                )
                return
            last_rate, next_ms = parse_funding_from_payload(data)
            interval_h: Optional[int] = None
            if last_rate is not None or next_ms is not None:
                try:
                    interval_h = await asyncio.to_thread(
                        get_funding_interval_hours, symbol_key, self._testnet
                    )
                except Exception as exc:
                    logger.debug(f"[MarkPrice] funding interval {symbol_key}: {exc}")
            _tick_count[0] += 1
            log_every_ticks = 30  # log every ~30s when stream is 1s
            for entry in entries:
                try:
                    position_side = entry.get("position_side") or "LONG"
                    unrealized_pnl = _compute_unrealized_pnl(
                        mark_price,
                        entry["entry_price"],
                        entry["position_size"],
                        position_side,
                    )
                    entry["max_unrealized_pnl"] = update_peak_unrealized(
                        entry.get("max_unrealized_pnl"),
                        unrealized_pnl,
                    )
                    max_u = entry["max_unrealized_pnl"]
                    await self._broadcast.broadcast_position_update(
                        entry["user_id"],
                        entry["strategy_id"],
                        symbol=symbol_key,
                        account_id=entry.get("account_id"),
                        position_size=entry["position_size"],
                        entry_price=entry["entry_price"],
                        unrealized_pnl=unrealized_pnl,
                        position_side=position_side,
                        current_price=mark_price,
                        leverage=entry.get("leverage"),
                        initial_margin=entry.get("initial_margin"),
                        strategy_name=entry.get("strategy_name"),
                        max_unrealized_pnl=max_u,
                        last_funding_rate=last_rate,
                        next_funding_time_ms=next_ms,
                        funding_interval_hours=interval_h,
                    )
                except Exception as e:
                    logger.warning(
                        f"[MarkPrice] broadcast for {entry.get('strategy_id', '?')} failed: {e}",
                        exc_info=True,
                    )
            if _tick_count[0] % log_every_ticks == 1:
                logger.info(
                    f"[MarkPrice] {symbol_key} real-time tick #{_tick_count[0]}: mark_price={mark_price} (broadcast to clients)"
                )
        return _on_mark_price

    async def subscribe(self, symbol: str) -> None:
        """Subscribe to mark price for symbol. One connection per symbol; reuse if already connected."""
        key = symbol.upper()
        async with self._lock:
            if key in self._connections:
                logger.debug(f"[MarkPrice] Reusing existing connection for {key} (no duplicate WebSocket)")
                return
            self._subscription_counts[key] = 1
            handler = self._on_mark_price_factory(key)
            self._mark_handlers[key] = handler
            conn = MarkPriceConnection(
                symbol=key,
                testnet=self._testnet,
                on_mark_price=handler,
            )
            self._connections[key] = conn
        # Stagger connection so it's not in same burst as User Data / other streams (reduces 502 on same machine)
        await asyncio.sleep(2)
        async with self._lock:
            if key not in self._connections or self._connections[key] is not conn:
                self._subscription_counts[key] = self._subscription_counts.get(key, 1) - 1
                if self._subscription_counts[key] <= 0:
                    del self._subscription_counts[key]
                return
        logger.info(f"[MarkPrice] Connecting to {conn.url} (testnet={self._testnet})")
        try:
            await conn.connect()
        except Exception as e:
            logger.warning(f"[MarkPrice] subscribe {key} connect failed: {e}")
            async with self._lock:
                self._subscription_counts[key] = self._subscription_counts.get(key, 1) - 1
                if self._subscription_counts[key] <= 0:
                    del self._subscription_counts[key]
                if key in self._connections:
                    del self._connections[key]
                self._mark_handlers.pop(key, None)
            return
        logger.info(f"[MarkPrice] Subscribed to {key} (position opened; real-time PnL updates enabled)")
        # Start REST fallback so PnL still updates when WebSocket fails (502/timeout)
        async with self._lock:
            if key not in self._rest_fallback_tasks:
                task = asyncio.create_task(self._rest_fallback_loop(key))
                self._rest_fallback_tasks[key] = task

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from mark price for symbol (decrement count; disconnect when 0)."""
        key = symbol.upper()
        async with self._lock:
            if key not in self._subscription_counts or self._subscription_counts[key] <= 0:
                return
            self._subscription_counts[key] -= 1
            if self._subscription_counts[key] > 0:
                return
            conn = self._connections.pop(key, None)
            if key in self._subscription_counts:
                del self._subscription_counts[key]
            self._mark_handlers.pop(key, None)
            fallback_task = self._rest_fallback_tasks.pop(key, None)
        if fallback_task:
            fallback_task.cancel()
            try:
                await fallback_task
            except asyncio.CancelledError:
                pass
        if conn:
            await conn.disconnect()
        logger.debug(f"[MarkPrice] Unsubscribed: {key}")

    async def maybe_unsubscribe(self, symbol: str) -> None:
        """If no open positions for this symbol in registry, unsubscribe."""
        key = symbol.upper()
        if key not in self._registry or not self._registry[key]:
            await self.unsubscribe(symbol)

    async def stop_all(self) -> None:
        """Disconnect all mark price connections and REST fallback tasks (shutdown)."""
        async with self._lock:
            conns = list(self._connections.values())
            self._connections.clear()
            self._subscription_counts.clear()
            self._mark_handlers.clear()
            fallback_tasks = list(self._rest_fallback_tasks.values())
            self._rest_fallback_tasks.clear()
        for t in fallback_tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        for c in conns:
            try:
                await c.disconnect()
            except Exception as e:
                logger.debug(f"[MarkPrice] stop_all disconnect: {e}")
        async with self._http_client_lock:
            if self._http_client is not None:
                try:
                    await self._http_client.aclose()
                except Exception as e:
                    logger.debug(f"[MarkPrice] stop_all httpx close: {e}")
                self._http_client = None
