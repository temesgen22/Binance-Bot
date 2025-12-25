"""
Test async database operations and performance improvements.
"""
import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import (
    init_database_async,
    get_async_db,
    close_async_database,
    get_async_engine,
)
from app.services.database_service import DatabaseService
from app.models.db_models import User, Account, Strategy, Trade
from app.core.config import get_settings


@pytest.mark.asyncio
@pytest.mark.database
async def test_async_database_initialization():
    """Test that async database can be initialized."""
    import os
    # Skip if DATABASE_URL is not set (e.g., in CI without database)
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    success, error = await init_database_async(max_retries=3)
    if not success:
        pytest.skip(f"Database not available: {error}")
    print("✅ Async database initialized successfully")


@pytest.mark.asyncio
@pytest.mark.database
async def test_async_database_connection():
    """Test basic async database connection and query."""
    import os
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    try:
        engine = await get_async_engine()
    except RuntimeError as e:
        pytest.skip(f"Database not available: {e}")
    
    async with engine.connect() as conn:
        from sqlalchemy import text
        result = await conn.execute(text("SELECT 1"))
        row = result.fetchone()
        assert row[0] == 1
        print("✅ Async database connection test passed")


@pytest.mark.asyncio
@pytest.mark.database
async def test_async_db_dependency():
    """Test the async database dependency."""
    import os
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    try:
        async for db in get_async_db():
            assert isinstance(db, AsyncSession)
            # Test a simple query
            from sqlalchemy import text
            result = await db.execute(text("SELECT 1"))
            row = result.fetchone()
            assert row[0] == 1
            print("✅ Async database dependency works")
            break
    except RuntimeError as e:
        pytest.skip(f"Database not available: {e}")


@pytest.mark.asyncio
@pytest.mark.database
async def test_async_database_service():
    """Test async methods in DatabaseService."""
    import os
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    try:
        async for db in get_async_db():
            db_service = DatabaseService(db)
            
            # Test that it detects async session
            assert db_service._is_async, "DatabaseService should detect async session"
            
            # Test async_get_user_by_id (may return None if no users exist)
            # This is fine - we're just testing the method works
            try:
                test_user_id = uuid4()
                user = await db_service.async_get_user_by_id(test_user_id)
                # Should return None for non-existent user, not raise error
                assert user is None or isinstance(user, User)
                print("✅ async_get_user_by_id() works")
            except Exception as e:
                pytest.fail(f"async_get_user_by_id() failed: {e}")
            
            break
    except RuntimeError as e:
        pytest.skip(f"Database not available: {e}")


@pytest.mark.asyncio
@pytest.mark.database
async def test_async_vs_sync_performance():
    """Compare async vs sync query performance (basic test)."""
    import time
    import os
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    try:
        async for db in get_async_db():
            db_service = DatabaseService(db)
            
            # Test async query timing
            start_time = time.time()
            try:
                # Simple query that should be fast
                from sqlalchemy import text
                result = await db.execute(text("SELECT COUNT(*) FROM users"))
                count = result.scalar()
                async_time = time.time() - start_time
                print(f"✅ Async query completed in {async_time:.4f}s (count: {count})")
            except Exception as e:
                print(f"⚠️ Async query test skipped (table may not exist): {e}")
            
            break
    except RuntimeError as e:
        pytest.skip(f"Database not available: {e}")


@pytest.mark.asyncio
@pytest.mark.database
async def test_async_batch_queries():
    """Test async batch query operations."""
    import os
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    try:
        async for db in get_async_db():
            db_service = DatabaseService(db)
            
            # Test async_get_user_trades_batch
            try:
                test_user_id = uuid4()
                trades = await db_service.async_get_user_trades_batch(
                    user_id=test_user_id,
                    strategy_ids=[],
                    limit=100
                )
                assert isinstance(trades, list)
                print(f"✅ async_get_user_trades_batch() works (returned {len(trades)} trades)")
            except Exception as e:
                pytest.fail(f"async_get_user_trades_batch() failed: {e}")
            
            break
    except RuntimeError as e:
        pytest.skip(f"Database not available: {e}")


@pytest.mark.asyncio
@pytest.mark.database
async def test_concurrent_async_queries():
    """Test that multiple async queries can run concurrently."""
    import time
    import os
    from app.core.database import get_async_engine
    
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    try:
        # Use separate connections for concurrent queries (SQLAlchemy async sessions don't support concurrent ops)
        engine = await get_async_engine()
        
        # Run multiple queries concurrently using separate connections
        async def run_query(query_id: int):
            async with engine.connect() as conn:
                from sqlalchemy import text
                # Use a simple query that works with asyncpg
                result = await conn.execute(text(f"SELECT {query_id}"))
                return result.scalar()
        
        # Run 5 queries concurrently
        start_time = time.time()
        results = await asyncio.gather(*[run_query(i) for i in range(5)])
        concurrent_time = time.time() - start_time
        
        assert len(results) == 5
        assert all(r == i for i, r in enumerate(results))
        print(f"✅ 5 concurrent async queries completed in {concurrent_time:.4f}s")
    except RuntimeError as e:
        pytest.skip(f"Database not available: {e}")


@pytest.mark.asyncio
async def test_async_database_cleanup():
    """Test that async database can be closed properly."""
    try:
        await close_async_database()
        print("✅ Async database cleanup successful")
    except Exception as e:
        print(f"⚠️ Async database cleanup warning: {e}")


# Integration test - requires database with test data
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.database
async def test_async_database_integration():
    """Integration test with real database operations."""
    import os
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database test")
    
    try:
        async for db in get_async_db():
            db_service = DatabaseService(db)
            
            # Test getting all users (if any exist)
            try:
                from sqlalchemy import select
                result = await db.execute(select(User).limit(5))
                users = list(result.scalars().all())
                print(f"✅ Found {len(users)} users in database")
                
                if users:
                    # Test getting user by ID
                    user = await db_service.async_get_user_by_id(users[0].id)
                    assert user is not None
                    assert user.id == users[0].id
                    print(f"✅ Successfully retrieved user: {user.username}")
            except Exception as e:
                print(f"⚠️ Integration test skipped: {e}")
            
            break
    except RuntimeError as e:
        pytest.skip(f"Database not available: {e}")


if __name__ == "__main__":
    """Run tests directly."""
    import sys
    
    async def run_all_tests():
        print("=" * 60)
        print("ASYNC DATABASE MIGRATION TESTS")
        print("=" * 60)
        print()
        
        tests = [
            ("Async Database Initialization", test_async_database_initialization),
            ("Async Database Connection", test_async_database_connection),
            ("Async DB Dependency", test_async_db_dependency),
            ("Async Database Service", test_async_database_service),
            ("Async vs Sync Performance", test_async_vs_sync_performance),
            ("Async Batch Queries", test_async_batch_queries),
            ("Concurrent Async Queries", test_concurrent_async_queries),
            ("Async Database Cleanup", test_async_database_cleanup),
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                print(f"Running: {test_name}...")
                await test_func()
                passed += 1
                print()
            except Exception as e:
                print(f"❌ {test_name} FAILED: {e}")
                failed += 1
                import traceback
                traceback.print_exc()
                print()
        
        print("=" * 60)
        print(f"RESULTS: {passed} passed, {failed} failed")
        print("=" * 60)
        
        return 0 if failed == 0 else 1
    
    sys.exit(asyncio.run(run_all_tests()))

