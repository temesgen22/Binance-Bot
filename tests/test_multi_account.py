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


# Removed TestMultiAccountConfig and TestBinanceClientManager classes
# These tested loading accounts from .env file, which is no longer supported.
# Accounts are now loaded from database only.


class TestStrategyWithMultiAccount:
    """Tests for strategy creation and execution with multiple accounts."""
    
    def make_runner_with_accounts(self):
        """Create a StrategyRunner with multiple accounts."""
        # Create mock clients
        default_client = MagicMock(spec=BinanceClient)
        main_client = MagicMock(spec=BinanceClient)
        
        # Create client manager (accounts are loaded from database, not .env)
        settings = get_settings()
        manager = BinanceClientManager(settings)
        
        # Manually add accounts to manager (simulating database-loaded accounts)
        default_account = BinanceAccountConfig(
            account_id="default",
            api_key="default_key",
            api_secret="default_secret",
            testnet=True
        )
        main_account = BinanceAccountConfig(
            account_id="main",
            api_key="main_key",
            api_secret="main_secret",
            testnet=False
        )
        
        manager._clients = {
            'default': default_client,
            'main': main_client,
        }
        manager._accounts = {
            'default': default_account,
            'main': main_account,
        }
        
        # Create default risk and executor
        default_risk = MagicMock(spec=RiskManager)
        default_executor = MagicMock(spec=OrderExecutor)
        
        return StrategyRunner(
            client_manager=manager,
            client=default_client,
            risk=default_risk,
            executor=default_executor,
            max_concurrent=5,
            use_websocket=False,  # Disable WebSocket in tests
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
        
        # Accounts are loaded from database, not .env
        settings = get_settings()
        manager = BinanceClientManager(settings)
        
        # Manually add default account (simulating database-loaded account)
        default_account = BinanceAccountConfig(
            account_id="default",
            api_key="default_key",
            api_secret="default_secret",
            testnet=True
        )
        manager._clients = {'default': default_client}
        manager._accounts = {'default': default_account}
        
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


# Removed TestAccountsAPI.test_list_accounts_endpoint
# This test was checking accounts loaded from .env file.
# The /accounts/list endpoint now returns accounts from database only.
# To test this endpoint, you would need to set up database fixtures with test accounts.


# Run tests with: pytest tests/test_multi_account.py -v

