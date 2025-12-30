"""
Comprehensive tests for Walk-Forward Analysis functionality.

Tests verify:
1. Window generation (rolling vs expanding)
2. Parameter optimization with guardrails
3. Result aggregation (compounded returns)
4. Equity curve generation
5. Integration with backtesting
6. Edge cases and error handling
"""
import pytest
pytestmark = pytest.mark.slow  # Walk-forward tests are excluded from CI due to CPU limitations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch
from typing import Optional

from fastapi import HTTPException

from app.services.walk_forward import (
    WalkForwardRequest,
    WalkForwardWindow,
    WalkForwardResult,
    generate_walk_forward_windows,
    calculate_robust_score,
    calculate_sharpe_ratio,
    aggregate_walk_forward_results,
    calculate_metric_score,
    generate_param_combinations,
    run_walk_forward_analysis
)
from app.api.routes.backtesting import BacktestRequest, BacktestResult, Trade
from app.core.my_binance_client import BinanceClient


# ============================================================================
# Helper Functions
# ============================================================================

def build_klines(count: int, base_price: float = 50000.0, price_trend: float = 0.0,
                 volatility: float = 100.0, base_volume: float = 1000.0,
                 start_time: Optional[datetime] = None, interval_minutes: int = 1) -> list[list]:
    """
    Helper to create klines for testing.
    
    Args:
        count: Number of candles to generate
        base_price: Starting price
        price_trend: Price change per candle (positive = uptrend, negative = downtrend)
        volatility: Price volatility (random variation)
        base_volume: Base volume per candle
        start_time: Start time for first candle (defaults to now - count minutes)
        interval_minutes: Minutes per candle
    
    Returns:
        List of klines in Binance format: [open_time, open, high, low, close, volume, ...]
    """
    import random
    
    if start_time is None:
        start_time = datetime.now(timezone.utc) - timedelta(minutes=count * interval_minutes)
    
    klines = []
    current_price = base_price
    
    for i in range(count):
        # Add trend
        current_price += price_trend
        
        # Add volatility
        price_change = random.uniform(-volatility, volatility)
        current_price += price_change
        
        # Ensure price stays positive
        current_price = max(current_price, 100.0)
        
        # Create OHLC
        open_price = current_price
        high_price = open_price + abs(random.uniform(0, volatility * 0.5))
        low_price = open_price - abs(random.uniform(0, volatility * 0.5))
        close_price = open_price + random.uniform(-volatility * 0.3, volatility * 0.3)
        
        # Ensure high >= open,close and low <= open,close
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)
        
        # Volume
        volume = base_volume + random.uniform(-base_volume * 0.2, base_volume * 0.2)
        
        # Timestamp
        candle_time = start_time + timedelta(minutes=i * interval_minutes)
        timestamp = int(candle_time.timestamp() * 1000)
        
        klines.append([
            timestamp,  # open_time
            str(open_price),  # open
            str(high_price),  # high
            str(low_price),  # low
            str(close_price),  # close
            str(volume),  # volume
            timestamp + (interval_minutes * 60 * 1000) - 1,  # close_time
            "0",  # quote_asset_volume
            "0",  # number_of_trades
            "0",  # taker_buy_base_asset_volume
            "0",  # taker_buy_quote_asset_volume
            "0"  # ignore
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
# Test Window Generation
# ============================================================================

class TestWindowGeneration:
    """Test walk-forward window generation logic."""
    
    def test_rolling_windows_fixed_size(self):
        """Test that rolling windows maintain fixed size."""
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2024, 2, 1, tzinfo=timezone.utc)  # 31 days
        
        windows = generate_walk_forward_windows(
            start_time=start_time,
            end_time=end_time,
            training_days=7,
            test_days=3,
            step_days=5,
            window_type="rolling"
        )
        
        assert len(windows) > 0
        
        # Check that all training windows are fixed size (7 days)
        for window in windows:
            training_duration = (window['training_end'] - window['training_start']).days
            assert training_duration == 7, f"Expected 7 days, got {training_duration}"
            
            # Test window should start immediately after training
            assert window['test_start'] == window['training_end']
            
            # Test window should be 3 days
            test_duration = (window['test_end'] - window['test_start']).days
            assert test_duration == 3, f"Expected 3 days, got {test_duration}"
    
    def test_expanding_windows_grow(self):
        """Test that expanding windows grow from the beginning."""
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2024, 2, 1, tzinfo=timezone.utc)  # 31 days
        
        windows = generate_walk_forward_windows(
            start_time=start_time,
            end_time=end_time,
            training_days=7,
            test_days=3,
            step_days=5,
            window_type="expanding"
        )
        
        assert len(windows) > 0
        
        # Check that all training windows start from the beginning
        for window in windows:
            assert window['training_start'] == start_time, "Expanding windows should always start from beginning"
            
            # Training window should grow (end increases)
            # Test window should start immediately after training
            assert window['test_start'] == window['training_end']
    
    def test_rolling_windows_step_smaller_than_training(self):
        """Test rolling windows when step_days < training_days (overlapping windows)."""
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, tzinfo=timezone.utc)  # 19 days
        
        windows = generate_walk_forward_windows(
            start_time=start_time,
            end_time=end_time,
            training_days=7,
            test_days=3,
            step_days=2,  # Step smaller than training
            window_type="rolling"
        )
        
        assert len(windows) > 0
        
        # Windows should overlap but maintain fixed size
        for i, window in enumerate(windows):
            training_duration = (window['training_end'] - window['training_start']).days
            assert training_duration == 7, f"Window {i}: Expected 7 days, got {training_duration}"
    
    def test_windows_dont_exceed_end_time(self):
        """Test that windows don't exceed the end_time boundary."""
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 15, tzinfo=timezone.utc)  # 14 days
        
        windows = generate_walk_forward_windows(
            start_time=start_time,
            end_time=end_time,
            training_days=7,
            test_days=3,
            step_days=5,
            window_type="rolling"
        )
        
        # All windows should be within bounds
        for window in windows:
            assert window['training_start'] >= start_time
            assert window['training_end'] <= end_time
            assert window['test_start'] >= start_time
            assert window['test_end'] <= end_time
    
    def test_no_windows_if_insufficient_data(self):
        """Test that no windows are generated if time range is too short."""
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 5, tzinfo=timezone.utc)  # Only 4 days
        
        windows = generate_walk_forward_windows(
            start_time=start_time,
            end_time=end_time,
            training_days=7,
            test_days=3,
            step_days=5,
            window_type="rolling"
        )
        
        # Should have no windows (need at least 7+3=10 days)
        assert len(windows) == 0


