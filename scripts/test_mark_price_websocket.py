#!/usr/bin/env python3
"""
Test Binance Futures Mark Price WebSocket (same URL as the app).

Usage:
  python scripts/test_mark_price_websocket.py [SYMBOL]           # Connect, receive one message, exit
  python scripts/test_mark_price_websocket.py PIPPINUSDT --stream 30   # Stream for 30 seconds
  python scripts/test_mark_price_websocket.py btcusdt --testnet  # Use testnet URL

Default symbol: btcusdt. Use --testnet to hit testnet.binancefuture.com (app uses mainnet unless BINANCE_TESTNET=true).
"""
import argparse
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


def get_url(symbol: str, testnet: bool = False) -> str:
    """Same URL logic as app (MarkPriceConnection)."""
    symbol = symbol.lower()
    if testnet:
        return f"wss://testnet.binancefuture.com/ws/{symbol}@markPrice@1s"
    return f"wss://fstream.binance.com/ws/{symbol}@markPrice@1s"


async def receive_one(url: str, timeout: float = 10.0) -> None:
    """Connect, receive one markPriceUpdate, print and exit."""
    print(f"Connecting to: {url}")
    try:
        async with websockets.connect(
            url,
            open_timeout=15,
            close_timeout=5,
        ) as ws:
            print("OK: WebSocket connected.")
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(msg)
            if data.get("e") != "markPriceUpdate":
                print(f"Message: e={data.get('e')} (expected markPriceUpdate)")
            else:
                s = data.get("s", "?")
                p = data.get("p", "?")
                print(f"OK: {s} markPrice={p}")
            print("Conclusion: Mark Price stream is reachable from this machine.")
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"FAIL: Server rejected connection: HTTP {e.status_code}")
        if e.status_code == 502:
            print("Conclusion: Binance (or proxy) returned 502 - server-side or network issue.")
    except asyncio.TimeoutError:
        print("FAIL: Timeout (connection or first message).")
        print("Conclusion: Network/firewall may be blocking or Binance slow.")
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        print("Conclusion: Connection failed (see error above).")


async def stream(url: str, duration_seconds: float) -> None:
    """Connect and print mark price updates for the given duration."""
    print(f"Connecting to: {url}")
    print(f"Streaming for {duration_seconds:.0f}s (Ctrl+C to stop early)...")
    try:
        async with websockets.connect(
            url,
            open_timeout=15,
            close_timeout=5,
        ) as ws:
            print("OK: WebSocket connected. Messages:")
            end = asyncio.get_event_loop().time() + duration_seconds
            count = 0
            while asyncio.get_event_loop().time() < end:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                data = json.loads(msg)
                if data.get("e") != "markPriceUpdate":
                    continue
                count += 1
                s = data.get("s", "?")
                p = data.get("p", "?")
                print(f"  [{count}] {s} markPrice={p}")
            print(f"Done: received {count} mark price updates.")
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"FAIL: HTTP {e.status_code}")
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Binance Futures Mark Price WebSocket")
    parser.add_argument("symbol", nargs="?", default="btcusdt", help="Symbol (e.g. btcusdt, pippinusdt)")
    parser.add_argument("--testnet", action="store_true", help="Use testnet URL (default: mainnet)")
    parser.add_argument("--stream", type=float, metavar="SECS", default=0, help="Stream for SECS seconds instead of one message")
    args = parser.parse_args()

    symbol = args.symbol.strip().lower()
    url = get_url(symbol, testnet=args.testnet)

    if args.stream > 0:
        asyncio.run(stream(url, args.stream))
    else:
        asyncio.run(receive_one(url))


if __name__ == "__main__":
    main()
