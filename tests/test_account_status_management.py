"""Tests for account status management (activate/deactivate) functionality."""

from __future__ import annotations

import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.db_models import User, Account
from app.api.deps import get_current_user_async, get_account_service_async
from app.services.account_service import AccountService
from app.services.database_service import DatabaseService
from app.core.config import BinanceAccountConfig


@pytest.fixture
def test_user():
    """Create a test user."""
    return User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed",
        is_active=True
    )


@pytest.fixture
def test_account(test_user):
    """Create a test account."""
    return Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="test_account_1",
        api_key_encrypted="encrypted_key",
        api_secret_encrypted="encrypted_secret",
        name="Test Account",
        exchange_platform="binance",
        testnet=True,
        is_active=True,
        is_default=False
    )


@pytest.fixture
def test_account_inactive(test_user):
    """Create an inactive test account."""
    return Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="test_account_2",
        api_key_encrypted="encrypted_key",
        api_secret_encrypted="encrypted_secret",
        name="Inactive Account",
        exchange_platform="binance",
        testnet=True,
        is_active=False,  # Inactive
        is_default=False
    )


@pytest.fixture
def mock_async_db():
    """Create a mock async database session."""
    return MagicMock(spec=AsyncSession)


@pytest.fixture
def mock_db_service(mock_async_db):
    """Create a mock database service."""
    service = MagicMock(spec=DatabaseService)
    service.db = mock_async_db
    service._is_async = True
    return service


@pytest.fixture
def mock_account_service(mock_db_service, test_user):
    """Create a mock account service."""
    service = MagicMock(spec=AccountService)
    service.db_service = mock_db_service
    service._is_async = True
    
    # Mock async methods
    service.async_update_account = AsyncMock()
    service.async_delete_account = AsyncMock()
    
    return service


@pytest.fixture
def authenticated_client(test_user, mock_account_service):
    """Create an authenticated test client."""
    app.dependency_overrides[get_current_user_async] = lambda: test_user
    app.dependency_overrides[get_account_service_async] = lambda: mock_account_service
    
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user_async, None)
        app.dependency_overrides.pop(get_account_service_async, None)


class TestListAccountsWithInactive:
    """Tests for listing accounts including inactive ones."""
    
    @pytest.mark.asyncio
    async def test_list_accounts_default_only_active(self, authenticated_client, mock_account_service, 
                                                     test_user, test_account, test_account_inactive):
        """Test that default list endpoint only returns active accounts."""
        from sqlalchemy import select
        
        # Mock async_get_user_accounts to return only active account
        async def mock_get_user_accounts(user_id):
            return [test_account]
        
        mock_account_service.db_service.async_get_user_accounts = AsyncMock(side_effect=mock_get_user_accounts)
        
        response = authenticated_client.get("/api/accounts/list")
        
        assert response.status_code == 200
        accounts = response.json()
        assert len(accounts) == 1
        assert accounts[0]["account_id"] == "test_account_1"
        assert accounts[0]["is_active"] is True
    
    @pytest.mark.asyncio
    async def test_list_accounts_include_inactive(self, authenticated_client, mock_account_service,
                                                   test_user, test_account, test_account_inactive):
        """Test listing accounts with include_inactive=True returns all accounts."""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession
        
        # Mock the database query to return both accounts
        async def mock_execute(query):
            result = MagicMock()
            result.scalars.return_value.all.return_value = [test_account, test_account_inactive]
            return result
        
        mock_async_db = MagicMock(spec=AsyncSession)
        mock_async_db.execute = AsyncMock(side_effect=mock_execute)
        mock_account_service.db_service.db = mock_async_db
        
        response = authenticated_client.get("/api/accounts/list?include_inactive=true")
        
        assert response.status_code == 200
        accounts = response.json()
        assert len(accounts) == 2
        
        # Check that both active and inactive accounts are present
        account_ids = [acc["account_id"] for acc in accounts]
        assert "test_account_1" in account_ids
        assert "test_account_2" in account_ids
        
        # Check status
        active_account = next(acc for acc in accounts if acc["account_id"] == "test_account_1")
        inactive_account = next(acc for acc in accounts if acc["account_id"] == "test_account_2")
        assert active_account["is_active"] is True
        assert inactive_account["is_active"] is False


class TestGetAccount:
    """Tests for getting a single account."""
    
    @pytest.mark.asyncio
    async def test_get_active_account(self, authenticated_client, mock_account_service,
                                      test_user, test_account):
        """Test getting an active account."""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession
        
        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = test_account
            return result
        
        mock_async_db = MagicMock(spec=AsyncSession)
        mock_async_db.execute = AsyncMock(side_effect=mock_execute)
        mock_account_service.db_service.db = mock_async_db
        
        response = authenticated_client.get("/api/accounts/test_account_1")
        
        assert response.status_code == 200
        account = response.json()
        assert account["account_id"] == "test_account_1"
        assert account["is_active"] is True
    
    @pytest.mark.asyncio
    async def test_get_inactive_account(self, authenticated_client, mock_account_service,
                                        test_user, test_account_inactive):
        """Test getting an inactive account (should work with include_inactive=True by default)."""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession
        
        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = test_account_inactive
            return result
        
        mock_async_db = MagicMock(spec=AsyncSession)
        mock_async_db.execute = AsyncMock(side_effect=mock_execute)
        mock_account_service.db_service.db = mock_async_db
        
        response = authenticated_client.get("/api/accounts/test_account_2")
        
        assert response.status_code == 200
        account = response.json()
        assert account["account_id"] == "test_account_2"
        assert account["is_active"] is False


