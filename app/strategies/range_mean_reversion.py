from __future__ import annotations

from typing import Optional, Literal, Tuple

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.strategies.base import Strategy, StrategyContext, StrategySignal
from app.strategies.indicators import calculate_ema, calculate_rsi, calculate_atr


# Shared functionality reuse:
# - Technical indicators (RSI, EMA, ATR) from app.strategies.indicators
# - Position state synchronization pattern from base Strategy class
# - Live price TP/SL checking pattern (following EmaScalpingStrategy approach)


class RangeMeanReversionStrategy(Strategy):
    """
    Range Mean-Reversion Scalping Strategy.
    
    This strategy trades in sideways/ranging markets by:
    - Buying near support (bottom 20% of range)
    - Selling near resistance (top 20% of range)
    - Taking profit at range midpoint or opposite boundary
    
    Key Features:
    - Range detection using lookback period (100-200 candles)
    - Trend filter (only trades when market is sideways, not trending)
    - RSI confirmation for entries
    - Dynamic TP/SL based on range boundaries
    - Support for both LONG and SHORT positions
    
    Trading Logic:
    - LONG Entry: Price in buy zone (bottom 20%) + RSI < 40
    - LONG Exit: TP at range_mid or range_high - buffer, SL below range_low
    - SHORT Entry: Price in sell zone (top 20%) + RSI > 60
    - SHORT Exit: TP at range_mid or range_low + buffer, SL above range_high
    """
    
    def __init__(self, context: StrategyContext, client: BinanceClient) -> None:
        super().__init__(context, client)
        
        # Range detection parameters
        self.lookback_period = int(context.params.get("lookback_period", 150))
        self.buy_zone_pct = float(context.params.get("buy_zone_pct", 0.2))  # Bottom 20%
        self.sell_zone_pct = float(context.params.get("sell_zone_pct", 0.2))  # Top 20%
        
        # Trend filter parameters
        self.ema_fast_period = int(context.params.get("ema_fast_period", 20))
        self.ema_slow_period = int(context.params.get("ema_slow_period", 50))
        self.max_ema_spread_pct = float(context.params.get("max_ema_spread_pct", 0.005))  # 0.5% max spread for range
        self.max_atr_multiplier = float(context.params.get("max_atr_multiplier", 2.0))  # ATR threshold
        
        # RSI parameters
        self.rsi_period = int(context.params.get("rsi_period", 14))
        self.rsi_oversold = float(context.params.get("rsi_oversold", 40))
        self.rsi_overbought = float(context.params.get("rsi_overbought", 60))
        
        # Exit parameters
        self.tp_buffer_pct = float(context.params.get("tp_buffer_pct", 0.001))  # 0.1% buffer from range boundary
        self.sl_buffer_pct = float(context.params.get("sl_buffer_pct", 0.002))  # 0.2% buffer beyond range
        
        # Kline interval
        self.interval = str(context.params.get("kline_interval", "5m"))
        valid_intervals = ["1s", "3s", "5s", "10s", "30s",  # Second-based intervals for high-frequency trading
                          "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]
        if self.interval not in valid_intervals:
            logger.warning(f"Invalid kline interval {self.interval}, using 5m")
            self.interval = "5m"
        
        # Short trading
        self.enable_short = self.parse_bool_param(context.params.get("enable_short"), default=True)
        
        # Cooldown after exit (prevents flip-flops)
        self.cooldown_candles = int(context.params.get("cooldown_candles", 2))  # Candles to wait after exit
        self.cooldown_left: int = 0  # Candles remaining in cooldown
        
        # Position tracking
        self.position: Optional[Literal["LONG", "SHORT"]] = None
        self.entry_price: Optional[float] = None
        self.entry_candle_time: Optional[int] = None  # Track entry candle to prevent immediate exits
        
        # Track last processed candle to avoid duplicate signals
        self.last_closed_candle_time: Optional[int] = None
        
        # Range state
        self.range_high: Optional[float] = None
        self.range_low: Optional[float] = None
        self.range_mid: Optional[float] = None
        self.range_valid: bool = False
        self.range_invalid_count: int = 0  # Track consecutive invalid range detections
        self.max_range_invalid_candles: int = int(context.params.get("max_range_invalid_candles", 20))  # Reset range after N invalid candles
    
    def _exit_signal(
        self,
        action: Literal["SELL", "BUY"],
        price: float,
        exit_reason: str,
        confidence: float
    ) -> StrategySignal:
        """Helper to create exit signal and reset position state."""
        current_position = self.position
        self.position = None
        self.entry_price = None
        self.entry_candle_time = None
        self.cooldown_left = self.cooldown_candles
        return StrategySignal(
            action=action,
            symbol=self.context.symbol,
            confidence=confidence,
            price=price,
            exit_reason=exit_reason,
            position_side=current_position
        )
    
    def _check_tp_sl(
        self,
        live_price: float,
        *,
        allow_tp: bool = True
    ) -> Optional[StrategySignal]:
        """
        Check TP/SL using last known range.
        
        Args:
            live_price: Current live price
            allow_tp: Whether to allow TP exits (False to block on entry candle)
        
        Returns:
            StrategySignal if TP/SL hit, None otherwise
        """
        # Only check if we have position and valid range
        # Note: entry_price is not used in range-based TP/SL calculations, so we don't check it
        # This prevents skipping exits if entry_price is None/0.0 due to desync
        if not (self.position and self.range_valid and 
                self.range_high is not None and self.range_low is not None and self.range_mid is not None):
            return None
        
        range_size = self.range_high - self.range_low
        
        if self.position == "LONG":
            tp1 = self.range_mid
            tp2 = self.range_high - (range_size * self.tp_buffer_pct)
            sl = self.range_low - (range_size * self.sl_buffer_pct)
            
            # Check SL first (critical exit - always allowed)
            if live_price <= sl:
                logger.info(
                    f"[{self.context.id}] Long SL hit (below range): "
                    f"{live_price:.8f} <= {sl:.8f}"
                )
                return self._exit_signal("SELL", live_price, "SL_RANGE_BREAK", 0.85)
            
            # Check TP (only if allowed - blocked on entry candle)
            if allow_tp:
                if live_price >= tp2:
                    logger.info(
                        f"[{self.context.id}] Long TP2 hit (range high): "
                        f"{live_price:.8f} >= {tp2:.8f}"
                    )
                    return self._exit_signal("SELL", live_price, "TP_RANGE_HIGH", 0.9)
                
                if live_price >= tp1:
                    logger.info(
                        f"[{self.context.id}] Long TP1 hit (range mid): "
                        f"{live_price:.8f} >= {tp1:.8f}"
                    )
                    return self._exit_signal("SELL", live_price, "TP_RANGE_MID", 0.85)
        
        elif self.position == "SHORT":
            tp1 = self.range_mid
            tp2 = self.range_low + (range_size * self.tp_buffer_pct)
            sl = self.range_high + (range_size * self.sl_buffer_pct)
            
            # Check SL first (critical exit - always allowed)
            if live_price >= sl:
                logger.info(
                    f"[{self.context.id}] Short SL hit (above range): "
                    f"{live_price:.8f} >= {sl:.8f}"
                )
                return self._exit_signal("BUY", live_price, "SL_RANGE_BREAK", 0.85)
            
            # Check TP (only if allowed - blocked on entry candle)
            if allow_tp:
                if live_price <= tp2:
                    logger.info(
                        f"[{self.context.id}] Short TP2 hit (range low): "
                        f"{live_price:.8f} <= {tp2:.8f}"
                    )
                    return self._exit_signal("BUY", live_price, "TP_RANGE_LOW", 0.9)
                
                if live_price <= tp1:
                    logger.info(
                        f"[{self.context.id}] Short TP1 hit (range mid): "
                        f"{live_price:.8f} <= {tp1:.8f}"
                    )
                    return self._exit_signal("BUY", live_price, "TP_RANGE_MID", 0.85)
        
        return None
    
    def sync_position_state(
        self,
        *,
        position_side: Optional[Literal["LONG", "SHORT"]],
        entry_price: Optional[float],
    ) -> None:
        """Sync strategy's internal position state with Binance reality."""
        if position_side is None and self.position is not None:
            logger.warning(
                f"[{self.context.id}] Strategy state desync: "
                f"strategy thinks position={self.position} but Binance says flat. "
                f"Syncing strategy to Binance reality."
            )
            self.position = None
            self.entry_price = None
            self.entry_candle_time = None
            # Set cooldown when position is closed externally
            self.cooldown_left = self.cooldown_candles
        elif position_side is not None and self.position is None:
            price_str = f"{entry_price:.8f}" if entry_price is not None else "unknown"
            logger.info(
                f"[{self.context.id}] Syncing strategy to Binance position: "
                f"{position_side} @ {price_str}"
            )
            self.position = position_side
            self.entry_price = entry_price
            # Entry candle time unknown when syncing from Binance
            self.entry_candle_time = None
        elif position_side != self.position:
            logger.warning(
                f"[{self.context.id}] Strategy position ({self.position}) doesn't match "
                f"Binance ({position_side}). Syncing to Binance."
            )
            self.position = position_side
            self.entry_price = entry_price
            self.entry_candle_time = None  # Unknown when syncing from Binance
        elif position_side is None:
            # Position closed - reset entry candle time and set cooldown
            self.position = None
            self.entry_price = None
            self.entry_candle_time = None
            if self.cooldown_left == 0:  # Only set if not already set
                self.cooldown_left = self.cooldown_candles
        else:
            # Position matches - but update entry_price to reflect actual filled price
            # This ensures strategy's entry_price matches Binance reality (handles slippage/spread)
            if entry_price is not None and entry_price != self.entry_price:
                logger.debug(
                    f"[{self.context.id}] Updating entry_price from {self.entry_price:.8f} "
                    f"to {entry_price:.8f} (actual filled price from Binance)"
                )
            self.entry_price = entry_price
    
    def _detect_range(self, klines: list[list]) -> Tuple[Optional[float], Optional[float], Optional[float], bool]:
        """
        Detect price range from klines.
        
        Returns:
            Tuple of (range_high, range_low, range_mid, is_valid_range)
        """
        if len(klines) < self.lookback_period:
            return None, None, None, False
        
        # Get lookback klines (exclude current forming candle)
        lookback_klines = klines[-self.lookback_period - 1:-1] if len(klines) > self.lookback_period else klines[:-1]
        
        if len(lookback_klines) < self.lookback_period:
            return None, None, None, False
        
        # Calculate range boundaries
        highs = [float(k[2]) for k in lookback_klines]
        lows = [float(k[3]) for k in lookback_klines]
        
        range_high = max(highs)
        range_low = min(lows)
        range_mid = (range_high + range_low) / 2
        
        # Check if range is valid (not too narrow, not too wide)
        range_size = range_high - range_low
        if range_size <= 0:
            return None, None, None, False
        
        # Calculate ATR for volatility check
        atr = calculate_atr(lookback_klines, period=14)
        if atr is None:
            return None, None, None, False
        
        # Range should be reasonable compared to ATR (not too volatile)
        if range_size > atr * self.max_atr_multiplier * 5:  # Allow range to be up to 5x ATR
            logger.debug(f"[{self.context.id}] Range too wide relative to ATR: {range_size:.8f} > {atr * self.max_atr_multiplier * 5:.8f}")
            return None, None, None, False
        
        # Check if market is trending (using EMA spread)
        closes = [float(k[4]) for k in lookback_klines]
        fast_ema = calculate_ema(closes, self.ema_fast_period)
        slow_ema = calculate_ema(closes, self.ema_slow_period)
        
        if fast_ema is None or slow_ema is None:
            return None, None, None, False
        
        # Check EMA spread (if too wide, market is trending, not ranging)
        current_price = closes[-1]
        ema_spread_pct = abs(fast_ema - slow_ema) / current_price if current_price > 0 else 0
        
        if ema_spread_pct > self.max_ema_spread_pct:
            logger.debug(
                f"[{self.context.id}] Market is trending (EMA spread {ema_spread_pct:.6f} > {self.max_ema_spread_pct:.6f}). "
                f"Not a valid range."
            )
            return None, None, None, False
        
        logger.debug(
            f"[{self.context.id}] Valid range detected: "
            f"high={range_high:.8f}, low={range_low:.8f}, mid={range_mid:.8f}, "
            f"size={range_size:.8f}, ATR={atr:.8f}, EMA spread={ema_spread_pct:.6f}"
        )
        
        return range_high, range_low, range_mid, True
    
    async def evaluate(self) -> StrategySignal:
        """
        Evaluate market conditions and generate trading signals.
        """
        try:
            # Get enough klines for range detection
            limit = max(self.lookback_period + 50, 200)
            klines = self.client.get_klines(
                symbol=self.context.symbol,
                interval=self.interval,
                limit=limit
            )
            
            if not klines or len(klines) < self.lookback_period + 10:
                current_price = self.client.get_price(self.context.symbol)
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.0,
                    price=current_price
                )
            
            # Get current price (live)
            live_price = self.client.get_price(self.context.symbol)
            
            # BUG FIX: Check for duplicate/older candles BEFORE any processing
            # This prevents processing the same candle multiple times
            closed_klines = klines[:-1]  # Exclude current forming candle
            if not closed_klines:
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.0,
                    price=live_price
                )
            
            last_closed = closed_klines[-1]
            last_closed_time = int(last_closed[6])  # close_time in ms
            
            # Check for strictly older candles (not duplicates)
            # CRITICAL FIX: If older candle received, do TP/SL only and return immediately
            # Do NOT update last_closed_candle_time to prevent corrupting forward-only logic
            if self.last_closed_candle_time is not None and last_closed_time < self.last_closed_candle_time:
                logger.warning(
                    f"[{self.context.id}] Skipping OLDER candle: time={last_closed_time} "
                    f"(last_processed={self.last_closed_candle_time}). "
                    f"Only checking TP/SL if in position, then returning."
                )
                # Only check TP/SL if in position, then return immediately
                # Do NOT update last_closed_candle_time (would corrupt forward-only logic)
                if self.position is not None and self.entry_price is not None:
                    # Check entry candle protection (consistent with duplicate/main paths)
                    on_entry_candle = (self.entry_candle_time is not None and 
                                      self.last_closed_candle_time is not None and 
                                      self.entry_candle_time == self.last_closed_candle_time)
                    
                    # Check TP/SL using unified helper (consistent with other paths)
                    exit_signal = self._check_tp_sl(live_price, allow_tp=not on_entry_candle)
                    if exit_signal:
                        return exit_signal
                # Return HOLD after TP/SL check (or if no position)
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.1,
                    price=live_price
                )
            
            # Check for duplicate candle processing
            # OPTIMIZATION: On duplicate candle, do TP/SL only and return early
            # Don't waste CPU/API on range detection for same candle
            if self.last_closed_candle_time == last_closed_time:
                logger.debug(
                    f"[{self.context.id}] Duplicate candle detected (time={last_closed_time}). "
                    f"Only checking TP/SL if in position, then returning."
                )
                # Only check TP/SL if in position, then return immediately
                # Don't run range detection (wasteful for duplicate candle)
                if self.position is not None and self.entry_price is not None:
                    # Check entry candle protection (consistent with older/main paths)
                    on_entry_candle = (self.entry_candle_time is not None and 
                                      self.last_closed_candle_time is not None and 
                                      self.entry_candle_time == self.last_closed_candle_time)
                    
                    # Check TP/SL using unified helper (consistent with other paths)
                    exit_signal = self._check_tp_sl(live_price, allow_tp=not on_entry_candle)
                    if exit_signal:
                        return exit_signal
                # Return HOLD after TP/SL check (or if no position)
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.1,
                    price=live_price
                )
            
            # Mark candle as processed (only if not older/duplicate)
            self.last_closed_candle_time = last_closed_time
            
            # Detect range
            range_high, range_low, range_mid, range_valid = self._detect_range(klines)
            
            # CRITICAL: If in position, check TP/SL FIRST using last known range
            # This ensures we can exit even if current range detection fails (e.g., breakout)
            # Following the same pattern as EmaScalpingStrategy for consistency
            if self.position is not None and self.entry_price is not None:
                # Check entry candle protection (consistent with older/duplicate paths)
                on_entry_candle = (self.entry_candle_time is not None and 
                                  self.last_closed_candle_time is not None and 
                                  self.entry_candle_time == self.last_closed_candle_time)
                
                # Check TP/SL using unified helper (consistent with other paths)
                exit_signal = self._check_tp_sl(live_price, allow_tp=not on_entry_candle)
                if exit_signal:
                    return exit_signal
            
            # Only block new entries when no valid range is detected
            if not range_valid or range_high is None or range_low is None or range_mid is None:
                # No valid range detected - update state but allow TP/SL checks above
                if self.position is None:
                    # Only return HOLD if we have no position (no entry possible)
                    logger.debug(f"[{self.context.id}] No valid range detected. Holding.")
                    return StrategySignal(
                        action="HOLD",
                        symbol=self.context.symbol,
                        confidence=0.0,
                        price=live_price
                    )
                # If we have a position, TP/SL was checked above using last known range
                # Continue to update range state if we got partial values
            
            # Update range state if valid range detected
            if range_valid and range_high is not None and range_low is not None and range_mid is not None:
                self.range_high = range_high
                self.range_low = range_low
                self.range_mid = range_mid
                self.range_valid = True
                self.range_invalid_count = 0  # Reset invalid count when range becomes valid
            else:
                # Range is invalid - increment invalid count
                self.range_invalid_count += 1
                # If range has been invalid for too long, reset range_valid to False
                # This prevents using stale range data after market stops ranging
                # CRITICAL: Only clear range when position is None (flat)
                # If position is open, keep last-known range for exit management
                if self.range_invalid_count >= self.max_range_invalid_candles:
                    if self.position is None:
                        # Safe to clear: no open position
                        if self.range_valid:
                            logger.warning(
                                f"[{self.context.id}] Range has been invalid for {self.range_invalid_count} candles. "
                                f"Resetting range_valid to False (no open position)."
                            )
                        self.range_valid = False
                        self.range_high = None
                        self.range_low = None
                        self.range_mid = None
                        self.range_invalid_count = 0  # Reset counter after clearing range
                    else:
                        # Keep last-known range for exit management (position is open)
                        logger.warning(
                            f"[{self.context.id}] Range has been invalid for {self.range_invalid_count} candles, "
                            f"but keeping last-known range because position is open "
                            f"(position={self.position}, entry_price={self.entry_price}). "
                            f"This ensures TP/SL can still exit the position."
                        )
                        self.range_invalid_count = 0  # Stop counter from growing forever
            
            # Calculate range zones for entry signals (only if valid range)
            if range_valid and range_high is not None and range_low is not None and range_mid is not None:
                range_size = range_high - range_low
                buy_zone_upper = range_low + (range_size * self.buy_zone_pct)  # Bottom 20%
                sell_zone_lower = range_high - (range_size * self.sell_zone_pct)  # Top 20%
            else:
                buy_zone_upper = None
                sell_zone_lower = None
            
            # No position - check for entry signals (only if valid range)
            if self.position is None:
                # BUG FIX: Check cooldown before generating entry signals
                if self.cooldown_left > 0:
                    self.cooldown_left -= 1
                    logger.debug(
                        f"[{self.context.id}] HOLD: Cooldown active ({self.cooldown_left} candles remaining) | "
                        f"Price: {live_price:.8f}"
                    )
                    return StrategySignal(
                        action="HOLD",
                        symbol=self.context.symbol,
                        confidence=0.1,
                        price=live_price
                    )
                
                # OPTIMIZATION: Early return if no valid range (saves RSI calculation)
                if not range_valid or range_high is None or range_low is None or range_mid is None:
                    logger.debug(f"[{self.context.id}] HOLD: No valid range detected for entry signals")
                    return StrategySignal(
                        action="HOLD",
                        symbol=self.context.symbol,
                        confidence=0.0,
                        price=live_price
                    )
                
                # Calculate RSI (only if valid range exists)
                closed_klines = klines[:-1]  # Exclude current forming candle
                closes = [float(k[4]) for k in closed_klines]
                rsi = calculate_rsi(closes, self.rsi_period)
                
                if rsi is None:
                    return StrategySignal(
                        action="HOLD",
                        symbol=self.context.symbol,
                        confidence=0.0,
                        price=live_price
                    )
                
                # LONG Entry: Price in buy zone + RSI oversold (only if valid range)
                if buy_zone_upper is not None and live_price <= buy_zone_upper and rsi < self.rsi_oversold:
                    logger.info(
                        f"[{self.context.id}] LONG entry signal: "
                        f"price={live_price:.8f} <= buy_zone={buy_zone_upper:.8f}, "
                        f"RSI={rsi:.2f} < {self.rsi_oversold}"
                    )
                    self.position = "LONG"
                    self.entry_price = live_price
                    self.entry_candle_time = last_closed_time  # Track entry candle
                    return StrategySignal(
                        action="BUY",
                        symbol=self.context.symbol,
                        confidence=0.75,
                        price=live_price
                    )
                
                # SHORT Entry: Price in sell zone + RSI overbought (only if valid range)
                if self.enable_short and sell_zone_lower is not None and live_price >= sell_zone_lower and rsi > self.rsi_overbought:
                    logger.info(
                        f"[{self.context.id}] SHORT entry signal: "
                        f"price={live_price:.8f} >= sell_zone={sell_zone_lower:.8f}, "
                        f"RSI={rsi:.2f} > {self.rsi_overbought}"
                    )
                    self.position = "SHORT"
                    self.entry_price = live_price
                    self.entry_candle_time = last_closed_time  # Track entry candle
                    return StrategySignal(
                        action="SELL",
                        symbol=self.context.symbol,
                        confidence=0.75,
                        price=live_price
                    )
            
            # Hold - no entry signals
            return StrategySignal(
                action="HOLD",
                symbol=self.context.symbol,
                confidence=0.0,
                price=live_price
            )
            
        except Exception as e:
            logger.exception(f"[{self.context.id}] Error in range mean-reversion evaluation: {e}")
            current_price = self.client.get_price(self.context.symbol)
            return StrategySignal(
                action="HOLD",
                symbol=self.context.symbol,
                confidence=0.0,
                price=current_price
            )

