from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.gzip import GZipMiddleware

from fastapi.exceptions import RequestValidationError
from time import time

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.strategies import router as strategies_router
from app.api.routes.logs import router as logs_router
from app.api.routes.trades import router as trades_router
from app.api.routes.strategy_performance import router as strategy_performance_router
from app.api.routes.reports import router as reports_router
from app.api.routes.accounts import router as accounts_router
from app.api.routes.test_accounts import router as test_accounts_router
from app.api.routes.market_analyzer import router as market_analyzer_router
from app.api.routes.backtesting import router as backtesting_router
from app.api.routes.auto_tuning import router as auto_tuning_router
from app.api.routes.risk_metrics import router as risk_metrics_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.notifications import router as notifications_router
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
    risk_limit_exceeded_handler,
    circuit_breaker_active_handler,
    drawdown_limit_exceeded_handler,
    symbol_conflict_handler,
    binance_bot_exception_handler,
    validation_error_handler,
    general_exception_handler,
)
from app.core.my_binance_client import BinanceClient
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import get_settings
from app.core.logger import configure_logging
from app.core.correlation_id import CorrelationIDMiddleware
from loguru import logger
from app.core.redis_storage import RedisStorage
from app.core.database import init_database, close_database, init_database_async, close_async_database
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
    RiskLimitExceededError,
    CircuitBreakerActiveError,
    DrawdownLimitExceededError,
    SymbolConflictError,
    BinanceBotException,
)
from app.risk.manager import RiskManager
from app.services.order_executor import OrderExecutor
from app.services.strategy_runner import StrategyRunner
from app.services.notifier import TelegramNotifier, NotificationService
from app.services.telegram_commands import TelegramCommandHandler
from app.services.service_monitor import ServiceMonitor


