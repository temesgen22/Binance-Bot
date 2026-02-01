"""API routes for managing Binance accounts."""
import os
import re
from fastapi import APIRouter, Depends, Request, HTTPException, status
from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.core.binance_client_manager import BinanceClientManager
from app.core.config import BinanceAccountConfig
from app.api.deps import (
    get_current_user, get_current_user_async,
    get_db_session_dependency, get_async_db,
    get_client_manager, get_account_service, get_account_service_async
)
from fastapi import Request
from app.models.db_models import User
from app.services.account_service import AccountService
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger


router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class CreateAccountRequest(BaseModel):
    """Request to create a new exchange account."""
    account_id: str = Field(..., min_length=1, max_length=50, description="Account identifier (unique per user)")
    api_key: Optional[str] = Field(None, description="Exchange API key (required for live trading, optional for paper trading)")
    api_secret: Optional[str] = Field(None, description="Exchange API secret (required for live trading, optional for paper trading)")
    name: Optional[str] = Field(None, max_length=255, description="Account display name")
    exchange_platform: str = Field("binance", description="Exchange platform name (binance, bybit, etc.)")
    testnet: bool = Field(True, description="Whether this is a testnet account")
    is_default: bool = Field(False, description="Set as default account for user")
    paper_trading: bool = Field(False, description="Whether this is a paper trading account (simulated trading)")
    paper_balance: Optional[float] = Field(None, description="Initial virtual balance for paper trading (default: 10000 USDT)")


class UpdateAccountRequest(BaseModel):
    """Request to update an account."""
    name: Optional[str] = Field(None, max_length=255, description="Account display name")
    exchange_platform: Optional[str] = Field(None, description="Exchange platform name")
    testnet: Optional[bool] = Field(None, description="Whether this is a testnet account")
    is_default: Optional[bool] = Field(None, description="Set as default account")
    is_active: Optional[bool] = Field(None, description="Activate/deactivate account")
    paper_balance: Optional[float] = Field(None, description="Update virtual balance for paper trading account")


