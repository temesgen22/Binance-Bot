"""Manager for multiple Binance client instances (one per account)."""
from __future__ import annotations

from typing import Dict, Optional, Union, Callable
from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.core.paper_binance_client import PaperBinanceClient
from app.core.config import Settings, BinanceAccountConfig, get_settings


class BinanceClientManager:
    """Manages multiple Binance client instances, one per account."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize the client manager.
        
        Args:
            settings: Settings instance (defaults to get_settings())
        """
        self.settings = settings or get_settings()
        self._clients: Dict[str, Union[BinanceClient, PaperBinanceClient]] = {}
        self._accounts: Dict[str, BinanceAccountConfig] = {}
        self._initialize_clients()
    
    def _initialize_clients(self) -> None:
        """Initialize Binance clients.
        
        Note: Accounts are now stored in database only, not in .env file.
        Clients are created on-demand when needed via get_client() or add_client().
        """
        # Accounts are loaded from database when needed, not from .env
        self._accounts = {}
        self._clients = {}
        logger.debug("BinanceClientManager initialized - accounts will be loaded from database when needed")
    
    def add_client(self, account_id: str, account_config: BinanceAccountConfig, balance_persistence_callback: Optional[Callable[[str, float], None]] = None) -> None:
        """Add a client for an account (typically loaded from database).
        
        Args:
            account_id: Account identifier
            account_config: Account configuration
            balance_persistence_callback: Optional callback(account_id: str, balance: float) for paper trading balance persistence
            
        Raises:
            ValueError: If API keys are invalid or missing (for non-paper trading accounts)
        """
        # ✅ CRITICAL: Skip API key validation for paper trading accounts
        if account_config.paper_trading:
            # Paper trading: Create PaperBinanceClient (no API keys needed)
            initial_balance = account_config.paper_balance if account_config.paper_balance else 10000.0
            client = PaperBinanceClient(
                account_id=account_id,
                initial_balance=initial_balance,
                balance_persistence_callback=balance_persistence_callback
            )
            self._clients[account_id.lower()] = client
            self._accounts[account_id.lower()] = account_config
            logger.info(
                f"✅ Added PaperBinanceClient for account '{account_id}' "
                f"({account_config.name}) - Initial Balance: ${initial_balance:.2f}"
            )
            return
        
        # Non-paper trading: Validate API keys before creating client
        if not account_config.api_key or not account_config.api_secret:
            error_msg = f"Account '{account_id}' has empty API key or secret"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Validate API key format (Binance API keys are typically 64 characters)
        if len(account_config.api_key) < 20:
            error_msg = f"Account '{account_id}' has invalid API key format (too short: {len(account_config.api_key)} chars)"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if len(account_config.api_secret) < 20:
            error_msg = f"Account '{account_id}' has invalid API secret format (too short: {len(account_config.api_secret)} chars)"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            client = BinanceClient(
                api_key=account_config.api_key,
                api_secret=account_config.api_secret,
                testnet=account_config.testnet,
            )
            self._clients[account_id.lower()] = client
            self._accounts[account_id.lower()] = account_config
            logger.info(
                f"✅ Added Binance client for account '{account_id}' "
                f"({account_config.name}) - Testnet: {account_config.testnet}"
            )
        except Exception as e:
            error_msg = f"Failed to add Binance client for account '{account_id}': {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
    
    def get_client(self, account_id: str) -> Optional[Union[BinanceClient, PaperBinanceClient]]:
        """Get Binance client for a specific account.
        
        Args:
            account_id: The account identifier
            
        Returns:
            BinanceClient or PaperBinanceClient instance if found, None otherwise
        """
        account_id_lower = account_id.lower()
        return self._clients.get(account_id_lower)
    
    def get_default_client(self) -> Optional[Union[BinanceClient, PaperBinanceClient]]:
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

