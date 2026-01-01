"""
Walk-Forward Analysis Service

Provides walk-forward analysis functionality for backtesting strategies.
Splits historical data into multiple training/test windows for robust validation.
"""
from __future__ import annotations

import itertools
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.services.backtest_service import (
    BacktestRequest, 
    BacktestResult, 
    run_backtest,
    fetch_historical_klines as _fetch_historical_klines,
    slice_klines_by_time_range as _slice_klines_by_time_range,
    normalize_interval as validate_and_normalize_interval,
)
from app.services.walk_forward_task_manager import get_task_manager


# ============================================================================
# Data Models
# ============================================================================

class WalkForwardRequest(BaseModel):
    """Request model for walk-forward analysis."""
    symbol: str
    strategy_type: Literal["scalping", "range_mean_reversion"]
    
    # User-friendly identification
    name: Optional[str] = Field(default=None, max_length=255, description="Optional name/label for this analysis")
    
    # Overall time range
    start_time: datetime
    end_time: datetime
    
    # Walk-forward configuration
    training_period_days: int = Field(ge=7, le=365, default=30, description="Training window size in days")
    test_period_days: int = Field(ge=1, le=90, default=7, description="Test window size in days")
    step_size_days: int = Field(ge=1, le=30, default=7, description="How much to advance each iteration in days")
    
    # Window type
    window_type: Literal["rolling", "expanding"] = Field(
        default="rolling",
        description="rolling: fixed-size training window, expanding: growing training window"
    )
    
    # Strategy parameters to optimize (optional - if not provided, use fixed params)
    optimize_params: Optional[dict] = Field(
        default=None,
        description="Parameters to optimize during training. Format: {'param_name': [value1, value2, ...]}. If None, uses fixed params."
    )
    
    # Fixed strategy parameters (used if optimize_params is None, or as base params if optimize_params is provided)
    leverage: int = Field(ge=1, le=50, default=5)
    risk_per_trade: float = Field(gt=0, lt=1, default=0.01)
    fixed_amount: Optional[float] = Field(default=None, gt=0)
    initial_balance: float = Field(gt=0, default=1000.0)
    params: dict = Field(default_factory=dict)  # Strategy-specific parameters
    
    # Optimization settings (if optimize_params is provided)
    optimization_metric: Literal["sharpe_ratio", "robust_score", "total_return", "win_rate", "profit_factor"] = Field(
        default="robust_score",
        description="Metric to optimize during training. 'robust_score' uses return-adjusted-by-drawdown (recommended)"
    )
    optimization_method: Literal["grid_search", "random_search"] = Field(
        default="grid_search",
        description="Optimization algorithm"
    )
    
    # Optimization guardrails (configurable thresholds)
    min_trades_guardrail: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Minimum number of completed trades required for a valid optimization result"
    )
    max_drawdown_cap: float = Field(
        default=50.0,
        ge=0.1,
        le=100.0,
        description="Maximum drawdown percentage allowed (rejects combinations exceeding this)"
    )
    lottery_trade_threshold: float = Field(
        default=0.5,
        ge=0.1,
        le=1.0,
        description="Lottery trade threshold (0.5 = 50%). Rejects if single trade > this percentage of total profit"
    )


class WalkForwardWindow(BaseModel):
    """Results for a single walk-forward window."""
    window_number: int
    training_start: datetime
    training_end: datetime
    test_start: datetime
    test_end: datetime
    
    # Training results
    training_result: BacktestResult
    optimized_params: Optional[dict] = None  # Best params found during training
    optimization_results: Optional[list[dict]] = None  # All parameter combinations tested during training
    
    # Test results (using optimized params)
    test_result: BacktestResult
    
    # Window metrics
    training_sharpe: Optional[float] = None
    test_sharpe: Optional[float] = None
    training_return_pct: float
    test_return_pct: float
    training_win_rate: float
    test_win_rate: float


class WalkForwardResult(BaseModel):
    """Complete walk-forward analysis results."""
    symbol: str
    strategy_type: str
    overall_start_time: datetime
    overall_end_time: datetime
    
    # Configuration
    training_period_days: int
    test_period_days: int
    step_size_days: int
    window_type: str
    total_windows: int
    
    # Window results
    windows: list[WalkForwardWindow]
    
    # Overall performance metrics
    total_return_pct: float  # Cumulative return across all test windows
    avg_window_return_pct: float  # Average return per test window
    consistency_score: float  # % of windows with positive returns
    sharpe_ratio: float  # Overall Sharpe ratio
    max_drawdown_pct: float
    total_trades: int
    avg_win_rate: float
    
    # Performance stability metrics
    return_std_dev: float  # Standard deviation of window returns
    best_window: int  # Window number with best performance
    worst_window: int  # Window number with worst performance
    
    # Equity curve (aggregated across all windows)
    equity_curve: list[dict]  # [{"time": timestamp, "balance": float}]
    initial_balance: float  # Initial balance for reference line in chart


# ============================================================================
# Helper Functions
# ============================================================================

def generate_walk_forward_windows(
    start_time: datetime,
    end_time: datetime,
    training_days: int,
    test_days: int,
    step_days: int,
    window_type: Literal["rolling", "expanding"]
) -> list[dict]:
    """
    Generate walk-forward window pairs.
    
    Correct rolling logic:
    - training_end = anchor + training_days (fixed size)
    - training_start = training_end - training_days
    - test_start = training_end
    - test_end = test_start + test_days
    - advance anchor by step_days
    
    Expanding logic:
    - training_start = overall_start (always from beginning)
    - training_end = anchor + training_days (grows)
    - test_start = training_end
    - test_end = test_start + test_days
    - advance anchor by step_days
    
    Args:
        start_time: Overall start time
        end_time: Overall end time
        training_days: Training window size in days
        test_days: Test window size in days
        step_days: How much to advance each iteration in days
        window_type: "rolling" for fixed-size, "expanding" for growing training window
    
    Returns:
        List of dicts with keys: training_start, training_end, test_start, test_end
    """
    windows = []
    
    # Ensure timezone-aware datetimes
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    # Anchor point that moves forward
    anchor = start_time + timedelta(days=training_days)  # First training window ends at anchor
    
    logger.debug(f"Window generation: start_time={start_time}, end_time={end_time}, "
                f"training_days={training_days}, test_days={test_days}, step_days={step_days}, "
                f"window_type={window_type}")
    logger.debug(f"Initial anchor: {anchor}")
    
    iteration = 0
    while True:
        iteration += 1
        
        if window_type == "rolling":
            # Rolling: Fixed-size training window that ends at anchor
            training_end = anchor
            training_start = training_end - timedelta(days=training_days)
        else:  # expanding
            # Expanding: Training window always starts from beginning, ends at anchor
            training_start = start_time
            training_end = anchor
        
        # Test window starts immediately after training ends
        test_start = training_end
        test_end = test_start + timedelta(days=test_days)
        
        # Check if we can create a valid window
        # Stop if anchor has moved beyond where we can create a complete test window
        if anchor >= end_time:
            logger.debug(f"Stopping at iteration {iteration}: anchor {anchor} >= end_time {end_time}")
            break
        
        # Check if test window exceeds end_time (we need complete test window)
        if test_end > end_time:
            logger.debug(f"Stopping at iteration {iteration}: test_end {test_end} > end_time {end_time}")
            break
        
        # Ensure we have valid windows
        if training_start >= training_end:
            logger.warning(f"Invalid window at iteration {iteration}: training_start {training_start} >= training_end {training_end}")
            break
        
        if test_start >= test_end:
            logger.warning(f"Invalid window at iteration {iteration}: test_start {test_start} >= test_end {test_end}")
            break
        
        # Ensure training window doesn't start before overall start (shouldn't happen, but check anyway)
        if training_start < start_time:
            logger.warning(f"Invalid window at iteration {iteration}: training_start {training_start} < start_time {start_time}")
            break
        
        # Window is valid - add it
        window = {
            "training_start": training_start,
            "training_end": training_end,
            "test_start": test_start,
            "test_end": test_end
        }
        windows.append(window)
        
        logger.debug(f"Window {iteration}: Training {training_start.date()} to {training_end.date()}, "
                    f"Test {test_start.date()} to {test_end.date()}")
        
        # Move anchor forward by step_size for next iteration
        anchor += timedelta(days=step_days)
        
        # Safety check: prevent infinite loop
        if iteration > 1000:
            logger.error(f"Window generation exceeded 1000 iterations! Stopping to prevent infinite loop.")
            break
    
    logger.info(f"Generated {len(windows)} windows from {start_time.date()} to {end_time.date()}")
    return windows


