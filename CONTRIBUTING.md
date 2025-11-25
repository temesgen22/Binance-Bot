# Contributing to Binance Trading Bot

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd "Binance Bot"
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"  # Install development dependencies
   ```

4. **Configure environment**
   ```bash
   copy env.example .env
   # Edit .env with your configuration
   ```

## Code Style

### Python Style Guide
- Follow [PEP 8](https://pep8.org/) style guidelines
- Use type hints for all function parameters and return values
- Maximum line length: 100 characters
- Use `black` for code formatting (if configured)

### Naming Conventions
- **Modules**: `snake_case` (e.g., `strategy_runner.py`)
- **Classes**: `PascalCase` (e.g., `StrategyRunner`)
- **Functions**: `snake_case` (e.g., `get_klines`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_LEVERAGE`)
- **Private**: `_leading_underscore` (e.g., `_run_loop`)

### Project Structure
- Follow the existing project structure (see [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md))
- Place new modules in appropriate directories:
  - API routes → `app/api/routes/`
  - Services → `app/services/`
  - Strategies → `app/strategies/`
  - Models → `app/models/`
  - Core utilities → `app/core/`

## Adding New Features

### Adding a New Strategy

1. **Create strategy file** in `app/strategies/`
   ```python
   from app.strategies.base import Strategy, StrategyContext, StrategySignal
   
   class MyNewStrategy(Strategy):
       async def evaluate(self) -> StrategySignal:
           # Implementation
   ```

2. **Register strategy** in `app/services/strategy_runner.py`
   ```python
   def _register_strategies(self):
       self.registry.register("my_strategy", MyNewStrategy)
   ```

3. **Add tests** in `tests/test_strategy_*.py`

4. **Update documentation** in `docs/`

### Adding a New API Endpoint

1. **Add route handler** in `app/api/routes/`
2. **Add dependency** in `app/api/deps.py` if needed
3. **Register route** in `app/main.py`
4. **Add tests** in `tests/test_*.py`
5. **Update API documentation** in `docs/API_USAGE.md`

### Adding a New Service

1. **Create service file** in `app/services/`
2. **Follow dependency injection pattern**
3. **Add tests** in `tests/test_*.py`

## Testing

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_strategy_scalping.py

# Run with coverage
pytest --cov=app --cov-report=html
```

### Writing Tests
- Place tests in `tests/` directory
- Name test files: `test_*.py`
- Name test functions: `test_*`
- Use fixtures from `tests/conftest.py`

### Test Coverage
- Aim for >80% code coverage
- Test critical paths thoroughly
- Include integration tests for complex flows

## Documentation

### Code Documentation
- Use docstrings for all public classes and functions
- Follow Google-style docstrings:
  ```python
  def get_klines(self, symbol: str, interval: str = "1m") -> list[list[Any]]:
      """Get klines (candlestick data) from Binance futures.
      
      Args:
          symbol: Trading symbol (e.g., 'BTCUSDT')
          interval: Kline interval (1m, 5m, 15m, 1h, etc.)
          limit: Number of klines to retrieve (max 1500)
          
      Returns:
          List of klines where each kline is [open_time, open, high, low, close, volume, ...]
      """
  ```

### User Documentation
- Update relevant docs in `docs/` directory
- Keep examples up to date
- Document breaking changes

## Commit Messages

Use clear, descriptive commit messages:

```
feat: Add trailing stop activation threshold
fix: Resolve Redis connection timeout issue
docs: Update API usage guide
refactor: Reorganize project structure
test: Add tests for WebSocket manager
```

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes**
   - Write code following style guidelines
   - Add tests for new features
   - Update documentation

3. **Run tests and linting**
   ```bash
   pytest
   # Run linter if configured
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: Add new feature"
   ```

5. **Push and create PR**
   ```bash
   git push origin feature/my-feature
   ```

6. **PR Requirements**
   - Clear description of changes
   - Reference related issues
   - Ensure all tests pass
   - Update documentation if needed

## Code Review

- All PRs require review before merging
- Address review comments promptly
- Be respectful and constructive in reviews

## Questions?

- Open an issue for questions or discussions
- Check existing documentation in `docs/`
- Review [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for architecture details

Thank you for contributing! 🚀

