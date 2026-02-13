from __future__ import annotations

import asyncio
from statistics import fmean
from typing import Deque, Optional, Literal
from collections import deque

from loguru import logger

from typing import TYPE_CHECKING
from app.core.my_binance_client import BinanceClient
from app.strategies.base import Strategy, StrategyContext, StrategySignal
from app.strategies.trailing_stop import TrailingStopManager
from app.strategies.indicators import calculate_ema as _calculate_ema_from_prices_shared

if TYPE_CHECKING:
    from app.core.websocket_kline_manager import WebSocketKlineManager


# Shared functionality:
# - Technical indicators (EMA) from app.strategies.indicators
# - Position state synchronization with Binance reality
# - Live price TP/SL checking on every evaluation (even without new candle)


class EmaScalpingStrategy(Strategy):
    """
    Configurable EMA Crossover Scalping Strategy with Long and Short support.
    
    - Configurable EMA periods (default: 8 fast / 21 slow)
    - Uses closed candlestick data (klines) for accurate signals
    - Only processes new closed candles to avoid duplicate signals
    - Supports both LONG and SHORT positions with take profit and stop loss
    
    Trading Logic (Long):
    - BUY when fast EMA crosses above slow EMA (golden cross)
    - SELL when fast EMA crosses below slow EMA (death cross) or TP/SL hit
    - Take profit at entry * (1 + take_profit_pct)
    - Stop loss at entry * (1 - stop_loss_pct)
    
    Trading Logic (Short):
    - SELL (short) when fast EMA crosses below slow EMA (death cross)
    - BUY (cover) when fast EMA crosses above slow EMA (golden cross) or TP/SL hit
    - Take profit at entry * (1 - take_profit_pct) [inverted]
    - Stop loss at entry * (1 + stop_loss_pct) [inverted]
    
    Advanced Features:
    - Minimum EMA separation filter (avoids noise)
    - Higher-timeframe bias (5m trend check for shorts)
    - Cooldown after exit (prevents flip-flops)
    """
    
    def __init__(
        self, 
        context: StrategyContext, 
        client: BinanceClient,
        kline_manager: Optional['WebSocketKlineManager'] = None
    ) -> None:
        super().__init__(context, client, kline_manager=kline_manager)
        self.fast_period = int(context.params.get("ema_fast", 8))
        self.slow_period = int(context.params.get("ema_slow", 21))
        self.take_profit_pct = float(context.params.get("take_profit_pct", 0.004))
        self.stop_loss_pct = float(context.params.get("stop_loss_pct", 0.002))
        
        # Short trading enabled (default: True)
        self.enable_short = self.parse_bool_param(context.params.get("enable_short"), default=True)
        
        # Advanced filters
        self.min_ema_separation = float(context.params.get("min_ema_separation", 0.0002))  # 0.02% of price
        self.enable_htf_bias = self.parse_bool_param(context.params.get("enable_htf_bias"), default=True)  # Higher timeframe bias
        self.cooldown_candles = int(context.params.get("cooldown_candles", 2))  # Candles to wait after exit
        self.enable_ema_cross_exit = self.parse_bool_param(context.params.get("enable_ema_cross_exit"), default=True)  # Enable EMA cross exits
        
        # Kline interval (default 1 minute for scalping)
        self.interval = str(context.params.get("kline_interval", "1m"))
        # Validate interval format (includes second-based intervals for high-frequency trading)
        valid_intervals = ["1s", "3s", "5s", "10s", "30s",  # Second-based intervals
                          "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]
        if self.interval not in valid_intervals:
            logger.warning(f"Invalid kline interval {self.interval}, using 1m")
            self.interval = "1m"
        
        # Store closing prices from klines (enough for stable EMA)
        self.closes: Deque[float] = deque(maxlen=self.slow_period * 5)
        
        # Track previous EMA values for crossover detection
        self.prev_fast: Optional[float] = None
        self.prev_slow: Optional[float] = None
        
        # Track position state (LONG, SHORT, or None)
        self.position: Optional[str] = None  # "LONG", "SHORT", or None
        self.entry_price: Optional[float] = None
        self.entry_candle_time: Optional[int] = None  # Track entry candle to prevent EMA exits on entry candle
        
        # Track last processed candle to avoid duplicate signals
        self.last_closed_candle_time: Optional[int] = None
        
        # Cooldown tracking (simplified counter approach)
        self.cooldown_left: int = 0  # Candles remaining in cooldown
        
        # Dynamic trailing stop (optional)
        self.trailing_stop_enabled = self.parse_bool_param(context.params.get("trailing_stop_enabled"), default=False)
        self.trailing_stop: Optional[TrailingStopManager] = None
    
    def _check_tp_sl(self, live_price: float, context: str = "") -> Optional[StrategySignal]:
        """
        Check take profit and stop loss conditions using live price.
        
        This method centralizes TP/SL logic to avoid duplication and ensure consistency.
        
        Args:
            live_price: Current market price
            context: Context string for logging (e.g., "older candle", "no new candle", "")
        
        Returns:
            StrategySignal if TP/SL is hit, None otherwise
        """
        if self.position is None or self.entry_price is None:
            return None
        
        # Optional: Block FIXED TP/SL on the entry candle to prevent immediate exits
        # This prevents tight SL from triggering right after entry on the same candle
        # Note: Trailing stop should be allowed even on entry candle (it's dynamic protection)
        # Note: Many scalpers do allow SL right away, so this is a conservative approach
        on_entry_candle = (self.entry_candle_time is not None and 
                          self.last_closed_candle_time is not None and 
                          self.entry_candle_time == self.last_closed_candle_time)
        
        if on_entry_candle:
            # We're still on the entry candle
            # Allow trailing stop to trigger (it's dynamic and protects against adverse moves)
            # But block fixed TP/SL (they're static and might be too tight)
            if not (self.trailing_stop_enabled and self.trailing_stop is not None):
                # Block fixed TP/SL on entry candle, but allow trailing stop
                return None
        
        context_suffix = f" ({context})" if context else ""
        
        if self.position == "LONG":
            if self.trailing_stop_enabled and self.trailing_stop is not None:
                tp_price, sl_price, trail_event = self.trailing_stop.update(live_price)
                if trail_event and getattr(self, "trail_recorder", None):
                    self.trail_recorder.record_trail_update(
                        self.context.id,
                        self.context.symbol,
                        "LONG",
                        trail_event.best_price,
                        trail_event.tp_price,
                        trail_event.sl_price,
                    )
                exit_reason = self.trailing_stop.check_exit(live_price)
                if exit_reason == "TP":
                    logger.info(
                        f"[{self.context.id}] Long Take profit hit (trailing{context_suffix}): "
                        f"{live_price:.8f} >= {tp_price:.8f}"
                    )
                    current_position = self.position
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.trailing_stop = None
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="SELL",
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="TP_TRAILING",
                        position_side=current_position
                    )
                elif exit_reason == "SL":
                    logger.info(
                        f"[{self.context.id}] Long Stop loss hit (trailing{context_suffix}): "
                        f"{live_price:.8f} <= {sl_price:.8f}"
                    )
                    current_position = self.position
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.trailing_stop = None
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="SELL",
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="SL_TRAILING",
                        position_side=current_position
                    )
            else:
                # Fixed TP/SL
                tp_price = self.entry_price * (1 + self.take_profit_pct)
                sl_price = self.entry_price * (1 - self.stop_loss_pct)
                if live_price >= tp_price:
                    logger.info(
                        f"[{self.context.id}] Long Take profit hit{context_suffix}: "
                        f"{live_price:.8f} >= {tp_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => SELL at {live_price:.8f} pos={self.position}")
                    current_position = self.position
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="SELL",
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="TP",
                        position_side=current_position
                    )
                if live_price <= sl_price:
                    logger.info(
                        f"[{self.context.id}] Long Stop loss hit{context_suffix}: "
                        f"{live_price:.8f} <= {sl_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => SELL at {live_price:.8f} pos={self.position}")
                    current_position = self.position
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="SELL",
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="SL",
                        position_side=current_position
                    )
        elif self.position == "SHORT":
            if self.trailing_stop_enabled and self.trailing_stop is not None:
                tp_price, sl_price, trail_event = self.trailing_stop.update(live_price)
                if trail_event and getattr(self, "trail_recorder", None):
                    self.trail_recorder.record_trail_update(
                        self.context.id,
                        self.context.symbol,
                        "SHORT",
                        trail_event.best_price,
                        trail_event.tp_price,
                        trail_event.sl_price,
                    )
                exit_reason = self.trailing_stop.check_exit(live_price)
                if exit_reason == "TP":
                    logger.info(
                        f"[{self.context.id}] Short Take profit hit (trailing{context_suffix}): "
                        f"{live_price:.8f} <= {tp_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => BUY at {live_price:.8f} pos={self.position}")
                    current_position = self.position
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.trailing_stop = None
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="BUY",  # Cover short
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="TP_TRAILING",
                        position_side=current_position
                    )
                elif exit_reason == "SL":
                    logger.info(
                        f"[{self.context.id}] Short Stop loss hit (trailing{context_suffix}): "
                        f"{live_price:.8f} >= {sl_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => BUY at {live_price:.8f} pos={self.position}")
                    current_position = self.position
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.trailing_stop = None
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="BUY",  # Cover short
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="SL_TRAILING",
                        position_side=current_position
                    )
            else:
                # Fixed TP/SL (inverted)
                tp_price = self.entry_price * (1 - self.take_profit_pct)
                sl_price = self.entry_price * (1 + self.stop_loss_pct)
                if live_price <= tp_price:
                    logger.info(
                        f"[{self.context.id}] Short Take profit hit{context_suffix}: "
                        f"{live_price:.8f} <= {tp_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => BUY at {live_price:.8f} pos={self.position}")
                    current_position = self.position
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="BUY",  # Cover short
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="TP",
                        position_side=current_position
                    )
                if live_price >= sl_price:
                    logger.info(
                        f"[{self.context.id}] Short Stop loss hit{context_suffix}: "
                        f"{live_price:.8f} >= {sl_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => BUY at {live_price:.8f} pos={self.position}")
                    current_position = self.position
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="BUY",  # Cover short
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="SL",
                        position_side=current_position
                    )
        
        return None
    
    def sync_position_state(
        self,
        *,
        position_side: Optional[Literal["LONG", "SHORT"]],
        entry_price: Optional[float],
    ) -> None:
        """Sync strategy's internal position state with Binance reality.
        
        BUG FIX 1: This prevents strategy state desync when Binance native TP/SL
        orders close positions without the strategy knowing.
        
        Args:
            position_side: Current position side from Binance (None if flat)
            entry_price: Current entry price from Binance (None if flat)
        """
        # If Binance says we're flat but strategy thinks we have a position,
        # Binance must have closed it (e.g., via native TP/SL order)
        if position_side is None and self.position is not None:
            logger.warning(
                f"[{self.context.id}] Strategy state desync detected: "
                f"strategy thinks position={self.position} but Binance says flat. "
                f"Syncing strategy to Binance reality (position closed)."
            )
            self.position = None
            self.entry_price = None
            self.entry_candle_time = None
            self.trailing_stop = None
            # Reset cooldown since position was closed externally
            self.cooldown_left = self.cooldown_candles
        
        # If Binance has a position but strategy thinks it's flat,
        # sync strategy to Binance state (may happen on restart/recovery)
        elif position_side is not None and self.position is None:
            price_str = f"{entry_price:.8f}" if entry_price is not None else "unknown"
            logger.info(
                f"[{self.context.id}] Syncing strategy to Binance position: "
                f"{position_side} @ {price_str}"
            )
            self.position = position_side
            self.entry_price = entry_price
            
            # Reinitialize trailing stop if enabled and we have entry price
            if self.trailing_stop_enabled and entry_price is not None:
                activation_pct = float(self.context.params.get("trailing_stop_activation_pct", 0.0))
                self.trailing_stop = TrailingStopManager(
                    entry_price=entry_price,
                    take_profit_pct=self.take_profit_pct,
                    stop_loss_pct=self.stop_loss_pct,
                    position_type=position_side,
                    enabled=True,
                    activation_pct=activation_pct
                )
                logger.debug(
                    f"[{self.context.id}] Trailing stop reinitialized for {position_side} "
                    f"@ {entry_price:.8f}"
                )
        
        # If both have positions but they don't match, sync to Binance
        elif position_side != self.position:
            logger.warning(
                f"[{self.context.id}] Strategy position ({self.position}) doesn't match "
                f"Binance ({position_side}). Syncing to Binance."
            )
            self.position = position_side
            self.entry_price = entry_price
            self.entry_candle_time = None  # Unknown when syncing from Binance
            # Reset trailing stop - will be reinitialized if needed
            self.trailing_stop = None
        
        # If entry price changed (position size changed), update it
        elif position_side is not None and entry_price is not None and self.entry_price != entry_price:
            logger.debug(
                f"[{self.context.id}] Entry price changed: {self.entry_price:.8f} -> {entry_price:.8f}. "
                f"Updating strategy state."
            )
            self.entry_price = entry_price
            # Reset trailing stop with new entry price if enabled
            if self.trailing_stop_enabled:
                activation_pct = float(self.context.params.get("trailing_stop_activation_pct", 0.0))
                self.trailing_stop = TrailingStopManager(
                    entry_price=entry_price,
                    take_profit_pct=self.take_profit_pct,
                    stop_loss_pct=self.stop_loss_pct,
                    position_type=position_side,
                    enabled=True,
                    activation_pct=activation_pct
                )
        
    async def evaluate(self) -> StrategySignal:
        """
        Evaluate market conditions using closed candlestick data.
        Only processes new closed candles to avoid duplicate signals.
        """
        try:
            # Get enough klines to compute EMAs
            limit = max(self.slow_period + 10, 50)
            
            # Try WebSocket first, fallback to REST API
            if self.kline_manager:
                try:
                    klines = await self.kline_manager.get_klines(
                        symbol=self.context.symbol,
                        interval=self.interval,
                        limit=limit
                    )
                except Exception as e:
                    logger.warning(f"WebSocket klines failed, falling back to REST API: {e}")
                    klines = await asyncio.to_thread(
                        self.client.get_klines,
                        symbol=self.context.symbol,
                        interval=self.interval,
                        limit=limit
                    )
            else:
                # Fallback to REST API
                klines = await asyncio.to_thread(
                    self.client.get_klines,
                    symbol=self.context.symbol,
                    interval=self.interval,
                    limit=limit
                )
            
            if not klines or len(klines) < self.slow_period + 2:
                # CRITICAL FIX: Wrap synchronous get_price() in to_thread to prevent blocking event loop
                current_price = await asyncio.to_thread(
                    self.client.get_price,
                    self.context.symbol
                )
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.0,
                    price=current_price
                )
            
            # Binance klines: last kline is usually still forming -> ignore it
            closed_klines = klines[:-1]
            last_closed = closed_klines[-1]
            
            # Kline structure: [open_time, open, high, low, close, volume, close_time, ...]
            last_closed_time = int(last_closed[6])  # close_time in ms
            last_close_price = float(last_closed[4])
            
            # CRITICAL: If in position, check TP/SL using live price even if no new candle
            # This allows TP/SL to be evaluated on every call, not just when candles close
            # CRITICAL FIX: Wrap synchronous get_price() in to_thread to prevent blocking event loop
            live_price = await asyncio.to_thread(
                self.client.get_price,
                self.context.symbol
            )
            
            # BUG FIX 1: Enforce monotonic candle time - prevent processing older candles
            # This prevents time from going backwards and causing contradictory signals
            # Initialize flag to track if a new candle was actually processed
            processed_new_candle = False
            
            # BUG FIX: Check for strictly older candles (not duplicates)
            # Duplicates are handled separately below to maintain clear logic separation
            if self.last_closed_candle_time is not None and last_closed_time < self.last_closed_candle_time:
                # Strictly older candle - skip EMA processing but allow TP/SL checks
                logger.debug(
                    f"[{self.context.id}] Skipping OLDER candle: time={last_closed_time} "
                    f"(last_processed={self.last_closed_candle_time}). "
                    f"Only checking TP/SL if in position."
                )
                # CRITICAL: When processing an older candle, we're NOT on the entry candle
                # (entry was at a later time), so temporarily clear entry_candle_time to allow TP/SL
                saved_entry_candle_time = self.entry_candle_time
                self.entry_candle_time = None  # Allow TP/SL on older candles
                try:
                    # Use centralized TP/SL check method
                    tp_sl_signal = self._check_tp_sl(live_price, context="older candle")
                    if tp_sl_signal:
                        return tp_sl_signal
                finally:
                    # Restore entry_candle_time (in case TP/SL didn't trigger)
                    self.entry_candle_time = saved_entry_candle_time
                
                # No position or TP/SL didn't trigger
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.1,
                    price=live_price
                )
            
            # BUG FIX 2: Check for duplicate candle processing BEFORE any state changes
            # This prevents processing the same candle multiple times when interval_seconds is very short
            if self.last_closed_candle_time == last_closed_time:
                # No new candle, but check TP/SL if in position
                logger.debug(
                    f"[{self.context.id}] Duplicate candle detected (time={last_closed_time}, "
                    f"last_processed={self.last_closed_candle_time}). Skipping EMA processing, "
                    f"only checking TP/SL if in position."
                )
                # Use centralized TP/SL check method
                tp_sl_signal = self._check_tp_sl(live_price, context="no new candle")
                if tp_sl_signal:
                    return tp_sl_signal
                
                # No position or TP/SL didn't trigger
                logger.debug(
                    f"[{self.context.id}] HOLD: Duplicate candle (already processed) | "
                    f"Price: {live_price:.8f} | Candle time: {last_closed_time} | Position: {self.position}"
                )
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.1,
                    price=live_price
                )
            
            # BUG FIX: Mark candle as processed IMMEDIATELY after duplicate check
            # This prevents race conditions when interval_seconds is very short
            # Set this BEFORE processing to prevent duplicate processing
            self.last_closed_candle_time = last_closed_time
            processed_new_candle = True  # Mark that we're processing a new candle
            
            # Per-candle logging removed for performance (progress tracked via SSE)
            # Only log occasionally: first 10 candles or every 100th candle
            if not hasattr(self, '_candle_count'):
                self._candle_count = 0
            self._candle_count += 1
            should_log = self._candle_count <= 10 or self._candle_count % 100 == 0
            # Keep INFO for live trading where SSE is not available
            if should_log:
                logger.debug(
                f"[{self.context.id}] Processing candle {self._candle_count}: time={last_closed_time} "
                f"(close_time={last_closed_time}), close_price={last_close_price:.8f}, "
                f"live_price={live_price:.8f}, position={self.position}"
            )
            
            # Rebuild closes from recent closed candles
            closing_prices = [float(k[4]) for k in closed_klines]
            self.closes.clear()
            self.closes.extend(closing_prices)
            
            if len(self.closes) < self.slow_period:
                logger.warning(
                    f"[{self.context.id}] HOLD: Insufficient data ({len(self.closes)} < {self.slow_period} required) | "
                    f"Price: {last_close_price:.8f}"
                )
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.0,
                    price=last_close_price
                )
            
            # CRITICAL: Save previous EMA values FIRST before computing new ones
            # This is needed for crossover detection to work correctly
            prev_fast = self.prev_fast
            prev_slow = self.prev_slow
            
            fast_ema = self._ema(self.fast_period)
            slow_ema = self._ema(self.slow_period)
            
            # Live price already fetched above (for TP/SL checks when no new candle)
            # For new candles, use live price for TP/SL, closed candle price for EMA logic
            candle_price = last_close_price  # Keep for EMA cross logic
            
            # EMA values logging removed for performance (too verbose per candle)
            # Only log on trade signals or errors
            
            # Use try/finally to ensure state is always updated at the end
            # This eliminates redundant updates while maintaining safety
            try:
                # --- Cooldown check (D) - simplified counter approach ---
                # BUG FIX: Only decrement cooldown when processing a new candle
                # This prevents cooldown from being decremented multiple times on the same candle
                if self.cooldown_left > 0:
                    if processed_new_candle:
                        self.cooldown_left -= 1
                    # Cooldown is normal behavior - use DEBUG for backtests, INFO for live
                    log_level = logger.debug if self.context.id == "backtest" else logger.info
                    log_level(
                        f"[{self.context.id}] HOLD: Cooldown active ({self.cooldown_left} candles remaining) | "
                        f"Price: {live_price:.8f} | Position: {self.position}"
                    )
                    # Early return: state will be updated in finally block
                    return StrategySignal(
                        action="HOLD",
                        symbol=self.context.symbol,
                        confidence=0.1,
                        price=live_price
                    )
                
                # --- TP / SL for LONG positions ---
                # ALWAYS check TP/SL using LIVE PRICE when in position
                if self.position == "LONG" and self.entry_price is not None:
                    # Use centralized TP/SL check method
                    tp_sl_signal = self._check_tp_sl(live_price, context="")
                    if tp_sl_signal:
                        return tp_sl_signal
                
                # --- TP / SL for SHORT positions (3) - INVERTED ---
                # ALWAYS check TP/SL using LIVE PRICE when in position
                if self.position == "SHORT" and self.entry_price is not None:
                    # Use centralized TP/SL check method
                    tp_sl_signal = self._check_tp_sl(live_price, context="")
                    if tp_sl_signal:
                        return tp_sl_signal
                
                # --- Minimum EMA separation filter (B) ---
                # Note: Apply separation filter only for entries, not exits (safety consideration)
                # For exits, we want to allow closing even if EMAs are close
                # Use candle_price for EMA calculations (stable reference)
                ema_separation_pct = abs(fast_ema - slow_ema) / candle_price if candle_price > 0 else 0
                should_check_separation = self.position is None  # Only check for new entries
                
                if should_check_separation and ema_separation_pct < self.min_ema_separation:
                    # EMA separation filter is normal behavior - use DEBUG for backtests, INFO for live
                    log_level = logger.debug if self.context.id == "backtest" else logger.info
                    log_level(
                        f"[{self.context.id}] HOLD: EMA separation too small ({ema_separation_pct:.6f} < {self.min_ema_separation}) | "
                        f"Price: {live_price:.8f} | Fast EMA: {fast_ema:.8f} | Slow EMA: {slow_ema:.8f} | Position: {self.position}"
                    )
                    # Early return: state will be updated in finally block
                    return StrategySignal(
                        action="HOLD",
                        symbol=self.context.symbol,
                        confidence=0.1,
                        price=live_price
                    )
                
                # --- Crossover detection on closed candles ---
                # CRITICAL: Use local prev_fast/prev_slow (from previous candle), not self.prev_*
                # This allows proper crossover detection between candles
                # Use candle_price for entry signals (consistent with EMA calculation)
                if prev_fast is not None and prev_slow is not None:
                    golden_cross = (prev_fast <= prev_slow) and (fast_ema > slow_ema)
                    death_cross = (prev_fast >= prev_slow) and (fast_ema < slow_ema)
                    
                    # BUG FIX: Log crossover detection for debugging
                    if golden_cross or death_cross:
                        # Crossover detection - use DEBUG for backtests, INFO for live
                        log_level = logger.debug if self.context.id == "backtest" else logger.info
                        log_level(
                            f"[{self.context.id}] Crossover detected on candle {last_closed_time}: "
                            f"golden_cross={golden_cross}, death_cross={death_cross}, "
                            f"prev_fast={prev_fast:.8f}, prev_slow={prev_slow:.8f}, "
                            f"fast_ema={fast_ema:.8f}, slow_ema={slow_ema:.8f}, "
                            f"position={self.position}"
                        )
                    
                    # --- LONG Entry: Golden Cross (when flat) ---
                    if golden_cross and self.position is None:
                        # Crossover detection - use DEBUG for backtests, INFO for live
                        log_level = logger.debug if self.context.id == "backtest" else logger.info
                        log_level(
                            f"[{self.context.id}] Golden Cross: fast {fast_ema:.8f} > slow {slow_ema:.8f} "
                            f"(prev: {prev_fast:.8f} <= {prev_slow:.8f})"
                        )
                        # CRITICAL: Use candle close price (where EMA cross was detected) for entry signal
                        # The actual fill price from Binance will update entry_price after order execution
                        # This prevents entry price mismatch when live_price is far from candle close
                        logger.warning(
                            f"[{self.context.id}] SIGNAL => BUY (LONG entry) at {candle_price:.8f} "
                            f"(candle close, live={live_price:.8f}) pos={self.position} "
                            f"candle_time={last_closed_time}"
                        )
                        self.position = "LONG"
                        self.entry_price = candle_price  # Use candle close price (will be updated with actual fill price)
                        self.entry_candle_time = last_closed_time  # Track entry candle to prevent EMA exits on same candle
                        
                        # Initialize trailing stop if enabled (will be updated with actual entry after fill)
                        if self.trailing_stop_enabled:
                            activation_pct = float(self.context.params.get("trailing_stop_activation_pct", 0.0))
                            self.trailing_stop = TrailingStopManager(
                                entry_price=candle_price,  # Initial estimate, will sync with real entry after fill
                                take_profit_pct=self.take_profit_pct,
                                stop_loss_pct=self.stop_loss_pct,
                                position_type="LONG",
                                enabled=True,
                                activation_pct=activation_pct
                            )
                            # Trailing stop initialization - use DEBUG for backtests, INFO for live
                            log_level = logger.debug if self.context.id == "backtest" else logger.info
                            log_level(
                                f"[{self.context.id}] Trailing stop enabled for LONG (initial): "
                                f"TP={self.trailing_stop.current_tp:.8f}, SL={self.trailing_stop.current_sl:.8f}, "
                                f"Activation={activation_pct*100:.2f}% (will sync with actual entry after fill)"
                            )
                        
                        # State will be updated in finally block
                        return StrategySignal(
                            action="BUY",
                            symbol=self.context.symbol,
                            confidence=0.75,
                            price=candle_price,  # Use candle close price for signal
                            exit_reason=None,  # Entry signal, no exit reason
                            position_side="LONG"  # Opening LONG position
                        )
                    
                    # --- LONG Exit: Death Cross (when long) ---
                    # BUG FIX: Forbid EMA exits on the entry candle (standard in professional EMA systems)
                    if (
                        death_cross
                        and self.position == "LONG"
                        and self.enable_ema_cross_exit
                        and self.entry_candle_time != last_closed_time  # Prevent exit on entry candle
                    ):
                        # Crossover detection - use DEBUG for backtests, INFO for live
                        log_level = logger.debug if self.context.id == "backtest" else logger.info
                        log_level(
                            f"[{self.context.id}] Death Cross (exit long): fast {fast_ema:.8f} < slow {slow_ema:.8f} "
                            f"(prev: {prev_fast:.8f} >= {prev_slow:.8f})"
                        )
                        logger.warning(
                            f"[{self.context.id}] SIGNAL => SELL at {live_price:.8f} "
                            f"pos={self.position} candle_time={last_closed_time}"
                        )
                        current_position = self.position
                        self.position, self.entry_price, self.entry_candle_time = None, None, None
                        self.trailing_stop = None  # Reset trailing stop
                        self.cooldown_left = self.cooldown_candles
                        # State will be updated in finally block
                        return StrategySignal(
                            action="SELL",
                            symbol=self.context.symbol,
                            confidence=0.75,
                            price=live_price,
                            exit_reason="EMA_DEATH_CROSS",
                            position_side=current_position
                        )
                    
                    # BUG FIX: Prevent contradictory signals - if death cross just exited LONG,
                    # don't enter SHORT in the same candle (cooldown prevents this, but add explicit check)
                    # --- SHORT Entry: Death Cross (1) - when flat and short enabled ---
                    if death_cross and self.position is None and self.enable_short:
                        # Higher-timeframe bias check (C)
                        if self.enable_htf_bias and self.interval == "1m":
                            # Check 5m trend - use WebSocket if available
                            if self.kline_manager:
                                try:
                                    htf_klines = await self.kline_manager.get_klines(
                                        symbol=self.context.symbol,
                                        interval="5m",  # HTF interval
                                        limit=self.slow_period + 5
                                    )
                                except Exception as e:
                                    logger.warning(f"WebSocket HTF klines failed, falling back to REST API: {e}")
                                    htf_klines = await asyncio.to_thread(
                                        self.client.get_klines,
                                        symbol=self.context.symbol,
                                        interval="5m",
                                        limit=self.slow_period + 5
                                    )
                            else:
                                # Fallback to REST API
                                htf_klines = await asyncio.to_thread(
                                    self.client.get_klines,
                                    symbol=self.context.symbol,
                                    interval="5m",
                                    limit=self.slow_period + 5
                                )
                            # BUG FIX: Fail-closed behavior - block short if HTF data unavailable when bias is enabled
                            # This prevents unwanted shorts when HTF trend check cannot be performed
                            if not htf_klines or len(htf_klines) < self.slow_period + 1:
                                logger.warning(
                                    f"[{self.context.id}] Short blocked: HTF bias enabled but insufficient 5m data "
                                    f"(got {len(htf_klines) if htf_klines else 0} klines, need {self.slow_period + 1})"
                                )
                                # Early return: state will be updated in finally block
                                return StrategySignal(
                                    action="HOLD",
                                    symbol=self.context.symbol,
                                    confidence=0.1,
                                    price=live_price
                                )
                            
                            htf_closes = [float(k[4]) for k in htf_klines[:-1]]  # Exclude forming candle
                            if len(htf_closes) >= self.slow_period:
                                htf_fast_ema = self._calculate_ema_from_prices(htf_closes, self.fast_period)
                                htf_slow_ema = self._calculate_ema_from_prices(htf_closes, self.slow_period)
                                
                                # Only short if 5m trend is down
                                if htf_fast_ema >= htf_slow_ema:
                                    logger.debug(
                                        f"[{self.context.id}] Short blocked: 5m trend is up "
                                        f"(5m fast={htf_fast_ema:.8f} >= slow={htf_slow_ema:.8f})"
                                    )
                                    # Early return: state will be updated in finally block
                                    return StrategySignal(
                                        action="HOLD",
                                        symbol=self.context.symbol,
                                        confidence=0.1,
                                        price=live_price
                                    )
                            else:
                                # Insufficient closed candles for HTF EMA calculation
                                logger.warning(
                                    f"[{self.context.id}] Short blocked: HTF bias enabled but insufficient closed 5m candles "
                                    f"(got {len(htf_closes)} closed, need {self.slow_period})"
                                )
                                return StrategySignal(
                                    action="HOLD",
                                    symbol=self.context.symbol,
                                    confidence=0.1,
                                    price=live_price
                                )
                        
                        # Crossover detection - use DEBUG for backtests, INFO for live
                        log_level = logger.debug if self.context.id == "backtest" else logger.info
                        log_level(
                            f"[{self.context.id}] Death Cross (enter short): fast {fast_ema:.8f} < slow {slow_ema:.8f} "
                            f"(prev: {prev_fast:.8f} >= {prev_slow:.8f})"
                        )
                        # CRITICAL: Use candle close price (where EMA cross was detected) for entry signal
                        # The actual fill price from Binance will update entry_price after order execution
                        # This prevents entry price mismatch when live_price is far from candle close
                        logger.warning(
                            f"[{self.context.id}] SIGNAL => SELL (SHORT entry) at {candle_price:.8f} "
                            f"(candle close, live={live_price:.8f}) pos={self.position} "
                            f"candle_time={last_closed_time}"
                        )
                        self.position = "SHORT"
                        self.entry_price = candle_price  # Use candle close price (will be updated with actual fill price)
                        self.entry_candle_time = last_closed_time  # Track entry candle to prevent EMA exits on same candle
                        
                        # Initialize trailing stop if enabled (will be updated with actual entry after fill)
                        if self.trailing_stop_enabled:
                            activation_pct = float(self.context.params.get("trailing_stop_activation_pct", 0.0))
                            self.trailing_stop = TrailingStopManager(
                                entry_price=candle_price,  # Initial estimate, will sync with real entry after fill
                                take_profit_pct=self.take_profit_pct,
                                stop_loss_pct=self.stop_loss_pct,
                                position_type="SHORT",
                                enabled=True,
                                activation_pct=activation_pct
                            )
                            # Trailing stop initialization - use DEBUG for backtests, INFO for live
                            log_level = logger.debug if self.context.id == "backtest" else logger.info
                            log_level(
                                f"[{self.context.id}] Trailing stop enabled for SHORT (initial): "
                                f"TP={self.trailing_stop.current_tp:.8f}, SL={self.trailing_stop.current_sl:.8f}, "
                                f"Activation={activation_pct*100:.2f}% (will sync with actual entry after fill)"
                            )
                        
                        # State will be updated in finally block
                        return StrategySignal(
                            action="SELL",  # Open short
                            symbol=self.context.symbol,
                            confidence=0.75,
                            price=candle_price,  # Use candle close price for signal
                            exit_reason=None,  # Entry signal, no exit reason
                            position_side="SHORT"  # Opening SHORT position
                        )
                    
                    # --- SHORT Exit: Golden Cross (2) - when short ---
                    # BUG FIX: Forbid EMA exits on the entry candle (standard in professional EMA systems)
                    if (
                        golden_cross
                        and self.position == "SHORT"
                        and self.enable_ema_cross_exit
                        and self.entry_candle_time != last_closed_time  # Prevent exit on entry candle
                    ):
                        # Crossover detection - use DEBUG for backtests, INFO for live
                        log_level = logger.debug if self.context.id == "backtest" else logger.info
                        log_level(
                            f"[{self.context.id}] Golden Cross (exit short): fast {fast_ema:.8f} > slow {slow_ema:.8f}"
                        )
                        logger.warning(f"[{self.context.id}] SIGNAL => BUY at {live_price:.8f} pos={self.position}")
                        current_position = self.position
                        self.position, self.entry_price, self.entry_candle_time = None, None, None
                        self.trailing_stop = None  # Reset trailing stop
                        self.cooldown_left = self.cooldown_candles
                        # State will be updated in finally block
                        return StrategySignal(
                            action="BUY",  # Cover short
                            symbol=self.context.symbol,
                            confidence=0.75,
                            price=live_price,
                            exit_reason="EMA_GOLDEN_CROSS",
                            position_side=current_position
                        )
                
                # Normal HOLD path (when no crossover or prev values not set)
                if prev_fast is None or prev_slow is None:
                    logger.warning(
                        f"[{self.context.id}] HOLD: No previous EMA values (first run or reset) | "
                        f"Price: {live_price:.8f} | Fast EMA: {fast_ema:.8f} | Slow EMA: {slow_ema:.8f} | "
                        f"Position: {self.position}"
                    )
                else:
                    # Check if EMAs are in crossover position but haven't crossed yet
                    fast_above_slow = fast_ema > slow_ema
                    prev_fast_above_slow = prev_fast > prev_slow
                    same_side = fast_above_slow == prev_fast_above_slow
                    
                    # HOLD signals are normal - removed verbose logging for performance
                    # Only log trade signals (BUY/SELL) at INFO level
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.2,
                    price=live_price
                )
            finally:
                # BUG FIX: Only update EMA history when a new candle was actually processed
                # This prevents EMA history from drifting when we return early (e.g., duplicate candle, older candle)
                # This matches TradingView and backtesting engines behavior
                if processed_new_candle:
                    self.prev_fast, self.prev_slow = fast_ema, slow_ema
            
        except Exception as exc:
            logger.error(f"[{self.context.id}] EMA scalping evaluation error: {exc}")
            # CRITICAL FIX: Wrap synchronous get_price() in to_thread to prevent blocking event loop
            current_price = await asyncio.to_thread(
                self.client.get_price,
                self.context.symbol
            )
            return StrategySignal(
                action="HOLD",
                symbol=self.context.symbol,
                confidence=0.0,
                price=current_price
            )
    
    def _ema(self, period: int) -> float:
        """
        Calculate Exponential Moving Average using standard EMA formula.
        - Seeds with SMA(period) for first value
        - Then iterates forward with EMA smoothing
        """
        return self._calculate_ema_from_prices(list(self.closes), period)
    
    def _calculate_ema_from_prices(self, prices: list[float], period: int) -> float:
        """
        Calculate EMA from a list of prices.
        Used for both 1m and 5m timeframes.
        
        Uses shared indicator utility function from app.strategies.indicators.
        Provides fallback for insufficient data to maintain backward compatibility.
        """
        ema = _calculate_ema_from_prices_shared(prices, period)
        if ema is None:
            return fmean(prices) if prices else 0.0
        return ema


# EmaCrossoverScalpingStrategy has been removed - use EmaScalpingStrategy with ema_fast=5, ema_slow=20
# This class is kept as an alias for backward compatibility
EmaCrossoverScalpingStrategy = EmaScalpingStrategy
