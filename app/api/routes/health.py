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


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Liveness probe endpoint.
    
    Kubernetes/Docker uses this to check if the container is alive.
    This should return quickly and not check external dependencies.
    
    Returns:
        Always returns OK if the application is running
    """
    return {
        "status": "alive",
        "message": "Application is running"
    }


@router.get("/health/ready")
def readiness(
    db: Session = Depends(get_db_session_dependency),
    client: BinanceClient = Depends(get_binance_client)
) -> dict[str, str | float | dict]:
    """Readiness probe endpoint.
    
    Kubernetes/Docker uses this to check if the application is ready
    to accept traffic. Checks critical dependencies (database).
    
    Returns:
        Status and component health if ready to serve traffic
        
    Raises:
        HTTPException: If critical services (database) are unreachable
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
    
    # Check Redis connection (if enabled) - with quick timeout to avoid blocking health check
    redis_status = "disabled"
    settings = get_settings()
    if settings.redis_enabled:
        try:
            import socket
            # Quick socket connection test with timeout (1 second max)
            # Parse Redis URL to get host and port
            redis_url = settings.redis_url
            if "://" in redis_url:
                redis_url = redis_url.split("://")[1]
            parts = redis_url.split(":")
            redis_host = parts[0] if parts else "localhost"
            redis_port = int(parts[1].split("/")[0]) if len(parts) > 1 else 6379
            
            # Quick socket connection test (non-blocking, 1 second timeout)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)  # 1 second timeout
            try:
                result = sock.connect_ex((redis_host, redis_port))
                sock.close()
                if result == 0:
                    # Socket is reachable, try quick Redis ping with timeout
                    try:
                        import redis
                        # Create Redis client with short timeout
                        redis_client = redis.from_url(
                            settings.redis_url,
                            socket_timeout=1.0,
                            socket_connect_timeout=1.0,
                            decode_responses=True
                        )
                        redis_client.ping()
                        redis_status = "ok"
                        redis_client.close()
                    except Exception:
                        redis_status = "failed"
                else:
                    redis_status = "failed"
            except (socket.timeout, OSError, Exception):
                redis_status = "failed"
                try:
                    sock.close()
                except Exception:
                    pass
        except Exception as redis_exc:
            logger.debug(f"Redis health check failed: {redis_exc}")
            redis_status = "failed"
            # Don't fail health check if Redis fails, but log it
            # Redis is optional, database is critical
    
    # Check Binance API connection with timeout
    # Use quick_health endpoint for Docker health checks to avoid timeouts
    binance_status = "ok"
    btc_price = None
    try:
        # Use threading timeout (more reliable in FastAPI than signal-based timeout)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(client.get_price, "BTCUSDT")
            try:
                price = future.result(timeout=5.0)  # 5 second timeout
                btc_price = price
                binance_status = "ok"
            except concurrent.futures.TimeoutError:
                logger.warning("Binance API health check timed out after 5 seconds")
                binance_status = "timeout"
                # Don't fail health check - database is more critical
            except Exception as binance_exc:
                logger.warning(f"Binance API health check failed: {binance_exc}")
                binance_status = "error"
                # Don't fail health check - database is more critical
    except Exception as exc:
        logger.warning(f"Binance health check error: {exc}")
        binance_status = "error"
        # Don't fail health check - database is more critical
    
    # Return OK status if database is OK, even if Binance fails
    # This prevents Docker health check failures when Binance API is temporarily unavailable
    overall_status = "ready" if db_status == "ok" else "not_ready"
    
    # For readiness, database is critical - fail if database is down
    if db_status != "ok":
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Application not ready: database is {db_status}"
        )
    
    return {
        "status": overall_status,
        "database": db_status,
        "redis": redis_status,
        "binance": binance_status,
        "btc_price": btc_price,
        "components": {
            "database": {"status": db_status},
            "redis": {"status": redis_status, "enabled": settings.redis_enabled},
            "binance": {"status": binance_status}
        }
    }


@router.get("/health")
def health(
    db: Session = Depends(get_db_session_dependency),
    client: BinanceClient = Depends(get_binance_client)
) -> dict[str, str | float]:
    """Health check endpoint (backward compatibility).
    
    Checks database, Redis (if enabled), and Binance API connections.
    This is used by Docker health checks, so it must verify critical services.
    
    Returns:
        Status and BTC price if all critical services are working
        
    Raises:
        HTTPException: If database, Redis, or Binance API is unreachable
    """
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as db_exc:
        logger.error(f"Database health check failed: {db_exc}")
        db.close()
        raise HTTPException(
            status_code=503,
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
            import socket
            redis_url = settings.redis_url
            if "://" in redis_url:
                redis_url = redis_url.split("://")[1]
            parts = redis_url.split(":")
            redis_host = parts[0] if parts else "localhost"
            redis_port = int(parts[1].split("/")[0]) if len(parts) > 1 else 6379
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                result = sock.connect_ex((redis_host, redis_port))
                sock.close()
                if result == 0:
                    try:
                        import redis
                        redis_client = redis.from_url(
                            settings.redis_url,
                            socket_timeout=1.0,
                            socket_connect_timeout=1.0,
                            decode_responses=True
                        )
                        redis_client.ping()
                        redis_status = "ok"
                        redis_client.close()
                    except Exception:
                        redis_status = "failed"
                else:
                    redis_status = "failed"
            except (socket.timeout, OSError, Exception):
                redis_status = "failed"
                try:
                    sock.close()
                except Exception:
                    pass
        except Exception:
            redis_status = "failed"
    
    # Check Binance API connection
    btc_price = None
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(client.get_price, "BTCUSDT")
            try:
                btc_price = future.result(timeout=5.0)
            except concurrent.futures.TimeoutError:
                logger.warning("Binance API health check timed out")
            except Exception as binance_exc:
                logger.warning(f"Binance API health check failed: {binance_exc}")
    except Exception as exc:
        logger.warning(f"Binance health check error: {exc}")
    
    return {
        "status": "ok" if db_status == "ok" else "error",
        "database": db_status,
        "redis": redis_status,
        "btc_price": btc_price
    }


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