def calculate_robust_score(result: BacktestResult) -> float:
    """
    Calculate a robust optimization score that doesn't require return series.
    
    Uses: total_return_pct - k * max_drawdown_pct (Calmar-like ratio)
    This is more reliable than a fake Sharpe ratio until we have proper return series.
    
    Args:
        result: BacktestResult to score
    
    Returns:
        Score value (higher is better), or -inf if insufficient data
    """
    if not result.trades or result.completed_trades < 5:
        # Require minimum trades for meaningful score
        return float('-inf')
    
    # Calmar-like ratio: return adjusted by drawdown
    # Penalize high drawdowns more heavily
    k = 2.0  # Penalty multiplier for drawdown
    score = result.total_return_pct - (k * result.max_drawdown_pct)
    
    return score


def calculate_sharpe_ratio(result: BacktestResult, risk_free_rate: float = 0.0) -> Optional[float]:
    """
    Calculate Sharpe ratio from backtest result using equity curve.
    
    Sharpe Ratio = (Mean Return - Risk-Free Rate) / Standard Deviation of Returns
    
    For backtesting, we calculate period returns from the equity curve and then
    compute the Sharpe ratio using the mean and standard deviation of those returns.
    
    Args:
        result: BacktestResult to calculate Sharpe ratio for
        risk_free_rate: Risk-free rate (default 0.0, annualized)
    
    Returns:
        Sharpe ratio or None if insufficient data
    """
    try:
        # Check if we have enough data
        if result.total_trades < 2:
            # Need at least 2 trades to calculate returns
            return None
        
        # Calculate period returns from trades
        # We'll use completed trades to calculate returns
        returns = []
        previous_balance = result.initial_balance
        
        # Extract returns from trades
        # Each trade's net_pnl gives us the return for that period
        for trade in result.trades:
            if not trade.get('is_open', True) and trade.get('net_pnl') is not None:
                # Calculate return as percentage of balance before trade
                if previous_balance > 0:
                    period_return = (trade['net_pnl'] / previous_balance) * 100  # As percentage
                    returns.append(period_return)
                    previous_balance += trade['net_pnl']
                else:
                    # Balance went to zero or negative - can't calculate meaningful returns
                    return None
        
        if len(returns) < 2:
            # Need at least 2 returns to calculate standard deviation
            return None
        
        # Calculate mean return
        mean_return = statistics.mean(returns)
        
        # Calculate standard deviation of returns
        if len(returns) > 1:
            std_dev = statistics.stdev(returns)
        else:
            return None
        
        # If standard deviation is zero or very small, Sharpe ratio is undefined
        if std_dev < 1e-10:
            return None
        
        # Calculate Sharpe ratio
        # Annualize if we have enough data points (rough approximation)
        # For daily returns: Sharpe = (mean_return - risk_free_rate) / std_dev * sqrt(252)
        # For our case, we'll use the raw Sharpe ratio (not annualized) since we don't know the exact period
        sharpe_ratio = (mean_return - risk_free_rate) / std_dev
        
        return sharpe_ratio
        
    except Exception as e:
        logger.warning(f"Error calculating Sharpe ratio: {e}")
        return None


def aggregate_walk_forward_results(
    window_results: list[WalkForwardWindow],
    initial_balance: float
) -> dict:
    """
    Aggregate statistics across all walk-forward windows.
    
    CRITICAL FIX: total_return_pct must be compounded, not summed.
    Since we chain balances via cumulative_balance, we calculate overall return
    from final balance vs initial balance.
    
    Args:
        window_results: List of WalkForwardWindow results
        initial_balance: Starting balance for the entire walk-forward analysis
    
    Returns:
        Dictionary with aggregated statistics
    """
    if not window_results:
        return {
            "total_return_pct": 0.0,
            "avg_window_return_pct": 0.0,
            "consistency_score": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "total_trades": 0,
            "avg_win_rate": 0.0,
            "return_std_dev": 0.0,
            "best_window": 0,
            "worst_window": 0
        }
    
    # CRITICAL: Calculate total return from final balance (compounded)
    final_balance = window_results[-1].test_result.final_balance
    if initial_balance > 0:
        total_return_pct = ((final_balance / initial_balance) - 1.0) * 100
    else:
        total_return_pct = 0.0
    
    test_returns = [w.test_return_pct for w in window_results]
    test_win_rates = [w.test_win_rate for w in window_results]
    
    # Average window return (mean of individual window returns)
    avg_window_return_pct = sum(test_returns) / len(test_returns) if test_returns else 0.0
    
    # Consistency score: % of windows with positive returns
    consistency_score = (sum(1 for r in test_returns if r > 0) / len(test_returns) * 100) if test_returns else 0.0
    
    # Average win rate
    avg_win_rate = sum(test_win_rates) / len(test_win_rates) if test_win_rates else 0.0
    
    # Calculate standard deviation of returns
    if len(test_returns) > 1:
        mean_return = avg_window_return_pct
        variance = sum((r - mean_return) ** 2 for r in test_returns) / (len(test_returns) - 1)
        return_std_dev = variance ** 0.5
    else:
        return_std_dev = 0.0
    
    # Calculate Sharpe ratio (using return std dev)
    sharpe_ratio = (avg_window_return_pct / return_std_dev) if return_std_dev > 0 else 0.0
    
    # Find best and worst windows
    if test_returns:
        best_window_idx = max(range(len(test_returns)), key=lambda i: test_returns[i])
        worst_window_idx = min(range(len(test_returns)), key=lambda i: test_returns[i])
        best_window = best_window_idx + 1  # Window numbers are 1-indexed
        worst_window = worst_window_idx + 1
    else:
        best_window = 0
        worst_window = 0
    
    # Calculate max drawdown from equity curve
    # Build equity curve from window results (using test window balances)
    balances = []
    for window in window_results:
        balances.append(window.test_result.final_balance)
    
    # Calculate max drawdown from equity curve
    if balances and initial_balance > 0:
        # Start from initial balance
        peak = initial_balance
        max_drawdown_pct = 0.0
        for balance in balances:
            if balance > peak:
                peak = balance
            if peak > 0:
                drawdown = ((peak - balance) / peak) * 100
                if drawdown > max_drawdown_pct:
                    max_drawdown_pct = drawdown
    else:
        max_drawdown_pct = 0.0
    
    # Total trades across all windows
    total_trades = sum(w.test_result.total_trades for w in window_results)
    
    return {
        "total_return_pct": total_return_pct,
        "avg_window_return_pct": avg_window_return_pct,
        "consistency_score": consistency_score,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "total_trades": total_trades,
        "avg_win_rate": avg_win_rate,
        "return_std_dev": return_std_dev,
        "best_window": best_window,
        "worst_window": worst_window
    }