class TestActivateAccount:
    """Tests for activating accounts."""
    
    @pytest.mark.asyncio
    async def test_activate_inactive_account(self, authenticated_client, mock_account_service,
                                             test_user, test_account_inactive):
        """Test activating an inactive account."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.sql import Select
        
        # Mock finding the inactive account
        async def mock_execute(query):
            result = MagicMock()
            if isinstance(query, Select):
                result.scalar_one_or_none.return_value = test_account_inactive
            else:  # update statement
                result = MagicMock()
            return result
        
        mock_async_db = MagicMock(spec=AsyncSession)
        mock_async_db.execute = AsyncMock(side_effect=mock_execute)
        mock_async_db.commit = AsyncMock()
        mock_async_db.refresh = AsyncMock()
        mock_account_service.db_service.db = mock_async_db
        
        # Mock async_update_account to return updated account
        # Create a copy without SQLAlchemy state
        updated_account = Account(
            id=test_account_inactive.id,
            user_id=test_account_inactive.user_id,
            account_id=test_account_inactive.account_id,
            api_key_encrypted=test_account_inactive.api_key_encrypted,
            api_secret_encrypted=test_account_inactive.api_secret_encrypted,
            name=test_account_inactive.name,
            exchange_platform=test_account_inactive.exchange_platform,
            testnet=test_account_inactive.testnet,
            is_active=True,  # Updated
            is_default=test_account_inactive.is_default
        )
        
        async def mock_update_account(user_id, account_id, **updates):
            return updated_account
        
        mock_account_service.async_update_account = AsyncMock(side_effect=mock_update_account)
        
        # Mock the endpoint's direct query to return updated account
        # The endpoint now uses a direct query instead of async_get_account_by_id
        async def mock_execute_endpoint(query):
            result = MagicMock()
            if isinstance(query, Select):
                result.scalar_one_or_none.return_value = updated_account
            return result
        
        mock_account_service.db_service.db.execute = AsyncMock(side_effect=mock_execute_endpoint)
        
        response = authenticated_client.put(
            "/api/accounts/test_account_2",
            json={"is_active": True}
        )
        
        assert response.status_code == 200
        account = response.json()
        assert account["account_id"] == "test_account_2"
        assert account["is_active"] is True
        
        # Verify update was called
        mock_account_service.async_update_account.assert_called_once()
        call_args = mock_account_service.async_update_account.call_args
        assert call_args[0][1] == "test_account_2"  # account_id
        assert call_args[1]["is_active"] is True


class TestDeactivateAccount:
    """Tests for deactivating accounts."""
    
    @pytest.mark.asyncio
    async def test_deactivate_active_account(self, authenticated_client, mock_account_service,
                                             test_user, test_account):
        """Test deactivating an active account."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.sql import Select
        
        # Mock finding the active account
        async def mock_execute(query):
            result = MagicMock()
            if isinstance(query, Select):
                result.scalar_one_or_none.return_value = test_account
            else:  # update statement
                result = MagicMock()
            return result
        
        mock_async_db = MagicMock(spec=AsyncSession)
        mock_async_db.execute = AsyncMock(side_effect=mock_execute)
        mock_async_db.commit = AsyncMock()
        mock_async_db.refresh = AsyncMock()
        mock_account_service.db_service.db = mock_async_db
        
        # Mock async_update_account to return deactivated account
        deactivated_account = Account(
            id=test_account.id,
            user_id=test_account.user_id,
            account_id=test_account.account_id,
            api_key_encrypted=test_account.api_key_encrypted,
            api_secret_encrypted=test_account.api_secret_encrypted,
            name=test_account.name,
            exchange_platform=test_account.exchange_platform,
            testnet=test_account.testnet,
            is_active=False,  # Deactivated
            is_default=test_account.is_default
        )
        
        async def mock_update_account(user_id, account_id, **updates):
            return deactivated_account
        
        mock_account_service.async_update_account = AsyncMock(side_effect=mock_update_account)
        
        # After update, the endpoint tries to get the account again
        # Since async_get_account_by_id filters by is_active=True, it won't find deactivated account
        # But we can still verify the update was called correctly
        # The endpoint might return 404 because async_get_account_by_id returns None for inactive accounts
        
        # Mock the endpoint's direct query to return deactivated account
        # The endpoint now uses a direct query instead of async_get_account_by_id
        async def mock_execute_endpoint(query):
            result = MagicMock()
            if isinstance(query, Select):
                result.scalar_one_or_none.return_value = deactivated_account
            return result
        
        mock_account_service.db_service.db.execute = AsyncMock(side_effect=mock_execute_endpoint)
        
        response = authenticated_client.put(
            "/api/accounts/test_account_1",
            json={"is_active": False}
        )
        
        # The update should succeed
        assert response.status_code == 200
        account = response.json()
        assert account["account_id"] == "test_account_1"
        assert account["is_active"] is False
        
        # Verify update was called
        mock_account_service.async_update_account.assert_called_once()
        call_args = mock_account_service.async_update_account.call_args
        assert call_args[0][1] == "test_account_1"  # account_id
        assert call_args[1]["is_active"] is False


