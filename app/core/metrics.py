"""
Prometheus metrics collection for the trading bot.

This module provides metrics for:
- Order execution (count, latency, success rate)
- Strategy performance (signals, trades, PnL)
- API latency (Binance, database, Redis)
- System health (active strategies, errors)
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Optional
from functools import wraps

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Create dummy classes for when prometheus_client is not installed
    class Counter:
        def __init__(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
    
    class Histogram:
        def __init__(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
        def time(self, *args, **kwargs):
            return self
    
    class Gauge:
        def __init__(self, *args, **kwargs):
            pass
        def set(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
        def dec(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
    
    def generate_latest():
        return b"# Prometheus metrics not available (prometheus_client not installed)\n"
    
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

from loguru import logger


# Order Execution Metrics
order_execution_total = Counter(
    "binance_bot_orders_total",
    "Total number of orders executed",
    ["symbol", "side", "status", "strategy_type"]
) if PROMETHEUS_AVAILABLE else Counter()

order_execution_duration = Histogram(
    "binance_bot_order_execution_duration_seconds",
    "Order execution duration in seconds",
    ["symbol", "side"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
) if PROMETHEUS_AVAILABLE else Histogram()

order_execution_errors = Counter(
    "binance_bot_order_errors_total",
    "Total number of order execution errors",
    ["symbol", "error_type"]
) if PROMETHEUS_AVAILABLE else Counter()

# Strategy Performance Metrics
strategy_signals_total = Counter(
    "binance_bot_strategy_signals_total",
    "Total number of strategy signals generated",
    ["strategy_id", "strategy_type", "signal_action"]
) if PROMETHEUS_AVAILABLE else Counter()

strategy_trades_total = Counter(
    "binance_bot_strategy_trades_total",
    "Total number of trades executed per strategy",
    ["strategy_id", "strategy_type", "symbol"]
) if PROMETHEUS_AVAILABLE else Counter()

strategy_pnl = Gauge(
    "binance_bot_strategy_pnl",
    "Current unrealized PnL per strategy",
    ["strategy_id", "strategy_type", "symbol"]
) if PROMETHEUS_AVAILABLE else Gauge()

strategy_position_size = Gauge(
    "binance_bot_strategy_position_size",
    "Current position size per strategy",
    ["strategy_id", "strategy_type", "symbol", "position_side"]
) if PROMETHEUS_AVAILABLE else Gauge()

# API Latency Metrics
api_request_duration = Histogram(
    "binance_bot_api_request_duration_seconds",
    "API request duration in seconds",
    ["api", "endpoint", "status"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
) if PROMETHEUS_AVAILABLE else Histogram()

api_request_errors = Counter(
    "binance_bot_api_request_errors_total",
    "Total number of API request errors",
    ["api", "endpoint", "error_type"]
) if PROMETHEUS_AVAILABLE else Counter()

# Database Metrics
database_query_duration = Histogram(
    "binance_bot_database_query_duration_seconds",
    "Database query duration in seconds",
    ["operation", "table"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
) if PROMETHEUS_AVAILABLE else Histogram()

database_connection_pool_size = Gauge(
    "binance_bot_database_connection_pool_size",
    "Database connection pool size",
    ["state"]  # "active", "idle", "total"
) if PROMETHEUS_AVAILABLE else Gauge()

# System Health Metrics
active_strategies = Gauge(
    "binance_bot_active_strategies",
    "Number of currently active strategies",
    ["status"]  # "running", "stopped", "error"
) if PROMETHEUS_AVAILABLE else Gauge()

system_errors_total = Counter(
    "binance_bot_system_errors_total",
    "Total number of system errors",
    ["component", "error_type"]
) if PROMETHEUS_AVAILABLE else Counter()

# Circuit Breaker Metrics
circuit_breaker_state = Gauge(
    "binance_bot_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open)",
    ["component", "name"]
) if PROMETHEUS_AVAILABLE else Gauge()

circuit_breaker_failures = Counter(
    "binance_bot_circuit_breaker_failures_total",
    "Total number of circuit breaker failures",
    ["component", "name"]
) if PROMETHEUS_AVAILABLE else Counter()


@contextmanager
def track_order_execution(symbol: str, side: str, strategy_type: Optional[str] = None):
    """Context manager to track order execution metrics.
    
    Usage:
        with track_order_execution("BTCUSDT", "BUY", "scalping"):
            # Execute order
            result = place_order(...)
    """
    start_time = time.time()
    status = "success"
    error_type = None
    
    try:
        yield
    except Exception as exc:
        status = "error"
        error_type = type(exc).__name__
        order_execution_errors.labels(symbol=symbol, error_type=error_type).inc()
        raise
    finally:
        duration = time.time() - start_time
        order_execution_duration.labels(symbol=symbol, side=side).observe(duration)
        order_execution_total.labels(
            symbol=symbol,
            side=side,
            status=status,
            strategy_type=strategy_type or "unknown"
        ).inc()


@contextmanager
def track_api_request(api: str, endpoint: str):
    """Context manager to track API request metrics.
    
    Usage:
        with track_api_request("binance", "get_price"):
            price = client.get_price("BTCUSDT")
    """
    start_time = time.time()
    status = "success"
    error_type = None
    
    try:
        yield
    except Exception as exc:
        status = "error"
        error_type = type(exc).__name__
        api_request_errors.labels(api=api, endpoint=endpoint, error_type=error_type).inc()
        raise
    finally:
        duration = time.time() - start_time
        api_request_duration.labels(api=api, endpoint=endpoint, status=status).observe(duration)


@contextmanager
def track_database_query(operation: str, table: str):
    """Context manager to track database query metrics.
    
    Usage:
        with track_database_query("select", "strategies"):
            result = db.query(Strategy).all()
    """
    start_time = time.time()
    
    try:
        yield
    finally:
        duration = time.time() - start_time
        database_query_duration.labels(operation=operation, table=table).observe(duration)


def record_strategy_signal(strategy_id: str, strategy_type: str, signal_action: str):
    """Record a strategy signal."""
    strategy_signals_total.labels(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        signal_action=signal_action
    ).inc()


def record_strategy_trade(strategy_id: str, strategy_type: str, symbol: str):
    """Record a strategy trade."""
    strategy_trades_total.labels(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        symbol=symbol
    ).inc()


def update_strategy_pnl(strategy_id: str, strategy_type: str, symbol: str, pnl: float):
    """Update strategy PnL metric."""
    strategy_pnl.labels(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        symbol=symbol
    ).set(pnl)


def update_strategy_position(
    strategy_id: str,
    strategy_type: str,
    symbol: str,
    position_side: Optional[str],
    position_size: float
):
    """Update strategy position size metric."""
    side = position_side or "FLAT"
    strategy_position_size.labels(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        symbol=symbol,
        position_side=side
    ).set(position_size)


def update_active_strategies(running: int, stopped: int, error: int):
    """Update active strategies count."""
    active_strategies.labels(status="running").set(running)
    active_strategies.labels(status="stopped").set(stopped)
    active_strategies.labels(status="error").set(error)


def record_system_error(component: str, error_type: str):
    """Record a system error."""
    system_errors_total.labels(component=component, error_type=error_type).inc()


def update_circuit_breaker_state(component: str, name: str, state: int):
    """Update circuit breaker state.
    
    Args:
        component: Component name (e.g., "binance", "database")
        name: Circuit breaker name
        state: 0=closed, 1=open, 2=half-open
    """
    circuit_breaker_state.labels(component=component, name=name).set(state)


def record_circuit_breaker_failure(component: str, name: str):
    """Record a circuit breaker failure."""
    circuit_breaker_failures.labels(component=component, name=name).inc()


def get_metrics():
    """Get Prometheus metrics in text format."""
    if not PROMETHEUS_AVAILABLE:
        logger.warning("Prometheus metrics not available (prometheus_client not installed)")
    return generate_latest()


def get_metrics_content_type():
    """Get the content type for Prometheus metrics."""
    return CONTENT_TYPE_LATEST

