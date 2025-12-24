"""
Circuit breaker implementation for protecting against cascading failures.

Circuit breakers prevent the system from repeatedly attempting operations
that are likely to fail, allowing the system to recover gracefully.
"""
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Optional, Callable, Any, TypeVar
from dataclasses import dataclass, field

from loguru import logger

from app.core.metrics import (
    update_circuit_breaker_state,
    record_circuit_breaker_failure,
)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = 0  # Normal operation, requests allowed
    OPEN = 1    # Failing, requests blocked
    HALF_OPEN = 2  # Testing if service recovered, limited requests allowed


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    failure_threshold: int = 5  # Number of failures before opening
    success_threshold: int = 2  # Number of successes in half-open to close
    timeout: float = 60.0  # Time in seconds before attempting half-open
    expected_exception: type[Exception] = Exception  # Exception type to catch


@dataclass
class CircuitBreakerStats:
    """Statistics for a circuit breaker."""
    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[float] = None
    state_changes: int = 0
    total_requests: int = 0
    blocked_requests: int = 0


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures.
    
    Usage:
        breaker = CircuitBreaker("binance_api", config=CircuitBreakerConfig())
        
        # In async function:
        try:
            result = await breaker.call_async(client.get_price, "BTCUSDT")
        except CircuitBreakerOpenError:
            # Circuit is open, service unavailable
            pass
    """
    
    def __init__(
        self,
        name: str,
        component: str = "unknown",
        config: Optional[CircuitBreakerConfig] = None,
    ):
        self.name = name
        self.component = component
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
        self._half_open_requests = 0  # Track requests in half-open state
        
        # Update metrics
        update_circuit_breaker_state(self.component, self.name, self.state.value)
    
    async def call_async(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """Execute a function with circuit breaker protection (async).
        
        Args:
            func: Async function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If function raises an exception (and circuit is not open)
        """
        async with self._lock:
            # Check if circuit is open
            if self.state == CircuitState.OPEN:
                # Check if timeout has passed to attempt half-open
                if self.stats.last_failure_time:
                    time_since_failure = time.time() - self.stats.last_failure_time
                    if time_since_failure >= self.config.timeout:
                        logger.info(
                            f"Circuit breaker {self.name} ({self.component}) "
                            f"attempting half-open state after {time_since_failure:.1f}s"
                        )
                        self.state = CircuitState.HALF_OPEN
                        self._half_open_requests = 0
                        self.stats.state_changes += 1
                        update_circuit_breaker_state(
                            self.component, self.name, self.state.value
                        )
                    else:
                        # Still in timeout period, block request
                        self.stats.blocked_requests += 1
                        raise CircuitBreakerOpenError(
                            f"Circuit breaker {self.name} is OPEN. "
                            f"Service unavailable. Retry after {self.config.timeout - time_since_failure:.1f}s"
                        )
                else:
                    # No failure time recorded, block request
                    self.stats.blocked_requests += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker {self.name} is OPEN. Service unavailable."
                    )
            
            # Check if circuit is half-open and limit requests
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_requests >= self.config.success_threshold:
                    # Too many requests in half-open, block
                    self.stats.blocked_requests += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker {self.name} is HALF_OPEN. "
                        f"Too many concurrent requests. Please retry."
                    )
                self._half_open_requests += 1
        
        # Execute function outside lock (to avoid blocking)
        self.stats.total_requests += 1
        try:
            result = await func(*args, **kwargs)
            
            # Success - update state
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self.stats.successes += 1
                    if self.stats.successes >= self.config.success_threshold:
                        logger.info(
                            f"Circuit breaker {self.name} ({self.component}) "
                            f"CLOSED after {self.stats.successes} successes"
                        )
                        self.state = CircuitState.CLOSED
                        self.stats.failures = 0
                        self.stats.successes = 0
                        self.stats.state_changes += 1
                        update_circuit_breaker_state(
                            self.component, self.name, self.state.value
                        )
                    self._half_open_requests -= 1
                elif self.state == CircuitState.CLOSED:
                    # Reset failure count on success
                    self.stats.failures = 0
            
            return result
            
        except self.config.expected_exception as exc:
            # Failure - update state
            async with self._lock:
                self.stats.failures += 1
                self.stats.last_failure_time = time.time()
                
                if self.state == CircuitState.HALF_OPEN:
                    # Failed in half-open, open circuit immediately
                    logger.warning(
                        f"Circuit breaker {self.name} ({self.component}) "
                        f"OPENED after failure in half-open state"
                    )
                    self.state = CircuitState.OPEN
                    self.stats.successes = 0
                    self.stats.state_changes += 1
                    self._half_open_requests -= 1
                    update_circuit_breaker_state(
                        self.component, self.name, self.state.value
                    )
                    record_circuit_breaker_failure(self.component, self.name)
                elif self.state == CircuitState.CLOSED:
                    # Check if threshold reached
                    if self.stats.failures >= self.config.failure_threshold:
                        logger.warning(
                            f"Circuit breaker {self.name} ({self.component}) "
                            f"OPENED after {self.stats.failures} failures"
                        )
                        self.state = CircuitState.OPEN
                        self.stats.state_changes += 1
                        update_circuit_breaker_state(
                            self.component, self.name, self.state.value
                        )
                        record_circuit_breaker_failure(self.component, self.name)
            
            # Re-raise the exception
            raise
    
    def call_sync(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """Execute a function with circuit breaker protection (sync).
        
        Args:
            func: Sync function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If function raises an exception (and circuit is not open)
        """
        # For sync functions, we need to use a different approach
        # Since we can't use async locks, we'll use threading locks
        import threading
        if not hasattr(self, '_sync_lock'):
            self._sync_lock = threading.Lock()
        
        with self._sync_lock:
            # Check if circuit is open
            if self.state == CircuitState.OPEN:
                if self.stats.last_failure_time:
                    time_since_failure = time.time() - self.stats.last_failure_time
                    if time_since_failure >= self.config.timeout:
                        logger.info(
                            f"Circuit breaker {self.name} ({self.component}) "
                            f"attempting half-open state after {time_since_failure:.1f}s"
                        )
                        self.state = CircuitState.HALF_OPEN
                        self._half_open_requests = 0
                        self.stats.state_changes += 1
                        update_circuit_breaker_state(
                            self.component, self.name, self.state.value
                        )
                    else:
                        self.stats.blocked_requests += 1
                        raise CircuitBreakerOpenError(
                            f"Circuit breaker {self.name} is OPEN. "
                            f"Service unavailable. Retry after {self.config.timeout - time_since_failure:.1f}s"
                        )
                else:
                    self.stats.blocked_requests += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker {self.name} is OPEN. Service unavailable."
                    )
            
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_requests >= self.config.success_threshold:
                    self.stats.blocked_requests += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker {self.name} is HALF_OPEN. "
                        f"Too many concurrent requests. Please retry."
                    )
                self._half_open_requests += 1
        
        # Execute function outside lock
        self.stats.total_requests += 1
        try:
            result = func(*args, **kwargs)
            
            # Success
            with self._sync_lock:
                if self.state == CircuitState.HALF_OPEN:
                    self.stats.successes += 1
                    if self.stats.successes >= self.config.success_threshold:
                        logger.info(
                            f"Circuit breaker {self.name} ({self.component}) "
                            f"CLOSED after {self.stats.successes} successes"
                        )
                        self.state = CircuitState.CLOSED
                        self.stats.failures = 0
                        self.stats.successes = 0
                        self.stats.state_changes += 1
                        update_circuit_breaker_state(
                            self.component, self.name, self.state.value
                        )
                    self._half_open_requests -= 1
                elif self.state == CircuitState.CLOSED:
                    self.stats.failures = 0
            
            return result
            
        except self.config.expected_exception as exc:
            # Failure
            with self._sync_lock:
                self.stats.failures += 1
                self.stats.last_failure_time = time.time()
                
                if self.state == CircuitState.HALF_OPEN:
                    logger.warning(
                        f"Circuit breaker {self.name} ({self.component}) "
                        f"OPENED after failure in half-open state"
                    )
                    self.state = CircuitState.OPEN
                    self.stats.successes = 0
                    self.stats.state_changes += 1
                    self._half_open_requests -= 1
                    update_circuit_breaker_state(
                        self.component, self.name, self.state.value
                    )
                    record_circuit_breaker_failure(self.component, self.name)
                elif self.state == CircuitState.CLOSED:
                    if self.stats.failures >= self.config.failure_threshold:
                        logger.warning(
                            f"Circuit breaker {self.name} ({self.component}) "
                            f"OPENED after {self.stats.failures} failures"
                        )
                        self.state = CircuitState.OPEN
                        self.stats.state_changes += 1
                        update_circuit_breaker_state(
                            self.component, self.name, self.state.value
                        )
                        record_circuit_breaker_failure(self.component, self.name)
            
            raise
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "component": self.component,
            "state": self.state.name,
            "failures": self.stats.failures,
            "successes": self.stats.successes,
            "total_requests": self.stats.total_requests,
            "blocked_requests": self.stats.blocked_requests,
            "state_changes": self.stats.state_changes,
            "last_failure_time": self.stats.last_failure_time,
        }
    
    def reset(self):
        """Reset circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._half_open_requests = 0
        update_circuit_breaker_state(self.component, self.name, self.state.value)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request is blocked."""
    pass

