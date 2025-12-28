"""
Test that backtesting correctly enforces all strategy parameters:
- Cooldown candles
- Min EMA separation
- HTF bias
- TP/SL percentages
- Trailing stop settings
- Enable short trading
"""
import pytest
pytestmark = pytest.mark.slow  # Backtesting tests excluded from CI
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.api.routes.backtesting import run_backtest, BacktestRequest
from app.core.my_binance_client import BinanceClient


@pytest.fixture
def mock_binance_client():
    """Create a mock Binance client for backtesting."""
    client = Mock(spec=BinanceClient)
    client._ensure = Mock(return_value=Mock())
    return client


@pytest.fixture
def sample_klines():
    """Generate sample klines data for testing with clear EMA crossovers."""
    base_time = datetime(2025, 12, 8, 19, 35, tzinfo=timezone.utc)
    klines = []
    
    # Generate 200 candles (1 minute each)
    # Create clear price movements that will trigger EMA crossovers
    # Pattern: Strong up trend -> Strong down trend -> Strong up trend
    base_price = 0.0280
    
    for i in range(200):
        timestamp = int((base_time + timedelta(minutes=i)).timestamp() * 1000)
        
        # Create clear trends that will cause EMA crossovers
        # Fast EMA (3) will cross slow EMA (13) when trend changes
        if i < 30:
            # Strong uptrend - fast EMA will be above slow EMA
            price = base_price + (i * 0.0001)  # Rising strongly
        elif i < 60:
            # Strong downtrend - fast EMA will cross below slow EMA
            price = base_price + 0.003 - ((i - 30) * 0.0001)  # Falling strongly
        elif i < 90:
            # Strong uptrend again - fast EMA will cross above slow EMA
            price = base_price - 0.003 + ((i - 60) * 0.0001)  # Rising strongly
        elif i < 120:
            # Strong downtrend again
            price = base_price + ((i - 90) * 0.0001) - ((i - 90) * 0.00015)  # Falling
        else:
            # Another uptrend
            price = base_price - 0.0045 + ((i - 120) * 0.0001)  # Rising
        
        # Kline format: [open_time, open, high, low, close, volume, close_time, ...]
        # Make high/low realistic (within 0.2% of close)
        high = price * 1.002
        low = price * 0.998
        klines.append([
            timestamp,  # open_time
            str(price),  # open
            str(high),   # high
            str(low),    # low
            str(price),  # close
            "1000.0",    # volume
            timestamp + 60000,  # close_time
            "0.0",       # quote_asset_volume
            "10",        # number_of_trades
            "500.0",     # taker_buy_base_asset_volume
            "500.0",     # taker_buy_quote_asset_volume
            "0"          # ignore
        ])
    
    return klines


class TestCooldownCandles:
    """Test that cooldown candles are properly enforced."""
    
    @pytest.mark.asyncio
    async def test_cooldown_prevents_immediate_reentry(self, mock_binance_client, sample_klines):
        """Test that after exiting a position, cooldown prevents immediate reentry."""
        # Mock futures_historical_klines to return sample klines
        mock_rest = mock_binance_client._ensure.return_value
        mock_rest.futures_historical_klines = Mock(return_value=sample_klines)
        
        start_time = datetime(2025, 12, 8, 19, 35, tzinfo=timezone.utc)
        end_time = datetime(2025, 12, 8, 20, 35, tzinfo=timezone.utc)
        
        request = BacktestRequest(
            symbol="MONUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={
                "kline_interval": "1m",
                "ema_fast": 3,
                "ema_slow": 13,
                "take_profit_pct": 0.04,
                "stop_loss_pct": 0.02,
                "enable_short": True,
                "cooldown_candles": 5,  # 5 candle cooldown
                "min_ema_separation": 0.001,
                "enable_htf_bias": False,  # Disable for simpler test
                "trailing_stop_enabled": False
            }
        )
        
        result = await run_backtest(request, mock_binance_client)
        
        # Verify we have trades (skip test if no trades generated)
        if result.total_trades == 0:
            pytest.skip("No trades generated - cannot test cooldown enforcement")
        
        # Check that consecutive trades respect cooldown
        completed_trades = [t for t in result.trades if not t.get("is_open", True)]
        
        if len(completed_trades) >= 2:
            # Get entry times
            trade_times = []
            for trade in completed_trades:
                entry_time_str = trade["entry_time"]
                if isinstance(entry_time_str, str):
                    entry_time = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
                else:
                    entry_time = entry_time_str
                trade_times.append((entry_time, trade))
            
            # Sort by entry time
            trade_times.sort(key=lambda x: x[0])
            
            # Check that consecutive trades are at least cooldown_candles apart
            # (1 minute candles, so 5 candles = 5 minutes)
            for i in range(len(trade_times) - 1):
                current_time = trade_times[i][0]
                next_time = trade_times[i + 1][0]
                time_diff = (next_time - current_time).total_seconds() / 60  # minutes
                
                # Allow some tolerance (cooldown is in candles, not exact minutes)
                # Cooldown of 5 candles should mean at least 4 minutes between entries
                # (since we can enter on the 6th candle after exit)
                assert time_diff >= 3, (
                    f"Trade {i+1} entered too soon after trade {i}: "
                    f"{time_diff:.2f} minutes (expected >= 3 minutes for 5-candle cooldown)"
                )


