# When Will a Position Be Created?

## Your Configuration Summary

- **Symbol**: PIPPINUSDT
- **Current Price**: 0.06084
- **Strategy**: Scalping with EMA 8/21
- **Kline Interval**: 1 minute
- **Fixed Amount**: 10,000 USDT per position
- **Enable Short**: Yes
- **Filters**: min_ema_separation=0.0002, enable_htf_bias=true, cooldown_candles=2

---

## Position Creation Conditions

A position will be created when **ALL** of the following conditions are met:

### 1. ✅ Sufficient Historical Data (Minimum 21 minutes)

**Requirement**: Strategy needs at least **21 closed 1-minute candles** to calculate the slow EMA (21-period).

**Timeline**:
- Strategy starts collecting data when you start it
- Needs minimum: **21 closed candles** = **21 minutes** of data
- Strategy checks every **10 seconds** (`interval_seconds: 10`)
- First possible signal: **After 21 minutes** (if crossover occurs)

**Status Check**:
- If strategy just started: Wait ~21 minutes for data collection
- If strategy has been running: Should already have data

---

### 2. ✅ EMA Crossover Event

The strategy only creates positions on **crossover events**, not just price movements.

#### For LONG Position (BUY):
**Golden Cross**: Fast EMA (8) crosses **above** slow EMA (21)
- Previous candle: `fast_ema ≤ slow_ema`
- Current closed candle: `fast_ema > slow_ema`
- **Result**: BUY signal → Long position created

#### For SHORT Position (SELL):
**Death Cross**: Fast EMA (8) crosses **below** slow EMA (21)
- Previous candle: `fast_ema ≥ slow_ema`
- Current closed candle: `fast_ema < slow_ema`
- **Result**: SELL signal → Short position created

**Important**: 
- Strategy only processes **closed candles** (not the forming candle)
- Crossover must happen between two consecutive closed candles
- Current price (0.06084) alone doesn't create a position - it needs a crossover

---

### 3. ✅ Filter Checks Must Pass

#### Filter 1: Minimum EMA Separation
**Requirement**: `|fast_ema - slow_ema| / price ≥ 0.0002` (0.02%)

**Example**:
- Price: 0.06084
- Fast EMA: 0.06090
- Slow EMA: 0.06085
- Separation: |0.06090 - 0.06085| / 0.06084 = 0.000082 (0.0082%)
- **Result**: ❌ BLOCKED (0.0082% < 0.02% required)

**If separation is too small**: Position creation is blocked (noise filter)

#### Filter 2: Higher-Timeframe Bias (For Shorts Only)
**Requirement**: If entering SHORT, 5-minute trend must be DOWN

**Check**:
- Strategy calculates 5m fast EMA and 5m slow EMA
- If 5m fast EMA ≥ 5m slow EMA: ❌ Short blocked (5m trend is up)
- If 5m fast EMA < 5m slow EMA: ✅ Short allowed (5m trend is down)

**Note**: This filter **only applies to SHORT entries**, not long entries.

#### Filter 3: Cooldown Period
**Requirement**: No cooldown active (or cooldown = 0)

**How it works**:
- After closing a position, cooldown starts: `cooldown_candles = 2`
- Strategy waits **2 closed candles** before allowing new entry
- If you just closed a position: Wait 2 minutes (2 × 1-minute candles)

**Status**:
- If no recent exit: ✅ No cooldown
- If just exited: Wait 2 candles before new entry

---

### 4. ✅ No Existing Position

**Requirement**: `max_positions = 1` means only one position at a time

**Check**:
- If you already have a LONG position: No new long entry (but can exit)
- If you already have a SHORT position: No new short entry (but can exit)
- If position is None: ✅ Can create new position

---

## Timeline Example

### Scenario: Strategy Just Started

```
Time    Action                          Status
----------------------------------------------------------
00:00   Strategy started                Collecting data
00:01   First candle closes             Data: 1/21 candles
00:02   Second candle closes            Data: 2/21 candles
...
00:20   20th candle closes              Data: 20/21 candles
00:21   21st candle closes              ✅ Data ready (21/21)
00:21   Strategy evaluates              Checking for crossover...
00:21   No crossover yet                 HOLD (waiting for signal)
00:22   22nd candle closes               ✅ Crossover detected!
00:22   Filters check                    ✅ All filters pass
00:22   Position created!                BUY or SELL executed
```

### Scenario: Strategy Already Running

```
Time    Action                          Status
----------------------------------------------------------
Now    Strategy running                 Has historical data
Now    Strategy checks every 10s        Waiting for new closed candle
Next   New 1m candle closes             Strategy processes it
Next   Crossover detected?              If yes → Check filters
Next   Filters pass?                    If yes → Create position
```

---

## How to Check Current Status

### 1. Check Strategy Status
```bash
GET /strategies/{strategy_id}
```

