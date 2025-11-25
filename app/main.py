from __future__ import annotations

import asyncio

from fastapi import FastAPI

from app.api.routes import health, strategies
from app.core.my_binance_client import BinanceClient
from app.core.config import get_settings
from app.core.logger import configure_logging
from app.core.redis_storage import RedisStorage
from app.risk.manager import RiskManager
from app.services.order_executor import OrderExecutor
from app.services.strategy_runner import StrategyRunner


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    client = BinanceClient(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
        testnet=settings.binance_testnet,
    )

    risk = RiskManager(client=client)
    executor = OrderExecutor(client=client)
    
    # Initialize Redis storage if enabled
    redis_storage = None
    if settings.redis_enabled:
        redis_storage = RedisStorage(
            redis_url=settings.redis_url,
            enabled=settings.redis_enabled
        )
    
    runner = StrategyRunner(
        client=client,
        risk=risk,
        executor=executor,
        max_concurrent=settings.max_concurrent_strategies,
        redis_storage=redis_storage,
    )

    app = FastAPI(title="Binance Trading Bot", version="0.1.0")

    @app.on_event("startup")
    async def startup() -> None:  # pragma: no cover
        app.state.binance_client = client
        app.state.strategy_runner = runner
        app.state.background_tasks: list[asyncio.Task] = []

    @app.on_event("shutdown")
    async def shutdown() -> None:  # pragma: no cover
        for task in app.state.background_tasks:
            task.cancel()

    app.include_router(health.router)
    app.include_router(strategies.router)
    return app


app = create_app()

