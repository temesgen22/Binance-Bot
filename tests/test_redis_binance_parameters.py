"""Test cases for Redis persistence with Binance trade parameters."""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.order import OrderResponse
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.core.redis_storage import RedisStorage


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.set.return_value = True
    mock_client.get.return_value = None
    mock_client.keys.return_value = []
    return mock_client


@pytest.fixture
def redis_storage(mock_redis_client):
    """Create RedisStorage instance with mocked client."""
    with patch('app.core.redis_storage.redis') as mock_redis_module:
        mock_redis_module.from_url.return_value = mock_redis_client
        mock_redis_module.Redis = MagicMock(return_value=mock_redis_client)
        storage = RedisStorage(redis_url="redis://localhost:6379/0", enabled=True)
        storage._client = mock_redis_client
        return storage


class TestRedisOrderResponseBinanceParameters:
    """Test Redis persistence with OrderResponse containing Binance parameters."""
    
    def test_save_order_response_with_all_binance_parameters(self, redis_storage, mock_redis_client):
        """Test that OrderResponse with all Binance parameters can be serialized and saved."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        update_time = datetime(2024, 1, 15, 10, 30, 50, tzinfo=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.5,
            executed_qty=0.1,
            timestamp=order_time,
            commission=0.0195,
            commission_asset="USDT",
            leverage=10,
            position_side="LONG",
            update_time=update_time,
            time_in_force="GTC",
            order_type="MARKET",
            notional_value=5000.05,
            cummulative_quote_qty=5000.05,
            initial_margin=50.25,
            margin_type="ISOLATED",
            client_order_id="my_order_123",
            working_type="MARK_PRICE",
            stop_price=None,
        )
        
        # Convert to dict for storage
        order_dict = order.model_dump()
        
        # Save as trade
        trades = [order_dict]
        result = redis_storage.save_trades("test-strategy-1", trades)
        
        assert result is True, "Should successfully save trades with Binance parameters"
        mock_redis_client.set.assert_called_once()
        
        # Verify data was serialized correctly
        call_args = mock_redis_client.set.call_args
        value = call_args[0][1]
        parsed = json.loads(value)
        
        assert len(parsed) == 1, "Should have 1 trade"
        trade_data = parsed[0]
        
        # Verify Binance parameters are preserved
        assert trade_data["symbol"] == "BTCUSDT"
        assert trade_data["order_id"] == 12345
        assert trade_data["commission"] == 0.0195
        assert trade_data["commission_asset"] == "USDT"
        assert trade_data["leverage"] == 10
        assert trade_data["initial_margin"] == 50.25
        assert trade_data["margin_type"] == "ISOLATED"
        assert trade_data["notional_value"] == 5000.05
        assert trade_data["client_order_id"] == "my_order_123"
        
        # Verify timestamps are serialized correctly
        assert "timestamp" in trade_data
        assert trade_data["timestamp"] == order_time.isoformat()
        assert "update_time" in trade_data
        assert trade_data["update_time"] == update_time.isoformat()
    
    def test_retrieve_order_response_with_binance_parameters(self, redis_storage, mock_redis_client):
        """Test that OrderResponse with Binance parameters can be retrieved from Redis."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        
        order_dict = {
            "symbol": "BTCUSDT",
            "order_id": 12345,
            "status": "FILLED",
            "side": "BUY",
            "price": 50000.0,
            "avg_price": 50000.5,
            "executed_qty": 0.1,
            "timestamp": order_time.isoformat(),
            "commission": 0.0195,
            "commission_asset": "USDT",
            "leverage": 10,
            "position_side": "LONG",
            "initial_margin": 50.25,
            "margin_type": "ISOLATED",
            "notional_value": 5000.05,
            "client_order_id": "my_order_123",
        }
        
        # Mock Redis to return saved data
        mock_redis_client.get.return_value = json.dumps([order_dict])
        
        trades = redis_storage.get_trades("test-strategy-1")
        
        assert len(trades) == 1, "Should retrieve 1 trade"
        trade_data = trades[0]
        
        # Verify all Binance parameters are retrieved
        assert trade_data["symbol"] == "BTCUSDT"
        assert trade_data["order_id"] == 12345
        assert trade_data["commission"] == 0.0195
        assert trade_data["commission_asset"] == "USDT"
        assert trade_data["leverage"] == 10
        assert trade_data["initial_margin"] == 50.25
        assert trade_data["margin_type"] == "ISOLATED"
        assert trade_data["notional_value"] == 5000.05
        assert trade_data["client_order_id"] == "my_order_123"
        
        # Verify timestamp is present (as ISO string)
        assert "timestamp" in trade_data
        assert isinstance(trade_data["timestamp"], str)
    
    def test_redis_handles_missing_optional_binance_parameters(self, redis_storage, mock_redis_client):
        """Test that Redis handles OrderResponse without optional Binance parameters."""
        order_dict = {
            "symbol": "BTCUSDT",
            "order_id": 12345,
            "status": "FILLED",
            "side": "BUY",
            "price": 50000.0,
            "avg_price": 50000.0,
            "executed_qty": 0.1,
            # No optional Binance parameters
        }
        
        # Save trade without optional parameters
        result = redis_storage.save_trades("test-strategy-2", [order_dict])
        assert result is True, "Should handle missing optional parameters"
        
        # Mock retrieval
        mock_redis_client.get.return_value = json.dumps([order_dict])
        trades = redis_storage.get_trades("test-strategy-2")
        
        assert len(trades) == 1, "Should retrieve trade without optional parameters"
        assert trades[0]["symbol"] == "BTCUSDT"


