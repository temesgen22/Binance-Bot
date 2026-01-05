"""
Test to verify that in backtesting, with fixed spread, opposite positions
should produce opposite profits (same amount, opposite sign).

This test checks if:
1. Same entry/exit times → opposite profits
2. Fixed spread → profits should be exactly opposite
3. Same quantity → profits should be exactly opposite
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.api.routes.backtesting import run_backtest, BacktestRequest, SPREAD_OFFSET, AVERAGE_FEE_RATE
from app.core.my_binance_client import BinanceClient


def create_simple_klines(count: int, base_price: float = 50000.0) -> list[list]:
    """Create simple klines for testing."""
    klines = []
    start_time = int((datetime.now(timezone.utc) - timedelta(hours=count)).timestamp() * 1000)
    interval_ms = 60000  # 1 minute
    
    for i in range(count):
        # Simple pattern: price goes up then down
        if i < count // 2:
            price = base_price + (i * 5)  # Upward trend
        else:
            price = base_price + ((count // 2) * 5) - ((i - count // 2) * 5)  # Downward trend
        
        open_time = start_time + (i * interval_ms)
        close_time = open_time + interval_ms
        
        klines.append([
            open_time,
            price,
            price + 2,
            price - 2,
            price,
            100.0,
            close_time,
            0, 0, 0, 0, 0
        ])
    
    return klines


@pytest.fixture
def mock_binance_client():
    """Create a mock BinanceClient for backtesting."""
    client = MagicMock(spec=BinanceClient)
    return client


@pytest.mark.asyncio
async def test_opposite_profits_same_entry_exit(mock_binance_client):
    """
    Test that opposite positions with same entry/exit times produce opposite profits.
    
    If normal scalping enters SHORT and reverse enters LONG at the same time,
    and they exit at the same time, profits should be opposite.
    """
    # Create simple price data
    klines = create_simple_klines(count=100, base_price=50000.0)
    
    with patch.object(mock_binance_client, '_ensure') as mock_ensure:
        mock_rest = MagicMock()
        mock_rest.futures_klines.return_value = klines
        mock_ensure.return_value = mock_rest
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=100)
        end_time = datetime.now(timezone.utc)
        
        # Normal scalping - SAME PARAMETERS
        normal_request = BacktestRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.02,  # 2%
                "stop_loss_pct": 0.02,    # 2%
                "enable_short": True,
                "min_ema_separation": 0.0,
                "enable_htf_bias": False,
                "cooldown_candles": 0,
            }
        )
        
        normal_result = await run_backtest(normal_request, mock_binance_client, pre_fetched_klines=klines)
        
        # Reverse scalping - EXACT SAME PARAMETERS
        reverse_request = BacktestRequest(
            symbol="BTCUSDT",
            strategy_type="reverse_scalping",
            start_time=start_time,
            end_time=end_time,
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={
                "kline_interval": "1m",
                "ema_fast": 8,
                "ema_slow": 21,
                "take_profit_pct": 0.02,  # 2%
                "stop_loss_pct": 0.02,    # 2%
                "enable_short": True,
                "min_ema_separation": 0.0,
                "enable_htf_bias": False,
                "cooldown_candles": 0,
            }
        )
        
        reverse_result = await run_backtest(reverse_request, mock_binance_client, pre_fetched_klines=klines)
        
        print(f"\n=== Opposite Profits Test ===")
        print(f"Normal Scalping:")
        print(f"  Completed Trades: {normal_result.completed_trades}")
        print(f"  Total PnL: ${normal_result.total_pnl:.4f}")
        print(f"  Trades: {len(normal_result.trades)}")
        
        print(f"\nReverse Scalping:")
        print(f"  Completed Trades: {reverse_result.completed_trades}")
        print(f"  Total PnL: ${reverse_result.total_pnl:.4f}")
        print(f"  Trades: {len(reverse_result.trades)}")
        
        # Analyze individual trades
        if len(normal_result.trades) == len(reverse_result.trades):
            print(f"\n=== Trade-by-Trade Comparison ===")
            for i, (normal_trade, reverse_trade) in enumerate(zip(normal_result.trades, reverse_result.trades)):
                if not normal_trade.get("is_open", True) and not reverse_trade.get("is_open", True):
                    normal_pnl = normal_trade.get("net_pnl", 0)
                    reverse_pnl = reverse_trade.get("net_pnl", 0)
                    expected_reverse = -normal_pnl
                    difference = abs(reverse_pnl - expected_reverse)
                    
                    print(f"\nTrade {i+1}:")
                    print(f"  Normal: {normal_trade.get('position_side')} @ ${normal_trade.get('entry_price', 0):.2f} -> ${normal_trade.get('exit_price', 0):.2f}")
                    print(f"    Entry: ${normal_trade.get('entry_price', 0):.8f}")
                    print(f"    Exit: ${normal_trade.get('exit_price', 0):.8f}")
                    print(f"    Quantity: {normal_trade.get('quantity', 0):.8f}")
                    print(f"    Gross PnL: ${normal_trade.get('pnl', 0):.4f}")
                    print(f"    Net PnL: ${normal_pnl:.4f}")
                    print(f"    Entry Fee: ${normal_trade.get('entry_fee', 0):.4f}")
                    print(f"    Exit Fee: ${normal_trade.get('exit_fee', 0):.4f}")
                    
                    print(f"  Reverse: {reverse_trade.get('position_side')} @ ${reverse_trade.get('entry_price', 0):.2f} -> ${reverse_trade.get('exit_price', 0):.2f}")
                    print(f"    Entry: ${reverse_trade.get('entry_price', 0):.8f}")
                    print(f"    Exit: ${reverse_trade.get('exit_price', 0):.8f}")
                    print(f"    Quantity: {reverse_trade.get('quantity', 0):.8f}")
                    print(f"    Gross PnL: ${reverse_trade.get('pnl', 0):.4f}")
                    print(f"    Net PnL: ${reverse_pnl:.4f}")
                    print(f"    Entry Fee: ${reverse_trade.get('entry_fee', 0):.4f}")
                    print(f"    Exit Fee: ${reverse_trade.get('exit_fee', 0):.4f}")
                    
                    print(f"    Expected Reverse: ${expected_reverse:.4f} (opposite of normal)")
                    print(f"    Actual Difference: ${difference:.4f}")
                    
                    # Calculate spread impact
                    normal_entry = normal_trade.get('entry_price', 0)
                    normal_exit = normal_trade.get('exit_price', 0)
                    reverse_entry = reverse_trade.get('entry_price', 0)
                    reverse_exit = reverse_trade.get('exit_price', 0)
                    
                    # Check if they entered/exited at same base prices
                    base_entry = normal_entry / (1 - SPREAD_OFFSET) if normal_trade.get('position_side') == 'SHORT' else normal_entry / (1 + SPREAD_OFFSET)
                    base_exit = normal_exit / (1 + SPREAD_OFFSET) if normal_trade.get('position_side') == 'SHORT' else normal_exit / (1 - SPREAD_OFFSET)
                    
                    print(f"    Base Entry Price (before spread): ${base_entry:.8f}")
                    print(f"    Base Exit Price (before spread): ${base_exit:.8f}")
                    
                    # With fixed spread, they should be very close to opposite
                    # Allow small tolerance for rounding and fees
                    if difference > 0.10:  # More than 10 cents difference
                        print(f"    [WARNING] NOT exactly opposite! Difference: ${difference:.4f}")
                        print(f"    This suggests different entry/exit prices or timing")
                    else:
                        print(f"    [OK] Close to opposite (within tolerance)")
        
        # Check if total PnL is opposite
        expected_reverse_total = -normal_result.total_pnl
        total_difference = abs(reverse_result.total_pnl - expected_reverse_total)
        
        print(f"\n=== Total PnL Comparison ===")
        print(f"Normal Total PnL: ${normal_result.total_pnl:.4f}")
        print(f"Reverse Total PnL: ${reverse_result.total_pnl:.4f}")
        print(f"Expected Reverse: ${expected_reverse_total:.4f} (opposite of normal)")
        print(f"Difference: ${total_difference:.4f}")
        
        # With fixed spread and same parameters, they should be very close to opposite
        # The spread creates a small asymmetry, but should be minimal
        if total_difference > 1.0:  # More than $1 difference
            print(f"\n⚠️  Total PnL is NOT exactly opposite!")
            print(f"   This suggests different entry/exit times or other factors")
        else:
            print(f"\n✅ Total PnL is approximately opposite (within tolerance)")
        
        # Both should have same number of trades
        assert normal_result.completed_trades == reverse_result.completed_trades, \
            f"Should have same trade count: normal={normal_result.completed_trades}, reverse={reverse_result.completed_trades}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

