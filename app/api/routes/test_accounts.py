"""API routes for testing Binance API key accounts."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.my_binance_client import BinanceClient
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import get_settings
from app.core.exceptions import (
    BinanceAPIError,
    BinanceNetworkError,
    BinanceAuthenticationError,
)
from app.api.deps import get_client_manager, get_current_user, get_db_session_dependency
from app.models.db_models import User


router = APIRouter(tags=["test-accounts"])


class TestAccountRequest(BaseModel):
    """Request model for testing an account."""
    api_key: str = Field(..., description="Binance API key")
    api_secret: str = Field(..., description="Binance API secret")
    testnet: bool = Field(default=True, description="Whether to use testnet")
    account_name: Optional[str] = Field(default=None, description="Optional account name for display")


class TestAccountResponse(BaseModel):
    """Response model for account test results."""
    success: bool
    account_name: Optional[str] = None
    testnet: bool
    connection_status: str
    authentication_status: str
    account_info: Optional[dict] = None
    balance: Optional[float] = None
    permissions: Optional[list[str]] = None
    error: Optional[str] = None
    details: Optional[dict] = None


@router.post("/api/test-account", response_model=TestAccountResponse)
async def test_account(request: TestAccountRequest) -> TestAccountResponse:
    """Test a Binance API key account.
    
    This endpoint tests:
    - Connection to Binance API (testnet or production)
    - API key authentication
    - Account permissions
    - Account balance retrieval
    - Futures account access
    
    Args:
        request: Account credentials and testnet flag
        
    Returns:
        Test results with detailed status information
    """
    try:
        # Create client with provided credentials
        client = BinanceClient(
            api_key=request.api_key,
            api_secret=request.api_secret,
            testnet=request.testnet
        )
        
        # Test 1: Connection and Authentication
        # Try to get account information (this requires valid API key)
        try:
            rest = client._ensure()
            
            # Test connection by getting account info
            account_info = rest.futures_account()
            
            # Extract account information
            account_balance = None
            try:
                account_balance = client.futures_account_balance()
            except Exception:
                pass  # Balance might not be available
            
            # Get API key permissions from account info
            permissions = []
            # Check if futures trading is enabled
            if account_info.get("canTrade", False):
                permissions.append("FUTURES_TRADING")
            if account_info.get("canDeposit", False):
                permissions.append("DEPOSIT")
            if account_info.get("canWithdraw", False):
                permissions.append("WITHDRAW")
            
            # If no permissions found, assume basic access
            if not permissions:
                permissions = ["BASIC_ACCESS"]
            
            # Prepare response
            return TestAccountResponse(
                success=True,
                account_name=request.account_name,
                testnet=request.testnet,
                connection_status="✅ Connected",
                authentication_status="✅ Authenticated",
                account_info={
                    "total_wallet_balance": float(account_info.get("totalWalletBalance", 0)),
                    "total_unrealized_profit": float(account_info.get("totalUnrealizedProfit", 0)),
                    "available_balance": float(account_info.get("availableBalance", 0)),
                    "margin_balance": float(account_info.get("marginBalance", 0)),
                },
                balance=account_balance,
                permissions=permissions,
                details={
                    "account_type": "FUTURES",
                    "can_trade": account_info.get("canTrade", False),
                    "can_deposit": account_info.get("canDeposit", False),
                    "can_withdraw": account_info.get("canWithdraw", False),
                }
            )
            
        except Exception as auth_exc:
            # Authentication failed
            error_msg = str(auth_exc)
            if "Invalid API-key" in error_msg or "Signature" in error_msg:
                return TestAccountResponse(
                    success=False,
                    account_name=request.account_name,
                    testnet=request.testnet,
                    connection_status="✅ Connected",
                    authentication_status="❌ Authentication Failed",
                    error=f"Invalid API credentials: {error_msg}",
                    details={"error_type": "AUTHENTICATION_ERROR"}
                )
            else:
                return TestAccountResponse(
                    success=False,
                    account_name=request.account_name,
                    testnet=request.testnet,
                    connection_status="✅ Connected",
                    authentication_status="❌ Authentication Failed",
                    error=f"Authentication error: {error_msg}",
                    details={"error_type": "AUTHENTICATION_ERROR"}
                )
    
    except BinanceNetworkError as e:
        return TestAccountResponse(
            success=False,
            account_name=request.account_name,
            testnet=request.testnet,
            connection_status="❌ Connection Failed",
            authentication_status="❓ Not Tested",
            error=f"Network error: {str(e)}",
            details={"error_type": "NETWORK_ERROR"}
        )
    
    except BinanceAuthenticationError as e:
        return TestAccountResponse(
            success=False,
            account_name=request.account_name,
            testnet=request.testnet,
            connection_status="✅ Connected",
            authentication_status="❌ Authentication Failed",
            error=f"Authentication error: {str(e)}",
            details={"error_type": "AUTHENTICATION_ERROR"}
        )
    
    except BinanceAPIError as e:
        return TestAccountResponse(
            success=False,
            account_name=request.account_name,
            testnet=request.testnet,
            connection_status="✅ Connected",
            authentication_status="❌ API Error",
            error=f"Binance API error: {str(e)}",
            details={"error_type": "API_ERROR"}
        )
    
    except Exception as e:
        return TestAccountResponse(
            success=False,
            account_name=request.account_name,
            testnet=request.testnet,
            connection_status="❌ Unknown Error",
            authentication_status="❓ Not Tested",
            error=f"Unexpected error: {str(e)}",
            details={"error_type": "UNKNOWN_ERROR"}
        )


@router.get("/api/test-account/quick")
async def quick_test(
    api_key: str,
    api_secret: str,
    testnet: bool = True
) -> dict:
    """Quick test endpoint for simple connectivity check.
    
    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        testnet: Whether to use testnet
        
    Returns:
        Simple success/failure status
    """
    try:
        client = BinanceClient(api_key=api_key, api_secret=api_secret, testnet=testnet)
        rest = client._ensure()
        
        # Simple connection test
        account_info = rest.futures_account()
        
        return {
            "success": True,
            "testnet": testnet,
            "can_trade": account_info.get("canTrade", False),
            "message": "Account credentials are valid"
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Account test failed: {str(e)}"
        )


@router.post("/api/test-account/{account_id}")
async def test_existing_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session_dependency)
) -> TestAccountResponse:
    """Test an existing account from database by account_id.
    
    This endpoint retrieves the account credentials from the database
    and tests them. Secrets are never exposed in the response.
    
    Args:
        account_id: The account ID to test
        request: FastAPI request object
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Test results with detailed status information
        
    Raises:
        HTTPException: If account not found
    """
    from app.services.account_service import AccountService
    from app.core.redis_storage import RedisStorage
    from app.core.config import get_settings
    
    # Get account from database
    settings = get_settings()
    redis_storage = None
    if settings.redis_enabled:
        redis_storage = RedisStorage(
            redis_url=settings.redis_url,
            enabled=settings.redis_enabled
        )
    
    account_service = AccountService(db, redis_storage)
    account_config = account_service.get_account(current_user.id, account_id)
    
    if not account_config:
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_id}' not found for current user"
        )
    
    # Create test request using the account's credentials
    request = TestAccountRequest(
        api_key=account_config.api_key,
        api_secret=account_config.api_secret,
        testnet=account_config.testnet,
        account_name=account_config.name or account_id
    )
    
    # Use the existing test_account endpoint logic
    # We'll call the internal test logic directly
    try:
        # Create client with account credentials
        client = BinanceClient(
            api_key=request.api_key,
            api_secret=request.api_secret,
            testnet=request.testnet
        )
        
        # Test connection and authentication
        try:
            rest = client._ensure()
            account_info = rest.futures_account()
            
            # Extract account information
            account_balance = None
            try:
                account_balance = client.futures_account_balance()
            except Exception:
                pass  # Balance might not be available
            
            # Get permissions from account info
            permissions = []
            if account_info.get("canTrade", False):
                permissions.append("FUTURES_TRADING")
            if account_info.get("canDeposit", False):
                permissions.append("DEPOSIT")
            if account_info.get("canWithdraw", False):
                permissions.append("WITHDRAW")
            
            if not permissions:
                permissions = ["BASIC_ACCESS"]
            
            return TestAccountResponse(
                success=True,
                account_name=request.account_name,
                testnet=request.testnet,
                connection_status="✅ Connected",
                authentication_status="✅ Authenticated",
                account_info={
                    "total_wallet_balance": float(account_info.get("totalWalletBalance", 0)),
                    "total_unrealized_profit": float(account_info.get("totalUnrealizedProfit", 0)),
                    "available_balance": float(account_info.get("availableBalance", 0)),
                    "margin_balance": float(account_info.get("marginBalance", 0)),
                },
                balance=account_balance,
                permissions=permissions,
                details={
                    "account_type": "FUTURES",
                    "can_trade": account_info.get("canTrade", False),
                    "can_deposit": account_info.get("canDeposit", False),
                    "can_withdraw": account_info.get("canWithdraw", False),
                }
            )
            
        except Exception as auth_exc:
            error_msg = str(auth_exc)
            if "Invalid API-key" in error_msg or "Signature" in error_msg:
                return TestAccountResponse(
                    success=False,
                    account_name=request.account_name,
                    testnet=request.testnet,
                    connection_status="✅ Connected",
                    authentication_status="❌ Authentication Failed",
                    error=f"Invalid API credentials: {error_msg}",
                    details={"error_type": "AUTHENTICATION_ERROR"}
                )
            else:
                return TestAccountResponse(
                    success=False,
                    account_name=request.account_name,
                    testnet=request.testnet,
                    connection_status="✅ Connected",
                    authentication_status="❌ Authentication Failed",
                    error=f"Authentication error: {error_msg}",
                    details={"error_type": "AUTHENTICATION_ERROR"}
                )
    
    except BinanceNetworkError as e:
        return TestAccountResponse(
            success=False,
            account_name=request.account_name,
            testnet=request.testnet,
            connection_status="❌ Connection Failed",
            authentication_status="❓ Not Tested",
            error=f"Network error: {str(e)}",
            details={"error_type": "NETWORK_ERROR"}
        )
    
    except BinanceAuthenticationError as e:
        return TestAccountResponse(
            success=False,
            account_name=request.account_name,
            testnet=request.testnet,
            connection_status="✅ Connected",
            authentication_status="❌ Authentication Failed",
            error=f"Authentication error: {str(e)}",
            details={"error_type": "AUTHENTICATION_ERROR"}
        )
    
    except BinanceAPIError as e:
        return TestAccountResponse(
            success=False,
            account_name=request.account_name,
            testnet=request.testnet,
            connection_status="✅ Connected",
            authentication_status="❌ API Error",
            error=f"Binance API error: {str(e)}",
            details={"error_type": "API_ERROR"}
        )
    
    except Exception as e:
        return TestAccountResponse(
            success=False,
            account_name=request.account_name,
            testnet=request.testnet,
            connection_status="❌ Unknown Error",
            authentication_status="❓ Not Tested",
            error=f"Unexpected error: {str(e)}",
            details={"error_type": "UNKNOWN_ERROR"}
        )

