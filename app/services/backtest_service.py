"""
Backtest service for running strategy backtests on historical data.

This service provides the core backtesting functionality, separated from the API layer
to allow reuse by other services (e.g., auto-tuning, sensitivity analysis, walk-forward).

NOTE: Currently wraps the implementation from API routes. The full implementation
should be moved here in a future refactoring to complete the service layer separation.
"""
from __future__ import annotations

from typing import Optional
from app.core.my_binance_client import BinanceClient

# Re-export models and functions from API routes
# TODO: Move these to a shared models file or keep in service
from app.api.routes.backtesting import (
    BacktestRequest,
    BacktestResult,
    Trade,
    MockBinanceClient,
    _fetch_historical_klines,
    _calculate_backtest_statistics,
    validate_and_normalize_interval,
    _infer_interval_from_klines,
    _slice_klines_by_time_range,
    run_backtest as _run_backtest_impl,
)


class BacktestService:
    """Service for running backtests on historical data."""
    
    def __init__(self, client: BinanceClient):
        """Initialize backtest service.
        
        Args:
            client: BinanceClient instance for fetching historical data
        """
        self.client = client
    
    async def run_backtest(
        self,
        request: BacktestRequest,
        pre_fetched_klines: Optional[list[list]] = None
    ) -> BacktestResult:
        """Run backtesting on historical data.
        
        Args:
            request: Backtest request with parameters
            pre_fetched_klines: Optional pre-fetched klines to use instead of fetching
        
        Returns:
            BacktestResult with statistics and trades
        """
        return await _run_backtest_impl(request, self.client, pre_fetched_klines)


# Re-export helper functions for backward compatibility
# Other services (sensitivity_analysis, walk_forward) can import from here
async def fetch_historical_klines(
    client: BinanceClient,
    symbol: str,
    interval: str,
    start_time,
    end_time
) -> list[list]:
    """Fetch historical klines with pagination support."""
    return await _fetch_historical_klines(client, symbol, interval, start_time, end_time)


def calculate_backtest_statistics(
    trades: list[Trade],
    initial_balance: float,
    final_balance: float
) -> dict:
    """Calculate backtest statistics from completed trades."""
    return _calculate_backtest_statistics(trades, initial_balance, final_balance)


def normalize_interval(
    interval: str,
    strategy_type: str,
    default_interval: Optional[str] = None
) -> str:
    """Validate and normalize Binance kline interval."""
    return validate_and_normalize_interval(interval, strategy_type, default_interval)


def infer_interval_from_klines(klines: list[list]) -> Optional[str]:
    """Infer kline interval from klines data."""
    return _infer_interval_from_klines(klines)


def slice_klines_by_time_range(
    klines: list[list],
    start_time,
    end_time
) -> list[list]:
    """Slice klines to include only those within the specified time range."""
    return _slice_klines_by_time_range(klines, start_time, end_time)


# Convenience function for direct use (maintains backward compatibility)
async def run_backtest(
    request: BacktestRequest,
    client: BinanceClient,
    pre_fetched_klines: Optional[list[list]] = None
) -> BacktestResult:
    """Run backtesting on historical data (convenience function).
    
    This function maintains backward compatibility with existing code.
    For new code, prefer using BacktestService.run_backtest().
    
    Args:
        request: Backtest request with parameters
        client: BinanceClient instance
        pre_fetched_klines: Optional pre-fetched klines to use instead of fetching
    
    Returns:
        BacktestResult with statistics and trades
    """
    service = BacktestService(client)
    return await service.run_backtest(request, pre_fetched_klines)





