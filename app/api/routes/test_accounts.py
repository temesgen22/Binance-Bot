"""API routes for testing Binance API key accounts."""

from __future__ import annotations
import traceback

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
from loguru import logger


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
    api_env = "TESTNET" if testnet else "PRODUCTION"
    api_key_preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
    
    logger.info(f"Testing Binance account credentials ({api_env}) - API Key: {api_key_preview}")
    
    # Step 1: Create client with provided credentials
    try:
        logger.debug(f"Step 1: Creating BinanceClient for {api_env}")
        client = BinanceClient(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet
        )
        logger.debug(f"Step 1: ✅ BinanceClient created successfully")
    except Exception as e:
        # Extract error details from BinanceAPIException if available
        error_code = getattr(e, 'code', None)
        status_code = getattr(e, 'status_code', None)
        error_type = type(e).__name__
        
        logger.error(
            f"❌ Step 1 FAILED: Client creation failed for {api_env} account\n"
            f"   Step: Creating BinanceClient (this includes connection test via ping())\n"
            f"   Error Type: {error_type}\n"
            f"   Error Message: {str(e)}\n"
            f"   Error Code: {error_code}\n"
            f"   HTTP Status: {status_code}\n"
            f"   Traceback:\n{traceback.format_exc()}"
        )
        raise
    
    # Step 2: Test connection and authentication
    try:
        logger.debug(f"Step 2: Testing connection and authentication")
        rest = client._ensure()
        logger.debug(f"Step 2: ✅ Connection established, testing futures account access")
        account_info = rest.futures_account()
        logger.debug(f"Step 2: ✅ Futures account access successful")
    except Exception as e:
        error_details = {
            "step": "connection_authentication",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "testnet": testnet
        }
        # Extract detailed error information
        error_code = None
        status_code = None
        if hasattr(e, 'error_code'):
            error_code = e.error_code
        if hasattr(e, 'status_code'):
            status_code = e.status_code
        
        logger.error(
            f"❌ Step 2 FAILED: Connection/Authentication failed for {api_env} account\n"
            f"   Step: Testing futures account access\n"
            f"   Error Type: {type(e).__name__}\n"
            f"   Error Message: {str(e)}\n"
            f"   Error Code: {error_code}\n"
            f"   HTTP Status: {status_code}\n"
            f"   Traceback: {traceback.format_exc()}"
        )
        raise
    
    # Step 3: Extract account balance (may not be available)
    account_balance = None
    try:
        logger.debug(f"Step 3: Retrieving account balance")
        account_balance = client.futures_account_balance()
        logger.debug(f"Step 3: ✅ Account balance retrieved: {account_balance}")
    except Exception as e:
        logger.warning(
            f"⚠️ Step 3: Balance retrieval failed (non-critical): {str(e)}\n"
            f"   This is usually not a problem - balance may not be available for this account type"
        )
        # Balance might not be available - this is not critical
    
    # Step 4: Extract permissions from account info
    try:
        logger.debug(f"Step 4: Extracting account permissions")
        permissions = _extract_permissions(account_info)
        logger.info(
            f"✅ Account test SUCCESSFUL for {api_env}\n"
            f"   Permissions: {', '.join(permissions)}\n"
            f"   Balance: {account_balance if account_balance else 'N/A'}"
        )
    except Exception as e:
        logger.warning(f"⚠️ Step 4: Permission extraction failed: {str(e)}, using defaults")
        permissions = ["BASIC_ACCESS"]
    
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
    
    # Extract detailed error information
    error_code = None
    status_code = None
    error_type = type(exc).__name__
    
    if hasattr(exc, 'error_code'):
        error_code = exc.error_code
    if hasattr(exc, 'status_code'):
        status_code = exc.status_code
    
    # Get full traceback for logging
    full_traceback = traceback.format_exc()
    
    # Log detailed error information
    api_env = "TESTNET" if testnet else "PRODUCTION"
    account_display = account_name or "Unknown Account"
    
    logger.error(
        f"❌ Account test FAILED for '{account_display}' ({api_env})\n"
        f"   Error Type: {error_type}\n"
        f"   Error Message: {error_msg}\n"
        f"   Error Code: {error_code}\n"
        f"   HTTP Status: {status_code}\n"
        f"   Full Traceback:\n{full_traceback}"
    )
    
    # Handle specific exception types
    if isinstance(exc, BinanceNetworkError):
        detailed_error = f"Network error: {error_msg}"
        if status_code:
            detailed_error += f" (HTTP {status_code})"
        if error_code:
            detailed_error += f" [Error Code: {error_code}]"
        
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="❌ Connection Failed",
            authentication_status="❓ Not Tested",
            error=detailed_error,
            details={
                "error_type": "NETWORK_ERROR",
                "error_code": error_code,
                "status_code": status_code,
                "full_error": error_msg,
                "testnet": testnet
            }
        )
    
    # Handle 502 Bad Gateway specifically (Binance server unavailable)
    elif status_code == 502 or "502 Bad Gateway" in error_msg or "Bad Gateway" in error_msg:
        api_env = "TESTNET" if testnet else "PRODUCTION"
        detailed_error = (
            f"Binance {api_env} API is temporarily unavailable (HTTP 502 Bad Gateway). "
            f"This is NOT an authentication issue - Binance's servers are down or unreachable. "
            f"Please try again in a few minutes."
        )
        
        logger.warning(
            f"⚠️ Binance {api_env} API returned 502 Bad Gateway - this indicates Binance server issues, "
            f"not a problem with the API credentials. The account credentials may be valid, "
            f"but we cannot verify them right now due to Binance infrastructure problems."
        )
        
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="❌ Binance Server Unavailable",
            authentication_status="❓ Cannot Test (Server Down)",
            error=detailed_error,
            details={
                "error_type": "BINANCE_SERVER_UNAVAILABLE",
                "error_code": error_code,
                "status_code": 502,
                "full_error": error_msg,
                "testnet": testnet,
                "explanation": (
                    "HTTP 502 Bad Gateway means Binance's API servers are temporarily unavailable. "
                    "This is NOT a problem with your API credentials. Your credentials may be valid, "
                    "but Binance's infrastructure is experiencing issues. Common causes:"
                ),
                "common_causes": [
                    "Binance API servers are temporarily down or overloaded",
                    "Binance load balancer/nginx is experiencing issues",
                    "Network connectivity problems between your server and Binance",
                    "Binance is performing maintenance",
                    "Regional API endpoint issues"
                ],
                "solutions": [
                    "Wait a few minutes and try again",
                    "Check Binance status page or Twitter for service updates",
                    "Try switching between testnet and production (if applicable)",
                    "Check your internet connection and firewall settings",
                    "If the problem persists, contact Binance support"
                ]
            }
        )
    
    elif isinstance(exc, BinanceAuthenticationError):
        detailed_error = f"Authentication error: {error_msg}"
        if status_code:
            detailed_error += f" (HTTP {status_code})"
        if error_code:
            detailed_error += f" [Error Code: {error_code}]"
        
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="✅ Connected",
            authentication_status="❌ Authentication Failed",
            error=detailed_error,
            details={
                "error_type": "AUTHENTICATION_ERROR",
                "error_code": error_code,
                "status_code": status_code,
                "full_error": error_msg,
                "testnet": testnet,
                "common_causes": [
                    "Invalid API key or secret",
                    "API key does not have futures trading permissions",
                    "IP address not whitelisted (if IP restriction is enabled)",
                    "API key is restricted to spot trading only"
                ]
            }
        )
    
    elif isinstance(exc, BinanceAPIError):
        detailed_error = f"Binance API error: {error_msg}"
        if status_code:
            detailed_error += f" (HTTP {status_code})"
        if error_code:
            detailed_error += f" [Error Code: {error_code}]"
        
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="✅ Connected",
            authentication_status="❌ API Error",
            error=detailed_error,
            details={
                "error_type": "API_ERROR",
                "error_code": error_code,
                "status_code": status_code,
                "full_error": error_msg,
                "testnet": testnet
            }
        )
    
    # Handle generic authentication errors (check for specific error messages)
    elif "Invalid API-key" in error_msg or "Signature" in error_msg:
        detailed_error = f"Invalid API credentials: {error_msg}"
        if error_code:
            detailed_error += f" [Error Code: {error_code}]"
        
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="✅ Connected",
            authentication_status="❌ Authentication Failed",
            error=detailed_error,
            details={
                "error_type": "AUTHENTICATION_ERROR",
                "error_code": error_code,
                "status_code": status_code,
                "full_error": error_msg,
                "testnet": testnet,
                "common_causes": [
                    "API key is incorrect or has been deleted",
                    "API secret is incorrect",
                    "API key signature is invalid"
                ]
            }
        )
    
    # Generic authentication error (other authentication failures)
    elif "authentication" in error_msg.lower() or "auth" in error_msg.lower():
        detailed_error = f"Authentication error: {error_msg}"
        if error_code:
            detailed_error += f" [Error Code: {error_code}]"
        
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="✅ Connected",
            authentication_status="❌ Authentication Failed",
            error=detailed_error,
            details={
                "error_type": "AUTHENTICATION_ERROR",
                "error_code": error_code,
                "status_code": status_code,
                "full_error": error_msg,
                "testnet": testnet
            }
        )
    
    # Check for 502 Bad Gateway in generic errors (catch-all for BinanceAPIException with 502)
    elif status_code == 502 or "502" in str(status_code) or "Bad Gateway" in error_msg:
        api_env = "TESTNET" if testnet else "PRODUCTION"
        detailed_error = (
            f"Binance {api_env} API is temporarily unavailable (HTTP 502 Bad Gateway). "
            f"This is NOT an authentication issue - Binance's servers are down or unreachable. "
            f"Please try again in a few minutes."
        )
        
        logger.warning(
            f"⚠️ Binance {api_env} API returned 502 Bad Gateway - this indicates Binance server issues, "
            f"not a problem with the API credentials."
        )
        
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="❌ Binance Server Unavailable",
            authentication_status="❓ Cannot Test (Server Down)",
            error=detailed_error,
            details={
                "error_type": "BINANCE_SERVER_UNAVAILABLE",
                "error_code": error_code,
                "status_code": 502,
                "full_error": error_msg,
                "testnet": testnet,
                "explanation": (
                    "HTTP 502 Bad Gateway means Binance's API servers are temporarily unavailable. "
                    "This is NOT a problem with your API credentials."
                ),
                "common_causes": [
                    "Binance API servers are temporarily down or overloaded",
                    "Binance load balancer/nginx is experiencing issues",
                    "Network connectivity problems",
                    "Binance is performing maintenance"
                ],
                "solutions": [
                    "Wait a few minutes and try again",
                    "Check Binance status page for service updates",
                    "Try switching between testnet and production",
                    "Check your internet connection"
                ]
            }
        )
    
    # Generic fallback for unexpected errors
    else:
        detailed_error = f"Unexpected error: {error_msg}"
        if error_code:
            detailed_error += f" [Error Code: {error_code}]"
        if status_code:
            detailed_error += f" (HTTP {status_code})"
        
        return TestAccountResponse(
            success=False,
            account_name=account_name,
            testnet=testnet,
            connection_status="❌ Unknown Error",
            authentication_status="❓ Not Tested",
            error=detailed_error,
            details={
                "error_type": "UNKNOWN_ERROR",
                "error_code": error_code,
                "status_code": status_code,
                "full_error": error_msg,
                "error_class": error_type,
                "testnet": testnet,
                "traceback": full_traceback
            }
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

