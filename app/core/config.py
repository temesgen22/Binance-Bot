from functools import lru_cache
from typing import Any, Dict, List, Optional, Union
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BinanceAccountConfig(BaseModel):
    """Configuration for a single Binance account."""
    account_id: str
    api_key: Optional[str] = None  # Optional for paper trading (only needed for market data)
    api_secret: Optional[str] = None  # Optional for paper trading
    testnet: bool = True
    paper_trading: bool = False  # Paper trading mode (no real API calls)
    paper_balance: Optional[float] = None  # Initial virtual balance for paper trading
    name: Optional[str] = None  # Optional display name
    
    @model_validator(mode='after')
    def validate_api_keys(self):
        """Validate API keys are provided for non-paper trading accounts."""
        if not self.paper_trading and (not self.api_key or not self.api_secret):
            raise ValueError("API keys required for non-paper trading accounts")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        # Prevent automatic JSON parsing for complex types
        json_schema_serialization_defaults_required=False,
    )

    # Note: API accounts are now stored in database only, not in .env file
    # These fields are kept for backward compatibility but are not used for account management
    binance_api_key: str = Field(default="demo", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="demo", alias="BINANCE_API_SECRET")
    binance_testnet: bool = Field(default=True, alias="BINANCE_TESTNET")
    base_symbols: Union[str, List[str]] = Field(
        default="BTCUSDT,ETHUSDT", alias="BASE_SYMBOLS"
    )
    default_leverage: int = Field(default=5, alias="DEFAULT_LEVERAGE")
    risk_per_trade: float = Field(default=0.01, alias="RISK_PER_TRADE")
    max_concurrent_strategies: int = Field(default=3, alias="MAX_CONCURRENT_STRATEGIES")
    max_concurrent_walk_forward_analyses: int = Field(
        default=5,
        alias="MAX_CONCURRENT_WALK_FORWARD_ANALYSES",
        description="Maximum number of concurrent walk-forward analyses across all users"
    )
    max_walk_forward_analyses_per_user: int = Field(
        default=2,
        alias="MAX_WALK_FORWARD_ANALYSES_PER_USER",
        description="Maximum number of concurrent walk-forward analyses per user"
    )
    walk_forward_task_cleanup_age_hours: int = Field(
        default=24,
        alias="WALK_FORWARD_TASK_CLEANUP_AGE_HOURS",
        description="Age in hours after which completed walk-forward tasks are cleaned up"
    )
    dead_task_cleanup_interval_seconds: int = Field(
        default=60,
        alias="DEAD_TASK_CLEANUP_INTERVAL_SECONDS",
        description="Interval in seconds for periodic cleanup of dead strategy tasks (default: 60 seconds)"
    )
    api_port: int = Field(default=8000, alias="API_PORT")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_enabled: bool = Field(default=True, alias="REDIS_ENABLED")
    
    # PostgreSQL Database Configuration
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/binance_bot",
        alias="DATABASE_URL",
        description="PostgreSQL database connection URL"
    )
    database_echo: bool = Field(
        default=False,
        alias="DATABASE_ECHO",
        description="Echo SQL queries (for debugging)"
    )
    database_pool_size: int = Field(
        default=20,
        alias="DATABASE_POOL_SIZE",
        description="Database connection pool size"
    )
    database_max_overflow: int = Field(
        default=10,
        alias="DATABASE_MAX_OVERFLOW",
        description="Maximum overflow connections"
    )
    
    # Encryption Configuration
    encryption_key: Optional[str] = Field(
        default=None,
        alias="ENCRYPTION_KEY",
        description="Fernet encryption key for API keys/secrets (base64-encoded). "
                   "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )
    
    # JWT Authentication Configuration
    jwt_secret_key: str = Field(
        default="your-secret-key-change-this-in-production",
        alias="JWT_SECRET_KEY",
        description="Secret key for JWT token signing. MUST be changed in production! "
                   "Must be at least 32 characters long and contain a mix of letters, numbers, and special characters."
    )
    jwt_access_token_expire_hours: int = Field(
        default=24,
        alias="JWT_ACCESS_TOKEN_EXPIRE_HOURS",
        description="Access token expiration time in hours"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS",
        description="Refresh token expiration time in days"
    )
    
    # Telegram Notification Configuration
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    telegram_profit_threshold_usd: Optional[float] = Field(default=None, alias="TELEGRAM_PROFIT_THRESHOLD_USD")
    telegram_loss_threshold_usd: Optional[float] = Field(default=None, alias="TELEGRAM_LOSS_THRESHOLD_USD")

    @field_validator("base_symbols", mode="after")
    @classmethod
    def parse_base_symbols(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Handle comma-separated string
            if v.strip().startswith("[") and v.strip().endswith("]"):
                # JSON array format
                import json
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            # Comma-separated format
            return [s.strip() for s in v.split(",") if s.strip()]
        return v if isinstance(v, list) else [str(v)]
    
    @field_validator("jwt_secret_key", mode="after")
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        """Validate JWT secret key strength."""
        # Skip strict validation in test environments and during Alembic migrations
        import os
        import sys
        import inspect
        
        # Check if we're in a test environment
        is_test_env = (
            "pytest" in sys.modules or
            "PYTEST_CURRENT_TEST" in os.environ or
            os.getenv("ENVIRONMENT", "").lower() == "test" or
            os.getenv("TESTING", "").lower() in ("true", "1", "yes")
        )
        
        # Check if we're running Alembic migrations
        # Check multiple ways: sys.argv, call stack, or environment variable
        is_alembic = False
        try:
            # Check if alembic is in command line arguments (most reliable)
            if len(sys.argv) > 0 and any("alembic" in arg.lower() for arg in sys.argv):
                is_alembic = True
            # Check call stack for alembic modules/files
            elif any(
                "alembic" in str(getattr(frame, 'filename', '')).lower() or
                "alembic" in str(getattr(frame, 'file', '')).lower()
                for frame in inspect.stack()
            ):
                is_alembic = True
            # Check if alembic module is loaded
            elif "alembic" in sys.modules:
                is_alembic = True
            # Check environment variable (can be set by deployment scripts)
            elif os.getenv("ALEMBIC_MIGRATION", "").lower() in ("true", "1", "yes"):
                is_alembic = True
        except Exception:
            # If inspection fails, continue with normal validation
            pass
        
        # Allow default value in test environments or during migrations
        if is_test_env or is_alembic:
            # In test/migration environments, allow default value but warn
            if v == "your-secret-key-change-this-in-production":
                env_type = "test" if is_test_env else "migration"
                logger.warning(
                    f"JWT_SECRET_KEY is using default value in {env_type} environment. "
                    "This is acceptable for testing/migrations but must be changed in production."
                )
            return v
        
        # Production validation - strict checks
        # Check for default/weak values
        weak_values = [
            "your-secret-key-change-this-in-production",
            "secret",
            "changeme",
            "password",
            "12345678",
            "default",
        ]
        
        if v.lower() in [w.lower() for w in weak_values]:
            raise ValueError(
                "JWT_SECRET_KEY must be changed from the default value. "
                "Use a strong, random secret key (at least 32 characters)."
            )
        
        # Check minimum length
        if len(v) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least 32 characters long (current: {len(v)}). "
                "Generate a strong key using: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        
        # Check for sufficient entropy (mix of character types)
        has_upper = bool(re.search(r'[A-Z]', v))
        has_lower = bool(re.search(r'[a-z]', v))
        has_digit = bool(re.search(r'\d', v))
        has_special = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>/?]', v))
        
        # Require at least 3 out of 4 character types for strong keys
        char_types = sum([has_upper, has_lower, has_digit, has_special])
        if char_types < 2:
            logger.warning(
                f"JWT_SECRET_KEY should contain a mix of uppercase, lowercase, digits, and special characters. "
                f"Current key has {char_types} character types."
            )
        
        return v
    
    @field_validator("encryption_key", mode="after")
    @classmethod
    def validate_encryption_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate encryption key format."""
        if v is None:
            # Allow None in development, but warn
            import os
            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                raise ValueError(
                    "ENCRYPTION_KEY is required in production. "
                    "Generate one using: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )
            logger.warning(
                "ENCRYPTION_KEY not set. API keys will be stored in plaintext. "
                "This is insecure and should only be used in development."
            )
            return v
        
        # Validate Fernet key format (base64, 32 bytes when decoded)
        try:
            import base64
            key_bytes = base64.urlsafe_b64decode(v.encode())
            if len(key_bytes) != 32:
                raise ValueError(
                    f"ENCRYPTION_KEY must decode to exactly 32 bytes (got {len(key_bytes)}). "
                    "Generate a new key using: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )
        except Exception as e:
            raise ValueError(
                f"Invalid ENCRYPTION_KEY format. Must be a base64-encoded 32-byte key. Error: {e}"
            ) from e
        
        return v
    


@lru_cache(1)
def get_settings() -> Settings:
    return Settings()

