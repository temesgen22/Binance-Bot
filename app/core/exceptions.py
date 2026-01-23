"""Custom exception classes for the Binance Trading Bot."""

from __future__ import annotations


class BinanceBotException(Exception):
    """Base exception for all bot-related errors."""
    
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation, safely handling details dict."""
        return self.message


class BinanceAPIError(BinanceBotException):
    """Exception raised for Binance API errors."""
    
    def __init__(self, message: str, status_code: int | None = None, error_code: int | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.status_code = status_code
        self.error_code = error_code


class BinanceRateLimitError(BinanceAPIError):
    """Exception raised when Binance API rate limit is exceeded."""
    
    def __init__(self, message: str = "Binance API rate limit exceeded. Please wait before making more requests.", 
                 retry_after: int | None = None, details: dict | None = None):
        super().__init__(message, status_code=429, details=details)
        self.retry_after = retry_after


class BinanceNetworkError(BinanceAPIError):
    """Exception raised for network-related Binance API errors."""
    
    def __init__(self, message: str = "Network error connecting to Binance API.", details: dict | None = None):
        super().__init__(message, status_code=None, details=details)


class BinanceAuthenticationError(BinanceAPIError):
    """Exception raised for Binance authentication errors."""
    
    def __init__(self, message: str = "Binance API authentication failed. Check your API key and secret.", details: dict | None = None):
        super().__init__(message, status_code=401, error_code=-2015, details=details)


class StrategyNotFoundError(BinanceBotException):
    """Exception raised when a strategy is not found."""
    
    def __init__(self, strategy_id: str):
        super().__init__(f"Strategy '{strategy_id}' not found", details={"strategy_id": strategy_id})
        self.strategy_id = strategy_id


class StrategyAlreadyRunningError(BinanceBotException):
    """Exception raised when trying to start an already running strategy."""
    
    def __init__(self, strategy_id: str):
        super().__init__(f"Strategy '{strategy_id}' is already running", details={"strategy_id": strategy_id})
        self.strategy_id = strategy_id


class StrategyNotRunningError(BinanceBotException):
    """Exception raised when trying to stop a strategy that is not running."""
    
    def __init__(self, strategy_id: str):
        super().__init__(f"Strategy '{strategy_id}' is not running", details={"strategy_id": strategy_id})
        self.strategy_id = strategy_id


class MaxConcurrentStrategiesError(BinanceBotException):
    """Exception raised when maximum concurrent strategies limit is reached."""
    
    def __init__(self, current: int, max_allowed: int):
        super().__init__(
            f"Maximum concurrent strategies limit reached: {current}/{max_allowed}. "
            f"Please stop a strategy before starting a new one.",
            details={"current": current, "max_allowed": max_allowed}
        )
        self.current = current
        self.max_allowed = max_allowed


class InvalidLeverageError(BinanceBotException):
    """Exception raised when leverage is invalid."""
    
    def __init__(self, leverage: int, reason: str = ""):
        message = f"Invalid leverage: {leverage}. Must be between 1 and 50."
        if reason:
            message += f" {reason}"
        super().__init__(message, details={"leverage": leverage, "reason": reason})
        self.leverage = leverage


class PositionSizingError(BinanceBotException):
    """Exception raised when position sizing fails."""
    
    def __init__(self, message: str, symbol: str | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.symbol = symbol


class OrderExecutionError(BinanceBotException):
    """Exception raised when order execution fails."""
    
    def __init__(self, message: str, symbol: str | None = None, order_id: int | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.symbol = symbol
        self.order_id = order_id


class OrderNotFilledError(OrderExecutionError):
    """Exception raised when an order is not filled."""
    
    def __init__(self, order_id: int, symbol: str, status: str):
        super().__init__(
            f"Order {order_id} for {symbol} was not filled. Status: {status}",
            symbol=symbol,
            order_id=order_id,
            details={"status": status}
        )
        self.status = status


class RedisConnectionError(BinanceBotException):
    """Exception raised when Redis connection fails."""
    
    def __init__(self, message: str = "Failed to connect to Redis. Check Redis configuration.", details: dict | None = None):
        super().__init__(message, details)


class ConfigurationError(BinanceBotException):
    """Exception raised for configuration errors."""
    
    def __init__(self, message: str, config_key: str | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.config_key = config_key


class RiskLimitExceededError(BinanceBotException):
    """Exception raised when risk limit would be exceeded."""
    
    def __init__(self, message: str, account_id: str | None = None, strategy_id: str | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.account_id = account_id
        self.strategy_id = strategy_id


class CircuitBreakerActiveError(BinanceBotException):
    """Exception raised when circuit breaker is active."""
    
    def __init__(self, message: str, account_id: str | None = None, strategy_id: str | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.account_id = account_id
        self.strategy_id = strategy_id


class DrawdownLimitExceededError(BinanceBotException):
    """Exception raised when drawdown limit is exceeded."""
    
    def __init__(self, message: str, account_id: str | None = None, current_drawdown: float | None = None, max_drawdown: float | None = None, details: dict | None = None):
        super().__init__(message, details)
        self.account_id = account_id
        self.current_drawdown = current_drawdown
        self.max_drawdown = max_drawdown
