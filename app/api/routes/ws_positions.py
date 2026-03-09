"""
WebSocket endpoint for real-time open position updates.

Clients connect with JWT (query ?token= or first message). The backend pushes
position_update messages when position state or mark price changes.
On connect, the backend sends an initial snapshot of current positions so the
webapp shows the correct numbers without waiting for the next broadcast.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.core.auth import decode_token, get_user_id_from_token

# Served under /api/ws so reverse proxies that only forward /api/* will reach this route (fixes 404 on server)
router = APIRouter(prefix="/api/ws", tags=["websocket"])


# Close code for invalid/expired token so client can refresh (per plan)
WS_CLOSE_INVALID_TOKEN = 4001


def _build_position_payload(summary) -> dict:
    """Build the same position_update payload used by PositionBroadcastService (Binance-like fields)."""
    size = (summary.position_size or 0) if summary.position_size is not None else 0
    payload = {
        "type": "position_update",
        "strategy_id": summary.id,
        "symbol": summary.symbol,
        "account_id": summary.account_id or "default",
        "position_size": size,
    }
    if summary.entry_price is not None:
        payload["entry_price"] = summary.entry_price
    if getattr(summary, "unrealized_pnl", None) is not None:
        payload["unrealized_pnl"] = summary.unrealized_pnl
    if summary.position_side is not None:
        payload["position_side"] = summary.position_side
    if getattr(summary, "current_price", None) is not None:
        payload["current_price"] = summary.current_price
    # Leverage: always include (Binance style); use 1 if missing
    payload["leverage"] = getattr(summary, "leverage", None) if getattr(summary, "leverage", None) is not None else 1
    if getattr(summary, "liquidation_price", None) is not None:
        payload["liquidation_price"] = summary.liquidation_price
    # Always include initial_margin so clients show Margin (USDT) like Binance; use 0 if missing
    payload["initial_margin"] = getattr(summary, "initial_margin", None) if getattr(summary, "initial_margin", None) is not None else 0.0
    if getattr(summary, "margin_type", None) is not None:
        payload["margin_type"] = summary.margin_type
    return payload


async def _send_initial_position_snapshot(websocket: WebSocket, user_id) -> None:
    """Send current position state for all strategies so the webapp shows correct numbers on load."""
    app = websocket.scope.get("app") if websocket.scope else None
    if not app:
        return
    runner = getattr(app.state, "strategy_runner", None)
    if not runner:
        return
    try:
        from app.core.database import get_session_factory
        from app.services.strategy_service import StrategyService
        session_factory = get_session_factory()
        db = session_factory()
        try:
            redis = getattr(runner, "redis", None)
            strategy_service = StrategyService(db, redis)
            strategies = strategy_service.list_strategies(user_id)
            for s in strategies:
                payload = _build_position_payload(s)
                await websocket.send_text(json.dumps(payload))
            if strategies:
                logger.debug(f"[ws/positions] Sent initial snapshot: {len(strategies)} strategies for user {user_id}")
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[ws/positions] Initial snapshot failed: {e}")


@router.websocket("/positions")
async def websocket_positions(websocket: WebSocket) -> None:
    """Accept WebSocket connection; require JWT. Broadcast position updates to this user."""
    await websocket.accept()
    # Token from query string (e.g. wss://host/api/ws/positions?token=...)
    token: Optional[str] = None
    raw_qs = websocket.scope.get("query_string")
    if raw_qs:
        from urllib.parse import parse_qs
        qs_str = raw_qs.decode() if isinstance(raw_qs, bytes) else raw_qs
        qs = parse_qs(qs_str)
        tokens = qs.get("token", [])
        if tokens:
            token = tokens[0]
    if not token:
        # Allow client to send token in first text message
        try:
            first = await websocket.receive_text()
            token = first.strip()
        except Exception as e:
            logger.debug(f"[ws/positions] Failed to receive first message: {e}")
            await websocket.close(code=WS_CLOSE_INVALID_TOKEN)
            return
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=WS_CLOSE_INVALID_TOKEN)
        return
    if payload.get("type") != "access":
        await websocket.close(code=WS_CLOSE_INVALID_TOKEN)
        return
    user_id = get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=WS_CLOSE_INVALID_TOKEN)
        return
    app = websocket.scope.get("app")
    manager = getattr(app.state, "position_connection_manager", None) if app else None
    if not manager:
        await websocket.close(code=1011)  # Internal error
        return
    await manager.register(user_id, websocket)
    # Send current positions so the UI shows correct numbers without waiting for the next broadcast
    await _send_initial_position_snapshot(websocket, user_id)
    try:
        while True:
            # Keep connection alive; optional: handle ping or token refresh via messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.unregister(user_id, websocket)
