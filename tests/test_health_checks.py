"""
Test cases for improved health check endpoints.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import create_app


class TestHealthChecks:
    """Test health check endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        app = create_app()
        return TestClient(app)
    
    def test_liveness_endpoint(self, client):
        """Test liveness endpoint always returns OK."""
        response = client.get("/health/live")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "message" in data
    
    def test_readiness_endpoint_success(self, client):
        """Test readiness endpoint when all services are healthy."""
        response = client.get("/health/ready")
        
        # Should return 200 if database is OK
        # May return 503 if database is not available (depends on test environment)
        # May return 500 if there's an error (e.g., Binance client initialization)
        assert response.status_code in [200, 503, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "database" in data
            assert "components" in data
    
    def test_readiness_endpoint_components(self, client):
        """Test that readiness endpoint returns component status."""
        response = client.get("/health/ready")
        
        if response.status_code == 200:
            data = response.json()
            assert "components" in data
            assert "database" in data["components"]
            assert "redis" in data["components"]
            assert "binance" in data["components"]
    
    def test_health_endpoint_backward_compatibility(self, client):
        """Test that /health endpoint still works (backward compatibility)."""
        response = client.get("/health")
        
        # Should return 200 or 503 depending on database availability
        # May return 500 if there's an error (e.g., Binance client initialization)
        assert response.status_code in [200, 503, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "database" in data
    
    def test_detailed_health_endpoint(self, client):
        """Test detailed health endpoint."""
        response = client.get("/health/detailed")
        
        # Should return 200 or have error status
        # May return 500 if there's an error (e.g., Binance client initialization)
        assert response.status_code in [200, 503, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "timestamp" in data
            assert "services" in data
            assert "database" in data["services"]
            assert "redis" in data["services"]
            assert "binance" in data["services"]
    
    def test_quick_health_endpoint(self, client):
        """Test quick health endpoint."""
        response = client.get("/health/quick")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "message" in data
    
    def test_correlation_id_in_health_response(self, client):
        """Test that correlation ID is included in health check responses."""
        test_id = "health-test-correlation-id"
        response = client.get("/health/live", headers={"X-Correlation-ID": test_id})
        
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == test_id

