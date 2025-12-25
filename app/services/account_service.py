"""
Account service with cache-aside pattern (PostgreSQL + Redis).
Handles account CRUD operations with Redis caching.
"""
from __future__ import annotations

import json
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.redis_storage import RedisStorage
from app.services.base_cache_service import BaseCacheService
from app.models.db_models import Account as DBAccount
from app.core.config import BinanceAccountConfig
from app.core.encryption import get_encryption_service


class AccountService(BaseCacheService):
    """Service for managing accounts with database + Redis cache-aside pattern.
    
    Supports both sync (Session) and async (AsyncSession) database operations.
    """
    
    def __init__(self, db: Session | AsyncSession, redis_storage: Optional[RedisStorage] = None):
        super().__init__(db, redis_storage, cache_ttl=3600)
        self._is_async = isinstance(db, AsyncSession)
    
    def _redis_key(self, user_id: UUID, account_id: str) -> str:
        """Generate Redis key for account with user_id."""
        return super()._redis_key(user_id, account_id, "account")
    
    def _redis_list_key(self, user_id: UUID) -> str:
        """Generate Redis key for user's account list."""
        return f"binance_bot:user:{user_id}:accounts:list"
    
    def _db_account_to_config(self, db_account: DBAccount, decrypt_func: Optional[callable] = None) -> BinanceAccountConfig:
        """Convert database Account model to BinanceAccountConfig.
        
        Args:
            db_account: Database Account model
            decrypt_func: Optional function to decrypt API keys/secrets (deprecated, uses encryption service automatically)
        
        Returns:
            BinanceAccountConfig
        """
        # Try to decrypt using encryption service
        try:
            encryption_service = get_encryption_service()
            api_key = encryption_service.decrypt(db_account.api_key_encrypted)
            api_secret = encryption_service.decrypt(db_account.api_secret_encrypted)
        except (ValueError, ImportError) as e:
            # If encryption service is not available or decryption fails,
            # check if data is stored in plaintext (backward compatibility)
            logger.warning(
                f"Failed to decrypt API keys for account {db_account.account_id}: {e}. "
                "Assuming plaintext storage (backward compatibility)."
            )
            # Try to use as plaintext if decryption fails
            # This handles migration from plaintext to encrypted storage
            try:
                # If it's already plaintext, this will work
                api_key = db_account.api_key_encrypted
                api_secret = db_account.api_secret_encrypted
            except Exception:
                raise ValueError(
                    f"Failed to decrypt API keys and data is not in plaintext format. "
                    f"Account {db_account.account_id} may need to be re-encrypted."
                ) from e
        
        # Legacy decrypt_func support (deprecated)
        if decrypt_func:
            logger.warning("Using deprecated decrypt_func parameter. Encryption service is used automatically.")
            api_key = decrypt_func(api_key)
            api_secret = decrypt_func(api_secret)
        
        return BinanceAccountConfig(
            account_id=db_account.account_id,
            api_key=api_key,
            api_secret=api_secret,
            testnet=db_account.testnet,
            name=db_account.name
        )
    
    def get_account(
        self,
        user_id: UUID,
        account_id: str,
        decrypt_func: Optional[callable] = None
    ) -> Optional[BinanceAccountConfig]:
        """Get account using cache-aside pattern.
        
        Args:
            user_id: User ID
            account_id: Account ID (string, not UUID)
            decrypt_func: Optional function to decrypt API keys/secrets
        
        Returns:
            BinanceAccountConfig if found, None otherwise
        """
        key = self._redis_key(user_id, account_id)
        
        # Try Redis first
        cached_data = self._get_from_cache(key)
        if cached_data:
            logger.debug(f"Cache HIT for account {account_id}")
            # Note: Don't cache decrypted keys in Redis for security
            # Only cache metadata, fetch from DB for actual keys
            if decrypt_func and "api_key" in cached_data:
                # If we have decrypted keys in cache, use them (not recommended for production)
                return BinanceAccountConfig(**cached_data)
            # Otherwise, fall through to database
        
        # Cache miss - check database
        logger.debug(f"Cache MISS for account {account_id}, checking database")
        # Normalize account_id to lowercase for querying
        account_id_normalized = account_id.lower().strip() if account_id else None
        if not account_id_normalized:
            logger.warning(f"Invalid account_id provided: {account_id}")
            return None
        
        # Use direct query for better performance and to check inactive accounts
        # Note: We're querying Account.account_id (string column), not Account.id (UUID primary key)
        logger.debug(f"Querying account with user_id={user_id}, account_id='{account_id_normalized}' (string column)")
        db_account = self.db_service.get_account_by_id(user_id, account_id_normalized)
        
        if not db_account:
            # Also check if account exists but is inactive (for better error messages)
            from app.models.db_models import Account
            inactive_account = self.db.query(Account).filter(
                Account.user_id == user_id,
                Account.account_id.ilike(account_id_normalized),  # Case-insensitive match
                Account.is_active == False
            ).first()
            if inactive_account:
                logger.warning(f"Account '{account_id}' exists but is INACTIVE for user {user_id}")
            return None
        
        # Convert to config
        config = self._db_account_to_config(db_account, decrypt_func)
        
        # Cache metadata in Redis (but NOT decrypted keys for security)
        # Only cache non-sensitive metadata
        metadata = {
            "account_id": config.account_id,
            "name": config.name,
            "testnet": config.testnet,
            "is_active": db_account.is_active,
            "is_default": db_account.is_default,
        }
        self._save_to_cache(key, metadata)
        
        return config
    
    def list_accounts(
        self,
        user_id: UUID,
        decrypt_func: Optional[callable] = None
    ) -> List[BinanceAccountConfig]:
        """List all accounts for a user (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_list_accounts() with AsyncSession")
        db_accounts = self.db_service.get_user_accounts(user_id)
        configs = [self._db_account_to_config(acc, decrypt_func) for acc in db_accounts]
        return configs
    
    async def async_list_accounts(
        self,
        user_id: UUID,
        decrypt_func: Optional[callable] = None
    ) -> List[BinanceAccountConfig]:
        """List all accounts for a user (async)."""
        if not self._is_async:
            raise RuntimeError("Use list_accounts() with Session")
        db_accounts = await self.db_service.async_get_user_accounts(user_id)
        configs = [self._db_account_to_config(acc, decrypt_func) for acc in db_accounts]
        return configs
    
    def get_default_account(
        self,
        user_id: UUID,
        decrypt_func: Optional[callable] = None
    ) -> Optional[BinanceAccountConfig]:
        """Get user's default account (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_default_account() with AsyncSession")
        db_account = self.db_service.get_default_account(user_id)
        if not db_account:
            return None
        return self._db_account_to_config(db_account, decrypt_func)
    
    async def async_get_default_account(
        self,
        user_id: UUID,
        decrypt_func: Optional[callable] = None
    ) -> Optional[BinanceAccountConfig]:
        """Get user's default account (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_default_account() with Session")
        db_account = await self.db_service.async_get_default_account(user_id)
        if not db_account:
            return None
        return self._db_account_to_config(db_account, decrypt_func)
    
    def create_account(
        self,
        user_id: UUID,
        account_id: str,
        api_key: str,
        api_secret: str,
        name: Optional[str] = None,
        exchange_platform: str = "binance",
        testnet: bool = True,
        is_default: bool = False,
        encrypt_func: Optional[callable] = None
    ) -> BinanceAccountConfig:
        """Create a new account in database.
        
        Args:
            user_id: User ID
            account_id: Account ID (string)
            api_key: API key (will be encrypted automatically)
            api_secret: API secret (will be encrypted automatically)
            name: Optional account name
            testnet: Whether this is a testnet account
            is_default: Whether this is the default account
            encrypt_func: Optional function to encrypt API keys/secrets (deprecated, uses encryption service automatically)
        
        Returns:
            BinanceAccountConfig
        """
        # Encrypt API keys using encryption service
        try:
            encryption_service = get_encryption_service()
            api_key_encrypted = encryption_service.encrypt(api_key)
            api_secret_encrypted = encryption_service.encrypt(api_secret)
        except (ValueError, ImportError) as e:
            # If encryption service is not available, fall back to plaintext (development only)
            logger.warning(
                f"Encryption service not available: {e}. "
                "Storing API keys in plaintext (INSECURE - development only)."
            )
            if encrypt_func:
                api_key_encrypted = encrypt_func(api_key)
                api_secret_encrypted = encrypt_func(api_secret)
            else:
                # Store as plaintext only if encryption is not configured
                api_key_encrypted = api_key
                api_secret_encrypted = api_secret
        
        # Create in database
        db_account = self.db_service.create_account(
            user_id=user_id,
            account_id=account_id,
            api_key_encrypted=api_key_encrypted,
            api_secret_encrypted=api_secret_encrypted,
            name=name,
            exchange_platform=exchange_platform,
            testnet=testnet,
            is_default=is_default
        )
        
        # Convert to config
        config = self._db_account_to_config(db_account, decrypt_func=None)
        
        # Invalidate cache
        key = self._redis_key(user_id, account_id)
        list_key = self._redis_list_key(user_id)
        self._invalidate_cache(key, list_key)
        
        return config
    
    def update_account(
        self,
        user_id: UUID,
        account_id: str,
        **updates
    ) -> Optional[BinanceAccountConfig]:
        """Update account in database and invalidate cache.
        
        If api_key or api_secret are provided in updates, they will be encrypted automatically.
        """
        # Encrypt API keys if they're being updated
        if "api_key" in updates:
            try:
                encryption_service = get_encryption_service()
                updates["api_key_encrypted"] = encryption_service.encrypt(updates.pop("api_key"))
            except (ValueError, ImportError) as e:
                logger.warning(f"Encryption service not available: {e}. Storing API key in plaintext.")
                updates["api_key_encrypted"] = updates.pop("api_key")
        
        if "api_secret" in updates:
            try:
                encryption_service = get_encryption_service()
                updates["api_secret_encrypted"] = encryption_service.encrypt(updates.pop("api_secret"))
            except (ValueError, ImportError) as e:
                logger.warning(f"Encryption service not available: {e}. Storing API secret in plaintext.")
                updates["api_secret_encrypted"] = updates.pop("api_secret")
        
        # Update in database
        db_account = self.db_service.update_account(user_id, account_id, **updates)
        
        if not db_account:
            return None
        
        # Convert to config
        config = self._db_account_to_config(db_account)
        
        # Invalidate cache
        key = self._redis_key(user_id, account_id)
        list_key = self._redis_list_key(user_id)
        self._invalidate_cache(key, list_key)
        
        return config
    
    def delete_account(self, user_id: UUID, account_id: str) -> bool:
        """Delete account from database and cache."""
        # Delete from database
        success = self.db_service.delete_account(user_id, account_id)
        
        if success:
            # Delete from cache
            key = self._redis_key(user_id, account_id)
            list_key = self._redis_list_key(user_id)
            self._invalidate_cache(key, list_key)
        
        return success

