"""
Backtesting API endpoint for strategy performance analysis on historical data.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from statistics import fmean
from typing import Optional, Literal, TYPE_CHECKING, Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.services.walk_forward import WalkForwardRequest, WalkForwardResult

from app.api.deps import get_binance_client, get_current_user_async
from app.core.my_binance_client import BinanceClient
from app.core.config import get_settings
from app.strategies.base import StrategyContext, StrategySignal
from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.range_mean_reversion import RangeMeanReversionStrategy
from app.strategies.indicators import calculate_ema, calculate_rsi
from app.risk.manager import RiskManager, PositionSizingResult
from app.utils.backtest_params import (
    extract_range_mean_reversion_params,
    extract_scalping_params,
    calculate_range_tp_sl_levels
)
from loguru import logger


router = APIRouter(prefix="/backtesting", tags=["backtesting"])


# Binance futures fee rates (average between maker and taker)
MAKER_FEE_RATE = 0.0002  # 0.02%
TAKER_FEE_RATE = 0.0004  # 0.04%
AVERAGE_FEE_RATE = 0.0003  # 0.03% average

# Spread offset to simulate bid/ask spread in live trading
SPREAD_OFFSET = 0.0002  # 0.02% - simulates real bid/ask difference


class BacktestRequest(BaseModel):
    """Request model for backtesting."""
    symbol: str
    strategy_type: Literal["scalping", "range_mean_reversion"]
    start_time: datetime
    end_time: datetime
    leverage: int = Field(ge=1, le=50, default=5)
    risk_per_trade: float = Field(gt=0, lt=1, default=0.01)
    fixed_amount: Optional[float] = Field(default=None, gt=0)
    initial_balance: float = Field(gt=0, default=1000.0)  # Starting balance in USDT
    params: dict = Field(default_factory=dict)  # Strategy-specific parameters
    include_klines: bool = Field(default=True, description="Include klines in response (set False to reduce payload size)")


class Trade(BaseModel):
    """Represents a single trade in backtesting."""
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    position_side: Literal["LONG", "SHORT"]
    quantity: float
    notional: float
    entry_fee: float
    exit_fee: Optional[float]
    pnl: Optional[float]  # Gross PnL (before fees)
    net_pnl: Optional[float]  # Net PnL (after fees)
    exit_reason: Optional[str]
    is_open: bool = True


class BacktestResult(BaseModel):
    """Backtesting results."""
    symbol: str
    strategy_type: str
    start_time: datetime
    end_time: datetime
    initial_balance: float
    final_balance: float
    total_pnl: float
    total_return_pct: float
    total_trades: int
    completed_trades: int
    open_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_fees: float
    avg_profit_per_trade: float
    largest_win: float
    largest_loss: float
    max_drawdown: float
    max_drawdown_pct: float
    trades: list[dict]  # List of trade details
    klines: Optional[list[list]] = None  # Historical candlestick data for charting
    indicators: Optional[dict] = None  # Indicator data (EMA fast/slow) for charting


class MockBinanceClient:
    """Mock Binance client for backtesting that uses historical prices."""
    
    def __init__(self, klines: list[list], current_index: int = 0, initial_balance: float = 1000.0):
        self.klines = klines
        self.current_index = current_index
        self.balance = initial_balance  # Track balance for futures_account_balance()
    
    def get_price(self, symbol: str) -> float:
        """Get current price from historical klines."""
        if self.current_index < len(self.klines):
            # Return close price of current candle
            return float(self.klines[self.current_index][4])  # close price
        # If past end, return last price
        return float(self.klines[-1][4]) if self.klines else 0.0
    
    def get_klines(self, symbol: str, interval: str, limit: int = 1000, start_time: Optional[int] = None, end_time: Optional[int] = None) -> list[list]:
        """
        Return historical klines up to current_index.
        
        This allows the strategy to see all klines up to the current candle being processed.
        The strategy will treat klines[:-1] as closed candles and klines[-1] as the forming candle.
        """
        # Return klines up to and including current_index
        # This avoids expensive monkey-patching on every iteration
        return self.klines[:self.current_index + 1]
    
    def get_min_notional(self, symbol: str) -> float:
        """Get minimum notional value (default: 5.0 USDT for backtesting)."""
        return 5.0
    
    def get_quantity_precision(self, symbol: str) -> int:
        """Get quantity precision (default: 8 decimals for backtesting)."""
        return 8
    
    def round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to the correct precision for the symbol."""
        precision = self.get_quantity_precision(symbol)
        return round(quantity, precision)
    
    def futures_account_balance(self) -> float:
        """Get USDT balance from futures account (returns current backtest balance)."""
        return self.balance
    
    def update_balance(self, new_balance: float) -> None:
        """Update the tracked balance (called after each trade)."""
        self.balance = new_balance


def _calculate_backtest_statistics(
    trades: list[Trade],
    initial_balance: float,
    final_balance: float
) -> dict:
    """Calculate backtest statistics from completed trades.
    
    Args:
        trades: List of all trades (completed and open)
        initial_balance: Starting balance
        final_balance: Ending balance
        
    Returns:
        Dictionary with calculated statistics
    """
    completed_trades = [t for t in trades if not t.is_open]
    open_trades = [t for t in trades if t.is_open]
    
    total_pnl = final_balance - initial_balance
    total_return_pct = (total_pnl / initial_balance) * 100 if initial_balance > 0 else 0
    
    winning_trades = [t for t in completed_trades if t.net_pnl and t.net_pnl > 0]
    losing_trades = [t for t in completed_trades if t.net_pnl and t.net_pnl <= 0]
    
    win_rate = (len(winning_trades) / len(completed_trades) * 100) if completed_trades else 0.0
    
    total_fees = sum((t.entry_fee + (t.exit_fee or 0)) for t in trades)
    
    avg_profit_per_trade = sum((t.net_pnl or 0) for t in completed_trades) / len(completed_trades) if completed_trades else 0.0
    
    largest_win = max((t.net_pnl or 0) for t in completed_trades) if completed_trades else 0.0
    largest_loss = min((t.net_pnl or 0) for t in completed_trades) if completed_trades else 0.0
    
    return {
        "completed_trades": completed_trades,
        "open_trades": open_trades,
        "total_pnl": total_pnl,
        "total_return_pct": total_return_pct,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_fees": total_fees,
        "avg_profit_per_trade": avg_profit_per_trade,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
    }


async def _fetch_historical_klines(
    client: BinanceClient,
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime
) -> list[list]:
    """Fetch historical klines with pagination support for large time ranges.
    
    Binance API limits: Maximum 1000 candles per request.
    This function implements pagination to fetch all data for large time ranges
    (e.g., 30 days of 1-minute klines = ~43,200 candles).
    
    Args:
        client: BinanceClient instance
        symbol: Trading symbol (e.g., 'BTCUSDT')
        interval: Kline interval (e.g., '1m', '5m', '1h')
        start_time: Start time (timezone-aware datetime)
        end_time: End time (timezone-aware datetime)
        
    Returns:
        List of klines in Binance format, sorted by timestamp
        
    Raises:
        HTTPException: If klines cannot be fetched or insufficient data
    """
    start_timestamp = int(start_time.timestamp() * 1000)
    end_timestamp = int(end_time.timestamp() * 1000)
    
    # Log fetch operation
    logger.info(
        f"Fetching klines from Binance: {symbol} {interval} "
        f"({start_time} to {end_time})"
    )
    
    # Calculate how many candles we need
    # NOTE: Seconds intervals (1s, 3s, etc.) are NOT supported by standard Binance klines endpoint
    interval_seconds_map = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200,
        "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2592000  # Approximate month = 30 days
    }
    interval_seconds = interval_seconds_map.get(interval, 60)
    duration_seconds = (end_timestamp - start_timestamp) / 1000
    estimated_candles = int(duration_seconds / interval_seconds) + 200  # Add buffer
    
    # Binance API limit: 1000 candles per request
    MAX_KLINES_PER_REQUEST = 1000
    
    # Fetch historical klines with pagination
    all_klines = []
    try:
        # Use python-binance client directly for historical data
        rest = client._ensure()
        
        # Check if we need pagination
        # Use pagination if estimated_candles > 500 to avoid issues with default limits
        # This ensures we get all data reliably, even if the estimate is slightly off
        needs_pagination = estimated_candles > 500
        
        if needs_pagination:
            logger.info(
                f"Large time range detected: ~{estimated_candles} candles needed. "
                f"Using pagination to fetch data in chunks of {MAX_KLINES_PER_REQUEST}."
            )
            
            # Pagination: Fetch data in chunks
            current_start = start_timestamp
            chunk_count = 0
            max_chunks = (estimated_candles // MAX_KLINES_PER_REQUEST) + 10  # Safety limit
            
            while current_start < end_timestamp and chunk_count < max_chunks:
                chunk_count += 1
                
                # Calculate end time for this chunk (current_start + MAX_KLINES_PER_REQUEST candles)
                chunk_end_timestamp = min(
                    current_start + (MAX_KLINES_PER_REQUEST * interval_seconds * 1000),
                    end_timestamp
                )
                
                try:
                    logger.debug(
                        f"Fetching chunk {chunk_count}: {current_start} to {chunk_end_timestamp} "
                        f"(~{MAX_KLINES_PER_REQUEST} candles)"
                    )
                    
                    # Fetch chunk
                    chunk_klines = rest.futures_klines(
                        symbol=symbol,
                        interval=interval,
                        limit=MAX_KLINES_PER_REQUEST,
                        startTime=current_start,
                        endTime=chunk_end_timestamp
                    )
                    
                    if not chunk_klines:
                        logger.warning(f"No data returned for chunk {chunk_count}, stopping pagination")
                        break
                    
                    # Filter to ensure we're within time range
                    filtered_chunk = [
                        k for k in chunk_klines
                        if start_timestamp <= int(k[0]) <= end_timestamp
                    ]
                    
                    if not filtered_chunk:
                        logger.warning(f"Chunk {chunk_count} had no data in time range, stopping pagination")
                        break
                    
                    all_klines.extend(filtered_chunk)
                    logger.debug(f"Chunk {chunk_count}: Added {len(filtered_chunk)} klines (total: {len(all_klines)})")
                    
                    # Move to next chunk: start from the last candle's timestamp + 1 interval
                    last_candle_time = int(chunk_klines[-1][0])
                    current_start = last_candle_time + (interval_seconds * 1000)
                    
                    # If we got fewer candles than requested, we've reached the end
                    if len(chunk_klines) < MAX_KLINES_PER_REQUEST:
                        logger.debug(f"Received {len(chunk_klines)} candles (less than {MAX_KLINES_PER_REQUEST}), reached end of data")
                        break
                        
                except Exception as chunk_error:
                    logger.error(f"Error fetching chunk {chunk_count}: {chunk_error}")
                    # Continue with next chunk if possible
                    if chunk_count >= 3:  # Stop after 3 consecutive errors
                        raise
                    current_start += (MAX_KLINES_PER_REQUEST * interval_seconds * 1000)
                    continue
            
            logger.info(f"Pagination complete: Fetched {len(all_klines)} klines in {chunk_count} chunks")
            
        else:
            # Single request should be sufficient, but use pagination if estimated_candles > 500
            # This ensures we get all data even if the estimate is slightly off
            # Note: futures_historical_klines has unreliable limits, so we always use futures_klines with explicit limit
            logger.info(f"Fetching historical klines for {symbol} using timestamps: {start_timestamp} to {end_timestamp} (UTC)")
            
            try:
                # Always use futures_klines with explicit limit for reliability
                # futures_historical_klines can have default limits that cause incomplete data
                limit = min(estimated_candles, MAX_KLINES_PER_REQUEST)
                klines = rest.futures_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=limit,
                    startTime=start_timestamp,
                    endTime=end_timestamp
                )
                if klines:
                    all_klines = [
                        k for k in klines
                        if start_timestamp <= int(k[0]) <= end_timestamp
                    ]
                    logger.info(f"Fetched {len(all_klines)} klines within time range using futures_klines with timestamps (limit={limit})")
                    
                    # CRITICAL: Check if we got enough data
                    # If we got fewer candles than expected and didn't reach the end time, we need pagination
                    if len(all_klines) < estimated_candles * 0.9:  # Allow 10% tolerance
                        last_kline_time = int(all_klines[-1][0]) if all_klines else start_timestamp
                        # If we haven't reached the end time and got exactly the limit, we need more data
                        if last_kline_time < end_timestamp - (interval_seconds * 1000) and len(all_klines) >= limit - 10:
                            logger.warning(
                                f"Received {len(all_klines)} klines but need more data. "
                                f"Last kline: {last_kline_time}, End time: {end_timestamp}. "
                                f"Switching to pagination mode."
                            )
                            # Switch to pagination mode
                            current_start = last_kline_time + (interval_seconds * 1000)
                            chunk_count = 1
                            max_chunks = 100  # Safety limit
                            
                            while current_start < end_timestamp and chunk_count < max_chunks:
                                chunk_count += 1
                                chunk_end_timestamp = min(
                                    current_start + (MAX_KLINES_PER_REQUEST * interval_seconds * 1000),
                                    end_timestamp
                                )
                                
                                try:
                                    logger.debug(
                                        f"Fetching additional chunk {chunk_count}: {current_start} to {chunk_end_timestamp}"
                                    )
                                    chunk_klines = rest.futures_klines(
                                        symbol=symbol,
                                        interval=interval,
                                        limit=MAX_KLINES_PER_REQUEST,
                                        startTime=current_start,
                                        endTime=chunk_end_timestamp
                                    )
                                    
                                    if not chunk_klines:
                                        break
                                    
                                    # Get existing timestamps to avoid duplicates
                                    existing_timestamps = {int(k[0]) for k in all_klines}
                                    filtered_chunk = [
                                        k for k in chunk_klines
                                        if start_timestamp <= int(k[0]) <= end_timestamp and int(k[0]) not in existing_timestamps
                                    ]
                                    
                                    if not filtered_chunk:
                                        break
                                    
                                    all_klines.extend(filtered_chunk)
                                    logger.debug(f"Chunk {chunk_count}: Added {len(filtered_chunk)} klines (total: {len(all_klines)})")
                                    
                                    last_candle_time = int(chunk_klines[-1][0])
                                    current_start = last_candle_time + (interval_seconds * 1000)
                                    
                                    if len(chunk_klines) < MAX_KLINES_PER_REQUEST:
                                        break
                                        
                                except Exception as chunk_error:
                                    logger.error(f"Error fetching chunk {chunk_count}: {chunk_error}")
                                    break
                            
                            logger.info(f"Pagination complete: Total {len(all_klines)} klines fetched")
                else:
                    all_klines = []
                        
            except Exception as e:
                logger.error(f"Error in single-request klines fetch: {e}")
                raise
    
    except Exception as e:
        logger.error(f"Error fetching historical klines: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch historical data: {e}"
        )
    
    # PERFORMANCE FIX: Optimize duplicate removal and sorting
    # Use dict to deduplicate by timestamp in one pass (preserves last occurrence)
    # Then sort if needed (Binance API usually returns sorted, but ensure consistency)
    if all_klines:
        # Use dict to deduplicate by timestamp (O(N) instead of O(N log N))
        # Dict preserves insertion order (Python 3.7+), so if already sorted, stays sorted
        unique_klines_dict = {}
        for k in all_klines:
            timestamp = int(k[0])
            unique_klines_dict[timestamp] = k  # Last occurrence wins
        
        # Convert to sorted list (O(N log N) but only once, not per iteration)
        all_klines = sorted(unique_klines_dict.values(), key=lambda k: int(k[0]))
    
    logger.info(f"Fetched {len(all_klines)} total unique klines from Binance (requested ~{estimated_candles})")
    
    if len(all_klines) < 50:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient historical data: only {len(all_klines)} candles available. Need at least 50. "
                   f"Requested time range: {start_time} to {end_time} ({estimated_candles} estimated candles)."
        )
    
    # Filter klines to requested time range
    filtered_klines = [
        k for k in all_klines
        if start_timestamp <= int(k[0]) <= end_timestamp
    ]
    
    logger.info(f"Filtered to {len(filtered_klines)} klines in time range {start_time} to {end_time}")
    
    if not filtered_klines:
        raise HTTPException(
            status_code=400,
            detail="No klines found in the specified time range"
        )
    
    return filtered_klines


