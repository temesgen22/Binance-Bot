"""
Example script to view the last 21 closed candlesticks and calculate EMAs
This shows exactly what data the strategy uses for 8/21 EMA configuration.
"""

from datetime import datetime
from statistics import fmean
from typing import Any
import sys
import os
from pathlib import Path

# Ensure project root on path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def _prefer_global_python_binance() -> None:
    exe = Path(sys.executable)
    global_site = exe.parent / "Lib" / "site-packages"
    client_file = global_site / "binance" / "client.py"
    if client_file.exists():
        site_str = str(global_site)
        if site_str in sys.path:
            sys.path.remove(site_str)
        sys.path.insert(0, site_str)


_prefer_global_python_binance()

USE_PROJECT_CLIENT = False
BINANCE_AVAILABLE = False

try:
    from app.core.my_binance_client import BinanceClient
    from app.core.config import get_settings
    USE_PROJECT_CLIENT = True
except ImportError:
    try:
        from binance.client import Client
        BINANCE_AVAILABLE = True
    except ImportError:
        print("⚠️  python-binance not installed and project BinanceClient unavailable.")
        print("   Showing example data structure instead...\n")


def calculate_ema_from_prices(prices: list[float], period: int) -> float:
    """
    Calculate EMA from a list of prices.
    This matches the strategy's EMA calculation method.
    """
    if len(prices) < period:
        return fmean(prices) if prices else 0.0
    
    smoothing = 2.0 / (period + 1)
    # Start with SMA for the first value
    ema = fmean(prices[:period])
    
    # Calculate EMA for remaining prices
    for p in prices[period:]:
        ema = (p - ema) * smoothing + ema
    
    return ema