class AccountResponse(BaseModel):
    """Account information response (without sensitive data)."""
    account_id: str
    name: Optional[str]
    exchange_platform: str
    testnet: bool
    is_default: bool
    is_active: bool
    paper_trading: bool
    paper_balance: Optional[float]
    created_at: str

    @classmethod
    def from_account(cls, account) -> "AccountResponse":
        """Create AccountResponse from Account model."""
        # Handle paper_trading: ensure it's always a boolean (default False if None)
        paper_trading = getattr(account, 'paper_trading', False)
        if paper_trading is None:
            paper_trading = False
        
        return cls(
            account_id=account.account_id,
            name=account.name,
            exchange_platform=getattr(account, 'exchange_platform', 'binance'),
            testnet=account.testnet,
            is_default=account.is_default,
            is_active=account.is_active,
            paper_trading=paper_trading,
            paper_balance=float(account.paper_balance) if hasattr(account, 'paper_balance') and account.paper_balance else None,
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
async def debug_accounts(
    request: Request,
    current_user: User = Depends(get_current_user_async),
    account_service: AccountService = Depends(get_account_service_async)
) -> Dict:
    """Debug endpoint to check account loading status."""
    try:
        db_accounts = await account_service.db_service.async_get_user_accounts(current_user.id)
        
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
async def list_accounts(
    request: Request,
    current_user: User = Depends(get_current_user_async),
    account_service: AccountService = Depends(get_account_service_async),
    include_env: bool = False,
    include_inactive: bool = False
) -> List[AccountResponse]:
    """List all Binance accounts for the current user.
    
    Returns accounts from database (multi-user mode).
    Optionally includes accounts from .env file if include_env=True.
    Optionally includes inactive accounts if include_inactive=True.
    """
    result = []
    
    # Get accounts from database (multi-user mode) - async
    try:
        if include_inactive:
            # Get all accounts including inactive ones
            from sqlalchemy import select
            from app.models.db_models import Account
            async_db = account_service.db_service.db
            query_result = await async_db.execute(
                select(Account).filter(Account.user_id == current_user.id)
            )
            db_accounts = list(query_result.scalars().all())
        else:
            # Get only active accounts (default behavior)
            db_accounts = await account_service.db_service.async_get_user_accounts(current_user.id)
        
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
async def create_account(
    request_data: CreateAccountRequest,
    request: Request,
    current_user: User = Depends(get_current_user_async),
    account_service: AccountService = Depends(get_account_service_async)
) -> AccountResponse:
    """Create a new Binance account for the current user."""
    try:
        
        # Check if account_id already exists for this user (async)
        existing = await account_service.db_service.async_get_account_by_id(current_user.id, request_data.account_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account '{request_data.account_id}' already exists"
            )
        
        # Create account (sync method for now - create_account is still sync)
        config = account_service.create_account(
            user_id=current_user.id,
            account_id=request_data.account_id,
            api_key=request_data.api_key,
            api_secret=request_data.api_secret,
            name=request_data.name,
            exchange_platform=request_data.exchange_platform,
            testnet=request_data.testnet,
            is_default=request_data.is_default,
            paper_trading=request_data.paper_trading,
            paper_balance=request_data.paper_balance
        )
        
        # Get the created account from database (async)
        db_account = await account_service.db_service.async_get_account_by_id(current_user.id, request_data.account_id)
        if not db_account:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Account created but could not be retrieved"
            )
        
        logger.info(f"Created account {request_data.account_id} for user {current_user.id}")
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
async def get_account(
    account_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_async),
    account_service: AccountService = Depends(get_account_service_async),
    include_inactive: bool = True
) -> AccountResponse:
    """Get a specific account by ID.
    
    By default, includes inactive accounts (for editing purposes).
    Set include_inactive=False to only get active accounts.
    """
    try:
        # For editing, we need to get account even if inactive
        if include_inactive:
            from sqlalchemy import select
            from app.models.db_models import Account
            async_db = account_service.db_service.db
            account_id_lower = account_id.lower().strip() if account_id else None
            if not account_id_lower:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid account_id"
                )
            result = await async_db.execute(
                select(Account).filter(
                    Account.user_id == current_user.id,
                    Account.account_id.ilike(account_id_lower)
                )
            )
            db_account = result.scalar_one_or_none()
        else:
            # Only get active accounts
            db_account = await account_service.db_service.async_get_account_by_id(current_user.id, account_id)
        
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
async def update_account(
    account_id: str,
    request_data: UpdateAccountRequest,
    request: Request,
    current_user: User = Depends(get_current_user_async),
    account_service: AccountService = Depends(get_account_service_async)
) -> AccountResponse:
    """Update an account."""
    try:
        
        # Build update dict
        updates = {}
        if request_data.name is not None:
            updates["name"] = request_data.name
        if request_data.exchange_platform is not None:
            updates["exchange_platform"] = request_data.exchange_platform
        if request_data.testnet is not None:
            updates["testnet"] = request_data.testnet
        if request_data.is_default is not None:
            updates["is_default"] = request_data.is_default
        if request_data.is_active is not None:
            updates["is_active"] = request_data.is_active
        if request_data.paper_balance is not None:
            updates["paper_balance"] = request_data.paper_balance
        
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        # Update account (async)
        config = await account_service.async_update_account(current_user.id, account_id, **updates)
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_id}' not found"
            )
        
        # Get updated account from database (async)
        # Note: If account was deactivated, async_get_account_by_id won't find it (filters by is_active=True)
        # So we need to get it directly without the is_active filter
        from sqlalchemy import select
        from app.models.db_models import Account
        async_db = account_service.db_service.db
        account_id_lower = account_id.lower().strip() if account_id else None
        if account_id_lower:
            result = await async_db.execute(
                select(Account).filter(
                    Account.user_id == current_user.id,
                    Account.account_id.ilike(account_id_lower)
                )
            )
            db_account = result.scalar_one_or_none()
        else:
            db_account = None
        
        if not db_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_id}' not found"
            )
        
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
async def delete_account(
    account_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_async),
    account_service: AccountService = Depends(get_account_service_async)
):
    """Permanently delete an account from the database.
    
    This is a HARD DELETE that permanently removes the account record.
    This action cannot be undone.
    
    The account will be deleted only if it has no associated strategies.
    If strategies exist, use deactivate (PUT with is_active=False) instead.
    """
    try:
        success = await account_service.async_delete_account(current_user.id, account_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_id}' not found"
            )
        
        logger.info(f"Permanently deleted account {account_id} for user {current_user.id}")
        return None
        
    except ValueError as e:
        # Handle ValueError from strategy constraint check
        logger.warning(f"Cannot delete account {account_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )

