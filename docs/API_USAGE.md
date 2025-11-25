# API Usage Guide

## Strategies Endpoints

### 1. List All Strategies
**GET** `http://127.0.0.1:8000/strategies/`

Returns an empty array `[]` if no strategies are registered yet.

**Response:**
```json
[]
```

### 2. Create a New Strategy

**POST** `http://127.0.0.1:8000/strategies/`

**Example: Create EMA Crossover Strategy (5 EMA & 20 EMA)**

```json
{
  "name": "BTC EMA Crossover Scalping",
  "symbol": "BTCUSDT",
  "strategy_type": "ema_crossover",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
    "take_profit_pct": 0.005,
    "stop_loss_pct": 0.003,
    "kline_interval": "1m",
    "interval_seconds": 10
  },
  "auto_start": false
}
```

**Example: Create Regular Scalping Strategy**

```json
{
  "name": "ETH Scalping",
  "symbol": "ETHUSDT",
  "strategy_type": "scalping",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {
    "ema_fast": 8,
    "ema_slow": 21,
    "take_profit_pct": 0.004,
    "stop_loss_pct": 0.002,
    "interval_seconds": 10
  },
  "auto_start": false
}
```

**Response:**
```json
{
  "id": "uuid-here",
  "name": "BTC EMA Crossover Scalping",
  "symbol": "BTCUSDT",
  "strategy_type": "ema_crossover",
  "status": "running",
  "leverage": 5,
  "risk_per_trade": 0.01,
  "params": {...},
  "created_at": "2025-11-19T15:30:00",
  "last_signal": "BUY",
  "entry_price": 42005.5,
  "current_price": 42150.0,
  "position_size": 0.001,
  "unrealized_pnl": 0.1445,
  "meta": {}
}
```

### 3. Get Specific Strategy

**GET** `http://127.0.0.1:8000/strategies/{strategy_id}`

### 4. Start a Strategy

**POST** `http://127.0.0.1:8000/strategies/{strategy_id}/start`

### 5. Stop a Strategy

**POST** `http://127.0.0.1:8000/strategies/{strategy_id}/stop`

### 6. Get Strategy Trades (Check if Traded)

**GET** `http://127.0.0.1:8000/strategies/{strategy_id}/trades`

Returns all executed trades for a specific strategy. Returns an empty array `[]` if no trades have been executed yet.

**Response Example:**
```json
[
  {
    "symbol": "BTCUSDT",
    "order_id": 12345678,
    "status": "FILLED",
    "side": "BUY",
    "price": 42000.0,
    "avg_price": 42005.5,
    "executed_qty": 0.001
  },
  {
    "symbol": "BTCUSDT",
    "order_id": 12345679,
    "status": "FILLED",
    "side": "SELL",
    "price": 42100.0,
    "avg_price": 42098.2,
    "executed_qty": 0.001
  }
]
```

**Empty Response (No Trades Yet):**
```json
[]
```

### 7. Get Strategy Statistics (Trade Count & Profit/Loss)

**GET** `http://127.0.0.1:8000/strategies/{strategy_id}/stats`

Returns detailed statistics for a specific strategy including trade count, profit/loss, and win rate.

**Response Example:**
```json
{
  "strategy_id": "b5be6bb0-e63b-4ae4-a31f-32c74dd3cc7c",
  "strategy_name": "STRK EMA Crossover Scalping",
  "symbol": "STRKUSDT",
  "total_trades": 6,
  "completed_trades": 3,
  "total_pnl": 2.45,
  "win_rate": 66.67,
  "winning_trades": 2,
  "losing_trades": 1,
  "avg_profit_per_trade": 0.8167,
  "largest_win": 1.30,
  "largest_loss": -0.15,
  "created_at": "2025-11-19T20:55:02.550857",
  "last_trade_at": "2025-11-19T21:15:30.123456"
}
```

### 8. Get Overall Statistics (All Strategies)

**GET** `http://127.0.0.1:8000/strategies/stats`

Returns overall statistics across all strategies.

**Response Example:**
```json
{
  "total_strategies": 2,
  "active_strategies": 1,
  "total_trades": 12,
  "completed_trades": 5,
  "total_pnl": 4.75,
  "win_rate": 60.0,
  "winning_trades": 3,
  "losing_trades": 2,
  "avg_profit_per_trade": 0.95,
  "best_performing_strategy": "STRK EMA Crossover Scalping",
  "worst_performing_strategy": "BTC Scalping Strategy"
}
```

## Using cURL Examples

### Create EMA Crossover Strategy
```bash
curl -X POST "http://127.0.0.1:8000/strategies/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "BTC EMA Crossover",
    "symbol": "BTCUSDT",
    "strategy_type": "ema_crossover",
    "leverage": 5,
    "risk_per_trade": 0.01,
    "params": {
      "take_profit_pct": 0.005,
      "stop_loss_pct": 0.003,
      "kline_interval": "1m",
      "interval_seconds": 10
    },
    "auto_start": false
  }'
```

### List All Strategies
```bash
curl http://127.0.0.1:8000/strategies/
```

### Start a Strategy
```bash
curl -X POST "http://127.0.0.1:8000/strategies/{strategy_id}/start"
```

### Check if Strategy Has Traded
```bash
curl "http://127.0.0.1:8000/strategies/{strategy_id}/trades"
```

### Get Strategy Statistics
```bash
curl "http://127.0.0.1:8000/strategies/{strategy_id}/stats"
```

### Get Overall Statistics
```bash
curl "http://127.0.0.1:8000/strategies/stats"
```

## Using the Interactive API Docs

Visit `http://127.0.0.1:8000/docs` for Swagger UI where you can:
- See all available endpoints
- Test API calls directly in the browser
- View request/response schemas

## Strategy Types

- `scalping` - General EMA scalping strategy (configurable periods)
- `ema_crossover` - EMA 5/20 Crossover Scalping Strategy
- `futures` - Reserved for future strategies