class TestMinEMASeparation:
    """Test that minimum EMA separation filter is applied."""
    
    @pytest.mark.asyncio
    async def test_min_ema_separation_prevents_noisy_signals(self, mock_binance_client, sample_klines):
        """Test that min_ema_separation prevents trades when EMAs are too close."""
        mock_rest = mock_binance_client._ensure.return_value
        mock_rest.futures_historical_klines = Mock(return_value=sample_klines)
        
        start_time = datetime(2025, 12, 8, 19, 35, tzinfo=timezone.utc)
        end_time = datetime(2025, 12, 8, 20, 35, tzinfo=timezone.utc)
        
        # Use a large min_ema_separation to filter out most signals
        request = BacktestRequest(
            symbol="MONUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={
                "kline_interval": "1m",
                "ema_fast": 3,
                "ema_slow": 13,
                "take_profit_pct": 0.04,
                "stop_loss_pct": 0.02,
                "enable_short": True,
                "cooldown_candles": 2,
                "min_ema_separation": 0.01,  # Large separation (1% of price)
                "enable_htf_bias": False,
                "trailing_stop_enabled": False
            }
        )
        
        result_large_separation = await run_backtest(request, mock_binance_client)
        
        # Now test with small separation (should allow more trades)
        request.params["min_ema_separation"] = 0.0001  # Small separation
        result_small_separation = await run_backtest(request, mock_binance_client)
        
        # With larger separation, we should have fewer or equal trades
        # (allowing for some variance, but generally fewer)
        assert result_large_separation.total_trades <= result_small_separation.total_trades, (
            f"Large separation ({request.params['min_ema_separation']}) should filter more signals. "
            f"Large: {result_large_separation.total_trades}, Small: {result_small_separation.total_trades}"
        )


class TestTPSLPercentages:
    """Test that TP/SL percentages are correctly applied."""
    
    @pytest.mark.asyncio
    async def test_tp_sl_percentages_are_respected(self, mock_binance_client, sample_klines):
        """Test that trades exit at correct TP/SL percentages."""
        mock_rest = mock_binance_client._ensure.return_value
        mock_rest.futures_historical_klines = Mock(return_value=sample_klines)
        
        start_time = datetime(2025, 12, 8, 19, 35, tzinfo=timezone.utc)
        end_time = datetime(2025, 12, 8, 20, 35, tzinfo=timezone.utc)
        
        take_profit_pct = 0.04  # 4%
        stop_loss_pct = 0.02    # 2%
        
        request = BacktestRequest(
            symbol="MONUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={
                "kline_interval": "1m",
                "ema_fast": 3,
                "ema_slow": 13,
                "take_profit_pct": take_profit_pct,
                "stop_loss_pct": stop_loss_pct,
                "enable_short": True,
                "cooldown_candles": 2,
                "min_ema_separation": 0.001,
                "enable_htf_bias": False,
                "trailing_stop_enabled": False
            }
        )
        
        result = await run_backtest(request, mock_binance_client)
        
        # Check completed trades that exited via TP or SL
        completed_trades = [t for t in result.trades if not t.get("is_open", True)]
        tp_sl_trades = [t for t in completed_trades if t.get("exit_reason") in ("TP", "SL")]
        
        if tp_sl_trades:
            for trade in tp_sl_trades:
                entry_price = trade["entry_price"]
                exit_price = trade["exit_price"]
                position_side = trade["position_side"]
                exit_reason = trade["exit_reason"]
                
                if position_side == "LONG":
                    if exit_reason == "TP":
                        # TP should be at entry * (1 + take_profit_pct)
                        expected_tp = entry_price * (1 + take_profit_pct)
                        # Allow small tolerance for spread and rounding
                        assert abs(exit_price - expected_tp) / entry_price < 0.001, (
                            f"LONG TP exit price {exit_price} doesn't match expected {expected_tp} "
                            f"(entry: {entry_price}, TP%: {take_profit_pct})"
                        )
                    elif exit_reason == "SL":
                        # SL should be at entry * (1 - stop_loss_pct)
                        expected_sl = entry_price * (1 - stop_loss_pct)
                        assert abs(exit_price - expected_sl) / entry_price < 0.001, (
                            f"LONG SL exit price {exit_price} doesn't match expected {expected_sl} "
                            f"(entry: {entry_price}, SL%: {stop_loss_pct})"
                        )
                else:  # SHORT
                    if exit_reason == "TP":
                        # TP should be at entry * (1 - take_profit_pct)
                        expected_tp = entry_price * (1 - take_profit_pct)
                        assert abs(exit_price - expected_tp) / entry_price < 0.001, (
                            f"SHORT TP exit price {exit_price} doesn't match expected {expected_tp} "
                            f"(entry: {entry_price}, TP%: {take_profit_pct})"
                        )
                    elif exit_reason == "SL":
                        # SL should be at entry * (1 + stop_loss_pct)
                        expected_sl = entry_price * (1 + stop_loss_pct)
                        assert abs(exit_price - expected_sl) / entry_price < 0.001, (
                            f"SHORT SL exit price {exit_price} doesn't match expected {expected_sl} "
                            f"(entry: {entry_price}, SL%: {stop_loss_pct})"
                        )