# ============================================================================
# Parameter Optimization
# ============================================================================

def generate_param_combinations(optimize_params: dict) -> list[dict]:
    """
    Generate all parameter combinations for grid search.
    
    Args:
        optimize_params: Dict with param names as keys and lists of values as values
        Example: {"ema_fast": [5, 8, 10], "ema_slow": [15, 21, 25]}
    
    Returns:
        List of dicts with all combinations
    """
    param_names = list(optimize_params.keys())
    param_values = list(optimize_params.values())
    
    # Validate that all values are lists
    for name, values in optimize_params.items():
        if not isinstance(values, list):
            raise ValueError(f"Parameter {name} must be a list of values, got {type(values)}")
        if not values:
            raise ValueError(f"Parameter {name} has no values to test")
        if len(values) == 1:
            logger.warning(f"Parameter {name} has only 1 value ({values[0]}). Optimization requires at least 2 values to test multiple combinations. "
                          f"This will result in only 1 combination being tested, which may not provide meaningful optimization.")
    
    # PERFORMANCE FIX: Generate combinations lazily (memory-efficient)
    # Note: itertools.product returns a generator, so we materialize it here for backward compatibility
    # For large parameter spaces, consider using generate_param_combinations_generator() instead
    combinations = itertools.product(*param_values)
    
    return [
        dict(zip(param_names, combo))
        for combo in combinations
    ]


def generate_param_combinations_generator(optimize_params: dict):
    """
    Generate parameter combinations lazily (memory-efficient generator).
    
    Use this for large parameter spaces to avoid memory explosion.
    
    Args:
        optimize_params: Dict mapping parameter names to lists of values to test
    
    Yields:
        Dict with parameter combination
    """
    param_names = list(optimize_params.keys())
    param_values = list(optimize_params.values())
    
    # Validate that all values are lists
    for name, values in optimize_params.items():
        if not isinstance(values, list):
            raise ValueError(f"Parameter {name} must be a list of values, got {type(values)}")
        if not values:
            raise ValueError(f"Parameter {name} has no values to test")
    
    # Generate combinations lazily (doesn't create all in memory)
    for combo in itertools.product(*param_values):
        yield dict(zip(param_names, combo))


def count_param_combinations(optimize_params: dict) -> int:
    """
    Calculate total number of parameter combinations without generating them.
    
    Note: This is an upper bound. Actual count may be lower if filters are applied
    (e.g., EMA fast < EMA slow constraint for scalping strategy).
    
    Args:
        optimize_params: Dict mapping parameter names to lists of values to test
    
    Returns:
        Total number of combinations (upper bound)
    """
    total = 1
    for values in optimize_params.values():
        if not isinstance(values, list):
            raise ValueError(f"Parameter values must be a list, got {type(values)}")
        total *= len(values)
    return total


def is_valid_ema_combination(param_set: dict, strategy_type: str) -> bool:
    """
    Validate EMA parameter combination for scalping strategy.
    
    For scalping strategy, EMA fast must be less than EMA slow.
    This filter prevents invalid combinations before running backtests.
    
    Args:
        param_set: Parameter combination dict
        strategy_type: Strategy type ("scalping" or "range_mean_reversion")
    
    Returns:
        True if combination is valid, False if it should be skipped
    """
    if strategy_type != "scalping":
        return True  # No EMA constraint for other strategy types
    
    # Check both possible parameter naming conventions
    # Scalping uses: ema_fast, ema_slow
    # Range uses: ema_fast_period, ema_slow_period
    ema_fast = None
    ema_slow = None
    
    if "ema_fast" in param_set:
        ema_fast = param_set["ema_fast"]
        ema_slow = param_set.get("ema_slow")
    elif "ema_fast_period" in param_set:
        ema_fast = param_set["ema_fast_period"]
        ema_slow = param_set.get("ema_slow_period")
    
    # If both EMA parameters are present, validate the constraint
    if ema_fast is not None and ema_slow is not None:
        try:
            fast_val = float(ema_fast)
            slow_val = float(ema_slow)
            # EMA fast must be less than EMA slow
            if fast_val >= slow_val:
                return False
        except (ValueError, TypeError):
            # If values can't be compared, allow it (will fail later in backtest)
            pass
    
    return True


def calculate_metric_score(
    result: BacktestResult, 
    metric: str,
    min_trades: int = 5,
    max_dd_cap: float = 50.0,
    lottery_threshold: float = 0.5
) -> float:
    """
    Calculate optimization score based on metric with guardrails.
    
    Args:
        result: BacktestResult to score
        metric: Metric name (sharpe_ratio, total_return, win_rate, profit_factor, robust_score)
        min_trades: Minimum trades required for valid score
        max_dd_cap: Maximum drawdown cap (reject if exceeded)
        lottery_threshold: Lottery trade threshold (0.5 = 50%). Rejects if single trade > this % of total profit
    
    Returns:
        Score value (higher is better), or -inf if guardrails fail
    """
    # Guardrail 1: Minimum trades
    if not result.trades or result.completed_trades < min_trades:
        return float('-inf')
    
    # Guardrail 2: Maximum drawdown cap
    if result.max_drawdown_pct > max_dd_cap:
        return float('-inf')
    
    # Guardrail 3: Check for lottery trades (single trade > threshold% of profit)
    if result.completed_trades > 0:
        winning_trades = [t for t in result.trades if t.get('net_pnl', 0) > 0]
        if winning_trades:
            total_profit = sum(t.get('net_pnl', 0) for t in winning_trades)
            max_single_profit = max((t.get('net_pnl', 0) for t in winning_trades), default=0)
            if total_profit > 0 and (max_single_profit / total_profit) > lottery_threshold:
                # Single trade contributes > threshold% of profit - likely lottery
                logger.debug(f"Rejecting lottery trade: single trade = {max_single_profit:.2f}, total = {total_profit:.2f}, threshold = {lottery_threshold:.1%}")
                return float('-inf')
    
    # Calculate score based on metric
    if metric == "sharpe_ratio":
        # Use robust_score instead of fake Sharpe
        return calculate_robust_score(result)
    elif metric == "robust_score":
        return calculate_robust_score(result)
    elif metric == "total_return":
        return result.total_return_pct
    elif metric == "win_rate":
        return result.win_rate
    elif metric == "profit_factor":
        # Profit factor = Gross Profit / Gross Loss
        winning_trades = [t for t in result.trades if t.get('net_pnl', 0) > 0]
        losing_trades = [t for t in result.trades if t.get('net_pnl', 0) <= 0]
        gross_profit = sum(t.get('net_pnl', 0) for t in winning_trades)
        gross_loss = abs(sum(t.get('net_pnl', 0) for t in losing_trades))
        return gross_profit / gross_loss if gross_loss > 0 else 0.0
    else:
        # Default: use robust score
        logger.warning(f"Unknown metric: {metric}, using robust_score")
        return calculate_robust_score(result)


