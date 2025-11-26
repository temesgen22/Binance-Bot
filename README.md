# Binance FastAPI Trading Bot

A customizable trading bot built with Python and FastAPI, designed to support multiple cryptocurrencies and integrate directly with Binance. The bot allows you to fully customize scalping and futures trading strategies, automate buy and sell orders, and implement precise risk-management rules based on your trading plan.

## Features

- **FastAPI Backend**: RESTful API with typed request/response models and automatic OpenAPI documentation
- **Binance Integration**: Direct integration with Binance Futures API (supports testnet and production)
- **Strategy Framework**: Pluggable strategy system with base classes for easy customization
- **Multiple Trading Strategies**: 
  - **EmaScalpingStrategy** (`scalping`): Configurable EMA crossover with long/short support, advanced filters, and state management
  - **EmaCrossoverScalpingStrategy** (`ema_crossover`): Alias for EmaScalpingStrategy (use `scalping` with `ema_fast=5, ema_slow=20`)
- **Long & Short Trading**: Support for both long and short positions with inverted TP/SL for shorts
- **Advanced Filters**: 
  - Minimum EMA separation filter (default 0.02% of price) to reduce noise
  - Higher-timeframe bias (5m trend check for shorts when using 1m interval)
  - Cooldown period after exits (default 2 candles) to prevent flip-flops
- **Risk Management**: Centralized risk management with position sizing, leverage caps, and per-trade risk limits
- **Multiple Cryptocurrencies**: Support for trading multiple symbols simultaneously
- **Background Execution**: Strategy runner with graceful start/stop and concurrent strategy support
- **Trade Tracking**: Redis-based trade storage with comprehensive statistics
- **Structured Logging**: Comprehensive logging with Loguru for debugging and monitoring
- **Web-Based Log Viewer**: Interactive GUI for viewing and filtering bot logs with real-time updates
- **Type Safety**: Full type hints and Pydantic models for validation
- **Comprehensive Testing**: 70+ tests covering critical functions, strategy behavior, log viewer GUI, and integration scenarios

## Prerequisites

- Python 3.11 or higher
- Binance API credentials (API Key and Secret)
- pip package manager

## Installation

1. **Clone or navigate to the project directory**
   ```bash
   cd "C:\Users\teme2\Binance Bot"
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   
   Or install in development mode:
   ```bash
   pip install -e .
   ```

3. **Configure environment variables**
   
   Copy the example environment file:
   ```bash
   copy env.example .env
   ```
   
   Edit `.env` and add your Binance API credentials:
   ```env
   BINANCE_API_KEY=your_api_key_here
   BINANCE_API_SECRET=your_api_secret_here
   BINANCE_TESTNET=true
   BASE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
   DEFAULT_LEVERAGE=5
   RISK_PER_TRADE=0.01
   MAX_CONCURRENT_STRATEGIES=5
   API_PORT=8000
   ```
   
   **Note**: `BASE_SYMBOLS` accepts comma-separated values (e.g., `BTCUSDT,ETHUSDT,SOLUSDT`) or JSON array format (e.g., `["BTCUSDT","ETHUSDT"]`).

4. **Run the API server**
   ```bash
   uvicorn app.main:app --reload
   ```
   
   The API will be available at `http://127.0.0.1:8000`
   
   View interactive API documentation at:
   - Swagger UI: `http://127.0.0.1:8000/docs`
   - ReDoc: `http://127.0.0.1:8000/redoc`

   Access the Log Viewer GUI at:
   - Log Viewer: `http://127.0.0.1:8000/` or `http://127.0.0.1:8000/static/index.html`

## Log Viewer GUI

The bot includes a web-based GUI for viewing and filtering logs in real-time. The interface provides:

- **Multi-Filter Support**: Filter by cryptocurrency symbol, log level, date range, module, function, and custom search text
- **Real-Time Updates**: Auto-refresh option to monitor logs as they're generated
- **Color-Coded Logs**: Visual distinction between DEBUG, INFO, WARNING, ERROR, and CRITICAL logs
- **Export Functionality**: Export filtered logs as text files
- **Interactive Features**: Click any log entry to copy it to clipboard

For detailed documentation, see [docs/LOG_VIEWER.md](docs/LOG_VIEWER.md).

## Docker Deployment

### 1. Build the image

```bash
docker build -t binance-bot .
```

### 2. Run with Docker

```bash
docker run --env-file .env -p 8000:8000 binance-bot
```

### 3. Run with Docker Compose (recommended)

```bash
docker compose up --build
```

The service will start automatically. Once running, access:
- **Log Viewer GUI**: `http://localhost:8000/`
- **API Documentation**: `http://localhost:8000/docs`
- **Health Check**: `http://localhost:8000/health`

