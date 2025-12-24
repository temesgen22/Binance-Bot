"""
Database service layer for CRUD operations.
Provides high-level database operations with proper error handling.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional, List, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from loguru import logger

from app.core.database import get_db_session
from app.models.db_models import (
    User, Role, Account, Strategy, Trade, TradePair,
    Backtest, BacktestTrade, StrategyMetric, SystemEvent
)


class DatabaseService:
    """Service layer for database operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
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
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.db.query(User).filter(User.email == email).first()
    
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
        is_default: bool = False
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
            is_default=is_default
        )
        self.db.add(account)
        with self._transaction(account, error_message=f"Failed to create account {account_id}"):
            logger.info(f"Created account {account_id} for user {user_id}")
        return account
    
    def get_user_accounts(self, user_id: UUID) -> List[Account]:
        """Get all accounts for a user."""
        return self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.is_active == True
        ).all()
    
    def get_default_account(self, user_id: UUID) -> Optional[Account]:
        """Get user's default account."""
        return self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.is_default == True,
            Account.is_active == True
        ).first()
    
    def get_account_by_id(self, user_id: UUID, account_id: str) -> Optional[Account]:
        """Get account by user_id and account_id.
        
        Note: account_id is the string identifier (e.g., 'main1'), not the UUID primary key (Account.id).
        The query is case-insensitive to handle any case variations.
        
        Args:
            user_id: User UUID
            account_id: Account string identifier (e.g., 'main1'), NOT the UUID primary key
            
        Returns:
            Account if found and active, None otherwise
        """
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
    
    def delete_account(self, user_id: UUID, account_id: str) -> bool:
        """Delete (deactivate) an account."""
        account = self.get_account_by_id(user_id, account_id)
        if not account:
            return False
        
        # Soft delete: set is_active to False
        account.is_active = False
        with self._transaction(error_message=f"Failed to delete account {account_id}"):
            logger.info(f"Deactivated account {account_id} for user {user_id}")
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
        """Get all strategies for a user."""
        return self.db.query(Strategy).filter(
            Strategy.user_id == user_id
        ).all()
    
    def get_strategy(self, user_id: UUID, strategy_id: str) -> Optional[Strategy]:
        """Get a specific strategy by user and strategy_id."""
        return self.db.query(Strategy).filter(
            Strategy.user_id == user_id,
            Strategy.strategy_id == strategy_id
        ).first()
    
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
        
        for key, value in updates.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)
        
        with self._transaction(strategy, error_message=f"Failed to update strategy {strategy_id}"):
            pass
        return strategy
    
    def delete_strategy(self, user_id: UUID, strategy_id: str) -> bool:
        """Delete a strategy."""
        strategy = self.get_strategy(user_id, strategy_id)
        if not strategy:
            return False
        
        self.db.delete(strategy)
        with self._transaction(error_message=f"Failed to delete strategy {strategy_id}"):
            logger.info(f"Deleted strategy {strategy_id} for user {user_id}")
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
        """Get trades for a user, optionally filtered by strategy."""
        query = self.db.query(Trade).filter(Trade.user_id == user_id)
        
        if strategy_id:
            query = query.filter(Trade.strategy_id == strategy_id)
        
        return query.order_by(Trade.timestamp.desc()).limit(limit).all()
    
    def get_user_trades_batch(
        self,
        user_id: UUID,
        strategy_ids: List[UUID],
        limit: int = 10000
    ) -> List[Trade]:
        """Get trades for multiple strategies in a single query (optimizes N+1 problem).
        
        Args:
            user_id: User ID
            strategy_ids: List of strategy UUIDs to fetch trades for
            limit: Maximum total trades to return (across all strategies)
        
        Returns:
            List of Trade objects for all specified strategies
        """
        if not strategy_ids:
            return []
        
        query = self.db.query(Trade).filter(
            Trade.user_id == user_id,
            Trade.strategy_id.in_(strategy_ids)
        )
        
        return query.order_by(Trade.timestamp.desc()).limit(limit).all()
    
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