class TestRedisStrategyWithBinanceParameters:
    """Test Redis persistence for strategies that use Binance parameters."""
    
    def test_save_strategy_with_binance_trades(self, redis_storage, mock_redis_client):
        """Test saving strategy that contains trades with Binance parameters."""
        strategy_data = {
            "id": "test-strategy-binance",
            "name": "Test Strategy with Binance Params",
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "status": "running",
            "leverage": 10,
        }
        
        result = redis_storage.save_strategy("test-strategy-binance", strategy_data)
        assert result is True, "Should save strategy"
        
        # Verify key format
        call_args = mock_redis_client.set.call_args
        key = call_args[0][0]
        assert key == "binance_bot:strategy:test-strategy-binance"
        
        # Verify data is serialized
        value = call_args[0][1]
        parsed = json.loads(value)
        assert parsed["id"] == "test-strategy-binance"
        assert parsed["leverage"] == 10
    
    def test_redis_persistence_survives_restart_with_binance_parameters(self, redis_storage, mock_redis_client):
        """Test that Binance parameters survive Redis restart simulation."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        
        # Save trades with Binance parameters
        trades = [{
            "symbol": "BTCUSDT",
            "order_id": 12345,
            "status": "FILLED",
            "side": "BUY",
            "price": 50000.0,
            "avg_price": 50000.0,
            "executed_qty": 0.1,
            "timestamp": order_time.isoformat(),
            "commission": 0.0195,
            "commission_asset": "USDT",
            "leverage": 10,
            "initial_margin": 50.25,
            "margin_type": "ISOLATED",
        }]
        
        redis_storage.save_trades("test-strategy-persist", trades)
        
        # Simulate Redis restart: create new client
        new_mock_client = MagicMock()
        new_mock_client.ping.return_value = True
        # After restart, Redis should have the data
        new_mock_client.get.return_value = json.dumps(trades)
        
        redis_storage._client = new_mock_client
        
        # Retrieve after "restart"
        retrieved_trades = redis_storage.get_trades("test-strategy-persist")
        
        assert len(retrieved_trades) == 1, "Trades should survive Redis restart"
        assert retrieved_trades[0]["commission"] == 0.0195, "Commission should be preserved"
        assert retrieved_trades[0]["initial_margin"] == 50.25, "Initial margin should be preserved"
        assert retrieved_trades[0]["margin_type"] == "ISOLATED", "Margin type should be preserved"
    
    def test_redis_serializes_datetime_objects_in_binance_parameters(self, redis_storage, mock_redis_client):
        """Test that Redis correctly serializes datetime objects in Binance parameters."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        update_time = datetime(2024, 1, 15, 10, 30, 50, tzinfo=timezone.utc)
        
        # Create OrderResponse with datetime objects
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=order_time,
            update_time=update_time,
            commission=0.02,
            leverage=10,
        )
        
        order_dict = order.model_dump()
        trades = [order_dict]
        
        result = redis_storage.save_trades("test-datetime", trades)
        assert result is True, "Should serialize datetime objects"
        
        # Verify datetime was converted to ISO string
        call_args = mock_redis_client.set.call_args
        value = call_args[0][1]
        parsed = json.loads(value)
        
        trade_data = parsed[0]
        assert isinstance(trade_data["timestamp"], str), "Timestamp should be ISO string"
        assert isinstance(trade_data["update_time"], str), "Update time should be ISO string"
        assert trade_data["timestamp"] == order_time.isoformat(), "Timestamp should match"
        assert trade_data["update_time"] == update_time.isoformat(), "Update time should match"


