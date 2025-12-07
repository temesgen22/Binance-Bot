# Market Analyzer Documentation

## Overview

The **Market Analyzer** is a tool that analyzes cryptocurrency markets to determine whether they are **trending** or **sideways** (ranging). Based on this analysis, it recommends the appropriate trading strategy:

- **TRENDING markets** → Use **EMA Scalping Strategy**
- **SIDEWAYS markets** → Use **Range Mean Reversion Strategy**

## How It Works

The Market Analyzer uses a multi-indicator approach to determine market conditions:

### 1. Data Collection
- Fetches historical candlestick data (klines) from Binance
- Analyzes the last N candles (lookback period)
- Excludes the current forming candle (uses only closed candles)

### 2. Indicator Calculation
The analyzer calculates several technical indicators:

#### **EMA (Exponential Moving Average)**
- **Fast EMA**: 20-period EMA (default)
- **Slow EMA**: 50-period EMA (default)
- **Purpose**: Measures trend direction and strength
- **Calculation**: Uses standard EMA formula with smoothing factor

#### **RSI (Relative Strength Index)**
- **Period**: 14 candles (default)
- **Purpose**: Measures momentum and overbought/oversold conditions
- **Scale**: 0-100
  - RSI < 30: Oversold (potential buy signal)
  - RSI 30-70: Neutral
  - RSI > 70: Overbought (potential sell signal)

#### **ATR (Average True Range)**
- **Period**: 14 candles (default)
- **Purpose**: Measures market volatility
- **Calculation**: Average of True Range over the period
- **True Range**: Maximum of:
  - Current High - Current Low
  - |Current High - Previous Close|
  - |Current Low - Previous Close|

#### **Price Range**
- **Range High**: Maximum price in lookback period
- **Range Low**: Minimum price in lookback period
- **Range Mid**: (Range High + Range Low) / 2
- **Range Size**: Range High - Range Low

#### **Volume Analysis**
- **Current Volume**: Volume of the most recent candle
- **Average Volume**: Simple average of volumes over the period (default 20)
- **Volume EMA**: Exponential Moving Average of volumes
- **Volume Ratio**: Current volume / Average volume
  - Ratio > 1.5: High volume (confirms trending moves)
  - Ratio < 0.5: Low volume (suggests weak moves, may be sideways)
  - Ratio 0.5-1.5: Normal volume
- **Volume Trend**: INCREASING, DECREASING, or STABLE
  - Compares current period average to previous period average
- **Volume Change %**: Percentage change in volume between periods

#### **Market Structure (HH/HL or LH/LL)**
- **Purpose**: Identifies trend direction by analyzing swing highs and swing lows
- **Swing Period**: Number of candles to look back/forward to identify swing points (default: 5)
- **Patterns**:
  - **HH/HL (Higher High / Higher Low)**: Bullish structure (uptrend)
    - Last swing high > Previous swing high
    - Last swing low > Previous swing low
  - **LH/LL (Lower High / Lower Low)**: Bearish structure (downtrend)
    - Last swing high < Previous swing high
    - Last swing low < Previous swing low
  - **NEUTRAL**: Mixed signals or insufficient swing points
- **Calculation**: 
  - Identifies swing highs (local maximums) and swing lows (local minimums)
  - Compares consecutive swing points to determine structure

### 3. Market Condition Determination

The analyzer uses a **voting system** where each indicator casts a vote for TRENDING or SIDEWAYS, then classifies based on the vote count.

#### **Step 1: Voting System**

Each of the four indicators casts a vote:

1. **EMA Spread Signal**
   - **TRENDING vote**: EMA spread > `max_ema_spread_pct` (default 0.5%)
   - **SIDEWAYS vote**: EMA spread ≤ `max_ema_spread_pct`

2. **Market Structure Signal**
   - **TRENDING vote**: Structure is BULLISH or BEARISH
   - **SIDEWAYS vote**: Structure is NEUTRAL

3. **Volume Signal**
   - **TRENDING vote**: Volume ratio > 1.0 (above average)
   - **SIDEWAYS vote**: Volume ratio < 1.0 (below average)

4. **Range/ATR Signal**
   - **TRENDING vote**: Range/ATR ratio >= 5.0
   - **SIDEWAYS vote**: Range/ATR ratio <= 2.0
   - **No vote**: 2.0 < Ratio < 5.0 (neutral zone)

