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
from app.api.deps import get_client_manager, get_current_user, get_db_session_dependency, get_account_service
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


def _extract_permissions(account_info: dict) -> list[str]:
    """Extract permissions from Binance account info.
    
    Args:
        account_info: Account info dictionary from Binance API
        
    Returns:
        List of permission strings
    """
    permissions = []
    if account_info.get("canTrade", False):
        permissions.append("FUTURES_TRADING")
    if account_info.get("canDeposit", False):
        permissions.append("DEPOSIT")
    if account_info.get("canWithdraw", False):
        permissions.append("WITHDRAW")
    
    # If no permissions found, assume basic access
    if not permissions:
        permissions = ["BASIC_ACCESS"]
    
    return permissions


def _test_binance_account_credentials(
    api_key: str,
    api_secret: str,
    testnet: bool
) -> dict:
    """Test Binance account credentials and return account information.
    
    This function centralizes the account testing logic to eliminate duplication
    across test_account() and test_existing_account() endpoints.
    
    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        testnet: Whether to use testnet
        
    Returns:
        Dictionary containing:
        - account_info: Raw account info from Binance
        - balance: Account balance (float or None)
        - permissions: List of permission strings
        
    Raises:
        Exception: Any exception from Binance API calls
    """
    # Create client with provided credentials
    client = BinanceClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet
    )
    
    # Test connection and authentication
    rest = client._ensure()
    account_info = rest.futures_account()
    
    # Extract account balance (may not be available)
    account_balance = None
    try:
        account_balance = client.futures_account_balance()
    except Exception:
        pass  # Balance might not be available
    
    # Extract permissions from account info
    permissions = _extract_permissions(account_info)
    
    return {
        "account_info": account_info,
        "balance": account_balance,
        "permissions": permissions,
    }


def _build_test_account_response(
    account_data: dict,
    account_name: Optional[str],
    testnet: bool
) -> TestAccountResponse:
    """Build TestAccountResponse from account test data.
    
    Args:
        account_data: Dictionary returned from _test_binance_account_credentials
        account_name: Optional account name for display
        testnet: Whether this is a testnet account
        
    Returns:
        TestAccountResponse with account information
    """
    account_info = account_data["account_info"]
    
    return TestAccountResponse(
        success=True,
        account_name=account_name,
        testnet=testnet,
        connection_status="✅ Connected",
        authentication_status="✅ Authenticated",
        account_info={
            "total_wallet_balance": float(account_info.get("totalWalletBalance", 0)),
            "total_unrealized_profit": float(account_info.get("totalUnrealizedProfit", 0)),
            "available_balance": float(account_info.get("availableBalance", 0)),
            "margin_balance": float(account_info.get("marginBalance", 0)),
        },
        balance=account_data["balance"],
        permissions=account_data["permissions"],
        details={
            "account_type": "FUTURES",
            "can_trade": account_info.get("canTrade", False),
            "can_deposit": account_info.get("canDeposit", False),
            "can_withdraw": account_info.get("canWithdraw", False),
        }
    )


def _handle_test_account_error(
    exc: Exception,
    account_name: Optional[str],
    testnet: bool
) -> TestAccountResponse:
    """Handle errors for account testing endpoints.
    
    This function centralizes error handling logic to eliminate duplication
    across test_account() and test_existing_account() endpoints.
    
    Args:
        exc: The exception that was raised
        account_name: Optional account name for the response
        testnet: Whether this is a testnet account
        
    Returns:
        TestAccountResponse with appropriate error details
    """
    error_msg = str(exc)
    
    # Handle specific exception types
    if isinstance(exc, BinanceNetworkError):
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="❌ Connection Failed",
            authentication_status="❓ Not Tested",
            error=f"Network error: {error_msg}",
            details={"error_type": "NETWORK_ERROR"}
        )
    
    elif isinstance(exc, BinanceAuthenticationError):
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="✅ Connected",
            authentication_status="❌ Authentication Failed",
            error=f"Authentication error: {error_msg}",
            details={"error_type": "AUTHENTICATION_ERROR"}
        )
    
    elif isinstance(exc, BinanceAPIError):
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="✅ Connected",
            authentication_status="❌ API Error",
            error=f"Binance API error: {error_msg}",
            details={"error_type": "API_ERROR"}
        )
    
    # Handle generic authentication errors (check for specific error messages)
    elif "Invalid API-key" in error_msg or "Signature" in error_msg:
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="✅ Connected",
            authentication_status="❌ Authentication Failed",
            error=f"Invalid API credentials: {error_msg}",
            details={"error_type": "AUTHENTICATION_ERROR"}
        )
    
    # Generic authentication error (other authentication failures)
    elif "authentication" in error_msg.lower() or "auth" in error_msg.lower():
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="✅ Connected",
            authentication_status="❌ Authentication Failed",
            error=f"Authentication error: {error_msg}",
            details={"error_type": "AUTHENTICATION_ERROR"}
        )
    
    # Generic fallback for unexpected errors
    else:
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="❌ Unknown Error",
            authentication_status="❓ Not Tested",
            error=f"Unexpected error: {error_msg}",
            details={"error_type": "UNKNOWN_ERROR"}
        )


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
        # Test account credentials using shared helper
        account_data = _test_binance_account_credentials(
            api_key=request.api_key,
            api_secret=request.api_secret,
            testnet=request.testnet
        )
        
        # Build and return response
        return _build_test_account_response(
            account_data=account_data,
            account_name=request.account_name,
            testnet=request.testnet
        )
    
    except (BinanceNetworkError, BinanceAuthenticationError, BinanceAPIError) as e:
        return _handle_test_account_error(e, request.account_name, request.testnet)
    
    except Exception as e:
        return _handle_test_account_error(e, request.account_name, request.testnet)


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
    account_service: AccountService = Depends(get_account_service)
) -> TestAccountResponse:
    """Test an existing account from database by account_id.
    
    This endpoint retrieves the account credentials from the database
    and tests them. Secrets are never exposed in the response.
    
    Args:
        account_id: The account ID to test
        current_user: Current authenticated user
        account_service: AccountService dependency
        
    Returns:
        Test results with detailed status information
        
    Raises:
        HTTPException: If account not found
    """
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
    
    # Test account credentials using shared helper
    try:
        account_data = _test_binance_account_credentials(
            api_key=request.api_key,
            api_secret=request.api_secret,
            testnet=request.testnet
        )
        
        # Build and return response
        return _build_test_account_response(
            account_data=account_data,
            account_name=request.account_name,
            testnet=request.testnet
        )
    
    except (BinanceNetworkError, BinanceAuthenticationError, BinanceAPIError) as e:
        return _handle_test_account_error(e, request.account_name, request.testnet)
    
    except Exception as e:
        return _handle_test_account_error(e, request.account_name, request.testnet)