async def optimize_parameters(
    request: WalkForwardRequest,
    training_start: datetime,
    training_end: datetime,
    client: BinanceClient,
    metric: str,
    method: str,
    pre_fetched_klines: Optional[list[list]] = None,
    task_manager=None,
    task_id: Optional[str] = None
) -> tuple[dict, list[dict]]:
    """
    Optimize strategy parameters during training window.
    
    Args:
        request: Walk-forward request with optimization settings
        training_start: Training period start
        training_end: Training period end
        client: Binance client
        metric: Metric to optimize (sharpe_ratio, total_return, etc.)
        method: Optimization method (grid_search, random_search)
    
    Returns:
        Tuple of (optimized_parameters_dict, all_optimization_results_list)
    """
    if method == "grid_search":
        return await grid_search_optimization(
            request, training_start, training_end, client, metric, pre_fetched_klines,
            task_manager=task_manager, task_id=task_id
        )
    elif method == "random_search":
        # For now, use grid search (random search can be added later)
        logger.warning("Random search not yet implemented, using grid search")
        return await grid_search_optimization(
            request, training_start, training_end, client, metric, pre_fetched_klines,
            task_manager=task_manager, task_id=task_id
        )
    else:
        # Fallback: return fixed params with empty results
        logger.warning(f"Unknown optimization method: {method}, using fixed parameters")
        return request.params, []


async def grid_search_optimization(
    request: WalkForwardRequest,
    training_start: datetime,
    training_end: datetime,
    client: BinanceClient,
    metric: str,
    pre_fetched_klines: Optional[list[list]] = None,
    task_manager=None,
    task_id: Optional[str] = None
) -> tuple[dict, list[dict]]:
    """
    Grid search optimization - tests all parameter combinations.
    
    Args:
        request: Walk-forward request
        training_start: Training period start
        training_end: Training period end
        client: Binance client
        metric: Metric to optimize
    
    Returns:
        Dictionary of optimized parameters
    """
    optimize_params = request.optimize_params
    logger.info(f"grid_search_optimization: optimize_params={optimize_params}, type={type(optimize_params)}")
    
    if not optimize_params:
        logger.warning("grid_search_optimization: optimize_params is None or empty, returning base params")
        return request.params, []
    
    if not isinstance(optimize_params, dict):
        logger.error(f"grid_search_optimization: optimize_params is not a dict, got {type(optimize_params)}")
        return request.params, []
    
    if len(optimize_params) == 0:
        logger.warning("grid_search_optimization: optimize_params is empty dict, returning base params")
        return request.params, []
    
    logger.info(f"grid_search_optimization: optimize_params keys={list(optimize_params.keys())}, values={optimize_params}")
    
    best_params = request.params.copy()
    best_score = float('-inf')
    
    # PERFORMANCE FIX: Calculate total combinations without materializing all in memory
    total_combinations = count_param_combinations(optimize_params)
    
    # Use generator for memory efficiency (only materialize as we iterate)
    param_combinations_gen = generate_param_combinations_generator(optimize_params)
    
    logger.info(f"Grid search: Testing up to {total_combinations} parameter combinations...")
    
    combinations_tested = 0
    combinations_failed = 0
    combinations_skipped = 0
    # MEMORY FIX: Only store top 20 results instead of all results (reduces memory by 90%+)
    # Use a heap to efficiently track top N results
    import heapq
    top_results = []  # Min-heap to track top N results (we'll keep the worst of the best)
    MAX_STORED_RESULTS = 20
    for i, param_set in enumerate(param_combinations_gen):
        # Check for cancellation during optimization loop
        if task_manager and task_id and task_manager.is_cancelled(task_id):
            logger.info(f"Optimization cancelled at combination {i+1}/{total_combinations}")
            raise HTTPException(
                status_code=499,
                detail="Walk-forward analysis was cancelled"
            )
        
        # FILTER: Skip invalid EMA combinations for scalping strategy
        # EMA fast must be less than EMA slow (saves time by skipping invalid combinations)
        if not is_valid_ema_combination(param_set, request.strategy_type):
            combinations_skipped += 1
            logger.debug(f"Skipping invalid EMA combination {i+1}: {param_set} (EMA fast >= EMA slow)")
            continue
        
        test_params = {**request.params, **param_set}
        
        # Run backtest with these parameters
        test_request = BacktestRequest(
            symbol=request.symbol,
            strategy_type=request.strategy_type,
            start_time=training_start,
            end_time=training_end,
            leverage=request.leverage,
            risk_per_trade=request.risk_per_trade,
            fixed_amount=request.fixed_amount,
            initial_balance=request.initial_balance,
            params=test_params
        )
        
        try:
            # Use pre-fetched klines if available, otherwise fetch
            result = await run_backtest(test_request, client, pre_fetched_klines=pre_fetched_klines)
            combinations_tested += 1
            
            # Calculate score based on metric (with guardrails)
            score = calculate_metric_score(
                result, 
                metric, 
                min_trades=request.min_trades_guardrail,
                max_dd_cap=request.max_drawdown_cap,
                lottery_threshold=request.lottery_trade_threshold
            )
            
            # Determine failure reason if score is -inf
            failure_reason = None
            if score == float('-inf'):
                if not result.trades or result.completed_trades < request.min_trades_guardrail:
                    failure_reason = f"Insufficient trades: {result.completed_trades} < {request.min_trades_guardrail} (minimum required)"
                elif result.max_drawdown_pct > request.max_drawdown_cap:
                    failure_reason = f"Max drawdown too high: {result.max_drawdown_pct:.2f}% > {request.max_drawdown_cap:.2f}% (maximum allowed)"
                else:
                    # Check for lottery trade
                    if result.completed_trades > 0:
                        winning_trades = [t for t in result.trades if t.get('net_pnl', 0) > 0]
                        if winning_trades:
                            total_profit = sum(t.get('net_pnl', 0) for t in winning_trades)
                            max_single_profit = max((t.get('net_pnl', 0) for t in winning_trades), default=0)
                            if total_profit > 0 and (max_single_profit / total_profit) > request.lottery_trade_threshold:
                                failure_reason = f"Lottery trade detected (single trade > {request.lottery_trade_threshold:.1%} of total profit)"
                            elif total_profit <= 0:
                                # Edge case: All winning trades have net_pnl <= 0 (shouldn't happen, but handle it)
                                failure_reason = "No profitable trades (all winning trades have zero or negative profit)"
                        else:
                            # Edge case: No winning trades at all
                            failure_reason = "No winning trades (all trades resulted in losses or break-even)"
                    else:
                        # Edge case: completed_trades is 0 but we got here (shouldn't happen due to first check)
                        failure_reason = "No completed trades"
                
                # Fallback: If we still don't have a failure reason, log it for debugging
                if not failure_reason:
                    logger.warning(
                        f"Combination {i+1} failed guardrails but no specific reason identified. "
                        f"completed_trades={result.completed_trades}, max_dd={result.max_drawdown_pct:.2f}%, "
                        f"trades={len(result.trades) if result.trades else 0}"
                    )
                    failure_reason = "Failed guardrails (unknown reason - check logs)"
            
            # MEMORY FIX: Only store top N results instead of all results
            # Store result only if it's in the top N or if it passed (for debugging failed ones)
            if score > float('-inf'):
                combination_result = {
                    "combination_number": i + 1,
                    "params": param_set.copy(),  # Only optimized params
                    "full_params": test_params.copy(),  # All params (base + optimized)
                    "score": score,
                    "status": "passed",
                    "failure_reason": None,
                    "total_return_pct": result.total_return_pct,
                    "total_trades": result.total_trades,
                    "completed_trades": result.completed_trades,
                    "win_rate": result.win_rate,
                    "max_drawdown_pct": result.max_drawdown_pct,
                    "sharpe_ratio": calculate_sharpe_ratio(result)
                }
                
                # Use min-heap to efficiently track top N results
                if len(top_results) < MAX_STORED_RESULTS:
                    heapq.heappush(top_results, (score, combination_result))
                elif score > top_results[0][0]:  # Better than worst in top N
                    heapq.heapreplace(top_results, (score, combination_result))
            else:
                # Store failed results only if we have space (for debugging)
                if len(top_results) < MAX_STORED_RESULTS:
                    combination_result = {
                        "combination_number": i + 1,
                        "params": param_set.copy(),
                        "full_params": test_params.copy(),
                        "score": None,
                        "status": "failed",
                        "failure_reason": failure_reason,
                        "total_return_pct": result.total_return_pct,
                        "total_trades": result.total_trades,
                        "completed_trades": result.completed_trades,
                        "win_rate": result.win_rate,
                        "max_drawdown_pct": result.max_drawdown_pct,
                        "sharpe_ratio": None
                    }
                    heapq.heappush(top_results, (float('-inf'), combination_result))
            
            if score == float('-inf'):
                combinations_failed += 1
            elif score > best_score:
                best_score = score
                best_params = test_params
                logger.debug(f"New best score: {score:.4f} with params {param_set}")
            
            # Update progress during optimization (every 10 combinations or at the end)
            if (i + 1) % 10 == 0 or (i + 1) == total_combinations:
                score_str = f"{best_score:.4f}" if best_score > float('-inf') else "N/A (all failed)"
                logger.info(f"Optimization progress: {i+1}/{total_combinations} combinations processed "
                           f"({combinations_tested} tested, {combinations_skipped} skipped), "
                           f"best score: {score_str}")
                
                # Update progress with sub-progress for optimization phase
                if task_manager and task_id:
                    opt_progress = (i + 1) / total_combinations  # 0.0 to 1.0
                    await task_manager.update_progress(
                        task_id,
                        current_phase="optimizing",
                        message=f"Optimizing: {combinations_tested}/{total_combinations} combinations tested ({combinations_skipped} skipped)...",
                        phase_progress=opt_progress
                    )
                
        except Exception as e:
            combinations_failed += 1
            error_msg = str(e)
            logger.warning(f"Error testing parameter set {i+1}/{total_combinations}: {error_msg}", exc_info=True)
            
            # Determine error type for better user feedback
            error_type = type(e).__name__
            if "IndexError" in error_type or "insufficient data" in error_msg.lower() or "klines" in error_msg.lower():
                failure_reason = f"Backtest error: Insufficient data or invalid klines ({error_type})"
            elif "ValueError" in error_type or "invalid" in error_msg.lower():
                failure_reason = f"Backtest error: Invalid parameters or configuration ({error_type})"
            elif "KeyError" in error_type:
                failure_reason = f"Backtest error: Missing required parameter ({error_type})"
            else:
                failure_reason = f"Backtest error: {error_type} - {error_msg[:100]}"  # Truncate long messages
            
            # MEMORY FIX: Store failed combination only if we have space
            if len(top_results) < MAX_STORED_RESULTS:
                combination_result = {
                    "combination_number": i + 1,
                    "params": param_set.copy(),
                    "full_params": test_params.copy(),
                    "score": None,
                    "status": "error",
                    "failure_reason": failure_reason,  # Add failure_reason for consistency
                    "error": error_msg,
                    "total_return_pct": None,
                    "total_trades": None,
                    "completed_trades": None,
                    "win_rate": None,
                    "max_drawdown_pct": None,
                    "sharpe_ratio": None
                }
                heapq.heappush(top_results, (float('-inf'), combination_result))
            continue
    
    # Check if all combinations failed
    if best_score == float('-inf'):
        logger.warning(
            f"All {total_combinations} parameter combinations failed optimization guardrails "
            f"(min_trades={request.min_trades_guardrail}, max_dd_cap={request.max_drawdown_cap:.1f}%, "
            f"lottery_threshold={request.lottery_trade_threshold:.1%}). "
            f"Returning base parameters. Consider adjusting optimization ranges or guardrails."
        )
        # Return base params as optimized (current behavior - user gets base params)
        # This allows the walk-forward to continue with base params
    
    # Return all parameters that were specified for optimization
    # This includes parameters with single values (they were still part of the optimization)
    optimized = {}
    for param_name in optimize_params.keys():
        if param_name in best_params:
            optimized[param_name] = best_params[param_name]
        else:
            # This should never happen - log error for debugging
            logger.error(
                f"CRITICAL: Parameter '{param_name}' not found in best_params! "
                f"This indicates a bug. best_params keys: {list(best_params.keys())}, "
                f"optimize_params keys: {list(optimize_params.keys())}"
            )
            # Fallback: use value from request.params
            optimized[param_name] = request.params.get(param_name)
    
    logger.info(f"Best parameters (all optimized params): {optimized} (score: {best_score:.4f})")
    logger.debug(f"All best_params keys: {list(best_params.keys())}")
    logger.debug(f"Optimize_params keys: {list(optimize_params.keys())}")
    
    # MEMORY FIX: Convert heap to sorted list (best results first)
    # Extract results from heap and sort by score (descending)
    # Ensure top_results is not None and is iterable
    if top_results is None:
        logger.warning("top_results is None, using empty list")
        all_optimization_results = []
    else:
        all_optimization_results = [result for _, result in sorted(top_results, key=lambda x: x[0], reverse=True)]
    
    # Ensure all_optimization_results is always a list, never None
    if all_optimization_results is None:
        logger.warning("all_optimization_results is None after conversion, using empty list")
        all_optimization_results = []
    
    # Log summary including skipped combinations
    logger.info(
        f"Optimization complete: {combinations_tested} combinations tested, "
        f"{combinations_skipped} skipped (invalid EMA combinations), "
        f"{combinations_failed} failed guardrails, "
        f"stored top {len(all_optimization_results)} results "
        f"(out of {total_combinations} total combinations)"
    )
    
    # Ensure optimized is not empty if optimization was attempted
    # If all combinations failed, return None instead of empty dict to indicate no optimization occurred
    if len(optimized) == 0 and best_score == float('-inf'):
        logger.warning("All optimization combinations failed - returning None for optimized_params")
        optimized = None
    
    # Return both optimized params and top results
    # Ensure all_optimization_results is always a list (never None) for proper serialization
    if all_optimization_results is None:
        logger.warning("all_optimization_results is None before return, converting to empty list")
        all_optimization_results = []
    
    logger.info(f"Returning from grid_search_optimization: optimized_params={optimized}, optimization_results_count={len(all_optimization_results)}")
    return optimized, all_optimization_results