#### **Step 2: Classification**

Based on vote count:

- **Strong TRENDING**: 3+ out of 4 signals vote TRENDING → Confidence 0.5-0.9
- **Strong SIDEWAYS**: 3+ out of 4 signals vote SIDEWAYS → Confidence 0.5-0.9
- **Moderate TRENDING**: EMA + Structure both vote TRENDING → Confidence 0.6-0.85
- **Moderate SIDEWAYS**: EMA + Structure both vote SIDEWAYS → Confidence 0.6-0.85
- **Weak TRENDING**: Only EMA votes TRENDING (others missing/neutral) → Confidence 0.5-0.8
- **Weak SIDEWAYS**: Only EMA votes SIDEWAYS (others missing/neutral) → Confidence 0.5-0.8
- **UNCERTAIN**: 2 vs 2 votes, or conflicting signals → Confidence set to 0.3 (low but not zero)
- **UNKNOWN**: Not enough data to calculate indicators (see data requirements below)

#### **Typical Strong Cases**

A typical **strong TRENDING** classification happens when all four signals agree:
- EMA spread > threshold
- Market Structure is BULLISH or BEARISH
- Volume ratio > 1.0
- Range/ATR ratio >= 5.0

A typical **strong SIDEWAYS** classification happens when all four signals agree:
- EMA spread ≤ threshold
- Market Structure is NEUTRAL
- Volume ratio < 1.0
- Range/ATR ratio <= 2.0

**Data Requirements for UNKNOWN:**
If there are not enough candles to compute EMA, ATR, volume, and market structure (e.g., less than `max(ema_slow_period, atr_period, rsi_period, swing_period * 2)`), the market condition is set to **UNKNOWN**.

### 4. RSI Integration

RSI is used for **confidence adjustment** (not for initial classification):

- **Healthy Trend Range (45-70)**: Confirms trend
  - If market is trending: +0.03 confidence
  - Indicates sustainable momentum

- **Extreme RSI (>75 or <25)**: Suggests trend exhaustion
  - If market is trending: -0.05 confidence
  - May indicate overbought/oversold conditions

- **Neutral RSI (45-55)**: Confirms range
  - If market is sideways: +0.03 confidence
  - Indicates balanced conditions

**Note**: RSI does not affect the initial TRENDING/SIDEWAYS classification, only confidence adjustment.

### 5. Volume Analysis

The analyzer uses Volume Analysis as part of the voting system:

- **Volume Signal Voting**:
  - **TRENDING vote**: Volume ratio > 1.0 (above average)
  - **SIDEWAYS vote**: Volume ratio < 1.0 (below average)
  - Volume is one of the 4 indicators that vote for market condition

- **Volume Interpretation**:
  - **High Volume (>1.5x average)**: Strong confirmation of trending moves
  - **Low Volume (<0.5x average)**: Suggests weak moves or potential sideways market
  - **Increasing Volume**: Supports trend continuation
  - **Decreasing Volume**: Trend may be weakening

**Note**: Volume affects the initial classification through voting, not just confidence adjustment.

### 6. Market Structure Analysis

The analyzer uses Market Structure as part of the voting system:

- **Market Structure Signal Voting**:
  - **TRENDING vote**: Structure is BULLISH or BEARISH
  - **SIDEWAYS vote**: Structure is NEUTRAL
  - Market Structure is one of the 4 indicators that vote for market condition

- **Structure Interpretation**:
  - **BULLISH Structure (HH/HL)**: Higher High and Higher Low pattern indicates uptrend
  - **BEARISH Structure (LH/LL)**: Lower High and Lower Low pattern indicates downtrend
  - **NEUTRAL Structure**: Mixed signals or insufficient swing points, suggests sideways market

**Note**: Market Structure affects the initial classification through voting. It's particularly important as it's checked alongside EMA for moderate classifications.

### 7. Confidence Calculation

The analyzer provides a confidence score (0.0 to 0.95) based on:

1. **Base Confidence from Voting**:
   - Strong agreement (3+ votes): 0.5 to 0.9
   - Moderate agreement (EMA + Structure): 0.6 to 0.85
   - Weak agreement (EMA only): 0.5 to 0.8