def validate_and_normalize_interval(
    interval: str,
    strategy_type: str,
    default_interval: Optional[str] = None
) -> str:
    """
    Validate and normalize Binance kline interval.
    
    NOTE: Seconds intervals (1s, 3s, etc.) are NOT supported by standard Binance klines endpoint.
    
    Args:
        interval: Interval string (may be comma-separated from optimization params)
        strategy_type: Strategy type for default fallback
        default_interval: Optional default interval (overrides strategy-based default)
    
    Returns:
        Validated and normalized interval string
    """
    # Valid Binance intervals (excluding seconds which are not supported)
    valid_intervals = {
        "1m", "3m", "5m", "15m", "30m",  # Minute-based
        "1h", "2h", "4h", "6h", "8h", "12h",  # Hour-based
        "1d", "3d", "1w", "1M"  # Day/week/month-based
    }
    
    # Determine default if not provided
    if default_interval is None:
        default_interval = "1m" if strategy_type == "scalping" else "5m"
    
    # If interval is a list/comma string (from optimization params), extract first valid one
    if isinstance(interval, str) and ("," in interval or interval not in valid_intervals):
        if "," in interval:
            # Split and take first valid interval
            parts = [p.strip() for p in interval.split(",")]
            interval = next((p for p in parts if p in valid_intervals), None)
            if interval is None:
                logger.warning(
                    f"Invalid interval in params, using default: {default_interval}. "
                    f"Note: Interval optimization requires separate datasets per interval."
                )
                return default_interval
        else:
            # Invalid single interval, use default
            logger.warning(f"Invalid interval '{interval}', using default: {default_interval}")
            return default_interval
    
    # Ensure interval is valid
    if interval not in valid_intervals:
        logger.warning(f"Invalid interval '{interval}', using default: {default_interval}")
        return default_interval
    
    return interval


def _infer_interval_from_klines(klines: list[list]) -> Optional[str]:
    """
    Infer kline interval from klines data by calculating time difference between candles.
    
    Args:
        klines: List of klines in Binance format (at least 2 klines needed)
    
    Returns:
        Interval string (e.g., "1m", "5m", "1h") or None if cannot be determined
    """
    if len(klines) < 2:
        return None
    
    # Calculate time difference between first two candles (in milliseconds)
    time_diff_ms = int(klines[1][0]) - int(klines[0][0])
    time_diff_seconds = time_diff_ms / 1000
    
    # Map common intervals (in seconds)
    interval_map = {
        60: "1m",
        180: "3m",
        300: "5m",
        900: "15m",
        1800: "30m",
        3600: "1h",
        7200: "2h",
        14400: "4h",
        21600: "6h",
        28800: "8h",
        43200: "12h",
        86400: "1d",
        259200: "3d",
        604800: "1w",
        2592000: "1M"  # Approximate
    }
    
    # Find closest match (allow tolerance for rounding/API variations)
    # Use a more lenient tolerance: within 20% or 5 seconds, whichever is larger
    for interval_sec, interval_str in sorted(interval_map.items()):
        tolerance = max(interval_sec * 0.2, 5)  # 20% or 5 seconds, whichever is larger
        if abs(time_diff_seconds - interval_sec) <= tolerance:
            return interval_str
    
    # If no exact match, return None (caller should handle)
    return None


def _slice_klines_by_time_range(
    klines: list[list],
    start_time: datetime,
    end_time: datetime
) -> list[list]:
    """
    Slice klines to include only those within the specified time range.
    
    Binance kline format: [open_time, open, high, low, close, volume, close_time, ...]
    - k[0] = open_time (candle start)
    - k[6] = close_time (candle end)
    
    Boundary handling:
    - Include candles with open_time >= start_time (inclusive start)
    - Include candles with close_time <= end_time (inclusive end)
    This ensures we don't cut the last candle unexpectedly.
    
    Args:
        klines: List of klines in Binance format
        start_time: Start time (timezone-aware datetime) - inclusive
        end_time: End time (timezone-aware datetime) - inclusive
    
    Returns:
        Filtered list of klines within the time range
    """
    start_timestamp = int(start_time.timestamp() * 1000)
    end_timestamp = int(end_time.timestamp() * 1000)
    
    filtered = [
        k for k in klines
        if int(k[0]) >= start_timestamp and int(k[6]) <= end_timestamp
    ]
    
    return filtered


