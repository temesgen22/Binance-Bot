from __future__ import annotations

import asyncio
import math
from statistics import fmean
from typing import Deque, Optional, Literal
from collections import deque

from loguru import logger

from typing import TYPE_CHECKING
from app.core.my_binance_client import BinanceClient
from app.strategies.base import Strategy, StrategyContext, StrategySignal
from app.strategies.trailing_stop import TrailingStopManager
from app.strategies.indicators import (
    calculate_atr,
    calculate_ema as _calculate_ema_from_prices_shared,
    calculate_rsi,
)
from app.strategies.structure_filters import (
    passes_market_structure_filter,
    required_closed_candles_for_structure,
)
from app.strategies.pnl_giveback import (
    giveback_should_trigger,
    update_peak_unrealized,
)

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
        p = context.params
        self.fast_period = self.param_int(p, "ema_fast", 8)
        self.slow_period = self.param_int(p, "ema_slow", 21)
        self.take_profit_pct = self.param_float(p, "take_profit_pct", 0.004)
        self.stop_loss_pct = self.param_float(p, "stop_loss_pct", 0.002)
        
        # Short trading enabled (default: True)
        self.enable_short = self.parse_bool_param(p.get("enable_short"), default=True)
        
        # Advanced filters
        self.min_ema_separation = self.param_float(p, "min_ema_separation", 0.0002)  # 0.02% of price
        self.enable_htf_bias = self.parse_bool_param(p.get("enable_htf_bias"), default=True)  # Higher timeframe bias
        self.cooldown_candles = self.param_int(p, "cooldown_candles", 2)  # Candles to wait after exit
        self.enable_ema_cross_exit = self.parse_bool_param(p.get("enable_ema_cross_exit"), default=True)  # Enable EMA cross exits
        self.use_rsi_filter = self.parse_bool_param(p.get("use_rsi_filter"), default=False)
        self.rsi_period_filter = self.param_int(p, "rsi_period", 14)
        self.rsi_long_min = self.param_float(p, "rsi_long_min", 50.0)
        self.rsi_short_max = self.param_float(p, "rsi_short_max", 50.0)
        self.use_atr_filter = self.parse_bool_param(p.get("use_atr_filter"), default=False)
        self.atr_period_filter = self.param_int(p, "atr_period", 14)
        self.atr_min_pct = self.param_float(p, "atr_min_pct", 0.0)
        self.atr_max_pct = self.param_float(p, "atr_max_pct", 100.0)
        self.use_volume_filter = self.parse_bool_param(p.get("use_volume_filter"), default=False)
        self.volume_ma_period = self.param_int(p, "volume_ma_period", 20)
        self.volume_multiplier_min = self.param_float(p, "volume_multiplier_min", 1.0)
        self.use_structure_filter = self.parse_bool_param(p.get("use_structure_filter"), default=False)
        self.structure_left_bars = self.param_int(p, "structure_left_bars", 2)
        self.structure_right_bars = self.param_int(p, "structure_right_bars", 2)
        self.structure_confirm_on_close = self.parse_bool_param(
            p.get("structure_confirm_on_close"), default=True
        )

        # Kline interval (default 1 minute for scalping)
        _ki = p.get("kline_interval", "1m")
        self.interval = "1m" if _ki is None else str(_ki)
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
        self.trailing_stop_enabled = self.parse_bool_param(p.get("trailing_stop_enabled"), default=False)
        self.trailing_stop: Optional[TrailingStopManager] = None

        # Open PnL giveback stop (optional): close after unrealized falls X USDT from peak
        self.pnl_giveback_enabled = self.parse_bool_param(p.get("pnl_giveback_enabled"), default=False)
        self.pnl_giveback_from_peak_usdt = max(0.0, self.param_float(p, "pnl_giveback_from_peak_usdt", 5.0))
        self.pnl_giveback_min_peak_usdt = max(0.0, self.param_float(p, "pnl_giveback_min_peak_usdt", 0.0))
        self.peak_unrealized_pnl: Optional[float] = None

        # SL trigger: live_price (any tick) or candle_close (only when candle close is beyond SL)
        _sl_raw = p.get("sl_trigger_mode", "live_price")
        _sl_mode = str(_sl_raw if _sl_raw is not None else "live_price").lower()
        self.sl_trigger_mode = _sl_mode if _sl_mode in ("live_price", "candle_close") else "live_price"

        _em = p.get("entry_mode", "cross_only")
        self.entry_mode: Literal["cross_only", "cross_or_trend"] = (
            _em if _em in ("cross_only", "cross_or_trend") else "cross_only"
        )
        self.trend_entry_max_candles_after_cross = max(0, self.param_int(p, "trend_entry_max_candles_after_cross", 0))
        self.trend_entry_unlimited_after_cross = self.parse_bool_param(
            p.get("trend_entry_unlimited_after_cross"), default=False
        )
        self.trend_entry_max_per_regime = max(1, self.param_int(p, "trend_entry_max_per_regime", 1))
        self.trend_entry_require_ema_separation = self.parse_bool_param(
            p.get("trend_entry_require_ema_separation"), default=True
        )
        self._entry_regime: Literal["none", "long", "short"] = "none"
        self._regime_armed_at: Optional[int] = None
        self._trend_entries_used: int = 0
        # True if last open was trend follow-up (regime + count persist after exit until opposite cross)
        self._opened_entry_via_trend: bool = False

    def _note_position_closed_flat(self) -> None:
        """When position goes flat: preserve regime after a trend entry exit; else clear regime."""
        if self._opened_entry_via_trend:
            self._opened_entry_via_trend = False
        else:
            self._clear_trend_regime()

    def _required_filter_candles(self) -> int:
        return max(
            self.slow_period + 2,
            (self.rsi_period_filter + 1) if self.use_rsi_filter else 0,
            (self.atr_period_filter + 1) if self.use_atr_filter else 0,
            (self.volume_ma_period + 1) if self.use_volume_filter else 0,
            required_closed_candles_for_structure(self.structure_left_bars, self.structure_right_bars)
            if self.use_structure_filter
            else 0,
        )

    def _passes_entry_filters(
        self,
        candidate_side: Literal["LONG", "SHORT"],
        closed_klines: list[list],
        closing_prices: list[float],
        candle_time: int,
    ) -> bool:
        # Fail-closed: if enabled filters cannot compute safely, block entry.
        if self.use_rsi_filter:
            rsi_value = calculate_rsi(closing_prices, period=self.rsi_period_filter)
            if rsi_value is None or not math.isfinite(rsi_value):
                logger.info(f"[{self.context.id}] Entry blocked by RSI insufficiency: side={candidate_side}, candle={candle_time}")
                return False
            if candidate_side == "LONG" and rsi_value < self.rsi_long_min:
                logger.info(
                    f"[{self.context.id}] Entry blocked by RSI: side=LONG, value={rsi_value:.4f}, min={self.rsi_long_min:.4f}, candle={candle_time}"
                )
                return False
            if candidate_side == "SHORT" and rsi_value > self.rsi_short_max:
                logger.info(
                    f"[{self.context.id}] Entry blocked by RSI: side=SHORT, value={rsi_value:.4f}, max={self.rsi_short_max:.4f}, candle={candle_time}"
                )
                return False

        if self.use_atr_filter:
            atr_value = calculate_atr(closed_klines, period=self.atr_period_filter)
            close_price = closing_prices[-1] if closing_prices else 0.0
            if (
                atr_value is None
                or not math.isfinite(atr_value)
                or not math.isfinite(close_price)
                or close_price <= 0
            ):
                logger.info(f"[{self.context.id}] Entry blocked by ATR insufficiency: side={candidate_side}, candle={candle_time}")
                return False
            atr_pct = (atr_value / close_price) * 100.0
            if not math.isfinite(atr_pct) or atr_pct < self.atr_min_pct or atr_pct > self.atr_max_pct:
                logger.info(
                    f"[{self.context.id}] Entry blocked by ATR: side={candidate_side}, value={atr_pct:.4f}, range=[{self.atr_min_pct:.4f}, {self.atr_max_pct:.4f}], candle={candle_time}"
                )
                return False

        if self.use_volume_filter:
            # Compare *current* closed candle volume to SMA of the *prior* N volumes only.
            # Including the signal candle in the mean biases the ratio toward 1.0 (common miscalculation).
            if len(closed_klines) < self.volume_ma_period + 1:
                logger.info(f"[{self.context.id}] Entry blocked by Volume insufficiency: side={candidate_side}, candle={candle_time}")
                return False
            prior_volumes = [float(k[5]) for k in closed_klines[-(self.volume_ma_period + 1) : -1]]
            current_volume = float(closed_klines[-1][5])
            vol_sma = fmean(prior_volumes)
            if (
                not math.isfinite(vol_sma)
                or not math.isfinite(current_volume)
                or vol_sma <= 0
            ):
                logger.info(f"[{self.context.id}] Entry blocked by Volume invalid data: side={candidate_side}, candle={candle_time}")
                return False
            volume_ratio = current_volume / vol_sma
            if not math.isfinite(volume_ratio) or volume_ratio < self.volume_multiplier_min:
                logger.info(
                    f"[{self.context.id}] Entry blocked by Volume: side={candidate_side}, value={volume_ratio:.4f}, min={self.volume_multiplier_min:.4f}, candle={candle_time}"
                )
                return False

        if self.use_structure_filter:
            ok, reason = passes_market_structure_filter(
                candidate_side,
                closed_klines,
                self.structure_left_bars,
                self.structure_right_bars,
                self.structure_confirm_on_close,
            )
            if not ok:
                logger.info(
                    f"[{self.context.id}] Entry blocked by Structure: side={candidate_side}, reason={reason}, candle={candle_time}"
                )
                return False

        return True
    
    def _reset_giveback_state(self) -> None:
        self.peak_unrealized_pnl = None

    def _clear_trend_regime(self) -> None:
        """Clear trend follow-up regime (arming bar in §4 plan; reset on opposite cross or cross entry)."""
        self._entry_regime = "none"
        self._regime_armed_at = None
        self._trend_entries_used = 0

    @staticmethod
    def _bars_after_regime_arm(closed_klines: list[list], armed_at: Optional[int]) -> int:
        """Number of closed candles from arming candle to last closed (0 = arming bar is last closed)."""
        if armed_at is None:
            return 0
        for i, k in enumerate(closed_klines):
            if int(k[6]) == armed_at:
                return len(closed_klines) - 1 - i
        return 0

    def _arm_scalping_regime_on_cross_flat(
        self, golden_cross: bool, death_cross: bool, last_closed_time: int
    ) -> None:
        """Arm regime on cross detection while flat; independent of filters."""
        if self.position is not None:
            return
        if golden_cross:
            self._entry_regime = "long"
            self._regime_armed_at = last_closed_time
            self._trend_entries_used = 0
        elif death_cross:
            self._entry_regime = "short"
            self._regime_armed_at = last_closed_time
            self._trend_entries_used = 0

    def _trend_followup_window_ok_scalping(self, closed_klines: list[list]) -> bool:
        if self.entry_mode != "cross_or_trend":
            return False
        if self.trend_entry_max_candles_after_cross == 0 and not self.trend_entry_unlimited_after_cross:
            return False
        if self._regime_armed_at is None:
            return False
        bars_after = self._bars_after_regime_arm(closed_klines, self._regime_armed_at)
        if bars_after < 1:
            return False
        if self.trend_entry_unlimited_after_cross:
            return True
        return bars_after <= self.trend_entry_max_candles_after_cross

    def _trend_separation_ok_scalping(self, ema_separation_pct: float) -> bool:
        if not self.trend_entry_require_ema_separation:
            return True
        return ema_separation_pct >= self.min_ema_separation

    async def _htf_bias_blocks_short_entry_scalping(self, live_price: float) -> bool:
        """True = block SHORT entry (same logic as death-cross SHORT path)."""
        if not (self.enable_htf_bias and self.interval == "1m"):
            return False
        if self.kline_manager:
            try:
                htf_klines = await self.kline_manager.get_klines(
                    symbol=self.context.symbol,
                    interval="5m",
                    limit=self.slow_period + 5,
                )
            except Exception as e:
                logger.warning(f"WebSocket HTF klines failed, falling back to REST API: {e}")
                htf_klines = await asyncio.to_thread(
                    self.client.get_klines,
                    symbol=self.context.symbol,
                    interval="5m",
                    limit=self.slow_period + 5,
                )
        else:
            htf_klines = await asyncio.to_thread(
                self.client.get_klines,
                symbol=self.context.symbol,
                interval="5m",
                limit=self.slow_period + 5,
            )
        if not htf_klines or len(htf_klines) < self.slow_period + 1:
            logger.warning(
                f"[{self.context.id}] Short blocked: HTF bias enabled but insufficient 5m data "
                f"(got {len(htf_klines) if htf_klines else 0} klines, need {self.slow_period + 1})"
            )
            return True
        htf_closes = [float(k[4]) for k in htf_klines[:-1]]
        if len(htf_closes) >= self.slow_period:
            htf_fast_ema = self._calculate_ema_from_prices(htf_closes, self.fast_period)
            htf_slow_ema = self._calculate_ema_from_prices(htf_closes, self.slow_period)
            if htf_fast_ema >= htf_slow_ema:
                logger.debug(
                    f"[{self.context.id}] Short blocked: 5m trend is up "
                    f"(5m fast={htf_fast_ema:.8f} >= slow={htf_slow_ema:.8f})"
                )
                return True
        else:
            logger.warning(
                f"[{self.context.id}] Short blocked: HTF bias enabled but insufficient closed 5m candles "
                f"(got {len(htf_closes)} closed, need {self.slow_period})"
            )
            return True
        return False

    def _maybe_pnl_giveback_exit(
        self,
        live_price: float,
        unrealized_pnl: Optional[float],
        context_suffix: str,
    ) -> Optional[StrategySignal]:
        """After TP/SL checks pass, optionally exit on peak-to-current unrealized drawdown (USDT)."""
        if not self.pnl_giveback_enabled or self.position is None or self.entry_price is None:
            return None
        if self.position not in ("LONG", "SHORT"):
            return None
        if unrealized_pnl is None:
            return None
        if not math.isfinite(unrealized_pnl):
            return None
        self.peak_unrealized_pnl = update_peak_unrealized(self.peak_unrealized_pnl, unrealized_pnl)
        peak = self.peak_unrealized_pnl
        ok, reason = giveback_should_trigger(
            peak_unrealized=peak,
            current_unrealized=unrealized_pnl,
            min_peak_usdt=self.pnl_giveback_min_peak_usdt,
            giveback_usdt=self.pnl_giveback_from_peak_usdt,
        )
        if not ok:
            return None
        current_position = self.position
        if current_position == "LONG":
            exit_sig = StrategySignal(
                action="SELL",
                symbol=self.context.symbol,
                confidence=0.85,
                price=live_price,
                exit_reason="PNL_GIVEBACK",
                position_side=current_position,
            )
        elif current_position == "SHORT":
            exit_sig = StrategySignal(
                action="BUY",
                symbol=self.context.symbol,
                confidence=0.85,
                price=live_price,
                exit_reason="PNL_GIVEBACK",
                position_side=current_position,
            )
        else:
            logger.error(
                f"[{self.context.id}] PnL giveback: invalid position_side={current_position!r}; not closing"
            )
            return None
        logger.info(
            f"[{self.context.id}] PnL giveback stop{context_suffix}: peak={peak:.4f} current={unrealized_pnl:.4f} "
            f"({reason})"
        )
        self._note_position_closed_flat()
        self.position, self.entry_price, self.entry_candle_time = None, None, None
        self.trailing_stop = None
        self._reset_giveback_state()
        self.cooldown_left = self.cooldown_candles
        return exit_sig

    def _check_tp_sl(
        self,
        live_price: float,
        context: str = "",
        candle_close_price: Optional[float] = None,
        unrealized_pnl: Optional[float] = None,
    ) -> Optional[StrategySignal]:
        """
        Check take profit and stop loss conditions using live price.
        
        This method centralizes TP/SL logic to avoid duplication and ensure consistency.
        When sl_trigger_mode is candle_close and candle_close_price is provided, SL uses
        the candle close for the check; TP always uses live_price.
        
        Args:
            live_price: Current market price
            context: Context string for logging (e.g., "older candle", "no new candle", "")
            candle_close_price: Close of last closed candle; used for SL when sl_trigger_mode is candle_close
        
        Returns:
            StrategySignal if TP/SL is hit, None otherwise
        """
        if self.position is None or self.entry_price is None:
            return None

        # Use candle close for SL only when user chose candle_close; otherwise always use live price
        if self.sl_trigger_mode == "candle_close" and candle_close_price is not None:
            use_sl_price = candle_close_price
            sl_exit_price = candle_close_price
        else:
            use_sl_price = live_price
            sl_exit_price = live_price
        
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
                # TP uses live_price; SL uses use_sl_price (candle close when sl_trigger_mode is candle_close)
                if live_price >= tp_price:
                    exit_reason = "TP"
                elif use_sl_price <= sl_price:
                    exit_reason = "SL"
                else:
                    exit_reason = None
                if exit_reason == "TP":
                    logger.info(
                        f"[{self.context.id}] Long Take profit hit (trailing{context_suffix}): "
                        f"{live_price:.8f} >= {tp_price:.8f}"
                    )
                    current_position = self.position
                    self._note_position_closed_flat()
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.trailing_stop = None
                    self._reset_giveback_state()
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
                        f"{use_sl_price:.8f} <= {sl_price:.8f}"
                    )
                    current_position = self.position
                    self._note_position_closed_flat()
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.trailing_stop = None
                    self._reset_giveback_state()
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="SELL",
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=sl_exit_price,
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
                    self._note_position_closed_flat()
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self._reset_giveback_state()
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="SELL",
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="TP",
                        position_side=current_position
                    )
                if use_sl_price <= sl_price:
                    logger.info(
                        f"[{self.context.id}] Long Stop loss hit{context_suffix}: "
                        f"{use_sl_price:.8f} <= {sl_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => SELL at {sl_exit_price:.8f} pos={self.position}")
                    current_position = self.position
                    self._note_position_closed_flat()
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self._reset_giveback_state()
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="SELL",
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=sl_exit_price,
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
                # TP uses live_price; SL uses use_sl_price (candle close when sl_trigger_mode is candle_close)
                if live_price <= tp_price:
                    exit_reason = "TP"
                elif use_sl_price >= sl_price:
                    exit_reason = "SL"
                else:
                    exit_reason = None
                if exit_reason == "TP":
                    logger.info(
                        f"[{self.context.id}] Short Take profit hit (trailing{context_suffix}): "
                        f"{live_price:.8f} <= {tp_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => BUY at {live_price:.8f} pos={self.position}")
                    current_position = self.position
                    self._note_position_closed_flat()
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.trailing_stop = None
                    self._reset_giveback_state()
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
                        f"{use_sl_price:.8f} >= {sl_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => BUY at {sl_exit_price:.8f} pos={self.position}")
                    current_position = self.position
                    self._note_position_closed_flat()
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self.trailing_stop = None
                    self._reset_giveback_state()
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="BUY",  # Cover short
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=sl_exit_price,
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
                    self._note_position_closed_flat()
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self._reset_giveback_state()
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="BUY",  # Cover short
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=live_price,
                        exit_reason="TP",
                        position_side=current_position
                    )
                if use_sl_price >= sl_price:
                    logger.info(
                        f"[{self.context.id}] Short Stop loss hit{context_suffix}: "
                        f"{use_sl_price:.8f} >= {sl_price:.8f}"
                    )
                    logger.warning(f"[{self.context.id}] SIGNAL => BUY at {sl_exit_price:.8f} pos={self.position}")
                    current_position = self.position
                    self._note_position_closed_flat()
                    self.position, self.entry_price, self.entry_candle_time = None, None, None
                    self._reset_giveback_state()
                    self.cooldown_left = self.cooldown_candles
                    return StrategySignal(
                        action="BUY",  # Cover short
                        symbol=self.context.symbol,
                        confidence=0.85,
                        price=sl_exit_price,
                        exit_reason="SL",
                        position_side=current_position
                    )
        
        return self._maybe_pnl_giveback_exit(live_price, unrealized_pnl, context_suffix)
    
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
            self._clear_trend_regime()
            self._opened_entry_via_trend = False
            self.position = None
            self.entry_price = None
            self.entry_candle_time = None
            self.trailing_stop = None
            self._reset_giveback_state()
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
            self._reset_giveback_state()
            
            # Reinitialize trailing stop if enabled and we have entry price
            if self.trailing_stop_enabled and entry_price is not None:
                activation_pct = self.param_float(self.context.params, "trailing_stop_activation_pct", 0.0)
                self.trailing_stop = TrailingStopManager(
                    entry_price=entry_price,
                    take_profit_pct=self.take_profit_pct,
                    stop_loss_pct=self.stop_loss_pct,
                    position_type=position_side,
                    enabled=True,
                    activation_pct=activation_pct,
                    trail_step_pct=activation_pct,  # same value: step = activation %
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
            self._reset_giveback_state()
        
        # If entry price changed (position size changed), update it
        elif position_side is not None and entry_price is not None and self.entry_price != entry_price:
            logger.debug(
                f"[{self.context.id}] Entry price changed: {self.entry_price:.8f} -> {entry_price:.8f}. "
                f"Updating strategy state."
            )
            self.entry_price = entry_price
            self._reset_giveback_state()
            # Reset trailing stop with new entry price if enabled
            if self.trailing_stop_enabled:
                activation_pct = self.param_float(self.context.params, "trailing_stop_activation_pct", 0.0)
                self.trailing_stop = TrailingStopManager(
                    entry_price=entry_price,
                    take_profit_pct=self.take_profit_pct,
                    stop_loss_pct=self.stop_loss_pct,
                    position_type=position_side,
                    enabled=True,
                    activation_pct=activation_pct,
                    trail_step_pct=activation_pct,  # same value: step = activation %
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
            
            required_candles = self._required_filter_candles()
            if not klines or len(klines) < required_candles:
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
            
            unrealized_snapshot: Optional[float] = None
            if self.position and self.pnl_giveback_enabled:
                try:
                    pos = await asyncio.to_thread(self.client.get_open_position, self.context.symbol)
                    if pos:
                        unrealized_snapshot = float(pos.get("unRealizedProfit") or 0)
                except Exception as exc:
                    logger.debug(f"[{self.context.id}] get_open_position for PnL giveback: {exc}")
            
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
                    candle_close_price = last_close_price if self.sl_trigger_mode == "candle_close" else None
                    tp_sl_signal = self._check_tp_sl(
                        live_price,
                        context="older candle",
                        candle_close_price=candle_close_price,
                        unrealized_pnl=unrealized_snapshot,
                    )
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
                candle_close_price = last_close_price if self.sl_trigger_mode == "candle_close" else None
                tp_sl_signal = self._check_tp_sl(
                    live_price,
                    context="no new candle",
                    candle_close_price=candle_close_price,
                    unrealized_pnl=unrealized_snapshot,
                )
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
                # ALWAYS check TP/SL when in position (SL may use candle close when sl_trigger_mode is candle_close)
                if self.position == "LONG" and self.entry_price is not None:
                    candle_close_price = last_close_price if self.sl_trigger_mode == "candle_close" else None
                    tp_sl_signal = self._check_tp_sl(
                        live_price,
                        context="",
                        candle_close_price=candle_close_price,
                        unrealized_pnl=unrealized_snapshot,
                    )
                    if tp_sl_signal:
                        return tp_sl_signal
                
                # --- TP / SL for SHORT positions (3) - INVERTED ---
                if self.position == "SHORT" and self.entry_price is not None:
                    candle_close_price = last_close_price if self.sl_trigger_mode == "candle_close" else None
                    tp_sl_signal = self._check_tp_sl(
                        live_price,
                        context="",
                        candle_close_price=candle_close_price,
                        unrealized_pnl=unrealized_snapshot,
                    )
                    if tp_sl_signal:
                        return tp_sl_signal
                
                # --- Minimum EMA separation filter (B) ---
                # Note: Apply separation filter only for entries, not exits (safety consideration)
                # For exits, we want to allow closing even if EMAs are close
                # Use candle_price for EMA calculations (stable reference)
                ema_separation_pct = abs(fast_ema - slow_ema) / candle_price if candle_price > 0 else 0
                # cross_only: global separation gate (same as legacy). cross_or_trend: separation checked per cross/trend path.
                if (
                    self.position is None
                    and self.entry_mode == "cross_only"
                    and ema_separation_pct < self.min_ema_separation
                ):
                    log_level = logger.debug if self.context.id == "backtest" else logger.info
                    log_level(
                        f"[{self.context.id}] HOLD: EMA separation too small ({ema_separation_pct:.6f} < {self.min_ema_separation}) | "
                        f"Price: {live_price:.8f} | Fast EMA: {fast_ema:.8f} | Slow EMA: {slow_ema:.8f} | Position: {self.position}"
                    )
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
                    if self.position is None:
                        self._arm_scalping_regime_on_cross_flat(
                            golden_cross, death_cross, last_closed_time
                        )

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
                        if ema_separation_pct < self.min_ema_separation:
                            return StrategySignal(
                                action="HOLD",
                                symbol=self.context.symbol,
                                confidence=0.1,
                                price=live_price,
                            )
                        if not self._passes_entry_filters("LONG", closed_klines, closing_prices, last_closed_time):
                            return StrategySignal(
                                action="HOLD",
                                symbol=self.context.symbol,
                                confidence=0.1,
                                price=live_price
                            )
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
                        self._clear_trend_regime()
                        self._opened_entry_via_trend = False
                        self.position = "LONG"
                        self.entry_price = candle_price  # Use candle close price (will be updated with actual fill price)
                        self.entry_candle_time = last_closed_time  # Track entry candle to prevent EMA exits on same candle
                        self._reset_giveback_state()
                        
                        # Initialize trailing stop if enabled (will be updated with actual entry after fill)
                        if self.trailing_stop_enabled:
                            activation_pct = self.param_float(self.context.params, "trailing_stop_activation_pct", 0.0)
                            self.trailing_stop = TrailingStopManager(
                                entry_price=candle_price,  # Initial estimate, will sync with real entry after fill
                                take_profit_pct=self.take_profit_pct,
                                stop_loss_pct=self.stop_loss_pct,
                                position_type="LONG",
                                enabled=True,
                                activation_pct=activation_pct,
                                trail_step_pct=activation_pct,  # same value: step = activation %
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
                        self._note_position_closed_flat()
                        self.position, self.entry_price, self.entry_candle_time = None, None, None
                        self.trailing_stop = None  # Reset trailing stop
                        self._reset_giveback_state()
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
                        if ema_separation_pct < self.min_ema_separation:
                            return StrategySignal(
                                action="HOLD",
                                symbol=self.context.symbol,
                                confidence=0.1,
                                price=live_price,
                            )
                        if not self._passes_entry_filters("SHORT", closed_klines, closing_prices, last_closed_time):
                            return StrategySignal(
                                action="HOLD",
                                symbol=self.context.symbol,
                                confidence=0.1,
                                price=live_price
                            )
                        if await self._htf_bias_blocks_short_entry_scalping(live_price):
                            return StrategySignal(
                                action="HOLD",
                                symbol=self.context.symbol,
                                confidence=0.1,
                                price=live_price,
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
                        self._clear_trend_regime()
                        self._opened_entry_via_trend = False
                        self.position = "SHORT"
                        self.entry_price = candle_price  # Use candle close price (will be updated with actual fill price)
                        self.entry_candle_time = last_closed_time  # Track entry candle to prevent EMA exits on same candle
                        self._reset_giveback_state()
                        
                        # Initialize trailing stop if enabled (will be updated with actual entry after fill)
                        if self.trailing_stop_enabled:
                            activation_pct = self.param_float(self.context.params, "trailing_stop_activation_pct", 0.0)
                            self.trailing_stop = TrailingStopManager(
                                entry_price=candle_price,  # Initial estimate, will sync with real entry after fill
                                take_profit_pct=self.take_profit_pct,
                                stop_loss_pct=self.stop_loss_pct,
                                position_type="SHORT",
                                enabled=True,
                                activation_pct=activation_pct,
                                trail_step_pct=activation_pct,  # same value: step = activation %
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
                        self._note_position_closed_flat()
                        self.position, self.entry_price, self.entry_candle_time = None, None, None
                        self.trailing_stop = None  # Reset trailing stop
                        self._reset_giveback_state()
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

                    # --- Trend follow-up entries (flat; not same bar as that side's cross) ---
                    if self.entry_mode == "cross_or_trend" and self.position is None:
                        if (
                            not golden_cross
                            and self._entry_regime == "long"
                            and fast_ema > slow_ema
                            and self._trend_followup_window_ok_scalping(closed_klines)
                            and self._trend_entries_used < self.trend_entry_max_per_regime
                            and self._trend_separation_ok_scalping(ema_separation_pct)
                        ):
                            if self._passes_entry_filters("LONG", closed_klines, closing_prices, last_closed_time):
                                log_level = logger.debug if self.context.id == "backtest" else logger.info
                                log_level(
                                    f"[{self.context.id}] [ENTRY_TREND_FOLLOWUP] LONG | "
                                    f"time={last_closed_time} fast={fast_ema:.8f} slow={slow_ema:.8f}"
                                )
                                logger.warning(
                                    f"[{self.context.id}] SIGNAL => BUY (LONG trend follow-up) at {candle_price:.8f} "
                                    f"(candle close, live={live_price:.8f}) candle_time={last_closed_time}"
                                )
                                self._trend_entries_used += 1
                                self._opened_entry_via_trend = True
                                self.position = "LONG"
                                self.entry_price = candle_price
                                self.entry_candle_time = last_closed_time
                                self._reset_giveback_state()
                                if self.trailing_stop_enabled:
                                    activation_pct = self.param_float(
                                        self.context.params, "trailing_stop_activation_pct", 0.0
                                    )
                                    self.trailing_stop = TrailingStopManager(
                                        entry_price=candle_price,
                                        take_profit_pct=self.take_profit_pct,
                                        stop_loss_pct=self.stop_loss_pct,
                                        position_type="LONG",
                                        enabled=True,
                                        activation_pct=activation_pct,
                                        trail_step_pct=activation_pct,
                                    )
                                return StrategySignal(
                                    action="BUY",
                                    symbol=self.context.symbol,
                                    confidence=0.72,
                                    price=candle_price,
                                    exit_reason=None,
                                    position_side="LONG",
                                )
                        if (
                            self.enable_short
                            and not death_cross
                            and self._entry_regime == "short"
                            and fast_ema < slow_ema
                            and self._trend_followup_window_ok_scalping(closed_klines)
                            and self._trend_entries_used < self.trend_entry_max_per_regime
                            and self._trend_separation_ok_scalping(ema_separation_pct)
                        ):
                            if self._passes_entry_filters(
                                "SHORT", closed_klines, closing_prices, last_closed_time
                            ) and not await self._htf_bias_blocks_short_entry_scalping(live_price):
                                log_level = logger.debug if self.context.id == "backtest" else logger.info
                                log_level(
                                    f"[{self.context.id}] [ENTRY_TREND_FOLLOWUP] SHORT | "
                                    f"time={last_closed_time} fast={fast_ema:.8f} slow={slow_ema:.8f}"
                                )
                                logger.warning(
                                    f"[{self.context.id}] SIGNAL => SELL (SHORT trend follow-up) at {candle_price:.8f} "
                                    f"(candle close, live={live_price:.8f}) candle_time={last_closed_time}"
                                )
                                self._trend_entries_used += 1
                                self._opened_entry_via_trend = True
                                self.position = "SHORT"
                                self.entry_price = candle_price
                                self.entry_candle_time = last_closed_time
                                self._reset_giveback_state()
                                if self.trailing_stop_enabled:
                                    activation_pct = self.param_float(
                                        self.context.params, "trailing_stop_activation_pct", 0.0
                                    )
                                    self.trailing_stop = TrailingStopManager(
                                        entry_price=candle_price,
                                        take_profit_pct=self.take_profit_pct,
                                        stop_loss_pct=self.stop_loss_pct,
                                        position_type="SHORT",
                                        enabled=True,
                                        activation_pct=activation_pct,
                                        trail_step_pct=activation_pct,
                                    )
                                return StrategySignal(
                                    action="SELL",
                                    symbol=self.context.symbol,
                                    confidence=0.72,
                                    price=candle_price,
                                    exit_reason=None,
                                    position_side="SHORT",
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
