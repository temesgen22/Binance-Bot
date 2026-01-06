"""Tests for RiskManagementService CRUD operations."""

import pytest
from datetime import datetime, time, timezone
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler, SQLiteDDLCompiler
from sqlalchemy.schema import CheckConstraint

from app.models.db_models import Base, User, Account, RiskManagementConfig as DBRiskConfig
from app.models.risk_management import (
    RiskManagementConfigCreate,
    RiskManagementConfigUpdate,
    RiskManagementConfigResponse,
)
from app.services.risk_management_service import RiskManagementService
from app.core.redis_storage import RedisStorage

# Test database URL (in-memory SQLite for testing)
TEST_DB_URL = "sqlite:///:memory:"

# Map JSONB to JSON for SQLite compatibility (must be done at module level)
if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    original_visit_JSONB = getattr(SQLiteTypeCompiler, 'visit_JSONB', None)
    
    def visit_JSONB(self, type_, **kw):
        """Map JSONB to JSON for SQLite compatibility."""
        return "JSON"
    
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True

# Skip PostgreSQL-specific CHECK constraints (regex operators) for SQLite
if not hasattr(SQLiteDDLCompiler, '_visit_check_constraint_patched'):
    original_visit_check_constraint = SQLiteDDLCompiler.visit_check_constraint
    
    def visit_check_constraint(self, constraint, **kw):
        """Skip CHECK constraints with regex operators for SQLite."""
        try:
            sqltext = str(constraint.sqltext)
            if '~' in sqltext or '~*' in sqltext:
                return None  # Skip this constraint (return None, not empty string)
        except Exception:
            pass
        return original_visit_check_constraint(self, constraint, **kw)
    
    SQLiteDDLCompiler.visit_check_constraint = visit_check_constraint
    SQLiteDDLCompiler._visit_check_constraint_patched = True


@pytest.fixture
def test_db_session():
    """Create a test database session with in-memory SQLite."""
    engine = create_engine(TEST_DB_URL, echo=False)
    
    # Remove PostgreSQL-specific CHECK constraints (regex operators) for SQLite
    for table in Base.metadata.tables.values():
        # Filter out CHECK constraints with regex operators
        constraints_to_remove = []
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                try:
                    sqltext = str(constraint.sqltext)
                    if '~' in sqltext or '~*' in sqltext:
                        constraints_to_remove.append(constraint)
                except Exception:
                    pass
        
        for constraint in constraints_to_remove:
            table.constraints.remove(constraint)
    
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(test_db_session: Session):
    """Create a test user in the database."""
    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)
    return user


@pytest.fixture
def test_account(test_db_session: Session, test_user: User):
    """Create a test account in the database."""
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="test_account",
        name="Test Account",
        api_key_encrypted="encrypted_key",
        api_secret_encrypted="encrypted_secret",
        is_active=True,
        is_default=True,
        exchange_platform="binance",
    )
    test_db_session.add(account)
    test_db_session.commit()
    test_db_session.refresh(account)
    return account


@pytest.fixture
def mock_redis():
    """Create a mock Redis storage."""
    redis = MagicMock(spec=RedisStorage)
    redis.enabled = True
    redis.get = MagicMock(return_value=None)
    redis.set = MagicMock()
    redis.delete = MagicMock()
    return redis


@pytest.fixture
def risk_service(test_db_session: Session, mock_redis):
    """Create a RiskManagementService instance."""
    return RiskManagementService(test_db_session, mock_redis)