2. **RSI Adjustment**:
   - Healthy trend range (45-70): +0.03
   - Extreme RSI (>75 or <25): -0.05
   - Neutral RSI (45-55) with sideways: +0.03

3. **Final Clamping**:
   - After all adjustments, confidence is clamped between **0.0 and 0.95**
   - **UNCERTAIN conditions**: Confidence is set to 0.3 (low but not zero)

### 8. Final Recommendation

Based on the analysis:
- **TRENDING** → "EMA Scalping Strategy - Market is trending, use EMA crossover signals"
- **SIDEWAYS** → "Range Mean Reversion Strategy - Market is ranging, trade between support/resistance"
- **UNCERTAIN** → "Monitor market - Conditions unclear, wait for clearer signals"

---

## Default Parameters

### API Endpoint Parameters

| Parameter | Default | Description | Valid Range |
|-----------|---------|-------------|-------------|
| `symbol` | Required | Trading symbol (e.g., BTCUSDT) | Any valid Binance symbol |
| `interval` | `"5m"` | Candlestick interval | 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d |
| `lookback_period` | `150` | Number of candles to analyze | 50-500 |
| `ema_fast_period` | `20` | Fast EMA period | 1-200 |
| `ema_slow_period` | `50` | Slow EMA period | 1-200 |
| `max_ema_spread_pct` | `0.005` | Max EMA spread % for sideways (0.5%) | > 0 |
| `rsi_period` | `14` | RSI calculation period | 1-50 |
| `swing_period` | `5` | Swing period for market structure | 3-20 |

### Internal Calculation Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `atr_period` | `14` | ATR calculation period (fixed) |
| `range_atr_trending_threshold` | `5.0` | Range/ATR ratio >= this value indicates trending |
| `range_atr_sideways_threshold` | `2.0` | Range/ATR ratio <= this value indicates sideways |
| `confidence_min` | `0.0` | Minimum confidence score (after clamping) |
| `confidence_max` | `0.95` | Maximum confidence score (after clamping) |
| `volume_trending_threshold` | `1.0` | Volume ratio > this indicates trending |
| `volume_sideways_threshold` | `1.0` | Volume ratio < this indicates sideways |

---

## Parameter Explanations

### `lookback_period` (Default: 150)
- **What it does**: Determines how many historical candles to analyze
- **Impact**: 
  - Larger values = More stable but slower to detect changes
  - Smaller values = More responsive but more noise
- **Example**: 
  - 150 candles at 5m interval = 12.5 hours of data
  - 150 candles at 1h interval = 6.25 days of data

### `ema_fast_period` (Default: 20)
- **What it does**: Period for the fast-moving EMA
- **Impact**: 
  - Smaller values = More sensitive to price changes
  - Larger values = Smoother, less sensitive
- **Typical values**: 8-21 for scalping, 20-50 for swing trading

### `ema_slow_period` (Default: 50)
- **What it does**: Period for the slow-moving EMA
- **Impact**: 
  - Must be greater than `ema_fast_period`
  - Larger values = More stable trend indicator
- **Typical values**: 21-50 for scalping, 50-200 for swing trading

### `max_ema_spread_pct` (Default: 0.005 = 0.5%)
- **What it does**: Threshold for determining if market is trending
- **Impact**: 
  - Smaller values = More likely to detect trending (stricter)
  - Larger values = More likely to detect sideways (looser)
- **Example**: 
  - 0.005 (0.5%) = If EMAs differ by more than 0.5% of price → Trending
  - 0.01 (1.0%) = If EMAs differ by more than 1.0% of price → Trending

### `rsi_period` (Default: 14)
- **What it does**: Period for RSI calculation
- **Impact**: 
  - Standard RSI period is 14
  - Smaller values = More sensitive
  - Larger values = Smoother

### `interval` (Default: "5m")
- **What it does**: Timeframe for candlestick data
- **Impact**: 
  - Shorter intervals (1m, 5m) = More signals, more noise
  - Longer intervals (1h, 4h) = Fewer signals, more reliable
- **Recommended**: 
  - Scalping: 1m, 5m
  - Swing trading: 15m, 1h, 4h

### `swing_period` (Default: 5)
- **What it does**: Number of candles to look back/forward to identify swing points for market structure
- **Impact**: 
  - Smaller values (3-5) = More swing points, more sensitive
  - Larger values (7-10) = Fewer swing points, more stable
