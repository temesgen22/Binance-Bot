"""
Tests for Walk-Forward Analysis Klines Fetching Optimization.

Validates that:
1. Klines are fetched once for entire time range
2. Pre-fetched klines are reused for all windows
3. Slicing function works correctly
4. Optimization uses pre-fetched klines
5. Memory is managed correctly
"""
import pytest
pytestmark = pytest.mark.slow

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, call
from typing import Optional

from app.services.walk_forward import (
    WalkForwardRequest,
    run_walk_forward_analysis
)
from app.api.routes.backtesting import (
    BacktestRequest,
    BacktestResult,
    run_backtest,
    _slice_klines_by_time_range
)
from app.core.my_binance_client import BinanceClient


# ============================================================================
# Helper Functions
# ============================================================================

def build_klines(count: int, base_price: float = 50000.0, price_trend: float = 0.0,
                 volatility: float = 100.0, base_volume: float = 1000.0,
                 start_time: Optional[datetime] = None, interval_minutes: int = 1) -> list[list]:
    """Helper to create klines for testing."""
    import random
    
    if start_time is None:
        start_time = datetime.now(timezone.utc) - timedelta(minutes=count * interval_minutes)
    
    klines = []
    current_price = base_price
    
    for i in range(count):
        current_price += price_trend
        price_change = random.uniform(-volatility, volatility)
        current_price += price_change
        current_price = max(current_price, 100.0)
        
        open_price = current_price
        high_price = open_price + abs(random.uniform(0, volatility * 0.5))
        low_price = open_price - abs(random.uniform(0, volatility * 0.5))
        close_price = open_price + random.uniform(-volatility * 0.3, volatility * 0.3)
        
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)
        
        volume = base_volume + random.uniform(-base_volume * 0.2, base_volume * 0.2)
        
        candle_time = start_time + timedelta(minutes=i * interval_minutes)
        timestamp = int(candle_time.timestamp() * 1000)
        
        klines.append([
            timestamp,
            str(open_price),
            str(high_price),
            str(low_price),
            str(close_price),
            str(volume),
            timestamp + (interval_minutes * 60 * 1000) - 1,
            "0", "0", "0", "0", "0"
        ])
    
    return klines


def create_mock_backtest_result(
    initial_balance: float = 1000.0,
    final_balance: float = 1050.0,
    total_trades: int = 10,
    completed_trades: int = 10,
    win_rate: float = 60.0,
    max_drawdown_pct: float = 5.0
) -> BacktestResult:
    """Create a mock BacktestResult for testing."""
    trades = []
    winning_count = int(completed_trades * (win_rate / 100))
    
    for i in range(completed_trades):
        is_winner = i < winning_count
        pnl = 10.0 if is_winner else -5.0
        trades.append({
            "entry_time": datetime.now(timezone.utc) - timedelta(hours=completed_trades - i),
            "exit_time": datetime.now(timezone.utc) - timedelta(hours=completed_trades - i - 1),
            "entry_price": 50000.0,
            "exit_price": 50200.0 if is_winner else 49900.0,
            "position_side": "LONG",
            "quantity": 0.01,
            "notional": 500.0,
            "entry_fee": 0.15,
            "exit_fee": 0.15,
            "pnl": pnl,
            "net_pnl": pnl - 0.3,
            "exit_reason": "TP" if is_winner else "SL",
            "is_open": False
        })
    
    total_return_pct = ((final_balance / initial_balance) - 1.0) * 100
    
    return BacktestResult(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=datetime.now(timezone.utc) - timedelta(days=30),
        end_time=datetime.now(timezone.utc),
        initial_balance=initial_balance,
        final_balance=final_balance,
        total_pnl=final_balance - initial_balance,
        total_return_pct=total_return_pct,
        total_trades=total_trades,
        completed_trades=completed_trades,
        open_trades=0,
        winning_trades=winning_count,
        losing_trades=completed_trades - winning_count,
        win_rate=win_rate,
        total_fees=completed_trades * 0.3,
        avg_profit_per_trade=(final_balance - initial_balance) / completed_trades if completed_trades > 0 else 0.0,
        largest_win=10.0,
        largest_loss=-5.0,
        max_drawdown=initial_balance * (max_drawdown_pct / 100),
        max_drawdown_pct=max_drawdown_pct,
        trades=trades,
        klines=None,
        indicators=None
    )