# ============================================================================
# Test Robust Score Calculation
# ============================================================================

class TestRobustScore:
    """Test robust score calculation."""
    
    def test_robust_score_with_sufficient_trades(self):
        """Test robust score calculation with sufficient trades."""
        result = create_mock_backtest_result(
            initial_balance=1000.0,
            final_balance=1050.0,  # 5% return
            completed_trades=10,
            max_drawdown_pct=2.0  # 2% drawdown
        )
        
        score = calculate_robust_score(result)
        
        # Expected: 5.0 - (2.0 * 2.0) = 5.0 - 4.0 = 1.0
        expected_score = 5.0 - (2.0 * 2.0)
        assert abs(score - expected_score) < 1e-10, f"Expected {expected_score}, got {score}"
    
    def test_robust_score_insufficient_trades(self):
        """Test that robust score returns -inf for insufficient trades."""
        result = create_mock_backtest_result(
            completed_trades=3  # Less than minimum (5)
        )
        
        score = calculate_robust_score(result)
        assert score == float('-inf'), "Should return -inf for insufficient trades"
    
    def test_robust_score_penalizes_high_drawdown(self):
        """Test that robust score penalizes high drawdowns."""
        result_low_dd = create_mock_backtest_result(
            final_balance=1050.0,  # 5% return
            max_drawdown_pct=2.0,  # 2% drawdown
            completed_trades=10
        )
        
        result_high_dd = create_mock_backtest_result(
            final_balance=1050.0,  # 5% return
            max_drawdown_pct=10.0,  # 10% drawdown
            completed_trades=10
        )
        
        score_low = calculate_robust_score(result_low_dd)
        score_high = calculate_robust_score(result_high_dd)
        
        # Low drawdown should score higher
        assert score_low > score_high, "Low drawdown should score higher than high drawdown"


# ============================================================================
# Test Metric Score with Guardrails
# ============================================================================

