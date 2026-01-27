"""Account and client management for strategy execution."""

from typing import TYPE_CHECKING, Optional

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.core.binance_client_manager import BinanceClientManager

if TYPE_CHECKING:
    from uuid import UUID
    from app.services.strategy_service import StrategyService


class StrategyAccountManager:
    """Manages account clients for strategy execution."""
    
    def __init__(
        self,
        client: Optional[BinanceClient],
        client_manager: BinanceClientManager,
        strategy_service: Optional["StrategyService"] = None,
        user_id: Optional["UUID"] = None,
        has_direct_client: bool = False,
    ) -> None:
        """Initialize the account manager.
        
        Args:
            client: Default Binance client (for backward compatibility)
            client_manager: Binance client manager for multi-account support
            strategy_service: Strategy service for database access (optional)
            user_id: User ID for multi-user mode (optional)
            has_direct_client: Whether a direct client was provided (for test mocks)
        """
        self.client = client
        self.client_manager = client_manager
        self.strategy_service = strategy_service
        self.user_id = user_id
        self._has_direct_client = has_direct_client
    
    def get_account_client(self, account_id: str) -> BinanceClient:
        """Get client for an account, loading from database if needed.
        
        This ensures mock clients in tests are always used instead of real clients.
        Also loads accounts from database on-demand if not already in client_manager.
        
        Args:
            account_id: Account identifier (e.g., "default", "acc1")
            
        Returns:
            BinanceClient for the specified account
            
        Raises:
            RuntimeError: If account cannot be loaded and fallback is not allowed
        """
        account_id = account_id or "default"
        
        # If we have a directly provided client and account_id is "default", use it
        # This ensures mock clients in tests override real clients from manager
        if account_id == "default" and self._has_direct_client and self.client:
            return self.client
        
        # Check if client already exists in manager
        client = self.client_manager.get_client(account_id)
        if client:
            return client
        
        # Client not found - try to load from database
        # First try with user_id if available, otherwise try to find user by account_id
        try:
            from app.services.account_service import AccountService
            from app.core.redis_storage import RedisStorage
            from app.core.config import get_settings
            from app.models.db_models import Account
            from app.core.database import get_db_session_dependency
            
            # Get database session - use strategy_service if available, otherwise create a new session
            db = None
            db_gen = None
            created_db_session = False
            
            if self.strategy_service:
                db = self.strategy_service.db_service.db
                # This is a shared session - do NOT close it
            else:
                # Create a new database session for account lookup
                # Use the dependency function to get a session
                try:
                    db_gen = get_db_session_dependency()
                    db = next(db_gen)
                    created_db_session = True
                except StopIteration:
                    logger.error("Failed to get database session")
                    db = None
            
            # Create AccountService to load account
            settings = get_settings()
            redis_storage = None
            if settings.redis_enabled:
                redis_storage = RedisStorage(
                    redis_url=settings.redis_url,
                    enabled=settings.redis_enabled
                )
            
            if db is None:
                logger.error("❌ Cannot load account: database session not available")
            else:
                try:
                    account_service = AccountService(db, redis_storage)
                    
                    # If we have user_id, use it directly
                    user_id_to_use = self.user_id
                    
                    # If no user_id, try to find the user by querying accounts with this account_id
                    if not user_id_to_use:
                        logger.debug(f"🔍 No user_id available, searching for account '{account_id}' in database")
                        account_id_normalized = account_id.lower().strip() if account_id else None
                        if account_id_normalized:
                            db_account = db.query(Account).filter(
                                Account.account_id.ilike(account_id_normalized),
                                Account.is_active == True
                            ).first()
                            if db_account:
                                user_id_to_use = db_account.user_id
                                logger.info(f"✅ Found account '{account_id}' belongs to user {user_id_to_use}")
                            else:
                                logger.warning(f"⚠️ Account '{account_id}' not found in database")
                    
                    # ✅ FIX: always define account_config before conditional assignment to prevent UnboundLocalError
                    account_config = None
                    if user_id_to_use:
                        logger.info(f"🔍 Attempting to load account '{account_id}' from database for user {user_id_to_use}")
                        account_config = account_service.get_account(user_id_to_use, account_id)
                    
                    if account_config:
                        # For paper trading accounts, API keys are optional
                        # For non-paper trading accounts, validate API keys before adding
                        if not account_config.paper_trading and (not account_config.api_key or not account_config.api_secret):
                            logger.error(
                                f"❌ Account '{account_id}' loaded but has empty API key or secret. "
                                f"API key present: {bool(account_config.api_key)}, Secret present: {bool(account_config.api_secret)}. "
                                f"This may indicate a decryption failure."
                            )
                        else:
                            # Create balance persistence callback for paper trading accounts
                            balance_callback = None
                            if account_config.paper_trading and db:
                                from app.services.database_service import DatabaseService
                                db_service = DatabaseService(db)
                                
                                def persist_balance(acc_id: str, balance: float) -> None:
                                    """Callback to persist paper trading balance to database."""
                                    try:
                                        db_service.update_paper_balance_by_account_id(acc_id, balance)
                                    except Exception as e:
                                        logger.warning(f"Failed to persist paper balance for account {acc_id}: {e}")
                                
                                balance_callback = persist_balance
                            
                            # Add client to manager
                            try:
                                self.client_manager.add_client(account_id, account_config, balance_callback)
                                logger.info(f"✅ Loaded account '{account_id}' from database and added to client manager")
                                loaded_client = self.client_manager.get_client(account_id)
                                if loaded_client:
                                    return loaded_client
                                else:
                                    logger.error(f"❌ Failed to retrieve client after adding account '{account_id}' to manager")
                            except ValueError as add_exc:
                                # API key validation failed
                                logger.error(f"❌ Failed to add account '{account_id}' to client manager: {add_exc}")
                                raise  # Re-raise to prevent fallback to default client
                            except Exception as add_exc:
                                logger.error(f"❌ Failed to add account '{account_id}' to client manager: {add_exc}", exc_info=True)
                                raise  # Re-raise to prevent fallback to default client
                    else:
                        # Account not found - check if it exists but is inactive or has other issues
                        # Normalize account_id to lowercase for querying
                        account_id_normalized = account_id.lower().strip() if account_id else None
                        user_id_for_query = user_id_to_use if user_id_to_use else None
                        
                        if account_id_normalized:
                            if user_id_for_query:
                                db_account = db.query(Account).filter(
                                    Account.user_id == user_id_for_query,
                                    Account.account_id.ilike(account_id_normalized)  # Case-insensitive match
                                ).first()
                            else:
                                # Search without user_id filter
                                db_account = db.query(Account).filter(
                                    Account.account_id.ilike(account_id_normalized)
                                ).first()
                        else:
                            db_account = None
                        
                        if db_account:
                            if not db_account.is_active:
                                logger.error(
                                    f"❌ Account '{account_id}' exists but is INACTIVE for user {db_account.user_id}. "
                                    f"Please activate the account or use a different account."
                                )
                            else:
                                logger.error(
                                    f"❌ Account '{account_id}' found in database but failed to load configuration. "
                                    f"This may indicate a decryption issue. Check account API keys."
                                )
                        else:
                            # List available accounts for better error message
                            try:
                                if user_id_for_query:
                                    available_accounts = account_service.list_accounts(user_id_for_query)
                                    account_names = [acc.account_id for acc in available_accounts]
                                    logger.error(
                                        f"❌ Account '{account_id}' not found in database for user {user_id_for_query}. "
                                        f"Available accounts: {', '.join(account_names) if account_names else 'none'}"
                                    )
                                else:
                                    logger.error(f"❌ Account '{account_id}' not found in database")
                            except Exception:
                                if user_id_for_query:
                                    logger.error(f"❌ Account '{account_id}' not found in database for user {user_id_for_query}")
                                else:
                                    logger.error(f"❌ Account '{account_id}' not found in database")
                except Exception as e:
                    logger.error(f"❌ Failed to load account '{account_id}' from database: {e}", exc_info=True)
                finally:
                    # IMPORTANT: only close if *we created* the session (not from strategy_service)
                    # Never close shared sessions from strategy_service (would break other requests)
                    if created_db_session:
                        if db_gen is not None:
                            try:
                                db_gen.close()
                            except Exception:
                                pass
                        if db is not None:
                            try:
                                db.close()
                            except Exception:
                                pass
        except Exception as e:
            logger.error(f"❌ Failed to load account '{account_id}' from database: {e}", exc_info=True)
        
        # CRITICAL FIX: Only allow fallback to default client if account_id is "default"
        # Otherwise, this could cause trades to go to the wrong Binance account, which is worse than an error
        if account_id == "default":
            fallback_client = self.client
            if not fallback_client:
                raise RuntimeError(
                    f"No default client available. "
                    f"Please ensure the default account is configured."
                )
            logger.warning(
                f"Default account not found in client manager, using fallback client. "
                f"This may cause API key errors if the fallback client has invalid keys."
            )
            return fallback_client
        else:
            # For non-default accounts, never fallback - this prevents trades going to wrong account
            raise RuntimeError(
                f"No client available for account '{account_id}'. "
                f"Please ensure the account is configured in the database. "
                f"Falling back to default client would risk trades going to the wrong Binance account."
            )