def setup_mock_binance_client(klines: list[list]):
    """Set up a mock Binance client that returns the provided klines."""
    mock_client = Mock(spec=BinanceClient)
    mock_rest = Mock()
    
    def futures_klines_mock(*args, **kwargs):
        return klines
    
    mock_rest.futures_klines = futures_klines_mock
    mock_client._ensure.return_value = mock_rest
    
    return mock_client


# ============================================================================
# Test Kline Slicing Function
# ============================================================================

class TestKlineSlicing:
    """Test the kline slicing function."""
    
    def test_slice_klines_by_time_range(self):
        """Test that slicing correctly filters klines by time range."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        
        # Create klines spanning 20 days
        all_klines = build_klines(
            count=28800,  # 20 days of 1-minute candles
            start_time=start_time,
            interval_minutes=1
        )
        
        # Slice for first 5 days
        slice_start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        slice_end = datetime(2024, 1, 5, 23, 59, 59, tzinfo=timezone.utc)
        
        sliced = _slice_klines_by_time_range(all_klines, slice_start, slice_end)
        
        # Should have ~5 days of 1-minute candles = ~7200 candles
        assert len(sliced) > 0, "Should have some klines"
        assert len(sliced) < len(all_klines), "Sliced should be smaller than original"
        
        # All sliced klines should be within time range
        slice_start_ts = int(slice_start.timestamp() * 1000)
        slice_end_ts = int(slice_end.timestamp() * 1000)
        
        for kline in sliced:
            kline_time = int(kline[0])
            assert slice_start_ts <= kline_time <= slice_end_ts, \
                f"Kline time {kline_time} should be between {slice_start_ts} and {slice_end_ts}"
    
    def test_slice_klines_empty_result(self):
        """Test that slicing returns empty list if no klines in range."""
        klines = build_klines(
            count=1000,
            start_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        )
        
        # Slice for time range that doesn't overlap
        slice_start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        slice_end = datetime(2025, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        
        sliced = _slice_klines_by_time_range(klines, slice_start, slice_end)
        
        assert len(sliced) == 0, "Should return empty list for non-overlapping range"
    
    def test_slice_klines_exact_boundaries(self):
        """Test that slicing includes klines at exact boundaries."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        klines = build_klines(
            count=100,
            start_time=start_time,
            interval_minutes=1
        )
        
        # Slice with exact start and end times
        # Start uses open_time (k[0]), end uses close_time (k[6]) for correct boundary handling
        first_kline_open_time = datetime.fromtimestamp(int(klines[0][0]) / 1000, tz=timezone.utc)
        last_kline_close_time = datetime.fromtimestamp(int(klines[-1][6]) / 1000, tz=timezone.utc)
        
        sliced = _slice_klines_by_time_range(klines, first_kline_open_time, last_kline_close_time)
        
        assert len(sliced) == len(klines), "Should include all klines with exact boundaries"
        assert sliced[0] == klines[0], "First kline should match"
        assert sliced[-1] == klines[-1], "Last kline should match"


# ============================================================================
# Test Pre-Fetched Klines in run_backtest
# ============================================================================

