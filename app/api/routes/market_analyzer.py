from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_binance_client
from app.core.my_binance_client import BinanceClient
from app.strategies.indicators import (
    calculate_ema, 
    calculate_rsi, 
    calculate_atr, 
    calculate_market_structure,
    calculate_volume_analysis
)
from loguru import logger


router = APIRouter(prefix="/market-analyzer", tags=["market-analyzer"])


class MarketAnalysisResponse(BaseModel):
    """Response model for market analysis."""
    symbol: str
    interval: str
    current_price: float
    market_condition: str  # "TRENDING", "SIDEWAYS", "UNCERTAIN", or "UNKNOWN"
    confidence: float  # 0.0 to 0.95 (clamped)
    recommendation: str  # Strategy recommendation
    indicators: dict
    range_info: Optional[dict] = None
    trend_info: dict
    market_structure: Optional[dict] = None  # Market structure analysis (HH/HL or LH/LL)
    volume_analysis: Optional[dict] = None  # Volume analysis metrics


@router.get("/analyze", response_model=MarketAnalysisResponse)
async def analyze_market(
    symbol: str = Query(..., description="Trading symbol (e.g., BTCUSDT)"),
    interval: str = Query("5m", description="Kline interval (1m, 5m, 15m, 1h, etc.)"),
    lookback_period: int = Query(150, description="Number of candles to analyze"),
    ema_fast_period: int = Query(20, description="Fast EMA period"),
    ema_slow_period: int = Query(50, description="Slow EMA period"),
    max_ema_spread_pct: float = Query(0.005, description="Max EMA spread % for sideways (0.5%)"),
    rsi_period: int = Query(14, description="RSI period"),
    swing_period: int = Query(5, description="Swing period for market structure (default 5)"),
    client: BinanceClient = Depends(get_binance_client),
) -> MarketAnalysisResponse:
    """
    Analyze market condition (trending vs sideways) and recommend strategy.
    
    This endpoint:
    - Fetches historical klines from Binance
    - Calculates technical indicators (EMA, RSI, ATR)
    - Determines if market is trending or sideways
    - Recommends appropriate strategy (EMA Scalping or Range Mean Reversion)
    """
    try:
        # Validate parameters
        if max_ema_spread_pct <= 0:
            raise HTTPException(
                status_code=400,
                detail="max_ema_spread_pct must be greater than 0"
            )
        if lookback_period < 50:
            raise HTTPException(
                status_code=400,
                detail="lookback_period must be at least 50"
            )
        if ema_fast_period >= ema_slow_period:
            raise HTTPException(
                status_code=400,
                detail="ema_fast_period must be less than ema_slow_period"
            )
        
        # Get enough klines for analysis
        limit = max(lookback_period + 50, 200)
        klines = client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        
        if not klines or len(klines) < lookback_period + 10:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need at least {lookback_period + 10} candles, got {len(klines) if klines else 0}"
            )
        
        # Get current price
        current_price = client.get_price(symbol)
        
        # Exclude current forming candle
        closed_klines = klines[:-1]
        
        # Extract price data
        closes = [float(k[4]) for k in closed_klines]
        highs = [float(k[2]) for k in closed_klines]
        lows = [float(k[3]) for k in closed_klines]
        
        # Get lookback period data
        lookback_klines = closed_klines[-lookback_period:] if len(closed_klines) >= lookback_period else closed_klines
        lookback_closes = closes[-lookback_period:] if len(closes) >= lookback_period else closes
        lookback_highs = highs[-lookback_period:] if len(highs) >= lookback_period else highs
        lookback_lows = lows[-lookback_period:] if len(lows) >= lookback_period else lows
        
        # Calculate indicators
        fast_ema = calculate_ema(lookback_closes, ema_fast_period)
        slow_ema = calculate_ema(lookback_closes, ema_slow_period)
        rsi = calculate_rsi(lookback_closes, rsi_period)
        atr = calculate_atr(lookback_klines, period=14)
        
        # Calculate market structure
        market_structure = calculate_market_structure(
            highs=lookback_highs,
            lows=lookback_lows,
            swing_period=swing_period
        )
        
        # Calculate volume analysis
        volume_analysis = calculate_volume_analysis(
            klines=lookback_klines,
            period=min(20, len(lookback_klines))
        )
        
        # Calculate range (handle empty lists to avoid ValueError)
        range_high = max(lookback_highs) if lookback_highs else None
        range_low = min(lookback_lows) if lookback_lows else None
        range_size = (range_high - range_low) if (range_high is not None and range_low is not None) else None
        range_mid = ((range_high + range_low) / 2) if (range_high is not None and range_low is not None) else None
        
        # Calculate EMA spread (use is not None to handle 0.0 values correctly)
        ema_spread_pct = None
        if fast_ema is not None and slow_ema is not None and current_price > 0:
            ema_spread_pct = abs(fast_ema - slow_ema) / current_price
        
        # Determine market condition
        market_condition = "UNKNOWN"
        confidence = 0.0
        recommendation = "HOLD - Insufficient data"
        
        # Check if we have enough data (matching documentation: max(ema_slow_period, atr_period, rsi_period, swing_period * 2))
        atr_period = 14
        min_required_candles = max(ema_slow_period, atr_period, rsi_period, swing_period * 2)
        if len(lookback_klines) < min_required_candles:
            # Format market structure and volume analysis if available (even if insufficient for full analysis)
            # Use is not None checks to handle 0.0 values correctly
            formatted_market_structure = None
            if market_structure:
                h = market_structure.get("last_swing_high")
                l = market_structure.get("last_swing_low")
                ph = market_structure.get("previous_swing_high")
                pl = market_structure.get("previous_swing_low")
                formatted_market_structure = {
                    "structure": market_structure.get("structure"),
                    "last_swing_high": round(h, 8) if h is not None else None,
                    "last_swing_low": round(l, 8) if l is not None else None,
                    "previous_swing_high": round(ph, 8) if ph is not None else None,
                    "previous_swing_low": round(pl, 8) if pl is not None else None,
                    "has_higher_high": market_structure.get("has_higher_high"),
                    "has_higher_low": market_structure.get("has_higher_low"),
                    "has_lower_high": market_structure.get("has_lower_high"),
                    "has_lower_low": market_structure.get("has_lower_low"),
                    "swing_high_count": len(market_structure.get("swing_highs", [])),
                    "swing_low_count": len(market_structure.get("swing_lows", [])),
                }
            
            formatted_volume_analysis = None
            if volume_analysis:
                cv = volume_analysis.get("current_volume")
                av = volume_analysis.get("average_volume")
                ve = volume_analysis.get("volume_ema")
                vr = volume_analysis.get("volume_ratio")
                vcp = volume_analysis.get("volume_change_pct")
                formatted_volume_analysis = {
                    "current_volume": round(cv, 2) if cv is not None else None,
                    "average_volume": round(av, 2) if av is not None else None,
                    "volume_ema": round(ve, 2) if ve is not None else None,
                    "volume_ratio": round(vr, 2) if vr is not None else None,
                    "volume_trend": volume_analysis.get("volume_trend"),
                    "volume_change_pct": round(vcp, 2) if vcp is not None else None,
                    "is_high_volume": volume_analysis.get("is_high_volume"),
                    "is_low_volume": volume_analysis.get("is_low_volume"),
                }
            
            return MarketAnalysisResponse(
                symbol=symbol,
                interval=interval,
                current_price=round(current_price, 8),
                market_condition=market_condition,
                confidence=confidence,
                recommendation=recommendation,
                indicators={
                    "fast_ema": round(fast_ema, 8) if fast_ema is not None else None,
                    "slow_ema": round(slow_ema, 8) if slow_ema is not None else None,
                    "rsi": round(rsi, 2) if rsi is not None else None,
                    "rsi_interpretation": "RSI is used for confidence adjustment: healthy trend (45-70), extreme (>75 or <25) reduces confidence" if rsi is not None else None,
                    "atr": round(atr, 8) if atr is not None else None,
                    "ema_spread_pct": round(ema_spread_pct * 100, 4) if ema_spread_pct is not None else None,
                    "ema_spread_abs": round(abs(fast_ema - slow_ema), 8) if (fast_ema is not None and slow_ema is not None) else None,
                    "ema_atr_strength": None,  # Not calculated due to insufficient data
                },
                trend_info={
                    "fast_ema": round(fast_ema, 8) if fast_ema is not None else None,
                    "slow_ema": round(slow_ema, 8) if slow_ema is not None else None,
                    "ema_spread_pct": round(ema_spread_pct * 100, 4) if ema_spread_pct is not None else None,
                    "fast_above_slow": fast_ema > slow_ema if (fast_ema is not None and slow_ema is not None) else None,
                    "trend_direction": "UP" if (fast_ema is not None and slow_ema is not None and fast_ema > slow_ema) else ("DOWN" if (fast_ema is not None and slow_ema is not None and fast_ema < slow_ema) else None),
                    "structure": "UNKNOWN",  # Not enough data
                },
                market_structure=formatted_market_structure,
                volume_analysis=formatted_volume_analysis
            )
        
        # Check if we have enough data for core indicators
        if fast_ema is None or slow_ema is None or rsi is None or atr is None:
            # Format market structure and volume analysis if available (even if core indicators missing)
            # Use is not None checks to handle 0.0 values correctly
            formatted_market_structure_early = None
            if market_structure:
                h = market_structure.get("last_swing_high")
                l = market_structure.get("last_swing_low")
                ph = market_structure.get("previous_swing_high")
                pl = market_structure.get("previous_swing_low")
                formatted_market_structure_early = {
                    "structure": market_structure.get("structure"),
                    "last_swing_high": round(h, 8) if h is not None else None,
                    "last_swing_low": round(l, 8) if l is not None else None,
                    "previous_swing_high": round(ph, 8) if ph is not None else None,
                    "previous_swing_low": round(pl, 8) if pl is not None else None,
                    "has_higher_high": market_structure.get("has_higher_high"),
                    "has_higher_low": market_structure.get("has_higher_low"),
                    "has_lower_high": market_structure.get("has_lower_high"),
                    "has_lower_low": market_structure.get("has_lower_low"),
                    "swing_high_count": len(market_structure.get("swing_highs", [])),
                    "swing_low_count": len(market_structure.get("swing_lows", [])),
                }
            
            formatted_volume_analysis_early = None
            if volume_analysis:
                cv = volume_analysis.get("current_volume")
                av = volume_analysis.get("average_volume")
                ve = volume_analysis.get("volume_ema")
                vr = volume_analysis.get("volume_ratio")
                vcp = volume_analysis.get("volume_change_pct")
                formatted_volume_analysis_early = {
                    "current_volume": round(cv, 2) if cv is not None else None,
                    "average_volume": round(av, 2) if av is not None else None,
                    "volume_ema": round(ve, 2) if ve is not None else None,
                    "volume_ratio": round(vr, 2) if vr is not None else None,
                    "volume_trend": volume_analysis.get("volume_trend"),
                    "volume_change_pct": round(vcp, 2) if vcp is not None else None,
                    "is_high_volume": volume_analysis.get("is_high_volume"),
                    "is_low_volume": volume_analysis.get("is_low_volume"),
                }
            
            return MarketAnalysisResponse(
                symbol=symbol,
                interval=interval,
                current_price=round(current_price, 8),
                market_condition=market_condition,
                confidence=confidence,
                recommendation=recommendation,
                indicators={
                    "fast_ema": round(fast_ema, 8) if fast_ema is not None else None,
                    "slow_ema": round(slow_ema, 8) if slow_ema is not None else None,
                    "rsi": round(rsi, 2) if rsi is not None else None,
                    "rsi_interpretation": "RSI is used for confidence adjustment: healthy trend (45-70), extreme (>75 or <25) reduces confidence" if rsi is not None else None,
                    "atr": round(atr, 8) if atr is not None else None,
                    "ema_spread_pct": round(ema_spread_pct * 100, 4) if ema_spread_pct is not None else None,
                    "ema_spread_abs": round(abs(fast_ema - slow_ema), 8) if (fast_ema is not None and slow_ema is not None) else None,
                    "ema_atr_strength": None,  # Not calculated due to insufficient data
                },
                trend_info={
                    "fast_ema": round(fast_ema, 8) if fast_ema is not None else None,
                    "slow_ema": round(slow_ema, 8) if slow_ema is not None else None,
                    "ema_spread_pct": round(ema_spread_pct * 100, 4) if ema_spread_pct is not None else None,
                    "fast_above_slow": fast_ema > slow_ema if (fast_ema is not None and slow_ema is not None) else None,
                    "trend_direction": "UP" if (fast_ema is not None and slow_ema is not None and fast_ema > slow_ema) else ("DOWN" if (fast_ema is not None and slow_ema is not None and fast_ema < slow_ema) else None),
                    "structure": "UNKNOWN",  # Not enough data for reliable structure
                },
                market_structure=formatted_market_structure_early,
                volume_analysis=formatted_volume_analysis_early
            )
        
        # Voting System for Market Condition Determination
        # Each indicator (EMA, Structure, Volume, Range) casts a vote for TRENDING or SIDEWAYS
        # Classification based on vote count: 3+ votes = Strong, 2 votes = Moderate, 1 vote = Weak
        
        # Extract values for decision logic
        structure_type = market_structure.get("structure") if market_structure else None
        
        # Extract volume_ratio with explicit None guard (avoid TypeError if volume_ratio is None)
        volume_ratio = None
        if volume_analysis:
            vr = volume_analysis.get("volume_ratio")
            if vr is not None:
                volume_ratio = vr
        
        range_atr_ratio = None
        if range_size is not None and atr is not None and atr > 0:
            range_atr_ratio = range_size / atr
        
        # Range/ATR thresholds
        range_atr_trending_threshold = 5.0
        range_atr_sideways_threshold = 2.0
        
        # Initialize signals
        ema_trending_signal = False
        ema_sideways_signal = False
        structure_trending_signal = False
        structure_sideways_signal = False
        volume_trending_signal = False
        volume_sideways_signal = False
        range_trending_signal = False
        range_sideways_signal = False
        
        # 1. EMA Spread Signal
        if ema_spread_pct is not None and max_ema_spread_pct > 0:
            if ema_spread_pct > max_ema_spread_pct:
                ema_trending_signal = True
            else:
                ema_sideways_signal = True
        
        # 2. Market Structure Signal
        if structure_type:
            if structure_type in ("BULLISH", "BEARISH"):
                structure_trending_signal = True
            elif structure_type == "NEUTRAL":
                structure_sideways_signal = True
        
        # 3. Volume Signal
        if volume_ratio is not None:
            if volume_ratio > 1.0:  # Above average volume
                volume_trending_signal = True
            elif volume_ratio < 1.0:  # Below average volume
                volume_sideways_signal = True
        
        # 4. Range/ATR Signal
        if range_atr_ratio is not None:
            if range_atr_ratio >= range_atr_trending_threshold:
                range_trending_signal = True
            elif range_atr_ratio <= range_atr_sideways_threshold:
                range_sideways_signal = True
        
        # Step 1: Count Votes
        # Each indicator casts a vote (True = vote cast, False = no vote)
        trending_votes = sum([
            ema_trending_signal,
            structure_trending_signal,
            volume_trending_signal,
            range_trending_signal
        ])
        
        sideways_votes = sum([
            ema_sideways_signal,
            structure_sideways_signal,
            volume_sideways_signal,
            range_sideways_signal
        ])
        
        # Step 2: Classification Based on Vote Count
        is_trending = False
        is_sideways = False
        
        # Exact tie (2 vs 2) → Will be handled as UNCERTAIN in final determination
        # Strong TRENDING: At least 3 out of 4 signals agree
        if trending_votes >= 3:
            is_trending = True
            confidence = 0.5 + (trending_votes / 4.0) * 0.4  # 0.5 to 0.9 base
        # Strong SIDEWAYS: At least 3 out of 4 signals agree
        elif sideways_votes >= 3:
            is_sideways = True
            confidence = 0.5 + (sideways_votes / 4.0) * 0.4  # 0.5 to 0.9 base
        # Moderate TRENDING: EMA + Structure agree (most important)
        elif ema_trending_signal and structure_trending_signal:
            is_trending = True
            confidence = 0.6 + (trending_votes / 4.0) * 0.25  # 0.6 to 0.85
        # Moderate SIDEWAYS: EMA + Structure agree
        elif ema_sideways_signal and structure_sideways_signal:
            is_sideways = True
            confidence = 0.6 + (sideways_votes / 4.0) * 0.25  # 0.6 to 0.85
        # Weak TRENDING: Only EMA suggests trending
        elif ema_trending_signal and not ema_sideways_signal:
            is_trending = True
            confidence = 0.5 + (trending_votes / 4.0) * 0.3  # 0.5 to 0.8
        # Weak SIDEWAYS: Only EMA suggests sideways
        elif ema_sideways_signal and not ema_trending_signal:
            is_sideways = True
            confidence = 0.5 + (sideways_votes / 4.0) * 0.3  # 0.5 to 0.8
        
        # RSI Integration for confidence adjustment
        rsi_adjustment = 0.0
        rsi_confirmation = None
        if rsi is not None:
            if is_trending:
                # RSI in healthy trend range (45-70) confirms trend
                if 45 <= rsi <= 70:
                    rsi_adjustment = 0.03
                    rsi_confirmation = "RSI in healthy trend range"
                # RSI extreme (>75 or <25) suggests trend exhaustion
                elif rsi > 75 or rsi < 25:
                    rsi_adjustment = -0.05
                    rsi_confirmation = "RSI extreme - trend may be exhausted"
            elif is_sideways:
                # RSI neutral (45-55) confirms range
                if 45 <= rsi <= 55:
                    rsi_adjustment = 0.03
                    rsi_confirmation = "RSI neutral - confirms range"
        
        # Apply RSI adjustment
        confidence = confidence + rsi_adjustment
        
        # Clamp confidence between 0.0 and 0.95
        confidence = max(0.0, min(0.95, confidence))
        
        # Build confirmation messages
        confirmations = []
        if structure_trending_signal and is_trending:
            confirmations.append("Market structure confirms trending")
        elif structure_sideways_signal and is_sideways:
            confirmations.append("Market structure confirms sideways")
        
        if volume_analysis:
            if volume_analysis.get("is_high_volume") and is_trending:
                confirmations.append("High volume confirms trending")
            elif volume_analysis.get("is_low_volume") and is_sideways:
                confirmations.append("Low volume confirms sideways")
            elif volume_analysis.get("volume_trend") == "INCREASING" and is_trending:
                confirmations.append("Increasing volume supports trend")
            elif volume_analysis.get("volume_trend") == "DECREASING" and is_trending:
                confirmations.append("Decreasing volume - trend weakening")
        
        if rsi_confirmation:
            confirmations.append(rsi_confirmation)
        
        confirmation_text = f" ({', '.join(confirmations)})" if confirmations else ""
        
        # Final determination
        # Check for exact tie first (2 vs 2 votes) - matches documentation
        if trending_votes == 2 and sideways_votes == 2:
            market_condition = "UNCERTAIN"
            recommendation = "Monitor market - Conditions unclear, wait for clearer signals"
            confidence = 0.3
        elif is_trending and not is_sideways:
            market_condition = "TRENDING"
            recommendation = "EMA Scalping Strategy - Market is trending, use EMA crossover signals" + confirmation_text
        elif is_sideways and not is_trending:
            market_condition = "SIDEWAYS"
            recommendation = "Range Mean Reversion Strategy - Market is ranging, trade between support/resistance" + confirmation_text
        elif is_trending and is_sideways:
            # Conflicting signals - use EMA spread as primary
            if ema_spread_pct is not None and max_ema_spread_pct > 0 and ema_spread_pct > max_ema_spread_pct:
                market_condition = "TRENDING"
                recommendation = "EMA Scalping Strategy - Market shows trending characteristics" + confirmation_text
            else:
                market_condition = "SIDEWAYS"
                recommendation = "Range Mean Reversion Strategy - Market shows ranging characteristics" + confirmation_text
        else:
            market_condition = "UNCERTAIN"
            recommendation = "Monitor market - Conditions unclear, wait for clearer signals"
            confidence = 0.3
        
        # Calculate EMA/ATR strength (for cross-symbol consistency, documented but not used in decision)
        # Use is not None checks to handle 0.0 values correctly
        ema_atr_strength = None
        if fast_ema is not None and slow_ema is not None and atr is not None and atr > 0:
            ema_atr_strength = abs(fast_ema - slow_ema) / atr
        
        # Build indicators dict (include EMA/ATR strength for reference)
        # Use is not None checks to handle 0.0 values correctly
        indicators = {
            "fast_ema": round(fast_ema, 8) if fast_ema is not None else None,
            "slow_ema": round(slow_ema, 8) if slow_ema is not None else None,
            "rsi": round(rsi, 2) if rsi is not None else None,
            "rsi_interpretation": "RSI is used for confidence adjustment: healthy trend (45-70), extreme (>75 or <25) reduces confidence" if rsi is not None else None,
            "atr": round(atr, 8) if atr is not None else None,
            "ema_spread_pct": round(ema_spread_pct * 100, 4) if ema_spread_pct is not None else None,  # Convert to percentage
            "ema_spread_abs": round(abs(fast_ema - slow_ema), 8) if (fast_ema is not None and slow_ema is not None) else None,
            "ema_atr_strength": round(ema_atr_strength, 4) if ema_atr_strength is not None else None,  # For cross-symbol consistency reference
        }
        
        # Build trend info (include structure for context)
        # Use is not None checks to handle 0.0 values correctly
        trend_info = {
            "fast_ema": round(fast_ema, 8) if fast_ema is not None else None,
            "slow_ema": round(slow_ema, 8) if slow_ema is not None else None,
            "ema_spread_pct": round(ema_spread_pct * 100, 4) if ema_spread_pct is not None else None,
            "fast_above_slow": fast_ema > slow_ema if (fast_ema is not None and slow_ema is not None) else None,
            "trend_direction": "UP" if (fast_ema is not None and slow_ema is not None and fast_ema > slow_ema) else ("DOWN" if (fast_ema is not None and slow_ema is not None and fast_ema < slow_ema) else None),
            "structure": structure_type if structure_type else "UNKNOWN",
        }
        
        # Build range info (include thresholds for clarity)
        # Use is not None checks to handle 0.0 values correctly
        range_info = None
        if (
            range_high is not None 
            and range_low is not None 
            and range_size is not None 
            and range_mid is not None
        ):
            range_atr_ratio_for_info = round(range_size / atr, 2) if (atr is not None and atr > 0) else None
            range_info = {
                "range_high": round(range_high, 8),
                "range_low": round(range_low, 8),
                "range_mid": round(range_mid, 8),
                "range_size": round(range_size, 8),
                "range_size_pct": round((range_size / range_mid) * 100, 2) if range_mid > 0 else None,
                "current_price_in_range": round(((current_price - range_low) / range_size) * 100, 2) if range_size > 0 else None,
                "atr_ratio": range_atr_ratio_for_info,
                "atr_ratio_trending_threshold": 5.0,
                "atr_ratio_sideways_threshold": 2.0,
            }
        
        # Format market structure for response
        # Use is not None checks to handle 0.0 values correctly
        formatted_market_structure = None
        if market_structure:
            h = market_structure.get("last_swing_high")
            l = market_structure.get("last_swing_low")
            ph = market_structure.get("previous_swing_high")
            pl = market_structure.get("previous_swing_low")
            formatted_market_structure = {
                "structure": market_structure.get("structure"),
                "last_swing_high": round(h, 8) if h is not None else None,
                "last_swing_low": round(l, 8) if l is not None else None,
                "previous_swing_high": round(ph, 8) if ph is not None else None,
                "previous_swing_low": round(pl, 8) if pl is not None else None,
                "has_higher_high": market_structure.get("has_higher_high"),
                "has_higher_low": market_structure.get("has_higher_low"),
                "has_lower_high": market_structure.get("has_lower_high"),
                "has_lower_low": market_structure.get("has_lower_low"),
                "swing_high_count": len(market_structure.get("swing_highs", [])),
                "swing_low_count": len(market_structure.get("swing_lows", [])),
            }
        
        # Format volume analysis for response
        # Use is not None checks to handle 0.0 values correctly
        formatted_volume_analysis = None
        if volume_analysis:
            cv = volume_analysis.get("current_volume")
            av = volume_analysis.get("average_volume")
            ve = volume_analysis.get("volume_ema")
            vr = volume_analysis.get("volume_ratio")
            vcp = volume_analysis.get("volume_change_pct")
            formatted_volume_analysis = {
                "current_volume": round(cv, 2) if cv is not None else None,
                "average_volume": round(av, 2) if av is not None else None,
                "volume_ema": round(ve, 2) if ve is not None else None,
                "volume_ratio": round(vr, 2) if vr is not None else None,
                "volume_trend": volume_analysis.get("volume_trend"),
                "volume_change_pct": round(vcp, 2) if vcp is not None else None,
                "is_high_volume": volume_analysis.get("is_high_volume"),
                "is_low_volume": volume_analysis.get("is_low_volume"),
            }
        
        return MarketAnalysisResponse(
            symbol=symbol,
            interval=interval,
            current_price=round(current_price, 8),
            market_condition=market_condition,
            confidence=round(confidence, 2),
            recommendation=recommendation,
            indicators=indicators,
            range_info=range_info,
            trend_info=trend_info,
            market_structure=formatted_market_structure,
            volume_analysis=formatted_volume_analysis,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error analyzing market for {symbol}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing market: {str(e)}"
        )

