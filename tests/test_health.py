import pytest
from fastapi.testclient import TestClient

from app.main import app


class StubBinanceClient:
    def get_price(self, symbol: str) -> float:  # noqa: ARG002
        return 42000.0


@pytest.fixture()
def client():
    app.state.binance_client = StubBinanceClient()
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["btc_price"] == 42000.0

