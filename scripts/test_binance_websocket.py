"""
Quick test: can this machine open a WebSocket to Binance Futures?
Uses a PUBLIC stream (no API keys). If this works, the network path is OK.
"""
import asyncio
import sys

try:
    import websockets
except ImportError:
    print("FAIL: websockets not installed. Run: pip install websockets")
    sys.exit(1)


async def test_public_stream():
    # Public mark price stream - same host as User Data Stream (fstream.binance.com)
    url = "wss://fstream.binance.com/ws/inusdt@markPrice@1s"
    print(f"Connecting to {url} ...")
    try:
        async with websockets.connect(url, open_timeout=15, close_timeout=5) as ws:
            print("OK: WebSocket connected.")
            # Wait for at least one message
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"OK: Received message ({len(msg)} bytes).")
            return True
    except asyncio.TimeoutError as e:
        print(f"FAIL: Timeout - {e}")
        return False
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    ok = asyncio.run(test_public_stream())
    sys.exit(0 if ok else 1)
