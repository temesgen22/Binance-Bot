"""
Test async route handlers with real HTTP requests.
"""
import asyncio
import httpx
import time
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_health_endpoint():
    """Test health endpoint (should be fast)."""
    print("\n" + "=" * 60)
    print("TESTING HEALTH ENDPOINT")
    print("=" * 60)
    
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10.0) as client:
        start_time = time.time()
        response = await client.get("/health/quick")
        elapsed = time.time() - start_time
        
        print(f"✅ Health endpoint response time: {elapsed:.4f}s")
        print(f"   Status: {response.status_code}")
        print(f"   Process time header: {response.headers.get('X-Process-Time', 'N/A')}")
        
        return elapsed


async def test_trades_endpoint_performance():
    """Test trades endpoint performance (requires authentication)."""
    print("\n" + "=" * 60)
    print("TESTING TRADES ENDPOINT (ASYNC)")
    print("=" * 60)
    
    # Note: This requires authentication
    # You'll need to get a token first or skip this test
    
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        # Try to get trades endpoint
        # This will fail without auth, but we can check response time
        try:
            start_time = time.time()
            response = await client.get("/trades/list")
            elapsed = time.time() - start_time
            
            print(f"Response time: {elapsed:.4f}s")
            print(f"Status: {response.status_code}")
            print(f"Process time header: {response.headers.get('X-Process-Time', 'N/A')}")
            
            if response.status_code == 401:
                print("⚠️ Authentication required - endpoint is working but needs token")
            elif response.status_code == 200:
                print("✅ Trades endpoint working!")
            
        except Exception as e:
            print(f"⚠️ Could not test trades endpoint: {e}")
            print("   (This is expected if server is not running or auth is required)")


async def test_concurrent_requests():
    """Test concurrent requests to see async benefits."""
    print("\n" + "=" * 60)
    print("TESTING CONCURRENT REQUESTS")
    print("=" * 60)
    
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10.0) as client:
        # Make 10 concurrent requests to health endpoint
        num_requests = 10
        
        async def make_request(i):
            start = time.time()
            response = await client.get("/health/quick")
            elapsed = time.time() - start
            return {
                "request_id": i,
                "status": response.status_code,
                "elapsed": elapsed,
                "process_time": response.headers.get("X-Process-Time", "N/A")
            }
        
        start_time = time.time()
        results = await asyncio.gather(*[make_request(i) for i in range(num_requests)])
        total_time = time.time() - start_time
        
        print(f"✅ Completed {num_requests} concurrent requests")
        print(f"   Total time: {total_time:.4f}s")
        print(f"   Average per request: {total_time/num_requests:.4f}s")
        print(f"   Requests per second: {num_requests/total_time:.2f}")
        
        # Show individual request times
        print("\n   Individual request times:")
        for result in results[:5]:  # Show first 5
            print(f"     Request {result['request_id']}: {result['elapsed']:.4f}s (process: {result['process_time']})")
        if len(results) > 5:
            print(f"     ... and {len(results) - 5} more")


async def check_server_running():
    """Check if the FastAPI server is running."""
    try:
        async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=2.0) as client:
            response = await client.get("/health/quick")
            return response.status_code == 200
    except:
        return False


async def main():
    """Run all route tests."""
    print("\n" + "=" * 70)
    print("ASYNC ROUTE HANDLER TESTS")
    print("=" * 70)
    
    # Check if server is running
    print("\nChecking if server is running...")
    server_running = await check_server_running()
    
    if not server_running:
        print("❌ Server is not running!")
        print("\nTo run these tests:")
        print("  1. Start the FastAPI server: uvicorn app.main:app --reload")
        print("  2. Then run this script again")
        return 1
    
    print("✅ Server is running\n")
    
    try:
        # Test 1: Health endpoint
        await test_health_endpoint()
        
        # Test 2: Concurrent requests
        await test_concurrent_requests()
        
        # Test 3: Trades endpoint (may require auth)
        await test_trades_endpoint_performance()
        
        print("\n" + "=" * 70)
        print("✅ All route tests completed!")
        print("=" * 70)
        print("\n💡 Tips:")
        print("  - Check X-Process-Time header in responses for performance metrics")
        print("  - Compare response times before/after async migration")
        print("  - Monitor server logs for any errors")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

