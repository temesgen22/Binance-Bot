"""
Database service layer for CRUD operations.
Provides high-level database operations with proper error handling.
"""
from __future__ import annotations

from typing import Optional, List
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
        try:
            self.db.commit()
            self.db.refresh(user)
            logger.info(f"Created user: {username}")
            return user
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create user {username}: {e}")
            raise
    
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
        
        try:
            self.db.commit()
            self.db.refresh(user)
            return user
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update user {user_id}: {e}")
            raise
    
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
        try:
            self.db.commit()
            self.db.refresh(account)
            logger.info(f"Created account {account_id} for user {user_id}")
            return account
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create account {account_id}: {e}")
            raise
    
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
        """Get account by user_id and account_id."""
        return self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.account_id == account_id,
            Account.is_active == True
        ).first()
    
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
        
        try:
            self.db.commit()
            self.db.refresh(account)
            return account
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update account {account_id}: {e}")
            raise
    
    def delete_account(self, user_id: UUID, account_id: str) -> bool:
        """Delete (deactivate) an account."""
        account = self.get_account_by_id(user_id, account_id)
        if not account:
            return False
        
        try:
            # Soft delete: set is_active to False
            account.is_active = False
            self.db.commit()
            logger.info(f"Deactivated account {account_id} for user {user_id}")
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete account {account_id}: {e}")
            raise
    
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
        try:
            self.db.commit()
            self.db.refresh(strategy)
            logger.info(f"Created strategy {strategy_id} for user {user_id}")
            return strategy
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create strategy {strategy_id}: {e}")
            raise
    
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
        
        try:
            self.db.commit()
            self.db.refresh(strategy)
            return strategy
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update strategy {strategy_id}: {e}")
            raise
    
    def delete_strategy(self, user_id: UUID, strategy_id: str) -> bool:
        """Delete a strategy."""
        strategy = self.get_strategy(user_id, strategy_id)
        if not strategy:
            return False
        
        try:
            self.db.delete(strategy)
            self.db.commit()
            logger.info(f"Deleted strategy {strategy_id} for user {user_id}")
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete strategy {strategy_id}: {e}")
            raise
    
    # ============================================
    # TRADE OPERATIONS
    # ============================================
    
    def create_trade(self, trade_data: dict) -> Trade:
        """Create a new trade record."""
        trade = Trade(**trade_data)
        self.db.add(trade)
        try:
            self.db.commit()
            self.db.refresh(trade)
            return trade
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create trade: {e}")
            raise
    
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
    
    # ============================================
    # TRADE PAIR OPERATIONS
    # ============================================
    
    def create_trade_pair(self, pair_data: dict) -> TradePair:
        """Create a new trade pair."""
        pair = TradePair(**pair_data)
        self.db.add(pair)
        try:
            self.db.commit()
            self.db.refresh(pair)
            return pair
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create trade pair: {e}")
            raise
    
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
        try:
            self.db.commit()
            self.db.refresh(backtest)
            return backtest
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create backtest: {e}")
            raise
    
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

