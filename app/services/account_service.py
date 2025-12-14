"""
Account service with cache-aside pattern (PostgreSQL + Redis).
Handles account CRUD operations with Redis caching.
"""
from __future__ import annotations

import json
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session
from loguru import logger

from app.core.redis_storage import RedisStorage
from app.services.database_service import DatabaseService
from app.models.db_models import Account as DBAccount
from app.core.config import BinanceAccountConfig


class AccountService:
    """Service for managing accounts with database + Redis cache-aside pattern."""
    
    def __init__(self, db: Session, redis_storage: Optional[RedisStorage] = None):
        self.db_service = DatabaseService(db)
        self.redis = redis_storage
        self._cache_ttl = 3600  # 1 hour cache TTL
    
    def _redis_key(self, user_id: UUID, account_id: str) -> str:
        """Generate Redis key for account with user_id."""
        return f"binance_bot:user:{user_id}:account:{account_id}"
    
    def _redis_list_key(self, user_id: UUID) -> str:
        """Generate Redis key for user's account list."""
        return f"binance_bot:user:{user_id}:accounts:list"
    
    def _db_account_to_config(self, db_account: DBAccount, decrypt_func: Optional[callable] = None) -> BinanceAccountConfig:
        """Convert database Account model to BinanceAccountConfig.
        
        Args:
            db_account: Database Account model
            decrypt_func: Optional function to decrypt API keys/secrets
        
        Returns:
            BinanceAccountConfig
        """
        # TODO: Implement encryption/decryption
        # For now, assume api_key_encrypted and api_secret_encrypted are plaintext
        # In production, you should decrypt them here
        api_key = db_account.api_key_encrypted
        api_secret = db_account.api_secret_encrypted
        
        if decrypt_func:
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
        # Try Redis first
        if self.redis and self.redis.enabled:
            try:
                key = self._redis_key(user_id, account_id)
                cached = self.redis._client.get(key) if self.redis._client else None
                if cached:
                    data = json.loads(cached)
                    logger.debug(f"Cache HIT for account {account_id}")
                    # Note: Don't cache decrypted keys in Redis for security
                    # Only cache metadata, fetch from DB for actual keys
                    if decrypt_func and "api_key" in data:
                        # If we have decrypted keys in cache, use them (not recommended for production)
                        return BinanceAccountConfig(**data)
                    # Otherwise, fall through to database
            except Exception as e:
                logger.warning(f"Redis cache read error for account {account_id}: {e}")
        
        # Cache miss - check database
        logger.debug(f"Cache MISS for account {account_id}, checking database")
        accounts = self.db_service.get_user_accounts(user_id)
        db_account = next((acc for acc in accounts if acc.account_id == account_id), None)
        
        if not db_account:
            return None
        
        # Convert to config
        config = self._db_account_to_config(db_account, decrypt_func)
        
        # Cache metadata in Redis (but NOT decrypted keys for security)
        if self.redis and self.redis.enabled:
            try:
                key = self._redis_key(user_id, account_id)
                # Only cache non-sensitive metadata
                metadata = {
                    "account_id": config.account_id,
                    "name": config.name,
                    "testnet": config.testnet,
                    "is_active": db_account.is_active,
                    "is_default": db_account.is_default,
                }
                if self.redis._client:
                    self.redis._client.setex(
                        key,
                        self._cache_ttl,
                        json.dumps(metadata)
                    )
            except Exception as e:
                logger.warning(f"Redis cache write error for account {account_id}: {e}")
        
        return config
    
    def list_accounts(
        self,
        user_id: UUID,
        decrypt_func: Optional[callable] = None
    ) -> List[BinanceAccountConfig]:
        """List all accounts for a user."""
        db_accounts = self.db_service.get_user_accounts(user_id)
        configs = [self._db_account_to_config(acc, decrypt_func) for acc in db_accounts]
        return configs
    
    def get_default_account(
        self,
        user_id: UUID,
        decrypt_func: Optional[callable] = None
    ) -> Optional[BinanceAccountConfig]:
        """Get user's default account."""
        db_account = self.db_service.get_default_account(user_id)
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
            api_key: API key (will be encrypted)
            api_secret: API secret (will be encrypted)
            name: Optional account name
            testnet: Whether this is a testnet account
            is_default: Whether this is the default account
            encrypt_func: Optional function to encrypt API keys/secrets
        
        Returns:
            BinanceAccountConfig
        """
        # TODO: Implement encryption
        # For now, store as plaintext (NOT RECOMMENDED FOR PRODUCTION)
        # In production, encrypt api_key and api_secret before storing
        api_key_encrypted = encrypt_func(api_key) if encrypt_func else api_key
        api_secret_encrypted = encrypt_func(api_secret) if encrypt_func else api_secret
        
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
        if self.redis and self.redis.enabled:
            try:
                key = self._redis_key(user_id, account_id)
                list_key = self._redis_list_key(user_id)
                if self.redis._client:
                    self.redis._client.delete(key, list_key)
            except Exception as e:
                logger.warning(f"Redis cache delete error for account {account_id}: {e}")
        
        return config
    
    def update_account(
        self,
        user_id: UUID,
        account_id: str,
        **updates
    ) -> Optional[BinanceAccountConfig]:
        """Update account in database and invalidate cache."""
        # Update in database
        db_account = self.db_service.update_account(user_id, account_id, **updates)
        
        if not db_account:
            return None
        
        # Convert to config
        config = self._db_account_to_config(db_account)
        
        # Invalidate cache
        if self.redis and self.redis.enabled:
            try:
                key = self._redis_key(user_id, account_id)
                list_key = self._redis_list_key(user_id)
                if self.redis._client:
                    self.redis._client.delete(key, list_key)
            except Exception as e:
                logger.warning(f"Redis cache delete error for account {account_id}: {e}")
        
        return config
    
    def delete_account(self, user_id: UUID, account_id: str) -> bool:
        """Delete account from database and cache."""
        # Delete from database
        success = self.db_service.delete_account(user_id, account_id)
        
        if success:
            # Delete from cache
            if self.redis and self.redis.enabled:
                try:
                    key = self._redis_key(user_id, account_id)
                    list_key = self._redis_list_key(user_id)
                    if self.redis._client:
                        self.redis._client.delete(key, list_key)
                except Exception as e:
                    logger.warning(f"Redis cache delete error for account {account_id}: {e}")
        
        return success

