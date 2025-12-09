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
    
    # Fetch historical klines
    start_timestamp = int(request.start_time.timestamp() * 1000)
    end_timestamp = int(request.end_time.timestamp() * 1000)
    
    # Determine interval from params or default
    interval = request.params.get("kline_interval", "1m" if request.strategy_type == "scalping" else "5m")
    
    # Fetch historical klines using python-binance directly
    # Calculate how many candles we need
    interval_seconds_map = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200, "1d": 86400
    }
    interval_seconds = interval_seconds_map.get(interval, 60)
    duration_seconds = (end_timestamp - start_timestamp) / 1000
    estimated_candles = int(duration_seconds / interval_seconds) + 200  # Add buffer
    
    # Fetch historical klines
    all_klines = []
    try:
        # Use python-binance client directly for historical data
        rest = client._ensure()
        
        # Use futures_historical_klines for historical data (proper method)
        # This method is specifically designed for fetching historical klines with start/end times
        try:
            # Check if futures_historical_klines method exists
            if hasattr(rest, 'futures_historical_klines'):
                # Use the proper historical klines method
                # Format: "01 Jan 2025 12:00:00"
                start_str = request.start_time.strftime("%d %b %Y %H:%M:%S")
                end_str = request.end_time.strftime("%d %b %Y %H:%M:%S")
                logger.info(f"Fetching historical klines for {request.symbol} from {start_str} to {end_str}")
                klines = rest.futures_historical_klines(
                    symbol=request.symbol,
                    interval=interval,
                    start_str=start_str,
                    end_str=end_str
                )
                all_klines = klines if klines else []
                logger.info(f"Fetched {len(all_klines)} historical klines using futures_historical_klines")
            else:
                # Fallback: try futures_klines with startTime/endTime
                limit = min(estimated_candles, 1500)
                logger.info(f"futures_historical_klines not available, using futures_klines with limit={limit}")
                try:
                    klines = rest.futures_klines(
                        symbol=request.symbol,
                        interval=interval,
                        limit=limit,
                        startTime=start_timestamp,
                        endTime=end_timestamp
                    )
                    all_klines = klines if klines else []
                except (TypeError, AttributeError) as e:
                    logger.warning(f"futures_klines with startTime/endTime failed: {e}, using fallback")
                    # If startTime/endTime not supported, fetch recent and filter
                    klines = rest.futures_klines(symbol=request.symbol, interval=interval, limit=limit)
                    # Filter by time range
                    all_klines = [
                        k for k in (klines or [])
                        if start_timestamp <= int(k[0]) <= end_timestamp
                    ]
        except Exception as fetch_error:
            logger.error(f"Error fetching historical klines: {fetch_error}")
            # Try fallback method
            try:
                limit = min(estimated_candles, 1500)
                logger.info(f"Trying fallback method with limit={limit}")
                klines = rest.futures_klines(symbol=request.symbol, interval=interval, limit=limit)
                all_klines = [
                    k for k in (klines or [])
                    if start_timestamp <= int(k[0]) <= end_timestamp
                ]
                logger.info(f"Fallback fetched {len(all_klines)} klines after filtering")
            except Exception as fallback_error:
                logger.error(f"Fallback method also failed: {fallback_error}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to fetch historical data: {fetch_error}. Fallback also failed: {fallback_error}"
                )
    except Exception as e:
        logger.error(f"Error fetching historical klines: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch historical data: {e}"
        )
    
    logger.info(f"Fetched {len(all_klines)} total klines from Binance")
    
    if len(all_klines) < 50:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient historical data: only {len(all_klines)} candles available. Need at least 50."
        )
    
    # Filter klines to requested time range
    filtered_klines = [
        k for k in all_klines
        if start_timestamp <= int(k[0]) <= end_timestamp
    ]
    
    logger.info(f"Filtered to {len(filtered_klines)} klines in time range {request.start_time} to {request.end_time}")
    
    if not filtered_klines:
        raise HTTPException(
            status_code=400,
            detail="No klines found in the specified time range"
        )
    
    # Create strategy context
    # Calculate interval_seconds from kline_interval (already calculated above)
    context = StrategyContext(
        id="backtest",
        name="Backtest Strategy",
        symbol=request.symbol,
        leverage=request.leverage,
        risk_per_trade=request.risk_per_trade,
        params=request.params,
        interval_seconds=interval_seconds  # Calculated from kline_interval
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
    
    # Process each candle
    slow_period = int(request.params.get("ema_slow", 21))
    fast_period = int(request.params.get("ema_fast", 8))
    min_required_candles = slow_period + 1  # Need slow_period for EMA + 1 forming candle
    logger.info(f"Starting backtest: Processing {len(filtered_klines)} candles for {request.symbol} from {request.start_time} to {request.end_time}")
    logger.info(f"Strategy: {request.strategy_type}, Params: {request.params}")
    logger.info(f"EMA periods: Fast={fast_period}, Slow={slow_period}. Will start evaluating after {min_required_candles} candles for stable EMAs.")
    
    # Track signal statistics
    signal_counts = {"BUY": 0, "SELL": 0, "HOLD": 0, "CLOSE": 0, "ERROR": 0}
    
    for i, kline in enumerate(filtered_klines):
        mock_client.current_index = i
        
        # Get current price (close price of current candle)
        current_price = float(kline[4])
        # Convert kline timestamp to timezone-aware datetime (UTC)
        candle_time = datetime.fromtimestamp(int(kline[0]) / 1000, tz=timezone.utc)
        
        # Update strategy's klines (feed it all klines up to current)
        # Strategy needs enough history for indicators, so provide all klines up to current
        # IMPORTANT: The strategy expects the last kline to be "forming" (not closed)
        # Strategy does: closed_klines = klines[:-1] and last_closed = closed_klines[-1]
        # This requires at least 2 klines: one closed (klines[0]) and one forming (klines[1])
        # Also need enough candles for EMAs to stabilize (slow_period = 21 by default)
        # Skip until we have enough candles for EMA calculation + 1 for forming candle
        slow_period = int(request.params.get("ema_slow", 21))
        min_required_candles = slow_period + 1  # slow_period for EMA + 1 forming candle
        if i < min_required_candles:
            # Not enough klines yet - need at least slow_period + 1 for stable EMAs
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
                trailing_stop_enabled = bool(request.params.get("trailing_stop_enabled", False))
                
                # Only use fixed TP/SL if trailing stop is disabled
                if not trailing_stop_enabled:
                    take_profit_pct = float(request.params.get("take_profit_pct", 0.004))
                    stop_loss_pct = float(request.params.get("stop_loss_pct", 0.002))
                    
                    if position_side == "LONG":
                        tp_price = entry_price * (1 + take_profit_pct)
                        sl_price = entry_price * (1 - stop_loss_pct)
                        # Check if TP/SL was hit during the candle using high/low
                        # TP is hit if high >= tp_price, SL is hit if low <= sl_price
                        # Priority: TP takes precedence if both are hit (more favorable)
                        if candle_high >= tp_price:
                            # TP hit during candle - exit at TP price (not close price)
                            exit_price = tp_price
                            exit_reason = "TP"
                            logger.info(f"TP hit during candle: high={candle_high:.8f} >= tp={tp_price:.8f}, exiting at {exit_price:.8f}")
                        elif candle_low <= sl_price:
                            # SL hit during candle - exit at SL price (not close price)
                            exit_price = sl_price
                            exit_reason = "SL"
                            logger.info(f"SL hit during candle: low={candle_low:.8f} <= sl={sl_price:.8f}, exiting at {exit_price:.8f}")
                    else:  # SHORT
                        tp_price = entry_price * (1 - take_profit_pct)
                        sl_price = entry_price * (1 + stop_loss_pct)
                        # For SHORT: TP is hit if low <= tp_price, SL is hit if high >= sl_price
                        # Priority: TP takes precedence if both are hit (more favorable)
                        if candle_low <= tp_price:
                            # TP hit during candle - exit at TP price
                            exit_price = tp_price
                            exit_reason = "TP"
                            logger.info(f"TP hit during candle: low={candle_low:.8f} <= tp={tp_price:.8f}, exiting at {exit_price:.8f}")
                        elif candle_high >= sl_price:
                            # SL hit during candle - exit at SL price
                            exit_price = sl_price
                            exit_reason = "SL"
                            logger.info(f"SL hit during candle: high={candle_high:.8f} >= sl={sl_price:.8f}, exiting at {exit_price:.8f}")
            else:
                # Range mean reversion - use strategy's internal TP/SL
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
                
                # Calculate exit fee
                exit_fee = current_trade.notional * AVERAGE_FEE_RATE
                
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
                
                # Reset strategy state
                strategy_position = None
                strategy_entry_price = None
                current_trade = None
        
        # Process new signals (only if no open position)
        # CRITICAL: Only process trades within the backtest time range
        if signal.action in ("BUY", "SELL"):
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
                
                # Calculate entry fee
                entry_fee = sizing.notional * AVERAGE_FEE_RATE
                
                # Check if we have enough balance
                if balance < entry_fee:
                    logger.warning(f"Insufficient balance for trade: balance={balance:.2f}, entry_fee={entry_fee:.2f}")
                    continue  # Skip trade if insufficient balance
                
                # Create new trade
                logger.info(f"Creating {position_side} trade: entry={real_entry_price:.8f} (spread-adjusted from {current_price:.8f}), quantity={sizing.quantity:.8f}, notional={sizing.notional:.2f}")
                current_trade = Trade(
                    entry_time=candle_time,
                    exit_time=None,
                    entry_price=real_entry_price,  # Store spread-adjusted entry price
                    exit_price=None,
                    position_side=position_side,
                    quantity=sizing.quantity,
                    notional=sizing.notional,
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
            
            # Calculate exit fee
            exit_fee = current_trade.notional * AVERAGE_FEE_RATE
            
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
        
        # Calculate exit fee
        exit_fee = current_trade.notional * AVERAGE_FEE_RATE
        
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
    
    # Calculate statistics
    completed_trades = [t for t in trades if not t.is_open]
    open_trades = [t for t in trades if t.is_open]
    
    # Log signal statistics
    logger.info(f"Signal statistics: {signal_counts}")
    logger.info(f"Backtest completed: {len(completed_trades)} completed trades, {len(open_trades)} open trades, {len(trades)} total")
    if len(trades) == 0:
        logger.warning("No trades were executed during backtest.")
        logger.warning(f"Signals generated: BUY={signal_counts.get('BUY', 0)}, SELL={signal_counts.get('SELL', 0)}, HOLD={signal_counts.get('HOLD', 0)}")
        if signal_counts.get('BUY', 0) == 0 and signal_counts.get('SELL', 0) == 0:
            logger.warning("Strategy is only generating HOLD signals. This could indicate:")
            logger.warning("  - Market conditions don't match strategy criteria")
            logger.warning("  - EMA periods need more candles to stabilize")
            logger.warning("  - Strategy parameters are too restrictive")
    
    total_pnl = balance - request.initial_balance
    total_return_pct = (total_pnl / request.initial_balance) * 100 if request.initial_balance > 0 else 0
    
    winning_trades = [t for t in completed_trades if t.net_pnl and t.net_pnl > 0]
    losing_trades = [t for t in completed_trades if t.net_pnl and t.net_pnl <= 0]
    
    win_rate = (len(winning_trades) / len(completed_trades) * 100) if completed_trades else 0.0
    
    total_fees = sum((t.entry_fee + (t.exit_fee or 0)) for t in trades)
    
    avg_profit_per_trade = sum((t.net_pnl or 0) for t in completed_trades) / len(completed_trades) if completed_trades else 0.0
    
    largest_win = max((t.net_pnl or 0) for t in completed_trades) if completed_trades else 0.0
    largest_loss = min((t.net_pnl or 0) for t in completed_trades) if completed_trades else 0.0
    
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
        klines=klines_data
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

