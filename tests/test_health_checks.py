"""
Test cases for improved health check endpoints.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.api.deps import get_db_session_dependency, get_binance_client


class StubBinanceClient:
    """Stub Binance client for testing."""
    def __init__(self):
        self.testnet = False
    
    def get_price(self, symbol: str) -> float:  # noqa: ARG002
        return 42000.0


def mock_db_session_generator():
    """Generator function that yields a mock database session."""
    mock_db_session = MagicMock(spec=Session)
    # Mock the execute method to return a mock result
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (1,)  # Return a tuple for SELECT 1
    mock_db_session.execute.return_value = mock_result
    try:
        yield mock_db_session
    finally:
        pass


class TestHealthChecks:
    """Test health check endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client with mocked dependencies."""
        app = create_app()
        
        # Override dependencies
        app.dependency_overrides[get_db_session_dependency] = mock_db_session_generator
        app.dependency_overrides[get_binance_client] = lambda: StubBinanceClient()
        
        # Set app state
        app.state.binance_client = StubBinanceClient()
        
        # Mock Redis to be disabled (so it doesn't try to connect)
        with patch('app.api.routes.health.get_settings') as mock_settings:
            mock_settings_instance = MagicMock()
            mock_settings_instance.redis_enabled = False
            mock_settings_instance.redis_url = "redis://localhost:6379/0"
            mock_settings.return_value = mock_settings_instance
            
            try:
                yield TestClient(app)
            finally:
                # Clean up dependency overrides
                app.dependency_overrides.pop(get_db_session_dependency, None)
                app.dependency_overrides.pop(get_binance_client, None)
    
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
        
        # Should return 200 when database is mocked and OK
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "components" in data
    
    def test_readiness_endpoint_components(self, client):
        """Test that readiness endpoint returns component status."""
        response = client.get("/health/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert "components" in data
        assert "database" in data["components"]
        assert "redis" in data["components"]
        assert "binance" in data["components"]
    
    def test_health_endpoint_backward_compatibility(self, client):
        """Test that /health endpoint still works (backward compatibility)."""
        response = client.get("/health")
        
        # Should return 200 when database is mocked and OK
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert data["database"] == "ok"
    
    def test_detailed_health_endpoint(self, client):
        """Test detailed health endpoint."""
        response = client.get("/health/detailed")
        
        # Should return 200 when database is mocked and OK
        assert response.status_code == 200
        
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

