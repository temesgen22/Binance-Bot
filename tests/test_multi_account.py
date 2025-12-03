"""Tests for multi-account Binance functionality."""
import asyncio
import os
from unittest.mock import MagicMock, patch
from typing import Dict

import pytest

from app.core.config import Settings, BinanceAccountConfig, get_settings
from app.core.binance_client_manager import BinanceClientManager
from app.core.my_binance_client import BinanceClient
from app.models.strategy import CreateStrategyRequest, StrategyType, StrategyParams, StrategyState
from app.services.strategy_runner import StrategyRunner
from app.risk.manager import RiskManager
from app.services.order_executor import OrderExecutor


class TestMultiAccountConfig:
    """Tests for multi-account configuration loading."""
    
    def test_default_account_loading(self):
        """Test that default account is loaded from BINANCE_API_KEY/SECRET."""
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_TESTNET': 'true',
        }):
            # Clear cache to force reload
            get_settings.cache_clear()
            settings = get_settings()
            
            accounts = settings.get_binance_accounts()
            assert 'default' in accounts
            assert accounts['default'].api_key == 'default_key'
            assert accounts['default'].api_secret == 'default_secret'
            assert accounts['default'].testnet is True
            assert accounts['default'].account_id == 'default'
    
    def test_additional_account_loading(self):
        """Test loading additional accounts from environment variables."""
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_TESTNET': 'true',
            'BINANCE_ACCOUNT_main_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_main_API_SECRET': 'main_secret',
            'BINANCE_ACCOUNT_main_NAME': 'Main Account',
            'BINANCE_ACCOUNT_main_TESTNET': 'false',
            'BINANCE_ACCOUNT_test_API_KEY': 'test_key',
            'BINANCE_ACCOUNT_test_API_SECRET': 'test_secret',
            'BINANCE_ACCOUNT_test_NAME': 'Test Account',
        }, clear=False):
            # Clear cache to force reload
            get_settings.cache_clear()
            settings = get_settings()
            
            accounts = settings.get_binance_accounts()
            
            # Check default account
            assert 'default' in accounts
            assert accounts['default'].api_key == 'default_key'
            
            # Check main account
            assert 'main' in accounts
            assert accounts['main'].api_key == 'main_key'
            assert accounts['main'].api_secret == 'main_secret'
            assert accounts['main'].name == 'Main Account'
            assert accounts['main'].testnet is False
            
            # Check test account (should inherit testnet from default)
            assert 'test' in accounts
            assert accounts['test'].api_key == 'test_key'
            assert accounts['test'].api_secret == 'test_secret'
            assert accounts['test'].name == 'Test Account'
            assert accounts['test'].testnet is True  # Inherits from BINANCE_TESTNET
    
    def test_get_account_by_id(self):
        """Test getting a specific account by ID."""
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_ACCOUNT_main_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_main_API_SECRET': 'main_secret',
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            
            account = settings.get_binance_account('main')
            assert account is not None
            assert account.api_key == 'main_key'
            
            account = settings.get_binance_account('nonexistent')
            assert account is None
    
    def test_account_id_case_insensitive(self):
        """Test that account IDs are case-insensitive."""
        with patch.dict(os.environ, {
            'BINANCE_ACCOUNT_MAIN_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_MAIN_API_SECRET': 'main_secret',
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            
            accounts = settings.get_binance_accounts()
            # Should be stored as lowercase
            assert 'main' in accounts
            assert accounts['main'].api_key == 'main_key'
            
            # Should be retrievable with any case
            assert settings.get_binance_account('MAIN') is not None
            assert settings.get_binance_account('Main') is not None


class TestBinanceClientManager:
    """Tests for BinanceClientManager."""
    
    @patch('app.core.binance_client_manager.BinanceClient')
    def test_client_manager_initialization(self, mock_client_class):
        """Test that client manager initializes clients for all accounts."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_TESTNET': 'true',
            'BINANCE_ACCOUNT_main_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_main_API_SECRET': 'main_secret',
            'BINANCE_ACCOUNT_main_TESTNET': 'false',
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            
            manager = BinanceClientManager(settings)
            
            # Should have created clients for both accounts
            assert 'default' in manager._clients
            assert 'main' in manager._clients
            # Check that at least 2 clients were created (may be more if other accounts exist in env)
            assert mock_client_class.call_count >= 2, f"Expected at least 2 clients, got {mock_client_class.call_count}"
            assert len(manager._clients) >= 2, f"Expected at least 2 clients in manager, got {len(manager._clients)}"
    
    @patch('app.core.binance_client_manager.BinanceClient')
    def test_get_client(self, mock_client_class):
        """Test getting a client by account ID."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_ACCOUNT_main_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_main_API_SECRET': 'main_secret',
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            manager = BinanceClientManager(settings)
            
            client = manager.get_client('main')
            assert client is not None
            
            client = manager.get_client('nonexistent')
            assert client is None
    
    @patch('app.core.binance_client_manager.BinanceClient')
    def test_list_accounts(self, mock_client_class):
        """Test listing all configured accounts."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_ACCOUNT_main_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_main_API_SECRET': 'main_secret',
            'BINANCE_ACCOUNT_main_NAME': 'Main Account',
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            manager = BinanceClientManager(settings)
            
            accounts = manager.list_accounts()
            assert 'default' in accounts
            assert 'main' in accounts
            assert accounts['main'].name == 'Main Account'
    
    @patch('app.core.binance_client_manager.BinanceClient')
    def test_account_exists(self, mock_client_class):
        """Test checking if an account exists."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_ACCOUNT_main_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_main_API_SECRET': 'main_secret',
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            manager = BinanceClientManager(settings)
            
            assert manager.account_exists('default') is True
            assert manager.account_exists('main') is True
            assert manager.account_exists('nonexistent') is False


class TestStrategyWithMultiAccount:
    """Tests for strategy creation and execution with multiple accounts."""
    
    def make_runner_with_accounts(self):
        """Create a StrategyRunner with multiple accounts."""
        # Create mock clients
        default_client = MagicMock(spec=BinanceClient)
        main_client = MagicMock(spec=BinanceClient)
        
        # Create client manager
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_ACCOUNT_main_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_main_API_SECRET': 'main_secret',
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            
            manager = BinanceClientManager(settings)
            manager._clients = {
                'default': default_client,
                'main': main_client,
            }
            manager._accounts = settings.get_binance_accounts()
            
            # Create default risk and executor
            default_risk = MagicMock(spec=RiskManager)
            default_executor = MagicMock(spec=OrderExecutor)
            
            return StrategyRunner(
                client_manager=manager,
                client=default_client,
                risk=default_risk,
                executor=default_executor,
                max_concurrent=5,
            ), default_client, main_client
    
    def test_register_strategy_with_account_id(self):
        """Test registering a strategy with a specific account_id."""
        runner, default_client, main_client = self.make_runner_with_accounts()
        
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload = CreateStrategyRequest(
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="main",  # Use main account
            params=params,
        )
        
        summary = runner.register(payload)
        assert summary.account_id == "main"
        assert summary.status == StrategyState.stopped
    
    def test_register_strategy_with_default_account(self):
        """Test registering a strategy without account_id (uses default)."""
        runner, default_client, main_client = self.make_runner_with_accounts()
        
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload = CreateStrategyRequest(
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            # account_id not specified - should use default
            params=params,
        )
        
        summary = runner.register(payload)
        assert summary.account_id == "default"
    
    def test_register_strategy_with_invalid_account(self):
        """Test that registering with invalid account_id raises error."""
        runner, default_client, main_client = self.make_runner_with_accounts()
        
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload = CreateStrategyRequest(
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="nonexistent",  # Invalid account
            params=params,
        )
        
        with pytest.raises(ValueError, match="not found"):
            runner.register(payload)
    
    @pytest.mark.asyncio
    async def test_start_strategy_uses_correct_account_client(self):
        """Test that starting a strategy uses the correct account's client."""
        from unittest.mock import AsyncMock
        
        runner, default_client, main_client = self.make_runner_with_accounts()
        
        # Register strategy with main account
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload = CreateStrategyRequest(
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="main",
            params=params,
        )
        
        summary = runner.register(payload)
        
        # Mock strategy methods
        mock_strategy = MagicMock()
        mock_strategy.evaluate = AsyncMock(return_value=MagicMock(action="HOLD"))
        mock_strategy.context = MagicMock(interval_seconds=1)
        mock_strategy.sync_position_state = MagicMock()
        mock_strategy.teardown = AsyncMock()
        
        # Mock registry to return our mock strategy
        with patch.object(runner.registry, 'build', return_value=mock_strategy):
            # Mock _update_position_info to avoid actual API calls
            async def mock_update_position_info(summary):
                summary.position_size = 0
                summary.position_side = None
            
            runner._update_position_info = mock_update_position_info
            
            # Start strategy
            started = await runner.start(summary.id)
            assert started.status == StrategyState.running
            
            # Verify that main_client was used (not default_client)
            # The strategy should be built with main_client
            runner.registry.build.assert_called_once()
            call_args = runner.registry.build.call_args
            assert call_args[0][2] == main_client  # Third argument is the client
            
            # Clean up
            if summary.id in runner._tasks:
                task = runner._tasks.pop(summary.id)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing code."""
    
    def test_strategy_without_account_id_uses_default(self):
        """Test that strategies without account_id still work (backward compatibility)."""
        # Create runner with just default client (old way)
        default_client = MagicMock(spec=BinanceClient)
        default_risk = MagicMock(spec=RiskManager)
        default_executor = MagicMock(spec=OrderExecutor)
        
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            manager = BinanceClientManager(settings)
            manager._clients = {'default': default_client}
            manager._accounts = settings.get_binance_accounts()
            
            runner = StrategyRunner(
                client=default_client,
                client_manager=manager,
                risk=default_risk,
                executor=default_executor,
                max_concurrent=5,
            )
            
            params = StrategyParams(ema_fast=8, ema_slow=21)
            payload = CreateStrategyRequest(
                name="Test Strategy",
                symbol="BTCUSDT",
                strategy_type=StrategyType.scalping,
                leverage=5,
                risk_per_trade=0.01,
                # No account_id - should default to "default"
                params=params,
            )
            
            summary = runner.register(payload)
            assert summary.account_id == "default"
    
    def test_old_runner_initialization_still_works(self):
        """Test that old way of initializing StrategyRunner still works."""
        default_client = MagicMock(spec=BinanceClient)
        default_risk = MagicMock(spec=RiskManager)
        default_executor = MagicMock(spec=OrderExecutor)
        
        # Old way: just pass client, risk, executor
        runner = StrategyRunner(
            client=default_client,
            risk=default_risk,
            executor=default_executor,
            max_concurrent=5,
        )
        
        # Should still work - creates client_manager internally
        assert runner.client_manager is not None
        assert runner.client == default_client


class TestAccountsAPI:
    """Tests for the accounts API endpoint."""
    
    @patch('app.core.binance_client_manager.BinanceClient')
    def test_list_accounts_endpoint(self, mock_client_class):
        """Test the /accounts/list API endpoint."""
        from fastapi.testclient import TestClient
        from app.main import create_app
        
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        with patch.dict(os.environ, {
            'BINANCE_API_KEY': 'default_key',
            'BINANCE_API_SECRET': 'default_secret',
            'BINANCE_ACCOUNT_main_API_KEY': 'main_key',
            'BINANCE_ACCOUNT_main_API_SECRET': 'main_secret',
            'BINANCE_ACCOUNT_main_NAME': 'Main Account',
            'BINANCE_ACCOUNT_main_TESTNET': 'false',
        }, clear=False):
            get_settings.cache_clear()
            
            app = create_app()
            # Ensure app state is set up (startup event may not run in test client)
            if not hasattr(app.state, 'binance_client_manager'):
                from app.core.binance_client_manager import BinanceClientManager
                settings = get_settings()
                app.state.binance_client_manager = BinanceClientManager(settings)
            
            client = TestClient(app)
            
            response = client.get("/accounts/list")
            assert response.status_code == 200
            
            data = response.json()
            assert 'default' in data
            assert 'main' in data
            
            # Check default account
            assert data['default']['account_id'] == 'default'
            assert data['default']['testnet'] == 'True'
            
            # Check main account
            assert data['main']['account_id'] == 'main'
            assert data['main']['name'] == 'Main Account'
            assert data['main']['testnet'] == 'False'


# Run tests with: pytest tests/test_multi_account.py -v