class TestMetricScoreGuardrails:
    """Test metric score calculation with guardrails."""
    
    def test_min_trades_guardrail(self):
        """Test that insufficient trades are rejected."""
        result = create_mock_backtest_result(completed_trades=3)
        
        score = calculate_metric_score(result, "robust_score", min_trades=5)
        assert score == float('-inf'), "Should reject insufficient trades"
    
    def test_max_drawdown_guardrail(self):
        """Test that high drawdowns are rejected."""
        result = create_mock_backtest_result(
            max_drawdown_pct=60.0,  # Exceeds 50% cap
            completed_trades=10
        )
        
        score = calculate_metric_score(result, "robust_score", max_dd_cap=50.0)
        assert score == float('-inf'), "Should reject high drawdown"
    
    def test_lottery_trade_detection(self):
        """Test that lottery trades (single trade > 50% of profit) are rejected."""
        # Create result with one large winning trade
        result = create_mock_backtest_result(
            initial_balance=1000.0,
            final_balance=1100.0,  # 10% return = 100 profit
            completed_trades=10
        )
        
        # Modify trades to have one large winner that's > 50% of total profit
        # Set first trade to 60.0 (60% of 100 profit)
        result.trades[0]['net_pnl'] = 60.0
        # Set second trade to 20.0
        result.trades[1]['net_pnl'] = 20.0
        # Set rest to small positive values to ensure total profit is ~100
        for i in range(2, 6):  # Make 4 more winning trades
            result.trades[i]['net_pnl'] = 5.0
        # Rest are losing trades (negative)
        for i in range(6, 10):
            result.trades[i]['net_pnl'] = -2.0
        
        score = calculate_metric_score(result, "robust_score")
        assert score == float('-inf'), f"Should reject lottery trade, got score: {score}"
    
    def test_valid_score_passes_guardrails(self):
        """Test that valid results pass all guardrails."""
        result = create_mock_backtest_result(
            initial_balance=1000.0,
            final_balance=1100.0,  # 10% return to ensure positive score
            completed_trades=10,
            max_drawdown_pct=2.0  # Low drawdown to ensure positive score
        )
        
        score = calculate_metric_score(result, "robust_score", min_trades=5, max_dd_cap=50.0)
        assert score != float('-inf'), "Valid result should pass guardrails"
        # Expected: 10.0 - (2.0 * 2.0) = 10.0 - 4.0 = 6.0
        assert score > 0, f"Should have positive score, got {score}"


# ============================================================================
# Test Result Aggregation
# ============================================================================