- **How it works**: 
  - A swing high is a high that is higher than N candles before and after
  - A swing low is a low that is lower than N candles before and after
- **Recommended**: 
  - Fast markets: 3-5
  - Normal markets: 5-7
  - Slow markets: 7-10

---

## Calculation Formulas

### EMA Spread Percentage
```
EMA Spread % = |Fast EMA - Slow EMA| / Current Price
```

**Example:**
- Fast EMA: $41,200
- Slow EMA: $41,180
- Current Price: $41,190
- EMA Spread: |$41,200 - $41,180| / $41,190 = 0.0485% (0.000485)

### EMA/ATR Strength (Optional)
```
EMA/ATR Strength = |Fast EMA - Slow EMA| / ATR
```

This measures EMA separation relative to volatility (ATR) for cross-symbol consistency.

**Interpretation:**
- **Values > 1.0**: EMA separation larger than current ATR (very strong trend)
- **Values 0.5–1.0**: Moderate trend strength
- **Values < 0.5**: Weak trend relative to volatility

**Example:**
- Fast EMA: $41,200
- Slow EMA: $41,180
- ATR: $500
- EMA/ATR Strength: |$41,200 - $41,180| / $500 = 0.04 (4% of ATR)

**Note**: This metric is calculated for reference but is not used in the voting system decision logic.

### Range-to-ATR Ratio
```
Range/ATR Ratio = (Range High - Range Low) / ATR
```

**Example:**
- Range High: $42,500
- Range Low: $40,000
- Range Size: $2,500
- ATR: $500
- Ratio: $2,500 / $500 = 5.0

### Volume Analysis
```
Average Volume = Mean of volumes over period (default 20)
Volume EMA = EMA of volumes over period
Volume Ratio = Current Volume / Average Volume

Volume Trend:
- Compare current period average to previous period average
- Change % = ((Current Avg - Previous Avg) / Previous Avg) * 100
- INCREASING: Change > 5%
- DECREASING: Change < -5%
- STABLE: -5% ≤ Change ≤ 5%

High Volume: Ratio > 1.5 (50% above average)
Low Volume: Ratio < 0.5 (50% below average)
```

**Example:**
- Current Volume: 1,250,000
- Average Volume: 800,000
- Volume Ratio: 1,250,000 / 800,000 = 1.56x (High Volume ✅)
- Previous Period Avg: 700,000
- Current Period Avg: 800,000
- Change: ((800,000 - 700,000) / 700,000) * 100 = 14.3% (INCREASING ✅)
- **Result**: High volume with increasing trend - Strong confirmation

### Market Structure
```
Swing High: High that is higher than N candles before and after
Swing Low: Low that is lower than N candles before and after

BULLISH (HH/HL):
- Last Swing High > Previous Swing High (Higher High)
- Last Swing Low > Previous Swing Low (Higher Low)

BEARISH (LH/LL):
- Last Swing High < Previous Swing High (Lower High)
- Last Swing Low < Previous Swing Low (Lower Low)
```

**Example:**
- Previous Swing High: $42,000
- Last Swing High: $42,500 (Higher High ✅)
- Previous Swing Low: $40,000
- Last Swing Low: $40,200 (Higher Low ✅)
- **Result**: BULLISH structure (HH/HL pattern)

### Confidence Score Calculation

Confidence is calculated using a **voting-based system** with RSI adjustments:

**Step 1: Base Confidence from Voting**
- **Strong agreement (3+ votes)**: 0.5 to 0.9
- **Moderate agreement (EMA + Structure)**: 0.6 to 0.85
- **Weak agreement (EMA only)**: 0.5 to 0.8

**Step 2: RSI Adjustment**
- Healthy trend range (45-70): +0.03
- Extreme RSI (>75 or <25): -0.05
- Neutral RSI (45-55) with sideways: +0.03

**Step 3: Final Clamping**
- After all adjustments, confidence is clamped between **0.0 and 0.95**

**Example:**
- 3 TRENDING votes → Base confidence: 0.7
- RSI = 58 (healthy trend) → +0.03 → 0.73
- Final confidence: 0.73 (within 0.0-0.95 range)

---

## Usage Examples

