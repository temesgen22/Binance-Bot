from fastapi import Depends, Request

from app.core.my_binance_client import BinanceClient
from app.core.config import Settings, get_settings
from app.services.strategy_runner import StrategyRunner
from app.core.binance_client_manager import BinanceClientManager


def get_strategy_runner(request: Request) -> StrategyRunner:
    return request.app.state.strategy_runner


def get_settings_dependency() -> Settings:
    return get_settings()


def get_binance_client(request: Request) -> BinanceClient:
    return request.app.state.binance_client


def get_client_manager(request: Request) -> BinanceClientManager:
    """Dependency to get BinanceClientManager from app state."""
    if not hasattr(request.app.state, 'binance_client_manager'):
        from loguru import logger
        logger.warning("binance_client_manager not found in app state, creating fallback")
        # Try to create one as fallback
        from app.core.config import get_settings
        # Clear cache to ensure fresh settings from .env
        get_settings.cache_clear()
        settings = get_settings()
        # Force reload accounts
        settings._binance_accounts = None
        manager = BinanceClientManager(settings)
        request.app.state.binance_client_manager = manager
        logger.info(f"Created BinanceClientManager as fallback with {len(manager.list_accounts())} accounts")
    return request.app.state.binance_client_manager
