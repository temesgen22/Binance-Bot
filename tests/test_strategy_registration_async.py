"""Test cases for strategy registration with async database dependencies.

This test specifically verifies the fix for the bug where get_database_service_async()
was called without await, causing 'coroutine' object has no attribute 'async_get_user_accounts' error.
"""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4
import asyncio

from app.api.deps import get_database_service_async
from app.services.database_service import DatabaseService
from sqlalchemy.ext.asyncio import AsyncSession


class TestStrategyRegistrationAsyncDependency:
    """Test strategy registration with async database dependencies.
    
    These tests verify the fix for the bug where get_database_service_async()
    was called without await, causing 'coroutine' object has no attribute 'async_get_user_accounts' error.
    """
    
    def test_await_get_database_service_async_returns_service(self):
        """Test that awaiting get_database_service_async returns a DatabaseService instance.
        
        This is the core fix - we must await get_database_service_async() to get
        a DatabaseService instance, not a coroutine object.
        
        Before the fix:
            db_service = get_database_service_async(db)  # Returns coroutine!
            accounts = await db_service.async_get_user_accounts(...)  # ERROR: 'coroutine' object has no attribute 'async_get_user_accounts'
        
        After the fix:
            db_service = await get_database_service_async(db)  # Returns DatabaseService
            accounts = await db_service.async_get_user_accounts(...)  # Works correctly!
        """
        # Create a mock async session
        mock_db = MagicMock(spec=AsyncSession)
        
        async def test():
            # This is the correct way - await the async function
            db_service = await get_database_service_async(mock_db)
            
            # Verify it's a DatabaseService instance (not a coroutine)
            assert isinstance(db_service, DatabaseService), \
                f"Expected DatabaseService instance, got {type(db_service)}"
            
            # Verify it has the async_get_user_accounts method
            assert hasattr(db_service, 'async_get_user_accounts'), \
                "DatabaseService should have async_get_user_accounts method"
            
            # Verify we can call async_get_user_accounts (it returns a coroutine)
            import inspect
            result = db_service.async_get_user_accounts(uuid4())
            assert inspect.iscoroutine(result), \
                "async_get_user_accounts should return a coroutine when called"
            
            return db_service
        
        # Run the test
        db_service = asyncio.run(test())
        assert db_service is not None
    
    def test_get_database_service_async_without_await_returns_coroutine(self):
        """Test that calling get_database_service_async without await returns a coroutine.
        
        This test demonstrates the bug - if we forget to await, we get a coroutine
        object instead of a DatabaseService instance.
        """
        # Create a mock async session
        mock_db = MagicMock(spec=AsyncSession)
        
        # Call without await - this returns a coroutine (the bug scenario)
        result = get_database_service_async(mock_db)
        
        # Verify it's a coroutine, not a DatabaseService
        import inspect
        assert inspect.iscoroutine(result), \
            "Calling get_database_service_async without await should return a coroutine"
        
        # Verify it does NOT have async_get_user_accounts attribute
        # (This is what causes the error: 'coroutine' object has no attribute 'async_get_user_accounts')
        assert not hasattr(result, 'async_get_user_accounts'), \
            "Coroutine should not have async_get_user_accounts attribute - this is the bug!"
    
    @pytest.mark.asyncio
    async def test_async_get_user_accounts_can_be_called_on_service(self):
        """Test that async_get_user_accounts can be called on the DatabaseService instance.
        
        This verifies that after awaiting get_database_service_async(), we get
        a service instance that has the async_get_user_accounts method.
        """
        # Create a mock async session
        mock_db = MagicMock(spec=AsyncSession)
        
        # Get the service (with await - correct way)
        db_service = await get_database_service_async(mock_db)
        
        # Verify we can call async_get_user_accounts
        user_id = uuid4()
        coroutine = db_service.async_get_user_accounts(user_id)
        
        # Verify it returns a coroutine (which can be awaited)
        import inspect
        assert inspect.iscoroutine(coroutine), \
            "async_get_user_accounts should return a coroutine"
        
        # The coroutine can be awaited (though we won't here since we don't have real data)
        # This test just verifies the method exists and is callable