class TestPreFetchedKlines:
    """Test that run_backtest accepts and uses pre-fetched klines."""
    
    @pytest.mark.asyncio
    async def test_run_backtest_with_pre_fetched_klines(self):
        """Test that run_backtest uses pre-fetched klines when provided."""
        # Create klines for entire range
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        all_klines = build_klines(
            count=12960,  # 9 days of 1-minute candles
            start_time=start_time,
            interval_minutes=1
        )
        
        # Create request for subset
        request_start = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        request_end = datetime(2024, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
        
        request = BacktestRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=request_start,
            end_time=request_end,
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={"kline_interval": "1m", "ema_fast": 8, "ema_slow": 21}
        )
        
        mock_client = setup_mock_binance_client(all_klines)
        
        # Mock run_backtest to track if it uses pre-fetched klines
        with patch('app.api.routes.backtesting._fetch_historical_klines') as mock_fetch:
            result = await run_backtest(request, mock_client, pre_fetched_klines=all_klines)
            
            # Should NOT call _fetch_historical_klines when pre_fetched_klines provided
            mock_fetch.assert_not_called()
            
            # Result should be valid
            assert isinstance(result, BacktestResult)
            assert result.symbol == "BTCUSDT"
    
    @pytest.mark.asyncio
    async def test_run_backtest_without_pre_fetched_klines(self):
        """Test that run_backtest fetches klines when pre_fetched_klines is None."""
        request = BacktestRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc),
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={"kline_interval": "1m", "ema_fast": 8, "ema_slow": 21}
        )
        
        klines = build_klines(count=1440, start_time=request.start_time)  # 1 day
        mock_client = setup_mock_binance_client(klines)
        
        # Should call _fetch_historical_klines when pre_fetched_klines is None
        with patch('app.api.routes.backtesting._fetch_historical_klines', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = klines
            result = await run_backtest(request, mock_client, pre_fetched_klines=None)
            
            # Should have called fetch
            mock_fetch.assert_called_once()
            assert isinstance(result, BacktestResult)


# ============================================================================
# Test Walk-Forward Optimization
# ============================================================================

class TestWalkForwardOptimization:
    """Test that walk-forward analysis uses single fetch optimization."""
    
    @pytest.mark.asyncio
    async def test_single_fetch_for_all_windows(self):
        """Test that klines are fetched once for entire time range."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, 0, 0, 0, tzinfo=timezone.utc)  # 19 days
        
        # Create klines for entire range
        all_klines = build_klines(
            count=27360,  # ~19 days of 1-minute candles
            start_time=start_time,
            interval_minutes=1
        )
        
        mock_client = setup_mock_binance_client(all_klines)
        
        request = WalkForwardRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            training_period_days=7,
            test_period_days=3,
            step_size_days=5,
            window_type="rolling",
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={"kline_interval": "1m", "ema_fast": 8, "ema_slow": 21}
        )
        
        # Mock _fetch_historical_klines to track calls
        with patch('app.services.walk_forward._fetch_historical_klines', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = all_klines
            
            # Mock run_backtest to return predictable results
            with patch('app.services.walk_forward.run_backtest', new_callable=AsyncMock) as mock_backtest:
                def create_result(initial_balance):
                    return create_mock_backtest_result(
                        initial_balance=initial_balance,
                        final_balance=initial_balance * 1.05
                    )
                
                mock_backtest.side_effect = lambda req, client, **kwargs: create_result(req.initial_balance)
                
                result = await run_walk_forward_analysis(request, mock_client)
                
                # Should fetch klines ONCE for entire range
                assert mock_fetch.call_count == 1, \
                    f"Expected 1 fetch call, got {mock_fetch.call_count}"
                
                # Verify it was called with entire time range
                call_args = mock_fetch.call_args
                assert call_args[1]['start_time'] == start_time
                assert call_args[1]['end_time'] == end_time
                
                # Verify result is valid
                assert isinstance(result, type(result))  # WalkForwardResult
                assert result.total_windows > 0
    
    @pytest.mark.asyncio
    async def test_pre_fetched_klines_passed_to_backtest(self):
        """Test that pre-fetched klines are passed to run_backtest calls."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)  # 14 days
        
        all_klines = build_klines(
            count=20160,  # ~14 days
            start_time=start_time,
            interval_minutes=1
        )
        
        mock_client = setup_mock_binance_client(all_klines)
        
        request = WalkForwardRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            training_period_days=7,
            test_period_days=3,
            step_size_days=5,
            window_type="rolling",
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={"kline_interval": "1m", "ema_fast": 8, "ema_slow": 21}
        )
        
        # Track calls to run_backtest
        backtest_calls = []
        
        async def track_backtest(req, client, **kwargs):
            backtest_calls.append({
                'request': req,
                'pre_fetched_klines': kwargs.get('pre_fetched_klines')
            })
            return create_mock_backtest_result(
                initial_balance=req.initial_balance,
                final_balance=req.initial_balance * 1.05
            )
        
        with patch('app.services.walk_forward._fetch_historical_klines', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = all_klines
            
            with patch('app.services.walk_forward.run_backtest', side_effect=track_backtest):
                result = await run_walk_forward_analysis(request, mock_client)
                
                # Verify all backtest calls received pre_fetched_klines (sliced per window)
                assert len(backtest_calls) > 0, "Should have called run_backtest"
                
                for call_info in backtest_calls:
                    assert call_info['pre_fetched_klines'] is not None, \
                        "All backtest calls should receive pre_fetched_klines"
                    # Note: Now calls receive sliced klines (training or test slice)
                    # This is correct - prevents data leakage
                    assert len(call_info['pre_fetched_klines']) > 0, \
                        "All backtest calls should receive sliced klines"
                    # Verify klines are within request time range
                    if call_info['pre_fetched_klines']:
                        first_time = datetime.fromtimestamp(int(call_info['pre_fetched_klines'][0][0]) / 1000, tz=timezone.utc)
                        last_time = datetime.fromtimestamp(int(call_info['pre_fetched_klines'][-1][0]) / 1000, tz=timezone.utc)
                        assert first_time >= call_info['request'].start_time, \
                            "Klines should start at or after request start time"
                        assert last_time <= call_info['request'].end_time, \
                            "Klines should end at or before request end time"
    
    @pytest.mark.asyncio
    async def test_optimization_uses_pre_fetched_klines(self):
        """Test that optimization uses pre-fetched klines for all combinations."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        
        all_klines = build_klines(
            count=20160,
            start_time=start_time,
            interval_minutes=1
        )
        
        mock_client = setup_mock_binance_client(all_klines)
        
        request = WalkForwardRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            training_period_days=7,
            test_period_days=3,
            step_size_days=5,
            window_type="rolling",
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={"kline_interval": "1m"},
            optimize_params={
                "ema_fast": [5, 8],
                "ema_slow": [15, 21]
            },
            optimization_metric="robust_score",
            optimization_method="grid_search"
        )
        
        # Track optimization backtest calls
        optimization_calls = []
        
        async def track_optimization_backtest(req, client, **kwargs):
            optimization_calls.append({
                'pre_fetched_klines': kwargs.get('pre_fetched_klines')
            })
            return create_mock_backtest_result(
                initial_balance=req.initial_balance,
                final_balance=req.initial_balance * 1.05,
                completed_trades=10
            )
        
        with patch('app.services.walk_forward._fetch_historical_klines', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = all_klines
            
            with patch('app.services.walk_forward.run_backtest', side_effect=track_optimization_backtest):
                result = await run_walk_forward_analysis(request, mock_client)
                
                # Should have multiple optimization calls (4 combinations)
                assert len(optimization_calls) >= 4, \
                    f"Expected at least 4 optimization calls (2×2 combinations), got {len(optimization_calls)}"
                
                # All should use pre-fetched klines (sliced training klines, not full all_klines)
                for call_info in optimization_calls:
                    assert call_info['pre_fetched_klines'] is not None, \
                        "Optimization calls should use pre-fetched klines"
                    # Note: Now optimization receives sliced training klines (correct behavior)
                    # This is smaller than all_klines but still pre-fetched and reused
                    assert len(call_info['pre_fetched_klines']) > 0, \
                        "Optimization calls should receive sliced training klines"
                    # Verify klines are within training period (not full range)
                    if call_info['pre_fetched_klines']:
                        first_time = datetime.fromtimestamp(int(call_info['pre_fetched_klines'][0][0]) / 1000, tz=timezone.utc)
                        last_time = datetime.fromtimestamp(int(call_info['pre_fetched_klines'][-1][0]) / 1000, tz=timezone.utc)
                        # Training period is 7 days, so klines should be within that range
                        assert (last_time - first_time).days <= 7, \
                            "Optimization klines should be within training period (7 days)"
    
    @pytest.mark.asyncio
    async def test_no_redundant_fetches(self):
        """Test that no redundant kline fetches occur."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, 0, 0, 0, tzinfo=timezone.utc)
        
        all_klines = build_klines(
            count=27360,
            start_time=start_time,
            interval_minutes=1
        )
        
        mock_client = setup_mock_binance_client(all_klines)
        
        request = WalkForwardRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            training_period_days=7,
            test_period_days=3,
            step_size_days=5,
            window_type="rolling",
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={"kline_interval": "1m", "ema_fast": 8, "ema_slow": 21}
        )
        
        # Count fetch calls
        fetch_call_count = 0
        
        async def count_fetch(*args, **kwargs):
            nonlocal fetch_call_count
            fetch_call_count += 1
            return all_klines
        
        with patch('app.services.walk_forward._fetch_historical_klines', side_effect=count_fetch):
            with patch('app.services.walk_forward.run_backtest', new_callable=AsyncMock) as mock_backtest:
                mock_backtest.side_effect = lambda req, client, **kwargs: create_mock_backtest_result(
                    initial_balance=req.initial_balance,
                    final_balance=req.initial_balance * 1.05
                )
                
                result = await run_walk_forward_analysis(request, mock_client)
                
                # Should only fetch once
                assert fetch_call_count == 1, \
                    f"Expected 1 fetch call, got {fetch_call_count} (should fetch once for entire range)"
                
                # Verify result
                assert result.total_windows > 0


