# Complete Strategy Parameters Manual

Complete guide to all trading strategies and their parameters in the Binance Bot.

## Table of Contents

1. [Available Strategies](#available-strategies)
2. [Common Parameters](#common-parameters)
3. [EMA Scalping Strategy](#ema-scalping-strategy)
4. [Range Mean-Reversion Strategy](#range-mean-reversion-strategy)
5. [Recommended Configurations](#recommended-configurations)
6. [Troubleshooting](#troubleshooting)

---

## Available Strategies

The bot supports two main trading strategies:

1. **EMA Scalping Strategy** (`scalping` or `ema_crossover`)
   - EMA crossover-based scalping strategy
   - Trades on golden cross (long) and death cross (short)
   - Configurable EMA periods, TP/SL, and advanced filters

2. **Range Mean-Reversion Strategy** (`range_mean_reversion`)
   - Range-bound trading strategy for sideways markets
   - Buys at support, sells at resistance
   - Uses range detection, RSI, and trend filtering

---

## Common Parameters

These parameters apply to ALL strategies and are set at the strategy creation level:

### `name` (string, required)
**Description**: A descriptive name for your strategy instance.

**Example**: `"BTC Scalping Bot"`, `"ETH Range Trader"`

**Notes**:
- Can be any string, but descriptive names help track multiple strategies
- Appears in logs, GUI, and API responses

---

### `strategy_type` (enum, required)
**Description**: The type of trading strategy to use.

**Valid Values**: 
- `"scalping"` - EMA Scalping Strategy (configurable EMA crossover)
- `"ema_crossover"` - Alias for `scalping` (for backward compatibility)
- `"range_mean_reversion"` - Range Mean-Reversion Strategy

**Example**: `"scalping"` or `"range_mean_reversion"`

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

### `leverage` (integer, required)
**Description**: The leverage multiplier for futures trading.

**Range**: `1` to `50`

**Example**: `5` (5x leverage)

**How It Works**:
- With 5x leverage, a $100 position requires $20 margin
- Higher leverage = higher potential profit/loss
- The bot automatically sets leverage on Binance when starting the strategy

**Risk Considerations**:
- Higher leverage amplifies both gains and losses
- Start with lower leverage (3-5x) for testing
- Maximum leverage depends on Binance's limits for the symbol

**Important**: Leverage is REQUIRED and must be explicitly set (no default) to avoid Binance's 20x default.

---

### `risk_per_trade` (float, optional, default: 0.01)
**Description**: The percentage of account balance to risk per trade.

**Range**: `0.001` (0.1%) to `0.99` (99%)`

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

## EMA Scalping Strategy

The EMA Scalping Strategy uses Exponential Moving Average crossovers to identify trading opportunities in trending markets.

### Strategy Type
- **Value**: `"scalping"` or `"ema_crossover"`
- **Implementation**: `EmaScalpingStrategy`

### Trading Logic

**Long Trading**:
- **Entry**: Golden Cross - Fast EMA crosses above Slow EMA
- **Exit**: Death Cross, Take Profit, or Stop Loss hit

**Short Trading** (if enabled):
- **Entry**: Death Cross - Fast EMA crosses below Slow EMA  
- **Exit**: Golden Cross, Take Profit, or Stop Loss hit

### Strategy Parameters (`params`)

#### `ema_fast` (integer, optional, default: 8)
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

**Notes**:
- Must be less than `ema_slow`
- Strategy needs at least `ema_slow` candles of data before trading

---

#### `ema_slow` (integer, optional, default: 21)
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

**Notes**:
- Must be greater than `ema_fast`
- Strategy needs at least this many candles before generating signals

---

#### `take_profit_pct` (float, optional, default: 0.004)
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

**Notes**:
- Expressed as decimal (0.004 = 0.4%)
- Should be larger than `stop_loss_pct` for positive risk/reward
- With 5x leverage, 0.4% price move = 2% account gain

---

#### `stop_loss_pct` (float, optional, default: 0.002)
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

**Notes**:
- Expressed as decimal (0.002 = 0.2%)
- Should be smaller than `take_profit_pct` for positive risk/reward
- With 5x leverage, 0.2% price move = 1% account loss

**Risk/Reward Ratio**:
- Default: TP 0.4% / SL 0.2% = 2:1 risk/reward ratio
- This means you risk $1 to make $2

---

#### `interval_seconds` (integer, optional, default: 10)
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

#### `kline_interval` (string, optional, default: "1m")
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

**Notes**:
- Strategy needs at least `ema_slow` candles before trading
- For 1m interval with ema_slow=21: needs 21 minutes of data
- For 5m interval with ema_slow=21: needs 105 minutes (1h 45m) of data
- Invalid intervals default to `"1m"`

**Data Requirements**:
- Minimum candles needed = `max(ema_slow + 10, 50)`
- Strategy fetches enough historical data automatically

---

#### `enable_short` (boolean, optional, default: true)
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

**Notes**:
- Short trading requires futures account with shorting enabled
- Shorts have inverted TP/SL calculations
- Higher-timeframe bias (if enabled) only affects short entries

**Use Cases**:
- `true`: Capture both uptrends and downtrends (recommended)
- `false`: Only trade long positions (safer for beginners)

---

#### `min_ema_separation` (float, optional, default: 0.0002)
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

**Notes**:
- Expressed as decimal (0.0002 = 0.02%)
- Set to `0` to disable the filter
- Only blocks **new entries**, exits are always allowed
- Helps reduce whipsaws in sideways markets

---

#### `enable_htf_bias` (boolean, optional, default: true)
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

**Notes**:
- Only active when `kline_interval = "1m"`
- Only affects SHORT entries, not long entries
- Uses same EMA periods (`ema_fast`, `ema_slow`) on 5m timeframe
- Set to `false` to disable the filter

**Use Cases**:
- `true`: Safer shorts, avoid counter-trend (recommended)
- `false`: More aggressive, allow all short signals

---

#### `cooldown_candles` (integer, optional, default: 2)
**Description**: Number of candles to wait after exiting a position before allowing new entry.

**Range**: `0` to `10`

**Default**: `2`

**Example**: `2` = Wait 2 candles after exit before new entry

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

#### `trailing_stop_enabled` (boolean, optional, default: false)
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
- Works best with wider TP/SL percentages (1-5%)
- See trailing stop documentation for detailed examples

---

#### `trailing_stop_activation_pct` (float, optional, default: 0.0)
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

---

## Range Mean-Reversion Strategy

The Range Mean-Reversion Strategy identifies and trades within price ranges (sideways markets) by buying at support and selling at resistance.

### Strategy Type
- **Value**: `"range_mean_reversion"`
- **Implementation**: `RangeMeanReversionStrategy`

### Trading Logic

**Long Trading**:
- **Entry**: Price in buy zone (bottom 20% of range) + RSI < 40
- **Exit**: Take profit at range midpoint or range high - buffer, Stop loss below range low

**Short Trading** (if enabled):
- **Entry**: Price in sell zone (top 20% of range) + RSI > 60
- **Exit**: Take profit at range midpoint or range low + buffer, Stop loss above range high

### Strategy Parameters (`params`)

#### `lookback_period` (integer, optional, default: 150)
**Description**: Number of candles to look back for range detection.

**Range**: `50` to `500`

**Default**: `150`

**Example**: `150` = Analyze last 150 candles to detect range

**How It Works**:
- Strategy analyzes the last `lookback_period` candles to find:
  - Highest high (range_high)
  - Lowest low (range_low)
  - Range midpoint (range_mid)
- Larger values = more stable but slower to adapt to new ranges
- Smaller values = faster adaptation but may miss larger ranges

**Common Values**:
- `100-150`: Standard, good for 5m-15m intervals
- `200-300`: Longer-term ranges, good for 1h+ intervals
- `50-100`: Short-term ranges, faster adaptation

**Notes**:
- Requires at least `lookback_period + 10` candles of data
- Range must pass trend filter and volatility checks to be valid
- Too small = may not capture full range
- Too large = slow to adapt to new ranges

---

#### `buy_zone_pct` (float, optional, default: 0.2)
**Description**: Buy zone as percentage of range (bottom portion where longs are entered).

**Range**: `0` to `0.5` (0% to 50% of range)

**Default**: `0.2` (bottom 20% of range)

**Example**: `0.2` = Buy when price is in bottom 20% of range

**How It Works**:
- Calculates buy zone: `range_low + (range_size × buy_zone_pct)`
- If price ≤ buy_zone_upper AND RSI < oversold → LONG entry signal
- Lower values = more conservative (only buy very near bottom)
- Higher values = more aggressive (buy in larger bottom area)

**Example Calculation**:
- Range: $40,000 (high) to $38,000 (low) = $2,000 range
- `buy_zone_pct = 0.2` (20%)
- Buy zone: $38,000 + ($2,000 × 0.2) = $38,400
- Long entry when price ≤ $38,400 and RSI < 40

**Common Values**:
- `0.15` (15%): Very conservative, only near bottom
- `0.2` (20%): Balanced, recommended
- `0.25-0.3` (25-30%): More aggressive, larger buy zone

**Notes**:
- Expressed as decimal (0.2 = 20%)
- Should be < 0.5 to ensure buy zone is below midpoint
- Smaller = fewer but higher-quality entries

---

#### `sell_zone_pct` (float, optional, default: 0.2)
**Description**: Sell zone as percentage of range (top portion where shorts are entered).

**Range**: `0` to `0.5` (0% to 50% of range)

**Default**: `0.2` (top 20% of range)

**Example**: `0.2` = Sell when price is in top 20% of range

**How It Works**:
- Calculates sell zone: `range_high - (range_size × sell_zone_pct)`
- If price ≥ sell_zone_lower AND RSI > overbought → SHORT entry signal
- Lower values = more conservative (only sell very near top)
- Higher values = more aggressive (sell in larger top area)

**Example Calculation**:
- Range: $40,000 (high) to $38,000 (low) = $2,000 range
- `sell_zone_pct = 0.2` (20%)
- Sell zone: $40,000 - ($2,000 × 0.2) = $39,600
- Short entry when price ≥ $39,600 and RSI > 60

**Common Values**:
- `0.15` (15%): Very conservative, only near top
- `0.2` (20%): Balanced, recommended
- `0.25-0.3` (25-30%): More aggressive, larger sell zone

**Notes**:
- Expressed as decimal (0.2 = 20%)
- Should be < 0.5 to ensure sell zone is above midpoint
- Smaller = fewer but higher-quality entries

---

#### `ema_fast_period` (integer, optional, default: 20)
**Description**: Fast EMA period for trend filter (detects if market is trending vs ranging).

**Range**: `5` to `100`

**Default**: `20`

**Example**: `20` = 20-period fast EMA

**How It Works**:
- Used to calculate EMA spread as trend filter
- If EMA spread > `max_ema_spread_pct` → Market is trending (not ranging)
- Range strategy only trades when EMAs are close (sideways market)
- Fast EMA reacts quickly to price changes

**Notes**:
- Must be less than `ema_slow_period`
- Used only for trend filtering, not for trading signals
- Larger values = slower reaction, stricter trend filter

---

#### `ema_slow_period` (integer, optional, default: 50)
**Description**: Slow EMA period for trend filter.

**Range**: `10` to `200`

**Default**: `50`

**Example**: `50` = 50-period slow EMA

**How It Works**:
- Used with fast EMA to calculate spread
- If fast and slow EMAs are far apart → Market is trending
- If fast and slow EMAs are close → Market is ranging
- Strategy only trades when range is valid (EMAs close together)

**Notes**:
- Must be greater than `ema_fast_period`
- Used only for trend filtering, not for trading signals
- Larger values = stricter trend filter (only very sideways markets)

---

#### `max_ema_spread_pct` (float, optional, default: 0.005)
**Description**: Maximum EMA spread percentage for valid range (if exceeded, market is trending).

**Range**: `0` to `0.02` (0% to 2%)

**Default**: `0.005` (0.5%)

**Example**: `0.005` = Range invalid if EMA spread > 0.5%

**How It Works**:
- Calculates: `|fast_ema - slow_ema| / current_price`
- If spread ≤ `max_ema_spread_pct` → Valid range (market is sideways)
- If spread > `max_ema_spread_pct` → Invalid range (market is trending)
- Strategy only trades when range is valid

**Purpose**:
- Ensures strategy only trades in sideways/ranging markets
- Blocks trades during strong trends
- Prevents mean-reversion trades against trends

**Example Calculation**:
- Price: $40,000
- Fast EMA: $40,150
- Slow EMA: $40,050
- Spread: |40150 - 40050| / 40000 = 0.0025 (0.25%)
- If `max_ema_spread_pct = 0.005` → Valid range (0.25% < 0.5%)

**Common Values**:
- `0.003` (0.3%): Strict, only very sideways markets
- `0.005` (0.5%): Balanced, recommended
- `0.01` (1%): Loose, allows more markets

**Notes**:
- Expressed as decimal (0.005 = 0.5%)
- Lower values = stricter (only very ranging markets)
- Higher values = looser (allows slight trends)

---

#### `max_atr_multiplier` (float, optional, default: 2.0)
**Description**: Maximum ATR multiplier for range volatility check (prevents trading in too volatile markets).

**Range**: `0` to `10`

**Default**: `2.0`

**Example**: `2.0` = Range size should be ≤ 5× ATR (ATR × multiplier × 5)

**How It Works**:
- Calculates Average True Range (ATR) to measure volatility
- Compares range size to ATR: `range_size / atr`
- If range too large relative to ATR → Market too volatile, invalid range
- Prevents trading in explosive/breakout conditions

**Purpose**:
- Ensures range is reasonable relative to recent volatility
- Blocks trades in highly volatile/chaotic markets
- Only trades in stable, predictable ranges

**Common Values**:
- `1.5`: Strict, only very stable ranges
- `2.0`: Balanced, recommended
- `3.0-5.0`: Loose, allows more volatile ranges

**Notes**:
- Higher values = allows more volatile ranges
- Lower values = stricter volatility filter
- Works with ATR to ensure range stability

---

#### `rsi_period` (integer, optional, default: 14)
**Description**: RSI calculation period.

**Range**: `5` to `50`

**Default**: `14`

**Example**: `14` = 14-period RSI

**How It Works**:
- Relative Strength Index measures momentum
- RSI < oversold → Oversold condition (buy signal confirmation)
- RSI > overbought → Overbought condition (sell signal confirmation)
- Used as confirmation filter for entry signals

**Notes**:
- Standard RSI period is 14
- Lower values = more sensitive, more signals
- Higher values = smoother, fewer signals

---

#### `rsi_oversold` (float, optional, default: 40)
**Description**: RSI oversold threshold for long entries.

**Range**: `0` to `50`

**Default**: `40`

**Example**: `40` = Enter long when RSI < 40

**How It Works**:
- Combined with buy zone: `price in buy zone AND RSI < rsi_oversold` → LONG entry
- Lower values = more conservative (only very oversold)
- Higher values = more aggressive (less oversold required)

**Common Values**:
- `30`: Very conservative, only extreme oversold
- `40`: Balanced, recommended
- `45`: More aggressive, less oversold required

**Notes**:
- Standard oversold level is 30, but 40 is more balanced
- Should be less than 50 (below midpoint)
- Lower = fewer but higher-quality entries

---

#### `rsi_overbought` (float, optional, default: 60)
**Description**: RSI overbought threshold for short entries.

**Range**: `50` to `100`

**Default**: `60`

**Example**: `60` = Enter short when RSI > 60

**How It Works**:
- Combined with sell zone: `price in sell zone AND RSI > rsi_overbought` → SHORT entry
- Higher values = more conservative (only very overbought)
- Lower values = more aggressive (less overbought required)

**Common Values**:
- `70`: Very conservative, only extreme overbought
- `60`: Balanced, recommended
- `55`: More aggressive, less overbought required

**Notes**:
- Standard overbought level is 70, but 60 is more balanced
- Should be greater than 50 (above midpoint)
- Higher = fewer but higher-quality entries

---

#### `tp_buffer_pct` (float, optional, default: 0.001)
**Description**: Take profit buffer percentage from range boundary (prevents exiting exactly at boundary).

**Range**: `0` to `0.01` (0% to 1%)

**Default**: `0.001` (0.1%)

**Example**: `0.001` = TP is 0.1% away from range boundary

**How It Works**:

**For LONG Positions**:
- TP1: `range_mid` (range midpoint)
- TP2: `range_high - (range_size × tp_buffer_pct)` (near top, with buffer)
- Takes profit before hitting exact range high

**For SHORT Positions**:
- TP1: `range_mid` (range midpoint)
- TP2: `range_low + (range_size × tp_buffer_pct)` (near bottom, with buffer)
- Takes profit before hitting exact range low

**Purpose**:
- Prevents exiting exactly at range boundary (may not fill)
- Leaves small buffer for order execution
- Ensures profit is captured before potential reversal

**Common Values**:
- `0.0005` (0.05%): Very tight, near boundary
- `0.001` (0.1%): Balanced, recommended
- `0.002` (0.2%): Wider buffer, safer

**Notes**:
- Expressed as decimal (0.001 = 0.1%)
- Lower values = closer to boundary, may risk not filling
- Higher values = further from boundary, safer but less profit

---

#### `sl_buffer_pct` (float, optional, default: 0.002)
**Description**: Stop loss buffer percentage beyond range boundary (exits if range breaks).

**Range**: `0` to `0.01` (0% to 1%)

**Default**: `0.002` (0.2%)

**Example**: `0.002` = SL is 0.2% beyond range boundary

**How It Works**:

**For LONG Positions**:
- SL: `range_low - (range_size × sl_buffer_pct)` (below range, with buffer)
- If price breaks below range → Exit long position

**For SHORT Positions**:
- SL: `range_high + (range_size × sl_buffer_pct)` (above range, with buffer)
- If price breaks above range → Exit short position

**Purpose**:
- Exits if range breaks (trend change, not mean-reversion)
- Buffer prevents premature exit from range wicks
- Protects capital when range strategy fails

**Common Values**:
- `0.001` (0.1%): Tight, quick exit on break
- `0.002` (0.2%): Balanced, recommended
- `0.003` (0.3%): Wider, more room for range wicks

**Notes**:
- Expressed as decimal (0.002 = 0.2%)
- Lower values = tighter stop, faster exit
- Higher values = wider stop, more room for range volatility

---

#### `kline_interval` (string, optional, default: "5m")
**Description**: The candlestick interval used for range detection and trading.

**Valid Values**: 
- `"1m"`, `"3m"`, `"5m"`, `"15m"`, `"30m"`
- `"1h"`, `"2h"`, `"4h"`, `"6h"`, `"8h"`, `"12h"`, `"1d"`

**Default**: `"5m"` (5-minute candles)

**Example**: `"5m"` = Use 5-minute candlesticks

**How It Works**:
- Strategy analyzes candlestick data to detect ranges
- Uses closing prices, highs, and lows from candles
- Only processes closed candles

**Common Values**:
- `"5m"`: Standard, good balance of signals and noise reduction
- `"15m"`: Medium-term, fewer but more stable ranges
- `"1h"`: Long-term, very stable but fewer opportunities

**Notes**:
- Requires at least `lookback_period + 10` candles of data
- For 5m interval with lookback=150: needs 150 × 5 = 750 minutes (12.5 hours)
- Invalid intervals default to `"5m"`

---

#### `enable_short` (boolean, optional, default: true)
**Description**: Enable short trading in range strategy.

**Default**: `true`

**Example**: `true` = Allow both long and short positions

**How It Works**:

**When `true`**:
- Strategy can enter SHORT positions at range top
- Strategy can enter LONG positions at range bottom
- Both directions are traded

**When `false`**:
- Strategy only enters LONG positions at range bottom
- No short trading

**Use Cases**:
- `true`: Capture both range bounces (recommended)
- `false`: Only trade long bounces (safer for beginners)

---

## Recommended Configurations

### EMA Scalping Strategy Configurations

#### Aggressive Scalping (1m, High Frequency)
```json
{
  "name": "Aggressive BTC Scalper",
  "strategy_type": "scalping",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
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
}
```
- Fast EMAs for quick signals
- Tight TP/SL for quick profits
- Short cooldown for frequent trading

#### Balanced Scalping (1m, Standard)
```json
{
  "name": "BTC Scalping Bot",
  "strategy_type": "scalping",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
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
}
```
- Default configuration
- Good balance of signals and quality
- Recommended for most users

#### Conservative Scalping (5m, Lower Frequency)
```json
{
  "name": "Conservative ETH Trader",
  "strategy_type": "scalping",
  "symbol": "ETHUSDT",
  "leverage": 3,
  "risk_per_trade": 0.005,
  "params": {
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
}
```
- Slower EMAs for stronger trends
- Wider TP/SL for more room
- Longer cooldown for fewer trades

### Range Mean-Reversion Strategy Configurations

#### Standard Range Trading (5m)
```json
{
  "name": "BTC Range Trader",
  "strategy_type": "range_mean_reversion",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
    "lookback_period": 150,
    "buy_zone_pct": 0.2,
    "sell_zone_pct": 0.2,
    "kline_interval": "5m",
    "rsi_period": 14,
    "rsi_oversold": 40,
    "rsi_overbought": 60,
    "enable_short": true
  }
}
```
- Standard configuration
- Good for most ranging markets
- Recommended starting point

#### Conservative Range Trading (15m)
```json
{
  "name": "ETH Conservative Range",
  "strategy_type": "range_mean_reversion",
  "symbol": "ETHUSDT",
  "leverage": 3,
  "risk_per_trade": 0.005,
  "params": {
    "lookback_period": 200,
    "buy_zone_pct": 0.15,
    "sell_zone_pct": 0.15,
    "kline_interval": "15m",
    "max_ema_spread_pct": 0.003,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "enable_short": true
  }
}
```
- Longer timeframe for stability
- Stricter filters for higher-quality signals
- Lower risk per trade

---

## Troubleshooting

### Strategy Not Trading

**Problem**: Strategy created but no trades executed.

**Check**:
1. Is strategy started? (`auto_start=true` or call `/start` endpoint)
2. Enough data? Need at least `ema_slow` (EMA) or `lookback_period` (Range) candles
3. Filters too strict? Check `min_ema_separation`, `max_ema_spread_pct`, etc.
4. Cooldown active? Check if recently exited (EMA strategy)

### Too Many False Signals (EMA Strategy)

**Problem**: Strategy enters and exits positions too frequently.

**Solutions**:
- Increase `min_ema_separation` (e.g., `0.0003`)
- Increase `cooldown_candles` (e.g., `3-5`)
- Use slower EMAs (e.g., `12/26` instead of `8/21`)
- Use higher timeframe (e.g., `5m` instead of `1m`)

### No Range Detected (Range Strategy)

**Problem**: Strategy not detecting valid ranges.

**Check**:
1. Market trending? Check `max_ema_spread_pct` - may need to increase
2. Too volatile? Check `max_atr_multiplier` - may need to increase
3. Enough data? Need at least `lookback_period + 10` candles
4. Market actually ranging? Strategy only works in sideways markets

### Missing Signals

**Problem**: Strategy not entering when it should.

**Solutions**:
- Decrease `min_ema_separation` (EMA) or increase `buy_zone_pct`/`sell_zone_pct` (Range)
- Decrease `cooldown_candles` (EMA)
- Check if `enable_short=false` is blocking shorts
- Verify `interval_seconds` is frequent enough

### Stop Loss Hit Too Often

**Problem**: Positions stopped out before reaching TP.

**Solutions**:
- Increase `stop_loss_pct` (EMA) or `sl_buffer_pct` (Range)
- Use wider TP/SL ratio (e.g., TP `0.006`, SL `0.002` = 3:1)
- Use higher timeframe (less noise)
- Check if market is too volatile for current settings

---

## Additional Resources

- [API Documentation](API_USAGE.md) - Complete API documentation
- [Strategy Examples](STRATEGY_EXAMPLES.md) - Strategy examples and scenarios
- [API Range Mean-Reversion Example](API_RANGE_MEAN_REVERSION_EXAMPLE.md) - Step-by-step guide for creating range_mean_reversion strategies via Swagger UI
- [README.md](README.md) - Project overview and setup

---

## Quick API Request Examples

### Creating a Range Mean-Reversion Strategy via API

**Endpoint**: `POST /strategies/`

**Minimal Request**:
```json
{
  "name": "BTC Range Bot",
  "strategy_type": "range_mean_reversion",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01
}
```

**Full Request with All Parameters**:
```json
{
  "name": "BTC Range Trader",
  "strategy_type": "range_mean_reversion",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "max_positions": 1,
  "auto_start": false,
  "params": {
    "lookback_period": 150,
    "buy_zone_pct": 0.2,
    "sell_zone_pct": 0.2,
    "ema_fast_period": 20,
    "ema_slow_period": 50,
    "max_ema_spread_pct": 0.005,
    "max_atr_multiplier": 2.0,
    "rsi_period": 14,
    "rsi_oversold": 40,
    "rsi_overbought": 60,
    "tp_buffer_pct": 0.001,
    "sl_buffer_pct": 0.002,
    "kline_interval": "5m",
    "enable_short": true
  }
}
```

**How to Use**:
1. Open Swagger UI at `http://127.0.0.1:8000/docs`
2. Find `POST /strategies/` endpoint
3. Click "Try it out"
4. Paste the JSON above
5. Click "Execute"

For detailed step-by-step instructions, see [API_RANGE_MEAN_REVERSION_EXAMPLE.md](API_RANGE_MEAN_REVERSION_EXAMPLE.md)

---

**Last Updated**: Based on strategy implementations in `app/strategies/scalping.py` and `app/strategies/range_mean_reversion.py`