def create_app() -> FastAPI:
    configure_logging()
    
    # Load .env file for other settings (database, redis, etc.)
    # Note: API accounts are now stored in database only, not in .env file
    from dotenv import load_dotenv
    
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
        # Validate API keys before creating default client
        if settings.binance_api_key in ("demo", "Demo", "DEMO", "") or settings.binance_api_secret in ("demo", "Demo", "DEMO", ""):
            logger.warning(
                "⚠️ Default API keys are set to 'demo' placeholder values. "
                "This will cause 'API-key format invalid' errors when making authenticated requests. "
                "Please configure a valid account in the database or set BINANCE_API_KEY and BINANCE_API_SECRET in .env file."
            )
        # Fallback: create default client if no accounts configured
        # Wrap in try-except to handle temporary Binance API unavailability
        try:
            default_client = BinanceClient(
                api_key=settings.binance_api_key,
                api_secret=settings.binance_api_secret,
                testnet=settings.binance_testnet,
            )
            # Add to manager directly (bypasses add_client validation for backward compatibility with demo keys)
            # Note: This is intentional - we allow demo/placeholder keys for backward compatibility
            client_manager._clients["default"] = default_client
        except Exception as e:
            logger.error(
                f"⚠️ Failed to initialize default Binance client during startup: {e}\n"
                f"   This may be due to temporary Binance API unavailability (502 Bad Gateway).\n"
                f"   The application will continue to start, but Binance operations may fail until the API is available.\n"
                f"   Clients will be created on-demand when accounts are accessed."
            )
            # Set to None - clients will be created on-demand when needed
            default_client = None
    
    # Create default risk manager and executor for backward compatibility
    # Note: OrderExecutor doesn't have trade_service/user_id in main.py (single-user mode)
    # This is fine - idempotency will work with in-memory cache only
    # If default_client is None (e.g., Binance API unavailable), create with None
    # They will be recreated when clients become available
    risk = RiskManager(client=default_client) if default_client else None
    executor = OrderExecutor(client=default_client, trade_service=None, user_id=None) if default_client else None
    
    if not default_client:
        logger.warning(
            "⚠️ Default Binance client not available. Risk manager and order executor not initialized.\n"
            "   They will be created on-demand when accounts are accessed."
        )
    
    # Initialize Redis storage if enabled
    redis_storage = None
    if settings.redis_enabled:
        redis_storage = RedisStorage(
            redis_url=settings.redis_url,
            enabled=settings.redis_enabled
        )
    
    # Initialize Telegram notification service if enabled
    telegram_notifier = None
    if settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id:
        telegram_notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            enabled=settings.telegram_enabled,
        )
    elif settings.telegram_enabled and (not settings.telegram_bot_token or not settings.telegram_chat_id):
        logger.warning(
            "Telegram notifications are enabled but bot_token or chat_id is missing. "
            "Telegram notifications will be disabled."
        )
    
    # Initialize FCM notifier if enabled
    fcm_notifier = None
    if settings.firebase_enabled:
        try:
            from app.services.fcm_notifier import FCMNotifier
            fcm_notifier = FCMNotifier(enabled=True)
            if fcm_notifier.enabled:
                logger.info("FCM push notifications enabled")
            else:
                logger.warning("FCM notifier disabled (initialization failed)")
                fcm_notifier = None
        except Exception as e:
            logger.warning(f"Failed to initialize FCM notifier: {e}")
            fcm_notifier = None
    
    # Create NotificationService with available notifiers
    notification_service = None
    if telegram_notifier or fcm_notifier:
        notification_service = NotificationService(
            telegram_notifier=telegram_notifier,
            fcm_notifier=fcm_notifier,
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
        use_websocket=settings.use_websocket_klines,  # Enable WebSocket from config
        testnet=settings.binance_testnet,  # Get testnet from config
    )
    
    # Initialize Telegram command handler if enabled
    telegram_command_handler = None
    if settings.telegram_enabled and settings.telegram_bot_token:
        telegram_command_handler = TelegramCommandHandler(
            bot_token=settings.telegram_bot_token,
            strategy_runner=runner,
            enabled=settings.telegram_enabled,
        )
    
    # Initialize service monitor for database, FastAPI, and Docker services
    service_monitor = None
    if notification_service:
        service_monitor = ServiceMonitor(
            notification_service=notification_service,
            check_interval=60,  # Check every 60 seconds
        )
        
        # Set up database connection failure notification callback
        async def db_failure_callback(error, retry_count, max_retries):
            """Callback for database connection failures."""
            await service_monitor.notify_database_connection_failed(
                error, retry_count, max_retries
            )
        
        from app.core.database import set_notification_callback
        set_notification_callback(db_failure_callback)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager for startup and shutdown.
        
        Note: When the server is stopped (Ctrl+C), a CancelledError may be raised
        by Starlette/Uvicorn's lifespan handler. This is expected behavior and harmless.
        The cleanup code in the finally block will still execute.
        """
        try:
            logger.info("🚀 Starting FastAPI application lifespan...")
        except Exception as log_exc:
            # Even if logging fails, try to print to stderr as last resort
            print("ERROR: Failed to log lifespan start", file=sys.stderr)
            print(f"Exception: {log_exc}", file=sys.stderr)
        
        # Startup
        startup_errors = []
        restored_strategies_count = 0
        db_connection_error = None
        
        try:
            logger.info("📊 Initializing database connection pools...")
            # Initialize both sync and async database connection pools
            try:
                # Initialize sync database (for backward compatibility)
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                
                # Sync database initialization (run in executor to not block)
                db_init_success, db_connection_error = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: init_database(max_retries=10)),
                    timeout=120.0
                )
                logger.info(f"✅ Sync database initialization completed: success={db_init_success}")
                
                # Initialize async database (native async)
                if db_init_success:
                    async_db_init_success, async_db_error = await asyncio.wait_for(
                        init_database_async(max_retries=10),
                        timeout=120.0
                )
                    logger.info(f"✅ Async database initialization completed: success={async_db_init_success}")
                    if not async_db_init_success:
                        logger.warning(
                            f"Async database initialization failed, but sync database is available. "
                            f"Some features may be slower. Error: {async_db_error}"
                        )
                else:
                    logger.warning("Skipping async database initialization due to sync database failure")
            except asyncio.TimeoutError:
                logger.error("❌ Database initialization timed out after 120 seconds")
                db_init_success = False
                db_connection_error = TimeoutError("Database initialization timed out after 120 seconds")
            except Exception as db_exc:
                logger.error(f"❌ Database initialization failed with exception: {db_exc}", exc_info=True)
                db_init_success = False
                db_connection_error = db_exc
            if not db_init_success:
                startup_errors.append("Database connection failed - server operating in degraded mode")
                # Send database connection failure notification
                if notification_service and db_connection_error:
                    try:
                        await notification_service.notify_database_connection_failed(
                            db_connection_error,
                            retry_count=10,  # We tried 10 times
                            max_retries=10
                        )
                    except Exception as notify_exc:
                        logger.warning(f"Failed to send database failure notification: {notify_exc}")
            else:
                # Database connected successfully - if we had a previous error, notify restoration
                if db_connection_error and notification_service:
                    try:
                        await notification_service.notify_database_connection_restored()
                    except Exception as notify_exc:
                        logger.warning(f"Failed to send database restored notification: {notify_exc}")
                
                # Check if tables exist, if not, try to create them
                logger.info("🔍 Verifying database tables...")
                try:
                    from sqlalchemy import inspect
                    from app.core.database import get_engine, create_tables
                    engine = get_engine()
                    inspector = inspect(engine)
                    existing_tables = inspector.get_table_names()
                    logger.info(f"✅ Database tables check completed. Found {len(existing_tables)} tables")
                    
                    # Check if accounts table exists (key table)
                    if 'accounts' not in existing_tables:
                        logger.warning("Database tables not found. Attempting to create tables...")
                        try:
                            # Create tables using SQLAlchemy (works as fallback if migrations haven't been run)
                            create_tables()
                            logger.info("✅ Database tables created successfully")
                        except Exception as table_exc:
                            logger.error(f"Failed to create database tables: {table_exc!s}")
                            startup_errors.append(
                                "Database tables not found and could not be created automatically. "
                                "Please run migrations manually: docker exec binance-bot-api alembic upgrade head"
                            )
                except Exception as check_exc:
                    logger.warning(f"Could not verify database tables: {check_exc!s}")
            
            logger.info("📦 Setting up application state...")
            app.state.binance_client = default_client  # For backward compatibility
            app.state.binance_client_manager = client_manager
            app.state.strategy_runner = runner
            app.state.background_tasks: list[asyncio.Task] = []
            logger.info("✅ Application state configured")
            
            # Start periodic dead task cleanup (must be in lifespan where event loop exists)
            cleanup_interval = settings.dead_task_cleanup_interval_seconds
            runner.start_periodic_cleanup(cleanup_interval)
            logger.info(f"✅ Started periodic dead task cleanup (interval: {cleanup_interval}s)")
            
            # Restore running strategies after server restart
            # This ensures strategies that were running before restart are automatically started
            logger.info("🔄 Restoring running strategies...")
            try:
                restored_strategy_ids = await runner.restore_running_strategies()
                if restored_strategy_ids:
                    restored_strategies_count = len(restored_strategy_ids)
                    logger.info(
                        f"✅ Restored {restored_strategies_count} running strategies after restart: "
                        f"{', '.join(restored_strategy_ids[:5])}"
                        f"{'...' if len(restored_strategy_ids) > 5 else ''}"
                    )
                else:
                    logger.info("No strategies needed restoration (all were stopped or already running)")
            except Exception as exc:
                error_msg = f"Failed to restore running strategies: {str(exc)[:200]}"
                startup_errors.append(error_msg)
                logger.error(f"Failed to restore running strategies on startup: {exc}", exc_info=True)
            
            # Start Telegram command handler if enabled
            if telegram_command_handler:
                try:
                    telegram_command_handler.start()
                    logger.info("Telegram command handler started")
                except Exception as exc:
                    error_msg = f"Failed to start Telegram command handler: {str(exc)[:200]}"
                    startup_errors.append(error_msg)
                    logger.error(f"Failed to start Telegram command handler: {exc}", exc_info=True)
            
            # Start Auto-Tuning Evaluator (background job to update performance_after)
            if db_init_success:
                try:
                    # Note: Auto-tuning evaluator will be created per-request in API routes
                    # Full service requires user context, so we don't create it here
                    logger.info("✅ Auto-tuning evaluator ready (will start on first evaluation request)")
                except Exception as exc:
                    logger.warning(f"Auto-tuning evaluator setup skipped: {exc}")
            
            # Send server restart notification
            if notification_service:
                try:
                    await notification_service.notify_server_restart(
                        restored_strategies_count=restored_strategies_count,
                        startup_errors=startup_errors if startup_errors else None,
                    )
                except Exception as exc:
                    logger.warning(f"Failed to send server restart notification: {exc}")
            
            # Start service monitor
            if service_monitor:
                try:
                    logger.info("🔍 Starting service monitor...")
                    service_monitor.start()
                    logger.info("✅ Service monitor started")
                except Exception as exc:
                    logger.warning(f"Failed to start service monitor: {exc}")
            
            logger.info("✅ FastAPI application startup completed successfully")
            logger.info("🌐 Server is ready to accept requests on port 8000")
        except Exception as startup_exc:
            # Log the error but don't prevent server from starting
            logger.error(f"❌ Error during startup, but continuing: {startup_exc}", exc_info=True)
            startup_errors.append(f"Startup error: {str(startup_exc)[:200]}")
            logger.warning("⚠️ Server starting in degraded mode due to startup errors")
        
        # Always yield to allow server to start, even if there were errors
        try:
            yield
        except asyncio.CancelledError:
            # Lifespan was cancelled (normal during shutdown)
            logger.debug("Lifespan cancelled during shutdown")
            # Fall through to shutdown cleanup
        
        # Shutdown
        try:
            logger.info("🛑 FastAPI application shutdown initiated...")
        except (Exception, asyncio.CancelledError):
            # Ignore logging errors during shutdown
            pass
        finally:
            # Shutdown - handle gracefully even if cancelled
            # Note: CancelledError may be raised during shutdown, which is expected behavior
            try:
                # Stop periodic cleanup first (before stopping strategies)
                try:
                    if hasattr(app.state, 'strategy_runner') and app.state.strategy_runner:
                        runner_instance = app.state.strategy_runner
                        if hasattr(runner_instance, 'stop_periodic_cleanup'):
                            await runner_instance.stop_periodic_cleanup()
                except (asyncio.CancelledError, Exception) as e:
                    logger.debug(f"Error stopping periodic cleanup: {type(e).__name__}")
                
                # Stop all running strategies
                try:
                    if hasattr(app.state, 'strategy_runner') and app.state.strategy_runner:
                        runner_instance = app.state.strategy_runner
                        # Cancel all strategy tasks
                        if hasattr(runner_instance, '_tasks'):
                            tasks_to_cancel = list(runner_instance._tasks.values())
                            for task in tasks_to_cancel:
                                if not task.done():
                                    task.cancel()
                            # Wait for tasks to finish cancelling (with timeout)
                            if tasks_to_cancel:
                                try:
                                    await asyncio.wait_for(
                                        asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                                        timeout=5.0
                                    )
                                except (asyncio.TimeoutError, asyncio.CancelledError):
                                    logger.debug("Strategy tasks cancellation completed (timeout or cancelled)")
                                except Exception as e:
                                    logger.warning(f"Error waiting for strategy tasks to cancel: {e}")
                except (asyncio.CancelledError, Exception) as e:
                    logger.debug(f"Error cancelling strategy tasks: {type(e).__name__}")
                
                # Stop Telegram command handler
                try:
                    if telegram_command_handler:
                        telegram_command_handler.stop()
                except (asyncio.CancelledError, Exception) as e:
                    logger.debug(f"Error stopping Telegram handler: {type(e).__name__}")
                
                # Cancel background tasks
                try:
                    if hasattr(app.state, 'background_tasks'):
                        for task in app.state.background_tasks:
                            if not task.done():
                                task.cancel()
                        # Wait for background tasks to finish (with timeout)
                        if app.state.background_tasks:
                            try:
                                await asyncio.wait_for(
                                    asyncio.gather(*app.state.background_tasks, return_exceptions=True),
                                    timeout=2.0
                                )
                            except (asyncio.TimeoutError, asyncio.CancelledError):
                                pass  # Ignore timeout/cancellation during shutdown
                            except Exception as e:
                                logger.warning(f"Error waiting for background tasks to cancel: {e}")
                except (asyncio.CancelledError, Exception) as e:
                    logger.debug(f"Error cancelling background tasks: {type(e).__name__}")
                
                # Stop service monitor
                try:
                    if service_monitor:
                        service_monitor.stop()
                except (asyncio.CancelledError, Exception) as e:
                    logger.debug(f"Error stopping service monitor: {type(e).__name__}")
                
                # Close database connections (critical - must complete)
                try:
                    close_database()  # Close sync database
                except (asyncio.CancelledError, Exception) as e:
                    logger.warning(f"Error closing sync database: {type(e).__name__}")
                
                try:
                    await close_async_database()  # Close async database
                except (asyncio.CancelledError, Exception) as e:
                    logger.warning(f"Error closing async database: {type(e).__name__}")
            except asyncio.CancelledError:
                # Final catch-all for any remaining CancelledError
                # This is expected during shutdown and can be safely ignored
                pass
            except Exception as e:
                # Log any unexpected errors but don't re-raise
                logger.error(f"Unexpected error during shutdown: {e}", exc_info=True)

    logger.info("🔨 Creating FastAPI application instance...")
    try:
        app = FastAPI(title="Binance Trading Bot", version="0.1.0", lifespan=lifespan)
        
        # Add correlation ID middleware (should be first middleware)
        app.add_middleware(CorrelationIDMiddleware)
        
        # Add compression middleware for faster response times
        app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses >1KB
        
        # Add process time header middleware for performance monitoring
        @app.middleware("http")
        async def add_process_time_header(request: Request, call_next):
            """Add X-Process-Time header to responses for performance monitoring."""
            start_time = time()
            response = await call_next(request)
            process_time = time() - start_time
            response.headers["X-Process-Time"] = f"{process_time:.4f}"
            return response
        
        logger.info("✅ FastAPI application instance created successfully")
    except Exception as app_exc:
        logger.error(f"❌ Failed to create FastAPI application: {app_exc}", exc_info=True)
        raise

    # Register exception handlers (order matters - most specific first)
    app.add_exception_handler(BinanceRateLimitError, binance_rate_limit_handler)
    app.add_exception_handler(BinanceAuthenticationError, binance_api_error_handler)
    app.add_exception_handler(BinanceNetworkError, binance_api_error_handler)
    app.add_exception_handler(BinanceAPIError, binance_api_error_handler)
    app.add_exception_handler(StrategyNotFoundError, strategy_not_found_handler)
    app.add_exception_handler(StrategyAlreadyRunningError, strategy_already_running_handler)
    app.add_exception_handler(StrategyNotRunningError, strategy_not_running_handler)
    app.add_exception_handler(MaxConcurrentStrategiesError, max_concurrent_strategies_handler)
    app.add_exception_handler(SymbolConflictError, symbol_conflict_handler)
    app.add_exception_handler(InvalidLeverageError, invalid_leverage_handler)
    app.add_exception_handler(PositionSizingError, position_sizing_handler)
    app.add_exception_handler(OrderExecutionError, order_execution_handler)
    app.add_exception_handler(RiskLimitExceededError, risk_limit_exceeded_handler)
    app.add_exception_handler(CircuitBreakerActiveError, circuit_breaker_active_handler)
    app.add_exception_handler(DrawdownLimitExceededError, drawdown_limit_exceeded_handler)
    app.add_exception_handler(BinanceBotException, binance_bot_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, general_exception_handler)

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
    
    # Generic helper function to serve GUI HTML files
    async def _serve_gui_file(filename: str, display_name: str = None) -> FileResponse:
        """Generic function to serve GUI HTML files.
        
        Args:
            filename: Name of the HTML file to serve (e.g., "trades.html")
            display_name: Optional display name for error messages (defaults to filename)
        
        Returns:
            FileResponse with the HTML file
        
        Raises:
            HTTPException: If file is not found
        """
        if display_name is None:
            display_name = filename
        
        file_path = static_dir / filename
        abs_file_path = file_path.resolve()
        abs_static_dir = static_dir.resolve()
        
        # Try multiple path variations in case of path resolution issues
        possible_paths = [
            abs_file_path,
            file_path,
            abs_static_dir / filename,
            static_dir / filename,
        ]
        
        for path in possible_paths:
            if path.exists():
                return FileResponse(
                    path=str(path),
                    media_type="text/html"
                )
        
        # If file not found, return detailed error
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"{display_name} not found.",
                "tried_paths": [str(p) for p in possible_paths],
                "static_dir": str(abs_static_dir),
                "static_dir_exists": abs_static_dir.exists(),
            }
        )
    
    # Include API routers FIRST to ensure API endpoints take precedence
    # This ensures /trades/list matches before /trades GUI route
    app.include_router(auth_router)  # Authentication endpoints
    app.include_router(health_router)
    app.include_router(metrics_router)  # Prometheus metrics endpoint
    app.include_router(accounts_router)
    app.include_router(test_accounts_router)  # Test accounts API
    app.include_router(trades_router)  # Must be before /trades GUI route
    app.include_router(strategy_performance_router)  # Must be before strategies_router to avoid route conflict
    app.include_router(strategies_router)  # Must be before /strategies GUI route
    app.include_router(logs_router)
    app.include_router(reports_router)  # Must be before /reports GUI route
    app.include_router(market_analyzer_router)  # Market analyzer API
    app.include_router(backtesting_router)  # Backtesting API
    app.include_router(auto_tuning_router)  # Auto-tuning API
    app.include_router(risk_metrics_router)  # Risk metrics and monitoring API
    app.include_router(dashboard_router)  # Dashboard overview API
    app.include_router(notifications_router)  # FCM token management for push notifications
    
    # GUI route for backtesting
    @app.get("/backtesting", tags=["gui"], include_in_schema=False)
    async def backtesting_gui():
        """Serve the Strategy Backtesting GUI (without trailing slash)."""
        return await _serve_gui_file("backtesting.html", "Strategy Backtesting GUI")
    
    @app.get("/backtesting/", tags=["gui"], include_in_schema=False)
    async def backtesting_gui_with_slash():
        """Serve the Strategy Backtesting GUI (with trailing slash)."""
        return await _serve_gui_file("backtesting.html", "Strategy Backtesting GUI")
    
    # GUI routes - registered AFTER API routers
    # FastAPI matches more specific routes first, so /trades/list will match before /trades
    @app.get("/trades", tags=["gui"], include_in_schema=False)
    async def trades_gui():
        """Serve the Trade & PnL Viewer GUI (without trailing slash)."""
        return await _serve_gui_file("trades.html", "Trade & PnL Viewer GUI")
    
    @app.get("/trades/", tags=["gui"], include_in_schema=False)
    async def trades_gui_with_slash():
        """Serve the Trade & PnL Viewer GUI (with trailing slash)."""
        return await _serve_gui_file("trades.html", "Trade & PnL Viewer GUI")
    
    # GUI routes for strategies - registered AFTER API routers
    @app.get("/strategies", tags=["gui"], include_in_schema=False)
    async def strategies_gui():
        """Serve the Strategy Performance & Ranking GUI (without trailing slash)."""
        return await _serve_gui_file("strategies.html", "Strategy Performance GUI")
    
    @app.get("/strategies/", tags=["gui"], include_in_schema=False)
    async def strategies_gui_with_slash():
        """Serve the Strategy Performance & Ranking GUI (with trailing slash)."""
        return await _serve_gui_file("strategies.html", "Strategy Performance GUI")
    
    # GUI routes for test accounts
    @app.get("/test-accounts", tags=["gui"], include_in_schema=False)
    async def test_accounts_gui():
        """Serve the Test API Accounts GUI (without trailing slash)."""
        return await _serve_gui_file("test-accounts.html", "Test API Accounts GUI")
    
    @app.get("/test-accounts/", tags=["gui"], include_in_schema=False)
    async def test_accounts_gui_with_slash():
        """Serve the Test API Accounts GUI (with trailing slash)."""
        return await _serve_gui_file("test-accounts.html", "Test API Accounts GUI")
    
    # GUI routes for reports - registered AFTER API routers
    @app.get("/reports", tags=["gui"], include_in_schema=False)
    async def reports_gui():
        """Serve the Trading Reports GUI (without trailing slash)."""
        return await _serve_gui_file("reports.html", "Trading Reports GUI")
    
    @app.get("/reports/", tags=["gui"], include_in_schema=False)
    async def reports_gui_with_slash():
        """Serve the Trading Reports GUI (with trailing slash)."""
        return await _serve_gui_file("reports.html", "Trading Reports GUI")
    
    # GUI routes for strategy registration - registered AFTER API routers
    @app.get("/strategy-register", tags=["gui"], include_in_schema=False)
    async def strategy_register_gui():
        """Serve the Strategy Registration GUI (without trailing slash)."""
        return await _serve_gui_file("strategy-register.html", "Strategy Registration GUI")
    
    @app.get("/strategy-register/", tags=["gui"], include_in_schema=False)
    async def strategy_register_gui_with_slash():
        """Serve the Strategy Registration GUI (with trailing slash)."""
        return await _serve_gui_file("strategy-register.html", "Strategy Registration GUI")
    
    # Keep /register route for backward compatibility (redirects to strategy-register)
    @app.get("/risk-management", tags=["gui"], include_in_schema=False)
    async def risk_management_gui():
        """Serve the Risk Management Dashboard page."""
        return await _serve_gui_file("risk-management.html", "Risk Management Dashboard")
    
    @app.get("/risk-management/", tags=["gui"], include_in_schema=False)
    async def risk_management_gui_slash():
        """Serve the Risk Management Dashboard page."""
        return await _serve_gui_file("risk-management.html", "Risk Management Dashboard")
    
    @app.get("/register", tags=["gui"], include_in_schema=False)
    async def register_gui_redirect():
        """Redirect /register to /strategy-register for backward compatibility."""
        return RedirectResponse(url="/strategy-register", status_code=301)
    
    # GUI routes for market analyzer - registered AFTER API routers
    @app.get("/market-analyzer", tags=["gui"], include_in_schema=False)
    async def market_analyzer_gui():
        """Serve the Market Analyzer GUI (without trailing slash)."""
        return await _serve_gui_file("market-analyzer.html", "Market Analyzer GUI")
    
    @app.get("/market-analyzer/", tags=["gui"], include_in_schema=False)
    async def market_analyzer_gui_with_slash():
        """Serve the Market Analyzer GUI (with trailing slash)."""
        return await _serve_gui_file("market-analyzer.html", "Market Analyzer GUI")
    
    # GUI route for dashboard
    @app.get("/dashboard", tags=["gui"], include_in_schema=False)
    async def dashboard_gui():
        """Serve the Dashboard page."""
        return await _serve_gui_file("dashboard.html", "Trading Dashboard")
    
    @app.get("/dashboard/", tags=["gui"], include_in_schema=False)
    async def dashboard_gui_slash():
        """Serve the Dashboard page (with trailing slash)."""
        return await _serve_gui_file("dashboard.html", "Trading Dashboard")
    
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
    
    logger.info("✅ FastAPI application setup completed, returning app instance")
    return app


app = create_app()