async def run_backtest(
    request: BacktestRequest,
    client: BinanceClient,
    pre_fetched_klines: Optional[list[list]] = None
) -> BacktestResult:
    """Run backtesting on historical data.
    
    Args:
        request: Backtest request with parameters
        client: BinanceClient instance (used if pre_fetched_klines is None)
        pre_fetched_klines: Optional pre-fetched klines to use instead of fetching
    
    Returns:
        BacktestResult with statistics and trades
    """
    # Ensure start_time and end_time are timezone-aware (UTC)
    if request.start_time.tzinfo is None:
        request.start_time = request.start_time.replace(tzinfo=timezone.utc)
    if request.end_time.tzinfo is None:
        request.end_time = request.end_time.replace(tzinfo=timezone.utc)
    
    # CRITICAL: When pre_fetched_klines is provided, infer interval from data
    # to avoid mismatch with request.params (which may be wrong/different)
    # When fetching, use interval from params as normal
    if pre_fetched_klines is not None:
        # Infer interval from pre-fetched klines data
        inferred_interval = _infer_interval_from_klines(pre_fetched_klines)
        if inferred_interval:
            interval = inferred_interval
            logger.debug(f"Inferred interval from pre-fetched klines: {interval}")
        else:
            # Fallback: use params if inference fails (shouldn't happen with valid data)
            raw_interval = request.params.get("kline_interval", "1m" if request.strategy_type == "scalping" else "5m")
            interval = validate_and_normalize_interval(raw_interval, request.strategy_type)
            logger.warning(
                f"Could not infer interval from pre-fetched klines, using params: {interval}. "
                f"This may cause incorrect interval_seconds calculation."
            )
        
        # PERFORMANCE: Pre-fetched klines are already sliced for the correct time range
        # Do NOT re-slice here to avoid double work (especially important in grid search)
        # The caller (walk_forward.py) is responsible for slicing before passing
        filtered_klines = pre_fetched_klines
        logger.debug(
            f"Using pre-fetched klines: {len(filtered_klines)} candles "
            f"(range: {request.start_time} to {request.end_time}, interval: {interval})"
        )
        if not filtered_klines:
            raise HTTPException(
                status_code=400,
                detail=f"No klines found in pre-fetched data for time range {request.start_time} to {request.end_time}"
            )
    else:
        # Fetch historical klines - use interval from params
        raw_interval = request.params.get("kline_interval", "1m" if request.strategy_type == "scalping" else "5m")
        interval = validate_and_normalize_interval(raw_interval, request.strategy_type)
        logger.debug(f"Fetching klines from Binance for range: {request.start_time} to {request.end_time}, interval: {interval}")
        filtered_klines = await _fetch_historical_klines(
            client=client,
            symbol=request.symbol,
            interval=interval,
            start_time=request.start_time,
            end_time=request.end_time
        )
        logger.debug(f"Fetched {len(filtered_klines)} klines from Binance")
    
    # Calculate interval_seconds for strategy context (using the correct interval)
    # NOTE: Seconds intervals (1s, 3s, etc.) are NOT supported by standard Binance klines endpoint
    interval_seconds_map = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200,
        "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2592000  # Approximate month = 30 days
    }
    interval_seconds = interval_seconds_map.get(interval, 60)
    
    # Create strategy context
    context = StrategyContext(
        id="backtest",
        name="Backtest Strategy",
        symbol=request.symbol,
        leverage=request.leverage,
        risk_per_trade=request.risk_per_trade,
        params=request.params,
        interval_seconds=interval_seconds
    )
    
    # Create mock client for strategy (with initial balance)
    mock_client = MockBinanceClient(filtered_klines, initial_balance=request.initial_balance)
    
    # Create strategy instance
    if request.strategy_type == "scalping":
        strategy = EmaScalpingStrategy(context, mock_client)
    elif request.strategy_type == "range_mean_reversion":
        strategy = RangeMeanReversionStrategy(context, mock_client)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown strategy type: {request.strategy_type}")
    
    # Initialize risk manager
    risk_manager = RiskManager(mock_client)
    
    # Backtesting state
    balance = request.initial_balance
    trades: list[Trade] = []
    current_trade: Optional[Trade] = None
    equity_curve = [balance]  # Track balance over time
    peak_balance = balance
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    
    # Track strategy's position state for TP/SL calculation
    strategy_position: Optional[Literal["LONG", "SHORT"]] = None
    strategy_entry_price: Optional[float] = None
    
    # Track if position was just closed in current iteration (to prevent immediate re-entry)
    position_just_closed_this_iteration = False
    
    # Process each candle
    # Calculate minimum required candles based on strategy type
    # PERFORMANCE FIX: Pre-calculate closing prices once (O(N)) instead of recalculating in loop (O(N²))
    closing_prices_all = [float(k[4]) for k in filtered_klines]
    
    # CODE QUALITY FIX: Extract parameters using utility functions to reduce duplication
    if request.strategy_type == "range_mean_reversion":
        rmr_params = extract_range_mean_reversion_params(request.params)
        lookback = rmr_params["lookback_period"]
        ema_slow = rmr_params["ema_slow_period"]
        rsi_p = rmr_params["rsi_period"]
        rsi_period = rmr_params["rsi_period"]
        ema_fast_period = rmr_params["ema_fast_period"]
        ema_slow_period = rmr_params["ema_slow_period"]
        min_required_candles = max(lookback + 1, ema_slow + 1, rsi_p + 1)
        logger.info(f"Starting backtest: Processing {len(filtered_klines)} candles for {request.symbol} from {request.start_time} to {request.end_time}")
        logger.info(f"Strategy: {request.strategy_type}, Params: {request.params}")
        logger.info(f"Range mean reversion requires: lookback={lookback}, ema_slow={ema_slow}, rsi_period={rsi_p}. Will start evaluating after {min_required_candles} candles.")
    else:
        # Scalping strategy
        scalping_params = extract_scalping_params(request.params)
        slow_period = scalping_params["ema_slow"]
        fast_period = scalping_params["ema_fast"]
        min_required_candles = slow_period + 1  # Need slow_period for EMA + 1 forming candle
        logger.info(f"Starting backtest: Processing {len(filtered_klines)} candles for {request.symbol} from {request.start_time} to {request.end_time}")
        logger.info(f"Strategy: {request.strategy_type}, Params: {request.params}")
        logger.info(f"EMA periods: Fast={fast_period}, Slow={slow_period}. Will start evaluating after {min_required_candles} candles for stable EMAs.")
    
    # Track signal statistics
    signal_counts = {"BUY": 0, "SELL": 0, "HOLD": 0, "CLOSE": 0, "ERROR": 0}
    
    # Track indicator data for range mean reversion charting
    range_indicator_snapshots = []  # List of indicator snapshots per candle
    
    for i, kline in enumerate(filtered_klines):
        mock_client.current_index = i
        
        # Reset flag at start of each iteration
        position_just_closed_this_iteration = False
        
        # Get current price (close price of current candle)
        current_price = float(kline[4])
        # Convert kline timestamp to timezone-aware datetime (UTC)
        candle_time = datetime.fromtimestamp(int(kline[0]) / 1000, tz=timezone.utc)
        
        # Update strategy's klines (feed it all klines up to current)
        # Strategy needs enough history for indicators, so provide all klines up to current
        # IMPORTANT: The strategy expects the last kline to be "forming" (not closed)
        # Strategy does: closed_klines = klines[:-1] and last_closed = closed_klines[-1]
        # This requires at least 2 klines: one closed (klines[0]) and one forming (klines[1])
        # min_required_candles was already calculated before the loop - reuse it here
        if i < min_required_candles:
            # Not enough klines yet - need at least required periods + 1 for stable indicators
            continue
        
        # Update mock_client.current_index so get_klines() returns the correct subset
        # This avoids expensive monkey-patching on every iteration
        # get_klines() will return klines[:current_index+1], where:
        # - klines[:-1] = all closed candles
        # - klines[-1] = current forming candle (klines[i])
        
        try:
            # Evaluate strategy (get_klines() will automatically return klines up to current_index)
            signal = await strategy.evaluate()
            # Track signal counts
            signal_counts[signal.action] = signal_counts.get(signal.action, 0) + 1
            # Log non-HOLD signals at DEBUG level (per-candle logging is expensive)
            # Trade events (entry/exit) are logged at INFO level below
            if signal.action != "HOLD":
                logger.debug(f"Candle {i}/{len(filtered_klines)}: {signal.action} signal at {current_price:.8f} (confidence: {signal.confidence:.2f}), current_trade={current_trade is not None}")
                # Detailed signal debugging at DEBUG level
                logger.debug(f"  -> Signal type: {type(signal.action)}, value: '{signal.action}', repr: {repr(signal.action)}")
                logger.debug(f"  -> Signal will be processed: {signal.action in ('BUY', 'SELL')}, current_trade is None: {current_trade is None}")
            # Log HOLD signals at DEBUG level (per-candle logging is expensive)
            # Progress is tracked via SSE, so verbose logging not needed
            elif i < 10 or i % 100 == 0:
                logger.debug(f"Candle {i}/{len(filtered_klines)}: {signal.action} at {current_price:.8f} (confidence: {signal.confidence:.2f})")
        except IndexError as e:
            # This happens when closed_klines is empty (i.e., only 1 kline provided)
            current_klines_count = len(mock_client.get_klines(request.symbol, ""))
            logger.error(f"IndexError at candle {i}: {e}. Need at least 2 klines. Provided {current_klines_count} klines.")
            continue  # Skip this candle
        except Exception as e:
            logger.error(f"Error evaluating strategy at candle {i}: {type(e).__name__}: {e}", exc_info=True)
            signal_counts["ERROR"] += 1
            signal = StrategySignal(
                action="HOLD",
                symbol=request.symbol,
                confidence=0.0,
                price=current_price
            )
        
        # Capture indicator snapshot for range mean reversion
        if request.strategy_type == "range_mean_reversion" and i >= min_required_candles:
            # ALIGNMENT FIX: Use current candle's timestamp for snapshot, but indicators calculated
            # from closed candles up to i-1 (no lookahead). This represents the state "at the start
            # of candle i" using only information available from closed candles.
            snapshot_timestamp = int(kline[0]) // 1000  # Current candle's timestamp
            snapshot = {
                "time": snapshot_timestamp,
                "range_high": None,
                "range_low": None,
                "range_mid": None,
                "range_valid": False,
                "rsi": None,
                "ema_fast": None,
                "ema_slow": None,
                "ema_spread_pct": None,
                "buy_zone_upper": None,
                "sell_zone_lower": None,
                "tp1": None,
                "tp2": None,
                "sl": None,
                "position_side": None
            }
            
            # Capture range state
            if hasattr(strategy, 'range_valid') and hasattr(strategy, 'range_high') and \
               hasattr(strategy, 'range_low') and hasattr(strategy, 'range_mid'):
                snapshot["range_valid"] = strategy.range_valid
                snapshot["range_high"] = strategy.range_high
                snapshot["range_low"] = strategy.range_low
                snapshot["range_mid"] = strategy.range_mid
                
                # Calculate entry zones if range is valid
                if strategy.range_valid and strategy.range_high is not None and strategy.range_low is not None:
                    range_size = strategy.range_high - strategy.range_low
                    buy_zone_pct = rmr_params["buy_zone_pct"]
                    sell_zone_pct = rmr_params["sell_zone_pct"]
                    snapshot["buy_zone_upper"] = strategy.range_low + (range_size * buy_zone_pct)
                    snapshot["sell_zone_lower"] = strategy.range_high - (range_size * sell_zone_pct)
                    
                    # CODE QUALITY FIX: Use utility function for TP/SL calculation
                    if hasattr(strategy, 'position') and strategy.position is not None:
                        snapshot["position_side"] = strategy.position
                        tp_sl_levels = calculate_range_tp_sl_levels(
                            range_high=strategy.range_high,
                            range_low=strategy.range_low,
                            range_mid=strategy.range_mid,
                            position_side=strategy.position,
                            tp_buffer_pct=rmr_params["tp_buffer_pct"],
                            sl_buffer_pct=rmr_params["sl_buffer_pct"]
                        )
                        snapshot["tp1"] = tp_sl_levels["tp1"]
                        snapshot["tp2"] = tp_sl_levels["tp2"]
                        snapshot["sl"] = tp_sl_levels["sl"]
            
            # Calculate RSI and EMA if we have enough data
            # PERFORMANCE FIX: Use pre-calculated closing_prices_all with O(1) slice instead of O(i) list comprehension
            # CRITICAL FIX: Use only closed candles (up to i-1) for indicators
            # Decision was made on candle i-1, so indicators should not include candle i's close (future data)
            if i >= min_required_candles:
                # Use pre-calculated prices with O(1) slice operation (much faster than list comprehension)
                closing_prices = closing_prices_all[:i]  # Only closed candles, up to i-1
                
                # Calculate RSI
                if len(closing_prices) >= rsi_period + 1:
                    snapshot["rsi"] = calculate_rsi(closing_prices, rsi_period)
                
                # Calculate EMA fast and slow (reuse same closing_prices variable - no redundant calculation)
                if len(closing_prices) >= ema_fast_period:
                    snapshot["ema_fast"] = calculate_ema(closing_prices, ema_fast_period)
                if len(closing_prices) >= ema_slow_period:
                    snapshot["ema_slow"] = calculate_ema(closing_prices, ema_slow_period)
                
                # Calculate EMA spread percentage
                if snapshot["ema_fast"] is not None and snapshot["ema_slow"] is not None:
                    ema_mid = (snapshot["ema_fast"] + snapshot["ema_slow"]) / 2
                    if ema_mid > 0:
                        snapshot["ema_spread_pct"] = abs(snapshot["ema_fast"] - snapshot["ema_slow"]) / ema_mid
            
            range_indicator_snapshots.append(snapshot)
            
        # Check for TP/SL on open position
        # CRITICAL: Use high/low prices to check if TP/SL was hit during the candle
        # This simulates live trading where TP/SL can be hit mid-candle
        # Also ensure we're within backtest time range
        if current_trade and current_trade.is_open and request.start_time <= candle_time <= request.end_time:
            entry_price = current_trade.entry_price
            position_side = current_trade.position_side
            
            # Get high and low prices from current candle
            # Kline structure: [open_time, open, high, low, close, volume, close_time, ...]
            candle_high = float(kline[2])
            candle_low = float(kline[3])
            
            # First, check if strategy signal indicates an exit (e.g., trailing stop, TP/SL)
            # This handles trailing stop exits and other strategy-detected exits
            exit_price = None
            exit_reason = None
            
            if signal.exit_reason:
                # Strategy detected an exit (trailing stop, TP, SL, etc.)
                # Use signal price if available, otherwise check if it was hit during candle
                if signal.price is not None:
                    exit_price = signal.price
                else:
                    # Strategy detected exit but no price - check if it was hit during candle
                    exit_price = current_price  # Fallback to close price
                exit_reason = signal.exit_reason
                # Log trailing stop exits specifically for debugging
                if "TRAILING" in exit_reason:
                    logger.info(f"✅ Trailing stop exit detected: {exit_reason} at price {exit_price:.8f} (strategy signal)")
                else:
                    logger.info(f"Strategy detected exit: {exit_reason} at price {exit_price:.8f}")
            elif signal.action in ("SELL", "BUY"):
                # Check if signal action matches closing the current position
                # SELL signal when LONG is open, or BUY signal when SHORT is open
                if (signal.action == "SELL" and position_side == "LONG") or \
                   (signal.action == "BUY" and position_side == "SHORT"):
                    # Signal indicates closing the position
                    exit_price = signal.price if signal.price is not None else current_price
                    exit_reason = signal.exit_reason or "SIGNAL_CLOSE"
                    logger.info(f"Signal action {signal.action} closes {position_side} position at price {exit_price:.8f}")
            elif request.strategy_type == "scalping":
                # For scalping, check fixed TP/SL if trailing stop is not enabled or didn't trigger
                # Use strategy's parse_bool_param to safely handle string values from JSON/DB
                trailing_stop_enabled = EmaScalpingStrategy.parse_bool_param(
                    request.params.get("trailing_stop_enabled"), 
                    default=False
                )
                
                # Only use fixed TP/SL if trailing stop is disabled
                if not trailing_stop_enabled:
                    # CRITICAL: Check if we're on the entry candle (prevent immediate exits)
                    # Entry happens at candle i open, so entry_candle_time is candle i's open time
                    # We're checking candle i, so compare entry_candle_time with current candle's open time
                    on_entry_candle = False
                    if hasattr(strategy, 'entry_candle_time') and strategy.entry_candle_time is not None:
                        current_candle_open_time = int(kline[0])  # candle i open time
                        on_entry_candle = (strategy.entry_candle_time == current_candle_open_time)
                    
                    if on_entry_candle:
                        logger.debug(f"Skipping fixed TP/SL check on entry candle (entry_candle_time={strategy.entry_candle_time}, current_candle_open={int(kline[0])})")
                    else:
                        take_profit_pct = float(request.params.get("take_profit_pct", 0.004))
                        stop_loss_pct = float(request.params.get("stop_loss_pct", 0.002))
                        
                        if position_side == "LONG":
                            tp_price = entry_price * (1 + take_profit_pct)
                            sl_price = entry_price * (1 - stop_loss_pct)
                            # Check if TP/SL was hit during the candle using high/low
                            # TP is hit if high >= tp_price, SL is hit if low <= sl_price
                            # Priority: SL first (conservative - assume worse outcome if both hit)
                            # This matches range mean reversion strategy for consistency
                            if candle_low <= sl_price:
                                # SL hit during candle - exit at SL price (not close price)
                                exit_price = sl_price
                                exit_reason = "SL"
                                logger.info(f"SL hit during candle: low={candle_low:.8f} <= sl={sl_price:.8f}, exiting at {exit_price:.8f}")
                            elif candle_high >= tp_price:
                                # TP hit during candle - exit at TP price (not close price)
                                exit_price = tp_price
                                exit_reason = "TP"
                                logger.info(f"TP hit during candle: high={candle_high:.8f} >= tp={tp_price:.8f}, exiting at {exit_price:.8f}")
                        else:  # SHORT
                            tp_price = entry_price * (1 - take_profit_pct)
                            sl_price = entry_price * (1 + stop_loss_pct)
                            # For SHORT: TP is hit if low <= tp_price, SL is hit if high >= sl_price
                            # Priority: SL first (conservative - assume worse outcome if both hit)
                            # This matches range mean reversion strategy for consistency
                            if candle_high >= sl_price:
                                # SL hit during candle - exit at SL price
                                exit_price = sl_price
                                exit_reason = "SL"
                                logger.info(f"SL hit during candle: high={candle_high:.8f} >= sl={sl_price:.8f}, exiting at {exit_price:.8f}")
                            elif candle_low <= tp_price:
                                # TP hit during candle - exit at TP price
                                exit_price = tp_price
                                exit_reason = "TP"
                                logger.info(f"TP hit during candle: low={candle_low:.8f} <= tp={tp_price:.8f}, exiting at {exit_price:.8f}")
            elif request.strategy_type == "range_mean_reversion":
                # CRITICAL FIX: Check intra-candle TP/SL independently of strategy exit_reason
                # Problem: Strategy uses get_price() which returns close price in backtesting
                # Strategy may not detect TP/SL if close price doesn't hit it, even though
                # high/low prices did hit TP/SL during the candle.
                # Also, signal.price may be close price, not the actual TP/SL level price.
                # Solution: For range TP/SL exits, always use intra-candle logic to get exact TP/SL price.
                # Only trust signal.price for non-range exits (manual, range invalidation, etc.)
                
                # Check if exit_reason is a range TP/SL reason
                range_tp_sl_reasons = ["TP_RANGE_HIGH", "TP_RANGE_MID", "TP_RANGE_LOW", "SL_RANGE_BREAK"]
                is_range_tp_sl_exit = signal.exit_reason in range_tp_sl_reasons if signal.exit_reason else False
                
                # For range TP/SL exits, always use intra-candle logic to get exact price
                # For non-range exits (manual, range invalidation, etc.), trust signal.price
                if signal.exit_reason and not is_range_tp_sl_exit:
                    # Non-range exit - trust strategy's signal.price
                    if signal.price is not None:
                        exit_price = signal.price
                        exit_reason = signal.exit_reason
                        logger.info(f"Range mean reversion non-range exit detected by strategy: {exit_reason} at price {exit_price:.8f}")
                
                # CRITICAL: For range TP/SL exits, always check intra-candle to get exact TP/SL price
                # This ensures we exit at the actual TP/SL level, not the close price
                # Also handles cases where TP/SL was hit during candle but strategy didn't see it
                if (is_range_tp_sl_exit or exit_price is None) and hasattr(strategy, 'range_valid') and hasattr(strategy, 'range_high') and hasattr(strategy, 'range_low') and hasattr(strategy, 'range_mid'):
                    if strategy.range_valid and strategy.range_high is not None and strategy.range_low is not None and strategy.range_mid is not None:
                        range_size = strategy.range_high - strategy.range_low
                        tp_buffer_pct = float(request.params.get("tp_buffer_pct", 0.001))
                        sl_buffer_pct = float(request.params.get("sl_buffer_pct", 0.002))
                        
                        # Check entry candle protection (block TP on entry candle, allow SL)
                        # Entry happens at candle i open, so entry_candle_time is candle i's open time
                        # We're checking candle i, so compare entry_candle_time with current candle's open time
                        on_entry_candle = False
                        if hasattr(strategy, 'entry_candle_time') and strategy.entry_candle_time is not None:
                            current_candle_open_time = int(kline[0])  # candle i open time
                            on_entry_candle = (strategy.entry_candle_time == current_candle_open_time)
                        
                        if position_side == "LONG":
                            tp1 = strategy.range_mid
                            tp2 = strategy.range_high - (range_size * tp_buffer_pct)
                            sl = strategy.range_low - (range_size * sl_buffer_pct)
                            
                            # Check intra-candle TP/SL using high/low prices
                            # Priority: TP2 > TP1 > SL
                            # SL can trigger even on entry candle (critical exit)
                            if candle_low <= sl:
                                exit_price = sl
                                exit_reason = "SL_RANGE_BREAK"
                                logger.info(f"SL hit during candle (intra-candle check): low={candle_low:.8f} <= sl={sl:.8f}, exiting at {exit_price:.8f}")
                            elif not on_entry_candle:
                                # Block TP exits on entry candle
                                if candle_high >= tp2:
                                    exit_price = tp2
                                    exit_reason = "TP_RANGE_HIGH"
                                    logger.info(f"TP2 hit during candle (intra-candle check): high={candle_high:.8f} >= tp2={tp2:.8f}, exiting at {exit_price:.8f}")
                                elif candle_high >= tp1:
                                    exit_price = tp1
                                    exit_reason = "TP_RANGE_MID"
                                    logger.info(f"TP1 hit during candle (intra-candle check): high={candle_high:.8f} >= tp1={tp1:.8f}, exiting at {exit_price:.8f}")
                        else:  # SHORT
                            tp1 = strategy.range_mid
                            tp2 = strategy.range_low + (range_size * tp_buffer_pct)
                            sl = strategy.range_high + (range_size * sl_buffer_pct)
                            
                            # Check intra-candle TP/SL using high/low prices
                            # Priority: TP2 > TP1 > SL
                            # SL can trigger even on entry candle (critical exit)
                            if candle_high >= sl:
                                exit_price = sl
                                exit_reason = "SL_RANGE_BREAK"
                                logger.info(f"SL hit during candle (intra-candle check): high={candle_high:.8f} >= sl={sl:.8f}, exiting at {exit_price:.8f}")
                            elif not on_entry_candle:
                                # Block TP exits on entry candle
                                if candle_low <= tp2:
                                    exit_price = tp2
                                    exit_reason = "TP_RANGE_LOW"
                                    logger.info(f"TP2 hit during candle (intra-candle check): low={candle_low:.8f} <= tp2={tp2:.8f}, exiting at {exit_price:.8f}")
                                elif candle_low <= tp1:
                                    exit_price = tp1
                                    exit_reason = "TP_RANGE_MID"
                                    logger.info(f"TP1 hit during candle (intra-candle check): low={candle_low:.8f} <= tp1={tp1:.8f}, exiting at {exit_price:.8f}")
            else:
                # Other strategy types - use strategy's internal TP/SL
                if signal.exit_reason:
                    exit_price = current_price
                    exit_reason = signal.exit_reason
            
            # Close position if TP/SL hit
            if exit_price is not None:
                # Apply spread offset on exit
                if position_side == "LONG":
                    real_exit_price = exit_price * (1 - SPREAD_OFFSET)  # Sell at bid price
                else:  # SHORT
                    real_exit_price = exit_price * (1 + SPREAD_OFFSET)  # Buy back at ask price
                
                # Calculate PnL using spread-adjusted exit price
                if position_side == "LONG":
                    pnl = (real_exit_price - entry_price) * current_trade.quantity * request.leverage
                else:  # SHORT
                    pnl = (entry_price - real_exit_price) * current_trade.quantity * request.leverage
                
                # Calculate exit fee using exit notional (not entry notional)
                # Exit notional = quantity * exit_price (price may have changed)
                exit_notional = current_trade.quantity * real_exit_price
                exit_fee = exit_notional * AVERAGE_FEE_RATE
                
                # Net PnL (entry_fee already deducted when trade was opened)
                net_pnl = pnl - exit_fee
                
                # Update trade (store net_pnl including all fees for reporting)
                current_trade.exit_time = candle_time
                current_trade.exit_price = real_exit_price  # Store spread-adjusted exit price
                current_trade.exit_fee = exit_fee
                current_trade.pnl = pnl
                current_trade.net_pnl = pnl - current_trade.entry_fee - exit_fee  # Full net PnL for reporting
                current_trade.exit_reason = exit_reason
                current_trade.is_open = False
                
                # Update balance (entry_fee already deducted, so only subtract exit_fee)
                balance += net_pnl
                mock_client.update_balance(balance)  # Update mock client balance
                equity_curve.append(balance)
                
                # Update drawdown
                if balance > peak_balance:
                    peak_balance = balance
                drawdown = peak_balance - balance
                drawdown_pct = (drawdown / peak_balance) * 100 if peak_balance > 0 else 0
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                if drawdown_pct > max_drawdown_pct:
                    max_drawdown_pct = drawdown_pct
                
                # CRITICAL: Sync strategy's internal state when trade is closed
                # This ensures the strategy knows the position is closed and sets cooldown
                if hasattr(strategy, 'sync_position_state'):
                    strategy.sync_position_state(
                        position_side=None,
                        entry_price=None
                    )
                    # CRITICAL: Ensure cooldown is set if strategy doesn't have it set
                    # This handles cases where exit was triggered by backtesting's TP/SL check
                    # (not strategy's exit signal, which would have already set cooldown)
                    # Works for both scalping and range mean reversion strategies
                    if hasattr(strategy, 'cooldown_left') and hasattr(strategy, 'cooldown_candles'):
                        if strategy.cooldown_left == 0:  # Only set if not already set by strategy
                            strategy.cooldown_left = strategy.cooldown_candles
                            logger.debug(f"Set cooldown={strategy.cooldown_left} candles after {exit_reason} exit (backtesting TP/SL)")
                    logger.debug(f"Synced strategy state: position=None after {exit_reason} exit")
                
                # Reset strategy state
                strategy_position = None
                strategy_entry_price = None
                current_trade = None
                
                # CRITICAL: Mark that position was just closed in this iteration
                # This prevents immediate re-entry in the same candle, ensuring cooldown is respected
                # The signal was generated BEFORE we closed the position, so any entry signals in it
                # should be blocked by cooldown. We'll process them in the next candle iteration.
                position_just_closed_this_iteration = True
                logger.debug(f"Position closed at candle {i}, will skip new entry signals in same candle to respect cooldown")
        
        # Process new signals (only if no open position)
        # CRITICAL: Only process trades within the backtest time range
        if signal.action in ("BUY", "SELL"):
            # CRITICAL: Skip entry signals if we just closed a position in this same candle iteration
            # This ensures cooldown is respected - the signal was generated before we closed the position
            if position_just_closed_this_iteration:
                logger.debug(f"Skipping {signal.action} signal at candle {i}: position was just closed, cooldown active")
                continue
            
            # Ensure trade is within backtest time range
            if candle_time < request.start_time:
                logger.warning(f"Skipping {signal.action} signal at candle {i}: candle_time {candle_time} is before start_time {request.start_time}")
                continue
            if candle_time > request.end_time:
                logger.warning(f"Skipping {signal.action} signal at candle {i}: candle_time {candle_time} is after end_time {request.end_time}")
                continue
            
            # Per-candle signal checks at DEBUG level (progress tracked via SSE)
            logger.debug(f"Signal check: {signal.action} at candle {i}, current_trade={current_trade is not None}")
            if current_trade is not None:
                logger.warning(f"Skipping {signal.action} signal at candle {i}: position already open ({current_trade.position_side})")
            else:
                # CRITICAL FIX: Entry price should use candle i's OPEN, not close
                # Strategy generates signal from candle i-1's close, so entry should execute
                # at candle i's open (first available price when candle i starts)
                # Using candle i's close would be future knowledge (lookahead bias)
                entry_price_base = float(kline[1])  # open price of candle i
                sig_price_str = f"{signal.price:.8f}" if signal.price is not None else "None"
                # Signal processing details at DEBUG (trade entry/exit logged at INFO below)
                logger.debug(f"Processing {signal.action} signal at candle {i}, entry_price_base={entry_price_base:.8f} (candle i open), signal_price={sig_price_str} (candle i-1 close)")
                
                # Calculate position size using entry price (candle i open)
                try:
                    sizing = risk_manager.size_position(
                        symbol=request.symbol,
                        risk_per_trade=request.risk_per_trade,
                        price=entry_price_base,
                        fixed_amount=request.fixed_amount
                    )
                    logger.debug(f"Position sizing result: quantity={sizing.quantity:.8f}, notional={sizing.notional:.2f}")
                except Exception as e:
                    logger.warning(f"Error sizing position at candle {i}: {type(e).__name__}: {e}", exc_info=True)
                    continue
                
                # Determine position side
                if signal.action == "BUY":
                    position_side = "LONG"
                else:  # SELL
                    position_side = "SHORT"
                
                # Apply spread offset on entry (using candle i open price)
                if position_side == "LONG":
                    real_entry_price = entry_price_base * (1 + SPREAD_OFFSET)  # Pay ask price
                else:  # SHORT
                    real_entry_price = entry_price_base * (1 - SPREAD_OFFSET)  # Sell at bid price
                
                # Calculate executed notional using real entry price (with spread)
                # This matches exit fee logic which uses exit notional
                entry_notional = sizing.quantity * real_entry_price
                entry_fee = entry_notional * AVERAGE_FEE_RATE
                
                # Check if we have enough balance for entry fee
                if balance < entry_fee:
                    logger.warning(f"Insufficient balance for trade: balance={balance:.2f}, entry_fee={entry_fee:.2f}")
                    continue  # Skip trade if insufficient balance
                
                # Create new trade - use DEBUG to reduce backtest log noise
                logger.debug(f"Creating {position_side} trade: entry={real_entry_price:.8f} (spread-adjusted from candle i open {entry_price_base:.8f}), quantity={sizing.quantity:.8f}, executed_notional={entry_notional:.2f}")
                current_trade = Trade(
                    entry_time=candle_time,
                    exit_time=None,
                    entry_price=real_entry_price,  # Store spread-adjusted entry price
                    exit_price=None,
                    position_side=position_side,
                    quantity=sizing.quantity,
                    notional=entry_notional,  # Store executed notional (not sizing estimate)
                    entry_fee=entry_fee,
                    exit_fee=None,
                    pnl=None,
                    net_pnl=None,
                    exit_reason=None,
                    is_open=True
                )
                
                # Track strategy state
                strategy_position = position_side
                strategy_entry_price = real_entry_price  # Use spread-adjusted entry price
                
                # CRITICAL: Sync strategy's internal state when trade is opened
                # This ensures the strategy knows about the position and can check TP/SL correctly
                # This matches live trading behavior where strategy sets its own state when generating signals
                if hasattr(strategy, 'sync_position_state'):
                    strategy.sync_position_state(
                        position_side=position_side,
                        entry_price=real_entry_price  # Use spread-adjusted entry price
                    )
                    # CRITICAL: Set entry_candle_time to prevent same-candle exits
                    # Entry happens at candle i open, so entry_candle_time should be candle i's open time
                    # NOT last_closed_candle_time (which is candle i-1, the decision candle)
                    strategy.entry_candle_time = int(kline[0])  # candle i open time in ms
                    logger.debug(f"Set entry_candle_time={strategy.entry_candle_time} (candle i open) to prevent same-candle exits")
                    
                    # CRITICAL: For range mean reversion, ensure range state is preserved
                    # Range state should already be set by strategy during evaluate(), but verify
                    if request.strategy_type == "range_mean_reversion":
                        if hasattr(strategy, 'range_valid') and strategy.range_valid:
                            logger.debug(
                                f"Range state preserved: high={strategy.range_high}, "
                                f"low={strategy.range_low}, mid={strategy.range_mid}"
                            )
                    
                    logger.debug(f"Synced strategy state: position={position_side} @ {real_entry_price:.8f} after opening trade")
                
                # Add to trades list
                trades.append(current_trade)
                
                # Deduct entry fee from balance
                balance -= entry_fee
                mock_client.update_balance(balance)  # Update mock client balance
                equity_curve.append(balance)
        
        # Close position on CLOSE signal
        # Ensure we're within backtest time range
        if signal.action == "CLOSE" and current_trade and current_trade.is_open and request.start_time <= candle_time <= request.end_time:
            exit_price = current_price
            entry_price = current_trade.entry_price
            position_side = current_trade.position_side
            
            # Apply spread offset on exit
            if position_side == "LONG":
                real_exit_price = exit_price * (1 - SPREAD_OFFSET)  # Sell at bid price
            else:  # SHORT
                real_exit_price = exit_price * (1 + SPREAD_OFFSET)  # Buy back at ask price
            
            # Calculate PnL using spread-adjusted exit price
            if position_side == "LONG":
                pnl = (real_exit_price - entry_price) * current_trade.quantity * request.leverage
            else:  # SHORT
                pnl = (entry_price - real_exit_price) * current_trade.quantity * request.leverage
            
            # Calculate exit fee using exit notional (not entry notional)
            # Exit notional = quantity * exit_price (price may have changed)
            exit_notional = current_trade.quantity * real_exit_price
            exit_fee = exit_notional * AVERAGE_FEE_RATE
            
            # Net PnL (entry_fee already deducted when trade was opened)
            net_pnl = pnl - exit_fee
            
            # Update trade (store net_pnl including all fees for reporting)
            current_trade.exit_time = candle_time
            current_trade.exit_price = real_exit_price  # Store spread-adjusted exit price
            current_trade.exit_fee = exit_fee
            current_trade.pnl = pnl
            current_trade.net_pnl = pnl - current_trade.entry_fee - exit_fee  # Full net PnL for reporting
            current_trade.exit_reason = signal.exit_reason or "CLOSE"
            current_trade.is_open = False
            
            # Update balance (entry_fee already deducted, so only subtract exit_fee)
            balance += net_pnl
            mock_client.update_balance(balance)  # Update mock client balance
            equity_curve.append(balance)
            
            # Update drawdown
            if balance > peak_balance:
                peak_balance = balance
            drawdown = peak_balance - balance
            drawdown_pct = (drawdown / peak_balance) * 100 if peak_balance > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = drawdown_pct
            
            # CRITICAL: Sync strategy's internal state when trade is closed via CLOSE signal
            if hasattr(strategy, 'sync_position_state'):
                strategy.sync_position_state(
                    position_side=None,
                    entry_price=None
                )
                # CRITICAL: Ensure cooldown is set if strategy doesn't have it set
                if hasattr(strategy, 'cooldown_left') and hasattr(strategy, 'cooldown_candles'):
                    if strategy.cooldown_left == 0:  # Only set if not already set by strategy
                        strategy.cooldown_left = strategy.cooldown_candles
                        logger.debug(f"Set cooldown={strategy.cooldown_left} candles after CLOSE signal")
                logger.debug(f"Synced strategy state: position=None after CLOSE signal")
            
            # Reset strategy state
            strategy_position = None
            strategy_entry_price = None
            current_trade = None
    
    # Add final trade to list if it exists and is still open
    if current_trade and current_trade.is_open and current_trade not in trades:
        trades.append(current_trade)
    
    # Close any remaining open trades at final price
    if current_trade and current_trade.is_open:
        if not filtered_klines:
            logger.error("Cannot close open trade: no klines available")
            # Trade will remain open in results
        else:
            final_price = float(filtered_klines[-1][4])
            final_time = datetime.fromtimestamp(int(filtered_klines[-1][0]) / 1000, tz=timezone.utc)
            
            entry_price = current_trade.entry_price
            position_side = current_trade.position_side
            
            # Apply spread offset on exit
            if position_side == "LONG":
                real_exit_price = final_price * (1 - SPREAD_OFFSET)  # Sell at bid price
            else:  # SHORT
                real_exit_price = final_price * (1 + SPREAD_OFFSET)  # Buy back at ask price
            
            # Calculate PnL using spread-adjusted exit price
            if position_side == "LONG":
                pnl = (real_exit_price - entry_price) * current_trade.quantity * request.leverage
            else:  # SHORT
                pnl = (entry_price - real_exit_price) * current_trade.quantity * request.leverage
            
            # Calculate exit fee using exit notional (not entry notional)
            # Exit notional = quantity * exit_price (price may have changed)
            exit_notional = current_trade.quantity * real_exit_price
            exit_fee = exit_notional * AVERAGE_FEE_RATE
            
            # Net PnL (entry_fee already deducted when trade was opened)
            net_pnl = pnl - exit_fee
            
            # Update trade (store net_pnl including all fees for reporting)
            current_trade.exit_time = final_time
            current_trade.exit_price = real_exit_price  # Store spread-adjusted exit price
            current_trade.exit_fee = exit_fee
            current_trade.pnl = pnl
            current_trade.net_pnl = pnl - current_trade.entry_fee - exit_fee  # Full net PnL for reporting
            current_trade.exit_reason = "END_OF_PERIOD"
            current_trade.is_open = False
            
            # Update balance (entry_fee already deducted, so only subtract exit_fee)
            balance += net_pnl
            mock_client.update_balance(balance)  # Update mock client balance
    
    # Log signal statistics
    logger.info(f"Signal statistics: {signal_counts}")
    
    # Calculate statistics
    stats = _calculate_backtest_statistics(trades, request.initial_balance, balance)
    
    completed_trades = stats["completed_trades"]
    open_trades = stats["open_trades"]
    total_pnl = stats["total_pnl"]
    total_return_pct = stats["total_return_pct"]
    winning_trades = stats["winning_trades"]
    losing_trades = stats["losing_trades"]
    win_rate = stats["win_rate"]
    total_fees = stats["total_fees"]
    avg_profit_per_trade = stats["avg_profit_per_trade"]
    largest_win = stats["largest_win"]
    largest_loss = stats["largest_loss"]
    
    logger.info(f"Backtest completed: {len(completed_trades)} completed trades, {len(open_trades)} open trades, {len(trades)} total")
    if len(trades) == 0:
        logger.warning("No trades were executed during backtest.")
        logger.warning(f"Signals generated: BUY={signal_counts.get('BUY', 0)}, SELL={signal_counts.get('SELL', 0)}, HOLD={signal_counts.get('HOLD', 0)}")
        if signal_counts.get('BUY', 0) == 0 and signal_counts.get('SELL', 0) == 0:
            logger.warning("Strategy is only generating HOLD signals. This could indicate:")
            logger.warning("  - Market conditions don't match strategy criteria")
            logger.warning("  - EMA periods need more candles to stabilize")
            logger.warning("  - Strategy parameters are too restrictive")
    
    # Convert trades to dict for response
    # Note: Frontend will format prices/quantities to 5 decimal places for display
    # Backend preserves full precision in the data
    trades_dict = [t.model_dump() for t in trades]
    
    # Prepare klines data for charting (format: [time, open, high, low, close, volume])
    klines_data = []
    for k in filtered_klines:
        klines_data.append([
            int(k[0]),  # timestamp
            float(k[1]),  # open
            float(k[2]),  # high
            float(k[3]),  # low
            float(k[4]),  # close
            float(k[5])   # volume
        ])
    
    # Calculate indicators for charting
    indicators_data = None
    if request.strategy_type == "range_mean_reversion":
        # Build indicators data from snapshots
        indicators_data = {
            "range_high": [{"time": s["time"], "value": s["range_high"]} for s in range_indicator_snapshots if s["range_high"] is not None],
            "range_low": [{"time": s["time"], "value": s["range_low"]} for s in range_indicator_snapshots if s["range_low"] is not None],
            "range_mid": [{"time": s["time"], "value": s["range_mid"]} for s in range_indicator_snapshots if s["range_mid"] is not None],
            "buy_zone_upper": [{"time": s["time"], "value": s["buy_zone_upper"]} for s in range_indicator_snapshots if s["buy_zone_upper"] is not None],
            "sell_zone_lower": [{"time": s["time"], "value": s["sell_zone_lower"]} for s in range_indicator_snapshots if s["sell_zone_lower"] is not None],
            "rsi": [{"time": s["time"], "value": s["rsi"]} for s in range_indicator_snapshots if s["rsi"] is not None],
            "ema_fast": [{"time": s["time"], "value": s["ema_fast"]} for s in range_indicator_snapshots if s["ema_fast"] is not None],
            "ema_slow": [{"time": s["time"], "value": s["ema_slow"]} for s in range_indicator_snapshots if s["ema_slow"] is not None],
            "ema_spread_pct": [{"time": s["time"], "value": s["ema_spread_pct"]} for s in range_indicator_snapshots if s["ema_spread_pct"] is not None],
            "tp_sl_levels": [
                {
                    "time": s["time"],
                    "tp1": s["tp1"],
                    "tp2": s["tp2"],
                    "sl": s["sl"],
                    "position_side": s["position_side"]
                }
                for s in range_indicator_snapshots
                if s["position_side"] is not None and (s["tp1"] is not None or s["tp2"] is not None or s["sl"] is not None)
            ],
            # CODE QUALITY FIX: Use extracted parameters instead of repeated lookups
            "rsi_period": rmr_params["rsi_period"],
            "rsi_oversold": rmr_params["rsi_oversold"],
            "rsi_overbought": rmr_params["rsi_overbought"],
            "ema_fast_period": rmr_params["ema_fast_period"],
            "ema_slow_period": rmr_params["ema_slow_period"],
            "max_ema_spread_pct": rmr_params["max_ema_spread_pct"],
            "buy_zone_pct": rmr_params["buy_zone_pct"],
            "sell_zone_pct": rmr_params["sell_zone_pct"]
        }
    elif request.strategy_type == "scalping":
        # PERFORMANCE FIX: Use pre-calculated closing_prices_all (already calculated above)
        closing_prices = closing_prices_all
        
        # Calculate EMA fast and slow using incremental calculation (O(N) instead of O(N²))
        ema_fast_values = []
        ema_slow_values = []
        
        fast_period = int(request.params.get("ema_fast", 8))
        slow_period = int(request.params.get("ema_slow", 21))
        
        # Incremental EMA calculation (O(N) total instead of O(N²))
        ema_fast_prev = None
        ema_slow_prev = None
        alpha_fast = 2.0 / (fast_period + 1)
        alpha_slow = 2.0 / (slow_period + 1)
        
        for i, price in enumerate(closing_prices):
            # EMA fast incremental calculation
            if i < fast_period - 1:
                ema_fast_values.append(None)
            else:
                if i == fast_period - 1:
                    # Initialize with SMA
                    ema_fast_prev = fmean(closing_prices[:fast_period])
                else:
                    # Update EMA incrementally (O(1) per iteration)
                    ema_fast_prev = (price - ema_fast_prev) * alpha_fast + ema_fast_prev
                ema_fast_values.append(ema_fast_prev)
            
            # EMA slow incremental calculation
            if i < slow_period - 1:
                ema_slow_values.append(None)
            else:
                if i == slow_period - 1:
                    # Initialize with SMA (fmean imported at top of file)
                    ema_slow_prev = fmean(closing_prices[:slow_period])
                else:
                    # Update EMA incrementally (O(1) per iteration)
                    ema_slow_prev = (price - ema_slow_prev) * alpha_slow + ema_slow_prev
                ema_slow_values.append(ema_slow_prev)
        
        # Create indicators data with timestamps matching klines
        indicators_data = {
            "ema_fast": [
                {"time": int(k[0]) // 1000, "value": ema_fast_values[i]} 
                for i, k in enumerate(filtered_klines) 
                if ema_fast_values[i] is not None
            ],
            "ema_slow": [
                {"time": int(k[0]) // 1000, "value": ema_slow_values[i]} 
                for i, k in enumerate(filtered_klines) 
                if ema_slow_values[i] is not None
            ],
            "ema_fast_period": fast_period,
            "ema_slow_period": slow_period
        }
    
    # PERFORMANCE FIX: Conditionally include klines to reduce response payload size
    # For large backtests (30+ days), excluding klines can reduce payload by 90%+
    return BacktestResult(
        symbol=request.symbol,
        strategy_type=request.strategy_type,
        start_time=request.start_time,
        end_time=request.end_time,
        initial_balance=request.initial_balance,
        final_balance=balance,
        total_pnl=total_pnl,
        total_return_pct=total_return_pct,
        total_trades=len(trades),
        completed_trades=len(completed_trades),
        open_trades=len(open_trades),
        winning_trades=len(winning_trades),
        losing_trades=len(losing_trades),
        win_rate=win_rate,
        total_fees=total_fees,
        avg_profit_per_trade=avg_profit_per_trade,
        largest_win=largest_win,
        largest_loss=largest_loss,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        trades=trades_dict,
        klines=klines_data if request.include_klines else None,
        indicators=indicators_data
    )


@router.post("/run", response_model=BacktestResult)
async def run_backtest_endpoint(
    request: BacktestRequest,
    client: BinanceClient = Depends(get_binance_client)
) -> BacktestResult:
    """
    Run backtesting on historical data.
    
    Analyzes how a strategy would have performed over a selected historical period
    using real market data from Binance.
    
    **Timeout**: This operation has a 10-minute timeout to prevent hanging requests.
    For very large backtests, consider using walk-forward analysis with async task management.
    """
    from app.services.backtest_service import BacktestService
    
    # PERFORMANCE FIX: Add timeout to prevent hanging requests
    # 10 minutes should be sufficient for most backtests
    # Very large backtests should use walk-forward analysis with async tasks
    timeout_seconds = 600  # 10 minutes
    
    try:
        service = BacktestService(client)
        result = await asyncio.wait_for(
            service.run_backtest(request),
            timeout=timeout_seconds
        )
        return result
    except asyncio.TimeoutError:
        logger.error(
            f"Backtest timeout after {timeout_seconds}s for {request.symbol} "
            f"({request.start_time} to {request.end_time})"
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Backtest operation timed out after {timeout_seconds} seconds. "
                f"Consider using walk-forward analysis for large time ranges or reducing the time period."
            )
        )


@router.post("/walk-forward")
async def run_walk_forward_endpoint(
    request: Annotated[dict, Body()],
    client: BinanceClient = Depends(get_binance_client)
) -> dict:
    """
    Run walk-forward analysis on historical data.
    
    Walk-forward analysis splits historical data into multiple training and test periods:
    - Optimizes parameters on training data (if optimize_params provided)
    - Validates on out-of-sample test data
    - Provides more robust performance estimates than single-period backtesting
    
    Example:
    - Training: 30 days, Test: 7 days, Step: 7 days
    - Window 1: Train on days 1-30, Test on days 31-37
    - Window 2: Train on days 8-37, Test on days 38-44
    - Window 3: Train on days 15-44, Test on days 45-51
    - etc.
    
    Window Types:
    - "rolling": Fixed-size training window that moves forward
    - "expanding": Growing training window that always starts from the beginning
    
    Note: For progress tracking, use the /walk-forward/start endpoint with SSE.
    """
    # Lazy import to avoid circular dependency
    from app.services.walk_forward import (
        WalkForwardRequest,
        WalkForwardResult,
        run_walk_forward_analysis
    )
    
    # Parse and validate request
    walk_forward_request = WalkForwardRequest(**request)
    
    # Run analysis
    result = await run_walk_forward_analysis(walk_forward_request, client)
    
    # Return as dict (FastAPI will serialize the Pydantic model)
    return result.model_dump()


@router.post("/walk-forward/start")
async def start_walk_forward_analysis(
    request: Annotated[dict, Body()],
    current_user = Depends(get_current_user_async),
    client: BinanceClient = Depends(get_binance_client)
) -> dict:
    """
    Start walk-forward analysis and return task ID for progress tracking.
    
    Requires authentication. Checks concurrency limits before starting.
    
    Returns:
        {"task_id": "uuid", "message": "Analysis started"}
    
    Raises:
        HTTPException 429: If concurrency limits are exceeded
    """
    from app.services.walk_forward import WalkForwardRequest, run_walk_forward_analysis
    from app.services.walk_forward_task_manager import get_task_manager
    from app.services.walk_forward import generate_walk_forward_windows
    from fastapi import status
    
    # Get user ID
    user_id = str(current_user.id)
    
    # Get settings for concurrency limits
    settings = get_settings()
    
    # Parse and validate request
    try:
        logger.info(f"Received walk-forward request: optimize_params={request.get('optimize_params')}, "
                   f"optimization_metric={request.get('optimization_metric')}, "
                   f"optimization_method={request.get('optimization_method')}")
        logger.info(f"Full request keys: {list(request.keys())}")
        
        walk_forward_request = WalkForwardRequest(**request)
    except Exception as e:
        logger.error(f"Error parsing walk-forward request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request data: {str(e)}"
        )
    
    logger.info(f"Parsed WalkForwardRequest: optimize_params={walk_forward_request.optimize_params}, "
               f"optimization_metric={walk_forward_request.optimization_metric}, "
               f"optimization_method={walk_forward_request.optimization_method}")
    
    # Generate windows to get total count
    windows = generate_walk_forward_windows(
        start_time=walk_forward_request.start_time,
        end_time=walk_forward_request.end_time,
        training_days=walk_forward_request.training_period_days,
        test_days=walk_forward_request.test_period_days,
        step_days=walk_forward_request.step_size_days,
        window_type=walk_forward_request.window_type
    )
    
    # Get task manager
    task_manager = get_task_manager()
    
    # Check global concurrency limit
    running_tasks = await task_manager.count_running_tasks()
    if running_tasks >= settings.max_concurrent_walk_forward_analyses:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Server at capacity: {running_tasks}/{settings.max_concurrent_walk_forward_analyses} concurrent analyses running. Please try again later."
        )
    
    # Check per-user concurrency limit
    user_running = await task_manager.count_user_running_tasks(user_id)
    if user_running >= settings.max_walk_forward_analyses_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many concurrent analyses: {user_running}/{settings.max_walk_forward_analyses_per_user} analyses already running. Please wait for one to complete."
        )
    
    # Create task with user_id
    task_id = await task_manager.create_task(total_windows=len(windows), user_id=user_id)
    
    # Start analysis in background
    async def run_analysis():
        import time
        start_time = time.time()
        candles_processed = 0  # Will be calculated from result if available
        
        try:
            result = await run_walk_forward_analysis(walk_forward_request, client, task_id=task_id)
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Store result in task manager - ensure it's serializable
            try:
                if hasattr(result, 'model_dump'):
                    result_dict = result.model_dump()
                elif hasattr(result, 'dict'):
                    result_dict = result.dict()
                else:
                    result_dict = result
                
                # Verify equity_curve is included
                if isinstance(result_dict, dict) and 'equity_curve' in result_dict:
                    logger.info(f"Storing result with equity_curve containing {len(result_dict.get('equity_curve', []))} points")
                
                await task_manager.complete_task(task_id, result=result_dict)
                
                # Auto-save to database after successful completion
                try:
                    from app.services.database_service import DatabaseService
                    from app.core.database import get_async_session_factory
                    
                    # Create a new database session for the background task
                    # We can't use the dependency injection here, so we create the session manually
                    async_session_factory = await get_async_session_factory()
                    
                    async with async_session_factory() as db:
                        db_service = DatabaseService(db)
                        
                        # Calculate candles processed (estimate from windows and periods)
                        if hasattr(result, 'windows') and result.windows:
                            # Rough estimate: each window processes training + test period candles
                            candles_processed = len(result.windows) * (
                                walk_forward_request.training_period_days * 24 * 60 +  # Training period (assuming 1m candles)
                                walk_forward_request.test_period_days * 24 * 60  # Test period
                            )
                        else:
                            candles_processed = 0
                        
                        analysis_id = await db_service.save_walk_forward_analysis(
                            user_id=current_user.id,
                            result=result,
                            request=walk_forward_request,
                            execution_time_ms=execution_time_ms,
                            candles_processed=candles_processed,
                            name=walk_forward_request.name,  # Optional name from parsed request
                            keep_details=True
                        )
                        logger.info(f"✅ Saved walk-forward analysis {analysis_id} to database for user {user_id}")
                except Exception as save_error:
                    logger.error(f"❌ Failed to save walk-forward analysis to database: {save_error}", exc_info=True)
                    # Don't fail the analysis - just log the error
            except Exception as serialize_error:
                logger.error(f"Error serializing result: {serialize_error}", exc_info=True)
                await task_manager.fail_task(task_id, f"Failed to serialize result: {str(serialize_error)}")
        except HTTPException as e:
            if e.status_code == 499:  # Cancelled
                await task_manager.cancel_task(task_id)
            else:
                await task_manager.fail_task(task_id, str(e.detail))
        except Exception as e:
            logger.error(f"Error in walk-forward analysis: {e}", exc_info=True)
            await task_manager.fail_task(task_id, str(e))
    
    # Run in background
    asyncio.create_task(run_analysis())
    
    logger.info(f"Started walk-forward analysis {task_id} for user {user_id} ({len(windows)} windows)")
    return {
        "task_id": task_id,
        "message": "Walk-forward analysis started",
        "total_windows": len(windows)
    }


