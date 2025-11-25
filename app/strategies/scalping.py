from __future__ import annotations

from statistics import fmean
from typing import Deque, Optional
from collections import deque

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.strategies.base import Strategy, StrategyContext, StrategySignal
from app.strategies.trailing_stop import TrailingStopManager


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
    
    def __init__(self, context: StrategyContext, client: BinanceClient) -> None:
        super().__init__(context, client)
        self.fast_period = int(context.params.get("ema_fast", 8))
        self.slow_period = int(context.params.get("ema_slow", 21))
        self.take_profit_pct = float(context.params.get("take_profit_pct", 0.004))
        self.stop_loss_pct = float(context.params.get("stop_loss_pct", 0.002))
        
        # Short trading enabled (default: True)
        self.enable_short = bool(context.params.get("enable_short", True))
        
        # Advanced filters
        self.min_ema_separation = float(context.params.get("min_ema_separation", 0.0002))  # 0.02% of price
        self.enable_htf_bias = bool(context.params.get("enable_htf_bias", True))  # Higher timeframe bias
        self.cooldown_candles = int(context.params.get("cooldown_candles", 2))  # Candles to wait after exit
        
        # Kline interval (default 1 minute for scalping)
        self.interval = str(context.params.get("kline_interval", "1m"))
        # Validate interval format
        valid_intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]
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
        
        # Track last processed candle to avoid duplicate signals
        self.last_closed_candle_time: Optional[int] = None
        
        # Cooldown tracking (simplified counter approach)
        self.cooldown_left: int = 0  # Candles remaining in cooldown
        
        # Dynamic trailing stop (optional)
        self.trailing_stop_enabled = bool(context.params.get("trailing_stop_enabled", False))
        self.trailing_stop: Optional[TrailingStopManager] = None
        
    async def evaluate(self) -> StrategySignal:
        """
        Evaluate market conditions using closed candlestick data.
        Only processes new closed candles to avoid duplicate signals.
        """
        try:
            # Get enough klines to compute EMAs
            limit = max(self.slow_period + 10, 50)
            klines = self.client.get_klines(
                symbol=self.context.symbol,
                interval=self.interval,
                limit=limit
            )
            
            if not klines or len(klines) < self.slow_period + 2:
                current_price = self.client.get_price(self.context.symbol)
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
            
            # Avoid re-processing same candle
            if self.last_closed_candle_time == last_closed_time:
                current_price = self.client.get_price(self.context.symbol)
                logger.debug(
                    f"[{self.context.id}] HOLD: Duplicate candle (already processed) | "
                    f"Price: {current_price:.8f} | Candle time: {last_closed_time}"
                )
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.1,
                    price=current_price
                )
            
            self.last_closed_candle_time = last_closed_time
            
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
            price = last_close_price
            
            logger.debug(
                f"[{self.context.id}] close={price:.8f} fast_ema={fast_ema:.8f} slow_ema={slow_ema:.8f} "
                f"prev_fast={prev_fast} prev_slow={prev_slow}"
            )
            
            # Use try/finally to ensure state is always updated at the end
            # This eliminates redundant updates while maintaining safety
            try:
                # --- Cooldown check (D) - simplified counter approach ---
                if self.cooldown_left > 0:
                    self.cooldown_left -= 1
                    logger.warning(
                        f"[{self.context.id}] HOLD: Cooldown active ({self.cooldown_left} candles remaining) | "
                        f"Price: {price:.8f} | Position: {self.position}"
                    )
                    # Early return: state will be updated in finally block
                    return StrategySignal(
                        action="HOLD",
                        symbol=self.context.symbol,
                        confidence=0.1,
                        price=price
                    )
                
                # --- TP / SL for LONG positions ---
                if self.position == "LONG" and self.entry_price is not None:
                    # Use trailing stop if enabled, otherwise use fixed TP/SL
                    if self.trailing_stop_enabled and self.trailing_stop is not None:
                        # Update trailing stop with current price
                        tp_price, sl_price = self.trailing_stop.update(price)
                        
                        # Check for exit conditions
                        exit_reason = self.trailing_stop.check_exit(price)
                        if exit_reason == "TP":
                            logger.info(
                                f"[{self.context.id}] Long Take profit hit (trailing): {price:.8f} >= {tp_price:.8f}"
                            )
                            logger.warning(f"[{self.context.id}] SIGNAL => SELL at {price:.8f} pos={self.position}")
                            self.position, self.entry_price = None, None
                            self.trailing_stop = None
                            self.cooldown_left = self.cooldown_candles
                            return StrategySignal(
                                action="SELL",
                                symbol=self.context.symbol,
                                confidence=0.85,
                                price=price
                            )
                        elif exit_reason == "SL":
                            logger.info(
                                f"[{self.context.id}] Long Stop loss hit (trailing): {price:.8f} <= {sl_price:.8f}"
                            )
                            logger.warning(f"[{self.context.id}] SIGNAL => SELL at {price:.8f} pos={self.position}")
                            self.position, self.entry_price = None, None
                            self.trailing_stop = None
                            self.cooldown_left = self.cooldown_candles
                            return StrategySignal(
                                action="SELL",
                                symbol=self.context.symbol,
                                confidence=0.85,
                                price=price
                            )
                    else:
                        # Fixed TP/SL (original behavior)
                        tp_price = self.entry_price * (1 + self.take_profit_pct)
                        sl_price = self.entry_price * (1 - self.stop_loss_pct)
                        
                        if price >= tp_price:
                            logger.info(
                                f"[{self.context.id}] Long Take profit hit: {price:.8f} >= {tp_price:.8f}"
                            )
                            logger.warning(f"[{self.context.id}] SIGNAL => SELL at {price:.8f} pos={self.position}")
                            self.position, self.entry_price = None, None
                            self.cooldown_left = self.cooldown_candles
                            return StrategySignal(
                                action="SELL",
                                symbol=self.context.symbol,
                                confidence=0.85,
                                price=price
                            )
                        
                        if price <= sl_price:
                            logger.info(
                                f"[{self.context.id}] Long Stop loss hit: {price:.8f} <= {sl_price:.8f}"
                            )
                            logger.warning(f"[{self.context.id}] SIGNAL => SELL at {price:.8f} pos={self.position}")
                            self.position, self.entry_price = None, None
                            self.cooldown_left = self.cooldown_candles
                            return StrategySignal(
                                action="SELL",
                                symbol=self.context.symbol,
                                confidence=0.85,
                                price=price
                            )
                
                # --- TP / SL for SHORT positions (3) - INVERTED ---
                if self.position == "SHORT" and self.entry_price is not None:
                    # Use trailing stop if enabled, otherwise use fixed TP/SL
                    if self.trailing_stop_enabled and self.trailing_stop is not None:
                        # Update trailing stop with current price
                        tp_price, sl_price = self.trailing_stop.update(price)
                        
                        # Check for exit conditions
                        exit_reason = self.trailing_stop.check_exit(price)
                        if exit_reason == "TP":
                            logger.info(
                                f"[{self.context.id}] Short Take profit hit (trailing): {price:.8f} <= {tp_price:.8f}"
                            )
                            logger.warning(f"[{self.context.id}] SIGNAL => BUY at {price:.8f} pos={self.position}")
                            self.position, self.entry_price = None, None
                            self.trailing_stop = None
                            self.cooldown_left = self.cooldown_candles
                            return StrategySignal(
                                action="BUY",  # Cover short
                                symbol=self.context.symbol,
                                confidence=0.85,
                                price=price
                            )
                        elif exit_reason == "SL":
                            logger.info(
                                f"[{self.context.id}] Short Stop loss hit (trailing): {price:.8f} >= {sl_price:.8f}"
                            )
                            logger.warning(f"[{self.context.id}] SIGNAL => BUY at {price:.8f} pos={self.position}")
                            self.position, self.entry_price = None, None
                            self.trailing_stop = None
                            self.cooldown_left = self.cooldown_candles
                            return StrategySignal(
                                action="BUY",  # Cover short
                                symbol=self.context.symbol,
                                confidence=0.85,
                                price=price
                            )
                    else:
                        # Fixed TP/SL (original behavior - inverted for shorts)
                        tp_price = self.entry_price * (1 - self.take_profit_pct)  # Price must drop
                        sl_price = self.entry_price * (1 + self.stop_loss_pct)  # Price must rise
                        
                        if price <= tp_price:
                            logger.info(
                                f"[{self.context.id}] Short Take profit hit: {price:.8f} <= {tp_price:.8f}"
                            )
                            logger.warning(f"[{self.context.id}] SIGNAL => BUY at {price:.8f} pos={self.position}")
                            self.position, self.entry_price = None, None
                            self.cooldown_left = self.cooldown_candles
                            return StrategySignal(
                                action="BUY",  # Cover short
                                symbol=self.context.symbol,
                                confidence=0.85,
                                price=price
                            )
                        
                        if price >= sl_price:
                            logger.info(
                                f"[{self.context.id}] Short Stop loss hit: {price:.8f} >= {sl_price:.8f}"
                            )
                            logger.warning(f"[{self.context.id}] SIGNAL => BUY at {price:.8f} pos={self.position}")
                            self.position, self.entry_price = None, None
                            self.cooldown_left = self.cooldown_candles
                            return StrategySignal(
                                action="BUY",  # Cover short
                                symbol=self.context.symbol,
                                confidence=0.85,
                                price=price
                            )
                
                # --- Minimum EMA separation filter (B) ---
                # Note: Apply separation filter only for entries, not exits (safety consideration)
                # For exits, we want to allow closing even if EMAs are close
                ema_separation_pct = abs(fast_ema - slow_ema) / price if price > 0 else 0
                should_check_separation = self.position is None  # Only check for new entries
                
                if should_check_separation and ema_separation_pct < self.min_ema_separation:
                    logger.warning(
                        f"[{self.context.id}] HOLD: EMA separation too small ({ema_separation_pct:.6f} < {self.min_ema_separation}) | "
                        f"Price: {price:.8f} | Fast EMA: {fast_ema:.8f} | Slow EMA: {slow_ema:.8f} | Position: {self.position}"
                    )
                    # Early return: state will be updated in finally block
                    return StrategySignal(
                        action="HOLD",
                        symbol=self.context.symbol,
                        confidence=0.1,
                        price=price
                    )
                
                # --- Crossover detection on closed candles ---
                # CRITICAL: Use local prev_fast/prev_slow (from previous candle), not self.prev_*
                # This allows proper crossover detection between candles
                if prev_fast is not None and prev_slow is not None:
                    golden_cross = (prev_fast <= prev_slow) and (fast_ema > slow_ema)
                    death_cross = (prev_fast >= prev_slow) and (fast_ema < slow_ema)
                    
                    # --- LONG Entry: Golden Cross (when flat) ---
                    if golden_cross and self.position is None:
                        logger.info(
                            f"[{self.context.id}] Golden Cross: fast {fast_ema:.8f} > slow {slow_ema:.8f} "
                            f"(prev: {prev_fast:.8f} <= {prev_slow:.8f})"
                        )
                        logger.warning(f"[{self.context.id}] SIGNAL => BUY at {price:.8f} pos={self.position}")
                        self.position = "LONG"
                        self.entry_price = price
                        
                        # Initialize trailing stop if enabled
                        if self.trailing_stop_enabled:
                            activation_pct = float(self.context.params.get("trailing_stop_activation_pct", 0.0))
                            self.trailing_stop = TrailingStopManager(
                                entry_price=price,
                                take_profit_pct=self.take_profit_pct,
                                stop_loss_pct=self.stop_loss_pct,
                                position_type="LONG",
                                enabled=True,
                                activation_pct=activation_pct
                            )
                            logger.info(
                                f"[{self.context.id}] Trailing stop enabled for LONG: "
                                f"TP={self.trailing_stop.current_tp:.8f}, SL={self.trailing_stop.current_sl:.8f}, "
                                f"Activation={activation_pct*100:.2f}% (price must reach {self.trailing_stop.activation_price:.8f})"
                            )
                        
                        # State will be updated in finally block
                        return StrategySignal(
                            action="BUY",
                            symbol=self.context.symbol,
                            confidence=0.75,
                            price=price
                        )
                    
                    # --- LONG Exit: Death Cross (when long) ---
                    if death_cross and self.position == "LONG":
                        logger.info(
                            f"[{self.context.id}] Death Cross (exit long): fast {fast_ema:.8f} < slow {slow_ema:.8f} "
                            f"(prev: {prev_fast:.8f} >= {prev_slow:.8f})"
                        )
                        logger.warning(f"[{self.context.id}] SIGNAL => SELL at {price:.8f} pos={self.position}")
                        self.position, self.entry_price = None, None
                        self.trailing_stop = None  # Reset trailing stop
                        self.cooldown_left = self.cooldown_candles
                        # State will be updated in finally block
                        return StrategySignal(
                            action="SELL",
                            symbol=self.context.symbol,
                            confidence=0.75,
                            price=price
                        )
                    
                    # --- SHORT Entry: Death Cross (1) - when flat and short enabled ---
                    if death_cross and self.position is None and self.enable_short:
                        # Higher-timeframe bias check (C)
                        if self.enable_htf_bias and self.interval == "1m":
                            # Check 5m trend
                            htf_klines = self.client.get_klines(
                                symbol=self.context.symbol,
                                interval="5m",
                                limit=self.slow_period + 5
                            )
                            if htf_klines and len(htf_klines) >= self.slow_period:
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
                                            price=price
                                        )
                        
                        logger.info(
                            f"[{self.context.id}] Death Cross (enter short): fast {fast_ema:.8f} < slow {slow_ema:.8f} "
                            f"(prev: {prev_fast:.8f} >= {prev_slow:.8f})"
                        )
                        logger.warning(f"[{self.context.id}] SIGNAL => SELL at {price:.8f} pos={self.position}")
                        self.position = "SHORT"
                        self.entry_price = price
                        
                        # Initialize trailing stop if enabled
                        if self.trailing_stop_enabled:
                            activation_pct = float(self.context.params.get("trailing_stop_activation_pct", 0.0))
                            self.trailing_stop = TrailingStopManager(
                                entry_price=price,
                                take_profit_pct=self.take_profit_pct,
                                stop_loss_pct=self.stop_loss_pct,
                                position_type="SHORT",
                                enabled=True,
                                activation_pct=activation_pct
                            )
                            logger.info(
                                f"[{self.context.id}] Trailing stop enabled for SHORT: "
                                f"TP={self.trailing_stop.current_tp:.8f}, SL={self.trailing_stop.current_sl:.8f}, "
                                f"Activation={activation_pct*100:.2f}% (price must reach {self.trailing_stop.activation_price:.8f})"
                            )
                        
                        # State will be updated in finally block
                        return StrategySignal(
                            action="SELL",  # Open short
                            symbol=self.context.symbol,
                            confidence=0.75,
                            price=price
                        )
                    
                    # --- SHORT Exit: Golden Cross (2) - when short ---
                    if golden_cross and self.position == "SHORT":
                        logger.info(
                            f"[{self.context.id}] Golden Cross (exit short): fast {fast_ema:.8f} > slow {slow_ema:.8f}"
                        )
                        logger.warning(f"[{self.context.id}] SIGNAL => BUY at {price:.8f} pos={self.position}")
                        self.position, self.entry_price = None, None
                        self.trailing_stop = None  # Reset trailing stop
                        self.cooldown_left = self.cooldown_candles
                        # State will be updated in finally block
                        return StrategySignal(
                            action="BUY",  # Cover short
                            symbol=self.context.symbol,
                            confidence=0.75,
                            price=price
                        )
                
                # Normal HOLD path (when no crossover or prev values not set)
                if prev_fast is None or prev_slow is None:
                    logger.warning(
                        f"[{self.context.id}] HOLD: No previous EMA values (first run or reset) | "
                        f"Price: {price:.8f} | Fast EMA: {fast_ema:.8f} | Slow EMA: {slow_ema:.8f} | "
                        f"Position: {self.position}"
                    )
                else:
                    # Check if EMAs are in crossover position but haven't crossed yet
                    fast_above_slow = fast_ema > slow_ema
                    prev_fast_above_slow = prev_fast > prev_slow
                    same_side = fast_above_slow == prev_fast_above_slow
                    
                    logger.warning(
                        f"[{self.context.id}] HOLD: No crossover detected | "
                        f"Price: {price:.8f} | Fast EMA: {fast_ema:.8f} | Slow EMA: {slow_ema:.8f} | "
                        f"Prev Fast: {prev_fast:.8f} | Prev Slow: {prev_slow:.8f} | "
                        f"Fast above slow: {fast_above_slow} | Prev fast above slow: {prev_fast_above_slow} | "
                        f"Same side: {same_side} | Position: {self.position}"
                    )
                return StrategySignal(
                    action="HOLD",
                    symbol=self.context.symbol,
                    confidence=0.2,
                    price=price
                )
            finally:
                # CRITICAL: Always update state at the end, regardless of return path
                # This ensures state consistency and eliminates redundant updates
                self.prev_fast, self.prev_slow = fast_ema, slow_ema
            
        except Exception as exc:
            logger.error(f"[{self.context.id}] EMA scalping evaluation error: {exc}")
            current_price = self.client.get_price(self.context.symbol)
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
        """
        if len(prices) < period:
            return fmean(prices) if prices else 0.0
        
        smoothing = 2.0 / (period + 1)
        # Start with SMA for the first value
        ema = fmean(prices[:period])
        
        # Calculate EMA for remaining prices
        for p in prices[period:]:
            ema = (p - ema) * smoothing + ema
        
        return ema


# EmaCrossoverScalpingStrategy has been removed - use EmaScalpingStrategy with ema_fast=5, ema_slow=20
# This class is kept as an alias for backward compatibility
EmaCrossoverScalpingStrategy = EmaScalpingStrategy

