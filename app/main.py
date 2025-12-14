from __future__ import annotations

import asyncio
import os

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from fastapi.exceptions import RequestValidationError

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.strategies import router as strategies_router
from app.api.routes.logs import router as logs_router
from app.api.routes.trades import router as trades_router
from app.api.routes.strategy_performance import router as strategy_performance_router
from app.api.routes.reports import router as reports_router
from app.api.routes.accounts import router as accounts_router
from app.api.routes.test_accounts import router as test_accounts_router
from app.api.routes.market_analyzer import router as market_analyzer_router
from app.api.routes.backtesting import router as backtesting_router
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
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import get_settings
from app.core.logger import configure_logging
from loguru import logger
from app.core.redis_storage import RedisStorage
from app.core.database import init_database, close_database
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
from app.services.notifier import TelegramNotifier, NotificationService
from app.services.telegram_commands import TelegramCommandHandler


def create_app() -> FastAPI:
    configure_logging()
    
    # Load .env file for other settings (database, redis, etc.)
    # Note: API accounts are now stored in database only, not in .env file
    from dotenv import load_dotenv
    from pathlib import Path
    
    # Try multiple possible locations for .env file
    project_root = Path(__file__).parent.parent
    env_file = None
    possible_paths = [
        project_root / ".env",  # Project root (most reliable)
        Path(".env"),  # Current directory
        Path.cwd() / ".env",  # Current working directory
    ]
    
    for env_path in possible_paths:
        if env_path.exists() and env_path.is_file():
            env_file = env_path
            logger.debug(f"Loading .env file from: {env_file.absolute()}")
            load_dotenv(env_file, override=False)  # Don't override existing env vars
            break
    
    # Clear settings cache to ensure fresh load
    get_settings.cache_clear()
    settings = get_settings()
    
    # Initialize Binance client manager (accounts are loaded from database when needed)
    client_manager = BinanceClientManager(settings)
    logger.info("Initialized BinanceClientManager - accounts will be loaded from database when needed")
    
    # Get default client for backward compatibility
    default_client = client_manager.get_default_client()
    if not default_client:
        # Fallback: create default client if no accounts configured
        default_client = BinanceClient(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
            testnet=settings.binance_testnet,
        )
        # Add to manager
        client_manager._clients["default"] = default_client
    
    # Create default risk manager and executor for backward compatibility
    risk = RiskManager(client=default_client)
    executor = OrderExecutor(client=default_client)
    
    # Initialize Redis storage if enabled
    redis_storage = None
    if settings.redis_enabled:
        redis_storage = RedisStorage(
            redis_url=settings.redis_url,
            enabled=settings.redis_enabled
        )
    
    # Initialize Telegram notification service if enabled
    notification_service = None
    if settings.telegram_enabled:
        telegram_notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            enabled=settings.telegram_enabled,
        )
        notification_service = NotificationService(
            telegram_notifier=telegram_notifier,
            profit_threshold_usd=settings.telegram_profit_threshold_usd,
            loss_threshold_usd=settings.telegram_loss_threshold_usd,
        )
    
    runner = StrategyRunner(
        client_manager=client_manager,
        client=default_client,  # For backward compatibility
        risk=risk,
        executor=executor,
        max_concurrent=settings.max_concurrent_strategies,
        redis_storage=redis_storage,
        notification_service=notification_service,
    )
    
    # Initialize Telegram command handler if enabled
    telegram_command_handler = None
    if settings.telegram_enabled and settings.telegram_bot_token:
        telegram_command_handler = TelegramCommandHandler(
            bot_token=settings.telegram_bot_token,
            strategy_runner=runner,
            enabled=settings.telegram_enabled,
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
        # Initialize database connection pool
        init_database()
        
        app.state.binance_client = default_client  # For backward compatibility
        app.state.binance_client_manager = client_manager
        app.state.strategy_runner = runner
        app.state.background_tasks: list[asyncio.Task] = []
        
        # Start Telegram command handler if enabled
        if telegram_command_handler:
            telegram_command_handler.start()
            logger.info("Telegram command handler started")

    @app.on_event("shutdown")
    async def shutdown() -> None:  # pragma: no cover
        # Stop Telegram command handler
        if telegram_command_handler:
            telegram_command_handler.stop()
        
        # Close database connections
        close_database()
        
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
    # Serve login.html and register.html (user registration) - public routes
    @app.get("/login.html", tags=["gui"], include_in_schema=False)
    async def login_gui():
        """Serve the Login page."""
        login_path = static_dir / "login.html"
        if login_path.exists():
            return FileResponse(path=str(login_path), media_type="text/html")
        raise HTTPException(status_code=404, detail="Login page not found")
    
    @app.get("/register.html", tags=["gui"], include_in_schema=False)
    async def register_html_gui():
        """Serve the User Registration page."""
        register_path = static_dir / "register.html"
        if register_path.exists():
            return FileResponse(path=str(register_path), media_type="text/html")
        raise HTTPException(status_code=404, detail="Registration page not found")
    
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
    app.include_router(auth_router)  # Authentication endpoints
    app.include_router(health_router)
    app.include_router(accounts_router)
    app.include_router(test_accounts_router)  # Test accounts API
    app.include_router(trades_router)  # Must be before /trades GUI route
    app.include_router(strategies_router)  # Must be before /strategies GUI route
    app.include_router(logs_router)
    app.include_router(strategy_performance_router)
    app.include_router(reports_router)  # Must be before /reports GUI route
    app.include_router(market_analyzer_router)  # Market analyzer API
    app.include_router(backtesting_router)  # Backtesting API
    
    # Serve backtesting.html for Strategy Backtesting
    async def _serve_backtesting_gui():
        """Helper function to serve the Strategy Backtesting GUI."""
        backtesting_path = static_dir / "backtesting.html"
        abs_backtesting_path = backtesting_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations
        possible_paths = [
            abs_backtesting_path,
            backtesting_path,
            abs_static_dir / "backtesting.html",
            static_dir / "backtesting.html",
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
                "message": "Strategy Backtesting GUI not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
            }
        )
    
    # GUI route for backtesting
    @app.get("/backtesting", tags=["gui"], include_in_schema=False)
    async def backtesting_gui():
        """Serve the Strategy Backtesting GUI (without trailing slash)."""
        return await _serve_backtesting_gui()
    
    @app.get("/backtesting/", tags=["gui"], include_in_schema=False)
    async def backtesting_gui_with_slash():
        """Serve the Strategy Backtesting GUI (with trailing slash)."""
        return await _serve_backtesting_gui()
    
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
    
    # Serve test-accounts.html for API Account Testing
    async def _serve_test_accounts_gui():
        """Helper function to serve the Test API Accounts GUI."""
        test_accounts_path = static_dir / "test-accounts.html"
        abs_test_accounts_path = test_accounts_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations
        possible_paths = [
            abs_test_accounts_path,
            test_accounts_path,
            abs_static_dir / "test-accounts.html",
            static_dir / "test-accounts.html",
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
                "message": "Test API Accounts GUI not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
            }
        )
    
    # GUI routes for test accounts
    @app.get("/test-accounts", tags=["gui"], include_in_schema=False)
    async def test_accounts_gui():
        """Serve the Test API Accounts GUI (without trailing slash)."""
        return await _serve_test_accounts_gui()
    
    @app.get("/test-accounts/", tags=["gui"], include_in_schema=False)
    async def test_accounts_gui_with_slash():
        """Serve the Test API Accounts GUI (with trailing slash)."""
        return await _serve_test_accounts_gui()
    
    # Serve reports.html for Trading Reports
    async def _serve_reports_gui():
        """Helper function to serve the Trading Reports GUI."""
        reports_path = static_dir / "reports.html"
        abs_reports_path = reports_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations
        possible_paths = [
            abs_reports_path,
            reports_path,
            abs_static_dir / "reports.html",
            static_dir / "reports.html",
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
                "message": "Trading Reports GUI not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
            }
        )
    
    # GUI routes for reports - registered AFTER API routers
    @app.get("/reports", tags=["gui"], include_in_schema=False)
    async def reports_gui():
        """Serve the Trading Reports GUI (without trailing slash)."""
        return await _serve_reports_gui()
    
    @app.get("/reports/", tags=["gui"], include_in_schema=False)
    async def reports_gui_with_slash():
        """Serve the Trading Reports GUI (with trailing slash)."""
        return await _serve_reports_gui()
    
    # Serve strategy-register.html for Strategy Registration
    async def _serve_strategy_register_gui():
        """Helper function to serve the Strategy Registration GUI."""
        register_path = static_dir / "strategy-register.html"
        abs_register_path = register_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations
        possible_paths = [
            abs_register_path,
            register_path,
            abs_static_dir / "strategy-register.html",
            static_dir / "strategy-register.html",
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
                "message": "Strategy Registration GUI not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
            }
        )
    
    # GUI routes for strategy registration - registered AFTER API routers
    @app.get("/strategy-register", tags=["gui"], include_in_schema=False)
    async def strategy_register_gui():
        """Serve the Strategy Registration GUI (without trailing slash)."""
        return await _serve_strategy_register_gui()
    
    @app.get("/strategy-register/", tags=["gui"], include_in_schema=False)
    async def strategy_register_gui_with_slash():
        """Serve the Strategy Registration GUI (with trailing slash)."""
        return await _serve_strategy_register_gui()
    
    # Keep /register route for backward compatibility (redirects to strategy-register)
    @app.get("/register", tags=["gui"], include_in_schema=False)
    async def register_gui_redirect():
        """Redirect /register to /strategy-register for backward compatibility."""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/strategy-register", status_code=301)
    
    # Serve market-analyzer.html for Market Analyzer
    async def _serve_market_analyzer_gui():
        """Helper function to serve the Market Analyzer GUI."""
        market_analyzer_path = static_dir / "market-analyzer.html"
        abs_market_analyzer_path = market_analyzer_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations
        possible_paths = [
            abs_market_analyzer_path,
            market_analyzer_path,
            abs_static_dir / "market-analyzer.html",
            static_dir / "market-analyzer.html",
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
                "message": "Market Analyzer GUI not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
            }
        )
    
    # GUI routes for market analyzer - registered AFTER API routers
    @app.get("/market-analyzer", tags=["gui"], include_in_schema=False)
    async def market_analyzer_gui():
        """Serve the Market Analyzer GUI (without trailing slash)."""
        return await _serve_market_analyzer_gui()
    
    @app.get("/market-analyzer/", tags=["gui"], include_in_schema=False)
    async def market_analyzer_gui_with_slash():
        """Serve the Market Analyzer GUI (with trailing slash)."""
        return await _serve_market_analyzer_gui()
    
    # Diagnostic endpoint to check if register.html exists (for debugging)
    @app.get("/debug/check-register-file", tags=["debug"], include_in_schema=False)
    async def check_register_file():
        """Debug endpoint to check if register.html exists in the container."""
        register_path = static_dir / "register.html"
        abs_register_path = register_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        return {
            "register_path": str(register_path),
            "abs_register_path": str(abs_register_path),
            "register_exists": register_path.exists(),
            "abs_register_exists": abs_register_path.exists(),
            "static_dir": str(abs_static_dir),
            "static_dir_exists": abs_static_dir.exists(),
            "static_dir_contents": list(abs_static_dir.iterdir()) if abs_static_dir.exists() else [],
        }
    
    return app


app = create_app()

