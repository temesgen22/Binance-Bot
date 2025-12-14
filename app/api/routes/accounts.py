"""API routes for managing Binance accounts."""
import os
import re
from fastapi import APIRouter, Depends, Request, HTTPException, status
from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.core.binance_client_manager import BinanceClientManager
from app.core.config import BinanceAccountConfig
from app.api.deps import get_current_user, get_db_session_dependency, get_client_manager
from app.models.db_models import User
from app.services.account_service import AccountService
from app.core.redis_storage import RedisStorage
from app.core.config import get_settings
from sqlalchemy.orm import Session
from loguru import logger


router = APIRouter(prefix="/accounts", tags=["accounts"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class CreateAccountRequest(BaseModel):
    """Request to create a new exchange account."""
    account_id: str = Field(..., min_length=1, max_length=50, description="Account identifier (unique per user)")
    api_key: str = Field(..., description="Exchange API key")
    api_secret: str = Field(..., description="Exchange API secret")
    name: Optional[str] = Field(None, max_length=255, description="Account display name")
    exchange_platform: str = Field("binance", description="Exchange platform name (binance, bybit, etc.)")
    testnet: bool = Field(True, description="Whether this is a testnet account")
    is_default: bool = Field(False, description="Set as default account for user")


class UpdateAccountRequest(BaseModel):
    """Request to update an account."""
    name: Optional[str] = Field(None, max_length=255, description="Account display name")
    exchange_platform: Optional[str] = Field(None, description="Exchange platform name")
    testnet: Optional[bool] = Field(None, description="Whether this is a testnet account")
    is_default: Optional[bool] = Field(None, description="Set as default account")
    is_active: Optional[bool] = Field(None, description="Activate/deactivate account")


class AccountResponse(BaseModel):
    """Account information response (without sensitive data)."""
    account_id: str
    name: Optional[str]
    exchange_platform: str
    testnet: bool
    is_default: bool
    is_active: bool
    created_at: str

    @classmethod
    def from_account(cls, account) -> "AccountResponse":
        """Create AccountResponse from Account model."""
        return cls(
            account_id=account.account_id,
            name=account.name,
            exchange_platform=getattr(account, 'exchange_platform', 'binance'),
            testnet=account.testnet,
            is_default=account.is_default,
            is_active=account.is_active,
            created_at=account.created_at.isoformat() if account.created_at else ""
        )


def get_client_manager(request: Request) -> BinanceClientManager:
    """Dependency to get BinanceClientManager from app state."""
    if not hasattr(request.app.state, 'binance_client_manager'):
        from loguru import logger
        logger.warning("binance_client_manager not found in app state, creating fallback")
        # Try to create one as fallback
        from app.core.binance_client_manager import BinanceClientManager
        from app.core.config import get_settings
        # Get settings (accounts are in database, not .env)
        get_settings.cache_clear()
        settings = get_settings()
        manager = BinanceClientManager(settings)
        request.app.state.binance_client_manager = manager
        logger.info(f"Created BinanceClientManager as fallback with {len(manager.list_accounts())} accounts")
    return request.app.state.binance_client_manager


@router.get("/debug")
def debug_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency)
) -> Dict:
    """Debug endpoint to check account loading status."""
    try:
        settings = get_settings()
        redis_storage = None
        if settings.redis_enabled:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
        
        account_service = AccountService(db, redis_storage)
        db_accounts = account_service.db_service.get_user_accounts(current_user.id)
        
        return {
            'database_accounts_count': len(db_accounts),
            'database_account_ids': [acc.account_id for acc in db_accounts],
            'user_id': str(current_user.id),
            'user_email': current_user.email,
            'note': 'Accounts are stored in database only (no .env loading)'
        }
    except Exception as e:
        logger.error(f"Error in debug_accounts: {e}")
        return {
            'error': str(e),
            'note': 'Accounts are stored in database only (no .env loading)'
        }




@router.get("/list", response_model=List[AccountResponse])
def list_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency),
    include_env: bool = False
) -> List[AccountResponse]:
    """List all Binance accounts for the current user.
    
    Returns accounts from database (multi-user mode).
    Optionally includes accounts from .env file if include_env=True.
    """
    result = []
    
    # Get accounts from database (multi-user mode)
    try:
        settings = get_settings()
        redis_storage = None
        if settings.redis_enabled:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
        
        account_service = AccountService(db, redis_storage)
        db_accounts = account_service.db_service.get_user_accounts(current_user.id)
        
        for acc in db_accounts:
            response = AccountResponse.from_account(acc)
            # Add source marker (can be extended later)
            result.append(response)
    except Exception as e:
        logger.warning(f"Error loading accounts from database: {e}")
    
    # Optionally include .env accounts (for display purposes)
    # Note: This requires a Request object, so we'll handle it differently
    # For now, return only database accounts - frontend can call /accounts/env separately
    
    return result


@router.post("/", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    request: CreateAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency)
) -> AccountResponse:
    """Create a new Binance account for the current user."""
    try:
        settings = get_settings()
        redis_storage = None
        if settings.redis_enabled:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
        
        account_service = AccountService(db, redis_storage)
        
        # Check if account_id already exists for this user
        existing = account_service.db_service.get_account_by_id(current_user.id, request.account_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account '{request.account_id}' already exists"
            )
        
        # Create account
        config = account_service.create_account(
            user_id=current_user.id,
            account_id=request.account_id,
            api_key=request.api_key,
            api_secret=request.api_secret,
            name=request.name,
            exchange_platform=request.exchange_platform,
            testnet=request.testnet,
            is_default=request.is_default
        )
        
        # Get the created account from database
        db_account = account_service.db_service.get_account_by_id(current_user.id, request.account_id)
        if not db_account:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Account created but could not be retrieved"
            )
        
        logger.info(f"Created account {request.account_id} for user {current_user.id}")
        return AccountResponse.from_account(db_account)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create account: {str(e)}"
        )


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency)
) -> AccountResponse:
    """Get a specific account by ID."""
    try:
        settings = get_settings()
        redis_storage = None
        if settings.redis_enabled:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
        
        account_service = AccountService(db, redis_storage)
        db_account = account_service.db_service.get_account_by_id(current_user.id, account_id)
        
        if not db_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_id}' not found"
            )
        
        return AccountResponse.from_account(db_account)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get account: {str(e)}"
        )


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: str,
    request: UpdateAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency)
) -> AccountResponse:
    """Update an account."""
    try:
        settings = get_settings()
        redis_storage = None
        if settings.redis_enabled:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
        
        account_service = AccountService(db, redis_storage)
        
        # Build update dict
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.exchange_platform is not None:
            updates["exchange_platform"] = request.exchange_platform
        if request.testnet is not None:
            updates["testnet"] = request.testnet
        if request.is_default is not None:
            updates["is_default"] = request.is_default
        if request.is_active is not None:
            updates["is_active"] = request.is_active
        
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        config = account_service.update_account(current_user.id, account_id, **updates)
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_id}' not found"
            )
        
        db_account = account_service.db_service.get_account_by_id(current_user.id, account_id)
        return AccountResponse.from_account(db_account)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update account: {str(e)}"
        )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency)
):
    """Delete (deactivate) an account."""
    try:
        settings = get_settings()
        redis_storage = None
        if settings.redis_enabled:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
        
        account_service = AccountService(db, redis_storage)
        success = account_service.delete_account(current_user.id, account_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_id}' not found"
            )
        
        logger.info(f"Deleted account {account_id} for user {current_user.id}")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )

