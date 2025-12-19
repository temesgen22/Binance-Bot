"""
Database connection and session management for PostgreSQL.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, event, pool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base
from loguru import logger

from app.core.config import get_settings
from app.models.db_models import Base

# Global engine and session factory
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_database_url() -> str:
    """Get database URL from settings."""
    settings = get_settings()
    return settings.database_url


def init_database(max_retries: int = 3) -> tuple[bool, Optional[Exception]]:
    """Initialize database connection pool.
    
    Args:
        max_retries: Maximum number of connection retry attempts
        
    Returns:
        Tuple of (success: bool, error: Optional[Exception])
        - success: True if initialization succeeded, False otherwise
        - error: The exception that occurred if initialization failed, None otherwise
    """
    global _engine, _SessionLocal
    
    if _engine is not None:
        logger.warning("Database already initialized")
        return True, None
    
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
            
            # Return success (and error if we had retries)
            return True, last_error if attempt > 1 else None
            
        except Exception as e:
            last_error = e
            logger.error(f"Database connection attempt {attempt}/{max_retries} failed: {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < max_retries:
                import time
                wait_time = min(2 ** attempt, 10)  # Max 10 seconds
                logger.info(f"Retrying database connection in {wait_time} seconds...")
                time.sleep(wait_time)
    
    # All retries failed
    logger.error(f"Failed to initialize database after {max_retries} attempts")
    return False, last_error


def get_engine() -> Engine:
    """Get database engine. Initializes if not already initialized."""
    if _engine is None:
        init_database()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Get session factory. Initializes database if not already initialized."""
    if _SessionLocal is None:
        init_database()
    return _SessionLocal


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Get database session context manager.
    
    Usage:
        with get_db_session() as db:
            user = db.query(User).first()
            db.commit()
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session_dependency() -> Generator[Session, None, None]:
    """FastAPI dependency for database session.
    
    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db_session_dependency)):
            return db.query(User).all()
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


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

