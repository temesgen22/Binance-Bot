"""Tests for test accounts API endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import BinanceAccountConfig, get_settings
from app.core.my_binance_client import BinanceClient
from app.core.exceptions import (
    BinanceAPIError,
    BinanceNetworkError,
    BinanceAuthenticationError,
)


@pytest.fixture
def mock_binance_client():
    """Create a mock BinanceClient."""
    client = MagicMock(spec=BinanceClient)
    client._ensure = MagicMock(return_value=MagicMock())
    return client


@pytest.fixture
def mock_client_manager():
    """Create a mock BinanceClientManager."""
    manager = MagicMock(spec=BinanceClientManager)
    return manager


@pytest.fixture
def test_client(mock_client_manager):
    """Create a test client with mocked dependencies."""
    from uuid import uuid4
    from app.models.db_models import User
    from app.api.deps import get_current_user, get_db_session_dependency
    from unittest.mock import MagicMock
    
    # Create a mock user for authentication
    mock_user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed",
        is_active=True
    )
    
    # Create a mock database session
    mock_db_session = MagicMock()
    
    # Override dependencies
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session_dependency] = lambda: mock_db_session
    
    try:
        # Ensure app state is set up
        if not hasattr(app.state, 'binance_client_manager'):
            app.state.binance_client_manager = mock_client_manager
        
        # Set a default client for backward compatibility
        if not hasattr(app.state, 'binance_client'):
            app.state.binance_client = MagicMock()
        
        yield TestClient(app)
    finally:
        # Clean up dependency overrides
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session_dependency, None)


class TestTestAccountEndpoint:
    """Tests for POST /api/test-account endpoint (manual testing)."""
    
    def test_test_account_success(self, test_client, mock_binance_client):
        """Test successful account testing."""
        # Mock the BinanceClient creation and futures_account call
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            # Mock successful account info
            mock_rest.futures_account.return_value = {
                "totalWalletBalance": "1000.0",
                "totalUnrealizedProfit": "50.0",
                "availableBalance": "950.0",
                "marginBalance": "1050.0",
                "canTrade": True,
                "canDeposit": True,
                "canWithdraw": True,
            }
            
            # Mock balance retrieval
            mock_binance_client.futures_account_balance.return_value = 1000.0
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True,
                    "account_name": "Test Account"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["account_name"] == "Test Account"
            assert data["testnet"] is True
            assert data["connection_status"] == "✅ Connected"
            assert data["authentication_status"] == "✅ Authenticated"
            assert data["account_info"]["total_wallet_balance"] == 1000.0
            assert data["balance"] == 1000.0
            assert "FUTURES_TRADING" in data["permissions"]
            assert data["details"]["can_trade"] is True
    
    def test_test_account_authentication_failed(self, test_client, mock_binance_client):
        """Test account testing with invalid credentials."""
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            # Mock authentication error
            mock_rest.futures_account.side_effect = Exception("Invalid API-key")
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "invalid_key",
                    "api_secret": "invalid_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Authentication Failed" in data["authentication_status"]
            assert "Invalid API credentials" in data["error"]
            assert data["details"]["error_type"] == "AUTHENTICATION_ERROR"
    
    def test_test_account_network_error(self, test_client):
        """Test account testing with network error."""
        with patch('app.api.routes.test_accounts.BinanceClient') as mock_client_class:
            mock_client_class.side_effect = BinanceNetworkError(
                "Network error",
                details={"endpoint": "test"}
            )
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Connection Failed" in data["connection_status"]
            assert "Network error" in data["error"]
            assert data["details"]["error_type"] == "NETWORK_ERROR"
    
    def test_test_account_missing_balance(self, test_client, mock_binance_client):
        """Test account testing when balance retrieval fails."""
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            # Mock successful account info
            mock_rest.futures_account.return_value = {
                "totalWalletBalance": "1000.0",
                "totalUnrealizedProfit": "0.0",
                "availableBalance": "1000.0",
                "marginBalance": "1000.0",
                "canTrade": True,
                "canDeposit": False,
                "canWithdraw": False,
            }
            
            # Mock balance retrieval failure
            mock_binance_client.futures_account_balance.side_effect = Exception("Balance not found")
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["balance"] is None  # Balance failed but test still succeeds
            assert data["account_info"]["total_wallet_balance"] == 1000.0


class TestTestExistingAccountEndpoint:
    """Tests for POST /api/test-account/{account_id} endpoint."""
    
    def test_test_existing_account_success(self, test_client, mock_client_manager):
        """Test successful testing of existing account."""
        from app.services.account_service import AccountService
        
        # Mock account config that AccountService.get_account should return
        mock_account_config = BinanceAccountConfig(
            account_id="test_account",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
            name="Test Account"
        )
        
        # Mock AccountService - patch where it's imported (inside the function)
        with patch('app.services.account_service.AccountService') as mock_account_service_class:
            mock_account_service = MagicMock(spec=AccountService)
            mock_account_service_class.return_value = mock_account_service
            mock_account_service.get_account.return_value = mock_account_config
            
            # Mock BinanceClient
            with patch('app.api.routes.test_accounts.BinanceClient') as mock_client_class:
                mock_client = MagicMock(spec=BinanceClient)
                mock_client_class.return_value = mock_client
                
                mock_rest = MagicMock()
                mock_client._ensure.return_value = mock_rest
                
                # Mock successful account info
                mock_rest.futures_account.return_value = {
                    "totalWalletBalance": "2000.0",
                    "totalUnrealizedProfit": "100.0",
                    "availableBalance": "1900.0",
                    "marginBalance": "2100.0",
                    "canTrade": True,
                    "canDeposit": True,
                    "canWithdraw": True,
                }
                
                mock_client.futures_account_balance.return_value = 2000.0
                
                response = test_client.post("/api/test-account/test_account")
                
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["account_name"] == "Test Account"
                assert data["testnet"] is True
                assert data["connection_status"] == "✅ Connected"
                assert data["authentication_status"] == "✅ Authenticated"
                assert data["account_info"]["total_wallet_balance"] == 2000.0
                assert data["balance"] == 2000.0
                assert "FUTURES_TRADING" in data["permissions"]
    
    def test_test_existing_account_not_found(self, test_client, mock_client_manager):
        """Test testing non-existent account."""
        from app.services.account_service import AccountService
        
        # Mock AccountService to return None (account not found)
        with patch('app.services.account_service.AccountService') as mock_account_service_class:
            mock_account_service = MagicMock(spec=AccountService)
            mock_account_service_class.return_value = mock_account_service
            mock_account_service.get_account.return_value = None
            
            response = test_client.post("/api/test-account/nonexistent")
            
            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()
            assert "nonexistent" in data["detail"]
    
    @pytest.mark.slow
    def test_test_existing_account_authentication_failed(self, test_client, mock_client_manager):
        """Test existing account with invalid credentials."""
        from app.services.account_service import AccountService
        
        # Mock account config with invalid credentials
        mock_account_config = BinanceAccountConfig(
            account_id="test_account",
            api_key="invalid_key",
            api_secret="invalid_secret",
            testnet=True
        )
        
        # Mock AccountService to return the account
        with patch('app.services.account_service.AccountService') as mock_account_service_class:
            mock_account_service = MagicMock(spec=AccountService)
            mock_account_service_class.return_value = mock_account_service
            mock_account_service.get_account.return_value = mock_account_config
            
            with patch('app.api.routes.test_accounts.BinanceClient') as mock_client_class:
                mock_client = MagicMock(spec=BinanceClient)
                mock_client_class.return_value = mock_client
                
                mock_rest = MagicMock()
                mock_client._ensure.return_value = mock_rest
                
                # Mock authentication error
                mock_rest.futures_account.side_effect = Exception("Invalid API-key")
                
                response = test_client.post("/api/test-account/test_account")
                
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False
                assert "Authentication Failed" in data["authentication_status"]
                assert "Invalid API credentials" in data["error"]
    
    def test_test_existing_account_default(self, test_client, mock_client_manager):
        """Test testing default account."""
        from app.services.account_service import AccountService
        
        # Mock account config for default account
        mock_account_config = BinanceAccountConfig(
            account_id="default",
            api_key="default_key",
            api_secret="default_secret",
            testnet=True,
            name="Default Account"
        )
        
        # Mock AccountService to return the account
        with patch('app.services.account_service.AccountService') as mock_account_service_class:
            mock_account_service = MagicMock(spec=AccountService)
            mock_account_service_class.return_value = mock_account_service
            mock_account_service.get_account.return_value = mock_account_config
            
            with patch('app.api.routes.test_accounts.BinanceClient') as mock_client_class:
                mock_client = MagicMock(spec=BinanceClient)
                mock_client_class.return_value = mock_client
                
                mock_rest = MagicMock()
                mock_client._ensure.return_value = mock_rest
                
                mock_rest.futures_account.return_value = {
                    "totalWalletBalance": "5000.0",
                    "totalUnrealizedProfit": "0.0",
                    "availableBalance": "5000.0",
                    "marginBalance": "5000.0",
                    "canTrade": True,
                    "canDeposit": True,
                    "canWithdraw": True,
                }
                
                mock_client.futures_account_balance.return_value = 5000.0
                
                response = test_client.post("/api/test-account/default")
                
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["account_name"] == "Default Account"
                assert data["account_info"]["total_wallet_balance"] == 5000.0


class TestQuickTestEndpoint:
    """Tests for GET /api/test-account/quick endpoint."""
    
    def test_quick_test_success(self, test_client, mock_binance_client):
        """Test quick test endpoint success."""
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            mock_rest.futures_account.return_value = {
                "canTrade": True
            }
            
            response = test_client.get(
                "/api/test-account/quick",
                params={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": "true"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["testnet"] is True
            assert data["can_trade"] is True
            assert "valid" in data["message"].lower()
    
    def test_quick_test_failure(self, test_client):
        """Test quick test endpoint failure."""
        with patch('app.api.routes.test_accounts.BinanceClient') as mock_client_class:
            mock_client_class.side_effect = Exception("Invalid credentials")
            
            response = test_client.get(
                "/api/test-account/quick",
                params={
                    "api_key": "invalid_key",
                    "api_secret": "invalid_secret",
                    "testnet": "true"
                }
            )
            
            assert response.status_code == 400
            data = response.json()
            assert "failed" in data["detail"].lower()


class TestAccountPermissions:
    """Tests for account permissions in test results."""
    
    def test_permissions_all_enabled(self, test_client, mock_binance_client):
        """Test account with all permissions enabled."""
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            mock_rest.futures_account.return_value = {
                "totalWalletBalance": "1000.0",
                "totalUnrealizedProfit": "0.0",
                "availableBalance": "1000.0",
                "marginBalance": "1000.0",
                "canTrade": True,
                "canDeposit": True,
                "canWithdraw": True,
            }
            
            mock_binance_client.futures_account_balance.return_value = 1000.0
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "FUTURES_TRADING" in data["permissions"]
            assert "DEPOSIT" in data["permissions"]
            assert "WITHDRAW" in data["permissions"]
    
    def test_permissions_none_enabled(self, test_client, mock_binance_client):
        """Test account with no permissions enabled."""
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            mock_rest.futures_account.return_value = {
                "totalWalletBalance": "1000.0",
                "totalUnrealizedProfit": "0.0",
                "availableBalance": "1000.0",
                "marginBalance": "1000.0",
                "canTrade": False,
                "canDeposit": False,
                "canWithdraw": False,
            }
            
            mock_binance_client.futures_account_balance.return_value = 1000.0
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["permissions"] == ["BASIC_ACCESS"]


class TestAccountInfoFormatting:
    """Tests for account info formatting in responses."""
    
    def test_account_info_numeric_values(self, test_client, mock_binance_client):
        """Test that account info values are properly converted to floats."""
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            # Binance returns strings for numeric values
            mock_rest.futures_account.return_value = {
                "totalWalletBalance": "1234.56",
                "totalUnrealizedProfit": "-12.34",
                "availableBalance": "1222.22",
                "marginBalance": "1234.56",
                "canTrade": True,
                "canDeposit": True,
                "canWithdraw": True,
            }
            
            mock_binance_client.futures_account_balance.return_value = 1234.56
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data["account_info"]["total_wallet_balance"], float)
            assert data["account_info"]["total_wallet_balance"] == 1234.56
            assert isinstance(data["account_info"]["total_unrealized_profit"], float)
            assert data["account_info"]["total_unrealized_profit"] == -12.34


class TestErrorHandling:
    """Tests for error handling in test endpoints."""
    
    def test_binance_api_error(self, test_client):
        """Test handling of BinanceAPIError."""
        with patch('app.api.routes.test_accounts.BinanceClient') as mock_client_class:
            mock_client_class.side_effect = BinanceAPIError(
                "API error",
                status_code=400,
                error_code=-1000
            )
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert data["details"]["error_type"] == "API_ERROR"
    
    def test_binance_authentication_error(self, test_client):
        """Test handling of BinanceAuthenticationError."""
        with patch('app.api.routes.test_accounts.BinanceClient') as mock_client_class:
            mock_client_class.side_effect = BinanceAuthenticationError("Auth error")
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Authentication Failed" in data["authentication_status"]
            assert data["details"]["error_type"] == "AUTHENTICATION_ERROR"
    
    def test_unexpected_error(self, test_client):
        """Test handling of unexpected errors."""
        with patch('app.api.routes.test_accounts.BinanceClient') as mock_client_class:
            mock_client_class.side_effect = ValueError("Unexpected error")
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert data["details"]["error_type"] == "UNKNOWN_ERROR"


class TestProductionVsTestnet:
    """Tests for testnet vs production account testing."""
    
    def test_testnet_account(self, test_client, mock_binance_client):
        """Test testnet account."""
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            mock_rest.futures_account.return_value = {
                "totalWalletBalance": "1000.0",
                "totalUnrealizedProfit": "0.0",
                "availableBalance": "1000.0",
                "marginBalance": "1000.0",
                "canTrade": True,
                "canDeposit": True,
                "canWithdraw": True,
            }
            
            mock_binance_client.futures_account_balance.return_value = 1000.0
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["testnet"] is True
    
    def test_production_account(self, test_client, mock_binance_client):
        """Test production account."""
        with patch('app.api.routes.test_accounts.BinanceClient', return_value=mock_binance_client):
            mock_rest = MagicMock()
            mock_binance_client._ensure.return_value = mock_rest
            
            mock_rest.futures_account.return_value = {
                "totalWalletBalance": "1000.0",
                "totalUnrealizedProfit": "0.0",
                "availableBalance": "1000.0",
                "marginBalance": "1000.0",
                "canTrade": True,
                "canDeposit": True,
                "canWithdraw": True,
            }
            
            mock_binance_client.futures_account_balance.return_value = 1000.0
            
            response = test_client.post(
                "/api/test-account",
                json={
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": False
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["testnet"] is False