class TestResultAggregation:
    """Test walk-forward result aggregation."""
    
    def test_compounded_total_return(self):
        """Test that total return is compounded, not summed."""
        initial_balance = 1000.0
        
        # Create 3 windows with different returns
        window1 = WalkForwardWindow(
            window_number=1,
            training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
            test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
            test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
            training_result=create_mock_backtest_result(initial_balance=1000.0, final_balance=1000.0),
            test_result=create_mock_backtest_result(initial_balance=1000.0, final_balance=1050.0),  # 5% return
            training_return_pct=0.0,
            test_return_pct=5.0,
            training_win_rate=50.0,
            test_win_rate=60.0
        )
        
        window2 = WalkForwardWindow(
            window_number=2,
            training_start=datetime(2024, 1, 6, tzinfo=timezone.utc),
            training_end=datetime(2024, 1, 13, tzinfo=timezone.utc),
            test_start=datetime(2024, 1, 13, tzinfo=timezone.utc),
            test_end=datetime(2024, 1, 16, tzinfo=timezone.utc),
            training_result=create_mock_backtest_result(initial_balance=1000.0, final_balance=1000.0),
            test_result=create_mock_backtest_result(initial_balance=1050.0, final_balance=1102.5),  # 5% return on 1050
            training_return_pct=0.0,
            test_return_pct=5.0,
            training_win_rate=50.0,
            test_win_rate=60.0
        )
        
        window_results = [window1, window2]
        
        aggregated = aggregate_walk_forward_results(window_results, initial_balance)
        
        # Total return should be compounded: (1102.5 / 1000 - 1) * 100 = 10.25%
        # NOT summed: 5% + 5% = 10%
        expected_total_return = ((1102.5 / 1000.0) - 1.0) * 100
        assert abs(aggregated['total_return_pct'] - expected_total_return) < 0.01, \
            f"Expected compounded return {expected_total_return}%, got {aggregated['total_return_pct']}%"
    
    def test_consistency_score(self):
        """Test consistency score calculation."""
        window_results = [
            WalkForwardWindow(
                window_number=i+1,
                training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
                test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
                test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
                training_result=create_mock_backtest_result(),
                test_result=create_mock_backtest_result(
                    initial_balance=1000.0,
                    final_balance=1050.0 if i % 2 == 0 else 950.0  # Alternating wins/losses
                ),
                training_return_pct=0.0,
                test_return_pct=5.0 if i % 2 == 0 else -5.0,
                training_win_rate=50.0,
                test_win_rate=60.0 if i % 2 == 0 else 40.0
            )
            for i in range(4)
        ]
        
        aggregated = aggregate_walk_forward_results(window_results, 1000.0)
        
        # 2 out of 4 windows positive = 50%
        assert aggregated['consistency_score'] == 50.0, \
            f"Expected 50%, got {aggregated['consistency_score']}%"
    
    def test_best_worst_window_identification(self):
        """Test that best and worst windows are correctly identified."""
        returns = [10.0, 5.0, -5.0, -10.0]  # Different returns for each window
        
        window_results = [
            WalkForwardWindow(
                window_number=i+1,
                training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
                test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
                test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
                training_result=create_mock_backtest_result(),
                test_result=create_mock_backtest_result(
                    initial_balance=1000.0,
                    final_balance=1000.0 + (returns[i] * 10.0)  # returns: [10%, 5%, -5%, -10%]
                ),
                training_return_pct=0.0,
                test_return_pct=returns[i],
                training_win_rate=50.0,
                test_win_rate=60.0
            )
            for i in range(4)
        ]
        
        aggregated = aggregate_walk_forward_results(window_results, 1000.0)
        
        assert aggregated['best_window'] == 1, "Window 1 has highest return (10%)"
        assert aggregated['worst_window'] == 4, "Window 4 has lowest return (-10%)"


# ============================================================================
# Test Parameter Optimization
# ============================================================================

class TestParameterOptimization:
    """Test parameter optimization functionality."""
    
    def test_generate_param_combinations(self):
        """Test parameter combination generation."""
        optimize_params = {
            "ema_fast": [5, 8],
            "ema_slow": [15, 21]
        }
        
        combinations = generate_param_combinations(optimize_params)
        
        # Should have 2 * 2 = 4 combinations
        assert len(combinations) == 4
        
        # Check all combinations are present
        expected = [
            {"ema_fast": 5, "ema_slow": 15},
            {"ema_fast": 5, "ema_slow": 21},
            {"ema_fast": 8, "ema_slow": 15},
            {"ema_fast": 8, "ema_slow": 21}
        ]
        
        for expected_combo in expected:
            assert expected_combo in combinations, f"Missing combination: {expected_combo}"
    
    def test_generate_param_combinations_validation(self):
        """Test that invalid parameter combinations are rejected."""
        # Non-list value
        with pytest.raises(ValueError, match="must be a list"):
            generate_param_combinations({"ema_fast": 5})  # Should be [5]
        
        # Empty list
        with pytest.raises(ValueError, match="no values to test"):
            generate_param_combinations({"ema_fast": []})


# ============================================================================
# Test Integration
# ============================================================================

