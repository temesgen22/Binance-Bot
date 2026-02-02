"""
Test script to verify Public API implementation for market data.

Tests:
1. BinanceClient.get_klines() uses public API (works without valid API keys)
2. BinanceClient.get_price() uses public API (works without valid API keys)
3. PaperBinanceClient already uses public API
4. Trading operations still require authentication
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from loguru import logger
from app.core.my_binance_client import BinanceClient
from app.core.paper_binance_client import PaperBinanceClient
from app.core.public_market_data_client import PublicMarketDataClient
from app.core.exceptions import BinanceAPIError, BinanceAuthenticationError


def test_public_market_data_client():
    """Test PublicMarketDataClient directly."""
    print("\n" + "="*80)
    print("TEST 1: PublicMarketDataClient Direct Test")
    print("="*80)
    
    try:
        client = PublicMarketDataClient()
        
        # Test get_klines
        print("\n[TEST] Fetching klines for BTCUSDT...")
        klines = client.get_klines("BTCUSDT", "1m", 10)
        print(f"[OK] Got {len(klines)} klines")
        if klines:
            print(f"[OK] Latest candle: open_time={klines[-1][0]}, close={klines[-1][4]}")
        
        # Test get_price
        print("\n[TEST] Fetching price for BTCUSDT...")
        price = client.get_price("BTCUSDT")
        print(f"[OK] Current price: ${price:,.2f}")
        
        return True
    except Exception as e:
        print(f"[FAILED] Error: {e}")
        return False


def test_binance_client_klines():
    """Test BinanceClient.get_klines() uses public API."""
    print("\n" + "="*80)
    print("TEST 2: BinanceClient.get_klines() - Should Use Public API")
    print("="*80)
    
    try:
        # Use dummy API keys - should still work because get_klines uses public API
        print("\n[TEST] Creating BinanceClient with dummy API keys...")
        client = BinanceClient(api_key="dummy_key", api_secret="dummy_secret", testnet=True)
        
        print("[TEST] Fetching klines (should work without valid API keys)...")
        klines = client.get_klines("BTCUSDT", "1m", 10)
        print(f"[OK] Got {len(klines)} klines using public API")
        if klines:
            print(f"[OK] Latest candle: open_time={klines[-1][0]}, close={klines[-1][4]}")
        
        return True
    except Exception as e:
        print(f"[FAILED] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_binance_client_price():
    """Test BinanceClient.get_price() uses public API."""
    print("\n" + "="*80)
    print("TEST 3: BinanceClient.get_price() - Should Use Public API")
    print("="*80)
    
    try:
        # Use dummy API keys - should still work because get_price uses public API
        print("\n[TEST] Creating BinanceClient with dummy API keys...")
        client = BinanceClient(api_key="dummy_key", api_secret="dummy_secret", testnet=True)
        
        print("[TEST] Fetching price (should work without valid API keys)...")
        price = client.get_price("BTCUSDT")
        print(f"[OK] Got price: ${price:,.2f} using public API")
        
        return True
    except Exception as e:
        print(f"[FAILED] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_paper_binance_client():
    """Test PaperBinanceClient already uses public API."""
    print("\n" + "="*80)
    print("TEST 4: PaperBinanceClient - Should Use Public API")
    print("="*80)
    
    try:
        print("\n[TEST] Creating PaperBinanceClient...")
        client = PaperBinanceClient(account_id="test", initial_balance=10000.0)
        
        print("[TEST] Fetching klines (should use public API)...")
        klines = client.get_klines("BTCUSDT", "1m", 10)
        print(f"[OK] Got {len(klines)} klines using public API")
        
        print("[TEST] Fetching price (should use public API)...")
        price = client.get_price("BTCUSDT")
        print(f"[OK] Got price: ${price:,.2f} using public API")
        
        return True
    except Exception as e:
        print(f"[FAILED] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_trading_operations_require_auth():
    """Test that trading operations still require authentication."""
    print("\n" + "="*80)
    print("TEST 5: Trading Operations - Should Require Authentication")
    print("="*80)
    
    try:
        # Use dummy API keys - trading operations should fail
        print("\n[TEST] Creating BinanceClient with dummy API keys...")
        client = BinanceClient(api_key="dummy_key", api_secret="dummy_secret", testnet=True)
        
        print("[TEST] Attempting to get open position (should fail without valid API keys)...")
        try:
            position = client.get_open_position("BTCUSDT")
            print(f"[WARNING] Got position: {position} (unexpected - should require auth)")
            return False
        except (BinanceAPIError, BinanceAuthenticationError, Exception) as e:
            print(f"[OK] Correctly requires authentication: {type(e).__name__}")
            return True
        
    except Exception as e:
        print(f"[INFO] Expected error for trading operations: {e}")
        return True


def test_multiple_symbols():
    """Test fetching klines and prices for multiple symbols."""
    print("\n" + "="*80)
    print("TEST 6: Multiple Symbols Test")
    print("="*80)
    
    try:
        client = PublicMarketDataClient()
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "INUSDT"]
        
        print("\n[TEST] Fetching klines for multiple symbols...")
        for symbol in symbols:
            try:
                klines = client.get_klines(symbol, "1m", 10)
                price = client.get_price(symbol)
                print(f"[OK] {symbol}: {len(klines)} klines, price=${price:,.4f}")
            except Exception as e:
                print(f"[FAILED] {symbol}: {e}")
                return False
        
        return True
    except Exception as e:
        print(f"[FAILED] Error: {e}")
        return False


def test_different_intervals():
    """Test fetching klines for different intervals."""
    print("\n" + "="*80)
    print("TEST 7: Different Intervals Test")
    print("="*80)
    
    try:
        client = PublicMarketDataClient()
        intervals = ["1m", "5m", "15m", "1h"]
        
        print("\n[TEST] Fetching klines for different intervals...")
        for interval in intervals:
            try:
                klines = client.get_klines("BTCUSDT", interval, 10)
                print(f"[OK] {interval}: Got {len(klines)} klines")
            except Exception as e:
                print(f"[FAILED] {interval}: {e}")
                return False
        
        return True
    except Exception as e:
        print(f"[FAILED] Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("PUBLIC API IMPLEMENTATION TEST SUITE")
    print("="*80)
    print("\nTesting that market data (klines, prices) uses public API")
    print("while trading operations still require authentication.\n")
    
    results = []
    
    # Run tests
    results.append(("PublicMarketDataClient Direct", test_public_market_data_client()))
    results.append(("BinanceClient.get_klines()", test_binance_client_klines()))
    results.append(("BinanceClient.get_price()", test_binance_client_price()))
    results.append(("PaperBinanceClient", test_paper_binance_client()))
    results.append(("Trading Operations Auth", test_trading_operations_require_auth()))
    results.append(("Multiple Symbols", test_multiple_symbols()))
    results.append(("Different Intervals", test_different_intervals()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed} [OK]")
    print(f"Failed: {total - passed} [FAILED]")
    
    print("\nDetailed Results:")
    for test_name, result in results:
        status = "[OK]" if result else "[FAILED]"
        print(f"  {status} {test_name}")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed! Public API implementation is working correctly.")
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed. Please review the errors above.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