@router.get("/walk-forward/progress/{task_id}")
async def get_walk_forward_progress(
    task_id: str,
    token: Optional[str] = Query(None, description="Auth token (for EventSource compatibility)"),
    request: Request = None
):
    """
    Server-Sent Events endpoint for walk-forward analysis progress.
    
    Returns real-time progress updates including:
    - Current window number
    - Total windows
    - Progress percentage
    - Estimated time remaining
    - Current phase
    - Status message
    
    Note: Token can be passed as query parameter for EventSource compatibility
    (EventSource doesn't support custom headers).
    
    Requires authentication and verifies task ownership.
    """
    from app.services.walk_forward_task_manager import get_task_manager
    from app.core.auth import decode_token, get_user_id_from_token
    from fastapi import status
    
    # Authenticate: prefer query parameter token (for EventSource), fallback to Authorization header
    user_id = None
    
    if token:
        # EventSource compatibility: authenticate from query parameter token
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token"
            )
        token_user_id = get_user_id_from_token(token)
        if not token_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        user_id = str(token_user_id)
    else:
        # Fallback: try Authorization header (for regular HTTP requests)
        if request:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                auth_token = auth_header[7:]  # Remove "Bearer " prefix
                payload = decode_token(auth_token)
                if payload and payload.get("type") == "access":
                    token_user_id = get_user_id_from_token(auth_token)
                    if token_user_id:
                        user_id = str(token_user_id)
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Provide token as query parameter or Authorization header.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    task_manager = get_task_manager()
    
    # Verify task ownership
    progress = await task_manager.get_progress(task_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    if progress.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to access this task"
        )
    
    async def event_generator():
        last_window = -1
        last_status = None
        last_ping_time = asyncio.get_event_loop().time()
        ping_interval = 15.0  # Send keep-alive ping every 15 seconds
        
        try:
            while True:
                # Check for disconnect (this is handled by FastAPI/Starlette automatically)
                # but we can add explicit checks if needed
                
                progress = await task_manager.get_progress(task_id)
                
                if not progress:
                    yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                    break
                
                # Only send update if progress changed (window number or status)
                if (progress.current_window != last_window or 
                    progress.status != last_status or
                    progress.status in ("completed", "cancelled", "error")):
                    
                    progress_dict = {
                        "task_id": progress.task_id,
                        "status": progress.status,
                        "current_window": progress.current_window,
                        "total_windows": progress.total_windows,
                        "progress_percent": round(progress.progress_percent, 2),
                        "current_phase": progress.current_phase,
                        "message": progress.message,
                        "estimated_time_remaining_seconds": (
                            round(progress.estimated_time_remaining_seconds, 1)
                            if progress.estimated_time_remaining_seconds is not None
                            else None
                        ),
                        "error": progress.error
                    }
                    yield f"data: {json.dumps(progress_dict)}\n\n"
                    last_window = progress.current_window
                    last_status = progress.status
                    
                    # Stop if completed, cancelled, or error
                    if progress.status in ("completed", "cancelled", "error"):
                        break
                
                # Send keep-alive ping every ~15 seconds to prevent proxy timeouts
                current_time = asyncio.get_event_loop().time()
                if current_time - last_ping_time >= ping_interval:
                    yield ": keep-alive ping\n\n"  # SSE comment line (keeps connection alive)
                    last_ping_time = current_time
                
                await asyncio.sleep(0.5)  # Poll every 500ms
        except asyncio.CancelledError:
            # Client disconnected - stop streaming
            logger.debug(f"SSE stream cancelled for task {task_id}")
            raise
        except Exception as e:
            logger.error(f"Error in SSE stream for task {task_id}: {e}")
            yield f"data: {json.dumps({'error': f'Stream error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "X-Content-Type-Options": "nosniff"
        }
    )


