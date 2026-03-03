"""
WebSocket endpoint for real-time open position updates.

Clients connect with JWT (query ?token= or first message). The backend pushes
position_update messages when position state or mark price changes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.core.auth import decode_token, get_user_id_from_token

router = APIRouter(prefix="/ws", tags=["websocket"])


# Close code for invalid/expired token so client can refresh (per plan)
WS_CLOSE_INVALID_TOKEN = 4001


@router.websocket("/positions")
async def websocket_positions(websocket: WebSocket) -> None:
    """Accept WebSocket connection; require JWT. Broadcast position updates to this user."""
    await websocket.accept()
    # Token from query string (e.g. ws://host/ws/positions?token=...)
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
    try:
        while True:
            # Keep connection alive; optional: handle ping or token refresh via messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.unregister(user_id, websocket)