### Example 1: Basic Analysis (Default Parameters)
```bash
GET /market-analyzer/analyze?symbol=BTCUSDT
```

**Response:**
```json
{
  "symbol": "BTCUSDT",
  "interval": "5m",
  "current_price": 41250.50,
  "market_condition": "TRENDING",
  "confidence": 0.85,
  "recommendation": "EMA Scalping Strategy - Market is trending, use EMA crossover signals",
  "indicators": {
    "fast_ema": 41200.25,
    "slow_ema": 41180.10,
    "rsi": 55.5,
    "rsi_interpretation": "RSI is used for confidence adjustment: healthy trend (45-70), extreme (>75 or <25) reduces confidence",
    "atr": 500.25,
    "ema_spread_pct": 0.0485,
    "ema_spread_abs": 20.15,
    "ema_atr_strength": 0.04
  },
  "trend_info": {
    "fast_ema": 41200.25,
    "slow_ema": 41180.10,
    "ema_spread_pct": 0.0485,
    "fast_above_slow": true,
    "trend_direction": "UP",
    "structure": "BULLISH"
  },
  "range_info": {
    "range_high": 42500.00,
    "range_low": 40000.00,
    "range_mid": 41250.00,
    "range_size": 2500.00,
    "range_size_pct": 6.06,
    "current_price_in_range": 50.00,
    "atr_ratio": 5.0,
    "atr_ratio_trending_threshold": 5.0,
    "atr_ratio_sideways_threshold": 2.0
  },
  "market_structure": {
    "structure": "BULLISH",
    "last_swing_high": 42500.00,
    "last_swing_low": 40200.00,
    "previous_swing_high": 42000.00,
    "previous_swing_low": 40000.00,
    "has_higher_high": true,
    "has_higher_low": true,
    "has_lower_high": false,
    "has_lower_low": false,
    "swing_high_count": 3,
    "swing_low_count": 3
  },
  "volume_analysis": {
    "current_volume": 1250000.50,
    "average_volume": 800000.25,
    "volume_ema": 850000.75,
    "volume_ratio": 1.56,
    "volume_trend": "INCREASING",
    "volume_change_pct": 12.5,
    "is_high_volume": true,
    "is_low_volume": false
  }
}
```

### Example 2: Custom Parameters
```bash
GET /market-analyzer/analyze?symbol=ETHUSDT&interval=15m&lookback_period=200&ema_fast_period=20&ema_slow_period=50&max_ema_spread_pct=0.003
```

**Parameters:**
- Symbol: ETHUSDT
- Interval: 15 minutes
- Lookback: 200 candles (50 hours)
- EMA Fast: 20
- EMA Slow: 50
- Max EMA Spread: 0.3% (stricter threshold)

### Example 3: Using the GUI

1. Navigate to: `http://127.0.0.1:8000/market-analyzer`
2. Enter symbol: `BTCUSDT`
3. Select interval: `5m`
4. Set lookback: `150`
5. Click "Analyze Market"

---

## Understanding the Results

### Market Condition Values

- **TRENDING**: Market is moving in a clear direction (up or down)
  - **Classification**: At least 3 out of 4 signals vote TRENDING
  - **Typically**: EMA spread > threshold, structure is BULLISH/BEARISH, volume above average (ratio > 1.0), Range/ATR >= 5.0
  - **Action**: Use EMA Scalping Strategy

- **SIDEWAYS**: Market is moving within a range
  - **Classification**: At least 3 out of 4 signals vote SIDEWAYS
  - **Typically**: EMA spread ≤ threshold, structure is NEUTRAL, volume below average (ratio < 1.0), Range/ATR <= 2.0
  - **Action**: Use Range Mean Reversion Strategy

- **UNCERTAIN**: Market signals are conflicting
  - **Classification**: Mixed votes (2 vs 2) or weak EMA-only signal
  - **Confidence**: Set to 0.3 (low but not zero)
  - **Action**: Wait for clearer signals

- **UNKNOWN**: Insufficient data
  - **Classification**: Not enough candles to calculate indicators
  - **Requirement**: Need at least `max(ema_slow_period, atr_period, rsi_period, swing_period * 2)` candles
  - **Action**: Wait for more data

### Confidence Score