@router.post("/walk-forward/cancel/{task_id}")
async def cancel_walk_forward_analysis(
    task_id: str,
    current_user = Depends(get_current_user_async)
) -> dict:
    """
    Cancel a running walk-forward analysis.
    
    Requires authentication and verifies task ownership.
    
    Returns:
        {"success": true, "message": "Task cancelled"}
    """
    from app.services.walk_forward_task_manager import get_task_manager
    from fastapi import status
    
    task_manager = get_task_manager()
    user_id = str(current_user.id)
    
    # Verify task ownership
    progress = await task_manager.get_progress(task_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    if progress.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to cancel this task"
        )
    
    success = await task_manager.cancel_task(task_id)
    
    if success:
        logger.info(f"User {user_id} cancelled walk-forward task {task_id}")
        return {"success": True, "message": "Task cancelled"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )


@router.get("/walk-forward/result/{task_id}")
async def get_walk_forward_result(
    task_id: str,
    current_user = Depends(get_current_user_async)
) -> dict:
    """
    Get the final result of a completed walk-forward analysis.
    
    Requires authentication and verifies task ownership.
    """
    from app.services.walk_forward_task_manager import get_task_manager
    from fastapi import status
    
    task_manager = get_task_manager()
    user_id = str(current_user.id)
    
    progress = await task_manager.get_progress(task_id)
    
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Verify task ownership
    if progress.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to access this task"
        )
    
    if progress.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is not completed (status: {progress.status})"
        )
    
    if progress.result is None:
        raise HTTPException(
            status_code=500,
            detail="Result not available"
        )
    
    result = progress.result
    # Debug: Log equity_curve presence
    if 'equity_curve' in result:
        logger.debug(f"Returning result with equity_curve containing {len(result.get('equity_curve', []))} points")
    else:
        logger.warning(f"Equity curve missing in result! Keys: {list(result.keys())}")
    
    return result


