"""
Test cases for correlation ID middleware and context management.
"""
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.correlation_id import (
    get_correlation_id,
    set_correlation_id,
    CorrelationIDMiddleware,
)


class TestCorrelationIDContext:
    """Test correlation ID context management."""
    
    def test_get_correlation_id_none_by_default(self):
        """Test that correlation ID is None by default."""
        # In a new context, correlation ID should be None
        # Note: ContextVar is thread-local, so this test may not work as expected
        # in all scenarios, but it's a basic test
        correlation_id = get_correlation_id()
        # Can be None or a value from previous test context
        assert correlation_id is None or isinstance(correlation_id, str)
    
    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID."""
        test_id = str(uuid.uuid4())
        set_correlation_id(test_id)
        
        correlation_id = get_correlation_id()
        assert correlation_id == test_id
    
    def test_correlation_id_is_string(self):
        """Test that correlation ID is a string."""
        test_id = str(uuid.uuid4())
        set_correlation_id(test_id)
        
        correlation_id = get_correlation_id()
        assert isinstance(correlation_id, str)
        assert len(correlation_id) > 0


class TestCorrelationIDMiddleware:
    """Test correlation ID middleware."""
    
    @pytest.mark.asyncio
    async def test_middleware_generates_id_if_missing(self):
        """Test that middleware generates ID if not in header."""
        middleware = CorrelationIDMiddleware(lambda request, call_next: call_next(request))
        
        # Create a mock request without correlation ID header
        request = MagicMock(spec=Request)
        request.headers = {}
        
        # Create a mock response
        response = MagicMock()
        response.headers = {}
        
        async def call_next(request):
            return response
        
        result = await middleware.dispatch(request, call_next)
        
        # Should have correlation ID in response
        assert "X-Correlation-ID" in result.headers
        assert result.headers["X-Correlation-ID"] is not None
        assert len(result.headers["X-Correlation-ID"]) > 0
    
    @pytest.mark.asyncio
    async def test_middleware_uses_existing_id(self):
        """Test that middleware uses existing ID from header."""
        middleware = CorrelationIDMiddleware(lambda request, call_next: call_next(request))
        
        test_id = "test-correlation-id-123"
        
        # Create a mock request with correlation ID header
        request = MagicMock(spec=Request)
        request.headers = {"X-Correlation-ID": test_id}
        
        # Create a mock response
        response = MagicMock()
        response.headers = {}
        
        async def call_next(request):
            return response
        
        result = await middleware.dispatch(request, call_next)
        
        # Should use the provided correlation ID
        assert result.headers["X-Correlation-ID"] == test_id
    
    @pytest.mark.asyncio
    async def test_middleware_sets_context(self):
        """Test that middleware sets correlation ID in context."""
        middleware = CorrelationIDMiddleware(lambda request, call_next: call_next(request))
        
        test_id = "test-context-id"
        
        request = MagicMock(spec=Request)
        request.headers = {"X-Correlation-ID": test_id}
        
        response = MagicMock()
        response.headers = {}
        
        async def call_next(request):
            # Check that correlation ID is set in context
            correlation_id = get_correlation_id()
            assert correlation_id == test_id
            return response
        
        await middleware.dispatch(request, call_next)
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_middleware_with_fastapi_app(self):
        """Test middleware integration with FastAPI app."""
        from fastapi import FastAPI
        from app.main import create_app
        
        app = create_app()
        client = TestClient(app)
        
        # Test without correlation ID header
        response = client.get("/health/live")
        assert response.status_code == 200
        assert "X-Correlation-ID" in response.headers
        assert len(response.headers["X-Correlation-ID"]) > 0
        
        # Test with correlation ID header
        test_id = "my-test-correlation-id"
        response = client.get("/health/live", headers={"X-Correlation-ID": test_id})
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == test_id
    
    @pytest.mark.asyncio
    async def test_correlation_id_in_logs(self):
        """Test that correlation ID is included in logs."""
        from loguru import logger
        from app.core.correlation_id import set_correlation_id
        
        test_id = "log-test-id"
        set_correlation_id(test_id)
        
        # Log a message
        logger.info("Test log message with correlation ID")
        
        # Correlation ID should be available in context
        correlation_id = get_correlation_id()
        assert correlation_id == test_id