**Note**: The service starts automatically when the container starts - no manual command needed!
```

> **Note:** When running with Docker Compose, ensure `REDIS_URL` in `.env` points to the internal service, e.g. `REDIS_URL=redis://redis:6379/0`.

## CI/CD with Jenkins

The project includes a complete Jenkins CI/CD pipeline. **See [docs/JENKINS_SETUP.md](docs/JENKINS_SETUP.md) for detailed setup instructions.**

### Quick Start

1. **Prerequisites on Jenkins Agent** (see [setup guide](docs/JENKINS_SETUP.md)):
   - Python 3.11+ installed
   - Docker installed and running
   - Jenkins user added to docker group

2. **Create Jenkins Pipeline**:
   - Create new Pipeline job in Jenkins
   - Choose "Pipeline script from SCM"
   - Repository: `https://github.com/temesgen22/Binance-Bot.git`
   - Script Path: `Jenkinsfile`

3. **Pipeline Stages**:
   - ✅ Check prerequisites (Python, Docker) - **NEW: detects missing tools**
   - ✅ Checkout code from GitHub
   - ✅ Set up Python virtual environment
   - ✅ Run tests (71 tests)
   - ✅ Build Docker image
   - ✅ Push Docker image (optional, if registry configured)

### Troubleshooting

**If you see errors like:**
- `python3: not found` → Install Python 3.11+ (see [setup guide](docs/JENKINS_SETUP.md))
- `docker: not found` → Install Docker (see [setup guide](docs/JENKINS_SETUP.md))
- `Docker daemon is not running` → **See [Docker Daemon Fix Guide](docs/JENKINS_DOCKER_FIX.md)**
- `docker: command not found` in Jenkins container → **See [Docker-in-Docker Guide](docs/JENKINS_DOCKER_IN_DOCKER.md)**
- `permission denied` accessing Docker socket → **See [Docker Permissions Fix](docs/JENKINS_DOCKER_PERMISSIONS.md)** or run `.\fix-jenkins-docker.ps1`
- `permission denied` → Add Jenkins user to docker group (see [setup guide](docs/JENKINS_SETUP.md))

**For complete troubleshooting, see [docs/JENKINS_SETUP.md](docs/JENKINS_SETUP.md)**

### Optional: Docker Registry Push

To push images to a registry:
1. Create Jenkins credential (Username/Password) for your Docker registry
2. Set environment variables in Jenkins job:
   - `DOCKER_REGISTRY_URL` (e.g., `registry.hub.docker.com/username`)
   - `DOCKER_REGISTRY_CREDENTIALS_ID` (your credential ID)

### Optional: Deploy to Cloud Server

The pipeline includes automatic deployment to your cloud server via SSH. See [docs/JENKINS_DEPLOYMENT.md](docs/JENKINS_DEPLOYMENT.md) for complete setup instructions.

**Quick setup:**
1. Create SSH credentials in Jenkins
2. Set environment variables:
   - `DEPLOY_ENABLED = 'true'`
   - `DEPLOY_SSH_CREDENTIALS_ID = 'your-ssh-credential-id'`
   - `DEPLOY_SSH_HOST = 'your-server-ip'`
   - `DEPLOY_SSH_PORT = '22'` (optional)
   - `DEPLOY_PATH = '/opt/binance-bot'` (optional)
3. Run pipeline - it will automatically deploy after successful build!

## API Endpoints

### Health Check
- `GET /health` – Check API uptime and Binance connection status

### Strategy Management
- `GET /strategies` – List all registered strategies
- `POST /strategies` – Create and register a new strategy configuration
  ```json
  {
    "name": "my_scalping_strategy",
    "strategy_type": "scalping",
    "symbol": "BTCUSDT",
    "leverage": 5,
    "risk_per_trade": 0.01,
    "fixed_amount": null,
    "max_positions": 1,
    "params": {
      "ema_fast": 8,
      "ema_slow": 21,
      "take_profit_pct": 0.004,
      "stop_loss_pct": 0.002,
      "interval_seconds": 10,
      "kline_interval": "1m",
      "enable_short": true,
      "min_ema_separation": 0.0002,
      "enable_htf_bias": true,
      "cooldown_candles": 2
    },
    "auto_start": false
  }
  ```
- `POST /strategies/{strategy_id}/start` – Start a strategy (begins trading)
- `POST /strategies/{strategy_id}/stop` – Stop a strategy (halts trading and closes positions)
- `GET /strategies/{strategy_id}` – Get details about a specific strategy
- `GET /strategies/{strategy_id}/trades` – Get all executed trades for a strategy
- `GET /strategies/{strategy_id}/stats` – Get detailed statistics (trade count, PnL, win rate) for a strategy
- `GET /strategies/stats` – Get overall statistics across all strategies

### Available Strategy Types

