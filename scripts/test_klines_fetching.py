"""
Diagnostic tool to test klines fetching for symbols.

This script tests:
1. Basic klines fetching for various symbols
2. Different intervals (1m, 5m, 1h, etc.)
3. Error handling and retries
4. Data validation (timestamps, prices, etc.)
5. Rate limiting behavior
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from app.core.my_binance_client import BinanceClient
from app.core.paper_binance_client import PaperBinanceClient
from app.core.exceptions import BinanceAPIError, BinanceNetworkError, BinanceRateLimitError


def validate_klines(klines: List[List[Any]], symbol: str, interval: str) -> Dict[str, Any]:
    """Validate klines data structure and content.
    
    Returns:
        Dictionary with validation results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "stats": {}
    }
    
    if not klines:
        results["valid"] = False
        results["errors"].append("No klines returned")
        return results
    
    # Check structure
    if not isinstance(klines, list):
        results["valid"] = False
        results["errors"].append(f"Klines is not a list: {type(klines)}")
        return results
    
    if len(klines) == 0:
        results["warnings"].append("Empty klines list")
        return results
    
    # Validate first kline structure
    first_kline = klines[0]
    if not isinstance(first_kline, list):
        results["valid"] = False
        results["errors"].append(f"Kline is not a list: {type(first_kline)}")
        return results
    
    if len(first_kline) < 6:
        results["valid"] = False
        results["errors"].append(f"Kline has insufficient fields: {len(first_kline)} (expected at least 6)")
        return results
    
    # Extract data
    timestamps = []
    prices = []
    volumes = []
    
    for i, kline in enumerate(klines):
        try:
            # Kline format: [open_time, open, high, low, close, volume, close_time, ...]
            open_time = int(kline[0])
            close_time = int(kline[6]) if len(kline) > 6 else None
            open_price = float(kline[1])
            high_price = float(kline[2])
            low_price = float(kline[3])
            close_price = float(kline[4])
            volume = float(kline[5])
            
            # Validate prices
            if open_price <= 0 or high_price <= 0 or low_price <= 0 or close_price <= 0:
                results["errors"].append(f"Kline {i}: Invalid price (<= 0)")
                results["valid"] = False
            
            if high_price < low_price:
                results["errors"].append(f"Kline {i}: High < Low ({high_price} < {low_price})")
                results["valid"] = False
            
            if open_price > high_price or open_price < low_price:
                results["warnings"].append(f"Kline {i}: Open price outside [low, high] range")
            
            if close_price > high_price or close_price < low_price:
                results["warnings"].append(f"Kline {i}: Close price outside [low, high] range")
            
            # Validate timestamps
            if open_time <= 0:
                results["errors"].append(f"Kline {i}: Invalid open_time ({open_time})")
                results["valid"] = False
            
            if close_time and close_time <= open_time:
                results["errors"].append(f"Kline {i}: close_time <= open_time")
                results["valid"] = False
            
            # Validate volume
            if volume < 0:
                results["warnings"].append(f"Kline {i}: Negative volume ({volume})")
            
            timestamps.append(open_time)
            prices.append(close_price)
            volumes.append(volume)
            
        except (ValueError, IndexError, TypeError) as e:
            results["errors"].append(f"Kline {i}: Parse error - {e}")
            results["valid"] = False
    
    # Check timestamp ordering
    if len(timestamps) > 1:
        for i in range(1, len(timestamps)):
            if timestamps[i] <= timestamps[i-1]:
                results["warnings"].append(f"Kline {i}: Timestamp not strictly increasing")
    
    # Calculate stats
    if prices:
        results["stats"] = {
            "count": len(klines),
            "first_timestamp": timestamps[0] if timestamps else None,
            "last_timestamp": timestamps[-1] if timestamps else None,
            "first_price": prices[0] if prices else None,
            "last_price": prices[-1] if prices else None,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "total_volume": sum(volumes) if volumes else None,
        }
    
    return results


def test_klines_fetching(
    client: BinanceClient | PaperBinanceClient,
    symbol: str,
    interval: str = "1m",
    limit: int = 100
) -> Dict[str, Any]:
    """Test klines fetching for a symbol.
    
    Returns:
        Dictionary with test results
    """
    result = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "success": False,
        "error": None,
        "klines_count": 0,
        "validation": None,
        "duration_ms": 0
    }
    
    start_time = datetime.now(timezone.utc)
    
    try:
        # Fetch klines
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        
        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        result["success"] = True
        result["klines_count"] = len(klines) if klines else 0
        result["duration_ms"] = duration_ms
        
        # Validate klines
        if klines:
            validation = validate_klines(klines, symbol, interval)
            result["validation"] = validation
            
            if not validation["valid"]:
                result["error"] = f"Validation failed: {', '.join(validation['errors'])}"
        
    except BinanceRateLimitError as e:
        result["error"] = f"Rate limit error: {e}"
        result["rate_limited"] = True
    except BinanceAPIError as e:
        result["error"] = f"API error: {e}"
    except BinanceNetworkError as e:
        result["error"] = f"Network error: {e}"
    except Exception as e:
        result["error"] = f"Unexpected error: {type(e).__name__}: {e}"
    
    return result


