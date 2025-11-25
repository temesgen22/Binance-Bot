from fastapi import Depends, Request

from app.core.my_binance_client import BinanceClient
from app.core.config import Settings, get_settings
from app.services.strategy_runner import StrategyRunner


def get_strategy_runner(request: Request) -> StrategyRunner:
    return request.app.state.strategy_runner


def get_settings_dependency() -> Settings:
    return get_settings()


def get_binance_client(request: Request) -> BinanceClient:
    return request.app.state.binance_client