class TestUpdateAccountStatus:
    """Tests for updating account status along with other fields."""
    
    @pytest.mark.asyncio
    async def test_update_account_with_status_change(self, authenticated_client, mock_account_service,
                                                     test_user, test_account_inactive):
        """Test updating account name and status together."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.sql import Select
        
        async def mock_execute(query):
            result = MagicMock()
            if isinstance(query, Select):
                result.scalar_one_or_none.return_value = test_account_inactive
            else:
                result = MagicMock()
            return result
        
        mock_async_db = MagicMock(spec=AsyncSession)
        mock_async_db.execute = AsyncMock(side_effect=mock_execute)
        mock_async_db.commit = AsyncMock()
        mock_async_db.refresh = AsyncMock()
        mock_account_service.db_service.db = mock_async_db
        
        updated_account = Account(
            id=test_account_inactive.id,
            user_id=test_account_inactive.user_id,
            account_id=test_account_inactive.account_id,
            api_key_encrypted=test_account_inactive.api_key_encrypted,
            api_secret_encrypted=test_account_inactive.api_secret_encrypted,
            name="Updated Name",  # Updated
            exchange_platform=test_account_inactive.exchange_platform,
            testnet=test_account_inactive.testnet,
            is_active=True,  # Updated
            is_default=test_account_inactive.is_default
        )
        
        async def mock_update_account(user_id, account_id, **updates):
            return updated_account
        
        mock_account_service.async_update_account = AsyncMock(side_effect=mock_update_account)
        
        # Mock the endpoint's direct query to return updated account
        async def mock_execute_endpoint(query):
            result = MagicMock()
            if isinstance(query, Select):
                result.scalar_one_or_none.return_value = updated_account
            return result
        
        mock_account_service.db_service.db.execute = AsyncMock(side_effect=mock_execute_endpoint)
        
        response = authenticated_client.put(
            "/api/accounts/test_account_2",
            json={
                "name": "Updated Name",
                "is_active": True
            }
        )
        
        assert response.status_code == 200
        account = response.json()
        assert account["name"] == "Updated Name"
        assert account["is_active"] is True
        
        # Verify update was called with both fields
        call_args = mock_account_service.async_update_account.call_args
        assert "name" in call_args[1]
        assert call_args[1]["name"] == "Updated Name"
        assert call_args[1]["is_active"] is True


class TestAccountNotFound:
    """Tests for account not found scenarios."""
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_account(self, authenticated_client, mock_account_service,
                                              test_user):
        """Test updating a non-existent account."""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession
        
        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result
        
        mock_async_db = MagicMock(spec=AsyncSession)
        mock_async_db.execute = AsyncMock(side_effect=mock_execute)
        mock_account_service.db_service.db = mock_async_db
        
        async def mock_update_account(user_id, account_id, **updates):
            return None
        
        mock_account_service.async_update_account = AsyncMock(side_effect=mock_update_account)
        
        response = authenticated_client.put(
            "/api/accounts/nonexistent",
            json={"is_active": True}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestDatabaseServiceAsyncUpdateAccount:
    """Tests for async_update_account in DatabaseService."""
    
    @pytest.mark.asyncio
    async def test_async_update_account_finds_inactive_account(self, test_user, test_account_inactive):
        """Test that async_update_account can find and update inactive accounts."""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.services.database_service import DatabaseService
        
        mock_async_db = MagicMock(spec=AsyncSession)
        
        # Mock execute to return the inactive account
        from sqlalchemy.sql import Select
        
        async def mock_execute(query):
            result = MagicMock()
            # Check if it's a select query
            if isinstance(query, Select):
                result.scalar_one_or_none.return_value = test_account_inactive
            else:  # update statement
                result = MagicMock()
            return result
        
        mock_async_db.execute = AsyncMock(side_effect=mock_execute)
        mock_async_db.commit = AsyncMock()
        mock_async_db.refresh = AsyncMock()
        
        db_service = DatabaseService(mock_async_db)
        
        # Update the account to active
        updated_account = await db_service.async_update_account(
            test_user.id,
            "test_account_2",
            is_active=True
        )
        
        assert updated_account is not None
        assert updated_account.account_id == "test_account_2"
        assert updated_account.is_active is True
        
        # Verify the account was found (query was executed)
        assert mock_async_db.execute.call_count >= 1
        
        # Verify commit was called
        mock_async_db.commit.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

