"""
Performance test script for async database operations.
Compares sync vs async database query performance.
"""
import asyncio
import time
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import (
    init_database,
    init_database_async,
    get_db_session_dependency,
    get_async_db,
    get_engine,
    get_async_engine,
)
from app.services.database_service import DatabaseService
from app.models.db_models import User
from sqlalchemy import select, text
from uuid import uuid4


async def test_sync_query_performance():
    """Test sync query performance (blocking)."""
    print("\n" + "=" * 60)
    print("SYNC DATABASE QUERY PERFORMANCE TEST")
    print("=" * 60)
    
    # Initialize sync database
    success, error = init_database(max_retries=3)
    if not success:
        print(f"❌ Sync database initialization failed: {error}")
        return None
    
    engine = get_engine()
    
    # Run sync queries sequentially
    start_time = time.time()
    query_times = []
    
    for i in range(10):
        query_start = time.time()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        query_time = time.time() - query_start
        query_times.append(query_time)
    
    total_time = time.time() - start_time
    avg_time = sum(query_times) / len(query_times)
    
    print(f"✅ Completed 10 sync queries")
    print(f"   Total time: {total_time:.4f}s")
    print(f"   Average per query: {avg_time:.4f}s")
    print(f"   Queries per second: {10/total_time:.2f}")
    
    return {
        "total_time": total_time,
        "avg_time": avg_time,
        "queries_per_second": 10/total_time,
        "query_times": query_times
    }


async def test_async_query_performance():
    """Test async query performance (non-blocking)."""
    print("\n" + "=" * 60)
    print("ASYNC DATABASE QUERY PERFORMANCE TEST")
    print("=" * 60)
    
    # Initialize async database
    success, error = await init_database_async(max_retries=3)
    if not success:
        print(f"❌ Async database initialization failed: {error}")
        return None
    
    engine = await get_async_engine()
    
    # Run async queries concurrently
    async def run_query(query_id: int):
        query_start = time.time()
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            await result.fetchone()
        query_time = time.time() - query_start
        return query_time
    
    start_time = time.time()
    query_times = await asyncio.gather(*[run_query(i) for i in range(10)])
    total_time = time.time() - start_time
    avg_time = sum(query_times) / len(query_times)
    
    print(f"✅ Completed 10 async queries (concurrent)")
    print(f"   Total time: {total_time:.4f}s")
    print(f"   Average per query: {avg_time:.4f}s")
    print(f"   Queries per second: {10/total_time:.2f}")
    
    return {
        "total_time": total_time,
        "avg_time": avg_time,
        "queries_per_second": 10/total_time,
        "query_times": query_times
    }


async def test_concurrent_requests_simulation():
    """Simulate concurrent requests to compare sync vs async."""
    print("\n" + "=" * 60)
    print("CONCURRENT REQUESTS SIMULATION")
    print("=" * 60)
    
    # Initialize both databases
    sync_success, _ = init_database(max_retries=3)
    async_success, _ = await init_database_async(max_retries=3)
    
    if not sync_success or not async_success:
        print("❌ Database initialization failed")
        return
    
    sync_engine = get_engine()
    async_engine = await get_async_engine()
    
    num_requests = 20
    
    # Simulate sync requests (sequential)
    print(f"\n📊 Simulating {num_requests} sync requests (sequential)...")
    sync_start = time.time()
    for i in range(num_requests):
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    sync_total = time.time() - sync_start
    sync_qps = num_requests / sync_total
    
    # Simulate async requests (concurrent)
    print(f"\n📊 Simulating {num_requests} async requests (concurrent)...")
    async def async_request():
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    
    async_start = time.time()
    await asyncio.gather(*[async_request() for _ in range(num_requests)])
    async_total = time.time() - async_start
    async_qps = num_requests / async_total
    
    # Compare results
    print("\n" + "=" * 60)
    print("PERFORMANCE COMPARISON")
    print("=" * 60)
    print(f"Sync (sequential):")
    print(f"  Total time: {sync_total:.4f}s")
    print(f"  Queries/sec: {sync_qps:.2f}")
    print(f"\nAsync (concurrent):")
    print(f"  Total time: {async_total:.4f}s")
    print(f"  Queries/sec: {async_qps:.2f}")
    
    improvement = ((sync_total - async_total) / sync_total) * 100
    speedup = sync_total / async_total if async_total > 0 else 0
    
    print(f"\n📈 Performance Improvement:")
    print(f"  {improvement:.1f}% faster")
    print(f"  {speedup:.2f}x speedup")
    
    if speedup > 1.5:
        print(f"\n✅ Significant performance improvement with async!")
    elif speedup > 1.1:
        print(f"\n✅ Moderate performance improvement with async")
    else:
        print(f"\n⚠️ Minimal performance difference (may need more concurrent load)")


async def test_database_service_performance():
    """Test DatabaseService async methods performance."""
    print("\n" + "=" * 60)
    print("DATABASE SERVICE ASYNC METHODS TEST")
    print("=" * 60)
    
    success, error = await init_database_async(max_retries=3)
    if not success:
        print(f"❌ Async database initialization failed: {error}")
        return
    
    async for db in get_async_db():
        db_service = DatabaseService(db)
        
        # Test async_get_user_by_id performance
        test_user_id = uuid4()
        
        start_time = time.time()
        for _ in range(10):
            user = await db_service.async_get_user_by_id(test_user_id)
        total_time = time.time() - start_time
        
        print(f"✅ async_get_user_by_id() - 10 queries in {total_time:.4f}s")
        print(f"   Average: {total_time/10:.4f}s per query")
        
        # Test async_get_user_accounts performance
        start_time = time.time()
        for _ in range(10):
            accounts = await db_service.async_get_user_accounts(test_user_id)
        total_time = time.time() - start_time
        
        print(f"✅ async_get_user_accounts() - 10 queries in {total_time:.4f}s")
        print(f"   Average: {total_time/10:.4f}s per query")
        
        break


async def main():
    """Run all performance tests."""
    print("\n" + "=" * 70)
    print("ASYNC DATABASE MIGRATION - PERFORMANCE TESTS")
    print("=" * 70)
    
    try:
        # Test 1: Sync query performance
        sync_results = await test_sync_query_performance()
        
        # Test 2: Async query performance
        async_results = await test_async_query_performance()
        
        # Test 3: Concurrent requests simulation
        await test_concurrent_requests_simulation()
        
        # Test 4: DatabaseService async methods
        await test_database_service_performance()
        
        # Summary
        if sync_results and async_results:
            print("\n" + "=" * 70)
            print("SUMMARY")
            print("=" * 70)
            print(f"Sync average query time: {sync_results['avg_time']:.4f}s")
            print(f"Async average query time: {async_results['avg_time']:.4f}s")
            
            if async_results['avg_time'] < sync_results['avg_time']:
                improvement = ((sync_results['avg_time'] - async_results['avg_time']) / sync_results['avg_time']) * 100
                print(f"\n✅ Async is {improvement:.1f}% faster per query")
            else:
                print(f"\n⚠️ Sync is faster (may be due to connection overhead)")
            
            print(f"\nSync throughput: {sync_results['queries_per_second']:.2f} queries/sec")
            print(f"Async throughput: {async_results['queries_per_second']:.2f} queries/sec")
        
        print("\n" + "=" * 70)
        print("✅ All performance tests completed!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

