"""
FCM token management endpoints for push notifications.

This module provides REST API endpoints for managing Firebase Cloud Messaging (FCM)
tokens used for sending push notifications to mobile devices.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, field_validator
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.api.deps import get_current_user_async, get_async_db
from app.models.db_models import User, FCMToken

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ============================================
# Request/Response Models
# ============================================

class RegisterFCMTokenRequest(BaseModel):
    """Request model for FCM token registration."""
    token: str = Field(..., min_length=10, max_length=500, description="FCM token from Firebase")
    device_id: str = Field(..., min_length=1, max_length=255, description="Unique device identifier")
    device_type: str = Field(default="android", description="Device type (android, ios, web)")
    client_type: str = Field(default="android_app", description="Client application type (android_app, web_app, ios_app)")
    app_version: Optional[str] = Field(default=None, max_length=50, description="App version for debugging")
    device_name: Optional[str] = Field(default=None, max_length=100, description="User-friendly device name (e.g., 'Pixel 7', 'Chrome Browser')")
    
    @field_validator('device_type')
    @classmethod
    def validate_device_type(cls, v: str) -> str:
        allowed = ["android", "ios", "web"]
        if v.lower() not in allowed:
            raise ValueError(f"device_type must be one of {allowed}")
        return v.lower()
    
    @field_validator('client_type')
    @classmethod
    def validate_client_type(cls, v: str) -> str:
        allowed = ["android_app", "web_app", "ios_app"]
        if v.lower() not in allowed:
            raise ValueError(f"client_type must be one of {allowed}")
        return v.lower()


class FCMTokenResponse(BaseModel):
    """Response model for FCM token."""
    id: UUID
    device_id: str
    device_type: str
    client_type: str
    device_name: Optional[str] = None
    app_version: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class FCMTokenListResponse(BaseModel):
    """Response model for listing FCM tokens."""
    tokens: List[FCMTokenResponse]
    count: int


class ClientTypeSummary(BaseModel):
    """Summary of tokens by client type."""
    client_type: str
    total_count: int
    active_count: int


class FCMTokenSummaryResponse(BaseModel):
    """Response model for FCM token summary by client type."""
    total_tokens: int
    total_active: int
    by_client_type: List[ClientTypeSummary]
    by_device_type: dict


# ============================================
# FCM Token Endpoints
# ============================================

@router.post("/fcm/register", response_model=FCMTokenResponse)
async def register_fcm_token(
    request: RegisterFCMTokenRequest,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> FCMTokenResponse:
    """Register or update FCM token for push notifications.
    
    This endpoint should be called:
    - When app starts (if token is new)
    - When FCM token is refreshed
    - After user login
    
    The endpoint handles several scenarios:
    1. Token already exists for this user - updates device info
    2. Token exists but belongs to different user - reassigns to current user
    3. Device already has a token for this user - updates with new token
    4. New token - creates new entry
    """
    try:
        now = datetime.now(timezone.utc)
        
        # Check if token already exists (by token value)
        stmt = select(FCMToken).where(FCMToken.token == request.token)
        result = await db.execute(stmt)
        existing_token = result.scalar_one_or_none()
        
        if existing_token:
            # Token exists - update it (move to current user if different)
            existing_token.user_id = current_user.id
            existing_token.device_id = request.device_id
            existing_token.device_type = request.device_type
            existing_token.client_type = request.client_type
            existing_token.device_name = request.device_name
            existing_token.app_version = request.app_version
            existing_token.is_active = True
            existing_token.updated_at = now
            existing_token.last_used_at = now
            
            await db.commit()
            await db.refresh(existing_token)
            
            logger.info(f"Updated FCM token for user {current_user.id}, device {request.device_id}, client {request.client_type}")
            return FCMTokenResponse(
                id=existing_token.id,
                device_id=existing_token.device_id,
                device_type=existing_token.device_type,
                client_type=existing_token.client_type,
                device_name=existing_token.device_name,
                app_version=existing_token.app_version,
                is_active=existing_token.is_active,
                created_at=existing_token.created_at,
                updated_at=existing_token.updated_at,
                last_used_at=existing_token.last_used_at,
            )
        
        # Check if device already has a token for this user
        stmt = select(FCMToken).where(
            FCMToken.user_id == current_user.id,
            FCMToken.device_id == request.device_id
        )
        result = await db.execute(stmt)
        device_token = result.scalar_one_or_none()
        
        if device_token:
            # Update existing device token with new token value
            device_token.token = request.token
            device_token.device_type = request.device_type
            device_token.client_type = request.client_type
            device_token.device_name = request.device_name
            device_token.app_version = request.app_version
            device_token.is_active = True
            device_token.updated_at = now
            device_token.last_used_at = now
            
            await db.commit()
            await db.refresh(device_token)
            
            logger.info(f"Updated FCM token for device {request.device_id}, user {current_user.id}, client {request.client_type}")
            return FCMTokenResponse(
                id=device_token.id,
                device_id=device_token.device_id,
                device_type=device_token.device_type,
                client_type=device_token.client_type,
                device_name=device_token.device_name,
                app_version=device_token.app_version,
                is_active=device_token.is_active,
                created_at=device_token.created_at,
                updated_at=device_token.updated_at,
                last_used_at=device_token.last_used_at,
            )
        
        # Create new token
        from uuid import uuid4
        new_token = FCMToken(
            id=uuid4(),
            user_id=current_user.id,
            token=request.token,
            device_id=request.device_id,
            device_type=request.device_type,
            client_type=request.client_type,
            device_name=request.device_name,
            app_version=request.app_version,
            is_active=True,
            last_used_at=now,
        )
        
        db.add(new_token)
        await db.commit()
        await db.refresh(new_token)
        
        logger.info(f"Registered new FCM token for user {current_user.id}, device {request.device_id}, client {request.client_type}")
        return FCMTokenResponse(
            id=new_token.id,
            device_id=new_token.device_id,
            device_type=new_token.device_type,
            client_type=new_token.client_type,
            device_name=new_token.device_name,
            app_version=new_token.app_version,
            is_active=new_token.is_active,
            created_at=new_token.created_at,
            updated_at=new_token.updated_at,
            last_used_at=new_token.last_used_at,
        )
        
    except Exception as e:
        logger.error(f"Failed to register FCM token: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register FCM token: {str(e)}"
        )


@router.get("/fcm/tokens", response_model=FCMTokenListResponse)
async def list_fcm_tokens(
    client_type: Optional[str] = Query(default=None, description="Filter by client type (android_app, web_app, ios_app)"),
    active_only: bool = Query(default=False, description="Only return active tokens"),
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> FCMTokenListResponse:
    """List all FCM tokens for current user.
    
    Optionally filter by client_type (android_app, web_app, ios_app) to see
    which devices/applications are registered for push notifications.
    """
    try:
        # Build query with optional filters
        conditions = [FCMToken.user_id == current_user.id]
        
        if client_type:
            if client_type.lower() not in ["android_app", "web_app", "ios_app"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="client_type must be one of: android_app, web_app, ios_app"
                )
            conditions.append(FCMToken.client_type == client_type.lower())
        
        if active_only:
            conditions.append(FCMToken.is_active == True)
        
        stmt = select(FCMToken).where(*conditions).order_by(FCMToken.updated_at.desc())
        
        result = await db.execute(stmt)
        tokens = result.scalars().all()
        
        token_responses = [
            FCMTokenResponse(
                id=token.id,
                device_id=token.device_id,
                device_type=token.device_type,
                client_type=token.client_type,
                device_name=token.device_name,
                app_version=token.app_version,
                is_active=token.is_active,
                created_at=token.created_at,
                updated_at=token.updated_at,
                last_used_at=token.last_used_at,
            )
            for token in tokens
        ]
        
        return FCMTokenListResponse(tokens=token_responses, count=len(token_responses))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list FCM tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list FCM tokens: {str(e)}"
        )


@router.get("/fcm/summary", response_model=FCMTokenSummaryResponse)
async def get_fcm_token_summary(
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> FCMTokenSummaryResponse:
    """Get a summary of registered FCM tokens by client type.
    
    This helps identify how many Android app vs web app clients
    are registered for push notifications.
    """
    try:
        # Get all tokens for user
        stmt = select(FCMToken).where(FCMToken.user_id == current_user.id)
        result = await db.execute(stmt)
        tokens = result.scalars().all()
        
        # Calculate summaries
        total_tokens = len(tokens)
        total_active = sum(1 for t in tokens if t.is_active)
        
        # Group by client_type
        client_type_counts = {}
        for token in tokens:
            ct = token.client_type or "unknown"
            if ct not in client_type_counts:
                client_type_counts[ct] = {"total": 0, "active": 0}
            client_type_counts[ct]["total"] += 1
            if token.is_active:
                client_type_counts[ct]["active"] += 1
        
        by_client_type = [
            ClientTypeSummary(
                client_type=ct,
                total_count=counts["total"],
                active_count=counts["active"]
            )
            for ct, counts in client_type_counts.items()
        ]
        
        # Group by device_type
        device_type_counts = {}
        for token in tokens:
            dt = token.device_type or "unknown"
            if dt not in device_type_counts:
                device_type_counts[dt] = {"total": 0, "active": 0}
            device_type_counts[dt]["total"] += 1
            if token.is_active:
                device_type_counts[dt]["active"] += 1
        
        return FCMTokenSummaryResponse(
            total_tokens=total_tokens,
            total_active=total_active,
            by_client_type=by_client_type,
            by_device_type=device_type_counts
        )
        
    except Exception as e:
        logger.error(f"Failed to get FCM token summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get FCM token summary: {str(e)}"
        )


@router.delete("/fcm/token/{token_id}")
async def delete_fcm_token(
    token_id: UUID,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Delete FCM token (e.g., on logout or app uninstall).
    
    Only the owner of the token can delete it.
    """
    try:
        # Verify token exists and belongs to user
        stmt = select(FCMToken).where(
            FCMToken.id == token_id,
            FCMToken.user_id == current_user.id
        )
        result = await db.execute(stmt)
        token = result.scalar_one_or_none()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="FCM token not found"
            )
        
        # Delete token using delete statement
        delete_stmt = delete(FCMToken).where(FCMToken.id == token_id)
        await db.execute(delete_stmt)
        await db.commit()
        
        logger.info(f"Deleted FCM token {token_id} for user {current_user.id}")
        return {"message": "FCM token deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete FCM token: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete FCM token: {str(e)}"
        )


