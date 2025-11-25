# Candlestick Data Example - 8/21 EMA Strategy

This document shows exactly what the last 21 closed candlesticks look like and how they're used for EMA calculation.

## Data Structure

Each candlestick (kline) from Binance is a list with 12 elements:

```python
[
    open_time,      # [0] Opening time in milliseconds
    open,           # [1] Opening price
    high,           # [2] Highest price during the candle
    low,            # [3] Lowest price during the candle
    close,          # [4] Closing price (THIS IS USED FOR EMA)
    volume,         # [5] Trading volume
    close_time,     # [6] Closing time in milliseconds
    quote_volume,  # [7] Quote asset volume
    trades,         # [8] Number of trades
    taker_buy_base, # [9] Taker buy base volume
    taker_buy_quote,# [10] Taker buy quote volume
    ignore          # [11] Ignore field
]
```

**Important**: The strategy only uses the **closing price** (index [4]) for EMA calculations.

---

## Example: Last 21 Closed Candlesticks for PIPPINUSDT

Here's what the last 21 closed 1-minute candles might look like:

| # | Time | Open | High | Low | Close | Volume |
|---|------|------|------|-----|-------|--------|
| 1 | 10:00:00 | 0.06080 | 0.06090 | 0.06075 | 0.06085 | 125000 |
| 2 | 10:01:00 | 0.06085 | 0.06095 | 0.06080 | 0.06090 | 132000 |
| 3 | 10:02:00 | 0.06090 | 0.06100 | 0.06085 | 0.06095 | 118000 |
| 4 | 10:03:00 | 0.06095 | 0.06105 | 0.06090 | 0.06100 | 145000 |
| 5 | 10:04:00 | 0.06100 | 0.06110 | 0.06095 | 0.06105 | 138000 |
| 6 | 10:05:00 | 0.06105 | 0.06115 | 0.06100 | 0.06110 | 142000 |
| 7 | 10:06:00 | 0.06110 | 0.06120 | 0.06105 | 0.06115 | 150000 |
| 8 | 10:07:00 | 0.06115 | 0.06125 | 0.06110 | 0.06120 | 148000 |
| 9 | 10:08:00 | 0.06120 | 0.06130 | 0.06115 | 0.06125 | 155000 |
| 10 | 10:09:00 | 0.06125 | 0.06135 | 0.06120 | 0.06130 | 160000 |
| 11 | 10:10:00 | 0.06130 | 0.06140 | 0.06125 | 0.06135 | 158000 |
| 12 | 10:11:00 | 0.06135 | 0.06145 | 0.06130 | 0.06140 | 162000 |
| 13 | 10:12:00 | 0.06140 | 0.06150 | 0.06135 | 0.06145 | 165000 |
| 14 | 10:13:00 | 0.06145 | 0.06155 | 0.06140 | 0.06150 | 170000 |
| 15 | 10:14:00 | 0.06150 | 0.06160 | 0.06145 | 0.06155 | 168000 |
| 16 | 10:15:00 | 0.06155 | 0.06165 | 0.06150 | 0.06160 | 172000 |
| 17 | 10:16:00 | 0.06160 | 0.06170 | 0.06155 | 0.06165 | 175000 |
| 18 | 10:17:00 | 0.06165 | 0.06175 | 0.06160 | 0.06170 | 178000 |
| 19 | 10:18:00 | 0.06170 | 0.06180 | 0.06165 | 0.06175 | 180000 |
| 20 | 10:19:00 | 0.06175 | 0.06185 | 0.06170 | 0.06180 | 182000 |
| 21 | 10:20:00 | 0.06180 | 0.06190 | 0.06175 | **0.06184** | 185000 |

**Note**: The strategy uses the **Close** prices from these 21 candles to calculate EMAs.

---

## How Strategy Processes This Data

### Step 1: Extract Closing Prices

Strategy extracts closing prices from the last 21 closed candles:

```python
closing_prices = [
    0.06085,  # Candle 1 close
    0.06090,  # Candle 2 close
    0.06095,  # Candle 3 close
    0.06100,  # Candle 4 close
    0.06105,  # Candle 5 close
    0.06110,  # Candle 6 close
    0.06115,  # Candle 7 close
    0.06120,  # Candle 8 close
    0.06125,  # Candle 9 close
    0.06130,  # Candle 10 close
    0.06135,  # Candle 11 close
    0.06140,  # Candle 12 close
    0.06145,  # Candle 13 close
    0.06150,  # Candle 14 close
    0.06155,  # Candle 15 close
    0.06160,  # Candle 16 close
    0.06165,  # Candle 17 close
    0.06170,  # Candle 18 close
    0.06175,  # Candle 19 close
    0.06180,  # Candle 20 close
    0.06184,  # Candle 21 close (most recent)
]
```

### Step 2: Calculate Fast EMA (8-period)

Strategy calculates 8-period EMA from these closing prices:

```python
# Uses first 8 prices to seed with SMA
sma_8 = (0.06085 + 0.06090 + 0.06095 + 0.06100 + 
         0.06105 + 0.06110 + 0.06115 + 0.06120) / 8
sma_8 = 0.0610125

# Then calculates EMA for remaining prices
smoothing = 2.0 / (8 + 1) = 0.2222

ema_8 = sma_8  # Start with SMA
for price in [0.06125, 0.06130, 0.06135, ..., 0.06184]:
    ema_8 = (price - ema_8) * 0.2222 + ema_8

# Result: Fast EMA ≈ 0.06175
```