# ============================================================================
# Core Walk-Forward Analysis
# ============================================================================

async def run_walk_forward_analysis(
    request: WalkForwardRequest,
    client: BinanceClient,
    task_id: Optional[str] = None
) -> WalkForwardResult:
    """
    Run walk-forward analysis on historical data.
    
    Walk-forward analysis splits historical data into multiple training and test periods:
    - Optimizes parameters on training data (if optimize_params provided)
    - Validates on out-of-sample test data
    - Provides more robust performance estimates than single-period backtesting
    
    Process:
    1. Generate training/test window pairs
    2. For each window:
       a. Run backtest on training period (with optimization if enabled)
       b. Run backtest on test period using optimized/fixed params
       c. Store results
    3. Aggregate results across all windows
    
    Args:
        request: WalkForwardRequest with configuration
        client: BinanceClient instance
    
    Returns:
        WalkForwardResult with aggregated statistics
    
    Raises:
        HTTPException: If insufficient data or configuration errors
    """
    # Ensure timezone-aware datetimes
    if request.start_time.tzinfo is None:
        request.start_time = request.start_time.replace(tzinfo=timezone.utc)
    if request.end_time.tzinfo is None:
        request.end_time = request.end_time.replace(tzinfo=timezone.utc)
    
    # Validate time range
    if request.start_time >= request.end_time:
        raise HTTPException(
            status_code=400,
            detail="start_time must be before end_time"
        )
    
    total_days = (request.end_time - request.start_time).days
    if total_days < request.training_period_days + request.test_period_days:
        raise HTTPException(
            status_code=400,
            detail=f"Time range too short: need at least {request.training_period_days + request.test_period_days} days "
                   f"(training: {request.training_period_days}, test: {request.test_period_days}), got {total_days} days"
        )
    
    # Step 1: Generate window pairs
    windows = generate_walk_forward_windows(
        start_time=request.start_time,
        end_time=request.end_time,
        training_days=request.training_period_days,
        test_days=request.test_period_days,
        step_days=request.step_size_days,
        window_type=request.window_type
    )
    
    if not windows:
        raise HTTPException(
            status_code=400,
            detail="No valid windows generated. Check time range and window sizes."
        )
    
    logger.info(f"Starting walk-forward analysis: {len(windows)} windows, {request.window_type} window type")
    logger.info(f"Time range: {request.start_time} to {request.end_time}")
    logger.info(f"Training: {request.training_period_days} days, Test: {request.test_period_days} days, Step: {request.step_size_days} days")
    
    # Initialize progress tracking if task_id provided
    task_manager = get_task_manager() if task_id else None
    if task_manager and task_id:
        await task_manager.update_progress(
            task_id,
            current_window=0,
            current_phase="fetching_klines",
            message="Fetching historical klines..."
        )
    
    # PERFORMANCE OPTIMIZATION: Fetch all klines once for the entire time range
    # This reduces API calls from N windows × M combinations to just 1 fetch
    logger.info("Fetching all klines once for the entire time range (optimization)...")
    
    # Validate and normalize interval using shared utility function
    raw_interval = request.params.get("kline_interval", "1m" if request.strategy_type == "scalping" else "5m")
    interval = validate_and_normalize_interval(raw_interval, request.strategy_type)
    
    # CRITICAL: Hard-fail if kline_interval is in optimize_params
    # Interval optimization requires separate datasets per interval, which breaks the single-fetch optimization
    if request.optimize_params and "kline_interval" in request.optimize_params:
        raise HTTPException(
            status_code=400,
            detail=(
                "kline_interval optimization is not supported with shared-kline caching. "
                "Each interval requires a separate dataset, which conflicts with the single-fetch optimization. "
                "Please remove 'kline_interval' from optimize_params."
            )
        )
    
    try:
        all_klines = await _fetch_historical_klines(
            client=client,
            symbol=request.symbol,
            interval=interval,
            start_time=request.start_time,
            end_time=request.end_time
        )
        logger.info(
            f"✅ Fetched {len(all_klines)} klines for entire time range. "
            f"Will reuse cached data for all windows (no additional Binance API calls)."
        )
        if task_manager and task_id:
            await task_manager.update_progress(
                task_id,
                current_phase="processing_windows",
                message=f"Fetched {len(all_klines)} klines. Processing {len(windows)} windows..."
            )
    except Exception as e:
        logger.error(f"Error fetching klines for walk-forward analysis: {e}")
        if task_manager and task_id:
            await task_manager.fail_task(task_id, f"Failed to fetch klines: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch historical klines: {str(e)}"
        )
    
    # Step 2: Process each window
    window_results = []
    equity_curve_points = []
    cumulative_balance = request.initial_balance
    
    for i, window in enumerate(windows):
        # Check for cancellation
        if task_manager and task_id and task_manager.is_cancelled(task_id):
            logger.info(f"Walk-forward analysis cancelled at window {i+1}/{len(windows)}")
            # Don't call fail_task here - let the endpoint handler set status to "cancelled"
            # Just raise the exception and the endpoint will handle it properly
            raise HTTPException(
                status_code=499,  # Client Closed Request
                detail="Walk-forward analysis was cancelled"
            )
        logger.info(
            f"Processing window {i+1}/{len(windows)}: "
            f"Training {window['training_start'].date()} to {window['training_end'].date()}, "
            f"Test {window['test_start'].date()} to {window['test_end'].date()}"
        )
        
        # Update progress
        if task_manager and task_id:
            await task_manager.update_progress(
                task_id,
                current_window=i,
                current_phase="processing_windows",
                message=f"Processing window {i+1}/{len(windows)}..."
            )
        
        # CRITICAL: Slice klines per window to prevent data leakage
        # Training slice: only training period data
        train_klines = _slice_klines_by_time_range(
            all_klines,
            window['training_start'],
            window['training_end']
        )
        if not train_klines:
            raise HTTPException(
                status_code=400,
                detail=f"No klines found for training period {window['training_start']} to {window['training_end']}"
            )
        
        # Test slice: only test period data
        test_klines = _slice_klines_by_time_range(
            all_klines,
            window['test_start'],
            window['test_end']
        )
        if not test_klines:
            logger.warning(
                f"Window {i+1}: No klines found for test period {window['test_start']} to {window['test_end']}. "
                f"Total klines available: {len(all_klines)}, "
                f"First kline time: {datetime.fromtimestamp(int(all_klines[0][0])/1000, tz=timezone.utc) if all_klines else 'N/A'}, "
                f"Last kline time: {datetime.fromtimestamp(int(all_klines[-1][6])/1000, tz=timezone.utc) if all_klines else 'N/A'}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"No klines found for test period {window['test_start']} to {window['test_end']}. "
                       f"Available data: {datetime.fromtimestamp(int(all_klines[0][0])/1000, tz=timezone.utc) if all_klines else 'N/A'} to "
                       f"{datetime.fromtimestamp(int(all_klines[-1][6])/1000, tz=timezone.utc) if all_klines else 'N/A'}"
            )
        
        logger.debug(
            f"Window {i+1}: Training klines={len(train_klines)}, Test klines={len(test_klines)}"
        )
        
        # Step 2a: Run training backtest (with optimization if enabled)
        logger.info(f"Window {i+1}: Checking optimization - optimize_params={request.optimize_params is not None}, "
                   f"optimize_params keys={list(request.optimize_params.keys()) if request.optimize_params else 'None'}, "
                   f"optimize_params values={request.optimize_params if request.optimize_params else 'None'}")
        
        if request.optimize_params and len(request.optimize_params) > 0:
            # Optimize parameters during training
            # CRITICAL: Pass only training klines to prevent data leakage
            logger.info(f"Optimizing parameters for window {i+1}...")
            logger.info(f"Optimization config: metric={request.optimization_metric}, method={request.optimization_method}")
            logger.info(f"Parameters to optimize: {request.optimize_params}")
            logger.info(f"Base params: {request.params}")
            
            if task_manager and task_id:
                await task_manager.update_progress(
                    task_id,
                    current_window=i,
                    current_phase="optimizing",
                    message=f"Optimizing parameters for window {i+1}/{len(windows)}..."
                )
            try:
                result = await optimize_parameters(
                    request=request,
                    training_start=window['training_start'],
                    training_end=window['training_end'],
                    client=client,
                    metric=request.optimization_metric,
                    method=request.optimization_method,
                    pre_fetched_klines=train_klines,  # Only training data for optimization
                    task_manager=task_manager,
                    task_id=task_id
                )
                # Safely unpack result, ensuring we always have valid values
                if result is None or not isinstance(result, tuple) or len(result) != 2:
                    logger.error(f"optimize_parameters returned invalid result: {result}")
                    optimized_params = None
                    optimization_results = []
                else:
                    optimized_params, optimization_results = result
                    # Ensure optimization_results is a list, not None
                    if optimization_results is None:
                        logger.warning(f"Optimization returned None for results, using empty list")
                        optimization_results = []
                
                logger.info(f"Optimization returned params: {optimized_params}")
                logger.info(f"Optimization tested {len(optimization_results)} combinations")
                logger.info(f"Optimization results type: {type(optimization_results)}, length: {len(optimization_results) if optimization_results else 'None'}")
                training_params = {**request.params, **optimized_params} if optimized_params else request.params
                logger.info(f"Final training params for window {i+1}: {training_params}")
                logger.info(f"Optimized parameters for window {i+1}: {optimized_params}")
                # Ensure optimization_results is always a list (not None) for proper serialization
                if optimization_results is None:
                    logger.warning(f"optimization_results is None for window {i+1}, converting to empty list")
                    optimization_results = []
            except Exception as e:
                logger.error(f"Optimization failed for window {i+1}: {e}", exc_info=True)
                logger.warning(f"Using fixed parameters due to optimization failure.")
                optimized_params = None
                optimization_results = []  # Use empty list instead of None for consistency
                training_params = request.params
        else:
            # Use fixed parameters
            if request.optimize_params is None:
                logger.info(f"Window {i+1}: Using fixed parameters (optimization disabled - optimize_params is None)")
            elif len(request.optimize_params) == 0:
                logger.info(f"Window {i+1}: Using fixed parameters (optimization disabled - optimize_params is empty)")
            else:
                logger.warning(f"Window {i+1}: Using fixed parameters despite optimize_params being set (this should not happen)")
            optimized_params = None
            optimization_results = []  # Use empty list instead of None for consistency
            training_params = request.params
        
        # Check for cancellation before training backtest
        if task_manager and task_id and task_manager.is_cancelled(task_id):
            logger.info(f"Walk-forward analysis cancelled before training backtest for window {i+1}")
            raise HTTPException(
                status_code=499,
                detail="Walk-forward analysis was cancelled"
            )
        
        # Run training backtest (using training slice only)
        if task_manager and task_id:
            await task_manager.update_progress(
                task_id,
                current_window=i,
                current_phase="training",
                message=f"Running training backtest for window {i+1}/{len(windows)}..."
            )
        try:
            training_request = BacktestRequest(
                symbol=request.symbol,
                strategy_type=request.strategy_type,
                start_time=window['training_start'],
                end_time=window['training_end'],
                leverage=request.leverage,
                risk_per_trade=request.risk_per_trade,
                fixed_amount=request.fixed_amount,
                initial_balance=request.initial_balance,  # Use initial balance for each training window
                params=training_params
            )
            training_result = await run_backtest(training_request, client, pre_fetched_klines=train_klines)
        except Exception as e:
            logger.error(f"Error running training backtest for window {i+1}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to run training backtest for window {i+1}: {str(e)}"
            )
        
        # Step 2b: Run test backtest using optimized/fixed params (using test slice only)
        test_params = training_params  # Use same params as training
        if task_manager and task_id:
            await task_manager.update_progress(
                task_id,
                current_window=i,
                current_phase="testing",
                message=f"Running test backtest for window {i+1}/{len(windows)}..."
            )
        
        # Check for cancellation before test backtest
        if task_manager and task_id and task_manager.is_cancelled(task_id):
            logger.info(f"Walk-forward analysis cancelled before test backtest for window {i+1}")
            raise HTTPException(
                status_code=499,
                detail="Walk-forward analysis was cancelled"
            )
        
        try:
            test_request = BacktestRequest(
                symbol=request.symbol,
                strategy_type=request.strategy_type,
                start_time=window['test_start'],
                end_time=window['test_end'],
                leverage=request.leverage,
                risk_per_trade=request.risk_per_trade,
                fixed_amount=request.fixed_amount,
                initial_balance=cumulative_balance,  # Use cumulative balance from previous windows
                params=test_params
            )
            test_result = await run_backtest(test_request, client, pre_fetched_klines=test_klines)
        except Exception as e:
            logger.error(f"Error running test backtest for window {i+1}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to run test backtest for window {i+1}: {str(e)}"
            )
        
        # Store balance at start of test (before updating)
        test_start_balance = cumulative_balance
        
        # Update cumulative balance after test
        cumulative_balance = test_result.final_balance
        
        # Calculate window metrics
        training_sharpe = calculate_sharpe_ratio(training_result)
        test_sharpe = calculate_sharpe_ratio(test_result)
        
        window_result = WalkForwardWindow(
            window_number=i + 1,
            training_start=window['training_start'],
            training_end=window['training_end'],
            test_start=window['test_start'],
            test_end=window['test_end'],
            training_result=training_result,
            optimized_params=optimized_params,
            optimization_results=optimization_results,
            test_result=test_result,
            training_sharpe=training_sharpe,
            test_sharpe=test_sharpe,
            training_return_pct=training_result.total_return_pct,
            test_return_pct=test_result.total_return_pct,
            training_win_rate=training_result.win_rate,
            test_win_rate=test_result.win_rate
        )
        window_results.append(window_result)
        
        # Add equity curve points from test period
        # Add start of test window (balance before test)
        equity_curve_points.append({
            "time": int(window['test_start'].timestamp()),
            "balance": test_start_balance
        })
        
        # Extract per-trade equity points for granular visualization
        # This provides much better equity curve granularity than just start/end points
        # CRITICAL: Even if there are no trades, we still need to add the end point
        # to ensure the equity curve is continuous and shows the balance progression
        if test_result.trades and len(test_result.trades) > 0:
            # Sort trades by entry_time to ensure chronological order
            # Trades should already be in order from backtest, but sort to be safe
            def get_entry_time(trade):
                entry_time = trade.get('entry_time')
                if isinstance(entry_time, datetime):
                    return entry_time
                elif isinstance(entry_time, str):
                    try:
                        return datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    except:
                        return datetime.fromtimestamp(0, tz=timezone.utc)
                else:
                    return datetime.fromtimestamp(0, tz=timezone.utc)
            
            sorted_trades = sorted(test_result.trades, key=get_entry_time)
            
            current_balance = test_start_balance
            for trade in sorted_trades:
                # Add point at trade entry (balance before trade)
                if trade.get('entry_time'):
                    entry_time = trade['entry_time']
                    if isinstance(entry_time, str):
                        entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    elif isinstance(entry_time, datetime):
                        entry_dt = entry_time
                    else:
                        continue
                    equity_curve_points.append({
                        "time": int(entry_dt.timestamp()),
                        "balance": current_balance
                    })
                
                # Add point at trade exit (balance after trade)
                if trade.get('exit_time') and trade.get('net_pnl') is not None:
                    exit_time = trade['exit_time']
                    if isinstance(exit_time, str):
                        exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00'))
                    elif isinstance(exit_time, datetime):
                        exit_dt = exit_time
                    else:
                        continue
                    # Update balance with trade PnL
                    # Note: net_pnl already accounts for entry and exit fees
                    current_balance += trade.get('net_pnl', 0)
                    equity_curve_points.append({
                        "time": int(exit_dt.timestamp()),
                        "balance": current_balance
                    })
            
            # Verify final balance matches test_result.final_balance
            # If there's a discrepancy, use test_result.final_balance (more accurate)
            if abs(current_balance - cumulative_balance) > 0.01:  # Allow small floating point differences
                logger.warning(
                    f"Window {i+1}: Balance mismatch in equity curve: "
                    f"calculated={current_balance:.2f}, actual={cumulative_balance:.2f}. "
                    f"Using actual balance for final point."
                )
                # Update the last point with actual balance
                if equity_curve_points:
                    equity_curve_points[-1]["balance"] = cumulative_balance
        
        # Always add end point to ensure continuity (only once)
        equity_curve_points.append({
            "time": int(window['test_end'].timestamp()),
            "balance": cumulative_balance
        })
        
        logger.info(
            f"Window {i+1} completed: Training return={training_result.total_return_pct:.2f}%, "
            f"Test return={test_result.total_return_pct:.2f}%, "
            f"Cumulative balance={cumulative_balance:.2f}"
        )
    
    # Step 3: Aggregate results
    logger.info("Aggregating walk-forward results...")
    if task_manager and task_id:
        await task_manager.update_progress(
            task_id,
            current_window=len(windows),
            current_phase="aggregating",
            message="Aggregating results..."
        )
    aggregate_stats = aggregate_walk_forward_results(window_results, request.initial_balance)
    
    logger.info(
        f"Walk-forward analysis completed: {len(window_results)} windows, "
        f"Total return={aggregate_stats['total_return_pct']:.2f}%, "
        f"Consistency={aggregate_stats['consistency_score']:.1f}%, "
        f"Sharpe={aggregate_stats['sharpe_ratio']:.2f}"
    )
    
    # Build result
    # Ensure equity_curve_points is not empty - add initial balance point if needed
    if not equity_curve_points:
        logger.warning("Equity curve points list is empty! Adding initial and final balance points.")
        equity_curve_points = [
            {
                "time": int(request.start_time.timestamp()),
                "balance": request.initial_balance
            },
            {
                "time": int(request.end_time.timestamp()),
                "balance": request.initial_balance  # Use initial if no windows completed
            }
        ]
    else:
        # Ensure we have at least start and end points
        # Check if we have a point at the start
        has_start = any(
            abs(point.get('time', 0) - int(request.start_time.timestamp())) < 60 
            for point in equity_curve_points
        )
        if not has_start:
            equity_curve_points.insert(0, {
                "time": int(request.start_time.timestamp()),
                "balance": request.initial_balance
            })
        
        # Check if we have a point at the end
        has_end = any(
            abs(point.get('time', 0) - int(request.end_time.timestamp())) < 60 
            for point in equity_curve_points
        )
        if not has_end:
            # Use the last balance from equity curve, or initial balance if empty
            final_balance = equity_curve_points[-1].get('balance', request.initial_balance) if equity_curve_points else request.initial_balance
            equity_curve_points.append({
                "time": int(request.end_time.timestamp()),
                "balance": final_balance
            })
    
    # Sort equity curve points by time to ensure proper ordering
    equity_curve_points = sorted(equity_curve_points, key=lambda x: x.get('time', 0))
    
    # Remove duplicate points (same time)
    seen_times = set()
    unique_points = []
    for point in equity_curve_points:
        time_key = point.get('time', 0)
        if time_key not in seen_times:
            seen_times.add(time_key)
            unique_points.append(point)
    equity_curve_points = unique_points
    
    logger.info(f"Creating WalkForwardResult with {len(equity_curve_points)} equity curve points")
    if len(equity_curve_points) > 0:
        logger.debug(f"Equity curve range: {equity_curve_points[0].get('time')} to {equity_curve_points[-1].get('time')}")
    
    result = WalkForwardResult(
        symbol=request.symbol,
        strategy_type=request.strategy_type,
        overall_start_time=request.start_time,
        overall_end_time=request.end_time,
        training_period_days=request.training_period_days,
        test_period_days=request.test_period_days,
        step_size_days=request.step_size_days,
        window_type=request.window_type,
        total_windows=len(windows),
        windows=window_results,
        equity_curve=equity_curve_points,
        initial_balance=request.initial_balance,  # Include for frontend reference line
        **aggregate_stats
    )
    
    # Mark task as completed with result
    if task_manager and task_id:
        # Ensure equity_curve is properly serialized
        # Use mode='json' to ensure proper serialization of datetime and other types
        # Include all fields, even if None
        result_dict = result.model_dump(mode='json', exclude_none=False)
        
        # Debug: Log optimization data for first window
        if result_dict.get('windows') and len(result_dict['windows']) > 0:
            first_window = result_dict['windows'][0]
            logger.info(
                f"First window optimization data: "
                f"optimized_params={first_window.get('optimized_params')}, "
                f"optimization_results_count={len(first_window.get('optimization_results', []))}"
            )
        
        # Verify equity_curve is included
        if 'equity_curve' not in result_dict or not result_dict['equity_curve']:
            logger.warning(f"Equity curve missing or empty in result dict. Points: {len(equity_curve_points)}")
        else:
            logger.info(f"Storing result with equity_curve containing {len(result_dict['equity_curve'])} points")
        await task_manager.complete_task(task_id, result_dict)
    
    return result