- **0.0 - 0.3**: Low confidence, uncertain conditions
- **0.4 - 0.6**: Moderate confidence
- **0.7 - 0.9**: High confidence
- **0.9 - 0.95**: Very high confidence

### Indicator Interpretation

#### EMA Spread
- **< 0.3%**: Very tight, likely sideways
- **0.3% - 0.5%**: Moderate spread. With the default threshold (0.5%), this still votes SIDEWAYS, but it's close to a potential trend
- **> 0.5%**: Wide spread, votes TRENDING (with default threshold)

#### RSI
- **< 30**: Oversold, potential buy opportunity (extreme - reduces confidence if trending)
- **30-45**: Lower neutral zone
- **45-55**: Neutral zone (confirms sideways markets)
- **55-70**: Upper neutral zone (healthy trend range - confirms trending)
- **70-75**: Overbought zone
- **> 75**: Extremely overbought (extreme - reduces confidence if trending)

**Note**: RSI is used for confidence adjustment, not for initial market condition classification.

#### ATR
- **High ATR**: High volatility, larger price swings
- **Low ATR**: Low volatility, smaller price swings

#### Range Information
- **Range Size %**: Percentage of range relative to midpoint
  - Small (< 2%): Tight range, good for mean reversion
  - Large (> 5%): Wide range, may indicate trending
- **Range/ATR Ratio Thresholds**:
  - **Trending**: Ratio >= 5.0 (range is too wide, likely trending)
  - **Sideways**: Ratio <= 2.0 (range is reasonable, likely ranging)
  - **Neutral**: 2.0 < Ratio < 5.0 (no strong signal, no vote cast)
- **Current Price in Range**: Position of current price within range
  - 0%: At range low (support)
  - 50%: At range midpoint
  - 100%: At range high (resistance)

#### Market Structure
- **BULLISH (HH/HL)**: Higher High and Higher Low pattern
  - Indicates uptrend
  - Confirms trending market condition
  - Use EMA Scalping Strategy for long positions
  
- **BEARISH (LH/LL)**: Lower High and Lower Low pattern
  - Indicates downtrend
  - Confirms trending market condition
  - Use EMA Scalping Strategy for short positions
  
- **NEUTRAL**: Mixed signals or insufficient swing points
  - Market structure unclear
  - May indicate sideways market
  - Wait for clearer signals

#### Volume Analysis
- **High Volume (>1.5x average)**: Strong confirmation
  - Confirms trending moves
  - Increases confidence in market direction
  - Indicates strong conviction
  
- **Low Volume (<0.5x average)**: Weak signal
  - Suggests weak moves or potential sideways market
  - Decreases confidence in trending signals
  - May indicate lack of interest
  
- **Increasing Volume**: Trend continuation signal
  - Supports ongoing trend
  - Growing interest in the direction
  - Positive for trend strength
  
- **Decreasing Volume**: Trend weakening signal
  - Suggests trend losing momentum
  - May indicate upcoming reversal or consolidation
  - Reduces confidence in trend

---

## Best Practices

### 1. Choose Appropriate Timeframe
- **Scalping**: Use 1m or 5m intervals
- **Day Trading**: Use 15m or 30m intervals
- **Swing Trading**: Use 1h or 4h intervals

### 2. Adjust Lookback Period
- **Volatile Markets**: Use longer lookback (200-300)
- **Stable Markets**: Use shorter lookback (100-150)

### 3. Tune EMA Spread Threshold
- **Stricter Detection**: Lower `max_ema_spread_pct` (0.003 = 0.3%)
- **Looser Detection**: Higher `max_ema_spread_pct` (0.01 = 1.0%)

### 4. Verify with Multiple Timeframes
- Check 5m, 15m, and 1h to confirm market condition
- Higher timeframes provide more reliable signals

### 5. Consider Market Context
- News events can cause temporary trending
- Low volume periods may show false sideways signals
- Always verify with price action

---

## Troubleshooting

### Issue: "Insufficient data" Error
**Cause**: Not enough candles for the lookback period
**Solution**: 
- Reduce `lookback_period` (minimum 50)
- Use a longer `interval` (e.g., 1h instead of 5m)

### Issue: Low Confidence Scores
**Cause**: Conflicting signals between EMA and Range analysis
**Solution**:
- Increase `lookback_period` for more stable analysis
- Check multiple timeframes
- Wait for clearer market conditions

