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
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from loguru import logger

from app.core.database import get_db_session
from app.models.db_models import (
    User, Role, Account, Strategy, Trade, TradePair,
    Backtest, BacktestTrade, StrategyMetric, SystemEvent,
    WalkForwardAnalysis, WalkForwardWindow, WalkForwardEquityPoint
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
        """Get all strategies for a user (sync)."""
        if self._is_async:
            raise RuntimeError("Use async_get_user_strategies() with AsyncSession")
        return self.db.query(Strategy).filter(
            Strategy.user_id == user_id
        ).all()
    
    async def async_get_user_strategies(self, user_id: UUID) -> List[Strategy]:
        """Get all strategies for a user (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_user_strategies() with Session")
        result = await self.db.execute(
            select(Strategy).filter(Strategy.user_id == user_id)
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
        """Get a specific strategy by user and strategy_id (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_strategy() with Session")
        result = await self.db.execute(
            select(Strategy).filter(
                Strategy.user_id == user_id,
                Strategy.strategy_id == strategy_id
            )
        )
        return result.scalar_one_or_none()
    
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
        limit: int = 100
    ) -> List[Trade]:
        """Get trades for a user, optionally filtered by strategy (async)."""
        if not self._is_async:
            raise RuntimeError("Use get_user_trades() with Session")
        stmt = select(Trade).filter(Trade.user_id == user_id)
        
        if strategy_id:
            stmt = stmt.filter(Trade.strategy_id == strategy_id)
        
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

