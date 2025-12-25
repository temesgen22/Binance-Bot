"""
Database connection and session management for PostgreSQL.
Supports both synchronous (psycopg2) and asynchronous (asyncpg) operations.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, event, pool, text, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.exc import OperationalError, DisconnectionError
from loguru import logger

from app.core.config import get_settings
from app.models.db_models import Base

# Global sync engine and session factory (for backward compatibility)
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

# Global async engine and session factory (new async support)
_async_engine: AsyncEngine | None = None
_AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None

# Global notification callback for connection failures
_notification_callback = None
_last_connection_state = None  # Track connection state to detect changes
# Lock for thread-safe connection recovery
import threading
_connection_lock = threading.Lock()


def set_notification_callback(callback):
    """Set a callback function to be called on database connection failures.
    
    Args:
        callback: Async function that takes (error, retry_count, max_retries) as arguments
    """
    global _notification_callback
    _notification_callback = callback


def get_database_url() -> str:
    """Get database URL from settings."""
    settings = get_settings()
    return settings.database_url


def _validate_connection(engine: Engine, timeout: float = 2.0) -> bool:
    """Validate that database connection is working.
    
    Args:
        engine: SQLAlchemy engine to test
        timeout: Connection timeout in seconds
        
    Returns:
        True if connection is valid, False otherwise
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        return True
    except (OperationalError, DisconnectionError, Exception) as e:
        logger.debug(f"Connection validation failed: {e}")
        return False


def _reset_engine() -> None:
    """Dispose and reset the database engine and session factory.
    
    This is used when connection is lost and needs to be recreated.
    """
    global _engine, _SessionLocal, _last_connection_state
    
    if _engine is not None:
        try:
            _engine.dispose()
            logger.info("Disposed broken database engine")
        except Exception as e:
            logger.warning(f"Error disposing engine: {e}")
    
    _engine = None
    _SessionLocal = None
    _last_connection_state = None


def init_database(max_retries: int = 10, force_reconnect: bool = False) -> tuple[bool, Optional[Exception]]:
    """Initialize database connection pool.
    
    Args:
        max_retries: Maximum number of connection retry attempts
        force_reconnect: If True, force reconnection even if engine exists
        
    Returns:
        Tuple of (success: bool, error: Optional[Exception])
        - success: True if initialization succeeded, False otherwise
        - error: The exception that occurred if initialization failed, None otherwise
    """
    global _engine, _SessionLocal, _last_connection_state
    
    # Use lock to prevent concurrent initialization
    with _connection_lock:
        # If engine exists and we're not forcing reconnect, validate it
        if _engine is not None and not force_reconnect:
            # Validate existing connection
            if _validate_connection(_engine):
                logger.debug("Database connection validated successfully")
                return True, None
            else:
                # Connection is broken, reset and reconnect
                logger.warning("Database connection is broken, resetting engine...")
                _reset_engine()
                # Fall through to recreate connection
    
        settings = get_settings()
        database_url = settings.database_url
        
        logger.info(f"Initializing database connection: {database_url.split('@')[-1] if '@' in database_url else '***'}")
        
        last_error = None
        
        # Retry connection attempts
        for attempt in range(1, max_retries + 1):
            try:
                # Create engine with connection pooling and timeout
                # Add connect_timeout to prevent hanging on connection attempts
                _engine = create_engine(
                    database_url,
                    echo=settings.database_echo,
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_pre_ping=True,  # Verify connections before using
                    pool_recycle=3600,  # Recycle connections after 1 hour
                    connect_args={
                        "connect_timeout": 10,  # 10 second timeout for initial connection
                    },
                )
                
                # Test connection by creating a session (with timeout protection)
                logger.debug("Testing database connection...")
                test_session = _engine.connect()
                test_session.close()
                logger.debug("Database connection test successful")
                
                # Create session factory
                _SessionLocal = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=_engine
                )
                
                logger.info("Database connection pool initialized successfully")
                
                # Update connection state
                _last_connection_state = True
                
                # Return success (and error if we had retries)
                return True, last_error if attempt > 1 else None
                
            except Exception as e:
                last_error = e
                logger.error(f"Database connection attempt {attempt}/{max_retries} failed: {e}")
                
                # Send notification on connection failure (only on last attempt to avoid spam)
                if attempt == max_retries and _notification_callback:
                    try:
                        import asyncio
                        # Try to run the async callback
                        loop = None
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            pass
                        
                        if loop and loop.is_running():
                            # If loop is running, schedule the callback
                            asyncio.create_task(_notification_callback(e, attempt, max_retries))
                        elif loop:
                            # If loop exists but not running, run it
                            loop.run_until_complete(_notification_callback(e, attempt, max_retries))
                        else:
                            # Create new event loop if needed
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(_notification_callback(e, attempt, max_retries))
                            loop.close()
                    except Exception as notify_exc:
                        logger.warning(f"Failed to send database connection failure notification: {notify_exc}")
                
                # Wait before retry (exponential backoff with longer waits for later attempts)
                if attempt < max_retries:
                    import time
                    # Longer waits for later attempts: 2s, 4s, 8s, 10s, 10s, ...
                    wait_time = min(2 ** min(attempt, 3), 10)  # Max 10 seconds, but allow longer for early attempts
                    if attempt >= 5:
                        wait_time = 15  # After 5 attempts, wait 15 seconds between retries
                    logger.info(f"Retrying database connection in {wait_time} seconds... (attempt {attempt}/{max_retries})")
                    time.sleep(wait_time)
        
        # All retries failed
        logger.error(f"Failed to initialize database after {max_retries} attempts")
        
        # Update connection state
        _last_connection_state = False
        
        return False, last_error


