# Strategy Parameters Manual

Complete guide to all parameters for the EmaScalpingStrategy (`scalping` strategy type).

## Table of Contents

1. [Top-Level Parameters](#top-level-parameters)
2. [Strategy Parameters (`params`)](#strategy-parameters-params)
3. [Parameter Interactions](#parameter-interactions)
4. [Recommended Configurations](#recommended-configurations)
5. [Troubleshooting](#troubleshooting)

---

## Top-Level Parameters

### `name` (string, required)
**Description**: A descriptive name for your strategy instance.
docker exec -it jenkins bash
 the API responsespython -m pytest tests/test_log_viewer.py
- Can be any string, but descriptive names help track multiple strategies
- Appears in logs and statistics

---

### `strategy_type` (enum, required)
**Description**: The type of trading strategy to use.

**Valid Values**: 
- `"scalping"` - EmaScalpingStrategy (configurable EMA crossover)
- `"ema_crossover"` - Alias for `scalping` (for backward compatibility)

**Example**: `"scalping"`

**Notes**: 
- Both `scalping` and `ema_crossover` use the same underlying strategy
- For a 5/20 EMA crossover, use `scalping` with `ema_fast=5, ema_slow=20`

---

### `symbol` (string, required)
**Description**: The trading pair symbol to trade.

**Format**: `{BASE}{QUOTE}` (e.g., `BTCUSDT`, `ETHUSDT`)

**Example**: `"BTCUSDT"`

**Notes**:
- Must be a valid Binance Futures trading pair
- Symbol is automatically uppercased
- Ensure the symbol supports futures trading on Binance

---

### `leverage` (integer, optional, default: 5)
**Description**: The leverage multiplier for futures trading.

**Range**: `1` to `50`

**Default**: `5`

**Example**: `5` (5x leverage)

**How It Works**:
- With 5x leverage, a $100 position requires $20 margin
- Higher leverage = higher potential profit/loss
- The bot automatically sets leverage on Binance when starting the strategy

**Risk Considerations**:
- Higher leverage amplifies both gains and losses
- Start with lower leverage (3-5x) for testing
- Maximum leverage depends on Binance's limits for the symbol

---

### `risk_per_trade` (float, optional, default: 0.01)
**Description**: The percentage of account balance to risk per trade.

**Range**: `0.001` (0.1%) to `0.99` (99%)

**Default**: `0.01` (1%)

**Example**: `0.01` = 1% risk per trade

**How It Works**:
- If account balance is $10,000 and `risk_per_trade = 0.01`:
  - Risk amount = $10,000 × 0.01 = $100
  - Position size is calculated based on stop loss distance
  - If stop loss is 0.2% away, position size = $100 / 0.002 = $50,000 (with leverage)

**Important**:
- **Ignored if `fixed_amount` is set** (fixed_amount takes priority)
- Only applies to new positions, not existing ones
- Risk is calculated based on stop loss distance

**Formula**:
```
Position Size = (Account Balance × risk_per_trade) / stop_loss_pct
```

---

### `fixed_amount` (float, optional, default: null)
**Description**: Fixed USDT amount to trade per order (overrides `risk_per_trade`).

**Range**: Any positive number

**Default**: `null` (uses `risk_per_trade` instead)

**Example**: `50.0` = Always trade $50 worth per position

**How It Works**:
- When set, the bot uses this exact USDT amount for each position
- Ignores `risk_per_trade` completely
- Position size = `fixed_amount / current_price`

**Use Cases**:
- Consistent position sizing regardless of account balance
- Testing with small fixed amounts
- When you want predictable position sizes

**Example**:
```json
"fixed_amount": 50.0  // Always trade $50 worth of BTC
```

**Notes**:
- Set to `null` to use `risk_per_trade` instead
- Cannot be used together with `risk_per_trade` (fixed_amount takes priority)

---

### `max_positions` (integer, optional, default: 1)
**Description**: Maximum number of concurrent positions allowed for this strategy.

**Range**: `1` to `5`

**Default**: `1`

**Example**: `1` = Only one position at a time

**How It Works**:
- Prevents opening multiple positions simultaneously
- Strategy will hold until current position is closed
- Useful for preventing over-leveraging

**Use Cases**:
- `1`: Conservative, one position at a time (recommended for beginners)
- `2-3`: Allow multiple positions for trend-following
- `4-5`: Aggressive, maximum positions (higher risk)

**Notes**:
- Each position is independent (separate entry, TP, SL)
- Strategy tracks position count internally
- New signals are ignored if `max_positions` is reached

---

### `auto_start` (boolean, optional, default: false)
**Description**: Automatically start the strategy after creation.

**Default**: `false`

**Example**: `true` = Strategy starts trading immediately

**How It Works**:
- `false`: Strategy is created but not started (must call `/strategies/{id}/start`)
- `true`: Strategy starts trading immediately after creation

**Recommendation**: 
- Use `false` for testing to review configuration first
- Use `true` for automated deployments

---

## Strategy Parameters (`params`)

### `ema_fast` (integer, optional, default: 8)
**Description**: Period for the fast Exponential Moving Average.

**Range**: `1` to `200`

**Default**: `8`

**Example**: `8` = 8-period EMA

**How It Works**:
- Fast EMA reacts quickly to price changes
- Lower values = more sensitive to price movements
- Higher values = smoother, less reactive

**Trading Signals**:
- **Golden Cross**: When `ema_fast` crosses above `ema_slow` → BUY signal
- **Death Cross**: When `ema_fast` crosses below `ema_slow` → SELL signal

**Common Values**:
- `5-8`: Very reactive, good for scalping
- `12-15`: Balanced, medium-term trends
- `20-26`: Slower, longer-term trends

**Example**:
```json
"ema_fast": 8  // Fast 8-period EMA
```

**Notes**:
- Must be less than `ema_slow`
- Strategy needs at least `ema_slow` candles of data before trading

---

### `ema_slow` (integer, optional, default: 21)
**Description**: Period for the slow Exponential Moving Average.

**Range**: `2` to `400`

**Default**: `21`

**Example**: `21` = 21-period EMA

**How It Works**:
- Slow EMA is smoother and less reactive than fast EMA
- Acts as a trend filter
- Higher values = much smoother, longer-term trend

**Trading Signals**:
- Used in crossover detection with `ema_fast`
- When fast crosses above slow = uptrend signal
- When fast crosses below slow = downtrend signal

**Common Values**:
- `20-21`: Standard, good for 1m-5m intervals
- `26-30`: Medium-term, good for 5m-15m intervals
- `50-200`: Long-term, good for 1h+ intervals

**Example**:
```json
"ema_slow": 21  // Slow 21-period EMA
```

**Notes**:
- Must be greater than `ema_fast`
- Strategy needs at least this many candles before generating signals

---

### `take_profit_pct` (float, optional, default: 0.004)
**Description**: Take profit percentage (as decimal).

**Range**: Any positive number (typically `0.001` to `0.01`)

**Default**: `0.004` (0.4%)

**Example**: `0.004` = 0.4% profit target

**How It Works**:

**For LONG Positions**:
- Take profit price = `entry_price × (1 + take_profit_pct)`
- Example: Entry at $40,000, TP at 0.4% = $40,160
- Position closes automatically when price reaches TP

**For SHORT Positions** (inverted):
- Take profit price = `entry_price × (1 - take_profit_pct)`
- Example: Entry at $40,000, TP at 0.4% = $39,840
- Position closes when price drops to TP

**Common Values**:
- `0.002` (0.2%): Very tight, quick scalps
- `0.004` (0.4%): Balanced, recommended for scalping
- `0.006` (0.6%): Wider, more room for volatility
- `0.01` (1%): Wide, swing trading

**Example**:
```json
"take_profit_pct": 0.004  // 0.4% profit target
```

**Notes**:
- Expressed as decimal (0.004 = 0.4%)
- Should be larger than `stop_loss_pct` for positive risk/reward
- With 5x leverage, 0.4% price move = 2% account gain

---

### `stop_loss_pct` (float, optional, default: 0.002)
**Description**: Stop loss percentage (as decimal).

**Range**: Any positive number (typically `0.001` to `0.01`)

**Default**: `0.002` (0.2%)

**Example**: `0.002` = 0.2% stop loss

**How It Works**:

**For LONG Positions**:
- Stop loss price = `entry_price × (1 - stop_loss_pct)`
- Example: Entry at $40,000, SL at 0.2% = $39,920
- Position closes automatically when price hits SL

**For SHORT Positions** (inverted):
- Stop loss price = `entry_price × (1 + stop_loss_pct)`
- Example: Entry at $40,000, SL at 0.2% = $40,080
- Position closes when price rises to SL

**Common Values**:
- `0.001` (0.1%): Very tight, high risk of stop-outs
- `0.002` (0.2%): Tight, good for low volatility
- `0.003` (0.3%): Balanced, more room for noise
- `0.005` (0.5%): Wide, less frequent stop-outs

**Example**:
```json
"stop_loss_pct": 0.002  // 0.2% stop loss
```

**Notes**:
- Expressed as decimal (0.002 = 0.2%)
- Should be smaller than `take_profit_pct` for positive risk/reward
- With 5x leverage, 0.2% price move = 1% account loss

**Risk/Reward Ratio**:
- Default: TP 0.4% / SL 0.2% = 2:1 risk/reward ratio
- This means you risk $1 to make $2

---

### `interval_seconds` (integer, optional, default: 10)
**Description**: How often the strategy evaluates market conditions (in seconds).

**Range**: `1` to `3600` (1 second to 1 hour)

**Default**: `10` (every 10 seconds)

**Example**: `10` = Strategy checks market every 10 seconds

**How It Works**:
- Strategy runs its `evaluate()` method every `interval_seconds`
- Checks for new closed candles, crossovers, TP/SL hits
- More frequent = faster signal detection, more CPU usage

**Common Values**:
- `5-10`: Very frequent, good for 1m scalping
- `15-30`: Balanced, good for 5m-15m intervals
- `60`: Less frequent, good for 1h+ intervals

**Example**:
```json
"interval_seconds": 10  // Check every 10 seconds
```

**Notes**:
- Lower values = faster response but more API calls
- Should match your `kline_interval` (e.g., 1m candles = check every 10-30s)
- Too frequent (1-2s) may hit API rate limits
- Too infrequent (60s+) may miss signals

**Recommendation**:
- For 1m candles: `10-30` seconds
- For 5m candles: `30-60` seconds
- For 15m+ candles: `60-300` seconds

---

### `kline_interval` (string, optional, default: "1m")
**Description**: The candlestick interval used for EMA calculation.

**Valid Values**: 
- `"1m"`, `"3m"`, `"5m"`, `"15m"`, `"30m"`
- `"1h"`, `"2h"`, `"4h"`, `"6h"`, `"8h"`, `"12h"`, `"1d"`

**Default**: `"1m"` (1-minute candles)

**Example**: `"1m"` = Use 1-minute candlesticks

**How It Works**:
- Strategy fetches candlestick data (klines) from Binance
- Uses closing prices from each candle to calculate EMAs
- Only processes **closed** candles (ignores the forming candle)
- Each candle must close before it's used in calculations

**Common Values**:
- `"1m"`: Scalping, very active trading
- `"5m"`: Short-term trading, less noise
- `"15m"`: Medium-term, fewer signals
- `"1h"`: Swing trading, longer-term trends

**Example**:
```json
"kline_interval": "1m"  // Use 1-minute candles
```

**Notes**:
- Strategy needs at least `ema_slow` candles before trading
- For 1m interval with ema_slow=21: needs 21 minutes of data
- For 5m interval with ema_slow=21: needs 105 minutes (1h 45m) of data
- Invalid intervals default to `"1m"`

**Data Requirements**:
- Minimum candles needed = `max(ema_slow + 10, 50)`
- Strategy fetches enough historical data automatically

---

### `enable_short` (boolean, optional, default: true)
**Description**: Enable short trading (selling to open, buying to close).

**Default**: `true`

**Example**: `true` = Allow both long and short positions

**How It Works**:

**When `true`**:
- Strategy can enter SHORT positions on death cross
- Strategy can enter LONG positions on golden cross
- Both directions are traded

**When `false`**:
- Strategy only enters LONG positions on golden cross
- Death cross only exits long positions (no short entry)
- One-directional trading only

**Trading Logic**:

**Long Trading** (always enabled):
- Golden cross → BUY (open long)
- Death cross → SELL (close long)
- TP/SL based on price going up

**Short Trading** (only if `enable_short=true`):
- Death cross → SELL (open short)
- Golden cross → BUY (close short)
- TP/SL inverted (profit when price goes down)

**Example**:
```json
"enable_short": true  // Enable both long and short trading
```

**Notes**:
- Short trading requires futures account with shorting enabled
- Shorts have inverted TP/SL calculations
- Higher-timeframe bias (if enabled) only affects short entries

**Use Cases**:
- `true`: Capture both uptrends and downtrends (recommended)
- `false`: Only trade long positions (safer for beginners)

---

### `min_ema_separation` (float, optional, default: 0.0002)
**Description**: Minimum EMA separation filter to avoid noise (as decimal percentage of price).

**Range**: `0` (disabled) to any positive number

**Default**: `0.0002` (0.02% of price)

**Example**: `0.0002` = EMAs must be at least 0.02% apart

**How It Works**:
- Calculates: `|fast_ema - slow_ema| / current_price`
- If separation < `min_ema_separation` → Block entry signal
- **Only applies to NEW entries**, not exits (safety consideration)

**Purpose**:
- Prevents entering trades when EMAs are too close (noise)
- Reduces false signals in choppy markets
- Ensures clear trend direction

**Example Calculation**:
- Price: $40,000
- Fast EMA: $40,010
- Slow EMA: $40,005
- Separation: |40100 - 40005| / 40000 = 0.000125 (0.0125%)
- If `min_ema_separation = 0.0002` → Blocked (0.0125% < 0.02%)

**Common Values**:
- `0`: Disabled, allow all crossovers
- `0.0001` (0.01%): Very loose, allows most signals
- `0.0002` (0.02%): Balanced, recommended
- `0.0005` (0.05%): Strict, only strong trends

**Example**:
```json
"min_ema_separation": 0.0002  // 0.02% minimum separation
```

**Notes**:
- Expressed as decimal (0.0002 = 0.02%)
- Set to `0` to disable the filter
- Only blocks **new entries**, exits are always allowed
- Helps reduce whipsaws in sideways markets

---

### `enable_htf_bias` (boolean, optional, default: true)
**Description**: Enable higher-timeframe bias filter for short positions.

**Default**: `true`

**Example**: `true` = Check 5m trend before entering shorts

**How It Works**:

**When `true` and `kline_interval = "1m"`**:
- Before entering a SHORT position, checks 5-minute timeframe
- Calculates 5m fast EMA and slow EMA
- Only allows short if 5m trend is DOWN (5m fast EMA < 5m slow EMA)
- Blocks short if 5m trend is UP (prevents counter-trend shorts)

**When `false`**:
- No higher-timeframe check
- Shorts allowed on any death cross

**Purpose**:
- Prevents shorting against higher-timeframe uptrends
- Reduces risk of counter-trend trades
- Only applies to SHORT entries, not longs

**Example Scenario**:
- 1m chart: Death cross (short signal)
- 5m chart: Golden cross (uptrend)
- With `enable_htf_bias=true`: Short is **blocked** (5m trend is up)
- With `enable_htf_bias=false`: Short is **allowed**

**Example**:
```json
"enable_htf_bias": true  // Check 5m trend for shorts
```

**Notes**:
- Only active when `kline_interval = "1m"`
- Only affects SHORT entries, not long entries
- Uses same EMA periods (`ema_fast`, `ema_slow`) on 5m timeframe
- Set to `false` to disable the filter

**Use Cases**:
- `true`: Safer shorts, avoid counter-trend (recommended)
- `false`: More aggressive, allow all short signals

---

### `cooldown_candles` (integer, optional, default: 2)
**Description**: Number of candles to wait after exiting a position before allowing new entry.

**Range**: `0` to `10`

**Default**: `2`

**Example**: `2` = Wait 2 candles after exit before new entry

---

### `trailing_stop_enabled` (boolean, optional, default: false)
**Description**: Enable dynamic trailing stop loss that adjusts TP/SL as price moves favorably.

**Default**: `false`

**Example**: `true` = Enable trailing stop

**How It Works**:
- When enabled, TP and SL levels trail up (LONG) or down (SHORT) as price moves favorably
- Maintains constant risk/reward percentages from current best price
- Only trails in favorable direction (never gives back profits)
- Works with both LONG and SHORT positions

**Example**:
```json
"trailing_stop_enabled": true  // Enable dynamic trailing stop
```

**Notes**:
- Requires `trailing_stop_activation_pct` to control when trailing starts
- See [TRAILING_STOP_GUIDE.md](TRAILING_STOP_GUIDE.md) for detailed examples
- Works best with wider TP/SL percentages (1-5%)

---

### `trailing_stop_activation_pct` (float, optional, default: 0.0)
**Description**: Percentage price must move in favorable direction before trailing activates.

**Range**: `0.0` to `0.1` (0% to 10%)

**Default**: `0.0` (trailing starts immediately)

**Example**: `0.01` = Trailing starts after 1% move

**How It Works**:

**For LONG Positions**:
- Trailing activates when price reaches: `entry_price × (1 + activation_pct)`
- Example: Entry 100,000, activation 1% → Trailing starts at 101,000
- Before activation: TP/SL remain fixed at entry-based levels
- After activation: TP/SL trail up as price moves up

**For SHORT Positions**:
- Trailing activates when price reaches: `entry_price × (1 - activation_pct)`
- Example: Entry 100,000, activation 1% → Trailing starts at 99,000
- Before activation: TP/SL remain fixed at entry-based levels
- After activation: TP/SL trail down as price moves down

**Common Values**:
- `0.0` (0%): Trailing starts immediately (default)
- `0.01` (1%): Wait for 1% move before trailing (recommended for most cases)
- `0.02` (2%): Wait for 2% move (more conservative, avoids noise)
- `0.005` (0.5%): Very sensitive, trails on small moves

**Example**:
```json
"trailing_stop_activation_pct": 0.01  // 1% activation threshold
```

**Why Use Activation Threshold?**:
- Prevents trailing from activating on small price movements/noise
- Only trails when there's a clear favorable trend
- Reduces premature trailing that might exit too early
- Better for volatile markets where small moves are common

**Example Scenario**:
```
Entry: 100,000
Activation: 1% (price must reach 101,000)

Price at 100,500 (+0.5%): Trailing NOT active, TP/SL fixed
Price at 101,000 (+1.0%): ✅ Trailing ACTIVATED, starts trailing
Price at 102,000 (+2.0%): Trailing continues, TP/SL adjusted
```

**Notes**:
- Only applies when `trailing_stop_enabled = true`
- Set to `0.0` for immediate trailing (no threshold)
- Higher values = more conservative (waits for stronger moves)

**How It Works**:
- After closing a position (TP, SL, or crossover exit), starts cooldown
- Strategy holds for `cooldown_candles` before allowing new entry
- Prevents rapid flip-flopping between long/short
- Cooldown decrements each candle (not time-based)

**Purpose**:
- Prevents entering immediately after exit (reduces whipsaws)
- Gives market time to establish direction
- Reduces overtrading in choppy markets

**Example Scenario**:
1. Long position closed at TP
2. Cooldown starts: `cooldown_candles = 2`
3. Next candle: Cooldown = 1 (still blocked)
4. Next candle: Cooldown = 0 (new entries allowed)

**Common Values**:
- `0`: No cooldown, immediate re-entry (aggressive)
- `1-2`: Short cooldown, quick re-entry (recommended for scalping)
- `3-5`: Medium cooldown, more conservative
- `6-10`: Long cooldown, very conservative

**Example**:
```json
"cooldown_candles": 2  // Wait 2 candles after exit
```

**Notes**:
- Measured in candles, not time
- For 1m candles: 2 candles = 2 minutes
- For 5m candles: 2 candles = 10 minutes
- Applies to all exits (TP, SL, crossover)
- Set to `0` to disable cooldown

**Use Cases**:
- `0-1`: Very active trading, more signals
- `2-3`: Balanced, recommended for most cases
- `5+`: Conservative, fewer but higher-quality signals

---

## Parameter Interactions

### Risk Management Parameters

**`risk_per_trade` vs `fixed_amount`**:
- `fixed_amount` takes priority if set
- If `fixed_amount = null`, uses `risk_per_trade`
- Cannot use both simultaneously

**Position Size Calculation**:
```
If fixed_amount is set:
  position_size = fixed_amount / current_price

If risk_per_trade is used:
  risk_amount = account_balance × risk_per_trade
  position_size = risk_amount / stop_loss_pct
```

### EMA Parameters

**`ema_fast` vs `ema_slow`**:
- `ema_fast` must be < `ema_slow`
- Smaller gap = more frequent signals, more noise
- Larger gap = fewer signals, stronger trends

**Common Combinations**:
- `8/21`: Standard scalping (default)
- `5/20`: Faster, more signals
- `12/26`: Slower, fewer signals
- `20/50`: Long-term trends

### Filter Interactions

**`min_ema_separation` + `cooldown_candles`**:
- Both reduce false signals
- `min_ema_separation`: Blocks weak crossovers
- `cooldown_candles`: Prevents rapid re-entry
- Using both = very conservative strategy

**`enable_htf_bias` + `enable_short`**:
- `enable_htf_bias` only affects shorts
- If `enable_short = false`, `enable_htf_bias` has no effect
- Both enabled = safer short trading

### Timeframe Parameters

**`kline_interval` + `interval_seconds`**:
- `kline_interval`: Data granularity (1m, 5m, etc.)
- `interval_seconds`: How often to check
- Should match: 1m candles → check every 10-30s
- Too frequent checking wastes resources
- Too infrequent may miss signals

---

## Recommended Configurations

### Aggressive Scalping (1m, High Frequency)
```json
{
  "ema_fast": 5,
  "ema_slow": 15,
  "take_profit_pct": 0.003,
  "stop_loss_pct": 0.0015,
  "kline_interval": "1m",
  "interval_seconds": 10,
  "enable_short": true,
  "min_ema_separation": 0.0001,
  "enable_htf_bias": true,
  "cooldown_candles": 1
}
```
- Fast EMAs for quick signals
- Tight TP/SL for quick profits
- Short cooldown for frequent trading

### Balanced Scalping (1m, Standard)
```json
{
  "ema_fast": 8,
  "ema_slow": 21,
  "take_profit_pct": 0.004,
  "stop_loss_pct": 0.002,
  "kline_interval": "1m",
  "interval_seconds": 10,
  "enable_short": true,
  "min_ema_separation": 0.0002,
  "enable_htf_bias": true,
  "cooldown_candles": 2
}
```
- Default configuration
- Good balance of signals and quality
- Recommended for most users

### Conservative Scalping (5m, Lower Frequency)
```json
{
  "ema_fast": 12,
  "ema_slow": 26,
  "take_profit_pct": 0.006,
  "stop_loss_pct": 0.003,
  "kline_interval": "5m",
  "interval_seconds": 30,
  "enable_short": true,
  "min_ema_separation": 0.0003,
  "enable_htf_bias": false,
  "cooldown_candles": 3
}
```
- Slower EMAs for stronger trends
- Wider TP/SL for more room
- Longer cooldown for fewer trades

### Trailing Stop Scalping (1m, Profit Protection)
```json
{
  "ema_fast": 8,
  "ema_slow": 21,
  "take_profit_pct": 0.005,
  "stop_loss_pct": 0.002,
  "kline_interval": "1m",
  "interval_seconds": 10,
  "enable_short": true,
  "trailing_stop_enabled": true,
  "trailing_stop_activation_pct": 0.01,
  "min_ema_separation": 0.0002,
  "cooldown_candles": 2
}
```
- Trailing stop locks in profits
- 1% activation threshold (waits for clear move)
- Wider TP (0.5%) for better trailing effect

### Long-Only Strategy (No Shorts)
```json
{
  "ema_fast": 8,
  "ema_slow": 21,
  "take_profit_pct": 0.004,
  "stop_loss_pct": 0.002,
  "kline_interval": "1m",
  "interval_seconds": 10,
  "enable_short": false,
  "min_ema_separation": 0.0002,
  "enable_htf_bias": false,
  "cooldown_candles": 2
}
```
- Only trades long positions
- Safer for beginners
- No short exposure

---

## Troubleshooting

### Strategy Not Trading

**Problem**: Strategy created but no trades executed.

**Check**:
1. Is strategy started? (`auto_start=true` or call `/start` endpoint)
2. Enough data? Need at least `ema_slow` candles
3. `min_ema_separation` too high? Try lowering to `0.0001`
4. `cooldown_candles` blocking? Check if recently exited

### Too Many False Signals

**Problem**: Strategy enters and exits positions too frequently.

**Solutions**:
- Increase `min_ema_separation` (e.g., `0.0003`)
- Increase `cooldown_candles` (e.g., `3-5`)
- Use slower EMAs (e.g., `12/26` instead of `8/21`)
- Use higher timeframe (e.g., `5m` instead of `1m`)

### Missing Signals

**Problem**: Strategy not entering when it should.

**Solutions**:
- Decrease `min_ema_separation` (e.g., `0.0001` or `0`)
- Decrease `cooldown_candles` (e.g., `1` or `0`)
- Check if `enable_short=false` is blocking shorts
- Verify `interval_seconds` is frequent enough

### Shorts Not Working

**Problem**: Short positions not being entered.

**Check**:
1. `enable_short=true`?
2. `enable_htf_bias=true` blocking? (Check 5m trend)
3. `min_ema_separation` too high?
4. Account has shorting enabled on Binance?

### Stop Loss Hit Too Often

**Problem**: Positions stopped out before reaching TP.

**Solutions**:
- Increase `stop_loss_pct` (e.g., `0.003` instead of `0.002`)
- Use wider TP/SL ratio (e.g., TP `0.006`, SL `0.002` = 3:1)
- Use higher timeframe (less noise)
- Check if market is too volatile for current settings

### Take Profit Never Hit

**Problem**: Positions exit on crossover before reaching TP.

**Solutions**:
- This is normal behavior (crossover exit is valid)
- If you want TP priority, you'd need to modify strategy code
- Consider wider `take_profit_pct` if market moves fast
- Use slower EMAs for longer trends

---

## Quick Reference

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `name` | string | - | - | Strategy name |
| `strategy_type` | enum | - | `scalping`, `ema_crossover` | Strategy type |
| `symbol` | string | - | - | Trading pair |
| `leverage` | int | 5 | 1-50 | Leverage multiplier |
| `risk_per_trade` | float | 0.01 | 0.001-0.99 | Risk percentage |
| `fixed_amount` | float | null | >0 | Fixed USDT amount |
| `max_positions` | int | 1 | 1-5 | Max concurrent positions |
| `auto_start` | bool | false | true/false | Auto-start strategy |
| `ema_fast` | int | 8 | 1-200 | Fast EMA period |
| `ema_slow` | int | 21 | 2-400 | Slow EMA period |
| `take_profit_pct` | float | 0.004 | >0 | Take profit % |
| `stop_loss_pct` | float | 0.002 | >0 | Stop loss % |
| `interval_seconds` | int | 10 | 1-3600 | Check interval |
| `kline_interval` | string | "1m" | See list | Candlestick interval |
| `enable_short` | bool | true | true/false | Enable shorts |
| `min_ema_separation` | float | 0.0002 | ≥0 | Min EMA separation |
| `enable_htf_bias` | bool | true | true/false | 5m trend filter |
| `cooldown_candles` | int | 2 | 0-10 | Cooldown after exit |
| `trailing_stop_enabled` | bool | false | true/false | Enable trailing stop |
| `trailing_stop_activation_pct` | float | 0.0 | 0.0-0.1 | Activation threshold % |

---

## Additional Resources

- [API_USAGE.md](API_USAGE.md) - Complete API documentation
- [STRATEGY_EXAMPLES.md](STRATEGY_EXAMPLES.md) - Strategy examples and scenarios
- [TEST_SUMMARY.md](TEST_SUMMARY.md) - Test coverage and validation
- [README.md](README.md) - Project overview and setup

---

**Last Updated**: Based on EmaScalpingStrategy implementation in `app/strategies/scalping.py`