class TestWalkForwardIntegration:
    """Test walk-forward analysis integration."""
    
    @pytest.mark.asyncio
    async def test_walk_forward_basic_flow(self):
        """Test basic walk-forward analysis flow."""
        # Create enough klines for multiple windows
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, tzinfo=timezone.utc)  # 19 days
        
        # Generate klines (enough for training + test windows)
        klines = build_klines(
            count=20000,  # ~13.8 days of 1m candles
            start_time=start_time,
            interval_minutes=1
        )
        
        mock_client = setup_mock_binance_client(klines)
        
        # Mock run_backtest to return predictable results
        with patch('app.services.walk_forward.run_backtest') as mock_run_backtest:
            # Create mock results
            def create_result(initial_balance):
                return create_mock_backtest_result(
                    initial_balance=initial_balance,
                    final_balance=initial_balance * 1.05  # 5% return
                )
            
            mock_run_backtest.side_effect = lambda req, client, **kwargs: create_result(req.initial_balance)
            
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
                params={
                    "kline_interval": "1m",
                    "ema_fast": 8,
                    "ema_slow": 21
                }
            )
            
            result = await run_walk_forward_analysis(request, mock_client)
            
            # Verify result structure
            assert isinstance(result, WalkForwardResult)
            assert result.symbol == "BTCUSDT"
            assert result.strategy_type == "scalping"
            assert result.total_windows > 0
            assert len(result.windows) == result.total_windows
            
            # Verify total return is compounded
            final_balance = result.windows[-1].test_result.final_balance
            expected_return = ((final_balance / 1000.0) - 1.0) * 100
            assert abs(result.total_return_pct - expected_return) < 0.01
    
    @pytest.mark.asyncio
    async def test_walk_forward_validation_errors(self):
        """Test that validation errors are raised correctly."""
        mock_client = setup_mock_binance_client([])
        
        # Test: start_time >= end_time
        with pytest.raises(Exception):  # HTTPException in actual code
            request = WalkForwardRequest(
                symbol="BTCUSDT",
                strategy_type="scalping",
                start_time=datetime(2024, 1, 10, tzinfo=timezone.utc),
                end_time=datetime(2024, 1, 1, tzinfo=timezone.utc),  # Before start
                training_period_days=7,
                test_period_days=3,
                step_size_days=5,
                window_type="rolling",
                initial_balance=1000.0,
                params={}
            )
            await run_walk_forward_analysis(request, mock_client)
        
        # Test: insufficient time range
        with pytest.raises(Exception):  # HTTPException in actual code
            request = WalkForwardRequest(
                symbol="BTCUSDT",
                strategy_type="scalping",
                start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2024, 1, 5, tzinfo=timezone.utc),  # Only 4 days
                training_period_days=7,  # Need 7 + 3 = 10 days minimum
                test_period_days=3,
                step_size_days=5,
                window_type="rolling",
                initial_balance=1000.0,
                params={}
            )
            await run_walk_forward_analysis(request, mock_client)


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestWalkForwardEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_window_results_aggregation(self):
        """Test aggregation with empty window results."""
        aggregated = aggregate_walk_forward_results([], 1000.0)
        
        assert aggregated['total_return_pct'] == 0.0
        assert aggregated['total_trades'] == 0
        assert aggregated['consistency_score'] == 0.0
    
    def test_single_window_aggregation(self):
        """Test aggregation with single window."""
        window = WalkForwardWindow(
            window_number=1,
            training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
            test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
            test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
            training_result=create_mock_backtest_result(),
            test_result=create_mock_backtest_result(
                initial_balance=1000.0,
                final_balance=1050.0
            ),
            training_return_pct=0.0,
            test_return_pct=5.0,
            training_win_rate=50.0,
            test_win_rate=60.0
        )
        
        aggregated = aggregate_walk_forward_results([window], 1000.0)

        # Use approximate equality for floating point comparison
        assert abs(aggregated['total_return_pct'] - 5.0) < 1e-10, \
            f"Expected 5.0, got {aggregated['total_return_pct']}"
        assert aggregated['consistency_score'] == 100.0  # 1 window, positive return
        assert aggregated['best_window'] == 1
        assert aggregated['worst_window'] == 1


# ============================================================================
# Critical Data Leakage Prevention Tests
# ============================================================================

