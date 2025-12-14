"""
Database connection and session management for PostgreSQL.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

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


def init_database() -> None:
    """Initialize database connection pool."""
    global _engine, _SessionLocal
    
    if _engine is not None:
        logger.warning("Database already initialized")
        return
    
    settings = get_settings()
    database_url = settings.database_url
    
    logger.info(f"Initializing database connection: {database_url.split('@')[-1] if '@' in database_url else '***'}")
    
    # Create engine with connection pooling
    _engine = create_engine(
        database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,  # Recycle connections after 1 hour
    )
    
    # Create session factory
    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=_engine
    )
    
    logger.info("Database connection pool initialized")


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

