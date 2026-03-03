#!/usr/bin/env python3
"""
Live backtest comparison: Scalping vs Reverse Scalping with the same configuration and symbol.

Fetches real klines from Binance mainnet, runs both strategies with identical params,
and analyzes whether reverse scalping is correctly the opposite of scalping.

Backtest includes (so results are not perfectly opposite):
- Trading fees: 0.03% on entry and exit notional (AVERAGE_FEE_RATE).
- Spread: 0.02% bid/ask (SPREAD_OFFSET) on entry and exit.
- Fixed amount per trade is used so both strategies have the same notional per trade;
  otherwise balance paths differ and position sizes diverge, making total PnL asymmetric.

Usage (from project root):
  python scripts/run_scalping_reverse_live_backtest.py
  python scripts/run_scalping_reverse_live_backtest.py --symbol ETHUSDT --days 5
"""

import asyncio
import argparse
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

# Add project root to path when run as script
import sys
from pathlib import Path
if __name__ == "__main__" and __package__ is None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from app.api.routes.backtesting import (
    run_backtest,
    BacktestRequest,
    BacktestResult,
    _fetch_historical_klines_mainnet,
)
from app.core.my_binance_client import BinanceClient


# Shared config for both strategies (same symbol, range, params).
# Use same interval, no TP/SL (exits only on EMA cross), zero cooldown for comparable data.
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_DAYS = 5
DEFAULT_INTERVAL = "1m"
SHARED_PARAMS = {
    "kline_interval": DEFAULT_INTERVAL,
    "ema_fast": 8,
    "ema_slow": 21,
    "take_profit_pct": 1.0,   # exclude TP/SL: set very wide so only EMA cross exits (100% = never hit)
    "stop_loss_pct": 1.0,     # exclude TP/SL: same
    "enable_short": True,
    "min_ema_separation": 0.0,   # disabled so same crosses trigger both
    "enable_htf_bias": False,    # disabled so no 5m filter blocking entries
    "cooldown_candles": 0,       # zero cooldown
    "enable_ema_cross_exit": True,
    "trailing_stop_enabled": False,
}


# Fixed amount per trade (USDT) so both strategies use same notional → comparable PnL.
# Without this, balance changes differently so position sizes diverge and total PnL isn't opposite.
FIXED_AMOUNT_USDT = 50.0


def make_request(symbol: str, strategy_type: str, start_time: datetime, end_time: datetime) -> BacktestRequest:
    return BacktestRequest(
        symbol=symbol,
        strategy_type=strategy_type,
        start_time=start_time,
        end_time=end_time,
        leverage=5,
        risk_per_trade=0.01,
        initial_balance=1000.0,
        fixed_amount=FIXED_AMOUNT_USDT,
        params=SHARED_PARAMS.copy(),
        include_klines=False,
    )


def print_result(name: str, r: BacktestResult) -> None:
    print(f"\n--- {name} ---")
    print(f"  Completed trades: {r.completed_trades}")
    print(f"  Total PnL: ${r.total_pnl:.4f}")
    print(f"  Total return %: {r.total_return_pct:.2f}%")
    print(f"  Win rate: {r.win_rate:.1f}%")
    print(f"  Final balance: ${r.final_balance:.2f}")
    print(f"  Trades list: {len(r.trades)} entries")


