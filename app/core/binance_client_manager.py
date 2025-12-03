"""Manager for multiple Binance client instances (one per account)."""
from __future__ import annotations

from typing import Dict, Optional
from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.core.config import Settings, BinanceAccountConfig, get_settings


class BinanceClientManager:
    """Manages multiple Binance client instances, one per account."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize the client manager.
        
        Args:
            settings: Settings instance (defaults to get_settings())
        """
        self.settings = settings or get_settings()
        self._clients: Dict[str, BinanceClient] = {}
        self._accounts: Dict[str, BinanceAccountConfig] = {}
        self._initialize_clients()
    
    def _initialize_clients(self) -> None:
        """Initialize all Binance clients from configured accounts."""
        accounts = self.settings.get_binance_accounts()
        self._accounts = accounts
        
        for account_id, account_config in accounts.items():
            try:
                client = BinanceClient(
                    api_key=account_config.api_key,
                    api_secret=account_config.api_secret,
                    testnet=account_config.testnet,
                )
                self._clients[account_id] = client
                logger.info(
                    f"Initialized Binance client for account '{account_id}' "
                    f"({account_config.name}) - Testnet: {account_config.testnet}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize Binance client for account '{account_id}': {e}"
                )
    
    def get_client(self, account_id: str) -> Optional[BinanceClient]:
        """Get Binance client for a specific account.
        
        Args:
            account_id: The account identifier
            
        Returns:
            BinanceClient instance if found, None otherwise
        """
        account_id_lower = account_id.lower()
        return self._clients.get(account_id_lower)
    
    def get_default_client(self) -> Optional[BinanceClient]:
        """Get the default Binance client (account_id='default').
        
        Returns:
            BinanceClient instance if default account exists, None otherwise
        """
        return self.get_client("default")
    
    def list_accounts(self) -> Dict[str, BinanceAccountConfig]:
        """List all configured accounts.
        
        Returns:
            Dictionary mapping account_id to BinanceAccountConfig
        """
        return self._accounts.copy()
    
    def account_exists(self, account_id: str) -> bool:
        """Check if an account exists.
        
        Args:
            account_id: The account identifier
            
        Returns:
            True if account exists, False otherwise
        """
        return account_id.lower() in self._accounts
    
    def get_account_config(self, account_id: str) -> Optional[BinanceAccountConfig]:
        """Get account configuration.
        
        Args:
            account_id: The account identifier
            
        Returns:
            BinanceAccountConfig if found, None otherwise
        """
        return self._accounts.get(account_id.lower())

