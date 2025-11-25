# Dynamic Trailing Stop Loss Guide

## Overview

The Dynamic Trailing Stop Loss is a reusable feature that automatically adjusts take profit (TP) and stop loss (SL) levels as price moves favorably, maintaining constant risk/reward percentages. This helps lock in profits while protecting against reversals.

## How It Works

### Long Positions

**Initial Setup:**
- Entry Price: 100,000
- Take Profit: 105,000 (+5%)
- Stop Loss: 98,000 (-2%)

**As Price Moves Up:**

When price reaches 101,100 (+1.1% from entry):
- **Old** distance to SL: (101,100 - 98,000) / 101,100 ≈ 3%
- **New** SL: 101,100 × 0.98 = **99,078** (-2% from current price)
- **New** TP: 101,100 × 1.05 = **106,155** (+5% from current price)

The trailing stop:
- ✅ **Trails UP** when price moves up (locks in profits)
- ❌ **Never trails DOWN** (protects against giving back profits)

### Short Positions

**Initial Setup:**
- Entry Price: 100,000
- Take Profit: 95,000 (-5% from entry, price must drop)
- Stop Loss: 102,000 (+2% from entry, price must rise)

**As Price Moves Down:**

When price reaches 98,900 (-1.1% from entry):
- **Old** distance to SL: (102,000 - 98,900) / 98,900 ≈ 3.1%
- **New** SL: 98,900 × 1.02 = **100,878** (+2% from current price)
- **New** TP: 98,900 × 0.95 = **93,955** (-5% from current price)

The trailing stop:
- ✅ **Trails DOWN** when price moves down (locks in profits)
- ❌ **Never trails UP** (protects against giving back profits)

## Configuration

### Enable Trailing Stop

Add `trailing_stop_enabled: true` to your strategy parameters:

```json
{
  "name": "BTC Scalping with Trailing Stop",
  "strategy_type": "scalping",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
    "ema_fast": 8,
    "ema_slow": 21,
    "take_profit_pct": 0.004,
    "stop_loss_pct": 0.002,
    "trailing_stop_enabled": true,
    "trailing_stop_activation_pct": 0.01,
    "interval_seconds": 10,
    "kline_interval": "1m"
  },
  "auto_start": false
}
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `trailing_stop_enabled` | boolean | `false` | Enable dynamic trailing stop loss |
| `trailing_stop_activation_pct` | float | `0.0` | Percentage price must move before trailing activates (e.g., 0.01 = 1%). 0 = start immediately |
| `take_profit_pct` | float | `0.004` | Take profit percentage (0.004 = 0.4%) |
| `stop_loss_pct` | float | `0.002` | Stop loss percentage (0.002 = 0.2%) |

**Note**: The trailing stop uses the same `take_profit_pct` and `stop_loss_pct` values to maintain constant risk/reward ratios.

### Activation Threshold

The `trailing_stop_activation_pct` parameter controls when trailing starts:

- **`0.0` (default)**: Trailing starts immediately when position is entered
- **`0.01` (1%)**: Trailing only starts after price moves 1% in favorable direction
  - LONG: Price must reach `entry * 1.01` before trailing activates
  - SHORT: Price must reach `entry * 0.99` before trailing activates
- **`0.02` (2%)**: Trailing only starts after price moves 2% in favorable direction

**Why use activation threshold?**
- Prevents trailing from activating on small price movements/noise
- Only trails when there's a clear favorable move
- Reduces premature trailing that might exit too early

## Example Scenario

### Without Trailing Stop (Fixed TP/SL)

```
Entry: 100,000
TP: 105,000 (+5%)
SL: 98,000 (-2%)

Price moves to 104,000 (+4%) → Still holding
Price reverses to 98,000 → STOP LOSS HIT (-2% loss)
```

**Result**: Lost the opportunity despite being up 4% at one point.

### With Trailing Stop (Dynamic TP/SL, No Activation Threshold)

```
Entry: 100,000
Initial TP: 105,000 (+5%)
Initial SL: 98,000 (-2%)
Activation: 0% (starts immediately)

Price moves to 100,500 (+0.5%) → Trailing stop adjusts:
  New TP: 105,525 (+5% from 100,500)
  New SL: 98,490 (-2% from 100,500)

Price moves to 101,000 (+1%) → Trailing stop adjusts:
  New TP: 106,050 (+5% from 101,000)
  New SL: 98,980 (-2% from 101,000)

Price moves to 103,000 (+3%) → Trailing stop adjusts:
  New TP: 108,150 (+5% from 103,000)
  New SL: 100,940 (-2% from 103,000)

Price reverses to 100,950 → STOP LOSS HIT at 100,940 (+0.94% profit)
```

**Result**: Locked in profit instead of giving it all back!

### With Trailing Stop (1% Activation Threshold)

```
Entry: 100,000
Initial TP: 105,000 (+5%)
Initial SL: 98,000 (-2%)
Activation: 1% (price must reach 101,000)

