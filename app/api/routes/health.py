from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import time

from app.api.deps import get_binance_client, get_db_session_dependency
from app.core.my_binance_client import BinanceClient
from sqlalchemy.orm import Session
from sqlalchemy import text
from loguru import logger

from app.core.config import get_settings
from app.core.redis_storage import RedisStorage


router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    db: Session = Depends(get_db_session_dependency),
    client: BinanceClient = Depends(get_binance_client)
) -> dict[str, str | float]:
    """Health check endpoint.
    
    Checks database, Redis (if enabled), and Binance API connections.
    This is used by Docker health checks, so it must verify critical services.
    
    Returns:
        Status and BTC price if all critical services are working
        
    Raises:
        HTTPException: If database, Redis, or Binance API is unreachable
    """
    from fastapi import HTTPException, status
    
    # Check database connection first (critical for API functionality)
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as db_exc:
        logger.error(f"Database health check failed: {db_exc}")
        db.close()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(db_exc)[:200]}"
        ) from db_exc
    finally:
        try:
            db.close()
        except Exception:
            pass
    
    # Check Redis connection (if enabled)
    redis_status = "disabled"
    settings = get_settings()
    if settings.redis_enabled:
        try:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
            if redis_storage.enabled and redis_storage._client:
                redis_storage._client.ping()
                redis_status = "ok"
            else:
                logger.warning("Redis is enabled but connection failed")
                redis_status = "failed"
        except Exception as redis_exc:
            logger.error(f"Redis health check failed: {redis_exc}")
            redis_status = "failed"
            # Don't fail health check if Redis fails, but log it
            # Redis is optional, database is critical
    
    # Check Binance API connection
    try:
        price = client.get_price("BTCUSDT")
        return {
            "status": "ok",
            "database": db_status,
            "redis": redis_status,
            "btc_price": price
        }
    except Exception as exc:
        from app.core.exceptions import BinanceAPIError, BinanceNetworkError
        
        logger.error(f"Binance health check failed: {exc}")
        # Database is OK, but Binance failed - return degraded status
        # Don't fail completely since database is more critical
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Binance API unreachable: {exc}"
            ) from exc
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Binance API error: {exc}"
            ) from exc


@router.get("/health/detailed")
def detailed_health(
    db: Session = Depends(get_db_session_dependency),
    client: BinanceClient = Depends(get_binance_client)
) -> Dict[str, Any]:
    """Comprehensive health check endpoint.
    
    Checks:
    - Database connection
    - Redis connection (if enabled)
    - Binance API connection
    - Application status
    
    Returns:
        Detailed health status of all services
    """
    health_status: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {}
    }
    
    # Check Database (automatic recovery is handled by get_db_session_dependency)
    db_status = {"status": "unknown", "response_time_ms": None, "error": None}
    try:
        start_time = time.time()
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        response_time = (time.time() - start_time) * 1000
        db_status = {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "database_url": get_settings().database_url.split("@")[-1] if "@" in get_settings().database_url else "***"
        }
    except (RuntimeError, Exception) as exc:
        # Database connection error - automatic recovery should have been attempted
        # by get_db_session_dependency, but if it still fails, report as unhealthy
        db_status = {
            "status": "unhealthy",
            "error": str(exc)[:200],  # Truncate long error messages
            "error_type": type(exc).__name__
        }
        health_status["status"] = "degraded"
        logger.warning(f"Database health check failed: {exc}")
    finally:
        try:
            db.close()
        except Exception:
            pass  # Ignore errors during cleanup
    
    health_status["services"]["database"] = db_status
    
    # Check Redis
    redis_status = {"status": "unknown", "enabled": False, "error": None}
    settings = get_settings()
    if settings.redis_enabled:
        try:
            redis_storage = RedisStorage(
                redis_url=settings.redis_url,
                enabled=settings.redis_enabled
            )
            if redis_storage.enabled and redis_storage._client:
                start_time = time.time()
                redis_storage._client.ping()
                response_time = (time.time() - start_time) * 1000
                redis_status = {
                    "status": "healthy",
                    "enabled": True,
                    "response_time_ms": round(response_time, 2),
                    "redis_url": settings.redis_url.split("@")[-1] if "@" in settings.redis_url else settings.redis_url
                }
            else:
                redis_status = {
                    "status": "disabled",
                    "enabled": False,
                    "reason": "Redis package not installed or connection failed"
                }
        except Exception as exc:
            redis_status = {
                "status": "unhealthy",
                "enabled": True,
                "error": str(exc),
                "error_type": type(exc).__name__
            }
            health_status["status"] = "degraded"
    else:
        redis_status = {
            "status": "disabled",
            "enabled": False,
            "reason": "Redis disabled in configuration"
        }
    
    health_status["services"]["redis"] = redis_status
    
    # Check Binance API
    binance_status = {"status": "unknown", "response_time_ms": None, "error": None}
    try:
        start_time = time.time()
        price = client.get_price("BTCUSDT")
        response_time = (time.time() - start_time) * 1000
        binance_status = {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "btc_price": price,
            "testnet": client.testnet
        }
    except Exception as exc:
        binance_status = {
            "status": "unhealthy",
            "error": str(exc),
            "error_type": type(exc).__name__
        }
        health_status["status"] = "degraded"
    
    health_status["services"]["binance"] = binance_status
    
    # Overall status
    if health_status["status"] == "healthy":
        health_status["message"] = "All services are operational"
    else:
        health_status["message"] = "Some services are experiencing issues"
    
    return health_status


@router.get("/health/quick")
def quick_health() -> Dict[str, str]:
    """Quick health check - no external dependencies.
    
    Returns:
        Basic application status
    """
    return {
        "status": "ok",
        "message": "Application is running"
    }

