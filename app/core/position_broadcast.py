"""
Position broadcast: in-memory connection manager and broadcast service for real-time
open position updates to connected clients (Android/web) over WebSocket.

Clients connect to GET /api/ws/positions with JWT; when position state changes (or mark price
ticks), the backend calls broadcast_position_update and all connections for that user
receive the JSON payload. No DB write on tick; DB is updated only on position open/close.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional, Set
from uuid import UUID

from fastapi import WebSocket
from loguru import logger


class PositionConnectionManager:
    """Maps user_id -> set of WebSocket connections; register, unregister, broadcast_to_user."""

    def __init__(self) -> None:
        self._connections: Dict[UUID, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, user_id: UUID, websocket: WebSocket) -> None:
        """Add a WebSocket for the given user."""
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
        logger.debug(f"[PositionBroadcast] Registered connection for user {user_id}")

    async def unregister(self, user_id: UUID, websocket: WebSocket) -> None:
        """Remove a WebSocket for the given user."""
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
        logger.debug(f"[PositionBroadcast] Unregistered connection for user {user_id}")

    async def broadcast_to_user(self, user_id: UUID, payload: dict) -> None:
        """Send payload (as JSON) to all WebSockets for this user. Remove dead connections."""
        async with self._lock:
            conns = set(self._connections.get(user_id) or [])
        if not conns:
            return
        text = json.dumps(payload)
        dead: Set[WebSocket] = set()
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception as e:
                logger.debug(f"[PositionBroadcast] Send failed for user {user_id}: {e}")
                dead.add(ws)
        if dead:
            async with self._lock:
                if user_id in self._connections:
                    for w in dead:
                        self._connections[user_id].discard(w)
                    if not self._connections[user_id]:
                        del self._connections[user_id]


class PositionBroadcastService:
    """Builds position update payload and sends to all connections for the strategy's owner."""

    def __init__(self, connection_manager: PositionConnectionManager) -> None:
        self._manager = connection_manager

    async def broadcast_position_update(
        self,
        user_id: UUID,
        strategy_id: Optional[str],
        *,
        symbol: str,
        account_id: Optional[str] = None,
        position_size: float = 0,
        entry_price: Optional[float] = None,
        unrealized_pnl: Optional[float] = None,
        position_side: Optional[str] = None,
        current_price: Optional[float] = None,
        leverage: Optional[int] = None,
        liquidation_price: Optional[float] = None,
        initial_margin: Optional[float] = None,
        margin_type: Optional[str] = None,
        strategy_name: Optional[str] = None,
        max_unrealized_pnl: Optional[float] = None,
    ) -> None:
        """Broadcast a position update to all client WebSockets for this user (Binance-like fields).
        When strategy_id is None (position not owned by any strategy, e.g. manual), clients show 'Not matched'.
        """
        payload: Dict[str, Any] = {
            "type": "position_update",
            "strategy_id": strategy_id,
            "symbol": symbol,
            "account_id": account_id or "default",
            "position_size": position_size,
        }
        if strategy_name is not None:
            payload["strategy_name"] = strategy_name
        if entry_price is not None:
            payload["entry_price"] = entry_price
        if unrealized_pnl is not None:
            payload["unrealized_pnl"] = unrealized_pnl
        if position_side is not None:
            payload["position_side"] = position_side
        if current_price is not None:
            payload["current_price"] = current_price
        if leverage is not None:
            payload["leverage"] = leverage
        if liquidation_price is not None:
            payload["liquidation_price"] = liquidation_price
        # Always include initial_margin so clients can show Margin (USDT) like Binance; use 0 if None
        payload["initial_margin"] = initial_margin if initial_margin is not None else 0.0
        if margin_type is not None:
            payload["margin_type"] = margin_type
        if max_unrealized_pnl is not None:
            payload["max_unrealized_pnl"] = max_unrealized_pnl
        await self._manager.broadcast_to_user(user_id, payload)