### Issue: Incorrect Market Condition
**Cause**: Parameters may not be suitable for current market
**Solution**:
- Adjust `max_ema_spread_pct` threshold
- Try different `interval` values
- Verify with manual chart analysis

---

## API Reference

### Endpoint
```
GET /market-analyzer/analyze
```

### Query Parameters
All parameters are optional except `symbol`:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | Yes | - | Trading symbol (e.g., BTCUSDT) |
| `interval` | string | No | "5m" | Kline interval |
| `lookback_period` | integer | No | 150 | Number of candles |
| `ema_fast_period` | integer | No | 20 | Fast EMA period |
| `ema_slow_period` | integer | No | 50 | Slow EMA period |
| `max_ema_spread_pct` | float | No | 0.005 | Max EMA spread (0.5%) |
| `rsi_period` | integer | No | 14 | RSI period |
| `swing_period` | integer | No | 5 | Swing period for market structure |

### Response Model
```json
{
  "symbol": "string",
  "interval": "string",
  "current_price": 0.0,
  "market_condition": "TRENDING|SIDEWAYS|UNCERTAIN|UNKNOWN",
  "confidence": 0.0,
  "recommendation": "string",
  "indicators": {
    "fast_ema": 0.0,
    "slow_ema": 0.0,
    "rsi": 0.0,
    "rsi_interpretation": "string",
    "atr": 0.0,
    "ema_spread_pct": 0.0,
    "ema_spread_abs": 0.0,
    "ema_atr_strength": 0.0
  },
  "trend_info": {
    "fast_ema": 0.0,
    "slow_ema": 0.0,
    "ema_spread_pct": 0.0,
    "fast_above_slow": true,
    "trend_direction": "UP|DOWN|null",
    "structure": "BULLISH|BEARISH|NEUTRAL|UNKNOWN"
  },
  "range_info": {
    "range_high": 0.0,
    "range_low": 0.0,
    "range_mid": 0.0,
    "range_size": 0.0,
    "range_size_pct": 0.0,
    "current_price_in_range": 0.0,
    "atr_ratio": 0.0,
    "atr_ratio_trending_threshold": 5.0,
    "atr_ratio_sideways_threshold": 2.0
  },
  "market_structure": {
    "structure": "BULLISH|BEARISH|NEUTRAL|UNKNOWN",
    "last_swing_high": 0.0,
    "last_swing_low": 0.0,
    "previous_swing_high": 0.0,
    "previous_swing_low": 0.0,
    "has_higher_high": false,
    "has_higher_low": false,
    "has_lower_high": false,
    "has_lower_low": false,
    "swing_high_count": 0,
    "swing_low_count": 0
  },
  "volume_analysis": {
    "current_volume": 0.0,
    "average_volume": 0.0,
    "volume_ema": 0.0,
    "volume_ratio": 0.0,
    "volume_trend": "INCREASING|DECREASING|STABLE",
    "volume_change_pct": 0.0,
    "is_high_volume": false,
    "is_low_volume": false
  }
}
```

**Note**: All fields in `market_structure` and `volume_analysis` are optional and may be `null` if insufficient data is available.

---

## Access Methods

### 1. Web GUI
Navigate to: `http://127.0.0.1:8000/market-analyzer`

### 2. API Endpoint
```bash
curl "http://127.0.0.1:8000/market-analyzer/analyze?symbol=BTCUSDT&interval=5m"
```

### 3. Python Example
```python
import requests

response = requests.get(
    "http://127.0.0.1:8000/market-analyzer/analyze",
    params={
        "symbol": "BTCUSDT",
        "interval": "5m",
        "lookback_period": 150
    }
)
data = response.json()
print(f"Market Condition: {data['market_condition']}")
print(f"Recommendation: {data['recommendation']}")
```

---

## Summary

The Market Analyzer is a powerful tool that:
- ✅ Analyzes market conditions using multiple indicators
- ✅ Determines if market is trending or sideways
- ✅ Provides confidence scores for decisions
- ✅ Recommends appropriate trading strategies
- ✅ Uses configurable parameters for different market conditions

**Key Takeaway**: Use the analyzer to choose between:
- **EMA Scalping Strategy** for trending markets
- **Range Mean Reversion Strategy** for sideways markets