def format_timestamp(ms: int) -> str:
    """Convert milliseconds timestamp to readable format."""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def view_candles(
    symbol: str = "PIPPINUSDT",
    interval: str = "1m",
    limit: int = 31,
    use_testnet: bool | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> None:
    """
    Fetch and display the last N closed candles and calculate EMAs.
    
    Args:
        symbol: Trading pair (e.g., "PIPPINUSDT")
        interval: Candlestick interval (e.g., "1m")
        limit: Number of candles to fetch (strategy fetches 31, uses last 21 closed)
        use_testnet: Use Binance testnet (default: False, uses production)
        api_key: Binance API key (optional, for authenticated requests)
        api_secret: Binance API secret (optional, for authenticated requests)
    """
    if not (USE_PROJECT_CLIENT or BINANCE_AVAILABLE):
        show_example_structure()
        return

    try:
        # Prefer project BinanceClient for consistent behavior
        if USE_PROJECT_CLIENT:
            settings = get_settings()
            resolved_testnet = settings.binance_testnet if use_testnet is None else use_testnet
            resolved_key = api_key or settings.binance_api_key
            resolved_secret = api_secret or settings.binance_api_secret
            client = BinanceClient(
                api_key=resolved_key,
                api_secret=resolved_secret,
                testnet=resolved_testnet,
            )
            print(f"✅ Using project BinanceClient ({'TESTNET' if resolved_testnet else 'PRODUCTION'})")
        else:
            # Fallback to python-binance client
            if api_key and api_secret:
                client = Client(api_key=api_key, api_secret=api_secret, testnet=use_testnet)
                print(f"🔑 Using authenticated client (testnet={use_testnet})")
            else:
                # Try load from .env
                try:
                    from dotenv import load_dotenv

                    load_dotenv()
                    env_key = os.getenv("BINANCE_API_KEY")
                    env_secret = os.getenv("BINANCE_API_SECRET")
                    env_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
                    if env_key and env_secret:
                        client = Client(api_key=env_key, api_secret=env_secret, testnet=env_testnet)
                        print(f"🔑 Loaded API keys from .env file (testnet={env_testnet})")
                    else:
                        client = Client(testnet=use_testnet)
                        print(f"📡 Using public client (testnet={use_testnet}) - no API keys required")
                except ImportError:
                    client = Client(testnet=use_testnet)
                    print(f"📡 Using public client (testnet={use_testnet}) - no API keys required")
        
        print(f"\n{'='*80}")
        print(f"Fetching {limit} candles for {symbol} ({interval} interval)")
        print(f"{'='*80}\n")
        
        # Test connection first
        current_time = datetime.now()
        print(f"⏰ Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            current_time = datetime.now()
            print(f"⏰ Current time: {current_time:%Y-%m-%d %H:%M:%S}")

            if USE_PROJECT_CLIENT:
                klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            else:
                klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
            
            if not klines or len(klines) == 0:
                print("❌ No data received from Binance")
                print("\n💡 Possible issues:")
                print("   1. Symbol doesn't exist on Binance Futures")
                print("   2. Symbol not available on testnet (if using testnet=True)")
                print("   3. Network connection issue")
                return
                
        except Exception as api_error:
            print(f"❌ Error fetching data from Binance: {api_error}")
            print(f"\nError type: {type(api_error).__name__}")
            print("\n💡 Possible solutions:")
            print("   1. Check if symbol exists: Try 'BTCUSDT' or 'ETHUSDT'")
            print("   2. If using testnet, try production (testnet=False)")
            print("   3. Check internet connection")
            print("   4. Verify symbol is available on Binance Futures")
            raise
        
        # Verify we got actual data
        if len(klines) < 2:
            print(f"⚠️  Warning: Only received {len(klines)} candle(s) - need at least 2")
            return
        
        # Strategy ignores the last (forming) candle
        closed_klines = klines[:-1]
        forming_candle = klines[-1]
        
        # Get timestamps to verify data freshness
        first_candle_time = datetime.fromtimestamp(int(closed_klines[0][0]) / 1000)
        last_closed_time = datetime.fromtimestamp(int(closed_klines[-1][6]) / 1000)
        forming_time = datetime.fromtimestamp(int(forming_candle[0]) / 1000)
        
        print(f"📊 Total candles fetched: {len(klines)}")
        print(f"✅ Closed candles: {len(closed_klines)}")
        print(f"⏳ Forming candle: 1 (ignored by strategy)")
        print(f"\n📅 First candle: {first_candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 Last closed: {last_closed_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 Forming now: {forming_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Check data freshness
        time_diff = (current_time - last_closed_time).total_seconds()
        if time_diff > 300:  # More than 5 minutes old
            print(f"⚠️  WARNING: Last candle is {time_diff/60:.1f} minutes old - data may be stale!")
        
        print()
        
        # Extract closing prices (strategy uses these for EMA)
        closing_prices = [float(k[4]) for k in closed_klines]  # Index 4 = close price
        
        print(f"{'='*80}")
        print(f"LAST 21 CLOSED CANDLESTICKS (for 8/21 EMA calculation)")
        print(f"{'='*80}\n")
        
        # Show last 21 candles (minimum needed for slow EMA)
        last_21 = closed_klines[-21:] if len(closed_klines) >= 21 else closed_klines
        last_21_prices = closing_prices[-21:] if len(closing_prices) >= 21 else closing_prices
        
        print(f"{'#':<4} {'Time':<20} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12} {'Volume':<15}")
        print("-" * 80)
        
        start_idx = len(closed_klines) - len(last_21)
        for i, kline in enumerate(last_21):
            candle_num = start_idx + i + 1
            open_time = int(kline[0])
            open_price = float(kline[1])
            high_price = float(kline[2])
            low_price = float(kline[3])
            close_price = float(kline[4])
            volume = float(kline[5])
            
            time_str = format_timestamp(open_time)
            
            print(f"{candle_num:<4} {time_str:<20} {open_price:<12.8f} {high_price:<12.8f} "
                  f"{low_price:<12.8f} {close_price:<12.8f} {volume:<15.2f}")
        
        print(f"\n{'='*80}")
        print("EMA CALCULATIONS (8/21 EMA Configuration)")
        print(f"{'='*80}\n")
        
        # Calculate EMAs (same as strategy)
        fast_period = 8
        slow_period = 21
        
        if len(closing_prices) >= slow_period:
            # Use all available prices (strategy uses up to slow_period * 5)
            fast_ema = calculate_ema_from_prices(closing_prices, fast_period)
            slow_ema = calculate_ema_from_prices(closing_prices, slow_period)
            last_close = closing_prices[-1]
            
            print(f"📈 Fast EMA ({fast_period}): {fast_ema:.8f}")
            print(f"📉 Slow EMA ({slow_period}): {slow_ema:.8f}")
            print(f"💰 Last Close Price: {last_close:.8f}")
            print()
            
            # Check for crossover
            if len(closing_prices) >= slow_period + 1:
                # Calculate previous EMAs for crossover detection
                prev_prices = closing_prices[:-1]
                prev_fast_ema = calculate_ema_from_prices(prev_prices, fast_period)
                prev_slow_ema = calculate_ema_from_prices(prev_prices, slow_period)
                
                print(f"📊 Previous Fast EMA: {prev_fast_ema:.8f}")
                print(f"📊 Previous Slow EMA: {prev_slow_ema:.8f}")
                print()
                
                # Crossover detection
                golden_cross = (prev_fast_ema <= prev_slow_ema) and (fast_ema > slow_ema)
                death_cross = (prev_fast_ema >= prev_slow_ema) and (fast_ema < slow_ema)
                
                if golden_cross:
                    print("🟢 GOLDEN CROSS DETECTED → BUY SIGNAL (Long Entry)")
                elif death_cross:
                    print("🔴 DEATH CROSS DETECTED → SELL SIGNAL (Short Entry or Long Exit)")
                else:
                    if fast_ema > slow_ema:
                        print("📈 Fast EMA > Slow EMA (Uptrend, but no crossover)")
                    else:
                        print("📉 Fast EMA < Slow EMA (Downtrend, but no crossover)")
                
                # EMA separation
                ema_separation_pct = abs(fast_ema - slow_ema) / last_close if last_close > 0 else 0
                min_separation = 0.0002  # 0.02%
                print()
                print(f"📏 EMA Separation: {ema_separation_pct:.6f} ({ema_separation_pct*100:.4f}%)")
                print(f"🎯 Min Required: {min_separation:.6f} ({min_separation*100:.4f}%)")
                
                if ema_separation_pct >= min_separation:
                    print("✅ Separation filter: PASSED")
                else:
                    print("❌ Separation filter: BLOCKED (too small)")
        else:
            print(f"⚠️  Insufficient data: {len(closing_prices)} candles (need {slow_period} minimum)")
            print(f"   Strategy will HOLD until {slow_period} closed candles are available")
        
        print(f"\n{'='*80}")
        print("CANDLESTICK DATA STRUCTURE")
        print(f"{'='*80}\n")
        print("Each kline is a list with the following structure:")
        print("  [0] open_time    - Opening time (milliseconds)")
        print("  [1] open         - Opening price")
        print("  [2] high         - Highest price")
        print("  [3] low          - Lowest price")
        print("  [4] close        - Closing price (used for EMA)")
        print("  [5] volume       - Trading volume")
        print("  [6] close_time   - Closing time (milliseconds)")
        print("  [7] quote_volume - Quote asset volume")
        print("  [8] trades       - Number of trades")
        print("  [9] taker_buy_base - Taker buy base volume")
        print("  [10] taker_buy_quote - Taker buy quote volume")
        print("  [11] ignore      - Ignore field")
        
        print(f"\n{'='*80}")
        print("STRATEGY BEHAVIOR")
        print(f"{'='*80}\n")
        print("✅ Strategy uses: Closing prices from closed candles (index [4])")
        print("❌ Strategy ignores: The last (forming) candle")
        print("📊 Strategy needs: Minimum 21 closed candles for slow EMA")
        print("🔄 Strategy checks: Every 10 seconds (interval_seconds)")
        print("🎯 Strategy trades: Only on EMA crossovers (golden/death cross)")
        
    except Exception as e:
        import traceback
        print(f"❌ Error: {e}")
        print(f"\n{'='*80}")
        print("FULL ERROR DETAILS:")
        print("="*80)
        traceback.print_exc()
        print(f"\n{'='*80}")
        print("\n💡 Troubleshooting:")
        print("   1. python-binance installed? Run: pip install python-binance")
        print("   2. Internet connection working?")
        print("   3. Symbol exists on Binance Futures? Try: BTCUSDT, ETHUSDT")
        print("   4. If using testnet, symbol may not exist - try production")
        print("   5. Check your .env file for BINANCE_API_KEY and BINANCE_API_SECRET")


def show_example_structure():
    """Show example data structure when Binance is not available."""
    print("\n" + "="*80)
    print("EXAMPLE: Last 21 Closed Candlesticks Structure")
    print("="*80 + "\n")
    
    print("Each candle is a list with 12 elements:")
    print("  [open_time, open, high, low, close, volume, close_time, ...]")
    print()
    print("Example for PIPPINUSDT (1-minute candles):")
    print("-" * 80)
    print(f"{'#':<4} {'Time':<20} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12}")
    print("-" * 80)
    
    # Example data (simulated)
    base_price = 0.06084
    import random
    random.seed(42)  # For reproducible example
    
    for i in range(21):
        # Simulate price movement
        change = random.uniform(-0.001, 0.001)
        price = base_price + change
        open_price = price - random.uniform(0, 0.0005)
        high_price = price + random.uniform(0, 0.0005)
        low_price = price - random.uniform(0, 0.0005)
        close_price = price
        
        time_str = f"2024-01-15 10:{20+i:02d}:00"
        print(f"{i+1:<4} {time_str:<20} {open_price:<12.8f} {high_price:<12.8f} "
              f"{low_price:<12.8f} {close_price:<12.8f}")
    
    print("\n" + "="*80)
    print("EMA Calculation Process")
    print("="*80 + "\n")
    print("1. Strategy extracts closing prices: [close_price_1, close_price_2, ..., close_price_21]")
    print("2. Calculates Fast EMA (8-period) from these closing prices")
    print("3. Calculates Slow EMA (21-period) from these closing prices")
    print("4. Compares current EMAs with previous EMAs to detect crossovers")
    print("5. If crossover detected + filters pass → Creates position")


if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="View Binance candlestick data and calculate EMAs")
    parser.add_argument("symbol", nargs="?", default="BTCUSDT", help="Trading symbol (e.g., BTCUSDT)")
    parser.add_argument("interval", nargs="?", default="1m", help="Candlestick interval (e.g., 1m, 5m)")
    parser.add_argument("--testnet", action="store_true", help="Force Binance testnet")
    parser.add_argument("--production", action="store_true", help="Force Binance production")
    parser.add_argument("--api-key", help="Binance API key (optional)")
    parser.add_argument("--api-secret", help="Binance API secret (optional)")
    
    args = parser.parse_args()
    
    symbol = args.symbol
    interval = args.interval
    use_testnet = True if args.testnet and not args.production else False if args.production and not args.testnet else None
    
    print("\n" + "="*80)
    print("CANDLESTICK DATA VIEWER - 8/21 EMA Strategy")
    print("="*80)
    print(f"\nSymbol: {symbol}")
    print(f"Interval: {interval}")
    print(f"Network: {'TESTNET' if use_testnet else 'PRODUCTION'}")
    print(f"EMA Configuration: Fast=8, Slow=21")
    print(f"\nThis shows the exact data the strategy uses for calculations.\n")
    
    view_candles(
        symbol=symbol, 
        interval=interval, 
        limit=31,
        use_testnet=use_testnet,
        api_key=args.api_key,
        api_secret=args.api_secret
    )
    
    print("\n" + "="*80)
    print("USAGE")
    print("="*80)
    print("\nBasic usage:")
    print("  python view_candles_example.py [SYMBOL] [INTERVAL]")
    print("\nExamples:")
    print("  python view_candles_example.py BTCUSDT 1m")
    print("  python view_candles_example.py ETHUSDT 5m")
    print("  python view_candles_example.py PIPPINUSDT 1m --production")
    print("  python view_candles_example.py BTCUSDT 1m --testnet")
    print("\nOptions:")
    print("  --testnet          Force Binance testnet (overrides settings)")
    print("  --production       Force Binance production (overrides settings)")
    print("  --api-key KEY      Binance API key (optional)")
    print("  --api-secret SECRET Binance API secret (optional)")
    print("\nNote:")
    print("  - Requires python-binance: pip install python-binance")
    print("  - API keys are optional for viewing candlestick data")
    print("  - Script will try to load keys from .env file if available")
    print("  - Most symbols work better on production (not all exist on testnet)")
    print("="*80 + "\n")