@router.delete("/fcm/tokens")
async def delete_all_fcm_tokens(
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Delete all FCM tokens for current user (e.g., on logout from all devices)."""
    try:
        # Delete all tokens for user
        delete_stmt = delete(FCMToken).where(FCMToken.user_id == current_user.id)
        result = await db.execute(delete_stmt)
        await db.commit()
        
        deleted_count = result.rowcount
        logger.info(f"Deleted {deleted_count} FCM tokens for user {current_user.id}")
        return {"message": f"Deleted {deleted_count} FCM token(s)"}
        
    except Exception as e:
        logger.error(f"Failed to delete all FCM tokens: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete FCM tokens: {str(e)}"
        )


@router.put("/fcm/token/{token_id}/deactivate")
async def deactivate_fcm_token(
    token_id: UUID,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> FCMTokenResponse:
    """Deactivate FCM token (stops notifications without deleting).
    
    Useful for temporarily disabling notifications for a device.
    """
    try:
        # Verify token exists and belongs to user
        stmt = select(FCMToken).where(
            FCMToken.id == token_id,
            FCMToken.user_id == current_user.id
        )
        result = await db.execute(stmt)
        token = result.scalar_one_or_none()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="FCM token not found"
            )
        
        token.is_active = False
        token.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(token)
        
        logger.info(f"Deactivated FCM token {token_id} for user {current_user.id}")
        return FCMTokenResponse(
            id=token.id,
            device_id=token.device_id,
            device_type=token.device_type,
            client_type=token.client_type,
            device_name=token.device_name,
            app_version=token.app_version,
            is_active=token.is_active,
            created_at=token.created_at,
            updated_at=token.updated_at,
            last_used_at=token.last_used_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate FCM token: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate FCM token: {str(e)}"
        )


@router.put("/fcm/token/{token_id}/activate")
async def activate_fcm_token(
    token_id: UUID,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
) -> FCMTokenResponse:
    """Activate FCM token (re-enables notifications).
    
    Useful for re-enabling notifications after they were disabled.
    """
    try:
        # Verify token exists and belongs to user
        stmt = select(FCMToken).where(
            FCMToken.id == token_id,
            FCMToken.user_id == current_user.id
        )
        result = await db.execute(stmt)
        token = result.scalar_one_or_none()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="FCM token not found"
            )
        
        token.is_active = True
        token.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(token)
        
        logger.info(f"Activated FCM token {token_id} for user {current_user.id}")
        return FCMTokenResponse(
            id=token.id,
            device_id=token.device_id,
            device_type=token.device_type,
            client_type=token.client_type,
            device_name=token.device_name,
            app_version=token.app_version,
            is_active=token.is_active,
            created_at=token.created_at,
            updated_at=token.updated_at,
            last_used_at=token.last_used_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate FCM token: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate FCM token: {str(e)}"
        )
