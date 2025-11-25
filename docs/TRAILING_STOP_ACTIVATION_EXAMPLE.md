# Trailing Stop Activation Threshold - Usage Guide

## Overview

The `trailing_stop_activation_pct` parameter controls when the trailing stop starts working. It prevents trailing from activating on small price movements, waiting for a clear favorable move before starting to trail.

## How It Works

### Example: 1% Activation Threshold

**Setup:**
- Entry Price: 100,000
- Take Profit: 5% (105,000)
- Stop Loss: 2% (98,000)
- **Activation Threshold: 1%** (101,000)

**Price Movement:**

```
Time    Price     Change    Trailing Status    TP        SL
---------------------------------------------------------------
Entry   100,000   0%        Not Activated      105,000   98,000
T+1     100,500   +0.5%     Not Activated      105,000   98,000 (unchanged)
T+2     100,800   +0.8%     Not Activated      105,000   98,000 (unchanged)
T+3     101,000   +1.0%     ✅ ACTIVATED!      106,050   98,980 (trailing starts)
T+4     101,500   +1.5%     Trailing Active    106,575   99,470 (trailed up)
T+5     102,000   +2.0%     Trailing Active    107,100   99,960 (trailed up)
T+6     101,800   +1.8%     Trailing Active    107,100   99,960 (no change, price down)
T+7     102,500   +2.5%     Trailing Active    107,625   100,450 (trailed up again)
```

## Configuration Examples

### Example 1: 1% Activation (Recommended)

```json
{
  "trailing_stop_enabled": true,
  "trailing_stop_activation_pct": 0.01,
  "take_profit_pct": 0.005,
  "stop_loss_pct": 0.002
}
```

**Behavior:**
- LONG: Trailing starts when price reaches `entry × 1.01` (+1%)
- SHORT: Trailing starts when price reaches `entry × 0.99` (-1%)
- Good balance: Waits for clear move, not too sensitive

### Example 2: 2% Activation (Conservative)

```json
{
  "trailing_stop_enabled": true,
  "trailing_stop_activation_pct": 0.02,
  "take_profit_pct": 0.005,
  "stop_loss_pct": 0.002
}
```

**Behavior:**
- LONG: Trailing starts when price reaches `entry × 1.02` (+2%)
- SHORT: Trailing starts when price reaches `entry × 0.98` (-2%)
- More conservative: Only trails on stronger moves
- Better for volatile markets

### Example 3: 0.5% Activation (Sensitive)

```json
{
  "trailing_stop_enabled": true,
  "trailing_stop_activation_pct": 0.005,
  "take_profit_pct": 0.004,
  "stop_loss_pct": 0.002
}
```

**Behavior:**
- LONG: Trailing starts when price reaches `entry × 1.005` (+0.5%)
- SHORT: Trailing starts when price reaches `entry × 0.995` (-0.5%)
- More sensitive: Trails on smaller moves
- Good for tight scalping

### Example 4: Immediate Trailing (No Threshold)

```json
{
  "trailing_stop_enabled": true,
  "trailing_stop_activation_pct": 0.0,
  "take_profit_pct": 0.004,
  "stop_loss_pct": 0.002
}
```

**Behavior:**
- Trailing starts immediately when position is entered
- Most aggressive: Trails on any favorable move
- May trail on noise/small movements

## Complete Strategy Example

```json
{
  "name": "BTC Trailing Scalping 1% Activation",
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

## When to Use Different Activation Values

| Activation % | Use Case | Best For |
|--------------|----------|----------|
| `0.0` (0%) | Immediate trailing | Very tight scalping, want immediate protection |
| `0.005` (0.5%) | Sensitive trailing | Quick scalping, small moves matter |
| `0.01` (1%) | Balanced (recommended) | Most trading scenarios, good balance |
| `0.02` (2%) | Conservative | Volatile markets, want stronger confirmation |
| `0.03-0.05` (3-5%) | Very conservative | Swing trading, longer timeframes |

## Important Notes

1. **Activation is one-time**: Once threshold is reached, trailing continues even if price drops back
2. **Only activates in favorable direction**: 
   - LONG: Only activates when price goes UP
   - SHORT: Only activates when price goes DOWN
3. **TP/SL remain fixed until activation**: Before activation, TP/SL stay at entry-based levels
4. **After activation, trailing is permanent**: Once activated, trailing continues until position closes

## Logging

When activation threshold is reached, you'll see:

```
TrailingStop activated for LONG: price 101000.00 >= activation 101000.00 (1.00% from entry)
TrailingStop LONG updated: best=101500.00, tp=106575.00, sl=99470.00
```

## Tips

1. **Start with 1%**: Good default for most scenarios
2. **Adjust based on volatility**: Higher volatility → higher activation threshold
3. **Match with TP/SL**: Wider TP/SL (e.g., 1-2%) work better with activation thresholds
4. **Test on testnet**: Always test different activation values before live trading