class TestRiskManagementService:
    """Tests for RiskManagementService CRUD operations."""
    
    def test_create_risk_config(
        self,
        risk_service: RiskManagementService,
        test_user: User,
        test_account: Account
    ):
        """Test creating a risk management configuration."""
        config_data = RiskManagementConfigCreate(
            account_id=test_account.account_id,
            max_portfolio_exposure_pct=0.8,
            max_daily_loss_pct=0.05,
            circuit_breaker_enabled=True,
        )
        
        result = risk_service.create_risk_config(test_user.id, config_data)
        
        assert result is not None
        assert result.account_id == test_account.account_id
        assert result.max_portfolio_exposure_pct == 0.8
        assert result.max_daily_loss_pct == 0.05
        assert result.circuit_breaker_enabled is True
        assert result.id is not None
        assert result.user_id == str(test_user.id)
    
    def test_get_risk_config(
        self,
        risk_service: RiskManagementService,
        test_user: User,
        test_account: Account
    ):
        """Test getting a risk management configuration."""
        # Create config first
        config_data = RiskManagementConfigCreate(
            account_id=test_account.account_id,
            max_portfolio_exposure_pct=0.8,
        )
        created = risk_service.create_risk_config(test_user.id, config_data)
        
        # Get config
        result = risk_service.get_risk_config(test_user.id, test_account.account_id)
        
        assert result is not None
        assert result.id == created.id
        assert result.max_portfolio_exposure_pct == 0.8
    
    def test_get_risk_config_not_found(
        self,
        risk_service: RiskManagementService,
        test_user: User,
        test_account: Account
    ):
        """Test getting a non-existent risk config returns None."""
        result = risk_service.get_risk_config(test_user.id, test_account.account_id)
        assert result is None
    
    def test_update_risk_config(
        self,
        risk_service: RiskManagementService,
        test_user: User,
        test_account: Account
    ):
        """Test updating a risk management configuration."""
        # Create config first
        config_data = RiskManagementConfigCreate(
            account_id=test_account.account_id,
            max_portfolio_exposure_pct=0.8,
        )
        risk_service.create_risk_config(test_user.id, config_data)
        
        # Update config
        update_data = RiskManagementConfigUpdate(
            max_portfolio_exposure_pct=0.5,
            max_daily_loss_pct=0.03,
        )
        result = risk_service.update_risk_config(
            test_user.id,
            test_account.account_id,
            update_data
        )
        
        assert result is not None
        assert result.max_portfolio_exposure_pct == 0.5
        assert result.max_daily_loss_pct == 0.03
    
    def test_delete_risk_config(
        self,
        risk_service: RiskManagementService,
        test_user: User,
        test_account: Account
    ):
        """Test deleting a risk management configuration."""
        # Create config first
        config_data = RiskManagementConfigCreate(
            account_id=test_account.account_id,
            max_portfolio_exposure_pct=0.8,
        )
        risk_service.create_risk_config(test_user.id, config_data)
        
        # Delete config
        result = risk_service.delete_risk_config(test_user.id, test_account.account_id)
        
        assert result is True
        
        # Verify deleted
        get_result = risk_service.get_risk_config(test_user.id, test_account.account_id)
        assert get_result is None
    
    def test_create_duplicate_risk_config_fails(
        self,
        risk_service: RiskManagementService,
        test_user: User,
        test_account: Account
    ):
        """Test that creating duplicate risk config fails."""
        config_data = RiskManagementConfigCreate(
            account_id=test_account.account_id,
            max_portfolio_exposure_pct=0.8,
        )
        risk_service.create_risk_config(test_user.id, config_data)
        
        # Try to create again
        with pytest.raises(ValueError, match="already exists"):
            risk_service.create_risk_config(test_user.id, config_data)
    
    def test_redis_caching(
        self,
        risk_service: RiskManagementService,
        test_user: User,
        test_account: Account,
        mock_redis
    ):
        """Test that risk config is cached in Redis."""
        config_data = RiskManagementConfigCreate(
            account_id=test_account.account_id,
            max_portfolio_exposure_pct=0.8,
        )
        
        # Create config
        created = risk_service.create_risk_config(test_user.id, config_data)
        
        # Verify Redis delete was called (cache invalidation)
        mock_redis.delete.assert_called()
        
        # Mock cache hit
        import json
        mock_redis.get.return_value = json.dumps(created.model_dump(), default=str)
        
        # Get config (should hit cache)
        result = risk_service.get_risk_config(test_user.id, test_account.account_id)
        
        assert result is not None
        # Verify Redis get was called
        mock_redis.get.assert_called()

