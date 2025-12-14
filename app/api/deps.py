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
        
        # Copy in-memory strategies from base runner (for backward compatibility)
        enhanced_runner._strategies = base_runner._strategies.copy()
        enhanced_runner._tasks = base_runner._tasks.copy()
        enhanced_runner._trades = base_runner._trades.copy()
        
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