def get_engine(retry_on_failure: bool = True) -> Engine:
    """Get database engine. Initializes if not already initialized.
    
    Automatically recovers from connection failures by recreating the engine.
    
    Args:
        retry_on_failure: If True, attempt to reconnect on failure
        
    Raises:
        RuntimeError: If database initialization failed after retries
    """
    global _engine
    
    # If engine doesn't exist, initialize it
    if _engine is None:
        success, error = init_database()
        if not success:
            raise RuntimeError(
                f"Database is not available. Initialization failed: {error}"
            ) from error
    
    # Validate connection and recover if broken
    if _engine is not None:
        if not _validate_connection(_engine):
            if retry_on_failure:
                logger.warning("Database connection is broken, attempting to recover...")
                # Reset and reconnect
                success, error = init_database(force_reconnect=True)
                if not success:
                    raise RuntimeError(
                        f"Database connection lost and recovery failed: {error}"
                    ) from error
            else:
                raise RuntimeError("Database connection is broken")
    
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    
    return _engine


def get_session_factory(retry_on_failure: bool = True) -> sessionmaker[Session]:
    """Get session factory. Initializes database if not already initialized.
    
    Automatically recovers from connection failures by recreating the engine.
    
    Args:
        retry_on_failure: If True, attempt to reconnect on failure
        
    Raises:
        RuntimeError: If database initialization failed after retries
    """
    global _SessionLocal
    
    # Ensure engine is valid (this will recover if broken)
    get_engine(retry_on_failure=retry_on_failure)
    
    if _SessionLocal is None:
        raise RuntimeError("Database session factory is not initialized")
    
    return _SessionLocal


@contextmanager
def get_db_session(max_retries: int = 2) -> Generator[Session, None, None]:
    """Get database session context manager with automatic connection recovery.
    
    Usage:
        with get_db_session() as db:
            user = db.query(User).first()
            db.commit()
    
    Args:
        max_retries: Maximum number of retry attempts on connection failure
    """
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            session_factory = get_session_factory(retry_on_failure=(attempt < max_retries))
            session = session_factory()
            try:
                yield session
                session.commit()
                return  # Success, exit retry loop
            except (OperationalError, DisconnectionError) as e:
                session.rollback()
                session.close()
                last_error = e
                
                # If this is not the last attempt, reset engine and retry
                if attempt < max_retries:
                    logger.warning(f"Database connection lost during operation (attempt {attempt}/{max_retries}), retrying...")
                    _reset_engine()
                    continue
                else:
                    raise
            except Exception:
                session.rollback()
                raise
            finally:
                if 'session' in locals():
                    session.close()
        except (OperationalError, DisconnectionError) as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Database connection failed (attempt {attempt}/{max_retries}), retrying...")
                _reset_engine()
                continue
            else:
                raise RuntimeError(f"Database connection failed after {max_retries} attempts: {e}") from e
    
    # Should not reach here, but just in case
    if last_error:
        raise RuntimeError(f"Database connection failed: {last_error}") from last_error