1. **`scalping`** - EmaScalpingStrategy
   - **Data Source**: Uses closed candlestick data (klines) from Binance - only processes new closed candles to avoid duplicate signals
   - **EMA Calculation**: Configurable EMA periods (default: 8 fast / 21 slow, range: 1-200 fast, 2-400 slow)
   - **Trading Logic**:
     - **Long Entry**: Golden cross (fast EMA crosses above slow EMA)
     - **Long Exit**: Death cross (fast EMA crosses below slow EMA) or TP/SL hit
     - **Short Entry**: Death cross (when `enable_short=true`) with optional 5m trend filter
     - **Short Exit**: Golden cross or TP/SL hit
   - **Risk Management**:
     - Take profit: `entry_price * (1 + take_profit_pct)` for longs, `entry_price * (1 - take_profit_pct)` for shorts
     - Stop loss: `entry_price * (1 - stop_loss_pct)` for longs, `entry_price * (1 + stop_loss_pct)` for shorts
   - **Configurable Kline Interval**: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d` (default: `1m`)
   - **Advanced Filters**:
     - `min_ema_separation`: Minimum EMA separation filter (default: 0.0002 = 0.02% of price) - only applies to new entries
     - `enable_htf_bias`: Higher timeframe bias - checks 5m trend for shorts when using 1m interval (default: true)
     - `cooldown_candles`: Candles to wait after exit before new entry (default: 2, range: 0-10)
   - **Parameters**:
     - `ema_fast`: Fast EMA period (default: 8)
     - `ema_slow`: Slow EMA period (default: 21)
     - `take_profit_pct`: Take profit percentage (default: 0.004 = 0.4%)
     - `stop_loss_pct`: Stop loss percentage (default: 0.002 = 0.2%)
     - `kline_interval`: Candlestick interval (default: "1m")
     - `enable_short`: Enable short trading (default: true)
     - `interval_seconds`: Strategy evaluation interval in seconds (default: 10)

2. **`ema_crossover`** - EmaCrossoverScalpingStrategy (Alias)
   - This is an alias for `scalping` strategy
   - For 5/20 EMA crossover, use `scalping` with `ema_fast=5, ema_slow=20`

See the [docs/](docs/) directory for detailed examples, API documentation, and comprehensive guides to all strategy parameters.

## Configuration

### Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `BINANCE_API_KEY` | Your Binance API key | `demo` | `your_api_key` |
| `BINANCE_API_SECRET` | Your Binance API secret | `demo` | `your_api_secret` |
| `BINANCE_TESTNET` | Use Binance testnet | `true` | `true` or `false` |
| `BASE_SYMBOLS` | Comma-separated trading symbols | `BTCUSDT,ETHUSDT` | `BTCUSDT,ETHUSDT,SOLUSDT` |
| `DEFAULT_LEVERAGE` | Default leverage for futures | `5` | `10` |
| `RISK_PER_TRADE` | Risk percentage per trade | `0.01` | `0.02` (2%) |
| `MAX_CONCURRENT_STRATEGIES` | Max strategies running simultaneously | `3` | `5` |
| `API_PORT` | FastAPI server port | `8000` | `8080` |

## Project Structure

```
Binance Bot/
├── app/
│   ├── api/              # FastAPI routes and dependencies
│   │   └── routes/        # API endpoint handlers
│   ├── core/              # Core configuration and Binance client
│   │   ├── binance.py     # Binance API client
│   │   ├── config.py      # Configuration management
│   │   ├── logger.py      # Logging setup
│   │   └── redis_storage.py  # Redis trade storage
│   ├── risk/              # Risk management module
│   ├── schemas/           # Pydantic models for API
│   ├── services/          # Business logic (order execution, strategy runner)
│   ├── strategies/        # Trading strategy implementations
│   │   ├── base.py        # Base Strategy class
│   │   └── scalping.py    # EmaScalpingStrategy implementation
│   └── main.py            # FastAPI application entry point
├── tests/                 # Comprehensive test suite
│   ├── test_critical_functions.py  # Critical function tests (19 tests)
│   ├── test_strategy_scalping.py   # Strategy behavior tests (20 tests)
│   ├── test_strategy_integration.py # Integration tests
│   └── conftest.py        # Test fixtures
├── requirements.txt       # Python dependencies
├── pyproject.toml         # Project metadata and build config
├── env.example            # Environment variables template
├── README.md              # This file
├── API_USAGE.md           # Complete API usage guide
├── STRATEGY_EXAMPLES.md   # Detailed strategy examples
├── STRATEGY_PARAMETERS_MANUAL.md  # Complete parameter reference guide
├── TEST_SUMMARY.md        # Test results and coverage
└── docs/                            # Documentation directory
    ├── API_USAGE.md                 # API usage guide
    ├── STRATEGY_PARAMETERS_MANUAL.md
    ├── TRAILING_STOP_GUIDE.md
    └── ...                          # Other documentation files
