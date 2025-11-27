from __future__ import annotations

import asyncio

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from fastapi.exceptions import RequestValidationError

from app.api.routes.health import router as health_router
from app.api.routes.strategies import router as strategies_router
from app.api.routes.logs import router as logs_router
from app.api.routes.trades import router as trades_router
from app.api.routes.strategy_performance import router as strategy_performance_router
from app.api.exception_handlers import (
    binance_rate_limit_handler,
    binance_api_error_handler,
    strategy_not_found_handler,
    strategy_already_running_handler,
    strategy_not_running_handler,
    max_concurrent_strategies_handler,
    invalid_leverage_handler,
    position_sizing_handler,
    order_execution_handler,
    binance_bot_exception_handler,
    validation_error_handler,
    general_exception_handler,
)
from app.core.my_binance_client import BinanceClient
from app.core.config import get_settings
from app.core.logger import configure_logging
from app.core.redis_storage import RedisStorage
from app.core.exceptions import (
    BinanceAPIError,
    BinanceRateLimitError,
    BinanceNetworkError,
    BinanceAuthenticationError,
    StrategyNotFoundError,
    StrategyAlreadyRunningError,
    StrategyNotRunningError,
    MaxConcurrentStrategiesError,
    InvalidLeverageError,
    PositionSizingError,
    OrderExecutionError,
    BinanceBotException,
)
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

    # Register exception handlers (order matters - most specific first)
    app.add_exception_handler(BinanceRateLimitError, binance_rate_limit_handler)
    app.add_exception_handler(BinanceAuthenticationError, binance_api_error_handler)
    app.add_exception_handler(BinanceNetworkError, binance_api_error_handler)
    app.add_exception_handler(BinanceAPIError, binance_api_error_handler)
    app.add_exception_handler(StrategyNotFoundError, strategy_not_found_handler)
    app.add_exception_handler(StrategyAlreadyRunningError, strategy_already_running_handler)
    app.add_exception_handler(StrategyNotRunningError, strategy_not_running_handler)
    app.add_exception_handler(MaxConcurrentStrategiesError, max_concurrent_strategies_handler)
    app.add_exception_handler(InvalidLeverageError, invalid_leverage_handler)
    app.add_exception_handler(PositionSizingError, position_sizing_handler)
    app.add_exception_handler(OrderExecutionError, order_execution_handler)
    app.add_exception_handler(BinanceBotException, binance_bot_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    @app.on_event("startup")
    async def startup() -> None:  # pragma: no cover
        app.state.binance_client = client
        app.state.strategy_runner = runner
        app.state.background_tasks: list[asyncio.Task] = []

    @app.on_event("shutdown")
    async def shutdown() -> None:  # pragma: no cover
        for task in app.state.background_tasks:
            task.cancel()

    # Serve static files (GUI)
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    index_path = static_dir / "index.html"
    
    # Mount static files
    if static_dir.exists():
        try:
            app.mount("/static", StaticFiles(directory=str(static_dir.resolve())), name="static")
        except Exception:
            pass  # Ignore if mount fails
    
    # Register GUI routes BEFORE API routers to ensure they take precedence
    # Serve index.html at root - register this route explicitly
    @app.get("/", tags=["gui"])
    async def root():
        """Serve the Log Viewer GUI at the root URL."""
        # Use absolute path to ensure it works in Docker containers
        abs_index_path = index_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations in case of path resolution issues
        possible_paths = [
            abs_index_path,
            index_path,
            abs_static_dir / "index.html",
            static_dir / "index.html",
        ]
        
        for path in possible_paths:
            if path.exists():
                return FileResponse(
                    path=str(path),
                    media_type="text/html"
                )
        
        # If file not found, return detailed error
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Log Viewer GUI not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
                "current_file": str(Path(__file__).resolve()),
                "parent_dir": str(Path(__file__).parent.resolve()),
                "hint": "Check if app/static/index.html exists in the Docker container"
            }
        )
    
    # Helper function to serve trades GUI
    async def _serve_trades_gui():
        """Helper function to serve the Trade & PnL Viewer GUI."""
        trades_path = static_dir / "trades.html"
        abs_trades_path = trades_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations
        possible_paths = [
            abs_trades_path,
            trades_path,
            abs_static_dir / "trades.html",
            static_dir / "trades.html",
        ]
        
        for path in possible_paths:
            if path.exists():
                return FileResponse(
                    path=str(path),
                    media_type="text/html"
                )
        
        # If file not found, return detailed error
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Trade & PnL Viewer GUI not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
            }
        )
    
    # Include API routers FIRST to ensure API endpoints take precedence
    # This ensures /trades/list matches before /trades GUI route
    app.include_router(health_router)
    app.include_router(trades_router)  # Must be before /trades GUI route
    app.include_router(strategies_router)  # Must be before /strategies GUI route
    app.include_router(logs_router)
    app.include_router(strategy_performance_router)
    
    # GUI routes - registered AFTER API routers
    # FastAPI matches more specific routes first, so /trades/list will match before /trades
    @app.get("/trades", tags=["gui"], include_in_schema=False)
    async def trades_gui():
        """Serve the Trade & PnL Viewer GUI (without trailing slash)."""
        return await _serve_trades_gui()
    
    @app.get("/trades/", tags=["gui"], include_in_schema=False)
    async def trades_gui_with_slash():
        """Serve the Trade & PnL Viewer GUI (with trailing slash)."""
        return await _serve_trades_gui()
    
    # Serve strategies.html for Strategy Performance Viewer
    async def _serve_strategies_gui():
        """Helper function to serve the Strategy Performance GUI."""
        strategies_path = static_dir / "strategies.html"
        abs_strategies_path = strategies_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations
        possible_paths = [
            abs_strategies_path,
            strategies_path,
            abs_static_dir / "strategies.html",
            static_dir / "strategies.html",
        ]
        
        for path in possible_paths:
            if path.exists():
                return FileResponse(
                    path=str(path),
                    media_type="text/html"
                )
        
        # If file not found, return detailed error
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Strategy Performance GUI not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
            }
        )
    
    # GUI routes for strategies - registered AFTER API routers
    @app.get("/strategies", tags=["gui"], include_in_schema=False)
    async def strategies_gui():
        """Serve the Strategy Performance & Ranking GUI (without trailing slash)."""
        return await _serve_strategies_gui()
    
    @app.get("/strategies/", tags=["gui"], include_in_schema=False)
    async def strategies_gui_with_slash():
        """Serve the Strategy Performance & Ranking GUI (with trailing slash)."""
        return await _serve_strategies_gui()
    
    return app


app = create_app()