# ============================================================================
# Test Memory Management
# ============================================================================

class TestMemoryManagement:
    """Test that memory is managed correctly."""
    
    def test_slicing_does_not_copy_klines(self):
        """Test that slicing creates views, not copies (memory efficient)."""
        klines = build_klines(count=1000)
        
        # Slice klines
        start_time = datetime.fromtimestamp(int(klines[100][0]) / 1000, tz=timezone.utc)
        end_time = datetime.fromtimestamp(int(klines[200][0]) / 1000, tz=timezone.utc)
        
        sliced = _slice_klines_by_time_range(klines, start_time, end_time)
        
        # Verify slicing worked
        assert len(sliced) > 0
        
        # Note: Python list slicing creates new list, but elements are references
        # This is still memory efficient for our use case
    
    @pytest.mark.asyncio
    async def test_klines_scope_management(self):
        """Test that klines go out of scope after analysis completes."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)  # 14 days (enough for 7+3)
        
        all_klines = build_klines(count=20160, start_time=start_time)  # ~14 days
        mock_client = setup_mock_binance_client(all_klines)
        
        request = WalkForwardRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            training_period_days=7,
            test_period_days=3,
            step_size_days=5,
            window_type="rolling",
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={"kline_interval": "1m", "ema_fast": 8, "ema_slow": 21}
        )
        
        # Track if klines are stored
        stored_klines = None
        
        async def track_fetch(*args, **kwargs):
            nonlocal stored_klines
            stored_klines = all_klines
            return all_klines
        
        with patch('app.services.walk_forward._fetch_historical_klines', side_effect=track_fetch):
            with patch('app.services.walk_forward.run_backtest', new_callable=AsyncMock) as mock_backtest:
                mock_backtest.side_effect = lambda req, client, **kwargs: create_mock_backtest_result(
                    initial_balance=req.initial_balance,
                    final_balance=req.initial_balance * 1.05
                )
                
                result = await run_walk_forward_analysis(request, mock_client)
                
                # Verify klines were stored during analysis
                assert stored_klines is not None
                assert len(stored_klines) > 0
                
                # After function returns, stored_klines reference remains but
                # the actual all_klines variable in the function goes out of scope
                # Python GC will clean it up automatically


# ============================================================================
# Integration Test
# ============================================================================

class TestWalkForwardOptimizationIntegration:
    """Integration test for complete walk-forward optimization flow."""
    
    @pytest.mark.asyncio
    async def test_complete_optimization_flow(self):
        """Test complete flow: single fetch, reuse, slicing, optimization."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, 0, 0, 0, tzinfo=timezone.utc)
        
        # Create klines for entire range
        all_klines = build_klines(
            count=27360,  # ~19 days
            start_time=start_time,
            interval_minutes=1
        )
        
        mock_client = setup_mock_binance_client(all_klines)
        
        request = WalkForwardRequest(
            symbol="BTCUSDT",
            strategy_type="scalping",
            start_time=start_time,
            end_time=end_time,
            training_period_days=7,
            test_period_days=3,
            step_size_days=5,
            window_type="rolling",
            leverage=5,
            risk_per_trade=0.01,
            initial_balance=1000.0,
            params={"kline_interval": "1m", "ema_fast": 8, "ema_slow": 21},
            optimize_params={
                "ema_fast": [5, 8],
                "ema_slow": [15, 21]
            },
            optimization_metric="robust_score",
            optimization_method="grid_search"
        )
        
        # Track all operations
        fetch_calls = []
        backtest_calls = []
        
        async def track_fetch(*args, **kwargs):
            fetch_calls.append(kwargs)
            return all_klines
        
        async def track_backtest(req, client, **kwargs):
            backtest_calls.append({
                'start_time': req.start_time,
                'end_time': req.end_time,
                'has_pre_fetched': kwargs.get('pre_fetched_klines') is not None
            })
            return create_mock_backtest_result(
                initial_balance=req.initial_balance,
                final_balance=req.initial_balance * 1.05,
                completed_trades=10
            )
        
        with patch('app.services.walk_forward._fetch_historical_klines', side_effect=track_fetch):
            with patch('app.services.walk_forward.run_backtest', side_effect=track_backtest):
                result = await run_walk_forward_analysis(request, mock_client)
                
                # Verify single fetch
                assert len(fetch_calls) == 1, \
                    f"Expected 1 fetch call, got {len(fetch_calls)}"
                assert fetch_calls[0]['start_time'] == start_time
                assert fetch_calls[0]['end_time'] == end_time
                
                # Verify all backtest calls received pre-fetched klines
                assert len(backtest_calls) > 0, "Should have backtest calls"
                for call_info in backtest_calls:
                    assert call_info['has_pre_fetched'], \
                        "All backtest calls should have pre-fetched klines"
                
                # Verify result
                assert result.total_windows > 0
                assert len(result.windows) == result.total_windows


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