class TestRedisComplexBinanceData:
    """Test Redis with complex Binance trade data structures."""
    
    def test_redis_handles_multiple_trades_with_binance_parameters(self, redis_storage, mock_redis_client):
        """Test Redis handling multiple trades with various Binance parameters."""
        trades = [
            {
                "symbol": "BTCUSDT",
                "order_id": 1001,
                "status": "FILLED",
                "side": "BUY",
                "price": 50000.0,
                "avg_price": 50000.0,
                "executed_qty": 0.1,
                "timestamp": datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc).isoformat(),
                "commission": 0.02,
                "leverage": 10,
                "margin_type": "ISOLATED",
            },
            {
                "symbol": "BTCUSDT",
                "order_id": 1002,
                "status": "FILLED",
                "side": "SELL",
                "price": 51000.0,
                "avg_price": 51000.0,
                "executed_qty": 0.1,
                "timestamp": datetime(2024, 1, 15, 11, 30, 45, tzinfo=timezone.utc).isoformat(),
                "commission": 0.0204,
                "leverage": 10,
                "margin_type": "ISOLATED",
            },
        ]
        
        result = redis_storage.save_trades("test-multiple", trades)
        assert result is True, "Should save multiple trades"
        
        # Mock retrieval
        mock_redis_client.get.return_value = json.dumps(trades)
        retrieved = redis_storage.get_trades("test-multiple")
        
        assert len(retrieved) == 2, "Should retrieve all trades"
        assert retrieved[0]["order_id"] == 1001, "First trade should match"
        assert retrieved[1]["order_id"] == 1002, "Second trade should match"
        assert retrieved[0]["margin_type"] == "ISOLATED", "Margin type should be preserved"
        assert retrieved[1]["margin_type"] == "ISOLATED", "Margin type should be preserved"
    
    def test_redis_handles_none_values_in_binance_parameters(self, redis_storage, mock_redis_client):
        """Test that Redis handles None values in optional Binance parameters."""
        trade = {
            "symbol": "BTCUSDT",
            "order_id": 12345,
            "status": "FILLED",
            "side": "BUY",
            "price": 50000.0,
            "avg_price": 50000.0,
            "executed_qty": 0.1,
            "commission": None,  # Optional field with None
            "initial_margin": None,  # Optional field with None
            "margin_type": None,  # Optional field with None
        }
        
        result = redis_storage.save_trades("test-none-values", [trade])
        assert result is True, "Should handle None values"
        
        # Mock retrieval
        mock_redis_client.get.return_value = json.dumps([trade])
        retrieved = redis_storage.get_trades("test-none-values")
        
        assert len(retrieved) == 1, "Should retrieve trade with None values"
        assert retrieved[0]["commission"] is None, "None values should be preserved"


class TestRedisConnectionHandling:
    """Test Redis connection handling with Binance parameters."""
    
    def test_redis_handles_connection_failure_gracefully(self):
        """Test that RedisStorage handles connection failures without crashing."""
        # Test with invalid Redis URL
        storage = RedisStorage(redis_url="redis://invalid-host:6379/0", enabled=True)
        
        # Should not crash, just disable Redis
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            commission=0.02,
            leverage=10,
        )
        
        trades = [order.model_dump()]
        result = storage.save_trades("test-fail", trades)
        assert result is False, "Should return False when Redis is unavailable"
    
    def test_redis_disabled_mode(self):
        """Test that RedisStorage works when disabled."""
        storage = RedisStorage(redis_url="redis://localhost:6379/0", enabled=False)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
        )
        
        trades = [order.model_dump()]
        result = storage.save_trades("test-disabled", trades)
        assert result is False, "Should return False when Redis is disabled"
        
        retrieved = storage.get_trades("test-disabled")
        assert retrieved == [], "Should return empty list when Redis is disabled"

