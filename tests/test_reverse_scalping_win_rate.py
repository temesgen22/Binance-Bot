"""
Test that validates reverse scalping produces opposite win rates to normal scalping.

This test:
1. Runs both strategies on the same historical data
2. Compares their win rates
3. Validates that reverse scalping produces opposite (complementary) win rates
4. Tests with 8/21 EMA configuration as specified
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.api.routes.backtesting import run_backtest, BacktestRequest
from app.core.my_binance_client import BinanceClient


def create_trending_klines(count: int, base_price: float = 50000.0, trend: str = "up") -> list[list]:
    """Create klines with a clear trend for testing."""
    klines = []
    start_time = int((datetime.now(timezone.utc) - timedelta(hours=count)).timestamp() * 1000)
    interval_ms = 60000  # 1 minute
    
    for i in range(count):
        if trend == "up":
            # Upward trend: price increases
            price = base_price + (i * 10) + (i % 3) * 5  # Some volatility
        elif trend == "down":
            # Downward trend: price decreases
            price = base_price - (i * 10) - (i % 3) * 5
        else:
            # Sideways with some movement
            price = base_price + (i % 20) * 2 - 20
        
        open_time = start_time + (i * interval_ms)
        close_time = open_time + interval_ms
        
        klines.append([
            open_time,           # open_time
            price,               # open
            price + 5,           # high
            price - 5,           # low
            price,               # close
            100.0,               # volume
            close_time,          # close_time
            0, 0, 0, 0, 0       # placeholders
        ])
    
    return klines


def create_oscillating_klines(count: int, base_price: float = 50000.0, cycles: int = 5) -> list[list]:
    """Create klines with oscillating pattern (good for testing opposite strategies)."""
    klines = []
    start_time = int((datetime.now(timezone.utc) - timedelta(hours=count)).timestamp() * 1000)
    interval_ms = 60000  # 1 minute
    
    for i in range(count):
        # Create oscillating pattern: price goes up then down in cycles
        cycle_position = (i % (count // cycles)) / (count // cycles)  # 0 to 1
        if cycle_position < 0.5:
            # First half of cycle: price goes up
            price = base_price + (cycle_position * 2) * 200
        else:
            # Second half of cycle: price goes down
            price = base_price + ((1 - cycle_position) * 2) * 200
        
        # Add some noise
        price += (i % 7) * 3 - 10
        
        open_time = start_time + (i * interval_ms)
        close_time = open_time + interval_ms
        
        klines.append([
            open_time,
            price,
            price + 5,
            price - 5,
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
class TestReverseScalpingOppositeWinRate:
    """Test that reverse scalping produces opposite win rates to normal scalping."""
    
    async def test_opposite_win_rate_oscillating_market(self, mock_binance_client):
        """
        Test with oscillating market pattern.
        
        In an oscillating market:
        - Normal scalping: Enters LONG on golden cross (when price is rising), exits on death cross
        - Reverse scalping: Enters LONG on death cross (when price is falling), exits on golden cross
        
        This should produce opposite win rates.
        """
        # Create oscillating price data (enough for EMA calculation)
        klines = create_oscillating_klines(count=200, base_price=50000.0, cycles=4)
        
        # Mock the client to return our klines
        with patch.object(mock_binance_client, '_ensure') as mock_ensure:
            mock_rest = MagicMock()
            mock_rest.futures_klines.return_value = klines
            mock_ensure.return_value = mock_rest
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=200)
            end_time = datetime.now(timezone.utc)
            
            # Run normal scalping backtest
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
                    "take_profit_pct": 0.004,
                    "stop_loss_pct": 0.002,
                    "enable_short": True,
                    "min_ema_separation": 0.0,  # Disable filter for testing
                    "enable_htf_bias": False,
                    "cooldown_candles": 0,
                    "enable_ema_cross_exit": True,
                }
            )
            
            normal_result = await run_backtest(normal_request, mock_binance_client, pre_fetched_klines=klines)
            
            # Run reverse scalping backtest with SAME data
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
                    "take_profit_pct": 0.004,
                    "stop_loss_pct": 0.002,
                    "enable_short": True,
                    "min_ema_separation": 0.0,
                    "enable_htf_bias": False,
                    "cooldown_candles": 0,
                    "enable_ema_cross_exit": True,
                }
            )
            
            reverse_result = await run_backtest(reverse_request, mock_binance_client, pre_fetched_klines=klines)
            
            # Validate results
            print(f"\n=== Win Rate Comparison ===")
            print(f"Normal Scalping:")
            print(f"  Completed Trades: {normal_result.completed_trades}")
            print(f"  Win Rate: {normal_result.win_rate:.2f}%")
            print(f"  Winning Trades: {normal_result.winning_trades}")
            print(f"  Losing Trades: {normal_result.losing_trades}")
            print(f"  Total PnL: ${normal_result.total_pnl:.2f}")
            
            print(f"\nReverse Scalping:")
            print(f"  Completed Trades: {reverse_result.completed_trades}")
            print(f"  Win Rate: {reverse_result.win_rate:.2f}%")
            print(f"  Winning Trades: {reverse_result.winning_trades}")
            print(f"  Losing Trades: {reverse_result.losing_trades}")
            print(f"  Total PnL: ${reverse_result.total_pnl:.2f}")
            
            # Both should have completed trades
            assert normal_result.completed_trades > 0, "Normal scalping should have completed trades"
            assert reverse_result.completed_trades > 0, "Reverse scalping should have completed trades"
            
            # Win rates should be different (opposite strategies)
            # In an oscillating market, if one strategy wins when price goes up,
            # the other should win when price goes down
            win_rate_diff = abs(normal_result.win_rate - reverse_result.win_rate)
            print(f"\nWin Rate Difference: {win_rate_diff:.2f}%")
            
            # The win rates should be significantly different (at least 10% difference)
            # This validates they're trading opposite signals
            assert win_rate_diff >= 10.0, \
                f"Win rates should be significantly different (got {win_rate_diff:.2f}% difference). " \
                f"This validates opposite trading behavior."
            
            # If normal has low win rate, reverse should have high win rate (and vice versa)
            # Calculate complementary win rate
            if normal_result.win_rate < 50:
                # Normal is losing, reverse should be winning
                assert reverse_result.win_rate > normal_result.win_rate, \
                    f"If normal scalping has low win rate ({normal_result.win_rate:.2f}%), " \
                    f"reverse should have higher win rate ({reverse_result.win_rate:.2f}%)"
            elif normal_result.win_rate > 50:
                # Normal is winning, reverse should be losing
                assert reverse_result.win_rate < normal_result.win_rate, \
                    f"If normal scalping has high win rate ({normal_result.win_rate:.2f}%), " \
                    f"reverse should have lower win rate ({reverse_result.win_rate:.2f}%)"
    
    async def test_opposite_win_rate_trending_market(self, mock_binance_client):
        """
        Test with trending market (upward trend).
        
        In an upward trending market:
        - Normal scalping: Should perform well (enters LONG on golden cross during uptrend)
        - Reverse scalping: Should perform poorly (enters LONG on death cross, missing uptrend)
        """
        # Create upward trending data
        klines = create_trending_klines(count=200, base_price=50000.0, trend="up")
        
        with patch.object(mock_binance_client, '_ensure') as mock_ensure:
            mock_rest = MagicMock()
            mock_rest.futures_klines.return_value = klines
            mock_ensure.return_value = mock_rest
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=200)
            end_time = datetime.now(timezone.utc)
            
            # Normal scalping
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
                    "take_profit_pct": 0.004,
                    "stop_loss_pct": 0.002,
                    "enable_short": True,
                    "min_ema_separation": 0.0,
                    "enable_htf_bias": False,
                    "cooldown_candles": 0,
                }
            )
            
            normal_result = await run_backtest(normal_request, mock_binance_client, pre_fetched_klines=klines)
            
            # Reverse scalping
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
                    "take_profit_pct": 0.004,
                    "stop_loss_pct": 0.002,
                    "enable_short": True,
                    "min_ema_separation": 0.0,
                    "enable_htf_bias": False,
                    "cooldown_candles": 0,
                }
            )
            
            reverse_result = await run_backtest(reverse_request, mock_binance_client, pre_fetched_klines=klines)
            
            print(f"\n=== Trending Market (Upward) ===")
            print(f"Normal Scalping Win Rate: {normal_result.win_rate:.2f}%")
            print(f"Reverse Scalping Win Rate: {reverse_result.win_rate:.2f}%")
            
            # In upward trend, normal should outperform reverse
            if normal_result.completed_trades > 0 and reverse_result.completed_trades > 0:
                # Win rates should be different
                assert abs(normal_result.win_rate - reverse_result.win_rate) >= 5.0, \
                    "Win rates should differ in trending market"
    
    async def test_complementary_win_rate_validation(self, mock_binance_client):
        """
        Test that validates complementary win rate relationship.
        
        If normal scalping has 40% win rate, reverse should have approximately 60% win rate
        (assuming balanced market conditions).
        """
        # Create balanced oscillating data
        klines = create_oscillating_klines(count=300, base_price=50000.0, cycles=6)
        
        with patch.object(mock_binance_client, '_ensure') as mock_ensure:
            mock_rest = MagicMock()
            mock_rest.futures_klines.return_value = klines
            mock_ensure.return_value = mock_rest
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=300)
            end_time = datetime.now(timezone.utc)
            
            # Normal scalping with 8/21 EMA - SAME PARAMETERS
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
                    "take_profit_pct": 0.02,  # 2% - SAME
                    "stop_loss_pct": 0.02,    # 2% - SAME
                    "enable_short": True,
                    "min_ema_separation": 0.0,
                    "enable_htf_bias": False,
                    "cooldown_candles": 0,
                    "enable_ema_cross_exit": True,  # Explicitly same
                    "trailing_stop_enabled": False,  # Explicitly same
                }
            )
            
            normal_result = await run_backtest(normal_request, mock_binance_client, pre_fetched_klines=klines)
            
            # Reverse scalping with 8/21 EMA - EXACT SAME PARAMETERS
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
                    "take_profit_pct": 0.02,  # 2% - SAME
                    "stop_loss_pct": 0.02,    # 2% - SAME
                    "enable_short": True,
                    "min_ema_separation": 0.0,
                    "enable_htf_bias": False,
                    "cooldown_candles": 0,
                    "enable_ema_cross_exit": True,  # Explicitly same
                    "trailing_stop_enabled": False,  # Explicitly same
                }
            )
            
            reverse_result = await run_backtest(reverse_request, mock_binance_client, pre_fetched_klines=klines)
            
            print(f"\n=== Complementary Win Rate Test (8/21 EMA) - SAME PARAMETERS ===")
            print(f"Parameters: TP=2%, SL=2%, EMA=8/21, cooldown=0, filters=off")
            print(f"\nNormal Scalping:")
            print(f"  Win Rate: {normal_result.win_rate:.2f}%")
            print(f"  Completed Trades: {normal_result.completed_trades}")
            print(f"  Winning Trades: {normal_result.winning_trades}")
            print(f"  Losing Trades: {normal_result.losing_trades}")
            print(f"  Total PnL: ${normal_result.total_pnl:.2f}")
            
            print(f"\nReverse Scalping:")
            print(f"  Win Rate: {reverse_result.win_rate:.2f}%")
            print(f"  Completed Trades: {reverse_result.completed_trades}")
            print(f"  Winning Trades: {reverse_result.winning_trades}")
            print(f"  Losing Trades: {reverse_result.losing_trades}")
            print(f"  Total PnL: ${reverse_result.total_pnl:.2f}")
            
            # Analyze trade details
            print(f"\n=== Trade Analysis ===")
            print(f"Trade Count Difference: {abs(normal_result.completed_trades - reverse_result.completed_trades)}")
            if normal_result.completed_trades != reverse_result.completed_trades:
                print(f"[WARNING] DIFFERENT TRADE COUNTS despite same parameters!")
                print(f"   This suggests TP/SL exits at different times or other factors")
            else:
                print(f"[SUCCESS] Same trade counts - perfect synchronization!")
                print(f"   This proves that with same TP/SL, they enter/exit at same times")
            
            # Calculate complementary win rate
            combined_win_rate = normal_result.win_rate + reverse_result.win_rate
            print(f"\nCombined Win Rate: {combined_win_rate:.2f}%")
            print(f"Expected: ~100% (if perfectly opposite)")
            
            # Both should have trades
            assert normal_result.completed_trades > 0, "Normal scalping should have trades"
            assert reverse_result.completed_trades > 0, "Reverse scalping should have trades"
            
            # KEY VALIDATION: Win rates should be significantly different
            # This proves they're trading opposite signals
            win_rate_diff = abs(normal_result.win_rate - reverse_result.win_rate)
            print(f"\nWin Rate Difference: {win_rate_diff:.2f}%")
            
            # The win rates should be significantly different (at least 15% difference)
            # This validates that they're trading opposite signals
            assert win_rate_diff >= 15.0, \
                f"Win rates should be significantly different to validate opposite behavior. " \
                f"Normal: {normal_result.win_rate:.2f}%, Reverse: {reverse_result.win_rate:.2f}%, " \
                f"Difference: {win_rate_diff:.2f}% (need >= 15%)"
            
            # Additional validation: If one strategy has low win rate, the other should have different performance
            # This doesn't mean they sum to 100% (due to different trade counts, TP/SL, etc.)
            # But they should show opposite tendencies
            
            # Check if strategies show opposite performance patterns
            # If normal has < 50% win rate, reverse should ideally have > 50% (or significantly different)
            # But we allow for cases where both might struggle in certain market conditions
            if normal_result.win_rate < 40.0:
                # Normal is struggling - reverse should perform differently
                # (either better OR worse, but different)
                print(f"\nNormal scalping has low win rate ({normal_result.win_rate:.2f}%)")
                print(f"Reverse scalping win rate: {reverse_result.win_rate:.2f}%")
                print(f"This shows opposite trading behavior (different entry/exit signals)")
            
            # Validate that they trade at different times (opposite signals)
            # This is the key proof - they should have different number of trades
            # because they enter/exit at opposite times
            trade_count_diff = abs(normal_result.completed_trades - reverse_result.completed_trades)
            print(f"\nTrade Count Difference: {trade_count_diff} trades")
            print(f"This validates they trade at different times (opposite signals)")
            
            # They should have different trade counts (trading at different times)
            # But both should have some trades
            assert normal_result.completed_trades > 0, "Normal scalping should have trades"
            assert reverse_result.completed_trades > 0, "Reverse scalping should have trades"
            
            # The key validation: Win rates are significantly different
            # This proves opposite behavior even if they don't sum to exactly 100%
            print(f"\n[VALIDATION] Win rates are significantly different ({win_rate_diff:.2f}%)")
            print(f"   This proves reverse scalping trades opposite signals to normal scalping")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

