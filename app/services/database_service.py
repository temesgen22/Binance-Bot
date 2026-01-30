"""
Database service layer for CRUD operations.
Provides high-level database operations with proper error handling.
Supports both synchronous and asynchronous operations.
"""
from __future__ import annotations

from contextlib import contextmanager, asynccontextmanager
from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
from loguru import logger

from app.core.database import get_db_session
from app.models.db_models import (
    User, Role, Account, Strategy, Trade, TradePair,
    Backtest, BacktestTrade, StrategyMetric, SystemEvent,
    WalkForwardAnalysis, WalkForwardWindow, WalkForwardEquityPoint,
    SensitivityAnalysis, SensitivityParameterResult,
    StrategyParameterHistory, StrategyRiskConfig
)


class DatabaseService:
    """Service layer for database operations.
    
    Supports both sync (Session) and async (AsyncSession) database operations.
    When initialized with AsyncSession, use async methods.
    When initialized with Session, use sync methods.
    """
    
    def __init__(self, db: Session | AsyncSession):
        self.db = db
        self._is_async = isinstance(db, AsyncSession)
    
    @contextmanager
    def _transaction(self, *objects_to_refresh, error_message: str = "Database operation"):
        """Context manager for database transactions with automatic error handling.
        
        Args:
            *objects_to_refresh: SQLAlchemy objects to refresh after commit
            error_message: Custom error message prefix for logging
        
        Yields:
            None (context manager)
        
        Raises:
            IntegrityError: If database integrity constraint is violated
            Exception: If any other database error occurs
        """
        try:
            yield
            self.db.commit()
            # Refresh objects after successful commit
            for obj in objects_to_refresh:
                if obj is not None:
                    self.db.refresh(obj)
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"{error_message} failed (integrity error): {e}")
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"{error_message} failed: {e}")
            raise
    
    # ============================================
    # USER OPERATIONS
    # ============================================
    
    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        full_name: Optional[str] = None
    ) -> User:
        """Create a new user."""
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            full_name=full_name
        )
        self.db.add(user)
        with self._transaction(user, error_message=f"Failed to create user {username}"):
            logger.info(f"Created user: {username}")
        return user
    
    def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_user_by_id() with AsyncSession")
        return self.db.query(User).filter(User.id == user_id).first()
    
    async def async_get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_user_by_id() with Session")
        result = await self.db.execute(select(User).filter(User.id == user_id))
        return result.scalar_one_or_none()
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_user_by_username() with AsyncSession")
        return self.db.query(User).filter(User.username == username).first()
    
    async def async_get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_user_by_username() with Session")
        result = await self.db.execute(select(User).filter(User.username == username))
        return result.scalar_one_or_none()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_user_by_email() with AsyncSession")
        return self.db.query(User).filter(User.email == email).first()
    
    async def async_get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_user_by_email() with Session")
        result = await self.db.execute(select(User).filter(User.email == email))
        return result.scalar_one_or_none()
    
    def update_user(self, user_id: UUID, **updates) -> Optional[User]:
        """Update user."""
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        
        for key, value in updates.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        with self._transaction(user, error_message=f"Failed to update user {user_id}"):
            pass
        return user
    
    # ============================================
    # ACCOUNT OPERATIONS
    # ============================================
    
    def create_account(
        self,
        user_id: UUID,
        account_id: str,
        api_key_encrypted: str,
        api_secret_encrypted: str,
        name: Optional[str] = None,
        exchange_platform: str = "binance",
        testnet: bool = True,
        is_default: bool = False,
        paper_trading: bool = False,
        paper_balance: Optional[float] = None
    ) -> Account:
        """Create a new Binance account for a user."""
        # If this is set as default, unset other defaults for this user
        if is_default:
            self.db.query(Account).filter(
                Account.user_id == user_id,
                Account.is_default == True
            ).update({"is_default": False})
        
        account = Account(
            user_id=user_id,
            account_id=account_id,
            api_key_encrypted=api_key_encrypted,
            api_secret_encrypted=api_secret_encrypted,
            name=name,
            exchange_platform=exchange_platform,
            testnet=testnet,
            is_default=is_default,
            paper_trading=paper_trading,
            paper_balance=paper_balance if paper_balance is not None else (10000.0 if paper_trading else None)
        )
        self.db.add(account)
        with self._transaction(account, error_message=f"Failed to create account {account_id}"):
            logger.info(f"Created account {account_id} for user {user_id}")
        return account
    
    def get_user_accounts(self, user_id: UUID) -> List[Account]:
        """Get all accounts for a user (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_user_accounts() with AsyncSession")
        return self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.is_active == True
        ).all()
    
    async def async_get_user_accounts(self, user_id: UUID) -> List[Account]:
        """Get all accounts for a user (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_user_accounts() with Session")
        result = await self.db.execute(
            select(Account).filter(
                Account.user_id == user_id,
                Account.is_active == True
            )
        )
        return list(result.scalars().all())
    
    def get_default_account(self, user_id: UUID) -> Optional[Account]:
        """Get user's default account (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_default_account() with AsyncSession")
        return self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.is_default == True,
            Account.is_active == True
        ).first()
    
    async def async_get_default_account(self, user_id: UUID) -> Optional[Account]:
        """Get user's default account (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_default_account() with Session")
        result = await self.db.execute(
            select(Account).filter(
                Account.user_id == user_id,
                Account.is_default == True,
                Account.is_active == True
            )
        )
        return result.scalar_one_or_none()
    
    def get_account_by_id(self, user_id: UUID, account_id: str) -> Optional[Account]:
        """Get account by user_id and account_id (sync).
        
        Note: account_id is the string identifier (e.g., 'main1'), not the UUID primary key (Account.id).
        The query is case-insensitive to handle any case variations.
        
        Args:
            user_id: User UUID
            account_id: Account string identifier (e.g., 'main1'), NOT the UUID primary key
            
        Returns:
            Account if found and active, None otherwise
        """
        if self._is_async:
            raise RuntimeError("Use async_get_account_by_id() with AsyncSession")
        
        # Normalize account_id to lowercase (constraint requires lowercase)
        account_id_lower = account_id.lower().strip() if account_id else None
        if not account_id_lower:
            return None
        
        # Query using Account.account_id (string column), not Account.id (UUID primary key)
        result = self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.account_id.ilike(account_id_lower),  # Case-insensitive match on string column
            Account.is_active == True
        ).first()
        
        if result:
            logger.debug(
                f"Found account: id={result.id} (UUID), account_id='{result.account_id}' (string), "
                f"user_id={result.user_id}, is_active={result.is_active}"
            )
        else:
            logger.debug(
                f"No active account found with user_id={user_id}, account_id='{account_id_lower}' (string column)"
            )
        
        return result
    
    async def async_get_account_by_id(self, user_id: UUID, account_id: str) -> Optional[Account]:
        """Get account by user_id and account_id (async).
        
        Note: account_id is the string identifier (e.g., 'main1'), not the UUID primary key (Account.id).
        The query is case-insensitive to handle any case variations.
        
        Args:
            user_id: User UUID
            account_id: Account string identifier (e.g., 'main1'), NOT the UUID primary key
            
        Returns:
            Account if found and active, None otherwise
        """
        if not self._is_async:
            raise RuntimeError("Use get_account_by_id() with Session")
        
        # Normalize account_id to lowercase (constraint requires lowercase)
        account_id_lower = account_id.lower().strip() if account_id else None
        if not account_id_lower:
            return None
        
        # Query using Account.account_id (string column), not Account.id (UUID primary key)
        result = await self.db.execute(
            select(Account).filter(
                Account.user_id == user_id,
                Account.account_id.ilike(account_id_lower),  # Case-insensitive match on string column
                Account.is_active == True
            )
        )
        account = result.scalar_one_or_none()
        
        if account:
            logger.debug(
                f"Found account: id={account.id} (UUID), account_id='{account.account_id}' (string), "
                f"user_id={account.user_id}, is_active={account.is_active}"
            )
        else:
            logger.debug(
                f"No active account found with user_id={user_id}, account_id='{account_id_lower}' (string column)"
            )
        
        return account
    
    def update_account(
        self,
        user_id: UUID,
        account_id: str,
        **updates
    ) -> Optional[Account]:
        """Update account."""
        account = self.get_account_by_id(user_id, account_id)
        if not account:
            return None
        
        # Handle is_default update
        if "is_default" in updates and updates["is_default"]:
            # Unset other defaults
            self.db.query(Account).filter(
                Account.user_id == user_id,
                Account.is_default == True,
                Account.id != account.id
            ).update({"is_default": False})
        
        for key, value in updates.items():
            if hasattr(account, key):
                setattr(account, key, value)
        
        with self._transaction(account, error_message=f"Failed to update account {account_id}"):
            pass
        return account
    
    def update_paper_balance_by_account_id(self, account_id: str, balance: float) -> bool:
        """Update paper balance for an account by account_id (without user_id).
        
        This is a convenience method for paper trading balance updates.
        Note: account_id is unique per user, so this queries all accounts.
        
        Args:
            account_id: Account identifier (string)
            balance: New paper balance value
            
        Returns:
            True if account was found and updated, False otherwise
        """
        if self._is_async:
            raise RuntimeError("Use async method for AsyncSession")
        
        account = self.db.query(Account).filter(
            Account.account_id.ilike(account_id.lower()),
            Account.is_active == True
        ).first()
        
        if not account:
            logger.warning(f"Account '{account_id}' not found for paper balance update")
            return False
        
        if not account.paper_trading:
            logger.warning(f"Account '{account_id}' is not a paper trading account")
            return False
        
        account.paper_balance = balance
        with self._transaction(account, error_message=f"Failed to update paper balance for account {account_id}"):
            logger.debug(f"Updated paper balance for account '{account_id}' to ${balance:.2f}")
        
        return True
    
    def delete_account(self, user_id: UUID, account_id: str) -> bool:
        """Hard delete an account from the database.
        
        Permanently removes the account record. This cannot be undone.
        Will fail if account has associated strategies (RESTRICT constraint).
        
        Returns:
            True if account was deleted, False if account not found
            
        Raises:
            ValueError: If account has associated strategies that prevent deletion
        """
        # Get account without is_active filter to allow deleting inactive accounts
        account_id_lower = account_id.lower().strip() if account_id else None
        if not account_id_lower:
            return False
        
        account = self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.account_id.ilike(account_id_lower)
        ).first()
        
        if not account:
            return False
        
        # Check if account has associated strategies (RESTRICT constraint)
        from app.models.db_models import Strategy
        strategy_count = self.db.query(Strategy).filter(
            Strategy.account_id == account.id
        ).count()
        
        if strategy_count > 0:
            raise ValueError(
                f"Cannot delete account '{account_id}': it has {strategy_count} associated strateg{'y' if strategy_count == 1 else 'ies'}. "
                f"Please delete or reassign the strategies first, or deactivate the account instead."
            )
        
        # Hard delete: actually remove the record from database
        self.db.delete(account)
        with self._transaction(error_message=f"Failed to delete account {account_id}"):
            logger.info(f"Permanently deleted account {account_id} for user {user_id}")
        return True
    
    async def async_update_account(
        self,
        user_id: UUID,
        account_id: str,
        **updates
    ) -> Optional[Account]:
        """Update account (async).
        
        Note: This method can update both active and inactive accounts,
        allowing reactivation of inactive accounts.
        """
        if not self._is_async:
            raise RuntimeError("Use update_account() with Session")
        
        # Get account without is_active filter to allow updating inactive accounts
        # Normalize account_id to lowercase (constraint requires lowercase)
        account_id_lower = account_id.lower().strip() if account_id else None
        if not account_id_lower:
            return None
        
        # Query using Account.account_id (string column), not Account.id (UUID primary key)
        # Don't filter by is_active to allow updating inactive accounts
        result = await self.db.execute(
            select(Account).filter(
                Account.user_id == user_id,
                Account.account_id.ilike(account_id_lower)  # Case-insensitive match on string column
                # Note: No is_active filter - allows updating inactive accounts
            )
        )
        account = result.scalar_one_or_none()
        
        if not account:
            return None
        
        # Handle is_default update
        if "is_default" in updates and updates["is_default"]:
            # Unset other defaults
            stmt = update(Account).where(
                Account.user_id == user_id,
                Account.is_default == True,
                Account.id != account.id
            ).values(is_default=False)
            await self.db.execute(stmt)
        
        for key, value in updates.items():
            if hasattr(account, key):
                setattr(account, key, value)
        
        try:
            await self.db.commit()
            await self.db.refresh(account)
            logger.info(f"Updated account {account_id} for user {user_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update account {account_id}: {e}")
            raise
        
        return account
    
    async def async_delete_account(self, user_id: UUID, account_id: str) -> bool:
        """Hard delete an account from the database (async).
        
        Permanently removes the account record. This cannot be undone.
        Will fail if account has associated strategies (RESTRICT constraint).
        
        Returns:
            True if account was deleted, False if account not found
            
        Raises:
            ValueError: If account has associated strategies that prevent deletion
        """
        if not self._is_async:
            raise RuntimeError("Use delete_account() with Session")
        
        # Get account without is_active filter to allow deleting inactive accounts
        account_id_lower = account_id.lower().strip() if account_id else None
        if not account_id_lower:
            return False
        
        result = await self.db.execute(
            select(Account).filter(
                Account.user_id == user_id,
                Account.account_id.ilike(account_id_lower)
            )
        )
        account = result.scalar_one_or_none()
        
        if not account:
            return False
        
        # Check if account has associated strategies (RESTRICT constraint)
        from app.models.db_models import Strategy
        strategy_result = await self.db.execute(
            select(func.count(Strategy.id)).filter(
                Strategy.account_id == account.id
            )
        )
        strategy_count = strategy_result.scalar_one() or 0
        
        if strategy_count > 0:
            raise ValueError(
                f"Cannot delete account '{account_id}': it has {strategy_count} associated strateg{'y' if strategy_count == 1 else 'ies'}. "
                f"Please delete or reassign the strategies first, or deactivate the account instead."
            )
        
        # Hard delete: actually remove the record from database
        try:
            await self.db.delete(account)
            await self.db.commit()
            logger.info(f"Permanently deleted account {account_id} for user {user_id}")
        except IntegrityError as e:
            await self.db.rollback()
            # Check if it's a RESTRICT constraint violation
            error_msg = str(e)
            if "restrict" in error_msg.lower() or "constraint" in error_msg.lower():
                raise ValueError(
                    f"Cannot delete account '{account_id}': it has associated strategies. "
                    f"Please delete or reassign the strategies first, or deactivate the account instead."
                ) from e
            logger.error(f"Failed to delete account {account_id}: {e}")
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to delete account {account_id}: {e}")
            raise
        
        return True
    
    # ============================================
    # STRATEGY OPERATIONS
    # ============================================
    
    def create_strategy(
        self,
        user_id: UUID,
        strategy_id: str,
        name: str,
        symbol: str,
        strategy_type: str,
        account_id: UUID,
        leverage: int,
        risk_per_trade: float,
        params: dict,
        fixed_amount: Optional[float] = None,
        max_positions: int = 1
    ) -> Strategy:
        """Create a new strategy."""
        # Strip whitespace from symbol to prevent API signature errors
        symbol = symbol.strip() if symbol else ""
        strategy = Strategy(
            user_id=user_id,
            strategy_id=strategy_id,
            name=name,
            symbol=symbol,
            strategy_type=strategy_type,
            account_id=account_id,
            leverage=leverage,
            risk_per_trade=risk_per_trade,
            params=params,
            fixed_amount=fixed_amount,
            max_positions=max_positions,
            status="stopped"
        )
        self.db.add(strategy)
        with self._transaction(strategy, error_message=f"Failed to create strategy {strategy_id}"):
            logger.info(f"Created strategy {strategy_id} for user {user_id}")
        return strategy
    
    def get_user_strategies(self, user_id: UUID) -> List[Strategy]:
        """Get all strategies for a user (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_user_strategies() with AsyncSession")
        return self.db.query(Strategy).filter(
            Strategy.user_id == user_id
        ).all()
    
    async def async_get_user_strategies(self, user_id: UUID) -> List[Strategy]:
        """Get all strategies for a user (async).
        
        Eagerly loads the account relationship to avoid lazy loading issues in async context.
        """
        if not self._is_async:
            raise RuntimeError("Use get_user_strategies() with Session")
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(Strategy)
            .options(selectinload(Strategy.account))
            .filter(Strategy.user_id == user_id)
        )
        return list(result.scalars().all())
    
    def get_strategy(self, user_id: UUID, strategy_id: str) -> Optional[Strategy]:
        """Get a specific strategy by user and strategy_id (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_strategy() with AsyncSession")
        return self.db.query(Strategy).filter(
            Strategy.user_id == user_id,
            Strategy.strategy_id == strategy_id
        ).first()
    
    async def async_get_strategy(self, user_id: UUID, strategy_id: str) -> Optional[Strategy]:
        """Get a specific strategy by user and strategy_id (async).
        
        Eagerly loads the account relationship to avoid lazy loading issues in async context.
        """
        if not self._is_async:
            raise RuntimeError("Use get_strategy() with Session")
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(Strategy)
            .options(selectinload(Strategy.account))
            .filter(
                Strategy.user_id == user_id,
                Strategy.strategy_id == strategy_id
            )
        )
        return result.scalar_one_or_none()
    
    def get_strategy_by_uuid(self, strategy_uuid: UUID) -> Optional[Strategy]:
        """Get strategy by UUID (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_strategy_by_uuid() with AsyncSession")
        return self.db.query(Strategy).filter(Strategy.id == strategy_uuid).first()
    
    def get_account_by_uuid(self, account_uuid: UUID) -> Optional[Account]:
        """Get account by UUID (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_account_by_uuid() with AsyncSession")
        return self.db.query(Account).filter(Account.id == account_uuid).first()
    
    def update_strategy(
        self,
        user_id: UUID,
        strategy_id: str,
        **updates
    ) -> Optional[Strategy]:
        """Update strategy."""
        strategy = self.get_strategy(user_id, strategy_id)
        if not strategy:
            return None
        
        # Strip whitespace from symbol if being updated
        if "symbol" in updates and updates["symbol"]:
            updates["symbol"] = updates["symbol"].strip()
        
        for key, value in updates.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)
        
        with self._transaction(strategy, error_message=f"Failed to update strategy {strategy_id}"):
            pass
        return strategy
    
    def delete_strategy(self, user_id: UUID, strategy_id: str) -> bool:
        """Delete a strategy.
        
        This will cascade delete:
        - All trades (via CASCADE foreign key)
        - All completed_trades (via CASCADE foreign key)
        - All completed_trade_orders (via CASCADE from completed_trades)
        - All trade_pairs (via CASCADE relationship)
        - All metrics (via CASCADE relationship)
        """
        from app.models.db_models import CompletedTrade
        
        strategy = self.get_strategy(user_id, strategy_id)
        if not strategy:
            return False
        
        # Log what will be deleted (for debugging)
        trade_count = len(strategy.trades) if strategy.trades else 0
        completed_trade_count = len(strategy.completed_trades) if strategy.completed_trades else 0
        logger.info(
            f"Deleting strategy {strategy_id}: "
            f"{trade_count} trades, {completed_trade_count} completed trades will be cascade deleted"
        )
        
        # Delete strategy - CASCADE will handle related records
        # Foreign keys with CASCADE:
        # - trades.strategy_id -> CASCADE (deletes all trades)
        # - completed_trades.strategy_id -> CASCADE (deletes all completed_trades)
        # - completed_trade_orders.completed_trade_id -> CASCADE (deletes when completed_trade deleted)
        self.db.delete(strategy)
        with self._transaction(error_message=f"Failed to delete strategy {strategy_id}"):
            logger.info(f"✅ Deleted strategy {strategy_id} for user {user_id} (cascade deleted {trade_count} trades, {completed_trade_count} completed trades)")
        return True
    
    # ============================================
    # STRATEGY RISK CONFIG OPERATIONS
    # ============================================
    
    def create_strategy_risk_config(
        self,
        user_id: UUID,
        strategy_id: str,  # String ID (e.g., "strategy-1"), NOT UUID
        max_daily_loss_usdt: Optional[float] = None,
        max_daily_loss_pct: Optional[float] = None,
        max_weekly_loss_usdt: Optional[float] = None,
        max_weekly_loss_pct: Optional[float] = None,
        max_drawdown_pct: Optional[float] = None,
        max_exposure_usdt: Optional[float] = None,
        max_exposure_pct: Optional[float] = None,
        enabled: bool = True,
        override_account_limits: bool = False,
        use_more_restrictive: bool = True,
        timezone: str = "UTC",
        daily_loss_reset_time: Optional[datetime] = None,
        weekly_loss_reset_day: Optional[int] = None
    ) -> StrategyRiskConfig:
        """Create a new strategy risk configuration.
        
        Args:
            user_id: User UUID
            strategy_id: Strategy string ID (e.g., "strategy-1"), NOT UUID
                Must convert to Strategy.id (UUID) for database foreign key
        
        Returns:
            Created StrategyRiskConfig
        
        Raises:
            IntegrityError: If strategy_id not found or config already exists
        """
        # Get strategy to get UUID for foreign key
        strategy = self.get_strategy(user_id, strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found for user {user_id}")
        
        # Create config with Strategy.id (UUID) as foreign key
        config = StrategyRiskConfig(
            strategy_id=strategy.id,  # Use UUID from Strategy.id
            user_id=user_id,
            max_daily_loss_usdt=max_daily_loss_usdt,
            max_daily_loss_pct=max_daily_loss_pct,
            max_weekly_loss_usdt=max_weekly_loss_usdt,
            max_weekly_loss_pct=max_weekly_loss_pct,
            max_drawdown_pct=max_drawdown_pct,
            max_exposure_usdt=max_exposure_usdt,
            max_exposure_pct=max_exposure_pct,
            enabled=enabled,
            override_account_limits=override_account_limits,
            use_more_restrictive=use_more_restrictive,
            timezone=timezone,
            daily_loss_reset_time=daily_loss_reset_time,
            weekly_loss_reset_day=weekly_loss_reset_day
        )
        self.db.add(config)
        with self._transaction(config, error_message=f"Failed to create strategy risk config for {strategy_id}"):
            logger.info(f"Created strategy risk config for strategy {strategy_id}")
        return config
    
    def get_strategy_risk_config(
        self,
        user_id: UUID,
        strategy_id: str  # String ID (e.g., "strategy-1"), NOT UUID
    ) -> Optional[StrategyRiskConfig]:
        """Get strategy risk configuration (sync).
        
        Args:
            user_id: User UUID
            strategy_id: Strategy string ID (e.g., "strategy-1"), NOT UUID
        
        Returns:
            StrategyRiskConfig if found, None otherwise
        """
        if self._is_async:
            raise RuntimeError("Use async_get_strategy_risk_config() with AsyncSession")
        
        # Get strategy to get UUID
        strategy = self.get_strategy(user_id, strategy_id)
        if not strategy:
            return None
        
        # Load with strategy relationship to access strategy.strategy_id (string)
        from sqlalchemy.orm import joinedload
        config = self.db.query(StrategyRiskConfig).options(
            joinedload(StrategyRiskConfig.strategy)
        ).filter(
            StrategyRiskConfig.strategy_id == strategy.id,
            StrategyRiskConfig.user_id == user_id
        ).first()
        
        return config
    
    async def async_get_strategy_risk_config(
        self,
        user_id: UUID,
        strategy_id: str  # String ID (e.g., "strategy-1"), NOT UUID
    ) -> Optional[StrategyRiskConfig]:
        """Get strategy risk configuration (async).
        
        Args:
            user_id: User UUID
            strategy_id: Strategy string ID (e.g., "strategy-1"), NOT UUID
        
        Returns:
            StrategyRiskConfig if found, None otherwise
        """
        if not self._is_async:
            raise RuntimeError("Use get_strategy_risk_config() with Session")
        
        # Get strategy to get UUID
        strategy = await self.async_get_strategy(user_id, strategy_id)
        if not strategy:
            return None
        
        # Load with strategy relationship to access strategy.strategy_id (string)
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(StrategyRiskConfig)
            .options(selectinload(StrategyRiskConfig.strategy))
            .filter(
                StrategyRiskConfig.strategy_id == strategy.id,
                StrategyRiskConfig.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    def update_strategy_risk_config(
        self,
        user_id: UUID,
        strategy_id: str,  # String ID (e.g., "strategy-1"), NOT UUID
        updates: dict  # Dictionary of fields to update
    ) -> Optional[StrategyRiskConfig]:
        """Update strategy risk configuration (sync).
        
        Args:
            user_id: User UUID
            strategy_id: Strategy string ID (e.g., "strategy-1"), NOT UUID
            updates: Dictionary of fields to update (from Pydantic model.model_dump(exclude_unset=True))
        
        Returns:
            Updated StrategyRiskConfig if found, None otherwise
        """
        if self._is_async:
            raise RuntimeError("Use async_update_strategy_risk_config() with AsyncSession")
        
        # Get existing config
        db_config = self.get_strategy_risk_config(user_id, strategy_id)
        if not db_config:
            return None
        
        # Update fields
        for key, value in updates.items():
            if hasattr(db_config, key):
                setattr(db_config, key, value)
        
        with self._transaction(db_config, error_message=f"Failed to update strategy risk config for {strategy_id}"):
            logger.info(f"Updated strategy risk config for strategy {strategy_id}")
        
        return db_config
    
    async def async_update_strategy_risk_config(
        self,
        user_id: UUID,
        strategy_id: str,  # String ID (e.g., "strategy-1"), NOT UUID
        updates: dict  # Dictionary of fields to update
    ) -> Optional[StrategyRiskConfig]:
        """Update strategy risk configuration (async).
        
        Args:
            user_id: User UUID
            strategy_id: Strategy string ID (e.g., "strategy-1"), NOT UUID
            updates: Dictionary of fields to update
        
        Returns:
            Updated StrategyRiskConfig if found, None otherwise
        """
        if not self._is_async:
            raise RuntimeError("Use update_strategy_risk_config() with Session")
        
        # Get existing config
        db_config = await self.async_get_strategy_risk_config(user_id, strategy_id)
        if not db_config:
            return None
        
        # Update fields
        for key, value in updates.items():
            if hasattr(db_config, key):
                setattr(db_config, key, value)
        
        self.db.add(db_config)
        await self.db.commit()
        await self.db.refresh(db_config)
        
        return db_config
    
    def delete_strategy_risk_config(
        self,
        user_id: UUID,
        strategy_id: str  # String ID (e.g., "strategy-1"), NOT UUID
    ) -> bool:
        """Delete strategy risk configuration (sync).
        
        Args:
            user_id: User UUID
            strategy_id: Strategy string ID (e.g., "strategy-1"), NOT UUID
        
        Returns:
            True if deleted, False if not found
        """
        if self._is_async:
            raise RuntimeError("Use async_delete_strategy_risk_config() with AsyncSession")
        
        # Get config
        db_config = self.get_strategy_risk_config(user_id, strategy_id)
        if not db_config:
            return False
        
        self.db.delete(db_config)
        with self._transaction(error_message=f"Failed to delete strategy risk config for {strategy_id}"):
            logger.info(f"Deleted strategy risk config for strategy {strategy_id}")
        
        return True
    
    async def async_delete_strategy_risk_config(
        self,
        user_id: UUID,
        strategy_id: str  # String ID (e.g., "strategy-1"), NOT UUID
    ) -> bool:
        """Delete strategy risk configuration (async).
        
        Args:
            user_id: User UUID
            strategy_id: Strategy string ID (e.g., "strategy-1"), NOT UUID
        
        Returns:
            True if deleted, False if not found
        """
        if not self._is_async:
            raise RuntimeError("Use delete_strategy_risk_config() with Session")
        
        # Get config
        db_config = await self.async_get_strategy_risk_config(user_id, strategy_id)
        if not db_config:
            return False
        
        await self.db.delete(db_config)
        await self.db.commit()
        
        return True
    
    # ============================================
    # TRADE OPERATIONS
    # ============================================
    
    def create_trade(self, trade_data: dict) -> Trade:
        """Create a new trade record."""
        trade = Trade(**trade_data)
        self.db.add(trade)
        with self._transaction(trade, error_message="Failed to create trade"):
            pass
        return trade
    
    def get_user_trades(
        self,
        user_id: UUID,
        strategy_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[Trade]:
        """Get trades for a user, optionally filtered by strategy (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_user_trades() with AsyncSession")
        query = self.db.query(Trade).filter(Trade.user_id == user_id)
        
        if strategy_id:
            query = query.filter(Trade.strategy_id == strategy_id)
        
        return query.order_by(Trade.timestamp.desc()).limit(limit).all()
    
    async def async_get_user_trades(
        self,
        user_id: UUID,
        strategy_id: Optional[UUID] = None,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Trade]:
        """Get trades for a user, optionally filtered by strategy and date range (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_user_trades() with Session")
        stmt = select(Trade).filter(Trade.user_id == user_id)
        
        if strategy_id:
            stmt = stmt.filter(Trade.strategy_id == strategy_id)
        
        if start_time:
            stmt = stmt.filter(Trade.timestamp >= start_time)
        if end_time:
            stmt = stmt.filter(Trade.timestamp <= end_time)
        
        stmt = stmt.order_by(Trade.timestamp.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    def get_user_trades_batch(
        self,
        user_id: UUID,
        strategy_ids: List[UUID],
        limit: int = 10000
    ) -> List[Trade]:
        """Get trades for multiple strategies in a single query (optimizes N+1 problem) - sync."""
        if self._is_async:
            raise RuntimeError("Use async_get_user_trades_batch() with AsyncSession")
        if not strategy_ids:
            return []
        
        query = self.db.query(Trade).filter(
            Trade.user_id == user_id,
            Trade.strategy_id.in_(strategy_ids)
        )
        
        return query.order_by(Trade.timestamp.desc()).limit(limit).all()
    
    async def async_get_user_trades_batch(
        self,
        user_id: UUID,
        strategy_ids: List[UUID],
        limit: int = 10000
    ) -> List[Trade]:
        """Get trades for multiple strategies in a single query (optimizes N+1 problem) - async."""
        if not self._is_async:
            raise RuntimeError("Use get_user_trades_batch() with Session")
        if not strategy_ids:
            return []
        
        stmt = select(Trade).filter(
            Trade.user_id == user_id,
            Trade.strategy_id.in_(strategy_ids)
        ).order_by(Trade.timestamp.desc()).limit(limit)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    # ============================================
    # TRADE PAIR OPERATIONS
    # ============================================
    
    def create_trade_pair(self, pair_data: dict) -> TradePair:
        """Create a new trade pair."""
        pair = TradePair(**pair_data)
        self.db.add(pair)
        with self._transaction(pair, error_message="Failed to create trade pair"):
            pass
        return pair
    
    def get_open_trade_pairs(self, user_id: UUID, strategy_id: Optional[UUID] = None) -> List[TradePair]:
        """Get open trade pairs for a user."""
        query = self.db.query(TradePair).filter(
            TradePair.user_id == user_id,
            TradePair.is_open == True
        )
        
        if strategy_id:
            query = query.filter(TradePair.strategy_id == strategy_id)
        
        return query.all()
    
    # ============================================
    # BACKTEST OPERATIONS
    # ============================================
    
    def create_backtest(self, backtest_data: dict) -> Backtest:
        """Create a new backtest."""
        backtest = Backtest(**backtest_data)
        self.db.add(backtest)
        with self._transaction(backtest, error_message="Failed to create backtest"):
            pass
        return backtest
    
    def get_user_backtests(self, user_id: UUID) -> List[Backtest]:
        """Get all backtests for a user."""
        return self.db.query(Backtest).filter(
            Backtest.user_id == user_id
        ).order_by(Backtest.created_at.desc()).all()
    
    def get_backtest(self, user_id: UUID, backtest_id: UUID) -> Optional[Backtest]:
        """Get a specific backtest."""
        return self.db.query(Backtest).filter(
            Backtest.id == backtest_id,
            Backtest.user_id == user_id
        ).first()
    
    # ============================================
    # WALK-FORWARD ANALYSIS OPERATIONS
    # ============================================
    
    async def save_walk_forward_analysis(
        self,
        user_id: UUID,
        result: Any,  # WalkForwardResult from walk_forward.py
        request: Any,  # WalkForwardRequest from walk_forward.py
        execution_time_ms: Optional[int] = None,
        candles_processed: Optional[int] = None,
        name: Optional[str] = None,
        label: Optional[str] = None,
        keep_details: bool = True
    ) -> UUID:
        """Save walk-forward analysis results to database.
        
        CRITICAL: Always sets user_id to ensure user isolation.
        
        Returns:
            UUID of saved analysis
        """
        if self._is_async:
            return await self._async_save_walk_forward_analysis(
                user_id, result, request, execution_time_ms, candles_processed,
                name, label, keep_details
            )
        else:
            return self._sync_save_walk_forward_analysis(
                user_id, result, request, execution_time_ms, candles_processed,
                name, label, keep_details
            )
    
    def _sync_save_walk_forward_analysis(
        self,
        user_id: UUID,
        result: Any,
        request: Any,
        execution_time_ms: Optional[int],
        candles_processed: Optional[int],
        name: Optional[str],
        label: Optional[str],
        keep_details: bool
    ) -> UUID:
        """Sync implementation of save_walk_forward_analysis."""
        from datetime import datetime, timezone
        
        # Create main analysis record
        analysis = WalkForwardAnalysis(
            user_id=user_id,  # CRITICAL: User isolation
            name=name,
            label=label,
            symbol=result.symbol,
            strategy_type=result.strategy_type,
            overall_start_time=result.overall_start_time,
            overall_end_time=result.overall_end_time,
            training_period_days=result.training_period_days,
            test_period_days=result.test_period_days,
            step_size_days=result.step_size_days,
            window_type=result.window_type,
            total_windows=result.total_windows,
            leverage=request.leverage,
            risk_per_trade=request.risk_per_trade,
            fixed_amount=request.fixed_amount,
            initial_balance=result.initial_balance,
            params=request.params,
            optimization_enabled=request.optimize_params is not None,
            optimization_method=request.optimization_method if request.optimize_params else None,
            optimization_metric=request.optimization_metric if request.optimize_params else None,
            optimize_params=request.optimize_params if request.optimize_params else {},
            min_trades_guardrail=request.min_trades_guardrail if request.optimize_params else None,
            max_drawdown_cap=request.max_drawdown_cap if request.optimize_params else None,
            lottery_trade_threshold=request.lottery_trade_threshold if request.optimize_params else None,
            total_return_pct=result.total_return_pct,
            avg_window_return_pct=result.avg_window_return_pct,
            consistency_score=result.consistency_score,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown_pct=result.max_drawdown_pct,
            total_trades=result.total_trades,
            avg_win_rate=result.avg_win_rate,
            return_std_dev=result.return_std_dev,
            best_window=result.best_window,
            worst_window=result.worst_window,
            final_balance=result.equity_curve[-1]["balance"] if result.equity_curve else result.initial_balance,
            execution_time_ms=execution_time_ms,
            candles_processed=candles_processed,
            keep_details=keep_details,
            completed_at=datetime.now(timezone.utc)
        )
        
        self.db.add(analysis)
        with self._transaction(analysis, error_message="Failed to save walk-forward analysis"):
            logger.info(f"Created walk-forward analysis {analysis.id} for user {user_id}")
        
        # Create window records
        if keep_details:
            for window in result.windows:
                window_record = WalkForwardWindow(
                    analysis_id=analysis.id,
                    window_number=window.window_number,
                    training_start=window.training_start,
                    training_end=window.training_end,
                    test_start=window.test_start,
                    test_end=window.test_end,
                    optimized_params=window.optimized_params if window.optimized_params else {},
                    training_return_pct=window.training_return_pct,
                    training_sharpe=window.training_sharpe,
                    training_win_rate=window.training_win_rate,
                    training_trades=window.training_result.completed_trades if window.training_result else 0,
                    test_return_pct=window.test_return_pct,
                    test_sharpe=window.test_sharpe,
                    test_win_rate=window.test_win_rate,
                    test_trades=window.test_result.completed_trades if window.test_result else 0,
                    test_final_balance=window.test_result.final_balance if window.test_result else None,
                    optimization_results=window.optimization_results if window.optimization_results else []
                )
                self.db.add(window_record)
        
        # Create equity curve points
        for point in result.equity_curve:
            equity_point = WalkForwardEquityPoint(
                analysis_id=analysis.id,
                time=datetime.fromtimestamp(point["time"], tz=timezone.utc),
                balance=point["balance"],
                window_number=point.get("window_number")
            )
            self.db.add(equity_point)
        
        with self._transaction(error_message="Failed to save walk-forward windows and equity points"):
            logger.info(f"Saved {len(result.windows)} windows and {len(result.equity_curve)} equity points for analysis {analysis.id}")
        
        return analysis.id
    
    async def _async_save_walk_forward_analysis(
        self,
        user_id: UUID,
        result: Any,
        request: Any,
        execution_time_ms: Optional[int],
        candles_processed: Optional[int],
        name: Optional[str],
        label: Optional[str],
        keep_details: bool
    ) -> UUID:
        """Async implementation of save_walk_forward_analysis."""
        from datetime import datetime, timezone
        from sqlalchemy import select
        
        # Create main analysis record
        analysis = WalkForwardAnalysis(
            user_id=user_id,  # CRITICAL: User isolation
            name=name,
            label=label,
            symbol=result.symbol,
            strategy_type=result.strategy_type,
            overall_start_time=result.overall_start_time,
            overall_end_time=result.overall_end_time,
            training_period_days=result.training_period_days,
            test_period_days=result.test_period_days,
            step_size_days=result.step_size_days,
            window_type=result.window_type,
            total_windows=result.total_windows,
            leverage=request.leverage,
            risk_per_trade=request.risk_per_trade,
            fixed_amount=request.fixed_amount,
            initial_balance=result.initial_balance,
            params=request.params,
            optimization_enabled=request.optimize_params is not None,
            optimization_method=request.optimization_method if request.optimize_params else None,
            optimization_metric=request.optimization_metric if request.optimize_params else None,
            optimize_params=request.optimize_params if request.optimize_params else {},
            min_trades_guardrail=request.min_trades_guardrail if request.optimize_params else None,
            max_drawdown_cap=request.max_drawdown_cap if request.optimize_params else None,
            lottery_trade_threshold=request.lottery_trade_threshold if request.optimize_params else None,
            total_return_pct=result.total_return_pct,
            avg_window_return_pct=result.avg_window_return_pct,
            consistency_score=result.consistency_score,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown_pct=result.max_drawdown_pct,
            total_trades=result.total_trades,
            avg_win_rate=result.avg_win_rate,
            return_std_dev=result.return_std_dev,
            best_window=result.best_window,
            worst_window=result.worst_window,
            final_balance=result.equity_curve[-1]["balance"] if result.equity_curve else result.initial_balance,
            execution_time_ms=execution_time_ms,
            candles_processed=candles_processed,
            keep_details=keep_details,
            completed_at=datetime.now(timezone.utc)
        )
        
        self.db.add(analysis)
        await self.db.commit()
        await self.db.refresh(analysis)
        logger.info(f"Created walk-forward analysis {analysis.id} for user {user_id}")
        
        # Create window records
        if keep_details:
            for window in result.windows:
                window_record = WalkForwardWindow(
                    analysis_id=analysis.id,
                    window_number=window.window_number,
                    training_start=window.training_start,
                    training_end=window.training_end,
                    test_start=window.test_start,
                    test_end=window.test_end,
                    optimized_params=window.optimized_params if window.optimized_params else {},
                    training_return_pct=window.training_return_pct,
                    training_sharpe=window.training_sharpe,
                    training_win_rate=window.training_win_rate,
                    training_trades=window.training_result.completed_trades if window.training_result else 0,
                    test_return_pct=window.test_return_pct,
                    test_sharpe=window.test_sharpe,
                    test_win_rate=window.test_win_rate,
                    test_trades=window.test_result.completed_trades if window.test_result else 0,
                    test_final_balance=window.test_result.final_balance if window.test_result else None,
                    optimization_results=window.optimization_results if window.optimization_results else []
                )
                self.db.add(window_record)
        
        # Create equity curve points
        for point in result.equity_curve:
            equity_point = WalkForwardEquityPoint(
                analysis_id=analysis.id,
                time=datetime.fromtimestamp(point["time"], tz=timezone.utc),
                balance=point["balance"],
                window_number=point.get("window_number")
            )
            self.db.add(equity_point)
        
        await self.db.commit()
        logger.info(f"Saved {len(result.windows)} windows and {len(result.equity_curve)} equity points for analysis {analysis.id}")
        
        return analysis.id
    
    async def get_walk_forward_analysis(
        self,
        analysis_id: UUID,
        user_id: UUID
    ) -> Optional[WalkForwardAnalysis]:
        """Get walk-forward analysis by ID (with ownership check).
        
        CRITICAL: Only returns analysis if it belongs to the specified user.
        Returns None if analysis doesn't exist or belongs to different user.
        """
        if self._is_async:
            stmt = select(WalkForwardAnalysis).filter(
                WalkForwardAnalysis.id == analysis_id,
                WalkForwardAnalysis.user_id == user_id  # CRITICAL: User isolation
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        else:
            return self.db.query(WalkForwardAnalysis).filter(
                WalkForwardAnalysis.id == analysis_id,
                WalkForwardAnalysis.user_id == user_id  # CRITICAL: User isolation
            ).first()
    
    async def list_walk_forward_analyses(
        self,
        user_id: UUID,  # CRITICAL: Always filter by user_id
        limit: int = 50,
        offset: int = 0,
        symbol: Optional[str] = None,
        strategy_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> tuple[list[WalkForwardAnalysis], int]:
        """List walk-forward analyses with filters.
        
        CRITICAL: Only returns analyses belonging to the specified user.
        All queries MUST include user_id filter to prevent data leakage.
        
        Returns:
            Tuple of (analyses list, total count)
        """
        if self._is_async:
            return await self._async_list_walk_forward_analyses(
                user_id, limit, offset, symbol, strategy_type, start_date, end_date
            )
        else:
            return self._sync_list_walk_forward_analyses(
                user_id, limit, offset, symbol, strategy_type, start_date, end_date
            )
    
    def _sync_list_walk_forward_analyses(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
        symbol: Optional[str],
        strategy_type: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> tuple[list[WalkForwardAnalysis], int]:
        """Sync implementation of list_walk_forward_analyses."""
        # ALWAYS start with user_id filter
        query = self.db.query(WalkForwardAnalysis).filter(
            WalkForwardAnalysis.user_id == user_id  # CRITICAL: User isolation
        )
        
        # Apply additional filters
        if symbol:
            query = query.filter(WalkForwardAnalysis.symbol == symbol)
        if strategy_type:
            query = query.filter(WalkForwardAnalysis.strategy_type == strategy_type)
        if start_date:
            query = query.filter(WalkForwardAnalysis.overall_start_time >= start_date)
        if end_date:
            query = query.filter(WalkForwardAnalysis.overall_end_time <= end_date)
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        analyses = query.order_by(WalkForwardAnalysis.created_at.desc()).offset(offset).limit(limit).all()
        
        return analyses, total
    
    async def _async_list_walk_forward_analyses(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
        symbol: Optional[str],
        strategy_type: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> tuple[list[WalkForwardAnalysis], int]:
        """Async implementation of list_walk_forward_analyses."""
        from sqlalchemy import func as sql_func
        
        # ALWAYS start with user_id filter
        stmt = select(WalkForwardAnalysis).filter(
            WalkForwardAnalysis.user_id == user_id  # CRITICAL: User isolation
        )
        
        # Apply additional filters
        if symbol:
            stmt = stmt.filter(WalkForwardAnalysis.symbol == symbol)
        if strategy_type:
            stmt = stmt.filter(WalkForwardAnalysis.strategy_type == strategy_type)
        if start_date:
            stmt = stmt.filter(WalkForwardAnalysis.overall_start_time >= start_date)
        if end_date:
            stmt = stmt.filter(WalkForwardAnalysis.overall_end_time <= end_date)
        
        # Get total count
        count_stmt = select(sql_func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()
        
        # Get paginated results
        stmt = stmt.order_by(WalkForwardAnalysis.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        analyses = list(result.scalars().all())
        
        return analyses, total
    
    async def delete_walk_forward_analysis(
        self,
        analysis_id: UUID,
        user_id: UUID
    ) -> bool:
        """Delete walk-forward analysis (with ownership check).
        
        CRITICAL: Only deletes if analysis belongs to the specified user.
        Returns False if analysis doesn't exist or belongs to different user.
        """
        analysis = await self.get_walk_forward_analysis(analysis_id, user_id)
        if not analysis:
            return False
        
        if self._is_async:
            await self.db.delete(analysis)
            await self.db.commit()
        else:
            self.db.delete(analysis)
            with self._transaction(error_message=f"Failed to delete walk-forward analysis {analysis_id}"):
                logger.info(f"Deleted walk-forward analysis {analysis_id} for user {user_id}")
        
        return True
    
    async def get_walk_forward_equity_curve(
        self,
        analysis_id: UUID,
        user_id: UUID
    ) -> list[dict]:
        """Get equity curve points for an analysis.
        
        CRITICAL: Only returns equity curve if analysis belongs to the specified user.
        First verifies ownership before returning data.
        
        Returns:
            List of {"time": datetime, "balance": float}
        """
        # First verify ownership
        analysis = await self.get_walk_forward_analysis(analysis_id, user_id)
        if not analysis:
            return []
        
        if self._is_async:
            stmt = select(WalkForwardEquityPoint).filter(
                WalkForwardEquityPoint.analysis_id == analysis_id
            ).order_by(WalkForwardEquityPoint.time)
            result = await self.db.execute(stmt)
            points = result.scalars().all()
        else:
            points = self.db.query(WalkForwardEquityPoint).filter(
                WalkForwardEquityPoint.analysis_id == analysis_id
            ).order_by(WalkForwardEquityPoint.time).all()
        
        return [
            {
                "time": point.time,
                "balance": float(point.balance),
                "window_number": point.window_number
            }
            for point in points
        ]
    
    # ============================================
    # SYSTEM EVENT OPERATIONS
    # ============================================
    
    def create_system_event(
        self,
        event_type: str,
        event_level: str,
        message: str,
        strategy_id: Optional[UUID] = None,
        account_id: Optional[UUID] = None,
        event_metadata: Optional[dict] = None
    ) -> SystemEvent:
        """Create a system event (audit log entry).
        
        Args:
            event_type: Type of event (e.g., 'strategy_started', 'strategy_stopped')
            event_level: Event level ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
            message: Event message
            strategy_id: Optional strategy UUID
            account_id: Optional account UUID
            event_metadata: Optional additional metadata as dict
            
        Returns:
            SystemEvent model instance
        """
        event = SystemEvent(
            event_type=event_type,
            event_level=event_level,
            message=message,
            strategy_id=strategy_id,
            account_id=account_id,
            event_metadata=event_metadata or {}
        )
        self.db.add(event)
        with self._transaction(event, error_message="Failed to create system event"):
            pass
        return event
    
    def get_enforcement_events(
        self,
        user_id: UUID,
        account_id: Optional[UUID] = None,
        strategy_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[SystemEvent], int]:
        """Get risk enforcement events with filters (sync).
        
        Args:
            user_id: User UUID (required for user isolation)
            account_id: Optional account UUID filter
            strategy_id: Optional strategy UUID filter
            event_type: Optional event type filter (e.g., 'ORDER_BLOCKED', 'CIRCUIT_BREAKER_TRIGGERED')
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum number of events to return
            offset: Pagination offset
            
        Returns:
            Tuple of (list of SystemEvent instances, total count)
        """
        # Get strategies for user to filter events
        user_strategies = self.get_user_strategies(user_id)
        strategy_uuids = [s.id for s in user_strategies]
        
        # Get accounts for user to filter events
        user_accounts = self.get_user_accounts(user_id)
        account_uuids = [a.id for a in user_accounts]
        
        # Build query - filter by user's strategies and accounts
        query = self.db.query(SystemEvent).filter(
            (SystemEvent.strategy_id.in_(strategy_uuids)) | 
            (SystemEvent.account_id.in_(account_uuids))
        )
        
        # Apply filters
        if account_id:
            query = query.filter(SystemEvent.account_id == account_id)
        if strategy_id:
            query = query.filter(SystemEvent.strategy_id == strategy_id)
        if event_type:
            query = query.filter(SystemEvent.event_type == event_type)
        if start_date:
            query = query.filter(SystemEvent.created_at >= start_date)
        if end_date:
            query = query.filter(SystemEvent.created_at <= end_date)
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        events = query.order_by(SystemEvent.created_at.desc()).offset(offset).limit(limit).all()
        
        return events, total
    
    def get_strategy_events(
        self,
        strategy_id: UUID,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[SystemEvent]:
        """Get system events for a strategy (sync).
        
        Args:
            strategy_id: Strategy UUID
            event_type: Optional filter by event type
            limit: Maximum number of events to return
            
        Returns:
            List of SystemEvent instances, ordered by created_at descending
        """
        if self._is_async:
            raise RuntimeError("Use async_get_strategy_events() with AsyncSession")
        
        query = self.db.query(SystemEvent).filter(
            SystemEvent.strategy_id == strategy_id
        )
        
        if event_type:
            query = query.filter(SystemEvent.event_type == event_type)
        
        return query.order_by(SystemEvent.created_at.desc()).limit(limit).all()
    
    async def async_get_strategy_events(
        self,
        strategy_id: UUID,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[SystemEvent]:
        """Get system events for a strategy (async).
        
        Args:
            strategy_id: Strategy UUID
            event_type: Optional filter by event type
            limit: Maximum number of events to return
            
        Returns:
            List of SystemEvent instances, ordered by created_at descending
        """
        if not self._is_async:
            raise RuntimeError("Use get_strategy_events() with Session")
        
        from sqlalchemy import select
        query = select(SystemEvent).filter(
            SystemEvent.strategy_id == strategy_id
        )
        
        if event_type:
            query = query.filter(SystemEvent.event_type == event_type)
        
        query = query.order_by(SystemEvent.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        events = list(result.scalars().all())
        return events

    # ============================================================================
    # PARAMETER SENSITIVITY ANALYSIS METHODS
    # ============================================================================
    
    async def save_sensitivity_analysis(
        self,
        user_id: UUID,
        result: Any,  # SensitivityAnalysisResult from sensitivity_analysis.py
        request: Any,  # SensitivityAnalysisRequest from sensitivity_analysis.py
        name: Optional[str] = None
    ) -> UUID:
        """Save sensitivity analysis results to database.
        
        CRITICAL: Always sets user_id to ensure user isolation.
        
        Returns:
            UUID of saved analysis
        """
        if self._is_async:
            return await self._async_save_sensitivity_analysis(user_id, result, request, name)
        else:
            return self._sync_save_sensitivity_analysis(user_id, result, request, name)
    
    def _sync_save_sensitivity_analysis(
        self,
        user_id: UUID,
        result: Any,
        request: Any,
        name: Optional[str]
    ) -> UUID:
        """Sync implementation of save_sensitivity_analysis."""
        from datetime import datetime, timezone
        
        # Create main analysis record
        analysis = SensitivityAnalysis(
            user_id=user_id,  # CRITICAL: User isolation
            name=name or request.name,
            symbol=result.symbol,
            strategy_type=result.strategy_type,
            start_time=result.start_time,
            end_time=result.end_time,
            base_params=request.base_params,
            analyze_params=request.analyze_params,
            metric=request.metric,
            kline_interval=result.kline_interval,
            leverage=request.leverage,
            risk_per_trade=request.risk_per_trade,
            fixed_amount=request.fixed_amount,
            initial_balance=request.initial_balance,
            most_sensitive_param=result.most_sensitive_param,
            least_sensitive_param=result.least_sensitive_param,
            recommended_params=result.recommended_params,
            completed_at=datetime.now(timezone.utc)
        )
        
        self.db.add(analysis)
        with self._transaction(analysis, error_message="Failed to save sensitivity analysis"):
            logger.info(f"Created sensitivity analysis {analysis.id} for user {user_id}")
        
        # Create parameter result records
        for param_result in result.parameter_results:
            param_record = SensitivityParameterResult(
                analysis_id=analysis.id,
                parameter_name=param_result.parameter_name,
                base_value=param_result.base_value,
                tested_values=param_result.tested_values,
                sensitivity_score=param_result.sensitivity_score,
                optimal_value=param_result.optimal_value,
                worst_value=param_result.worst_value,
                impact_range=param_result.impact_range,
                impact_range_display=param_result.impact_range_display,
                results=param_result.results  # Store full results as JSONB
            )
            self.db.add(param_record)
        
        with self._transaction(error_message="Failed to save sensitivity parameter results"):
            logger.info(f"Saved {len(result.parameter_results)} parameter results for analysis {analysis.id}")
        
        return analysis.id
    
    async def _async_save_sensitivity_analysis(
        self,
        user_id: UUID,
        result: Any,
        request: Any,
        name: Optional[str]
    ) -> UUID:
        """Async implementation of save_sensitivity_analysis."""
        from datetime import datetime, timezone
        
        # Create main analysis record
        analysis = SensitivityAnalysis(
            user_id=user_id,  # CRITICAL: User isolation
            name=name or request.name,
            symbol=result.symbol,
            strategy_type=result.strategy_type,
            start_time=result.start_time,
            end_time=result.end_time,
            base_params=request.base_params,
            analyze_params=request.analyze_params,
            metric=request.metric,
            kline_interval=result.kline_interval,
            leverage=request.leverage,
            risk_per_trade=request.risk_per_trade,
            fixed_amount=request.fixed_amount,
            initial_balance=request.initial_balance,
            most_sensitive_param=result.most_sensitive_param,
            least_sensitive_param=result.least_sensitive_param,
            recommended_params=result.recommended_params,
            completed_at=datetime.now(timezone.utc)
        )
        
        self.db.add(analysis)
        await self.db.commit()
        await self.db.refresh(analysis)
        logger.info(f"Created sensitivity analysis {analysis.id} for user {user_id}")
        
        # Create parameter result records
        for param_result in result.parameter_results:
            param_record = SensitivityParameterResult(
                analysis_id=analysis.id,
                parameter_name=param_result.parameter_name,
                base_value=param_result.base_value,
                tested_values=param_result.tested_values,
                sensitivity_score=param_result.sensitivity_score,
                optimal_value=param_result.optimal_value,
                worst_value=param_result.worst_value,
                impact_range=param_result.impact_range,
                impact_range_display=param_result.impact_range_display,
                results=param_result.results  # Store full results as JSONB
            )
            self.db.add(param_record)
        
        await self.db.commit()
        logger.info(f"Saved {len(result.parameter_results)} parameter results for analysis {analysis.id}")
        
        return analysis.id
    
    async def get_sensitivity_analysis(
        self,
        analysis_id: UUID,
        user_id: UUID
    ) -> Optional[SensitivityAnalysis]:
        """Get sensitivity analysis by ID (with ownership check).
        
        CRITICAL: Only returns analysis if it belongs to the specified user.
        Returns None if analysis doesn't exist or belongs to different user.
        """
        if self._is_async:
            stmt = select(SensitivityAnalysis).filter(
                SensitivityAnalysis.id == analysis_id,
                SensitivityAnalysis.user_id == user_id  # CRITICAL: User isolation
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        else:
            return self.db.query(SensitivityAnalysis).filter(
                SensitivityAnalysis.id == analysis_id,
                SensitivityAnalysis.user_id == user_id  # CRITICAL: User isolation
            ).first()
    
    async def list_sensitivity_analyses(
        self,
        user_id: UUID,  # CRITICAL: Always filter by user_id
        limit: int = 50,
        offset: int = 0,
        symbol: Optional[str] = None,
        strategy_type: Optional[str] = None
    ) -> tuple[List[SensitivityAnalysis], int]:
        """List sensitivity analyses for a user with pagination.
        
        CRITICAL: Always filters by user_id to ensure user isolation.
        
        Returns:
            Tuple of (list of analyses, total count)
        """
        if self._is_async:
            return await self._async_list_sensitivity_analyses(user_id, limit, offset, symbol, strategy_type)
        else:
            return self._sync_list_sensitivity_analyses(user_id, limit, offset, symbol, strategy_type)
    
    def _sync_list_sensitivity_analyses(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
        symbol: Optional[str],
        strategy_type: Optional[str]
    ) -> tuple[List[SensitivityAnalysis], int]:
        """Sync implementation of list_sensitivity_analyses."""
        query = self.db.query(SensitivityAnalysis).filter(
            SensitivityAnalysis.user_id == user_id  # CRITICAL: User isolation
        )
        
        if symbol:
            query = query.filter(SensitivityAnalysis.symbol == symbol)
        if strategy_type:
            query = query.filter(SensitivityAnalysis.strategy_type == strategy_type)
        
        total = query.count()
        analyses = query.order_by(SensitivityAnalysis.created_at.desc()).offset(offset).limit(limit).all()
        
        return list(analyses), total
    
    async def _async_list_sensitivity_analyses(
        self,
        user_id: UUID,
        limit: int,
        offset: int,
        symbol: Optional[str],
        strategy_type: Optional[str]
    ) -> tuple[List[SensitivityAnalysis], int]:
        """Async implementation of list_sensitivity_analyses."""
        query = select(SensitivityAnalysis).filter(
            SensitivityAnalysis.user_id == user_id  # CRITICAL: User isolation
        )
        
        if symbol:
            query = query.filter(SensitivityAnalysis.symbol == symbol)
        if strategy_type:
            query = query.filter(SensitivityAnalysis.strategy_type == strategy_type)
        
        # Get total count
        count_query = select(func.count()).select_from(SensitivityAnalysis).filter(
            SensitivityAnalysis.user_id == user_id
        )
        if symbol:
            count_query = count_query.filter(SensitivityAnalysis.symbol == symbol)
        if strategy_type:
            count_query = count_query.filter(SensitivityAnalysis.strategy_type == strategy_type)
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Get paginated results
        query = query.order_by(SensitivityAnalysis.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        analyses = list(result.scalars().all())
        
        return analyses, total
    
    async def delete_sensitivity_analysis(
        self,
        analysis_id: UUID,
        user_id: UUID
    ) -> bool:
        """Delete sensitivity analysis (with ownership check).
        
        CRITICAL: Only deletes if analysis belongs to the specified user.
        Returns True if deleted, False if not found or doesn't belong to user.
        """
        analysis = await self.get_sensitivity_analysis(analysis_id, user_id)
        if not analysis:
            return False
        
        if self._is_async:
            await self.db.delete(analysis)
            await self.db.commit()
        else:
            self.db.delete(analysis)
            with self._transaction(error_message=f"Failed to delete sensitivity analysis {analysis_id}"):
                pass
        
        logger.info(f"Deleted sensitivity analysis {analysis_id} for user {user_id}")
        return True
    
    # ============================================
    # STRATEGY PARAMETER HISTORY OPERATIONS
    # ============================================
    
    def create_parameter_history(
        self,
        strategy_uuid: UUID,
        user_id: UUID,
        old_params: dict,
        new_params: dict,
        changed_params: dict,
        reason: str,
        status: str = "applied",
        failure_reason: Optional[str] = None,
        performance_before: Optional[dict] = None,
        tuning_run_id: Optional[str] = None,
        strategy_label: Optional[str] = None
    ) -> StrategyParameterHistory:
        """Create a parameter history record.
        
        Args:
            strategy_uuid: Strategy UUID
            user_id: User ID
            old_params: Old parameter dictionary
            new_params: New parameter dictionary
            changed_params: Only changed parameters
            reason: Reason for change (e.g., "auto_tuning", "manual")
            status: Status (applied|rolled_back|aborted|failed)
            failure_reason: Error message if failed
            performance_before: Performance metrics before change
            tuning_run_id: Tuning run identifier
            strategy_label: Optional human-readable strategy label
            
        Returns:
            StrategyParameterHistory instance
        """
        history = StrategyParameterHistory(
            strategy_uuid=strategy_uuid,
            user_id=user_id,
            strategy_label=strategy_label,
            old_params=old_params,
            new_params=new_params,
            changed_params=changed_params,
            reason=reason,
            status=status,
            failure_reason=failure_reason,
            performance_before=performance_before,
            tuning_run_id=tuning_run_id
        )
        self.db.add(history)
        with self._transaction(history, error_message=f"Failed to create parameter history for {strategy_uuid}"):
            logger.info(f"Created parameter history record {history.id} for strategy {strategy_uuid}")
        return history
    
    async def async_create_parameter_history(
        self,
        strategy_uuid: UUID,
        user_id: UUID,
        old_params: dict,
        new_params: dict,
        changed_params: dict,
        reason: str,
        status: str = "applied",
        failure_reason: Optional[str] = None,
        performance_before: Optional[dict] = None,
        tuning_run_id: Optional[str] = None,
        strategy_label: Optional[str] = None
    ) -> StrategyParameterHistory:
        """Async version of create_parameter_history."""
        history = StrategyParameterHistory(
            strategy_uuid=strategy_uuid,
            user_id=user_id,
            strategy_label=strategy_label,
            old_params=old_params,
            new_params=new_params,
            changed_params=changed_params,
            reason=reason,
            status=status,
            failure_reason=failure_reason,
            performance_before=performance_before,
            tuning_run_id=tuning_run_id
        )
        self.db.add(history)
        await self.db.commit()
        await self.db.refresh(history)
        logger.info(f"Created parameter history record {history.id} for strategy {strategy_uuid}")
        return history
    
    def get_last_parameter_change(
        self,
        strategy_uuid: UUID,
        user_id: UUID,
        reason: Optional[str] = None,
        status: Optional[str] = None
    ) -> Optional[StrategyParameterHistory]:
        """Get last parameter change for a strategy.
        
        Args:
            strategy_uuid: Strategy UUID
            user_id: User ID
            reason: Optional reason filter (e.g., "auto_tuning")
            status: Optional status filter (e.g., "applied")
            
        Returns:
            Last StrategyParameterHistory record, or None
        """
        if self._is_async:
            raise RuntimeError("Use async_get_last_parameter_change() with AsyncSession")
        
        query = self.db.query(StrategyParameterHistory).filter(
            StrategyParameterHistory.strategy_uuid == strategy_uuid,
            StrategyParameterHistory.user_id == user_id
        )
        
        if reason:
            query = query.filter(StrategyParameterHistory.reason == reason)
        if status:
            query = query.filter(StrategyParameterHistory.status == status)
        
        return query.order_by(StrategyParameterHistory.created_at.desc()).first()
    
    async def async_get_last_parameter_change(
        self,
        strategy_uuid: UUID,
        user_id: UUID,
        reason: Optional[str] = None,
        status: Optional[str] = None
    ) -> Optional[StrategyParameterHistory]:
        """Async version of get_last_parameter_change."""
        stmt = select(StrategyParameterHistory).filter(
            StrategyParameterHistory.strategy_uuid == strategy_uuid,
            StrategyParameterHistory.user_id == user_id
        )
        
        if reason:
            stmt = stmt.filter(StrategyParameterHistory.reason == reason)
        if status:
            stmt = stmt.filter(StrategyParameterHistory.status == status)
        
        stmt = stmt.order_by(StrategyParameterHistory.created_at.desc()).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    def list_parameter_history(
        self,
        strategy_uuid: UUID,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[StrategyParameterHistory], int]:
        """List parameter history for a strategy with pagination.
        
        Args:
            strategy_uuid: Strategy UUID
            user_id: User ID
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            Tuple of (list of history records, total count)
        """
        if self._is_async:
            raise RuntimeError("Use async_list_parameter_history() with AsyncSession")
        else:
            return self._sync_list_parameter_history(strategy_uuid, user_id, limit, offset)
    
    async def async_list_parameter_history(
        self,
        strategy_uuid: UUID,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[StrategyParameterHistory], int]:
        """Async version of list_parameter_history."""
        if not self._is_async:
            raise RuntimeError("Use list_parameter_history() with Session")
        return await self._async_list_parameter_history(strategy_uuid, user_id, limit, offset)
    
    def _sync_list_parameter_history(
        self,
        strategy_uuid: UUID,
        user_id: UUID,
        limit: int,
        offset: int
    ) -> tuple[List[StrategyParameterHistory], int]:
        """Sync version of list_parameter_history."""
        query = self.db.query(StrategyParameterHistory).filter(
            StrategyParameterHistory.strategy_uuid == strategy_uuid,
            StrategyParameterHistory.user_id == user_id
        )
        
        total = query.count()
        records = query.order_by(
            StrategyParameterHistory.created_at.desc()
        ).offset(offset).limit(limit).all()
        
        return records, total
    
    async def _async_list_parameter_history(
        self,
        strategy_uuid: UUID,
        user_id: UUID,
        limit: int,
        offset: int
    ) -> tuple[List[StrategyParameterHistory], int]:
        """Async version of list_parameter_history."""
        # Count query
        count_stmt = select(func.count()).select_from(StrategyParameterHistory).filter(
            StrategyParameterHistory.strategy_uuid == strategy_uuid,
            StrategyParameterHistory.user_id == user_id
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar()
        
        # Data query
        stmt = select(StrategyParameterHistory).filter(
            StrategyParameterHistory.strategy_uuid == strategy_uuid,
            StrategyParameterHistory.user_id == user_id
        ).order_by(
            StrategyParameterHistory.created_at.desc()
        ).offset(offset).limit(limit)
        
        result = await self.db.execute(stmt)
        records = list(result.scalars().all())
        
        return records, total
    
    def update_parameter_history(
        self,
        history_id: UUID,
        performance_after: Optional[dict] = None,
        status: Optional[str] = None
    ) -> Optional[StrategyParameterHistory]:
        """Update parameter history record.
        
        Args:
            history_id: History record ID
            performance_after: Performance metrics after change
            status: Updated status
            
        Returns:
            Updated StrategyParameterHistory, or None if not found
        """
        if self._is_async:
            raise RuntimeError("Use async_update_parameter_history() with AsyncSession")
        
        history = self.db.query(StrategyParameterHistory).filter(
            StrategyParameterHistory.id == history_id
        ).first()
        
        if not history:
            return None
        
        if performance_after is not None:
            history.performance_after = performance_after
            from datetime import datetime, timezone
            history.performance_after_updated_at = datetime.now(timezone.utc)
        
        if status is not None:
            history.status = status
        
        with self._transaction(history, error_message=f"Failed to update parameter history {history_id}"):
            pass
        
        return history
    
    async def async_update_parameter_history(
        self,
        history_id: UUID,
        performance_after: Optional[dict] = None,
        status: Optional[str] = None
    ) -> Optional[StrategyParameterHistory]:
        """Async version of update_parameter_history."""
        stmt = select(StrategyParameterHistory).filter(
            StrategyParameterHistory.id == history_id
        )
        result = await self.db.execute(stmt)
        history = result.scalar_one_or_none()
        
        if not history:
            return None
        
        if performance_after is not None:
            history.performance_after = performance_after
            from datetime import datetime, timezone
            history.performance_after_updated_at = datetime.now(timezone.utc)
        
        if status is not None:
            history.status = status
        
        await self.db.commit()
        await self.db.refresh(history)
        
        return history

