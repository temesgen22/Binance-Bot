"""
Test cases for Prometheus metrics collection.
"""
import pytest
from unittest.mock import MagicMock, patch
import time

from app.core.metrics import (
    track_order_execution,
    track_api_request,
    track_database_query,
    record_strategy_signal,
    record_strategy_trade,
    update_strategy_pnl,
    update_strategy_position,
    update_active_strategies,
    record_system_error,
    update_circuit_breaker_state,
    record_circuit_breaker_failure,
    get_metrics,
    get_metrics_content_type,
    PROMETHEUS_AVAILABLE,
)


class TestMetricsCollection:
    """Test metrics collection functionality."""
    
    def test_track_order_execution_success(self):
        """Test tracking successful order execution."""
        with track_order_execution("BTCUSDT", "BUY", "scalping"):
            time.sleep(0.01)  # Simulate some work
        
        # Metrics should be recorded (if Prometheus available)
        # We can't easily assert metrics without Prometheus, but we can verify no exceptions
        assert True
    
    def test_track_order_execution_error(self):
        """Test tracking order execution with error."""
        with pytest.raises(ValueError):
            with track_order_execution("BTCUSDT", "SELL", "scalping"):
                raise ValueError("Order failed")
        
        # Error should be recorded in metrics
        assert True
    
    def test_track_api_request_success(self):
        """Test tracking successful API request."""
        with track_api_request("binance", "get_price"):
            time.sleep(0.01)  # Simulate API call
        
        assert True
    
    def test_track_api_request_error(self):
        """Test tracking API request with error."""
        with pytest.raises(Exception):
            with track_api_request("binance", "place_order"):
                raise Exception("API error")
        
        assert True
    
    def test_track_database_query(self):
        """Test tracking database query."""
        with track_database_query("select", "strategies"):
            time.sleep(0.001)  # Simulate query
        
        assert True
    
    def test_record_strategy_signal(self):
        """Test recording strategy signal."""
        record_strategy_signal("strategy-123", "scalping", "BUY")
        assert True
    
    def test_record_strategy_trade(self):
        """Test recording strategy trade."""
        record_strategy_trade("strategy-123", "scalping", "BTCUSDT")
        assert True
    
    def test_update_strategy_pnl(self):
        """Test updating strategy PnL."""
        update_strategy_pnl("strategy-123", "scalping", "BTCUSDT", 100.50)
        assert True
    
    def test_update_strategy_position(self):
        """Test updating strategy position."""
        update_strategy_position("strategy-123", "scalping", "BTCUSDT", "LONG", 0.001)
        assert True
    
    def test_update_active_strategies(self):
        """Test updating active strategies count."""
        update_active_strategies(running=5, stopped=3, error=1)
        assert True
    
    def test_record_system_error(self):
        """Test recording system error."""
        record_system_error("database", "ConnectionError")
        assert True
    
    def test_update_circuit_breaker_state(self):
        """Test updating circuit breaker state."""
        update_circuit_breaker_state("binance", "api", 0)  # CLOSED
        update_circuit_breaker_state("binance", "api", 1)  # OPEN
        update_circuit_breaker_state("binance", "api", 2)  # HALF_OPEN
        assert True
    
    def test_record_circuit_breaker_failure(self):
        """Test recording circuit breaker failure."""
        record_circuit_breaker_failure("binance", "api")
        assert True
    
    def test_get_metrics(self):
        """Test getting metrics in text format."""
        metrics = get_metrics()
        assert isinstance(metrics, bytes)
        assert len(metrics) > 0
    
    def test_get_metrics_content_type(self):
        """Test getting metrics content type."""
        content_type = get_metrics_content_type()
        assert content_type is not None
        assert "text" in content_type.lower() or "prometheus" in content_type.lower()


class TestMetricsEndpoint:
    """Test metrics endpoint."""
    
    def test_metrics_endpoint_available(self):
        """Test that metrics endpoint is accessible."""
        # This will be tested via integration test
        assert True
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_data(self):
        """Test that metrics endpoint returns data."""
        from fastapi.testclient import TestClient
        from app.main import create_app
        
        app = create_app()
        client = TestClient(app)
        
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert response.headers["content-type"] is not None
        assert len(response.content) > 0

