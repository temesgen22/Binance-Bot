"""
Mark price stream manager: subscribe/unsubscribe by symbol, registry of open positions,
and handler that computes PnL and pushes to client WebSockets on each mark price tick.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger

from app.core.mark_price_connection import MarkPriceConnection
from app.core.position_broadcast import PositionBroadcastService


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
        self._registry: Dict[str, List[Dict[str, Any]]] = {}  # symbol -> list of {strategy_id, user_id, entry_price, position_size, position_side, account_id}
        self._lock = asyncio.Lock()

    def register_position(
        self,
        symbol: str,
        strategy_id: str,
        user_id: UUID,
        entry_price: float,
        position_size: float,
        position_side: str,
        account_id: Optional[str] = None,
    ) -> None:
        """Record an open position for this symbol (called when position opens)."""
        key = symbol.upper()
        if key not in self._registry:
            self._registry[key] = []
        for entry in self._registry[key]:
            if entry["strategy_id"] == strategy_id:
                entry.update(
                    entry_price=entry_price,
                    position_size=position_size,
                    position_side=position_side,
                    account_id=account_id or "default",
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
            }
        )

    def unregister_position(self, symbol: str, strategy_id: str) -> None:
        """Remove a position from the registry (called when position closes)."""
        key = symbol.upper()
        if key not in self._registry:
            return
        self._registry[key] = [e for e in self._registry[key] if e["strategy_id"] != strategy_id]
        if not self._registry[key]:
            del self._registry[key]

    def _on_mark_price_factory(self, symbol_key: str):
        async def _on_mark_price(_symbol: str, data: Dict[str, Any]) -> None:
            mark_price = data.get("mark_price")
            if mark_price is None:
                return
            entries = self._registry.get(symbol_key, [])
            for entry in entries:
                try:
                    position_side = entry.get("position_side") or "LONG"
                    unrealized_pnl = _compute_unrealized_pnl(
                        mark_price,
                        entry["entry_price"],
                        entry["position_size"],
                        position_side,
                    )
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
                    )
                except Exception as e:
                    logger.debug(f"[MarkPrice] broadcast for {entry['strategy_id']}: {e}")
        return _on_mark_price

    async def subscribe(self, symbol: str) -> None:
        """Subscribe to mark price for symbol (reference count; one connection per symbol)."""
        key = symbol.upper()
        async with self._lock:
            self._subscription_counts[key] = self._subscription_counts.get(key, 0) + 1
            if key in self._connections:
                return
            conn = MarkPriceConnection(
                symbol=key,
                testnet=self._testnet,
                on_mark_price=self._on_mark_price_factory(key),
            )
            self._connections[key] = conn
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
            return
        logger.debug(f"[MarkPrice] Subscribed: {key}")

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
        if conn:
            await conn.disconnect()
        logger.debug(f"[MarkPrice] Unsubscribed: {key}")

    async def maybe_unsubscribe(self, symbol: str) -> None:
        """If no open positions for this symbol in registry, unsubscribe."""
        key = symbol.upper()
        if key not in self._registry or not self._registry[key]:
            await self.unsubscribe(symbol)

    async def stop_all(self) -> None:
        """Disconnect all mark price connections (shutdown)."""
        async with self._lock:
            conns = list(self._connections.values())
            self._connections.clear()
            self._subscription_counts.clear()
        for c in conns:
            try:
                await c.disconnect()
            except Exception as e:
                logger.debug(f"[MarkPrice] stop_all disconnect: {e}")