def analyze_opposite(scalping: BacktestResult, reverse: BacktestResult) -> None:
    """Check if reverse scalping is opposite of scalping (positions and PnL)."""
    print("\n" + "=" * 60)
    print("ANALYSIS: Is Reverse Scalping the opposite of Scalping?")
    print("=" * 60)

    # 1) Total PnL should be roughly opposite (opposite sign, within tolerance for fees/spread)
    expected_reverse_pnl = -scalping.total_pnl
    pnl_diff = abs(reverse.total_pnl - expected_reverse_pnl)
    opposite_sign = (scalping.total_pnl > 0) == (reverse.total_pnl < 0) or (scalping.total_pnl == 0 and reverse.total_pnl == 0)
    tolerance = max(2.0, abs(scalping.total_pnl) * 0.2)  # 20% of |scalping PnL| or $2
    pnl_ok = opposite_sign and pnl_diff <= tolerance
    print(f"\n1) Total PnL:")
    print(f"   Scalping  total PnL: ${scalping.total_pnl:.4f}")
    print(f"   Reverse   total PnL: ${reverse.total_pnl:.4f}")
    print(f"   Expected (opposite): ${expected_reverse_pnl:.4f}")
    print(f"   Difference: ${pnl_diff:.4f}")
    print(f"   Opposite sign: {'Yes' if opposite_sign else 'No'}")
    print(f"   Verdict: {'PASS (opposite sign and within tolerance)' if pnl_ok else 'CHECK (not opposite or large deviation)'}")

    # 2) Same number of completed trades (or very close)
    count_ok = scalping.completed_trades == reverse.completed_trades
    print(f"\n2) Trade count:")
    print(f"   Scalping: {scalping.completed_trades} completed")
    print(f"   Reverse:  {reverse.completed_trades} completed")
    print(f"   Verdict: {'PASS (same count)' if count_ok else 'CHECK (counts differ)'}")

    # 3) For each completed trade: position_side should be opposite
    closed_s = [t for t in scalping.trades if not t.get("is_open", True)]
    closed_r = [t for t in reverse.trades if not t.get("is_open", True)]
    opposite_sides = 0
    if len(closed_s) == len(closed_r) and len(closed_s) > 0:
        for i, (ts, tr) in enumerate(zip(closed_s, closed_r)):
            side_s = ts.get("position_side", "")
            side_r = tr.get("position_side", "")
            if (side_s == "LONG" and side_r == "SHORT") or (side_s == "SHORT" and side_r == "LONG"):
                opposite_sides += 1
            else:
                print(f"   Trade {i+1}: Scalping={side_s}, Reverse={side_r} (expected opposite sides)")
        print(f"\n3) Position sides (LONG vs SHORT):")
        print(f"   Opposite sides: {opposite_sides}/{len(closed_s)}")
        print(f"   Verdict: {'PASS (all opposite)' if opposite_sides == len(closed_s) else 'CHECK (some same-side)'}")
    else:
        print(f"\n3) Position sides: skipped (trade counts differ or no closed trades)")

    # 4) Net PnL per trade should be roughly opposite
    if len(closed_s) == len(closed_r) and len(closed_s) > 0:
        mismatches = 0
        for i, (ts, tr) in enumerate(zip(closed_s, closed_r)):
            ns = ts.get("net_pnl") or 0
            nr = tr.get("net_pnl") or 0
            expected_nr = -ns
            if abs(nr - expected_nr) > 0.5:
                mismatches += 1
        print(f"\n4) Per-trade net PnL (opposite sign):")
        print(f"   Trades with PnL ~opposite: {len(closed_s) - mismatches}/{len(closed_s)}")
        print(f"   Verdict: {'PASS' if mismatches == 0 else 'CHECK (some trades not opposite)'}")

    # Summary
    sides_ok = (len(closed_s) != len(closed_r)) or (len(closed_s) > 0 and opposite_sides == len(closed_s))
    all_ok = pnl_ok and count_ok and sides_ok
    print("\n--- Summary ---")
    if all_ok:
        print("Reverse scalping appears correctly opposite of scalping (same trade count, opposite sides, opposite PnL).")
    else:
        print("Reverse scalping is NOT fully opposite: check trade counts, position sides, or PnL.")
    print("=" * 60)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run scalping vs reverse scalping live backtest comparison")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Trading symbol (default: BTCUSDT)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Number of days of history (default: 5)")
    args = parser.parse_args()

    symbol = args.symbol
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=args.days)

    print("Scalping vs Reverse Scalping — Live backtest (Binance mainnet)")
    print(f"Symbol: {symbol}  Interval: {DEFAULT_INTERVAL}  Period: {start_time.date()} to {end_time.date()} ({args.days} days)")
    print("Fetching klines from Binance mainnet...")

    try:
        klines = await _fetch_historical_klines_mainnet(
            symbol=symbol,
            interval=DEFAULT_INTERVAL,
            start_time=start_time,
            end_time=end_time,
        )
    except Exception as e:
        print(f"Failed to fetch klines: {e}")
        sys.exit(1)

    print(f"Fetched {len(klines)} klines.")

    # Dummy client (not used when pre_fetched_klines is provided)
    mock_client = MagicMock(spec=BinanceClient)

    req_scalping = make_request(symbol, "scalping", start_time, end_time)
    req_reverse = make_request(symbol, "reverse_scalping", start_time, end_time)

    print("\nRunning Scalping backtest...")
    result_scalping = await run_backtest(req_scalping, mock_client, pre_fetched_klines=klines)
    print_result("Scalping", result_scalping)

    print("\nRunning Reverse Scalping backtest...")
    result_reverse = await run_backtest(req_reverse, mock_client, pre_fetched_klines=klines)
    print_result("Reverse Scalping", result_reverse)

    analyze_opposite(result_scalping, result_reverse)


if __name__ == "__main__":
    asyncio.run(main())
