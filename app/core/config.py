from functools import lru_cache
from typing import Any, Dict, List, Optional, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache(1)
def get_settings() -> Settings:
    return Settings()