def get_db_session_dependency() -> Generator[Session, None, None]:
    """FastAPI dependency for database session with automatic connection recovery.
    
    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db_session_dependency)):
            return db.query(User).all()
    
    Automatically recovers from connection failures by recreating the engine.
    """
    max_retries = 2
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            session_factory = get_session_factory(retry_on_failure=(attempt < max_retries))
            session = session_factory()
            try:
                yield session
                return  # Success, exit retry loop
            except (OperationalError, DisconnectionError) as e:
                session.close()
                last_error = e
                
                # If this is not the last attempt, reset engine and retry
                if attempt < max_retries:
                    logger.warning(f"Database connection lost during request (attempt {attempt}/{max_retries}), retrying...")
                    _reset_engine()
                    continue
                else:
                    # Last attempt failed, raise error
                    raise RuntimeError(f"Database connection failed after {max_retries} attempts: {e}") from e
            except Exception:
                # Other exceptions, don't retry
                raise
            finally:
                if 'session' in locals():
                    try:
                        session.close()
                    except Exception:
                        pass  # Ignore errors during cleanup
        except (OperationalError, DisconnectionError) as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Database connection failed (attempt {attempt}/{max_retries}), retrying...")
                _reset_engine()
                continue
            else:
                # Convert to RuntimeError for FastAPI to handle
                raise RuntimeError(f"Database connection unavailable: {e}") from e
    
    # Should not reach here, but just in case
    if last_error:
        raise RuntimeError(f"Database connection failed: {last_error}") from last_error


