"""
Backtesting API endpoint for strategy performance analysis on historical data.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_binance_client
from app.core.my_binance_client import BinanceClient
from app.strategies.base import StrategyContext, StrategySignal
from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.range_mean_reversion import RangeMeanReversionStrategy
from app.strategies.indicators import calculate_ema, calculate_rsi
from app.risk.manager import RiskManager, PositionSizingResult
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
        """Return historical klines (already provided in constructor)."""
        return self.klines
    
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
    
    # Calculate how many candles we need
    interval_seconds_map = {
        "1s": 1, "3s": 3, "5s": 5, "10s": 10, "30s": 30,  # Second-based intervals for high-frequency trading
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200, "1d": 86400
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
        needs_pagination = estimated_candles > MAX_KLINES_PER_REQUEST
        
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
            # Single request is sufficient
            logger.info(f"Fetching historical klines for {symbol} using timestamps: {start_timestamp} to {end_timestamp} (UTC)")
            
            try:
                # Try futures_historical_klines first (handles date ranges automatically)
                if hasattr(rest, 'futures_historical_klines'):
                    start_str = start_time.strftime("%d %b %Y %H:%M:%S")
                    end_str = end_time.strftime("%d %b %Y %H:%M:%S")
                    logger.debug(f"Using futures_historical_klines with string format: {start_str} to {end_str}")
                    try:
                        klines = rest.futures_historical_klines(
                            symbol=symbol,
                            interval=interval,
                            start_str=start_str,
                            end_str=end_str
                        )
                        all_klines = klines if klines else []
                        logger.info(f"Fetched {len(all_klines)} historical klines using futures_historical_klines (string format)")
                        
                        # Verify the fetched klines are within the requested time range
                        if all_klines:
                            first_kline_time = int(all_klines[0][0])
                            last_kline_time = int(all_klines[-1][0])
                            time_diff_start = abs(first_kline_time - start_timestamp)
                            time_diff_end = abs(last_kline_time - end_timestamp)
                            # Allow some tolerance (up to 1 hour difference might indicate timezone issue)
                            if time_diff_start > 3600000 or time_diff_end > 3600000:
                                logger.warning(
                                    f"Potential timezone issue: Fetched klines time range ({first_kline_time} to {last_kline_time}) "
                                    f"differs significantly from requested range ({start_timestamp} to {end_timestamp}). "
                                    f"Differences: {time_diff_start/1000/60:.1f} min start, {time_diff_end/1000/60:.1f} min end"
                                )
                    except Exception as str_format_error:
                        logger.warning(f"futures_historical_klines failed: {str_format_error}, trying timestamp method")
                        # Fall through to timestamp method
                
                # Fallback: Use futures_klines with timestamps
                if not all_klines:
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
                        logger.info(f"Fetched {len(all_klines)} klines within time range using futures_klines with timestamps")
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
    
    # Remove duplicates and sort by timestamp
    if all_klines:
        # Remove duplicates based on timestamp
        seen_timestamps = set()
        unique_klines = []
        for k in all_klines:
            timestamp = int(k[0])
            if timestamp not in seen_timestamps:
                seen_timestamps.add(timestamp)
                unique_klines.append(k)
        
        # Sort by timestamp
        unique_klines.sort(key=lambda k: int(k[0]))
        all_klines = unique_klines
    
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


async def run_backtest(
    request: BacktestRequest,
    client: BinanceClient
) -> BacktestResult:
    """Run backtesting on historical data."""
    
    # Ensure start_time and end_time are timezone-aware (UTC)
    if request.start_time.tzinfo is None:
        request.start_time = request.start_time.replace(tzinfo=timezone.utc)
    if request.end_time.tzinfo is None:
        request.end_time = request.end_time.replace(tzinfo=timezone.utc)
    
    # Determine interval from params or default
    interval = request.params.get("kline_interval", "1m" if request.strategy_type == "scalping" else "5m")
    
    # Calculate interval_seconds for strategy context
    interval_seconds_map = {
        "1s": 1, "3s": 3, "5s": 5, "10s": 10, "30s": 30,  # Second-based intervals for high-frequency trading
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200, "1d": 86400
    }
    interval_seconds = interval_seconds_map.get(interval, 60)
    
    # Fetch historical klines
    filtered_klines = await _fetch_historical_klines(
        client=client,
        symbol=request.symbol,
        interval=interval,
        start_time=request.start_time,
        end_time=request.end_time
    )
    
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
    if request.strategy_type == "range_mean_reversion":
        lookback = int(request.params.get("lookback_period", 150))
        ema_slow = int(request.params.get("ema_slow_period", 50))
        rsi_p = int(request.params.get("rsi_period", 14))
        min_required_candles = max(lookback + 1, ema_slow + 1, rsi_p + 1)
        logger.info(f"Starting backtest: Processing {len(filtered_klines)} candles for {request.symbol} from {request.start_time} to {request.end_time}")
        logger.info(f"Strategy: {request.strategy_type}, Params: {request.params}")
        logger.info(f"Range mean reversion requires: lookback={lookback}, ema_slow={ema_slow}, rsi_period={rsi_p}. Will start evaluating after {min_required_candles} candles.")
    else:
        # Scalping strategy
        slow_period = int(request.params.get("ema_slow", 21))
        fast_period = int(request.params.get("ema_fast", 8))
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
        
        strategy_klines = filtered_klines[:i+1]
        # Now we have at least 2 klines:
        # - klines[:-1] = all closed candles (at least klines[0])
        # - klines[-1] = current forming candle (klines[i])
        
        # Replace client's get_klines to return subset for this evaluation
        original_get_klines = mock_client.get_klines
        def get_klines_subset(symbol: str, interval: str, limit: int = 1000, start_time: Optional[int] = None, end_time: Optional[int] = None):
            # Return all klines up to current index
            # The strategy will treat klines[:-1] as closed and klines[-1] as forming
            return strategy_klines
        mock_client.get_klines = get_klines_subset
        
        try:
            # Evaluate strategy (this will use the klines we provide)
            signal = await strategy.evaluate()
            # Track signal counts
            signal_counts[signal.action] = signal_counts.get(signal.action, 0) + 1
            # Log ALL non-HOLD signals for debugging
            if signal.action != "HOLD":
                logger.info(f"Candle {i}/{len(filtered_klines)}: {signal.action} signal at {current_price:.8f} (confidence: {signal.confidence:.2f}), current_trade={current_trade is not None if current_trade else False}")
                logger.info(f"  -> Signal type: {type(signal.action)}, value: '{signal.action}', repr: {repr(signal.action)}")
                logger.info(f"  -> Signal will be processed: {signal.action in ('BUY', 'SELL')}, current_trade is None: {current_trade is None}")
            # Log signal for debugging (first few, every 100th)
            elif i < 10 or i % 100 == 0:
                logger.info(f"Candle {i}/{len(filtered_klines)}: {signal.action} at {current_price:.8f} (confidence: {signal.confidence:.2f})")
        except IndexError as e:
            # This happens when closed_klines is empty (i.e., only 1 kline provided)
            logger.error(f"IndexError at candle {i}: {e}. Need at least 2 klines. Provided {len(strategy_klines)} klines.")
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
        finally:
            # Restore original get_klines
            mock_client.get_klines = original_get_klines
        
        # Capture indicator snapshot for range mean reversion
        if request.strategy_type == "range_mean_reversion" and i >= min_required_candles:
            candle_timestamp = int(kline[0]) // 1000
            snapshot = {
                "time": candle_timestamp,
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
                    buy_zone_pct = float(request.params.get("buy_zone_pct", 0.2))
                    sell_zone_pct = float(request.params.get("sell_zone_pct", 0.2))
                    snapshot["buy_zone_upper"] = strategy.range_low + (range_size * buy_zone_pct)
                    snapshot["sell_zone_lower"] = strategy.range_high - (range_size * sell_zone_pct)
                    
                    # Calculate TP/SL levels if position is open
                    if hasattr(strategy, 'position') and strategy.position is not None:
                        snapshot["position_side"] = strategy.position
                        tp_buffer_pct = float(request.params.get("tp_buffer_pct", 0.001))
                        sl_buffer_pct = float(request.params.get("sl_buffer_pct", 0.002))
                        
                        if strategy.position == "LONG":
                            snapshot["tp1"] = strategy.range_mid
                            snapshot["tp2"] = strategy.range_high - (range_size * tp_buffer_pct)
                            snapshot["sl"] = strategy.range_low - (range_size * sl_buffer_pct)
                        else:  # SHORT
                            snapshot["tp1"] = strategy.range_mid
                            snapshot["tp2"] = strategy.range_low + (range_size * tp_buffer_pct)
                            snapshot["sl"] = strategy.range_high + (range_size * sl_buffer_pct)
            
            # Calculate RSI if we have enough data
            if i >= min_required_candles:
                closing_prices = [float(k[4]) for k in filtered_klines[:i+1]]
                rsi_period = int(request.params.get("rsi_period", 14))
                if len(closing_prices) >= rsi_period + 1:
                    snapshot["rsi"] = calculate_rsi(closing_prices, rsi_period)
            
            # Calculate EMA fast and slow
            if i >= min_required_candles:
                closing_prices = [float(k[4]) for k in filtered_klines[:i+1]]
                ema_fast_period = int(request.params.get("ema_fast_period", 20))
                ema_slow_period = int(request.params.get("ema_slow_period", 50))
                
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
                    # This matches the strategy's _check_tp_sl() behavior
                    on_entry_candle = False
                    if hasattr(strategy, 'entry_candle_time') and hasattr(strategy, 'last_closed_candle_time'):
                        if strategy.entry_candle_time is not None and strategy.last_closed_candle_time is not None:
                            on_entry_candle = (strategy.entry_candle_time == strategy.last_closed_candle_time)
                    
                    if on_entry_candle:
                        logger.debug(f"Skipping fixed TP/SL check on entry candle (entry_candle_time={strategy.entry_candle_time}, last_closed={strategy.last_closed_candle_time})")
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
                        on_entry_candle = False
                        if hasattr(strategy, 'entry_candle_time') and hasattr(strategy, 'last_closed_candle_time'):
                            if strategy.entry_candle_time is not None and strategy.last_closed_candle_time is not None:
                                on_entry_candle = (strategy.entry_candle_time == strategy.last_closed_candle_time)
                        
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
            
            logger.info(f"Signal check: {signal.action} at candle {i}, current_trade={current_trade is not None}")
            if current_trade is not None:
                logger.warning(f"Skipping {signal.action} signal at candle {i}: position already open ({current_trade.position_side})")
            else:
                logger.info(f"Processing {signal.action} signal at candle {i}, price {current_price:.8f}")
                # Calculate position size
                try:
                    sizing = risk_manager.size_position(
                        symbol=request.symbol,
                        risk_per_trade=request.risk_per_trade,
                        price=current_price,
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
                
                # Apply spread offset on entry
                if position_side == "LONG":
                    real_entry_price = current_price * (1 + SPREAD_OFFSET)  # Pay ask price
                else:  # SHORT
                    real_entry_price = current_price * (1 - SPREAD_OFFSET)  # Sell at bid price
                
                # Calculate executed notional using real entry price (with spread)
                # This matches exit fee logic which uses exit notional
                entry_notional = sizing.quantity * real_entry_price
                entry_fee = entry_notional * AVERAGE_FEE_RATE
                
                # Check if we have enough balance for entry fee
                if balance < entry_fee:
                    logger.warning(f"Insufficient balance for trade: balance={balance:.2f}, entry_fee={entry_fee:.2f}")
                    continue  # Skip trade if insufficient balance
                
                # Create new trade
                logger.info(f"Creating {position_side} trade: entry={real_entry_price:.8f} (spread-adjusted from {current_price:.8f}), quantity={sizing.quantity:.8f}, executed_notional={entry_notional:.2f}")
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
                    # Use the last closed candle time from the strategy (where entry signal was generated)
                    if hasattr(strategy, 'last_closed_candle_time') and strategy.last_closed_candle_time is not None:
                        strategy.entry_candle_time = strategy.last_closed_candle_time
                        logger.debug(f"Set entry_candle_time={strategy.entry_candle_time} to prevent same-candle exits")
                    else:
                        # Fallback: use current candle's open time (in milliseconds)
                        strategy.entry_candle_time = int(kline[0])
                        logger.debug(f"Set entry_candle_time={strategy.entry_candle_time} (fallback to current candle)")
                    
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
            "rsi_period": int(request.params.get("rsi_period", 14)),
            "rsi_oversold": float(request.params.get("rsi_oversold", 40)),
            "rsi_overbought": float(request.params.get("rsi_overbought", 60)),
            "ema_fast_period": int(request.params.get("ema_fast_period", 20)),
            "ema_slow_period": int(request.params.get("ema_slow_period", 50)),
            "max_ema_spread_pct": float(request.params.get("max_ema_spread_pct", 0.005)),
            "buy_zone_pct": float(request.params.get("buy_zone_pct", 0.2)),
            "sell_zone_pct": float(request.params.get("sell_zone_pct", 0.2))
        }
    elif request.strategy_type == "scalping":
        # Extract closing prices
        closing_prices = [float(k[4]) for k in filtered_klines]
        
        # Calculate EMA fast and slow
        ema_fast_values = []
        ema_slow_values = []
        
        fast_period = int(request.params.get("ema_fast", 8))
        slow_period = int(request.params.get("ema_slow", 21))
        
        for i in range(len(closing_prices)):
            # EMA fast
            prices_up_to_i = closing_prices[:i+1]
            ema_fast = calculate_ema(prices_up_to_i, fast_period) if len(prices_up_to_i) >= fast_period else None
            ema_fast_values.append(ema_fast)
            
            # EMA slow
            ema_slow = calculate_ema(prices_up_to_i, slow_period) if len(prices_up_to_i) >= slow_period else None
            ema_slow_values.append(ema_slow)
        
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
        klines=klines_data,
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
    """
    return await run_backtest(request, client)

