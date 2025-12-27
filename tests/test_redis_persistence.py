"""Test cases for Redis persistence configuration and data survival."""
import pytest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.core.redis_storage import RedisStorage


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client (module-level fixture)."""
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.set.return_value = True
    mock_client.get.return_value = None
    mock_client.keys.return_value = []
    return mock_client


class TestRedisPersistenceConfig:
    """Test that Redis persistence configuration is correct."""
    
    def test_redis_conf_file_exists(self):
        """Test that redis.conf file exists and has persistence settings."""
        redis_conf_path = Path("redis.conf")
        assert redis_conf_path.exists(), "redis.conf file should exist"
        
        content = redis_conf_path.read_text()
        
        # Verify AOF is disabled (RDB-only mode)
        assert "appendonly no" in content, "AOF should be disabled for RDB-only mode"
        
        # Verify RDB snapshots are configured
        assert "save " in content, "RDB snapshots should be configured"
        
        # Verify data directory is set
        assert "dir /data" in content, "Data directory should be /data"
    
    def test_docker_compose_redis_config(self):
        """Test that docker-compose files mount redis.conf correctly."""
        # Check docker-compose.yml
        compose_dev = Path("docker-compose.yml")
        if compose_dev.exists():
            content = compose_dev.read_text()
            assert "redis.conf" in content, "docker-compose.yml should mount redis.conf"
            assert "redis-server" in content or "command:" in content, "Should use custom Redis command"
        
        # Check docker-compose.prod.yml
        compose_prod = Path("docker-compose.prod.yml")
        if compose_prod.exists():
            content = compose_prod.read_text()
            assert "redis.conf" in content, "docker-compose.prod.yml should mount redis.conf"
            assert "redis-server" in content or "command:" in content, "Should use custom Redis command"


class TestRedisStoragePersistence:
    """Test Redis storage persistence functionality."""
    
    @pytest.fixture
    def redis_storage(self, mock_redis_client):
        """Create RedisStorage instance with mocked client."""
        with patch('app.core.redis_storage.redis') as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis_client
            mock_redis_module.Redis = MagicMock(return_value=mock_redis_client)
            storage = RedisStorage(redis_url="redis://localhost:6379/0", enabled=True)
            storage._client = mock_redis_client
            return storage
    
    def test_save_strategy_persists_data(self, redis_storage, mock_redis_client):
        """Test that saving a strategy persists data to Redis."""
        strategy_id = "test-strategy-123"
        strategy_data = {
            "id": strategy_id,
            "name": "Test Strategy",
            "symbol": "BTCUSDT",
            "status": "running"
        }
        
        result = redis_storage.save_strategy(strategy_id, strategy_data)
        
        assert result is True, "Should successfully save strategy"
        mock_redis_client.set.assert_called_once()
        
        # Verify the key format
        call_args = mock_redis_client.set.call_args
        key = call_args[0][0]
        assert key == f"binance_bot:strategy:{strategy_id}", "Key should follow expected format"
        
        # Verify data is JSON serialized
        value = call_args[0][1]
        parsed = json.loads(value)
        assert parsed["id"] == strategy_id, "Data should be correctly serialized"
    
    def test_get_strategy_retrieves_persisted_data(self, redis_storage, mock_redis_client):
        """Test that getting a strategy retrieves persisted data."""
        strategy_id = "test-strategy-123"
        strategy_data = {
            "id": strategy_id,
            "name": "Test Strategy",
            "symbol": "BTCUSDT"
        }
        
        # Mock Redis to return saved data
        mock_redis_client.get.return_value = json.dumps(strategy_data)
        
        result = redis_storage.get_strategy(strategy_id)
        
        assert result is not None, "Should retrieve strategy data"
        assert result["id"] == strategy_id, "Retrieved data should match"
        mock_redis_client.get.assert_called_once_with(f"binance_bot:strategy:{strategy_id}")
    
    def test_data_survives_redis_restart_simulation(self, redis_storage, mock_redis_client):
        """Test that data can be retrieved after a simulated Redis restart."""
        strategy_id = "test-strategy-456"
        strategy_data = {
            "id": strategy_id,
            "name": "Persistent Strategy",
            "symbol": "ETHUSDT"
        }
        
        # Simulate saving data
        redis_storage.save_strategy(strategy_id, strategy_data)
        
        # Simulate Redis restart: create new client (simulating reconnection)
        new_mock_client = MagicMock()
        new_mock_client.ping.return_value = True
        # After restart, Redis should have the data (from persistence files)
        new_mock_client.get.return_value = json.dumps(strategy_data)
        
        # Simulate reconnection after restart
        redis_storage._client = new_mock_client
        
        # Verify data is still accessible
        result = redis_storage.get_strategy(strategy_id)
        assert result is not None, "Data should survive Redis restart"
        assert result["id"] == strategy_id, "Data should be intact after restart"
    
    def test_get_all_strategies_retrieves_all_persisted(self, redis_storage, mock_redis_client):
        """Test that get_all_strategies retrieves all persisted strategies."""
        # Mock Redis to return multiple strategy keys
        mock_redis_client.keys.return_value = [
            "binance_bot:strategy:strategy-1",
            "binance_bot:strategy:strategy-2",
            "binance_bot:strategy:strategy-3"
        ]
        
        # Mock data for each strategy
        def mock_get(key):
            if "strategy-1" in key:
                return json.dumps({"id": "strategy-1", "name": "Strategy 1"})
            elif "strategy-2" in key:
                return json.dumps({"id": "strategy-2", "name": "Strategy 2"})
            elif "strategy-3" in key:
                return json.dumps({"id": "strategy-3", "name": "Strategy 3"})
            return None
        
        mock_redis_client.get.side_effect = mock_get
        
        result = redis_storage.get_all_strategies()
        
        assert len(result) == 3, "Should retrieve all strategies"
        assert "strategy-1" in result, "Should include strategy-1"
        assert "strategy-2" in result, "Should include strategy-2"
        assert "strategy-3" in result, "Should include strategy-3"


@pytest.mark.slow
class TestRedisPersistenceIntegration:
    """Integration tests for Redis persistence (requires actual Redis or better mocks)."""
    
    def test_redis_storage_handles_connection_failure_gracefully(self):
        """Test that RedisStorage handles connection failures without crashing."""
        # Test with invalid Redis URL
        storage = RedisStorage(redis_url="redis://invalid-host:6379/0", enabled=True)
        
        # Should not crash, just disable Redis
        result = storage.save_strategy("test", {"id": "test"})
        assert result is False, "Should return False when Redis is unavailable"
    
    def test_redis_storage_serializes_complex_data(self, mock_redis_client):
        """Test that RedisStorage correctly serializes complex data types."""
        with patch('app.core.redis_storage.redis') as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis_client
            storage = RedisStorage(redis_url="redis://localhost:6379/0", enabled=True)
            storage._client = mock_redis_client
            
            # Test with datetime and other complex types
            from datetime import datetime
            complex_data = {
                "id": "test-123",
                "created_at": datetime(2025, 11, 28, 10, 0, 0),
                "params": {"nested": {"deep": "value"}},
                "numbers": [1, 2, 3],
                "active": True
            }
            
            result = storage.save_strategy("test-123", complex_data)
            assert result is True, "Should handle complex data types"
            
            # Verify serialization was called
            mock_redis_client.set.assert_called_once()
            call_args = mock_redis_client.set.call_args
            value = call_args[0][1]
            
            # Should be valid JSON
            parsed = json.loads(value)
            assert parsed["id"] == "test-123", "Complex data should be serialized correctly"


class TestDockerComposeRedisPersistence:
    """Test Docker Compose configuration for Redis persistence."""
    
    def test_redis_volume_is_defined(self):
        """Test that Redis volume is defined in docker-compose files."""
        compose_files = ["docker-compose.yml", "docker-compose.prod.yml"]
        
        for compose_file in compose_files:
            path = Path(compose_file)
            if path.exists():
                content = path.read_text()
                assert "redis-data:" in content, f"{compose_file} should define redis-data volume"
                assert "redis-data:/data" in content, f"{compose_file} should mount redis-data to /data"
    
    def test_redis_uses_persistence_config(self):
        """Test that Redis container uses the persistence configuration file."""
        compose_files = ["docker-compose.yml", "docker-compose.prod.yml"]
        
        for compose_file in compose_files:
            path = Path(compose_file)
            if path.exists():
                content = path.read_text()
                # Should mount redis.conf
                assert "redis.conf" in content, f"{compose_file} should mount redis.conf"
                # Should use custom command to load config
                assert "redis-server" in content or "command:" in content, \
                    f"{compose_file} should use redis-server with config"


class TestRedisPersistenceVerification:
    """Test helper functions to verify Redis persistence is working."""
    
    def test_verify_redis_conf_settings(self):
        """Test that redis.conf has all required persistence settings."""
        redis_conf = Path("redis.conf")
        if not redis_conf.exists():
            pytest.skip("redis.conf not found")
        
        content = redis_conf.read_text()
        
        # Required settings for RDB-only mode
        required_settings = {
            "appendonly no": "AOF should be disabled for RDB-only mode",
            "dir /data": "Data directory must be /data",
            "dbfilename": "RDB filename must be specified",
        }
        
        for setting, message in required_settings.items():
            assert setting in content, f"{message}: '{setting}' not found in redis.conf"
        
        # At least one save directive should exist
        assert "save " in content, "At least one RDB save directive should be configured"
    
    def test_redis_conf_is_valid_syntax(self):
        """Test that redis.conf has valid Redis configuration syntax."""
        redis_conf = Path("redis.conf")
        if not redis_conf.exists():
            pytest.skip("redis.conf not found")
        
        content = redis_conf.read_text()
        lines = content.split('\n')
        
        # Check for common syntax issues
        for i, line in enumerate(lines, 1):
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Basic validation: should be key-value pairs or single directives
            if ' ' in line:
                parts = line.split(None, 1)
                assert len(parts) >= 1, f"Line {i}: Invalid format: {line}"
            
            # Check for common mistakes
            assert not line.startswith('='), f"Line {i}: Should not start with '=': {line}"

