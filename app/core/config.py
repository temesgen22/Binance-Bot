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
    api_key: str
    api_secret: str
    testnet: bool = True
    name: Optional[str] = None  # Optional display name


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        # Prevent automatic JSON parsing for complex types
        json_schema_serialization_defaults_required=False,
    )

    binance_api_key: str = Field(default="demo", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="demo", alias="BINANCE_API_SECRET")
    binance_testnet: bool = Field(default=True, alias="BINANCE_TESTNET")
    
    # Multi-account support: accounts are loaded from environment variables
    # Pattern: BINANCE_ACCOUNT_{account_id}_API_KEY, BINANCE_ACCOUNT_{account_id}_API_SECRET, etc.
    _binance_accounts: Optional[Dict[str, BinanceAccountConfig]] = None
    base_symbols: Union[str, List[str]] = Field(
        default="BTCUSDT,ETHUSDT", alias="BASE_SYMBOLS"
    )
    default_leverage: int = Field(default=5, alias="DEFAULT_LEVERAGE")
    risk_per_trade: float = Field(default=0.01, alias="RISK_PER_TRADE")
    max_concurrent_strategies: int = Field(default=3, alias="MAX_CONCURRENT_STRATEGIES")
    api_port: int = Field(default=8000, alias="API_PORT")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_enabled: bool = Field(default=True, alias="REDIS_ENABLED")
    
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
    
    def get_binance_accounts(self) -> Dict[str, BinanceAccountConfig]:
        """Load and return all configured Binance accounts from environment variables.
        
        Looks for environment variables with pattern:
        - BINANCE_ACCOUNT_{account_id}_API_KEY
        - BINANCE_ACCOUNT_{account_id}_API_SECRET
        - BINANCE_ACCOUNT_{account_id}_NAME (optional)
        - BINANCE_ACCOUNT_{account_id}_TESTNET (optional, defaults to BINANCE_TESTNET)
        
        Also includes the default account (from BINANCE_API_KEY/BINANCE_API_SECRET) as "default".
        
        Returns:
            Dictionary mapping account_id to BinanceAccountConfig
        """
        if self._binance_accounts is not None:
            return self._binance_accounts
        
        # CRITICAL: Explicitly load .env file to ensure all variables are in os.environ
        # pydantic-settings only loads fields defined in the Settings class,
        # so BINANCE_ACCOUNT_* variables won't be in os.environ unless we load them explicitly
        # Try multiple possible locations for .env file
        # __file__ is app/core/config.py, so parent.parent.parent is project root
        project_root = Path(__file__).parent.parent.parent
        env_file = None
        possible_paths = [
            project_root / ".env",  # Project root (most reliable)
            Path(".env"),  # Current directory
            Path.cwd() / ".env",  # Current working directory
        ]
        
        for env_path in possible_paths:
            if env_path.exists() and env_path.is_file():
                env_file = env_path
                break
        
        if env_file:
            logger.debug(f"Loading .env file from: {env_file.absolute()}")
            load_dotenv(env_file, override=False)  # Don't override existing env vars
        else:
            # Check if environment variables are already set (e.g., from Docker env_file or system env)
            has_env_vars = bool(os.environ.get('BINANCE_API_KEY') or any(
                key.startswith('BINANCE_ACCOUNT_') for key in os.environ.keys()
            ))
            if has_env_vars:
                logger.debug(
                    f"Could not find .env file in any of these locations: {[str(p) for p in possible_paths]}, "
                    "but environment variables are already set (likely from Docker or system environment). "
                    "Continuing with existing environment variables."
                )
            else:
                logger.warning(
                    f"Could not find .env file in any of these locations: {[str(p) for p in possible_paths]}. "
                    "Multi-account variables (BINANCE_ACCOUNT_*) may not be loaded. "
                    "If running in Docker, ensure env_file is configured in docker-compose.yml."
                )
        
        accounts: Dict[str, BinanceAccountConfig] = {}
        
        # Add default account if configured
        if self.binance_api_key and self.binance_api_key != "demo":
            accounts["default"] = BinanceAccountConfig(
                account_id="default",
                api_key=self.binance_api_key,
                api_secret=self.binance_api_secret,
                testnet=self.binance_testnet,
                name="Default Account"
            )
        
        # Scan environment for BINANCE_ACCOUNT_*_API_KEY variables
        pattern = re.compile(r'^BINANCE_ACCOUNT_([A-Za-z0-9_]+)_API_KEY$')
        found_account_vars = []
        for env_key, api_key in os.environ.items():
            match = pattern.match(env_key)
            if match:
                found_account_vars.append(env_key)
                account_id = match.group(1).lower()  # Use lowercase for consistency
                
                # Get corresponding API secret
                secret_key = f"BINANCE_ACCOUNT_{match.group(1)}_API_SECRET"
                api_secret = os.environ.get(secret_key)
                
                if not api_secret:
                    logger.warning(f"Found {env_key} but missing corresponding {secret_key}, skipping account '{account_id}'")
                    continue  # Skip if secret is missing
                
                # Get optional name
                name_key = f"BINANCE_ACCOUNT_{match.group(1)}_NAME"
                account_name = os.environ.get(name_key)
                
                # Get optional testnet setting (defaults to global BINANCE_TESTNET)
                testnet_key = f"BINANCE_ACCOUNT_{match.group(1)}_TESTNET"
                testnet_str = os.environ.get(testnet_key, "").lower()
                account_testnet = self.binance_testnet  # Default to global setting
                if testnet_str in ("true", "1", "yes"):
                    account_testnet = True
                elif testnet_str in ("false", "0", "no"):
                    account_testnet = False
                
                accounts[account_id] = BinanceAccountConfig(
                    account_id=account_id,
                    api_key=api_key,
                    api_secret=api_secret,
                    testnet=account_testnet,
                    name=account_name or account_id.title()
                )
        
        # Debug logging
        if found_account_vars:
            logger.debug(f"Found {len(found_account_vars)} BINANCE_ACCOUNT_* environment variables: {found_account_vars}")
        else:
            logger.debug("No BINANCE_ACCOUNT_* environment variables found in os.environ")
        
        logger.info(f"Loaded {len(accounts)} total account(s): {list(accounts.keys())}")
        
        self._binance_accounts = accounts
        return accounts
    
    def get_binance_account(self, account_id: str) -> Optional[BinanceAccountConfig]:
        """Get configuration for a specific Binance account.
        
        Args:
            account_id: The account identifier (e.g., "default", "account1", "main")
            
        Returns:
            BinanceAccountConfig if found, None otherwise
        """
        accounts = self.get_binance_accounts()
        return accounts.get(account_id.lower())


@lru_cache(1)
def get_settings() -> Settings:
    return Settings()