def print_test_results(results: List[Dict[str, Any]]) -> None:
    """Print formatted test results."""
    print("\n" + "="*80)
    print("KLINES FETCHING TEST RESULTS")
    print("="*80)
    
    total_tests = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total_tests - successful
    
    print(f"\nTotal Tests: {total_tests}")
    print(f"Successful: {successful} [OK]")
    print(f"Failed: {failed} [FAILED]")
    
    for result in results:
        print("\n" + "-"*80)
        print(f"Symbol: {result['symbol']} | Interval: {result['interval']} | Limit: {result['limit']}")
        
        if result["success"]:
            print(f"[OK] SUCCESS - Fetched {result['klines_count']} klines in {result['duration_ms']:.2f}ms")
            
            if result["validation"]:
                validation = result["validation"]
                if validation["valid"]:
                    print("[OK] Validation: PASSED")
                else:
                    print(f"[FAILED] Validation: FAILED")
                    for error in validation["errors"]:
                        print(f"   - {error}")
                
                if validation["warnings"]:
                    print("[WARNING] Warnings:")
                    for warning in validation["warnings"]:
                        print(f"   - {warning}")
                
                if validation["stats"]:
                    stats = validation["stats"]
                    print(f"[STATS] Stats:")
                    print(f"   - Count: {stats.get('count', 'N/A')}")
                    if stats.get("first_timestamp") and stats.get("last_timestamp"):
                        first_dt = datetime.fromtimestamp(stats["first_timestamp"] / 1000, tz=timezone.utc)
                        last_dt = datetime.fromtimestamp(stats["last_timestamp"] / 1000, tz=timezone.utc)
                        print(f"   - Time Range: {first_dt} to {last_dt}")
                    if stats.get("first_price") and stats.get("last_price"):
                        print(f"   - Price Range: {stats['first_price']:.8f} to {stats['last_price']:.8f}")
        else:
            print(f"[FAILED] FAILED - {result['error']}")
    
    print("\n" + "="*80)


async def main():
    """Main test function."""
    import os
    
    # Get API credentials from environment
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    
    if not api_key or not api_secret:
        print("WARNING: BINANCE_API_KEY and BINANCE_API_SECRET not set. Using test mode.")
        # Create a dummy client for testing (will fail on actual fetch)
        client = None
    else:
        # Create real client
        client = BinanceClient(api_key=api_key, api_secret=api_secret, testnet=testnet)
    
    # Test symbols (common trading pairs)
    test_symbols = [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "INUSDT",  # From user's logs
    ]
    
    # Test intervals
    test_intervals = [
        "1m",
        "5m",
        "15m",
        "1h",
    ]
    
    # Test limits
    test_limits = [10, 50, 100]
    
    results = []
    
    print("Starting klines fetching tests...")
    print(f"Test symbols: {', '.join(test_symbols)}")
    print(f"Test intervals: {', '.join(test_intervals)}")
    print(f"Test limits: {', '.join(map(str, test_limits))}")
    
    if client is None:
        print("\n[WARNING] Cannot run tests without API credentials.")
        print("Set BINANCE_API_KEY and BINANCE_API_SECRET environment variables.")
        return
    
    # Run tests
    for symbol in test_symbols:
        for interval in test_intervals:
            for limit in test_limits:
                print(f"\nTesting: {symbol} {interval} limit={limit}...")
                result = test_klines_fetching(client, symbol, interval, limit)
                results.append(result)
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)
    
    # Print results
    print_test_results(results)
    
    # Summary
    print("\n[SUMMARY] SUMMARY")
    print("="*80)
    
    # Group by symbol
    by_symbol = {}
    for result in results:
        symbol = result["symbol"]
        if symbol not in by_symbol:
            by_symbol[symbol] = {"success": 0, "failed": 0}
        if result["success"]:
            by_symbol[symbol]["success"] += 1
        else:
            by_symbol[symbol]["failed"] += 1
    
    print("\nResults by Symbol:")
    for symbol, counts in by_symbol.items():
        total = counts["success"] + counts["failed"]
        success_pct = (counts["success"] / total * 100) if total > 0 else 0
        print(f"  {symbol}: {counts['success']}/{total} successful ({success_pct:.1f}%)")
    
    # Group by interval
    by_interval = {}
    for result in results:
        interval = result["interval"]
        if interval not in by_interval:
            by_interval[interval] = {"success": 0, "failed": 0}
        if result["success"]:
            by_interval[interval]["success"] += 1
        else:
            by_interval[interval]["failed"] += 1
    
    print("\nResults by Interval:")
    for interval, counts in by_interval.items():
        total = counts["success"] + counts["failed"]
        success_pct = (counts["success"] / total * 100) if total > 0 else 0
        print(f"  {interval}: {counts['success']}/{total} successful ({success_pct:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())

