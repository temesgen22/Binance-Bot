"""
FastAPI dependencies for authentication, database access, and application services.
Supports both synchronous and asynchronous database operations.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session_dependency, get_async_db
from app.core.auth import decode_token, get_user_id_from_token
from app.core.my_binance_client import BinanceClient
from app.core.binance_client_manager import BinanceClientManager
from app.services.database_service import DatabaseService
from app.services.strategy_runner import StrategyRunner
from app.models.db_models import User
from loguru import logger

# HTTP Bearer token security scheme
security = HTTPBearer()


# Note: Use get_db_session_dependency directly as a dependency for sync operations
# Example: db: Session = Depends(get_db_session_dependency)
# For async operations, use get_async_db
# Example: db: AsyncSession = Depends(get_async_db)


def get_database_service(db: Session = Depends(get_db_session_dependency)) -> DatabaseService:
    """Get database service dependency (sync)."""
    return DatabaseService(db)


async def get_database_service_async(db: AsyncSession = Depends(get_async_db)) -> DatabaseService:
    """Get database service dependency (async).
    
    Use this for async route handlers to get better performance.
    """
    return DatabaseService(db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db_session_dependency)
) -> User:
    """Get current authenticated user from JWT token (sync).
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user_id from token
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    db_service = DatabaseService(db)
    user = db_service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    return user


