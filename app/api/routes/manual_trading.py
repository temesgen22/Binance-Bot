"""API routes for manual trading feature."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.api.deps import (
    get_current_user,
    get_database_service,
    get_client_manager,
    get_notification_service,
    get_position_broadcast_service,
    get_mark_price_stream_manager,
)
from app.core.binance_client_manager import BinanceClientManager
from app.core.position_broadcast import PositionBroadcastService
from app.models.db_models import User
from app.models.manual_trading import (
    ManualOpenRequest,
    ManualCloseRequest,
    ManualModifyTPSLRequest,
    ManualOpenResponse,
    ManualCloseResponse,
    ManualModifyResponse,
    ManualPositionResponse,
    ManualPositionListResponse,
)
from app.services.database_service import DatabaseService
from app.services.manual_trading_service import ManualTradingService
from app.services.notifier import NotificationService


router = APIRouter(prefix="/api/manual-trades", tags=["Manual Trading"])


def _get_manual_trading_service(
    current_user: User,
    db_service: DatabaseService,
    client_manager: BinanceClientManager,
    notification_service: Optional[NotificationService],
    broadcast_service: Optional[PositionBroadcastService],
    mark_price_stream_manager=None,
) -> ManualTradingService:
    """Helper to create ManualTradingService instance."""
    return ManualTradingService(
        db=db_service.db,
        client_manager=client_manager,
        user_id=current_user.id,
        notification_service=notification_service,
        broadcast_service=broadcast_service,
        mark_price_stream_manager=mark_price_stream_manager,
    )


@router.post("/open", response_model=ManualOpenResponse, status_code=status.HTTP_201_CREATED)
async def open_manual_position(
    request: ManualOpenRequest,
    current_user: User = Depends(get_current_user),
    db_service: DatabaseService = Depends(get_database_service),
    client_manager: BinanceClientManager = Depends(get_client_manager),
    notification_service: NotificationService = Depends(get_notification_service),
    broadcast_service: PositionBroadcastService = Depends(get_position_broadcast_service),
    mark_price_stream_manager=Depends(get_mark_price_stream_manager),
) -> ManualOpenResponse:
    """
    Open a manual position with optional TP/SL orders.
    
    - Places a market order to open the position
    - Optionally sets leverage and margin type
    - Places Binance native TP/SL orders if specified
    - Supports trailing stop
    """
    try:
        service = _get_manual_trading_service(
            current_user, db_service, client_manager,
            notification_service, broadcast_service, mark_price_stream_manager,
        )
        return await service.open_position(request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to open manual position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to open position: {str(e)}"
        )


@router.post("/close", response_model=ManualCloseResponse)
async def close_manual_position(
    request: ManualCloseRequest,
    current_user: User = Depends(get_current_user),
    db_service: DatabaseService = Depends(get_database_service),
    client_manager: BinanceClientManager = Depends(get_client_manager),
    notification_service: NotificationService = Depends(get_notification_service),
    broadcast_service: PositionBroadcastService = Depends(get_position_broadcast_service),
    mark_price_stream_manager=Depends(get_mark_price_stream_manager),
) -> ManualCloseResponse:
    """
    Close a manual position (full or partial).
    
    - Cancels existing TP/SL orders
    - Places market order to close
    - Calculates realized PnL
    """
    try:
        service = _get_manual_trading_service(
            current_user, db_service, client_manager,
            notification_service, broadcast_service, mark_price_stream_manager,
        )
        return await service.close_position(request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to close manual position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close position: {str(e)}"
        )


@router.put("/modify-tp-sl", response_model=ManualModifyResponse)
async def modify_tp_sl(
    request: ManualModifyTPSLRequest,
    current_user: User = Depends(get_current_user),
    db_service: DatabaseService = Depends(get_database_service),
    client_manager: BinanceClientManager = Depends(get_client_manager),
) -> ManualModifyResponse:
    """
    Modify TP/SL orders on an existing position.
    
    - Can update TP price/percentage
    - Can update SL price/percentage
    - Can cancel existing TP/SL orders
    - Can enable/disable trailing stop
    """
    try:
        service = _get_manual_trading_service(
            current_user, db_service, client_manager,
            None, None  # No notifications needed for modify
        )
        return await service.modify_tp_sl(request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to modify TP/SL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to modify TP/SL: {str(e)}"
        )


@router.get("/positions", response_model=ManualPositionListResponse)
async def list_manual_positions(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: OPEN, CLOSED, etc."),
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    current_user: User = Depends(get_current_user),
    db_service: DatabaseService = Depends(get_database_service),
    client_manager: BinanceClientManager = Depends(get_client_manager),
) -> ManualPositionListResponse:
    """
    List manual positions with optional filters.
    
    - Filter by status (OPEN, CLOSED, TP_HIT, SL_HIT, etc.)
    - Filter by account ID
    - Filter by symbol
    - Returns positions with current market data for open positions
    """
    try:
        service = _get_manual_trading_service(
            current_user, db_service, client_manager,
            None, None
        )
        return await service.list_positions(
            status=status_filter,
            account_id=account_id,
            symbol=symbol,
        )
    except Exception as e:
        logger.error(f"Failed to list manual positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list positions: {str(e)}"
        )


@router.get("/positions/{position_id}", response_model=ManualPositionResponse)
async def get_manual_position(
    position_id: UUID,
    current_user: User = Depends(get_current_user),
    db_service: DatabaseService = Depends(get_database_service),
    client_manager: BinanceClientManager = Depends(get_client_manager),
) -> ManualPositionResponse:
    """Get a single manual position with current market data."""
    try:
        service = _get_manual_trading_service(
            current_user, db_service, client_manager,
            None, None
        )
        return await service.get_position(position_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get manual position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get position: {str(e)}"
        )