Price moves to 100,500 (+0.5%) → Trailing NOT activated yet
  TP: 105,000 (unchanged)
  SL: 98,000 (unchanged)

Price moves to 101,000 (+1%) → ✅ TRAILING ACTIVATED!
  New TP: 106,050 (+5% from 101,000)
  New SL: 98,980 (-2% from 101,000)

Price moves to 103,000 (+3%) → Trailing stop adjusts:
  New TP: 108,150 (+5% from 103,000)
  New SL: 100,940 (-2% from 103,000)

Price reverses to 100,950 → STOP LOSS HIT at 100,940 (+0.94% profit)
```

**Result**: Trailing only started after 1% move, avoiding noise from small movements!

## Implementation Details

### Reusable Component

The trailing stop is implemented as `TrailingStopManager` in `app/strategies/trailing_stop.py`, making it reusable across all strategies.

### Integration

The trailing stop manager:
1. **Initializes** when a position is entered
2. **Updates** on each price evaluation (every `interval_seconds`)
3. **Checks** for TP/SL exits automatically
4. **Resets** when position is closed

### Strategy Support

Currently integrated into:
- ✅ `EmaScalpingStrategy` (scalping)

Can be easily added to any strategy by:
1. Importing `TrailingStopManager`
2. Initializing on position entry
3. Calling `update()` and `check_exit()` on each evaluation

## Use Cases

### ✅ Good For:
- Trending markets where price moves favorably
- Locking in profits during strong moves
- Reducing risk as position becomes profitable
- Strategies with wider TP/SL (better trailing effect)

### ❌ May Not Be Ideal For:
- Very tight scalping (trailing may trigger too early)
- Highly volatile markets (may trigger on noise)
- Very short timeframes (not enough price movement)

## Example API Request

### Example 1: Trailing Stop with 1% Activation

```bash
POST http://127.0.0.1:8000/strategies/
Content-Type: application/json

{
  "name": "BTC Trailing Scalping (1% Activation)",
  "strategy_type": "scalping",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
    "ema_fast": 8,
    "ema_slow": 21,
    "take_profit_pct": 0.005,
    "stop_loss_pct": 0.002,
    "trailing_stop_enabled": true,
    "trailing_stop_activation_pct": 0.01,
    "interval_seconds": 10,
    "kline_interval": "1m",
    "enable_short": true
  },
  "auto_start": false
}
```

### Example 2: Trailing Stop with 2% Activation

```bash
POST http://127.0.0.1:8000/strategies/
Content-Type: application/json

{
  "name": "BTC Trailing Scalping (2% Activation)",
  "strategy_type": "scalping",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
    "ema_fast": 8,
    "ema_slow": 21,
    "take_profit_pct": 0.005,
    "stop_loss_pct": 0.002,
    "trailing_stop_enabled": true,
    "trailing_stop_activation_pct": 0.02,
    "interval_seconds": 10,
    "kline_interval": "1m"
  },
  "auto_start": false
}
```

### Example 3: Immediate Trailing (No Activation Threshold)

```bash
POST http://127.0.0.1:8000/strategies/
Content-Type: application/json

{
  "name": "BTC Trailing Scalping (Immediate)",
  "strategy_type": "scalping",
  "symbol": "BTCUSDT",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
    "ema_fast": 8,
    "ema_slow": 21,
    "take_profit_pct": 0.005,
    "stop_loss_pct": 0.002,
    "trailing_stop_enabled": true,
    "trailing_stop_activation_pct": 0.0,
    "interval_seconds": 10,
    "kline_interval": "1m"
  },
  "auto_start": false
}
```

## Logging

When trailing stop is enabled, you'll see logs like:

```
TrailingStop initialized: entry=100000.00, tp=105000.00, sl=98000.00, type=LONG, enabled=True
TrailingStop LONG updated: best=101100.00, tp=106155.00, sl=99078.00
Long Take profit hit (trailing): 106155.00 >= 106155.00
```

## Tips

1. **Start with wider TP/SL**: Trailing stop works better with more room (e.g., 1-2% SL, 3-5% TP)
2. **Monitor performance**: Compare results with/without trailing stop for your symbols
3. **Combine with filters**: Use existing filters (cooldown, EMA separation) for better entries
4. **Test on testnet**: Always test new configurations on testnet first

## Technical Details

### Trailing Logic

- **LONG**: Only trails when `current_price > best_price` (locks in higher profits)
- **SHORT**: Only trails when `current_price < best_price` (locks in higher profits)
- **Never reverses**: Once TP/SL is trailed up/down, it never moves back

### Price Tracking

The manager tracks:
- `best_price`: Highest price reached (LONG) or lowest price reached (SHORT)
- `current_tp`: Current take profit level
- `current_sl`: Current stop loss level

These are recalculated on each price update, maintaining constant percentage distances from `best_price`.

