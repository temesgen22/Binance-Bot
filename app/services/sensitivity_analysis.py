"""
Parameter Sensitivity Analysis Service

Tests how individual parameter changes affect strategy performance.
Unlike optimization (which finds the best combination), sensitivity analysis
shows the impact of each parameter independently.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any, Literal, Optional, Callable, Awaitable

from fastapi import HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.services.backtest_service import (
    BacktestRequest,
    BacktestResult,
    run_backtest,
    fetch_historical_klines as _fetch_historical_klines,
)


# ============================================================================
# Data Models
# ============================================================================

class SensitivityAnalysisRequest(BaseModel):
    """Request model for sensitivity analysis."""
    symbol: str
    strategy_type: Literal["scalping", "range_mean_reversion", "reverse_scalping"]
    
    # User-friendly identification
    name: Optional[str] = Field(default=None, max_length=255, description="Optional name/label for this analysis")
    
    # Time period for analysis
    start_time: datetime
    end_time: datetime
    
    # Base parameters (starting point)
    base_params: dict
    
    # Parameters to analyze (which ones to vary)
    analyze_params: dict  # {"param_name": [value1, value2, value3, ...]}
    
    # Risk settings (fixed)
    leverage: int
    risk_per_trade: float
    fixed_amount: Optional[float]
    initial_balance: float
    
    # Analysis settings
    metric: Literal["total_return", "sharpe_ratio", "win_rate", "profit_factor", "max_drawdown"] = "total_return"
    kline_interval: str = "5m"  # Will be included in params when creating BacktestRequest


class SensitivityResult(BaseModel):
    """Results for a single parameter sensitivity analysis."""
    parameter_name: str
    base_value: Any  # Original parameter value
    tested_values: list[Any]  # Values tested
    results: list[dict]  # [{"value": X, "metric": Y, "summary": {...}, "is_invalid": bool, "is_capped": bool}]
    
    # Sensitivity metrics
    sensitivity_score: float  # How much parameter affects performance (0-1)
    optimal_value: Any  # Value that gives best metric
    worst_value: Any  # Value that gives worst metric
    impact_range: float  # Absolute difference between best and worst metric values
    impact_range_display: Optional[str] = None  # Formatted display string (e.g., "+5% improvement possible")


class SensitivityAnalysisResult(BaseModel):
    """Complete sensitivity analysis results."""
    symbol: str
    strategy_type: str
    start_time: datetime
    end_time: datetime
    kline_interval: str  # Actual kline interval used (for reproducibility)
    
    # Results for each parameter
    parameter_results: list[SensitivityResult]
    
    # Overall insights
    most_sensitive_param: str  # Parameter with highest sensitivity score
    least_sensitive_param: str  # Parameter with lowest sensitivity score
    recommended_params: dict  # Suggested parameter values based on analysis


# ============================================================================
# Metric Direction Mapping
# ============================================================================

METRIC_DIRECTIONS = {
    "total_return": True,      # Higher is better
    "sharpe_ratio": True,       # Higher is better
    "win_rate": True,          # Higher is better
    "profit_factor": True,     # Higher is better
    "max_drawdown": False,     # Lower is better (minimize drawdown)
}


# ============================================================================
# Core Functions
# ============================================================================

def calculate_sharpe_ratio(result: BacktestResult) -> Optional[float]:
    """
    Calculate Sharpe ratio from backtest result.
    
    Uses trade returns to compute Sharpe ratio.
    Returns None if insufficient data.
    """
    from app.services.walk_forward import calculate_sharpe_ratio as wf_calculate_sharpe_ratio
    
    # Reuse the walk-forward implementation
    return wf_calculate_sharpe_ratio(result)


def extract_metric_value(result: BacktestResult, metric: str) -> tuple[float, bool]:
    """
    Extract metric value from BacktestResult.
    
    Returns:
        Tuple of (metric_value, is_capped) where is_capped indicates if value was capped for storage
    """
    if metric == "total_return":
        return (result.total_return_pct, False)
    elif metric == "win_rate":
        return (result.win_rate, False)
    elif metric == "max_drawdown":
        return (result.max_drawdown_pct, False)  # Map to _pct version
    elif metric == "sharpe_ratio":
        # Calculate Sharpe ratio
        sharpe = calculate_sharpe_ratio(result)
        return (sharpe or 0.0, False)
    elif metric == "profit_factor":
        # Calculate profit factor
        winning_trades = [t for t in result.trades if t.get('net_pnl', 0) > 0]
        losing_trades = [t for t in result.trades if t.get('net_pnl', 0) <= 0]
        gross_profit = sum(t.get('net_pnl', 0) for t in winning_trades)
        gross_loss = abs(sum(t.get('net_pnl', 0) for t in losing_trades))
        
        # Fixed: Return capped value with flag for perfect profit factor
        if gross_loss == 0:
            if gross_profit > 0:
                # Perfect profit factor (infinite) - cap at reasonable value for storage
                return (99.0, True)  # Return value and is_capped flag
            else:
                # No trades or no profit/loss
                return (0.0, False)
        else:
            return (gross_profit / gross_loss, False)
    else:
        return (0.0, False)


def calculate_sensitivity_score(results: list[dict], base_metric: float = None) -> float:
    """
    Calculate how sensitive performance is to this parameter.
    
    Uses range relative to baseline as primary score (more stable than CV alone).
    Combines relative impact (70%) with CV (30%) for balanced scoring.
    
    Args:
        results: List of result dicts with "metric" key (may include invalid entries)
        base_metric: Metric value at base parameter (for relative calculation)
    
    Returns:
        Sensitivity score 0-1 (0 = no impact, 1 = high impact)
    """
    # Filter out invalid results (no trades, errors, etc.)
    valid_results = [
        r for r in results 
        if not r.get("is_invalid", False) and r.get("metric") is not None
    ]
    
    if len(valid_results) < 2:
        return 0.0  # Not enough valid data
    
    metric_values = [r["metric"] for r in valid_results]
    max_val = max(metric_values)
    min_val = min(metric_values)
    impact_range = max_val - min_val
    
    if impact_range == 0:
        return 0.0  # No variation
    
    # Primary score: Range relative to baseline (or median)
    if base_metric is not None:
        baseline = abs(base_metric)
    else:
        # Use median as baseline if base_metric not provided
        baseline = abs(statistics.median(metric_values))
    
    if baseline == 0:
        # If baseline is zero, use absolute range normalized by max absolute value
        max_abs = max(abs(max_val), abs(min_val))
        if max_abs == 0:
            return 0.0
        relative_score = min(1.0, impact_range / max_abs)
    else:
        # Relative impact score (primary)
        relative_score = min(1.0, impact_range / (baseline + 1e-9))
    
    # Secondary: CV for additional context
    mean_val = statistics.mean(metric_values)
    std_dev = statistics.stdev(metric_values) if len(metric_values) > 1 else 0
    cv = std_dev / abs(mean_val) if mean_val != 0 else 0
    cv_score = min(1.0, cv / 1.0)  # Cap CV at 1.0
    
    # Combine: 70% relative impact, 30% CV (adjustable weights)
    combined_score = 0.7 * relative_score + 0.3 * cv_score
    
    return min(1.0, combined_score)


def generate_recommendations(
    results: list[SensitivityResult],
    base_params: dict,
    sensitivity_threshold: float = 0.3
) -> dict:
    """
    Generate recommended parameter values based on sensitivity analysis.
    
    Args:
        results: List of SensitivityResult objects
        base_params: Original base parameters
        sensitivity_threshold: Minimum sensitivity score to consider for optimization
    
    Returns:
        Dictionary of recommended parameter values
    """
    recommended = base_params.copy()
    
    for result in results:
        # Only recommend changes for sensitive parameters
        if result.sensitivity_score >= sensitivity_threshold:
            # Use optimal value if it's different from base
            if result.optimal_value != result.base_value:
                recommended[result.parameter_name] = result.optimal_value
    
    return recommended


async def run_sensitivity_analysis(
    request: SensitivityAnalysisRequest,
    client: BinanceClient,
    task_id: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str, str, float], Awaitable[None]]] = None
) -> SensitivityAnalysisResult:
    """
    Run sensitivity analysis for specified parameters.
    
    For each parameter:
    1. Keep other params at base values
    2. Vary this parameter through test values
    3. Run backtest for each value
    4. Calculate sensitivity metrics
    """
    # Determine kline_interval with explicit priority and store actual value used
    if request.kline_interval:
        final_kline_interval = request.kline_interval
    elif 'kline_interval' in request.base_params:
        final_kline_interval = request.base_params['kline_interval']
    else:
        final_kline_interval = '5m'  # Default
    
    # Store the ACTUAL value used (ensures consistency between stored and used value)
    
    # Fetch klines once for all backtests (performance optimization)
    # Note: run_backtest() uses pre_fetched_klines in read-only mode (creates slices, doesn't mutate)
    # So it's safe to reuse the same klines list for all backtests
    klines = await _fetch_historical_klines(
        client=client,
        symbol=request.symbol,
        interval=final_kline_interval,  # Use final determined value
        start_time=request.start_time,
        end_time=request.end_time
    )
    
    # Run base backtest to get baseline metric (for relative sensitivity calculation)
    base_backtest_request = BacktestRequest(
        symbol=request.symbol,
        strategy_type=request.strategy_type,
        start_time=request.start_time,
        end_time=request.end_time,
        leverage=request.leverage,
        risk_per_trade=request.risk_per_trade,
        fixed_amount=request.fixed_amount,
        initial_balance=request.initial_balance,
        params=request.base_params.copy()
    )
    # Ensure kline_interval is in base params
    if final_kline_interval:
        base_backtest_request.params['kline_interval'] = final_kline_interval
    
    base_backtest_result = await run_backtest(
        base_backtest_request,
        client,
        pre_fetched_klines=klines
    )
    base_metric_value, _ = extract_metric_value(base_backtest_result, request.metric)
    
    results = []
    total_tests = sum(len(values) for values in request.analyze_params.values())
    current_test = 0
    
    for param_name, test_values in request.analyze_params.items():
        param_results = []
        
        # Update progress: starting parameter
        if progress_callback:
            await progress_callback(
                current_test,
                total_tests,
                "testing",
                f"Testing parameter: {param_name}",
                0.0
            )
        
        for test_value in test_values:
            current_test += 1
            
            # Update progress: current test
            if progress_callback:
                await progress_callback(
                    current_test,
                    total_tests,
                    "testing",
                    f"Testing {param_name}={test_value} ({current_test}/{total_tests})",
                    current_test / total_tests if total_tests > 0 else 0.0
                )
            
            try:
                # Create modified params
                test_params = request.base_params.copy()
                test_params[param_name] = test_value
                
                # Ensure kline_interval is in params (use final_kline_interval for consistency)
                if final_kline_interval:
                    test_params['kline_interval'] = final_kline_interval
                
                # Run backtest
                backtest_request = BacktestRequest(
                    symbol=request.symbol,
                    strategy_type=request.strategy_type,
                    start_time=request.start_time,
                    end_time=request.end_time,
                    leverage=request.leverage,
                    risk_per_trade=request.risk_per_trade,
                    fixed_amount=request.fixed_amount,
                    initial_balance=request.initial_balance,
                    params=test_params
                )
                
                backtest_result = await run_backtest(
                    backtest_request,
                    client,
                    pre_fetched_klines=klines  # Reuse fetched klines
                )
                
                # Handle no-trade cases (store with flag instead of skipping)
                if not backtest_result or backtest_result.total_trades == 0:
                    logger.warning(f"No trades for {param_name}={test_value}, storing as invalid")
                    
                    # Store invalid result (important for showing parameter boundaries)
                    param_results.append({
                        "value": test_value,
                        "metric": None,  # Exclude from sensitivity calculation
                        "summary": {
                            "total_trades": 0,
                            "is_invalid": True,
                            "reason": "no_trades"
                        },
                        "is_invalid": True  # Flag for visualization
                    })
                    continue
                
                # Extract metric value using helper (returns tuple: value, is_capped)
                metric_value, is_capped = extract_metric_value(backtest_result, request.metric)
                
                # Store only summary metrics (not full BacktestResult to avoid JSON/DB issues)
                summary = {
                    "total_return_pct": float(backtest_result.total_return_pct),
                    "max_drawdown_pct": float(backtest_result.max_drawdown_pct),
                    "win_rate": float(backtest_result.win_rate),
                    "total_trades": backtest_result.total_trades,
                    "completed_trades": backtest_result.completed_trades,
                    "winning_trades": backtest_result.winning_trades,
                    "losing_trades": backtest_result.losing_trades,
                    "avg_profit_per_trade": float(backtest_result.avg_profit_per_trade),
                    "largest_win": float(backtest_result.largest_win) if backtest_result.largest_win else None,
                    "largest_loss": float(backtest_result.largest_loss) if backtest_result.largest_loss else None,
                }
                
                param_results.append({
                    "value": test_value,
                    "metric": metric_value,
                    "summary": summary,
                    "is_invalid": False,
                    "is_capped": is_capped  # Flag for profit_factor visualization
                })
            except Exception as e:
                logger.error(f"Error testing {param_name}={test_value}: {e}")
                continue
        
        if not param_results:
            logger.warning(f"No valid results for parameter {param_name}")
            continue
        
        # Calculate sensitivity (with error handling)
        # Initialize all variables to prevent uninitialized variable errors
        sensitivity_score = 0.0
        optimal_value = request.base_params.get(param_name)
        worst_value = request.base_params.get(param_name)
        impact_range = 0.0
        impact_range_display = None
        
        try:
            # Fixed: calculate_sensitivity_score uses base_metric for relative calculation
            sensitivity_score = calculate_sensitivity_score(param_results, base_metric=base_metric_value)
            
            # Fixed: Use metric direction to determine optimal/worst values
            # Filter out invalid results for optimal/worst calculation
            valid_param_results = [r for r in param_results if not r.get("is_invalid", False) and r.get("metric") is not None]
            
            if not valid_param_results:
                # All results invalid - assign default values
                sensitivity_score = 0.0
                optimal_value = request.base_params.get(param_name)
                worst_value = request.base_params.get(param_name)
                impact_range = 0.0
                impact_range_display = "No valid results"
            else:
                higher_is_better = METRIC_DIRECTIONS.get(request.metric, True)
                best_fn = max if higher_is_better else min
                worst_fn = min if higher_is_better else max
                
                optimal_value = best_fn(valid_param_results, key=lambda x: x["metric"])["value"]
                worst_value = worst_fn(valid_param_results, key=lambda x: x["metric"])["value"]
                
                # Calculate impact range (absolute difference)
                metric_values = [r["metric"] for r in valid_param_results]
                impact_range = max(metric_values) - min(metric_values)
                
                # Format impact range for display based on metric direction
                if higher_is_better:
                    impact_range_display = f"+{impact_range:.2f}% improvement possible"
                else:
                    impact_range_display = f"{impact_range:.2f}% reduction possible"
        except Exception as e:
            logger.error(f"Error calculating sensitivity for {param_name}: {e}")
            sensitivity_score = 0.0
            optimal_value = request.base_params.get(param_name)
            worst_value = request.base_params.get(param_name)
            impact_range = 0.0
            impact_range_display = "Calculation error"
        
        results.append(SensitivityResult(
            parameter_name=param_name,
            base_value=request.base_params.get(param_name),
            tested_values=test_values,
            results=param_results,
            sensitivity_score=sensitivity_score,
            optimal_value=optimal_value,
            worst_value=worst_value,
            impact_range=impact_range,
            impact_range_display=impact_range_display
        ))
    
    if not results:
        raise ValueError("No valid sensitivity results generated")
    
    # Find most/least sensitive
    most_sensitive = max(results, key=lambda r: r.sensitivity_score)
    least_sensitive = min(results, key=lambda r: r.sensitivity_score)
    
    # Generate recommendations
    recommended_params = generate_recommendations(results, request.base_params)
    
    return SensitivityAnalysisResult(
        symbol=request.symbol,
        strategy_type=request.strategy_type,
        start_time=request.start_time,
        end_time=request.end_time,
        kline_interval=final_kline_interval,  # Store actual value used
        parameter_results=results,
        most_sensitive_param=most_sensitive.parameter_name,
        least_sensitive_param=least_sensitive.parameter_name,
        recommended_params=recommended_params
    )