async def get_current_user_async(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """Get current authenticated user from JWT token (async).
    
    Use this for async route handlers to get better performance.
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user_id from token
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database (async)
    db_service = DatabaseService(db)
    user = await db_service.async_get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    return user


def get_current_user_id(
    current_user: User = Depends(get_current_user)
) -> UUID:
    """Get current user ID from authenticated user."""
    return current_user.id


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db_session_dependency)
) -> Optional[User]:
    """Get current user if authenticated, None otherwise.
    
    This is useful for endpoints that work both with and without authentication.
    """
    if not credentials:
        return None
    
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


# ============================================
# APPLICATION SERVICE DEPENDENCIES
# ============================================

def get_strategy_runner(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db_session_dependency)
) -> StrategyRunner:
    """Get StrategyRunner from app state.
    
    If user is authenticated, returns a StrategyRunner with StrategyService.
    Otherwise, returns the default StrategyRunner (backward compatibility).
    
    Enhanced runners are cached per request to avoid repeated database queries and object creation.
    """
    base_runner = request.app.state.strategy_runner
    
    # If user is authenticated, enhance runner with StrategyService
    if current_user:
        # Cache enhanced runner per request to avoid repeated database queries and object creation
        cache_key = f"enhanced_runner_{current_user.id}"
        if hasattr(request.state, cache_key):
            return getattr(request.state, cache_key)
        
        from app.services.strategy_service import StrategyService
        from app.services.trade_service import TradeService
        
        # Cache StrategyService and TradeService per request to avoid repeated creation
        if not hasattr(request.state, 'strategy_service'):
            # Use shared Redis connection from base_runner to avoid creating multiple connections
            # This ensures all services (StrategyService, TradeService, StrategyRunner) use the same Redis connection
            shared_redis_storage = base_runner.redis
            request.state.strategy_service = StrategyService(db, shared_redis_storage)
            request.state.trade_service = TradeService(db, shared_redis_storage)
        
        strategy_service = request.state.strategy_service
        trade_service = request.state.trade_service
        
        # Check if strategies are already loaded or being loaded for this user (app-level cache)
        # This prevents multiple database loads when parallel requests come in
        app_state = request.app.state
        user_strategies_key = f"user_strategies_{current_user.id}"
        user_strategies_loading_key = f"user_strategies_loading_{current_user.id}"
        user_strategies_loaded = getattr(app_state, user_strategies_key, False)
        user_strategies_loading = getattr(app_state, user_strategies_loading_key, False)
        
        # Skip loading if already loaded or currently loading
        skip_load = user_strategies_loaded or user_strategies_loading
        
        # Get testnet value from base runner's kline_manager (if available) or from client
        testnet_value = True  # Default
        if base_runner.kline_manager:
            testnet_value = base_runner.kline_manager.testnet
        elif base_runner.client:
            testnet_value = getattr(base_runner.client, 'testnet', True)
        elif base_runner.client_manager:
            # Try to get from default account config
            default_client = base_runner.client_manager.get_default_client()
            if default_client:
                testnet_value = getattr(default_client, 'testnet', True)
        
        # Determine if we should enable WebSocket initialization
        # If base_runner has kline_manager, we'll reuse it (avoid wasteful creation)
        # If base_runner doesn't have kline_manager, let enhanced_runner create one
        should_enable_websocket = base_runner.kline_manager is None
        
        # Create enhanced runner
        # If base_runner has kline_manager, disable WebSocket initialization to avoid wasteful creation
        # that would be immediately discarded when we assign base_runner.kline_manager
        # Create enhanced runner with TradeService passed directly to avoid wasteful creation in __init__
        # Set loading flag to prevent other parallel requests from loading
        # Use double-check pattern to reduce race conditions
        if not skip_load:
            # Check again after getting the flag (double-check pattern to reduce race conditions)
            current_loading = getattr(app_state, user_strategies_loading_key, False)
            if not current_loading:
                setattr(app_state, user_strategies_loading_key, True)
            else:
                # Another request is already loading, skip this one
                skip_load = True
        
        try:
            # Create enhanced runner - skip loading if already loaded or currently loading
            enhanced_runner = StrategyRunner(
                client_manager=base_runner.client_manager,
                client=base_runner.client,
                max_concurrent=base_runner.max_concurrent,
                redis_storage=base_runner.redis,
                notification_service=base_runner.notifications,
                strategy_service=strategy_service,
                user_id=current_user.id,
                use_websocket=should_enable_websocket,  # Only enable if base_runner doesn't have kline_manager
                testnet=testnet_value,  # Get testnet from kline_manager or client
                trade_service=trade_service,  # Pass TradeService directly to avoid wasteful creation in __init__
                skip_strategy_load=skip_load,  # Skip if already loaded or currently loading
            )
            
            # Mark strategies as loaded for this user (app-level cache)
            # This prevents other parallel requests from loading again
            # IMPORTANT: Set flag even if we skipped loading, to prevent repeated attempts
            if not user_strategies_loaded:
                # Set flag if strategies were loaded OR if we skipped loading (to prevent retries)
                if enhanced_runner._strategies or skip_load:
                    setattr(app_state, user_strategies_key, True)
        finally:
            # Clear loading flag only if we actually attempted to load
            if not skip_load:
                setattr(app_state, user_strategies_loading_key, False)
        # Share kline_manager (singleton pattern)
        # If base_runner has one, use it. Otherwise, if enhanced_runner created one, share it back to base_runner
        if base_runner.kline_manager:
            enhanced_runner.kline_manager = base_runner.kline_manager
        elif enhanced_runner.kline_manager:
            # Enhanced runner created a kline_manager, share it with base_runner for singleton pattern
            base_runner.kline_manager = enhanced_runner.kline_manager
        
        # Share tasks with base runner (tasks run in the same event loop)
        # This ensures tasks started by per-user runners are visible to all runners
        enhanced_runner._tasks = base_runner._tasks
        enhanced_runner._trades = base_runner._trades
        
        # Note: Strategies are loaded from database in StrategyRunner.__init__ via load_from_database()
        # The load_from_database() method now skips loading if strategies already exist (optimization)
        # Copy base runner's strategies for backward compatibility, but user's strategies take precedence
        for strategy_id, summary in base_runner._strategies.items():
            if strategy_id not in enhanced_runner._strategies:
                enhanced_runner._strategies[strategy_id] = summary
        
        # Mark that strategies need to be restored for this user (lazy restoration)
        # Restoration will happen when strategies are actually accessed (e.g., in list_strategies)
        # This avoids the "no running event loop" error when called from sync dependency
        app_state = request.app.state
        if not hasattr(app_state, '_strategy_restore_flags'):
            app_state._strategy_restore_flags = set()
        
        restore_key = f"user_{current_user.id}"
        if restore_key not in app_state._strategy_restore_flags:
            # Mark that restoration is needed - will be done lazily when strategies are accessed
            app_state._strategy_restore_flags.add(restore_key)
            # Store a flag on the runner itself to trigger restoration on first access
            enhanced_runner._needs_restore = True
        
        # Cache enhanced runner per request to avoid repeated database queries
        setattr(request.state, cache_key, enhanced_runner)
        return enhanced_runner
    
    # No user authenticated: return base runner (backward compatibility)
    return base_runner


def get_binance_client(request: Request) -> BinanceClient:
    """Get default BinanceClient from app state."""
    if not hasattr(request.app.state, 'binance_client'):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BinanceClient not initialized"
        )
    return request.app.state.binance_client


def get_client_manager(request: Request) -> BinanceClientManager:
    """Get BinanceClientManager from app state."""
    if not hasattr(request.app.state, 'binance_client_manager'):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BinanceClientManager not initialized"
        )
    return request.app.state.binance_client_manager


def get_account_service(
    request: Request,
    db: Session = Depends(get_db_session_dependency)
):
    """Get AccountService with Redis storage (cached per request) - sync.
    
    This dependency eliminates duplication of Redis/AccountService initialization
    across multiple endpoints. The service is cached in request.state to avoid
    recreating it multiple times within the same request.
    
    Returns:
        AccountService instance with Redis storage configured
    """
    # Cache in request state to avoid recreating on each dependency call
    if hasattr(request.state, 'account_service'):
        return request.state.account_service
    
    from app.services.account_service import AccountService
    from app.core.redis_storage import RedisStorage
    from app.core.config import get_settings
    
    settings = get_settings()
    redis_storage = None
    if settings.redis_enabled:
        redis_storage = RedisStorage(
            redis_url=settings.redis_url,
            enabled=settings.redis_enabled
        )
    
    account_service = AccountService(db, redis_storage)
    request.state.account_service = account_service
    return account_service


async def get_account_service_async(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Get AccountService with Redis storage (cached per request) - async.
    
    This dependency eliminates duplication of Redis/AccountService initialization
    across multiple endpoints. The service is cached in request.state to avoid
    recreating it multiple times within the same request.
    
    Use this for async route handlers to get better performance.
    
    Returns:
        AccountService instance with Redis storage configured
    """
    # Cache in request state to avoid recreating on each dependency call
    if hasattr(request.state, 'account_service'):
        return request.state.account_service
    
    from app.services.account_service import AccountService
    from app.core.redis_storage import RedisStorage
    from app.core.config import get_settings
    
    settings = get_settings()
    redis_storage = None
    if settings.redis_enabled:
        redis_storage = RedisStorage(
            redis_url=settings.redis_url,
            enabled=settings.redis_enabled
        )
    
    account_service = AccountService(db, redis_storage)
    request.state.account_service = account_service
    return account_service