**Response shows**:
- `status`: "running" or "stopped"
- `last_signal`: Last signal generated
- `position_size`: Current position (0 if none)
- `entry_price`: Entry price if position exists

### 2. Check Logs
Look for log messages:
- `"HOLD: Insufficient data"` → Need more candles
- `"HOLD: Cooldown active"` → Waiting for cooldown
- `"HOLD: EMA separation too small"` → Filter blocking
- `"Golden Cross"` or `"Death Cross"` → Crossover detected
- `"SIGNAL => BUY"` or `"SIGNAL => SELL"` → Position created

### 3. Monitor EMAs
The strategy logs EMA values:
```
close=0.06084 fast_ema=0.06090 slow_ema=0.06085 prev_fast=0.06088 prev_slow=0.06086
```

**Interpretation**:
- If `fast_ema > slow_ema` and `prev_fast ≤ prev_slow`: Golden cross → BUY
- If `fast_ema < slow_ema` and `prev_fast ≥ prev_slow`: Death cross → SELL

---

## Expected Position Details (When Created)

### If LONG Position Created:
- **Entry Price**: Price at crossover (e.g., 0.06084)
- **Position Size**: 10,000 USDT / 0.06084 = ~164,366 PIPPIN tokens
- **Take Profit**: 0.06084 × 1.004 = **0.06108** (+0.4%)
- **Stop Loss**: 0.06084 × 0.998 = **0.06072** (-0.2%)
- **Exit Conditions**: 
  - Price reaches 0.06108 (TP)
  - Price drops to 0.06072 (SL)
  - Death cross occurs (fast EMA crosses below slow EMA)

### If SHORT Position Created:
- **Entry Price**: Price at crossover (e.g., 0.06084)
- **Position Size**: 10,000 USDT / 0.06084 = ~164,366 PIPPIN tokens
- **Take Profit**: 0.06084 × 0.996 = **0.06060** (-0.4% from entry)
- **Stop Loss**: 0.06084 × 1.002 = **0.06096** (+0.2% from entry)
- **Exit Conditions**:
  - Price drops to 0.06060 (TP)
  - Price rises to 0.06096 (SL)
  - Golden cross occurs (fast EMA crosses above slow EMA)

---

## Common Scenarios

### Scenario 1: "Strategy Started, No Position Yet"
**Possible Reasons**:
1. ✅ **Insufficient data**: Wait 21 minutes for data collection
2. ✅ **No crossover yet**: EMAs haven't crossed (normal)
3. ✅ **Filters blocking**: 
   - EMA separation too small
   - Cooldown active
   - HTF bias blocking short (if trying to short)

**Action**: Wait for crossover event and check filters

### Scenario 2: "Crossover Happened, But No Position"
**Possible Reasons**:
1. ❌ **EMA separation too small**: `min_ema_separation` filter blocking
2. ❌ **Cooldown active**: Recently closed a position (wait 2 candles)
3. ❌ **HTF bias blocking short**: 5m trend is up (for short entries)
4. ❌ **Already have position**: `max_positions=1` prevents new entry

**Action**: Check logs for specific filter message

### Scenario 3: "Position Created Successfully"
**What Happened**:
1. ✅ Sufficient data (21+ candles)
2. ✅ Crossover detected (golden or death cross)
3. ✅ All filters passed
4. ✅ No existing position

**Result**: Position created at crossover price with TP/SL set

---

## Quick Checklist

Before a position can be created, verify:

- [ ] Strategy is **started** (`auto_start=true` or `/start` called)
- [ ] At least **21 closed candles** collected (21 minutes for 1m interval)
- [ ] **Crossover occurred** (golden cross for long, death cross for short)
- [ ] **EMA separation** ≥ 0.02% of price
- [ ] **No cooldown** active (or cooldown = 0)
- [ ] **HTF bias check** passed (if entering short, 5m trend must be down)
- [ ] **No existing position** (max_positions=1)

---

## Monitoring Tips

1. **Watch the logs** for EMA values and crossover detection
2. **Check strategy status** via API to see current state
3. **Be patient**: Strategy only trades on crossovers, not every price movement
4. **Understand filters**: They prevent bad trades but may delay entries

---

## Summary

**A position will be created when**:
1. ✅ Strategy has 21+ minutes of data
2. ✅ Fast EMA crosses slow EMA (golden cross = long, death cross = short)
3. ✅ EMA separation ≥ 0.02% (filter passes)
4. ✅ No cooldown active
5. ✅ HTF bias allows it (for shorts, 5m trend must be down)
6. ✅ No existing position

**The current price (0.06084) alone doesn't create a position** - you need an EMA crossover event with all filters passing.

**Expected timeline**: 
- If strategy just started: Wait ~21 minutes + wait for crossover
- If strategy running: Next crossover event (could be minutes to hours)