# ============================================
# WALK-FORWARD HISTORY ENDPOINTS
# ============================================

@router.get("/walk-forward/history")
async def list_walk_forward_analyses(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of analyses to return"),
    offset: int = Query(0, ge=0, description="Number of analyses to skip"),
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g., BTCUSDT)"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    start_date: Optional[datetime] = Query(None, description="Filter analyses from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter analyses until this date"),
    current_user = Depends(get_current_user_async)  # CRITICAL: Authentication required
) -> dict:
    """List walk-forward analyses for current user.
    
    CRITICAL: Only returns analyses belonging to current_user.
    All queries automatically filter by user_id to ensure data isolation.
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        analyses, total = await db_service.list_walk_forward_analyses(
            user_id=current_user.id,  # CRITICAL: Always pass user_id
            limit=limit,
            offset=offset,
            symbol=symbol,
            strategy_type=strategy_type,
            start_date=start_date,
            end_date=end_date
        )
        
        # Convert to dict format for response
        analyses_list = []
        for analysis in analyses:
            analyses_list.append({
                "id": str(analysis.id),
                "name": analysis.name,
                "label": analysis.label,
                "symbol": analysis.symbol,
                "strategy_type": analysis.strategy_type,
                "overall_start_time": analysis.overall_start_time.isoformat(),
                "overall_end_time": analysis.overall_end_time.isoformat(),
                "total_windows": analysis.total_windows,
                "total_return_pct": float(analysis.total_return_pct),
                "consistency_score": float(analysis.consistency_score),
                "sharpe_ratio": float(analysis.sharpe_ratio) if analysis.sharpe_ratio else None,
                "max_drawdown_pct": float(analysis.max_drawdown_pct) if analysis.max_drawdown_pct else None,
                "total_trades": analysis.total_trades,
                "avg_win_rate": float(analysis.avg_win_rate),
                "created_at": analysis.created_at.isoformat(),
                "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
            })
        
        return {
            "analyses": analyses_list,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error listing walk-forward analyses: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list analyses: {str(e)}"
        )


@router.get("/walk-forward/history/{analysis_id}")
async def get_walk_forward_analysis_details(
    analysis_id: str,
    current_user = Depends(get_current_user_async)  # CRITICAL: Authentication required
) -> dict:
    """Get detailed walk-forward analysis by ID.
    
    CRITICAL: Only returns analysis if it belongs to current_user.
    Returns 404 if analysis doesn't exist or belongs to different user.
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    from uuid import UUID
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )
    
    try:
        from app.core.database import get_async_session_factory
        
        # Create a new database session for this request
        async_session_factory = await get_async_session_factory()
        
        async with async_session_factory() as db:
            db_service = DatabaseService(db)
            
            analysis = await db_service.get_walk_forward_analysis(analysis_uuid, current_user.id)
            if not analysis:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Analysis not found"
                )
            
            # Get windows if keep_details is True - need to query separately since relationship might not be loaded
            windows_list = []
            if analysis.keep_details:
                from sqlalchemy import select
                from app.models.db_models import WalkForwardWindow
                
                windows_stmt = select(WalkForwardWindow).filter(
                    WalkForwardWindow.analysis_id == analysis_uuid
                ).order_by(WalkForwardWindow.window_number)
                windows_result = await db.execute(windows_stmt)
                windows = windows_result.scalars().all()
                
                for window in windows:
                    windows_list.append({
                    "window_number": window.window_number,
                    "training_start": window.training_start.isoformat(),
                    "training_end": window.training_end.isoformat(),
                    "test_start": window.test_start.isoformat(),
                    "test_end": window.test_end.isoformat(),
                    "optimized_params": window.optimized_params if window.optimized_params else {},
                    "training_return_pct": float(window.training_return_pct) if window.training_return_pct else None,
                    "training_sharpe": float(window.training_sharpe) if window.training_sharpe else None,
                    "training_win_rate": float(window.training_win_rate) if window.training_win_rate else None,
                    "training_trades": window.training_trades,
                    "test_return_pct": float(window.test_return_pct) if window.test_return_pct else None,
                    "test_sharpe": float(window.test_sharpe) if window.test_sharpe else None,
                    "test_win_rate": float(window.test_win_rate) if window.test_win_rate else None,
                    "test_trades": window.test_trades,
                    "test_final_balance": float(window.test_final_balance) if window.test_final_balance else None,
                    "optimization_results": window.optimization_results if window.optimization_results else []
                })
            
            # Get equity curve
            equity_curve = await db_service.get_walk_forward_equity_curve(analysis_uuid, current_user.id)
            
            # Convert equity curve points to proper format
            equity_curve_formatted = []
            for point in equity_curve:
                if point.get("time") is None or point.get("balance") is None:
                    continue
                
                # Convert time to ISO string if it's a datetime object
                time_value = point["time"]
                if isinstance(time_value, datetime):
                    time_str = time_value.isoformat()
                elif hasattr(time_value, 'isoformat'):
                    time_str = time_value.isoformat()
                else:
                    time_str = str(time_value)
                
                # Ensure balance is a float
                balance_value = float(point["balance"]) if point["balance"] is not None else 0.0
                
                equity_curve_formatted.append({
                    "time": time_str,
                    "balance": balance_value,
                    "window_number": point.get("window_number")
                })
            
            return {
                "id": str(analysis.id),
                "name": analysis.name,
                "label": analysis.label,
                "symbol": analysis.symbol,
                "strategy_type": analysis.strategy_type,
                "overall_start_time": analysis.overall_start_time.isoformat(),
                "overall_end_time": analysis.overall_end_time.isoformat(),
                "training_period_days": analysis.training_period_days,
                "test_period_days": analysis.test_period_days,
                "step_size_days": analysis.step_size_days,
                "window_type": analysis.window_type,
                "total_windows": analysis.total_windows,
                "leverage": analysis.leverage,
                "risk_per_trade": float(analysis.risk_per_trade),
                "fixed_amount": float(analysis.fixed_amount) if analysis.fixed_amount else None,
                "initial_balance": float(analysis.initial_balance),
                "params": analysis.params,
                "optimization_enabled": analysis.optimization_enabled,
                "optimization_method": analysis.optimization_method,
                "optimization_metric": analysis.optimization_metric,
                "optimize_params": analysis.optimize_params if analysis.optimize_params else {},
                "min_trades_guardrail": analysis.min_trades_guardrail,
                "max_drawdown_cap": float(analysis.max_drawdown_cap) if analysis.max_drawdown_cap else None,
                "lottery_trade_threshold": float(analysis.lottery_trade_threshold) if analysis.lottery_trade_threshold else None,
                "total_return_pct": float(analysis.total_return_pct),
                "avg_window_return_pct": float(analysis.avg_window_return_pct),
                "consistency_score": float(analysis.consistency_score),
                "sharpe_ratio": float(analysis.sharpe_ratio) if analysis.sharpe_ratio else None,
                "max_drawdown_pct": float(analysis.max_drawdown_pct) if analysis.max_drawdown_pct else None,
                "total_trades": analysis.total_trades,
                "avg_win_rate": float(analysis.avg_win_rate),
                "return_std_dev": float(analysis.return_std_dev) if analysis.return_std_dev else None,
                "best_window": analysis.best_window,
                "worst_window": analysis.worst_window,
                "final_balance": float(analysis.final_balance) if analysis.final_balance else None,
                "execution_time_ms": analysis.execution_time_ms,
                "candles_processed": analysis.candles_processed,
                "windows": windows_list,
                "equity_curve": equity_curve_formatted,
                "created_at": analysis.created_at.isoformat(),
                "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting walk-forward analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis: {str(e)}"
        )


@router.delete("/walk-forward/history/{analysis_id}")
async def delete_walk_forward_analysis_endpoint(
    analysis_id: str,
    current_user = Depends(get_current_user_async)  # CRITICAL: Authentication required
) -> dict:
    """Delete walk-forward analysis.
    
    CRITICAL: Only deletes if analysis belongs to current_user.
    Returns 404 if analysis doesn't exist or belongs to different user.
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    from uuid import UUID
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        success = await db_service.delete_walk_forward_analysis(analysis_uuid, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        return {"success": True, "message": "Analysis deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting walk-forward analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete analysis: {str(e)}"
        )


@router.get("/walk-forward/dashboard/summary")
async def get_walk_forward_dashboard_summary(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    start_date: Optional[datetime] = Query(None, description="Filter analyses from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter analyses until this date"),
    current_user = Depends(get_current_user_async)
) -> dict:
    """Get dashboard summary statistics for walk-forward analyses.
    
    Returns aggregated statistics including:
    - Total analyses count
    - Best return analysis
    - Most consistent analysis
    - Average metrics
    - Success rate
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        # Get all analyses (with high limit to get all)
        analyses, total = await db_service.list_walk_forward_analyses(
            user_id=current_user.id,
            limit=10000,  # High limit to get all
            offset=0,
            symbol=symbol,
            strategy_type=strategy_type,
            start_date=start_date,
            end_date=end_date
        )
        
        if total == 0:
            return {
                "total_analyses": 0,
                "best_return": None,
                "most_consistent": None,
                "best_sharpe": None,
                "average_return": 0.0,
                "average_consistency": 0.0,
                "average_sharpe": None,
                "success_rate": 0.0,
                "positive_analyses": 0,
                "total_analyses_count": 0
            }
        
        # Calculate statistics
        returns = [float(a.total_return_pct) for a in analyses]
        consistency_scores = [float(a.consistency_score) for a in analyses]
        sharpe_ratios = [float(a.sharpe_ratio) for a in analyses if a.sharpe_ratio is not None]
        
        positive_count = sum(1 for r in returns if r > 0)
        success_rate = (positive_count / total) * 100 if total > 0 else 0.0
        
        # Find best performers
        best_return_analysis = max(analyses, key=lambda a: float(a.total_return_pct))
        most_consistent_analysis = max(analyses, key=lambda a: float(a.consistency_score))
        best_sharpe_analysis = None
        if sharpe_ratios:
            best_sharpe_analysis = max(
                [a for a in analyses if a.sharpe_ratio is not None],
                key=lambda a: float(a.sharpe_ratio) if a.sharpe_ratio else -999
            )
        
        return {
            "total_analyses": total,
            "best_return": {
                "id": str(best_return_analysis.id),
                "name": best_return_analysis.name or "Unnamed Analysis",
                "symbol": best_return_analysis.symbol,
                "strategy_type": best_return_analysis.strategy_type,
                "total_return_pct": float(best_return_analysis.total_return_pct),
                "consistency_score": float(best_return_analysis.consistency_score),
                "sharpe_ratio": float(best_return_analysis.sharpe_ratio) if best_return_analysis.sharpe_ratio else None,
                "created_at": best_return_analysis.created_at.isoformat()
            },
            "most_consistent": {
                "id": str(most_consistent_analysis.id),
                "name": most_consistent_analysis.name or "Unnamed Analysis",
                "symbol": most_consistent_analysis.symbol,
                "strategy_type": most_consistent_analysis.strategy_type,
                "total_return_pct": float(most_consistent_analysis.total_return_pct),
                "consistency_score": float(most_consistent_analysis.consistency_score),
                "sharpe_ratio": float(most_consistent_analysis.sharpe_ratio) if most_consistent_analysis.sharpe_ratio else None,
                "created_at": most_consistent_analysis.created_at.isoformat()
            },
            "best_sharpe": {
                "id": str(best_sharpe_analysis.id),
                "name": best_sharpe_analysis.name or "Unnamed Analysis",
                "symbol": best_sharpe_analysis.symbol,
                "strategy_type": best_sharpe_analysis.strategy_type,
                "total_return_pct": float(best_sharpe_analysis.total_return_pct),
                "consistency_score": float(best_sharpe_analysis.consistency_score),
                "sharpe_ratio": float(best_sharpe_analysis.sharpe_ratio) if best_sharpe_analysis.sharpe_ratio else None,
                "created_at": best_sharpe_analysis.created_at.isoformat()
            } if best_sharpe_analysis else None,
            "average_return": sum(returns) / len(returns) if returns else 0.0,
            "average_consistency": sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0.0,
            "average_sharpe": sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else None,
            "success_rate": success_rate,
            "positive_analyses": positive_count,
            "total_analyses_count": total
        }
    except Exception as e:
        logger.error(f"Error getting dashboard summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard summary: {str(e)}"
        )