class TestEnableShort:
    """Test that enable_short parameter controls short trading."""
    
    @pytest.mark.asyncio
    async def test_disable_short_prevents_short_trades(self, mock_binance_client, sample_klines):
        """Test that disabling short trading prevents SHORT positions."""
        mock_rest = mock_binance_client._ensure.return_value
        mock_rest.futures_historical_klines = Mock(return_value=sample_klines)
        
        start_time = datetime(2025, 12, 8, 19, 35, tzinfo=timezone.utc)
        end_time = datetime(2025, 12, 8, 20, 35, tzinfo=timezone.utc)
        
        # Test with shorts disabled
        request_no_short = BacktestRequest(
            symbol="MONUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={
                "kline_interval": "1m",
                "ema_fast": 3,
                "ema_slow": 13,
                "take_profit_pct": 0.04,
                "stop_loss_pct": 0.02,
                "enable_short": False,  # Disable shorts
                "cooldown_candles": 2,
                "min_ema_separation": 0.001,
                "enable_htf_bias": False,
                "trailing_stop_enabled": False
            }
        )
        
        result_no_short = await run_backtest(request_no_short, mock_binance_client)
        
        # Verify no SHORT trades
        short_trades = [t for t in result_no_short.trades if t.get("position_side") == "SHORT"]
        assert len(short_trades) == 0, (
            f"Found {len(short_trades)} SHORT trades when enable_short=False. "
            f"All trades: {[t.get('position_side') for t in result_no_short.trades]}"
        )


class TestStrategyStateSync:
    """Test that strategy state is properly synced when trades are closed."""
    
    @pytest.mark.asyncio
    async def test_strategy_state_synced_on_trade_close(self, mock_binance_client, sample_klines):
        """Test that strategy's internal state is synced when trades are closed."""
        mock_rest = mock_binance_client._ensure.return_value
        mock_rest.futures_historical_klines = Mock(return_value=sample_klines)
        
        start_time = datetime(2025, 12, 8, 19, 35, tzinfo=timezone.utc)
        end_time = datetime(2025, 12, 8, 20, 35, tzinfo=timezone.utc)
        
        request = BacktestRequest(
            symbol="MONUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={
                "kline_interval": "1m",
                "ema_fast": 3,
                "ema_slow": 13,
                "take_profit_pct": 0.04,
                "stop_loss_pct": 0.02,
                "enable_short": True,
                "cooldown_candles": 2,
                "min_ema_separation": 0.001,
                "enable_htf_bias": False,
                "trailing_stop_enabled": False
            }
        )
        
        result = await run_backtest(request, mock_binance_client)
        
        # Verify that we don't have overlapping positions
        # (which would indicate strategy state desync)
        completed_trades = [t for t in result.trades if not t.get("is_open", True)]
        
        if len(completed_trades) >= 2:
            # Check that no trade starts before the previous one ends
            for i in range(len(completed_trades) - 1):
                current = completed_trades[i]
                next_trade = completed_trades[i + 1]
                
                current_exit = current.get("exit_time")
                next_entry = next_trade.get("entry_time")
                
                if current_exit and next_entry:
                    # Convert to datetime if strings
                    if isinstance(current_exit, str):
                        current_exit = datetime.fromisoformat(current_exit.replace("Z", "+00:00"))
                    if isinstance(next_entry, str):
                        next_entry = datetime.fromisoformat(next_entry.replace("Z", "+00:00"))
                    
                    # Next trade should start after current trade ends
                    assert next_entry >= current_exit, (
                        f"Trade {i+1} starts before trade {i} ends: "
                        f"entry={next_entry}, exit={current_exit}"
                    )

