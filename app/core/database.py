"""
Database connection and session management for PostgreSQL.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError, DisconnectionError
from loguru import logger

from app.core.config import get_settings
from app.models.db_models import Base

# Global engine and session factory
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
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


def init_database(max_retries: int = 3, force_reconnect: bool = False) -> tuple[bool, Optional[Exception]]:
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
                # Create engine with connection pooling
                _engine = create_engine(
                    database_url,
                    echo=settings.database_echo,
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_pre_ping=True,  # Verify connections before using
                    pool_recycle=3600,  # Recycle connections after 1 hour
                )
                
                # Test connection by creating a session
                test_session = _engine.connect()
                test_session.close()
                
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
                
                # Wait before retry (exponential backoff)
                if attempt < max_retries:
                    import time
                    wait_time = min(2 ** attempt, 10)  # Max 10 seconds
                    logger.info(f"Retrying database connection in {wait_time} seconds...")
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
    """Close database connections."""
    global _engine, _SessionLocal
    
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
        logger.info("Database connections closed")