@router.get("/walk-forward/dashboard/top-performers")
async def get_walk_forward_top_performers(
    limit: int = Query(10, ge=1, le=50, description="Number of top performers to return"),
    sort_by: str = Query("return", description="Sort by: return, consistency, sharpe"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    start_date: Optional[datetime] = Query(None, description="Filter analyses from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter analyses until this date"),
    current_user = Depends(get_current_user_async)
) -> dict:
    """Get top performing walk-forward analyses.
    
    Returns ranked list of analyses sorted by specified metric.
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        # Get all analyses
        analyses, total = await db_service.list_walk_forward_analyses(
            user_id=current_user.id,
            limit=10000,
            offset=0,
            symbol=symbol,
            strategy_type=strategy_type,
            start_date=start_date,
            end_date=end_date
        )
        
        if total == 0:
            return {
                "top_performers": [],
                "total": 0
            }
        
        # Sort by specified metric
        if sort_by == "return":
            sorted_analyses = sorted(analyses, key=lambda a: float(a.total_return_pct), reverse=True)
        elif sort_by == "consistency":
            sorted_analyses = sorted(analyses, key=lambda a: float(a.consistency_score), reverse=True)
        elif sort_by == "sharpe":
            sorted_analyses = sorted(
                [a for a in analyses if a.sharpe_ratio is not None],
                key=lambda a: float(a.sharpe_ratio) if a.sharpe_ratio else -999,
                reverse=True
            )
        else:
            sorted_analyses = sorted(analyses, key=lambda a: float(a.total_return_pct), reverse=True)
        
        # Take top N
        top_analyses = sorted_analyses[:limit]
        
        # Convert to dict format
        performers = []
        for i, analysis in enumerate(top_analyses, 1):
            performers.append({
                "rank": i,
                "id": str(analysis.id),
                "name": analysis.name or "Unnamed Analysis",
                "symbol": analysis.symbol,
                "strategy_type": analysis.strategy_type,
                "total_return_pct": float(analysis.total_return_pct),
                "consistency_score": float(analysis.consistency_score),
                "sharpe_ratio": float(analysis.sharpe_ratio) if analysis.sharpe_ratio else None,
                "max_drawdown_pct": float(analysis.max_drawdown_pct) if analysis.max_drawdown_pct else None,
                "total_trades": analysis.total_trades,
                "avg_win_rate": float(analysis.avg_win_rate),
                "created_at": analysis.created_at.isoformat()
            })
        
        return {
            "top_performers": performers,
            "total": len(performers),
            "sort_by": sort_by
        }
    except Exception as e:
        logger.error(f"Error getting top performers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get top performers: {str(e)}"
        )


@router.get("/walk-forward/dashboard/recommendations")
async def get_walk_forward_recommendations(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    start_date: Optional[datetime] = Query(None, description="Filter analyses from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter analyses until this date"),
    current_user = Depends(get_current_user_async)
) -> dict:
    """Get recommendations based on walk-forward analysis results.
    
    Returns:
    - Best overall configuration
    - Most reliable strategy
    - Best risk-adjusted return
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        # Get all analyses
        analyses, total = await db_service.list_walk_forward_analyses(
            user_id=current_user.id,
            limit=10000,
            offset=0,
            symbol=symbol,
            strategy_type=strategy_type,
            start_date=start_date,
            end_date=end_date
        )
        
        if total == 0:
            return {
                "best_overall": None,
                "most_reliable": None,
                "best_risk_adjusted": None
            }
        
        # Best overall (highest return with good consistency)
        # Score = return * consistency_weight + consistency * (1 - consistency_weight)
        best_overall = max(
            analyses,
            key=lambda a: float(a.total_return_pct) * 0.6 + float(a.consistency_score) * 0.4
        )
        
        # Most reliable (highest consistency with positive return)
        positive_analyses = [a for a in analyses if float(a.total_return_pct) > 0]
        most_reliable = max(
            positive_analyses if positive_analyses else analyses,
            key=lambda a: float(a.consistency_score)
        )
        
        # Best risk-adjusted (highest Sharpe ratio)
        analyses_with_sharpe = [a for a in analyses if a.sharpe_ratio is not None]
        best_risk_adjusted = max(
            analyses_with_sharpe if analyses_with_sharpe else analyses,
            key=lambda a: float(a.sharpe_ratio) if a.sharpe_ratio else -999
        ) if analyses_with_sharpe else None
        
        def format_analysis(analysis):
            return {
                "id": str(analysis.id),
                "name": analysis.name or "Unnamed Analysis",
                "symbol": analysis.symbol,
                "strategy_type": analysis.strategy_type,
                "total_return_pct": float(analysis.total_return_pct),
                "consistency_score": float(analysis.consistency_score),
                "sharpe_ratio": float(analysis.sharpe_ratio) if analysis.sharpe_ratio else None,
                "max_drawdown_pct": float(analysis.max_drawdown_pct) if analysis.max_drawdown_pct else None,
                "total_trades": analysis.total_trades,
                "avg_win_rate": float(analysis.avg_win_rate),
                "created_at": analysis.created_at.isoformat()
            }
        
        return {
            "best_overall": format_analysis(best_overall),
            "most_reliable": format_analysis(most_reliable),
            "best_risk_adjusted": format_analysis(best_risk_adjusted) if best_risk_adjusted else None
        }
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recommendations: {str(e)}"
        )


@router.get("/walk-forward/dashboard/distribution")
async def get_walk_forward_distribution(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    start_date: Optional[datetime] = Query(None, description="Filter analyses from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter analyses until this date"),
    current_user = Depends(get_current_user_async)
) -> dict:
    """Get performance distribution data for charts.
    
    Returns:
    - Return distribution buckets
    - Performance by symbol/strategy heatmap data
    - Statistical summaries
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    from collections import defaultdict
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        # Get all analyses
        analyses, total = await db_service.list_walk_forward_analyses(
            user_id=current_user.id,
            limit=10000,
            offset=0,
            symbol=symbol,
            strategy_type=strategy_type,
            start_date=start_date,
            end_date=end_date
        )
        
        if total == 0:
            return {
                "return_distribution": [],
                "heatmap_data": [],
                "statistics": {}
            }
        
        # Return distribution buckets
        buckets = {
            "<-10%": 0,
            "-10% to 0%": 0,
            "0% to 10%": 0,
            "10% to 20%": 0,
            ">20%": 0
        }
        
        returns = []
        for analysis in analyses:
            return_pct = float(analysis.total_return_pct)
            returns.append(return_pct)
            
            if return_pct < -10:
                buckets["<-10%"] += 1
            elif return_pct < 0:
                buckets["-10% to 0%"] += 1
            elif return_pct < 10:
                buckets["0% to 10%"] += 1
            elif return_pct < 20:
                buckets["10% to 20%"] += 1
            else:
                buckets[">20%"] += 1
        
        return_distribution = [{"range": k, "count": v} for k, v in buckets.items()]
        
        # Heatmap data: Symbol × Strategy Type
        heatmap_data = defaultdict(lambda: defaultdict(lambda: {"count": 0, "total_return": 0.0, "avg_return": 0.0}))
        
        for analysis in analyses:
            sym = analysis.symbol
            strat = analysis.strategy_type
            return_pct = float(analysis.total_return_pct)
            
            heatmap_data[sym][strat]["count"] += 1
            heatmap_data[sym][strat]["total_return"] += return_pct
        
        # Calculate averages
        heatmap_list = []
        for symbol, strategies in heatmap_data.items():
            for strategy, data in strategies.items():
                avg_return = data["total_return"] / data["count"] if data["count"] > 0 else 0.0
                heatmap_list.append({
                    "symbol": symbol,
                    "strategy_type": strategy,
                    "count": data["count"],
                    "avg_return": avg_return
                })
        
        # Statistics
        returns_sorted = sorted(returns)
        median_return = returns_sorted[len(returns_sorted) // 2] if returns_sorted else 0.0
        
        # Calculate quartiles
        q1_idx = len(returns_sorted) // 4
        q3_idx = 3 * len(returns_sorted) // 4
        q1 = returns_sorted[q1_idx] if q1_idx < len(returns_sorted) else 0.0
        q3 = returns_sorted[q3_idx] if q3_idx < len(returns_sorted) else 0.0
        
        # Standard deviation
        if len(returns) > 1:
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
        else:
            std_dev = 0.0
        
        return {
            "return_distribution": return_distribution,
            "heatmap_data": heatmap_list,
            "statistics": {
                "min": min(returns) if returns else 0.0,
                "max": max(returns) if returns else 0.0,
                "median": median_return,
                "q1": q1,
                "q3": q3,
                "mean": sum(returns) / len(returns) if returns else 0.0,
                "std_dev": std_dev
            }
        }
    except Exception as e:
        logger.error(f"Error getting distribution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get distribution: {str(e)}"
        )


@router.get("/walk-forward/dashboard/parameter-insights")
async def get_walk_forward_parameter_insights(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    start_date: Optional[datetime] = Query(None, description="Filter analyses from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter analyses until this date"),
    current_user = Depends(get_current_user_async)
) -> dict:
    """Get parameter insights from walk-forward analyses.
    
    Returns:
    - Best parameter combinations
    - Parameter value performance analysis
    - Training period insights
    - Window type insights
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    from collections import defaultdict
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        # Get all analyses with details
        analyses, total = await db_service.list_walk_forward_analyses(
            user_id=current_user.id,
            limit=10000,
            offset=0,
            symbol=symbol,
            strategy_type=strategy_type,
            start_date=start_date,
            end_date=end_date
        )
        
        if total == 0:
            return {
                "best_combinations": [],
                "parameter_performance": {},
                "training_period_insights": {},
                "window_type_insights": {}
            }
        
        # Get detailed analysis data to access params
        from app.core.database import get_async_session_factory
        async_session_factory = await get_async_session_factory()
        
        parameter_performance = defaultdict(lambda: defaultdict(lambda: {"count": 0, "total_return": 0.0, "returns": []}))
        training_period_stats = defaultdict(lambda: {"count": 0, "total_return": 0.0, "returns": []})
        window_type_stats = defaultdict(lambda: {"count": 0, "total_return": 0.0, "returns": []})
        
        async with async_session_factory() as db_session:
            db_service_detail = DatabaseService(db_session)
            
            for analysis in analyses[:100]:  # Limit to first 100 for performance
                try:
                    analysis_detail = await db_service_detail.get_walk_forward_analysis(analysis.id, current_user.id)
                    if not analysis_detail:
                        continue
                    
                    return_pct = float(analysis.total_return_pct)
                    params = analysis_detail.params if analysis_detail.params else {}
                    
                    # Analyze key parameters
                    for param_name, param_value in params.items():
                        if param_name in ['ema_fast', 'ema_slow', 'rsi_period', 'take_profit_pct', 'stop_loss_pct']:
                            param_key = f"{param_name}={param_value}"
                            parameter_performance[param_name][param_value]["count"] += 1
                            parameter_performance[param_name][param_value]["total_return"] += return_pct
                            parameter_performance[param_name][param_value]["returns"].append(return_pct)
                    
                    # Training period analysis
                    training_days = analysis_detail.training_period_days
                    training_period_stats[training_days]["count"] += 1
                    training_period_stats[training_days]["total_return"] += return_pct
                    training_period_stats[training_days]["returns"].append(return_pct)
                    
                    # Window type analysis
                    window_type = analysis_detail.window_type
                    window_type_stats[window_type]["count"] += 1
                    window_type_stats[window_type]["total_return"] += return_pct
                    window_type_stats[window_type]["returns"].append(return_pct)
                    
                except Exception as e:
                    logger.warning(f"Error processing analysis {analysis.id} for insights: {e}")
                    continue
        
        # Calculate averages and find best values
        param_insights = {}
        for param_name, values in parameter_performance.items():
            best_value = None
            best_avg = float('-inf')
            
            for value, data in values.items():
                if data["count"] >= 2:  # Only consider parameters with at least 2 occurrences
                    avg_return = data["total_return"] / data["count"]
                    if avg_return > best_avg:
                        best_avg = avg_return
                        best_value = value
            
            if best_value:
                param_insights[param_name] = {
                    "best_value": best_value,
                    "best_avg_return": best_avg,
                    "total_occurrences": sum(v["count"] for v in values.values())
                }
        
        # Training period insights
        best_training_period = None
        best_training_avg = float('-inf')
        for period, data in training_period_stats.items():
            if data["count"] >= 2:
                avg_return = data["total_return"] / data["count"]
                if avg_return > best_training_avg:
                    best_training_avg = avg_return
                    best_training_period = period
        
        # Window type insights
        window_type_insights = {}
        for window_type, data in window_type_stats.items():
            if data["count"] >= 2:
                avg_return = data["total_return"] / data["count"]
                window_type_insights[window_type] = {
                    "avg_return": avg_return,
                    "count": data["count"]
                }
        
        return {
            "parameter_performance": param_insights,
            "training_period_insights": {
                "best_period": best_training_period,
                "best_avg_return": best_training_avg if best_training_period else None,
                "all_periods": {str(k): {"avg_return": v["total_return"] / v["count"], "count": v["count"]} 
                               for k, v in training_period_stats.items() if v["count"] >= 2}
            },
            "window_type_insights": window_type_insights
        }
    except Exception as e:
        logger.error(f"Error getting parameter insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get parameter insights: {str(e)}"
        )


