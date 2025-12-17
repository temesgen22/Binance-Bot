"""
FastAPI dependencies for authentication, database access, and application services.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db_session_dependency
from app.core.auth import decode_token, get_user_id_from_token
from app.core.my_binance_client import BinanceClient
from app.core.binance_client_manager import BinanceClientManager
from app.services.database_service import DatabaseService
from app.services.strategy_runner import StrategyRunner
from app.models.db_models import User
from loguru import logger

# HTTP Bearer token security scheme
security = HTTPBearer()


# Note: Use get_db_session_dependency directly as a dependency
# Example: db: Session = Depends(get_db_session_dependency)


def get_database_service(db: Session = Depends(get_db_session_dependency)) -> DatabaseService:
    """Get database service dependency."""
    return DatabaseService(db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db_session_dependency)
) -> User:
    """Get current authenticated user from JWT token.
    
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
    """
    base_runner = request.app.state.strategy_runner
    
    # If user is authenticated, enhance runner with StrategyService
    if current_user:
        from app.services.strategy_service import StrategyService
        from app.core.redis_storage import RedisStorage
        from app.core.config import get_settings
        
        settings = get_settings()
        redis_storage = None
        if settings.redis_enabled:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
        
        strategy_service = StrategyService(db, redis_storage)
        
        # Create TradeService for trade persistence
        from app.services.trade_service import TradeService
        trade_service = TradeService(db, redis_storage)
        
        # Create enhanced runner with StrategyService and TradeService
        # Note: We create a new runner instance with StrategyService, but share the same client_manager
        # This allows per-user strategy management while sharing execution resources
        enhanced_runner = StrategyRunner(
            client_manager=base_runner.client_manager,
            client=base_runner.client,
            max_concurrent=base_runner.max_concurrent,
            redis_storage=base_runner.redis,
            notification_service=base_runner.notifications,
            strategy_service=strategy_service,
            user_id=current_user.id
        )
        # Inject TradeService
        enhanced_runner.trade_service = trade_service
        
        # Share tasks with base runner (tasks run in the same event loop)
        # This ensures tasks started by per-user runners are visible to all runners
        enhanced_runner._tasks = base_runner._tasks
        enhanced_runner._trades = base_runner._trades
        
        # Copy base runner's strategies for backward compatibility, but user's strategies take precedence
        # (user strategies are loaded from database in StrategyRunner.__init__)
        for strategy_id, summary in base_runner._strategies.items():
            if strategy_id not in enhanced_runner._strategies:
                enhanced_runner._strategies[strategy_id] = summary
        
        # Restore running strategies for this user (only if not already restored)
        # Use a flag in app state to track which users have been restored
        app_state = request.app.state
        if not hasattr(app_state, '_strategy_restore_flags'):
            app_state._strategy_restore_flags = set()
        
        restore_key = f"user_{current_user.id}"
        if restore_key not in app_state._strategy_restore_flags:
            # First time this user's strategies are accessed - restore running ones
            import asyncio
            try:
                # Schedule restoration in background (non-blocking)
                asyncio.create_task(enhanced_runner.restore_running_strategies())
                app_state._strategy_restore_flags.add(restore_key)
            except Exception as exc:
                from loguru import logger
                logger.error(f"Failed to schedule strategy restoration for user {current_user.id}: {exc}")
        
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
    """Get AccountService with Redis storage (cached per request).
    
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