### Step 3: Calculate Slow EMA (21-period)

Strategy calculates 21-period EMA from all closing prices:

```python
# Uses first 21 prices to seed with SMA
sma_21 = average of all 21 closing prices
sma_21 ≈ 0.06130

# Then calculates EMA (in this case, we have exactly 21 prices)
smoothing = 2.0 / (21 + 1) = 0.0909

ema_21 = sma_21  # Start with SMA
# For 21 prices, EMA calculation iterates through remaining prices
# (though with exactly 21 prices, it's mostly the SMA)

# Result: Slow EMA ≈ 0.06130
```

### Step 4: Compare with Previous EMAs

Strategy saves previous EMA values to detect crossovers:

```python
# Previous candle's EMAs (calculated from first 20 candles)
prev_fast_ema = 0.06170
prev_slow_ema = 0.06125

# Current candle's EMAs (calculated from all 21 candles)
current_fast_ema = 0.06175
current_slow_ema = 0.06130

# Check for crossover
if prev_fast_ema <= prev_slow_ema and current_fast_ema > current_slow_ema:
    # GOLDEN CROSS → BUY signal
    print("Golden Cross detected!")
elif prev_fast_ema >= prev_slow_ema and current_fast_ema < current_slow_ema:
    # DEATH CROSS → SELL signal
    print("Death Cross detected!")
```

---

## Important Points

### 1. Only Closed Candles Are Used

- Strategy **ignores** the currently forming candle
- Only processes candles that have **closed** (completed their 1-minute period)
- This prevents duplicate signals and ensures accurate calculations

### 2. Minimum Data Requirement

- Strategy needs **at least 21 closed candles** to calculate slow EMA
- With 1-minute interval: Need 21 minutes of data
- Strategy will HOLD until sufficient data is available

### 3. EMA Calculation Method

- **Seeds with SMA**: First EMA value uses Simple Moving Average
- **Then iterates**: Subsequent values use EMA formula
- **Formula**: `EMA = (Price - Previous_EMA) × Smoothing + Previous_EMA`
- **Smoothing**: `2 / (Period + 1)`

### 4. Crossover Detection

- Compares **current EMAs** with **previous EMAs**
- Golden Cross: Fast EMA crosses **above** slow EMA
- Death Cross: Fast EMA crosses **below** slow EMA
- Must be an actual crossover (not just one above/below the other)

---

## How to View Your Actual Data

### Option 1: Use the Python Script

Run the provided script to see your actual candlestick data:

```bash
python view_candles_example.py PIPPINUSDT 1m
```

This will:
- Fetch the last 31 candles from Binance
- Show the last 21 closed candles
- Calculate and display the EMAs
- Show crossover detection status

### Option 2: Check Strategy Logs

The strategy logs EMA values on each evaluation:

```
[ strategy_id ] close=0.06184 fast_ema=0.06175 slow_ema=0.06130 
               prev_fast=0.06170 prev_slow=0.06125
```

### Option 3: Use Binance API Directly

You can fetch klines directly using Binance API:

```python
from binance.client import Client

client = Client(api_key="your_key", api_secret="your_secret", testnet=True)
klines = client.futures_klines(symbol="PIPPINUSDT", interval="1m", limit=31)

# Show last 21 closed candles
for kline in klines[-22:-1]:  # Exclude last (forming) candle
    close_price = float(kline[4])
    close_time = datetime.fromtimestamp(int(kline[6]) / 1000)
    print(f"{close_time}: {close_price}")
```

---

## Example Calculation Walkthrough

Let's say you have these closing prices from the last 21 minutes:

```
[0.06080, 0.06085, 0.06090, 0.06095, 0.06100, 0.06105, 0.06110, 0.06115,
 0.06120, 0.06125, 0.06130, 0.06135, 0.06140, 0.06145, 0.06150, 0.06155,
 0.06160, 0.06165, 0.06170, 0.06175, 0.06184]
```

**Fast EMA (8-period)**:
1. First 8 prices: `[0.06080, ..., 0.06115]` → SMA = 0.0609875
2. EMA smoothing = 2/(8+1) = 0.2222
3. Iterate through remaining prices:
   - Price 9 (0.06120): EMA = (0.06120 - 0.0609875) × 0.2222 + 0.0609875 = 0.061035
   - Price 10 (0.06125): EMA = (0.06125 - 0.061035) × 0.2222 + 0.061035 = 0.061083
   - ... continue for all 21 prices
   - Final Fast EMA ≈ **0.06175**

**Slow EMA (21-period)**:
1. All 21 prices → SMA = 0.06130
2. EMA smoothing = 2/(21+1) = 0.0909
3. With exactly 21 prices, EMA ≈ SMA
4. Final Slow EMA ≈ **0.06130**

**Crossover Check**:
- If previous Fast EMA was 0.06170 and previous Slow EMA was 0.06125
- Current Fast EMA = 0.06175, Current Slow EMA = 0.06130
- Fast EMA (0.06175) > Slow EMA (0.06130) ✅
- Previous: Fast (0.06170) > Slow (0.06125) ✅
- **No crossover** (both are above, no crossing occurred)

---

## Summary

- **Data Source**: Last 21 closed 1-minute candlesticks
- **Price Used**: Closing price (index [4] of each kline)
- **Calculation**: EMA seeded with SMA, then iterated
- **Detection**: Compares current EMAs with previous EMAs
- **Signal**: Only on actual crossovers (golden/death cross)

The strategy checks this every 10 seconds, but only processes when a new candle closes!