@router.get("/walk-forward/dashboard/trends")
async def get_walk_forward_trends(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    start_date: Optional[datetime] = Query(None, description="Filter analyses from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter analyses until this date"),
    current_user = Depends(get_current_user_async)
) -> dict:
    """Get trends over time for walk-forward analyses.
    
    Returns:
    - Performance over time (grouped by month/week)
    - Performance by strategy type over time
    - Symbol performance trends
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    from collections import defaultdict
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        # Get all analyses
        analyses, total = await db_service.list_walk_forward_analyses(
            user_id=current_user.id,
            limit=10000,
            offset=0,
            symbol=symbol,
            strategy_type=strategy_type,
            start_date=start_date,
            end_date=end_date
        )
        
        if total == 0:
            return {
                "time_series": [],
                "by_strategy_type": {},
                "by_symbol": {}
            }
        
        # Group by month
        monthly_data = defaultdict(lambda: {"count": 0, "total_return": 0.0, "returns": []})
        by_strategy = defaultdict(lambda: defaultdict(lambda: {"count": 0, "total_return": 0.0}))
        by_symbol = defaultdict(lambda: {"count": 0, "total_return": 0.0, "returns": []})
        
        for analysis in analyses:
            created_at = analysis.created_at
            month_key = created_at.strftime("%Y-%m")
            
            return_pct = float(analysis.total_return_pct)
            
            # Monthly aggregation
            monthly_data[month_key]["count"] += 1
            monthly_data[month_key]["total_return"] += return_pct
            monthly_data[month_key]["returns"].append(return_pct)
            
            # By strategy type
            by_strategy[analysis.strategy_type][month_key]["count"] += 1
            by_strategy[analysis.strategy_type][month_key]["total_return"] += return_pct
            
            # By symbol
            by_symbol[analysis.symbol]["count"] += 1
            by_symbol[analysis.symbol]["total_return"] += return_pct
            by_symbol[analysis.symbol]["returns"].append(return_pct)
        
        # Format time series
        time_series = []
        for month in sorted(monthly_data.keys()):
            data = monthly_data[month]
            time_series.append({
                "period": month,
                "count": data["count"],
                "avg_return": data["total_return"] / data["count"] if data["count"] > 0 else 0.0,
                "total_return": data["total_return"]
            })
        
        # Format by strategy type
        strategy_trends = {}
        for strategy, months in by_strategy.items():
            strategy_trends[strategy] = []
            for month in sorted(months.keys()):
                data = months[month]
                strategy_trends[strategy].append({
                    "period": month,
                    "count": data["count"],
                    "avg_return": data["total_return"] / data["count"] if data["count"] > 0 else 0.0
                })
        
        # Format by symbol
        symbol_trends = {}
        for symbol, data in by_symbol.items():
            symbol_trends[symbol] = {
                "count": data["count"],
                "avg_return": data["total_return"] / data["count"] if data["count"] > 0 else 0.0,
                "total_return": data["total_return"]
            }
        
        return {
            "time_series": time_series,
            "by_strategy_type": strategy_trends,
            "by_symbol": symbol_trends
        }
    except Exception as e:
        logger.error(f"Error getting trends: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trends: {str(e)}"
        )


@router.get("/walk-forward/history/{analysis_id}/config")
async def get_walk_forward_config(
    analysis_id: str,
    current_user = Depends(get_current_user_async)  # CRITICAL: Authentication required
) -> dict:
    """Get configuration from saved analysis for reuse.
    
    CRITICAL: Only returns config if analysis belongs to current_user.
    Returns 404 if analysis doesn't exist or belongs to different user.
    
    Returns:
        Configuration that can be used to recreate the analysis
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    from uuid import UUID
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        analysis = await db_service.get_walk_forward_analysis(analysis_uuid, current_user.id)
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        # Extract and return configuration
        config = {
            "symbol": analysis.symbol,
            "strategy_type": analysis.strategy_type,
            "start_time": analysis.overall_start_time.isoformat(),
            "end_time": analysis.overall_end_time.isoformat(),
            "training_period_days": analysis.training_period_days,
            "test_period_days": analysis.test_period_days,
            "step_size_days": analysis.step_size_days,
            "window_type": analysis.window_type,
            "leverage": analysis.leverage,
            "risk_per_trade": float(analysis.risk_per_trade),
            "initial_balance": float(analysis.initial_balance),
            "params": analysis.params,
            "optimization_enabled": analysis.optimization_enabled,
        }
        
        # Add optimization settings if enabled
        if analysis.optimization_enabled:
            config.update({
                "optimization_method": analysis.optimization_method,
                "optimization_metric": analysis.optimization_metric,
                "optimize_params": analysis.optimize_params if analysis.optimize_params else {},
                "min_trades_guardrail": analysis.min_trades_guardrail,
                "max_drawdown_cap": float(analysis.max_drawdown_cap) if analysis.max_drawdown_cap else None,
                "lottery_trade_threshold": float(analysis.lottery_trade_threshold) if analysis.lottery_trade_threshold else None,
            })
        
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting walk-forward config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get config: {str(e)}"
        )


# ============================================================================
# PARAMETER SENSITIVITY ANALYSIS ENDPOINTS
# ============================================================================

@router.post("/sensitivity-analysis/start")
async def start_sensitivity_analysis(
    request: Annotated[dict, Body()],
    current_user = Depends(get_current_user_async),
    client: BinanceClient = Depends(get_binance_client)
) -> dict:
    """
    Start parameter sensitivity analysis and return task ID for progress tracking.
    
    Requires authentication. Checks concurrency limits before starting.
    
    Returns:
        {"task_id": "uuid", "message": "Analysis started"}
    
    Raises:
        HTTPException 429: If concurrency limits are exceeded
    """
    from app.services.sensitivity_analysis import SensitivityAnalysisRequest, run_sensitivity_analysis
    from app.services.walk_forward_task_manager import get_task_manager
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    import time
    
    # Get user ID
    user_id = str(current_user.id)
    
    # Get settings for concurrency limits
    settings = get_settings()
    
    # Parse and validate request
    try:
        sensitivity_request = SensitivityAnalysisRequest(**request)
    except Exception as e:
        logger.error(f"Invalid sensitivity analysis request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request: {str(e)}"
        )
    
    # Calculate total tests (sum of all parameter values to test)
    total_tests = sum(len(values) for values in sensitivity_request.analyze_params.values())
    
    # Get task manager
    task_manager = get_task_manager()
    
    # Check concurrency limits
    user_running = await task_manager.count_user_running_tasks(user_id)
    max_concurrent = settings.max_concurrent_walk_forward_analyses  # Reuse same limit
    if user_running >= max_concurrent:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum concurrent analyses limit reached ({max_concurrent}). Please wait for existing analyses to complete."
        )
    
    # Create task
    task_id = await task_manager.create_task(total_tests, user_id)
    
    # Background task to run analysis
    async def run_analysis():
        start_time = time.time()
        try:
            # Update progress: starting
            await task_manager.update_progress(
                task_id,
                current_phase="initializing",
                message="Starting sensitivity analysis..."
            )
            
            # Run analysis with progress callback
            async def update_progress_callback(current_window, total_windows, current_phase, message, phase_progress):
                # Note: total_windows is set at task creation, not in update_progress
                await task_manager.update_progress(
                    task_id,
                    current_window=current_window,
                    current_phase=current_phase,
                    message=message,
                    phase_progress=phase_progress
                )
            
            result = await run_sensitivity_analysis(
                sensitivity_request, 
                client,
                task_id=task_id,
                progress_callback=update_progress_callback
            )
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Store result in task manager
            try:
                if hasattr(result, 'model_dump'):
                    result_dict = result.model_dump()
                elif hasattr(result, 'dict'):
                    result_dict = result.dict()
                else:
                    result_dict = result
                
                await task_manager.complete_task(task_id, result_dict)
                logger.info(f"✅ Sensitivity analysis {task_id} completed in {execution_time_ms}ms")
                
                # Save to database
                try:
                    async_db_gen = get_async_db()
                    db = await async_db_gen.__anext__()
                    db_service = DatabaseService(db)
                    
                    analysis_id = await db_service.save_sensitivity_analysis(
                        user_id=current_user.id,
                        result=result,
                        request=sensitivity_request,
                        name=sensitivity_request.name
                    )
                    logger.info(f"✅ Saved sensitivity analysis {analysis_id} to database for user {user_id}")
                except Exception as save_error:
                    logger.error(f"❌ Failed to save sensitivity analysis to database: {save_error}", exc_info=True)
                    # Don't fail the analysis - just log the error
            except Exception as serialize_error:
                logger.error(f"Error serializing result: {serialize_error}", exc_info=True)
                await task_manager.fail_task(task_id, f"Failed to serialize result: {str(serialize_error)}")
        except HTTPException as e:
            if e.status_code == 499:  # Cancelled
                await task_manager.cancel_task(task_id)
            else:
                await task_manager.fail_task(task_id, str(e.detail))
        except Exception as e:
            logger.error(f"Error in sensitivity analysis: {e}", exc_info=True)
            await task_manager.fail_task(task_id, str(e))
    
    # Run in background
    asyncio.create_task(run_analysis())
    
    logger.info(f"Started sensitivity analysis {task_id} for user {user_id} ({total_tests} tests)")
    return {
        "task_id": task_id,
        "message": "Sensitivity analysis started",
        "total_tests": total_tests
    }


@router.get("/sensitivity-analysis/progress/{task_id}")
async def get_sensitivity_progress(
    task_id: str,
    token: Optional[str] = Query(None, description="Auth token (for EventSource compatibility)"),
    request: Request = None
):
    """
    Server-Sent Events endpoint for sensitivity analysis progress.
    
    Returns real-time progress updates including:
    - Current parameter being tested
    - Total parameters
    - Progress percentage
    - Estimated time remaining
    - Current phase
    - Status message
    
    Note: Token can be passed as query parameter for EventSource compatibility
    """
    from app.services.walk_forward_task_manager import get_task_manager
    from fastapi import status
    
    task_manager = get_task_manager()
    progress = await task_manager.get_progress(task_id)
    
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    async def event_generator():
        last_progress = None
        while True:
            current_progress = await task_manager.get_progress(task_id)
            
            if not current_progress:
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                break
            
            # Only send update if progress changed
            if current_progress != last_progress:
                progress_dict = {
                    "task_id": current_progress.task_id,
                    "status": current_progress.status,
                    "current_window": current_progress.current_window,
                    "total_windows": current_progress.total_windows,
                    "progress_percent": current_progress.progress_percent,
                    "current_phase": current_progress.current_phase,
                    "message": current_progress.message,
                    "estimated_time_remaining_seconds": current_progress.estimated_time_remaining_seconds,
                    "error": current_progress.error
                }
                
                yield f"data: {json.dumps(progress_dict)}\n\n"
                last_progress = current_progress
            
            if current_progress.status in ("completed", "cancelled", "error"):
                break
            
            await asyncio.sleep(1)  # Update every second
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sensitivity-analysis/result/{task_id}")
async def get_sensitivity_result(
    task_id: str,
    current_user = Depends(get_current_user_async)
) -> dict:
    """
    Get the final result of a completed sensitivity analysis.
    
    Requires authentication and verifies task ownership.
    """
    from app.services.walk_forward_task_manager import get_task_manager
    from fastapi import status
    
    task_manager = get_task_manager()
    user_id = str(current_user.id)
    
    progress = await task_manager.get_progress(task_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Verify ownership
    if progress.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    if progress.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Analysis is not completed. Status: {progress.status}"
        )
    
    if not progress.result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Result not available"
        )
    
    return progress.result


@router.post("/sensitivity-analysis/cancel/{task_id}")
async def cancel_sensitivity_analysis(
    task_id: str,
    current_user = Depends(get_current_user_async)
) -> dict:
    """
    Cancel a running sensitivity analysis.
    
    Requires authentication and verifies task ownership.
    
    Returns:
        {"success": true, "message": "Task cancelled"}
    """
    from app.services.walk_forward_task_manager import get_task_manager
    from fastapi import status
    
    task_manager = get_task_manager()
    user_id = str(current_user.id)
    
    progress = await task_manager.get_progress(task_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Verify ownership
    if progress.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    if progress.status not in ("running", "pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task with status: {progress.status}"
        )
    
    await task_manager.cancel_task(task_id)
    
    return {"success": True, "message": "Task cancelled"}


@router.get("/sensitivity-analysis/history")
async def list_sensitivity_analyses(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of analyses to return"),
    offset: int = Query(0, ge=0, description="Number of analyses to skip"),
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g., BTCUSDT)"),
    strategy_type: Optional[str] = Query(None, description="Filter by strategy type"),
    current_user = Depends(get_current_user_async)  # CRITICAL: Authentication required
) -> dict:
    """List sensitivity analyses for current user.
    
    CRITICAL: Only returns analyses that belong to current_user.
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        analyses, total = await db_service.list_sensitivity_analyses(
            user_id=current_user.id,  # CRITICAL: User isolation
            limit=limit,
            offset=offset,
            symbol=symbol,
            strategy_type=strategy_type
        )
        
        # Convert to dict format
        analyses_list = []
        for analysis in analyses:
            analyses_list.append({
                "id": str(analysis.id),
                "name": analysis.name,
                "symbol": analysis.symbol,
                "strategy_type": analysis.strategy_type,
                "start_time": analysis.start_time.isoformat(),
                "end_time": analysis.end_time.isoformat(),
                "metric": analysis.metric,
                "kline_interval": analysis.kline_interval,
                "most_sensitive_param": analysis.most_sensitive_param,
                "least_sensitive_param": analysis.least_sensitive_param,
                "created_at": analysis.created_at.isoformat(),
                "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None
            })
        
        return {
            "analyses": analyses_list,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error listing sensitivity analyses: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list analyses: {str(e)}"
        )


@router.get("/sensitivity-analysis/history/{analysis_id}")
async def get_sensitivity_analysis_details(
    analysis_id: str,
    current_user = Depends(get_current_user_async)  # CRITICAL: Authentication required
) -> dict:
    """Get detailed sensitivity analysis by ID.
    
    CRITICAL: Only returns analysis if it belongs to current_user.
    Returns 404 if analysis doesn't exist or belongs to different user.
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    from uuid import UUID
    from sqlalchemy import select
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        analysis = await db_service.get_sensitivity_analysis(analysis_uuid, current_user.id)
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        # Get parameter results
        from app.models.db_models import SensitivityParameterResult
        if db_service._is_async:
            stmt = select(SensitivityParameterResult).filter(
                SensitivityParameterResult.analysis_id == analysis_uuid
            ).order_by(SensitivityParameterResult.created_at)
            result = await db.execute(stmt)
            param_results = list(result.scalars().all())
        else:
            param_results = db.query(SensitivityParameterResult).filter(
                SensitivityParameterResult.analysis_id == analysis_uuid
            ).order_by(SensitivityParameterResult.created_at).all()
        
        # Format parameter results
        parameter_results = []
        for param_result in param_results:
            parameter_results.append({
                "parameter_name": param_result.parameter_name,
                "base_value": param_result.base_value,
                "tested_values": param_result.tested_values,
                "sensitivity_score": float(param_result.sensitivity_score),
                "optimal_value": param_result.optimal_value,
                "worst_value": param_result.worst_value,
                "impact_range": float(param_result.impact_range) if param_result.impact_range else None,
                "impact_range_display": param_result.impact_range_display,
                "results": param_result.results
            })
        
        return {
            "id": str(analysis.id),
            "name": analysis.name,
            "symbol": analysis.symbol,
            "strategy_type": analysis.strategy_type,
            "start_time": analysis.start_time.isoformat(),
            "end_time": analysis.end_time.isoformat(),
            "base_params": analysis.base_params,
            "analyze_params": analysis.analyze_params,
            "metric": analysis.metric,
            "kline_interval": analysis.kline_interval,
            "leverage": analysis.leverage,
            "risk_per_trade": float(analysis.risk_per_trade),
            "fixed_amount": float(analysis.fixed_amount) if analysis.fixed_amount else None,
            "initial_balance": float(analysis.initial_balance),
            "most_sensitive_param": analysis.most_sensitive_param,
            "least_sensitive_param": analysis.least_sensitive_param,
            "recommended_params": analysis.recommended_params,
            "parameter_results": parameter_results,
            "created_at": analysis.created_at.isoformat(),
            "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sensitivity analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis: {str(e)}"
        )


@router.delete("/sensitivity-analysis/history/{analysis_id}")
async def delete_sensitivity_analysis_endpoint(
    analysis_id: str,
    current_user = Depends(get_current_user_async)  # CRITICAL: Authentication required
) -> dict:
    """Delete sensitivity analysis.
    
    CRITICAL: Only deletes if analysis belongs to current_user.
    Returns 404 if analysis doesn't exist or belongs to different user.
    """
    from app.services.database_service import DatabaseService
    from app.api.deps import get_async_db
    from fastapi import status
    from uuid import UUID
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )
    
    try:
        async_db_gen = get_async_db()
        db = await async_db_gen.__anext__()
        db_service = DatabaseService(db)
        
        success = await db_service.delete_sensitivity_analysis(analysis_uuid, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        return {"success": True, "message": "Analysis deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting sensitivity analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete analysis: {str(e)}"
        )