└── scripts/                         # Utility scripts
    ├── check_redis.py
    ├── view_candles_example.py
    └── ...                          # Other utility scripts
```

## Creating Custom Strategies

To create your own trading strategy:

1. **Subclass the base Strategy class** in `app/strategies/base.py`:
   ```python
   from app.strategies.base import Strategy, StrategySignal, StrategyContext
   from app.core.my_binance_client import BinanceClient
   
   class MyCustomStrategy(Strategy):
       def __init__(self, context: StrategyContext, client: BinanceClient) -> None:
           super().__init__(context, client)
           # Initialize your strategy parameters from context.params
       
       async def evaluate(self) -> StrategySignal:
           # Your trading logic here
           # Return StrategySignal with action: "BUY", "SELL", "HOLD", or "CLOSE"
           # Include symbol, confidence, and price
           return StrategySignal(
               action="HOLD",
               symbol=self.context.symbol,
               confidence=0.0,
               price=current_price
           )
   ```

2. **Register your strategy** in the `StrategyFactory` (in `app/services/strategy_runner.py`)

3. **Use the API** to create and start your strategy with custom parameters

### Strategy Examples

- **EmaScalpingStrategy**: See `app/strategies/scalping.py` for a complete example with:
  - EMA calculation using closed candlestick data (klines) with proper state management
  - Crossover detection with previous value preservation (prevents duplicate signals)
  - Long and short position support with inverted TP/SL for shorts
  - Advanced filtering logic:
    - Minimum EMA separation filter (only for entries, not exits)
    - Higher-timeframe bias (5m trend check for shorts on 1m interval)
    - Cooldown period after exits
  - Take profit/stop loss management for both long and short positions
  - Duplicate candle detection to avoid reprocessing the same signal

For detailed strategy examples and usage, see the documentation in the [docs/](docs/) directory.

## Risk Management

The bot includes built-in risk management features:

- **Position Sizing**: Automatically calculates position size based on risk percentage or fixed USDT amount (`fixed_amount` parameter)
- **Leverage Limits**: Enforces maximum leverage per strategy (configurable, default: 5, max: 50)
- **Per-Trade Risk**: Configurable risk percentage per trade (default: 0.01 = 1%)
- **Take Profit & Stop Loss**: Configurable TP/SL percentages (default: 0.4% TP, 0.2% SL, inverted for short positions)
- **Max Positions**: Configurable maximum concurrent positions per strategy (default: 1, max: 5)
- **Concurrent Strategy Limits**: Prevents over-trading with max concurrent strategies
- **Advanced Filters**: 
  - Minimum EMA separation threshold (default: 0.02% of price) to avoid noise - only applies to new entries
  - Cooldown period after position exit (default: 2 candles, range: 0-10) to prevent flip-flops
  - Higher-timeframe bias for short positions (checks 5m trend when using 1m interval, default: enabled)

## Testing

The project includes comprehensive test coverage with 38+ tests:

- **Critical Functions Tests** (`test_critical_functions.py`): 19/19 tests passing
  - EMA calculation and validation
  - Crossover detection (golden cross, death cross)
  - State management and preservation
  - Take profit/stop loss calculations (long and short)
  - Filter logic (cooldown, EMA separation)

- **Comprehensive Strategy Tests** (`test_strategy_scalping.py`): 19/20 tests passing
  - Full strategy behavior validation
  - Position tracking and management
  - Integration scenarios

- **Integration Tests** (`test_strategy_integration.py`): Complete trading flow tests

### Running Tests

Run all tests:
```bash
python -m pytest tests/ -v
```

Run critical functions only:
```bash
python -m pytest tests/test_critical_functions.py -v
```

Run with coverage:
```bash
python -m pytest tests/ --cov=app.strategies.scalping --cov-report=html
```

See [TEST_SUMMARY.md](TEST_SUMMARY.md) for detailed test results and coverage information.

## Security Notes

⚠️ **Important**: 
- Never commit your `.env` file to version control
- Use Binance testnet (`BINANCE_TESTNET=true`) for testing
- Keep your API keys secure and use read-only keys when possible
- Start with small position sizes and test thoroughly before live trading

## Troubleshooting

### Common Issues

1. **JSONDecodeError for BASE_SYMBOLS**
   - Ensure `BASE_SYMBOLS` is comma-separated (e.g., `BTCUSDT,ETHUSDT`) or valid JSON array
   
2. **ModuleNotFoundError**
   - Run `pip install -r requirements.txt` to install dependencies
   
3. **Binance API Errors**
   - Verify your API keys are correct
   - Check if testnet is enabled/disabled as needed
   - Ensure your API key has futures trading permissions

## License

This project is provided as-is for educational and personal use.

## Contributing

Feel free to extend this bot with your own strategies and improvements!

