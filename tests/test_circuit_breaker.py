"""
Test cases for circuit breaker implementation.
"""
import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.fixture
    def breaker(self):
        """Create a circuit breaker for testing."""
        return CircuitBreaker(
            name="test_breaker",
            component="test",
            config=CircuitBreakerConfig(
                failure_threshold=3,  # Lower threshold for faster testing
                success_threshold=2,
                timeout=1.0,  # 1 second timeout for faster testing
                expected_exception=Exception
            )
        )
    
    def test_initial_state_closed(self, breaker):
        """Test that circuit breaker starts in CLOSED state."""
        assert breaker.state == CircuitState.CLOSED
    
    def test_successful_call(self, breaker):
        """Test successful call doesn't change state."""
        def success_func():
            return "success"
        
        result = breaker.call_sync(success_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failures == 0
    
    def test_failure_increments_counter(self, breaker):
        """Test that failures increment the counter."""
        def fail_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            breaker.call_sync(fail_func)
        
        assert breaker.stats.failures == 1
        assert breaker.state == CircuitState.CLOSED  # Not open yet
    
    def test_circuit_opens_after_threshold(self, breaker):
        """Test that circuit opens after failure threshold."""
        def fail_func():
            raise ValueError("Test error")
        
        # Cause failures up to threshold
        for i in range(breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                breaker.call_sync(fail_func)
        
        # Circuit should be OPEN now
        assert breaker.state == CircuitState.OPEN
        assert breaker.stats.failures >= breaker.config.failure_threshold
    
    def test_circuit_blocks_requests_when_open(self, breaker):
        """Test that circuit blocks requests when open."""
        def fail_func():
            raise ValueError("Test error")
        
        # Open the circuit
        for i in range(breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                breaker.call_sync(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Try to call - should be blocked
        def any_func():
            return "should not execute"
        
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call_sync(any_func)
        
        assert breaker.stats.blocked_requests > 0
    
    def test_circuit_attempts_half_open_after_timeout(self, breaker):
        """Test that circuit attempts half-open after timeout."""
        def fail_func():
            raise ValueError("Test error")
        
        # Open the circuit
        for i in range(breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                breaker.call_sync(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for timeout
        breaker.stats.last_failure_time = time.time() - (breaker.config.timeout + 0.1)
        
        # Try to call - should attempt half-open
        def success_func():
            return "success"
        
        # First call should go through (half-open)
        result = breaker.call_sync(success_func)
        assert result == "success"
        assert breaker.state == CircuitState.HALF_OPEN or breaker.state == CircuitState.CLOSED
    
    def test_circuit_closes_after_success_threshold(self, breaker):
        """Test that circuit closes after success threshold in half-open."""
        def fail_func():
            raise ValueError("Test error")
        
        # Open the circuit
        for i in range(breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                breaker.call_sync(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for timeout and enter half-open
        breaker.stats.last_failure_time = time.time() - (breaker.config.timeout + 0.1)
        breaker.state = CircuitState.HALF_OPEN
        breaker.stats.successes = 0
        breaker._half_open_requests = 0
        
        # Succeed enough times to close
        def success_func():
            return "success"
        
        for i in range(breaker.config.success_threshold):
            result = breaker.call_sync(success_func)
            assert result == "success"
        
        # Circuit should be closed
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failures == 0
    
    def test_circuit_reopens_on_failure_in_half_open(self, breaker):
        """Test that circuit reopens on failure in half-open state."""
        def fail_func():
            raise ValueError("Test error")
        
        # Set to half-open state
        breaker.state = CircuitState.HALF_OPEN
        breaker.stats.successes = 0
        breaker._half_open_requests = 0
        
        # Fail - should reopen
        with pytest.raises(ValueError):
            breaker.call_sync(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        assert breaker.stats.successes == 0
    
    def test_get_stats(self, breaker):
        """Test getting circuit breaker statistics."""
        stats = breaker.get_stats()
        
        assert "name" in stats
        assert "component" in stats
        assert "state" in stats
        assert "failures" in stats
        assert "successes" in stats
        assert "total_requests" in stats
        assert "blocked_requests" in stats
        assert stats["name"] == "test_breaker"
        assert stats["component"] == "test"
    
    def test_reset(self, breaker):
        """Test resetting circuit breaker."""
        def fail_func():
            raise ValueError("Test error")
        
        # Cause some failures
        for i in range(2):
            with pytest.raises(ValueError):
                breaker.call_sync(fail_func)
        
        # Reset
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failures == 0
        assert breaker.stats.successes == 0
        assert breaker._half_open_requests == 0


class TestCircuitBreakerAsync:
    """Test circuit breaker async functionality."""
    
    @pytest.fixture
    def breaker(self):
        """Create a circuit breaker for testing."""
        return CircuitBreaker(
            name="test_breaker_async",
            component="test",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout=1.0,
                expected_exception=Exception
            )
        )
    
    @pytest.mark.asyncio
    async def test_async_successful_call(self, breaker):
        """Test successful async call."""
        async def success_func():
            await asyncio.sleep(0.01)
            return "success"
        
        result = await breaker.call_async(success_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_async_failure(self, breaker):
        """Test async call with failure."""
        async def fail_func():
            await asyncio.sleep(0.01)
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await breaker.call_async(fail_func)
        
        assert breaker.stats.failures == 1
    
    @pytest.mark.asyncio
    async def test_async_circuit_opens(self, breaker):
        """Test that async circuit opens after threshold."""
        async def fail_func():
            await asyncio.sleep(0.01)
            raise ValueError("Test error")
        
        # Cause failures up to threshold
        for i in range(breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await breaker.call_async(fail_func)
        
        assert breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_async_circuit_blocks(self, breaker):
        """Test that async circuit blocks when open."""
        async def fail_func():
            raise ValueError("Test error")
        
        # Open the circuit
        for i in range(breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await breaker.call_async(fail_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Try to call - should be blocked
        async def any_func():
            return "should not execute"
        
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call_async(any_func)


class TestCircuitBreakerConfig:
    """Test circuit breaker configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 60.0
        assert config.expected_exception == Exception
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            success_threshold=3,
            timeout=120.0,
            expected_exception=ValueError
        )
        
        assert config.failure_threshold == 10
        assert config.success_threshold == 3
        assert config.timeout == 120.0
        assert config.expected_exception == ValueError

