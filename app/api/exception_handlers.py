"""Exception handlers for FastAPI application."""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from loguru import logger

from app.core.exceptions import (
    BinanceBotException,
    BinanceAPIError,
    BinanceRateLimitError,
    BinanceNetworkError,
    BinanceAuthenticationError,
    StrategyNotFoundError,
    StrategyAlreadyRunningError,
    StrategyNotRunningError,
    MaxConcurrentStrategiesError,
    InvalidLeverageError,
    PositionSizingError,
    OrderExecutionError,
    OrderNotFilledError,
    RedisConnectionError,
    ConfigurationError,
)


async def binance_rate_limit_handler(request: Request, exc: BinanceRateLimitError) -> JSONResponse:
    """Handle Binance rate limit errors."""
    retry_after = exc.retry_after or 10
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "Rate Limit Exceeded",
            "message": exc.message,
            "details": exc.details,
            "retry_after_seconds": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


async def binance_api_error_handler(request: Request, exc: BinanceAPIError) -> JSONResponse:
    """Handle Binance API errors."""
    status_code = exc.status_code or status.HTTP_502_BAD_GATEWAY
    logger.error(f"Binance API Error: {exc.message} (status: {exc.status_code}, code: {exc.error_code})")
    return JSONResponse(
        status_code=status_code,
        content={
            "error": "Binance API Error",
            "message": exc.message,
            "status_code": exc.status_code,
            "error_code": exc.error_code,
            "details": exc.details,
        },
    )


async def strategy_not_found_handler(request: Request, exc: StrategyNotFoundError) -> JSONResponse:
    """Handle strategy not found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "Strategy Not Found",
            "message": exc.message,
            "details": exc.details,
        },
    )


async def strategy_already_running_handler(request: Request, exc: StrategyAlreadyRunningError) -> JSONResponse:
    """Handle strategy already running errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Strategy Already Running",
            "message": exc.message,
            "details": exc.details,
        },
    )


async def strategy_not_running_handler(request: Request, exc: StrategyNotRunningError) -> JSONResponse:
    """Handle strategy not running errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Strategy Not Running",
            "message": exc.message,
            "details": exc.details,
        },
    )


async def max_concurrent_strategies_handler(request: Request, exc: MaxConcurrentStrategiesError) -> JSONResponse:
    """Handle max concurrent strategies errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Maximum Concurrent Strategies Reached",
            "message": exc.message,
            "details": exc.details,
        },
    )


async def invalid_leverage_handler(request: Request, exc: InvalidLeverageError) -> JSONResponse:
    """Handle invalid leverage errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Invalid Leverage",
            "message": exc.message,
            "details": exc.details,
        },
    )


async def position_sizing_handler(request: Request, exc: PositionSizingError) -> JSONResponse:
    """Handle position sizing errors."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Position Sizing Error",
            "message": exc.message,
            "symbol": exc.symbol,
            "details": exc.details,
        },
    )


async def order_execution_handler(request: Request, exc: OrderExecutionError) -> JSONResponse:
    """Handle order execution errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Order Execution Error",
            "message": exc.message,
            "symbol": exc.symbol,
            "order_id": exc.order_id,
            "details": exc.details,
        },
    )


async def binance_bot_exception_handler(request: Request, exc: BinanceBotException) -> JSONResponse:
    """Handle general bot exceptions."""
    logger.error(f"Bot Exception: {exc.message}", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Trading Bot Error",
            "message": exc.message,
            "details": exc.details,
        },
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors."""
    errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field_path,
            "message": error["msg"],
            "type": error["type"],
        })
    
    logger.warning(f"Validation Error: {errors}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "message": "Invalid request data. Please check the following fields:",
            "errors": errors,
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.exception(f"Unexpected error: {exc}", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please check logs for details.",
            "type": type(exc).__name__,
        },
    )

