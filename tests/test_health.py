import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from app.main import app
from app.api.deps import get_db_session_dependency, get_binance_client


class StubBinanceClient:
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


@pytest.fixture()
def client():
    """Create a test client with mocked dependencies."""
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


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert data["database"] == "ok"
    assert data["redis"] == "disabled"
    assert data["btc_price"] == 42000.0