class TestDataLeakagePrevention:
    """Critical tests to ensure no data leakage in walk-forward analysis."""
    
    @pytest.mark.asyncio
    async def test_fetch_only_once(self):
        """
        CRITICAL TEST: Verify klines are fetched only once for entire time range.
        
        This validates the performance optimization: instead of fetching
        N windows × M combinations times, we fetch once and reuse.
        """
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, 0, 0, 0, tzinfo=timezone.utc)
        
        all_klines = build_klines(count=27360, start_time=start_time)
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
        
        # Track fetch calls
        fetch_call_count = 0
        
        async def track_fetch(*args, **kwargs):
            nonlocal fetch_call_count
            fetch_call_count += 1
            return all_klines
        
        with patch('app.services.walk_forward._fetch_historical_klines', side_effect=track_fetch):
            with patch('app.services.walk_forward.run_backtest', new_callable=AsyncMock) as mock_backtest:
                mock_backtest.side_effect = lambda req, client, **kwargs: create_mock_backtest_result(
                    initial_balance=req.initial_balance,
                    final_balance=req.initial_balance * 1.05
                )
                
                result = await run_walk_forward_analysis(request, mock_client)
                
                # CRITICAL: Should fetch exactly once
                assert fetch_call_count == 1, \
                    f"Expected 1 fetch call, got {fetch_call_count}. " \
                    f"Performance optimization failed - klines should be fetched once for entire range."
                
                # Verify result is valid
                assert result.total_windows > 0
    
    @pytest.mark.asyncio
    async def test_no_data_leakage_training_test_slices(self):
        """
        CRITICAL TEST: Verify no data leakage - training and test use correctly sliced klines.
        
        This ensures:
        - Training backtest only receives training period klines
        - Test backtest only receives test period klines
        - No future data leakage
        """
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, 0, 0, 0, tzinfo=timezone.utc)
        
        all_klines = build_klines(count=27360, start_time=start_time)
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
        
        # Track all backtest calls with their klines
        backtest_calls = []
        
        async def track_backtest(req, client, **kwargs):
            pre_fetched = kwargs.get('pre_fetched_klines', [])
            
            # Extract time range from klines
            if pre_fetched:
                first_time = datetime.fromtimestamp(int(pre_fetched[0][0]) / 1000, tz=timezone.utc)
                last_time = datetime.fromtimestamp(int(pre_fetched[-1][0]) / 1000, tz=timezone.utc)
            else:
                first_time = None
                last_time = None
            
            backtest_calls.append({
                'request_start': req.start_time,
                'request_end': req.end_time,
                'klines_start': first_time,
                'klines_end': last_time,
                'klines_count': len(pre_fetched) if pre_fetched else 0
            })
            
            return create_mock_backtest_result(
                initial_balance=req.initial_balance,
                final_balance=req.initial_balance * 1.05
            )
        
        with patch('app.services.walk_forward._fetch_historical_klines', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = all_klines
            
            with patch('app.services.walk_forward.run_backtest', side_effect=track_backtest):
                result = await run_walk_forward_analysis(request, mock_client)
                
                # Verify we have calls (training + test for each window)
                assert len(backtest_calls) >= 2, "Should have at least training and test calls"
                
                # Group calls by window (training comes before test)
                for i in range(0, len(backtest_calls), 2):
                    if i + 1 < len(backtest_calls):
                        training_call = backtest_calls[i]
                        test_call = backtest_calls[i + 1]
                        
                        # CRITICAL: Training klines should only be within training period
                        if training_call['klines_start'] and training_call['klines_end']:
                            assert training_call['klines_start'] >= training_call['request_start'], \
                                f"Training klines start ({training_call['klines_start']}) before request start ({training_call['request_start']})"
                            assert training_call['klines_end'] <= training_call['request_end'], \
                                f"Training klines end ({training_call['klines_end']}) after request end ({training_call['request_end']})"
                            
                            # CRITICAL: Training klines should NOT include test period
                            assert training_call['klines_end'] <= test_call['request_start'], \
                                f"DATA LEAKAGE: Training klines ({training_call['klines_end']}) extend into test period ({test_call['request_start']})"
                        
                        # CRITICAL: Test klines should only be within test period
                        if test_call['klines_start'] and test_call['klines_end']:
                            assert test_call['klines_start'] >= test_call['request_start'], \
                                f"Test klines start ({test_call['klines_start']}) before request start ({test_call['request_start']})"
                            assert test_call['klines_end'] <= test_call['request_end'], \
                                f"Test klines end ({test_call['klines_end']}) after request end ({test_call['request_end']})"
                            
                            # CRITICAL: Test klines should NOT include training period
                            assert test_call['klines_start'] >= training_call['request_end'], \
                                f"DATA LEAKAGE: Test klines ({test_call['klines_start']}) include training period ({training_call['request_end']})"
    
    @pytest.mark.asyncio
    async def test_grid_search_uses_only_training_klines(self):
        """
        CRITICAL TEST: Verify optimization (grid search) only uses training klines.
        
        This ensures:
        - Grid search never receives test period klines
        - Grid search never receives future data
        - All optimization combinations use only training data
        """
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, 0, 0, 0, tzinfo=timezone.utc)
        
        all_klines = build_klines(count=27360, start_time=start_time)
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
        
        # Get expected training period end from first window
        windows = generate_walk_forward_windows(
            request.start_time,
            request.end_time,
            request.training_period_days,
            request.test_period_days,
            request.step_size_days,
            request.window_type
        )
        first_window_training_end = windows[0]['training_end']
        first_window_test_start = windows[0]['test_start']
        
        # Track all backtest calls
        all_calls = []
        
        async def track_all_backtests(req, client, **kwargs):
            pre_fetched = kwargs.get('pre_fetched_klines', [])
            
            # Extract time range from klines
            if pre_fetched:
                first_time = datetime.fromtimestamp(int(pre_fetched[0][0]) / 1000, tz=timezone.utc)
                last_time = datetime.fromtimestamp(int(pre_fetched[-1][0]) / 1000, tz=timezone.utc)
            else:
                first_time = None
                last_time = None
            
            call_info = {
                'request_start': req.start_time,
                'request_end': req.end_time,
                'klines_start': first_time,
                'klines_end': last_time,
                'klines_count': len(pre_fetched) if pre_fetched else 0,
                'is_optimization': req.end_time <= first_window_training_end  # Optimization uses training period
            }
            all_calls.append(call_info)
            
            return create_mock_backtest_result(
                initial_balance=req.initial_balance,
                final_balance=req.initial_balance * 1.05,
                completed_trades=10
            )
        
        with patch('app.services.walk_forward._fetch_historical_klines', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = all_klines
            
            with patch('app.services.walk_forward.run_backtest', side_effect=track_all_backtests):
                result = await run_walk_forward_analysis(request, mock_client)
                
                # Filter optimization calls (those with end_time <= training_end)
                optimization_calls = [c for c in all_calls if c['is_optimization']]
                
                # Verify we have optimization calls (grid search tests multiple combinations)
                assert len(optimization_calls) >= 4, \
                    f"Expected at least 4 optimization calls (2×2 combinations), got {len(optimization_calls)}. " \
                    f"Total calls: {len(all_calls)}"
                
                # CRITICAL: All optimization calls should only use training period klines
                for call_info in optimization_calls:
                    if call_info['klines_start'] and call_info['klines_end']:
                        # CRITICAL: Optimization klines should NOT extend into test period
                        assert call_info['klines_end'] <= first_window_test_start, \
                            f"DATA LEAKAGE: Optimization klines end ({call_info['klines_end']}) extends into test period (starts {first_window_test_start})"
                        
                        # CRITICAL: Optimization klines should be within training period
                        assert call_info['klines_start'] >= call_info['request_start'], \
                            f"Optimization klines start ({call_info['klines_start']}) before request start ({call_info['request_start']})"
                        assert call_info['klines_end'] <= call_info['request_end'], \
                            f"Optimization klines end ({call_info['klines_end']}) after request end ({call_info['request_end']})"
                        
                        # CRITICAL: Optimization klines should NOT exceed training period end
                        assert call_info['klines_end'] <= first_window_training_end, \
                            f"DATA LEAKAGE: Optimization klines ({call_info['klines_end']}) extend beyond training period end ({first_window_training_end})"


    @pytest.mark.asyncio
    async def test_kline_interval_optimization_hard_fail(self):
        """
        CRITICAL TEST: Verify that kline_interval in optimize_params causes hard-fail.
        
        Interval optimization requires separate datasets per interval, which breaks
        the single-fetch optimization. This should fail fast with a clear error.
        """
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 20, 0, 0, 0, tzinfo=timezone.utc)
        
        all_klines = build_klines(count=27360, start_time=start_time)
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
                "kline_interval": ["1m", "5m"],  # This should cause hard-fail
                "ema_fast": [5, 8]
            },
            optimization_metric="robust_score",
            optimization_method="grid_search"
        )
        
        # Should raise HTTPException with 400 status
        with pytest.raises(HTTPException) as exc_info:
            await run_walk_forward_analysis(request, mock_client)
        
        assert exc_info.value.status_code == 400
        assert "kline_interval" in str(exc_info.value.detail).lower()
        assert "not supported" in str(exc_info.value.detail).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