def create_tables() -> None:
    """Create all database tables. Use Alembic migrations in production."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")


def drop_tables() -> None:
    """Drop all database tables. Use with caution!"""
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    logger.warning("All database tables dropped")


def close_database() -> None:
    """Close database connections (both sync and async)."""
    global _engine, _SessionLocal, _async_engine, _AsyncSessionLocal
    
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
    
    if _async_engine:
        # Note: async engine disposal should be done in async context
        # This is a sync function, so we'll dispose it in the lifespan shutdown
        _async_engine = None
        _AsyncSessionLocal = None
    
        logger.info("Database connections closed")


# ============================================
# ASYNC DATABASE OPERATIONS
# ============================================

async def init_database_async(max_retries: int = 10, force_reconnect: bool = False) -> tuple[bool, Optional[Exception]]:
    """Initialize async database connection pool using asyncpg.
    
    Args:
        max_retries: Maximum number of connection retry attempts
        force_reconnect: If True, force reconnection even if engine exists
        
    Returns:
        Tuple of (success: bool, error: Optional[Exception])
    """
    global _async_engine, _AsyncSessionLocal, _last_connection_state
    
    # If engine exists and we're not forcing reconnect, validate it
    if _async_engine is not None and not force_reconnect:
        # Validate existing connection
        try:
            async with _async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.debug("Async database connection validated successfully")
            return True, None
        except Exception as e:
            logger.warning(f"Async database connection is broken, resetting engine...: {e}")
            await _reset_async_engine()
    
    settings = get_settings()
    database_url = settings.database_url
    
    # Convert postgresql:// to postgresql+asyncpg://
    if database_url.startswith("postgresql://"):
        async_database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    elif database_url.startswith("postgresql+psycopg2://"):
        async_database_url = database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    else:
        async_database_url = database_url
    
    logger.info(f"Initializing async database connection: {async_database_url.split('@')[-1] if '@' in async_database_url else '***'}")
    
    last_error = None
    
    # Retry connection attempts
    for attempt in range(1, max_retries + 1):
        try:
            # Create async engine with connection pooling
            _async_engine = create_async_engine(
                async_database_url,
                echo=settings.database_echo,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,  # Verify connections before using
                pool_recycle=3600,  # Recycle connections after 1 hour
                connect_args={
                    "command_timeout": 10,  # 10 second timeout for commands
                },
            )
            
            # Test connection
            logger.debug("Testing async database connection...")
            async with _async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.debug("Async database connection test successful")
            
            # Create async session factory
            _AsyncSessionLocal = async_sessionmaker(
                _async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            logger.info("Async database connection pool initialized successfully")
            
            # Update connection state
            _last_connection_state = True
            
            return True, last_error if attempt > 1 else None
            
        except Exception as e:
            last_error = e
            logger.error(f"Async database connection attempt {attempt}/{max_retries} failed: {e}")
            
            # Send notification on connection failure (only on last attempt)
            if attempt == max_retries and _notification_callback:
                try:
                    await _notification_callback(e, attempt, max_retries)
                except Exception as notify_exc:
                    logger.warning(f"Failed to send database connection failure notification: {notify_exc}")
            
            # Wait before retry (exponential backoff)
            if attempt < max_retries:
                import asyncio
                wait_time = min(2 ** min(attempt, 3), 10)
                if attempt >= 5:
                    wait_time = 15
                logger.info(f"Retrying async database connection in {wait_time} seconds... (attempt {attempt}/{max_retries})")
                await asyncio.sleep(wait_time)
    
    # All retries failed
    logger.error(f"Failed to initialize async database after {max_retries} attempts")
    _last_connection_state = False
    
    return False, last_error


async def _reset_async_engine() -> None:
    """Dispose and reset the async database engine."""
    global _async_engine, _AsyncSessionLocal
    
    if _async_engine is not None:
        try:
            await _async_engine.dispose()
            logger.info("Disposed broken async database engine")
        except Exception as e:
            logger.warning(f"Error disposing async engine: {e}")
    
    _async_engine = None
    _AsyncSessionLocal = None


async def get_async_engine(retry_on_failure: bool = True) -> AsyncEngine:
    """Get async database engine. Initializes if not already initialized.
    
    Args:
        retry_on_failure: If True, attempt to reconnect on failure
        
    Raises:
        RuntimeError: If database initialization failed after retries
    """
    global _async_engine
    
    # If engine doesn't exist, initialize it
    if _async_engine is None:
        success, error = await init_database_async()
        if not success:
            raise RuntimeError(
                f"Async database is not available. Initialization failed: {error}"
            ) from error
    
    # Validate connection and recover if broken
    if _async_engine is not None:
        try:
            async with _async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            if retry_on_failure:
                logger.warning("Async database connection is broken, attempting to recover...")
                success, error = await init_database_async(force_reconnect=True)
                if not success:
                    raise RuntimeError(
                        f"Async database connection lost and recovery failed: {error}"
                    ) from error
            else:
                raise RuntimeError("Async database connection is broken")
    
    if _async_engine is None:
        raise RuntimeError("Async database engine is not initialized")
    
    return _async_engine


async def get_async_session_factory(retry_on_failure: bool = True) -> async_sessionmaker[AsyncSession]:
    """Get async session factory. Initializes database if not already initialized.
    
    Args:
        retry_on_failure: If True, attempt to reconnect on failure
        
    Raises:
        RuntimeError: If database initialization failed after retries
    """
    global _AsyncSessionLocal
    
    # Ensure engine is valid (this will recover if broken)
    await get_async_engine(retry_on_failure=retry_on_failure)
    
    if _AsyncSessionLocal is None:
        raise RuntimeError("Async database session factory is not initialized")
    
    return _AsyncSessionLocal


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Async database session dependency for FastAPI.
    
    Usage:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
    
    Automatically recovers from connection failures by recreating the engine.
    """
    max_retries = 2
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            session_factory = await get_async_session_factory(retry_on_failure=(attempt < max_retries))
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                    return  # Success, exit retry loop
                except (OperationalError, DisconnectionError) as e:
                    await session.rollback()
                    last_error = e
                    
                    # If this is not the last attempt, reset engine and retry
                    if attempt < max_retries:
                        logger.warning(f"Async database connection lost during request (attempt {attempt}/{max_retries}), retrying...")
                        await _reset_async_engine()
                        continue
                    else:
                        raise RuntimeError(f"Async database connection failed after {max_retries} attempts: {e}") from e
                except Exception:
                    await session.rollback()
                    raise
        except (OperationalError, DisconnectionError) as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Async database connection failed (attempt {attempt}/{max_retries}), retrying...")
                await _reset_async_engine()
                continue
            else:
                raise RuntimeError(f"Async database connection unavailable: {e}") from e
    
    # Should not reach here, but just in case
    if last_error:
        raise RuntimeError(f"Async database connection failed: {last_error}") from last_error


async def close_async_database() -> None:
    """Close async database connections."""
    global _async_engine, _AsyncSessionLocal
    
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        _AsyncSessionLocal = None
        logger.info("Async database connections closed")

