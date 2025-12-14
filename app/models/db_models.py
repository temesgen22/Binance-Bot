"""
SQLAlchemy database models for PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, BigInteger, CheckConstraint, Column, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, JSON, Index, func, Table
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# ============================================
# ASSOCIATION TABLES
# ============================================

# Many-to-many relationship between users and roles
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Index("idx_user_roles_user_id", "user_id"),
    Index("idx_user_roles_role_id", "role_id"),
)


# ============================================
# USER MANAGEMENT
# ============================================

class User(Base):
    """User account for multi-user support."""
    __tablename__ = "users"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)  # bcrypt hash
    full_name = Column(String(255))
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_verified = Column(Boolean, nullable=False, default=False)  # Email verification
    is_superuser = Column(Boolean, nullable=False, default=False)  # Super admin
    
    # Security
    last_login = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True))  # Account lockout
    
    # Metadata (renamed from 'metadata' to avoid SQLAlchemy reserved name)
    user_metadata = Column(JSONB, default=lambda: {})  # Use lambda to avoid shared mutable default
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_activity_at = Column(DateTime(timezone=True))

    # Relationships
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    strategies = relationship("Strategy", back_populates="user", cascade="all, delete-orphan")
    # Positions are runtime state - stored in Redis only, derived from trade_pairs when needed
    backtests = relationship("Backtest", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    api_tokens = relationship("APIToken", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("username ~ '^[a-z0-9_-]+$'", name="users_username_check"),
        CheckConstraint("email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}$'", name="users_email_check"),
    )


class Role(Base):
    """Role for role-based access control (RBAC) - simplified for v1."""
    __tablename__ = "roles"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(50), unique=True, nullable=False, index=True)  # 'admin', 'user', 'read_only'
    description = Column(Text)
    is_system = Column(Boolean, nullable=False, default=False)  # System roles cannot be deleted
    
    # Permissions (JSONB for flexibility - can evolve to permissions table later)
    permissions = Column(JSONB, nullable=False, default=lambda: {})  # Use lambda to avoid shared mutable default
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    users = relationship("User", secondary=user_roles, back_populates="roles")
    # Optional: permissions_rel for future granular permissions
    # permissions_rel = relationship("Permission", back_populates="role", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("name ~ '^[a-z0-9_-]+$'", name="roles_name_check"),
    )


# Permission table - Optional for v1, can be added later for granular permissions
# For v1, use permissions JSONB on roles table instead
# 
# class Permission(Base):
#     """Granular permissions for roles (optional for v1)."""
#     __tablename__ = "permissions"
#     ...


class UserSession(Base):
    """User session management."""
    __tablename__ = "user_sessions"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Session details
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(Text)
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="sessions")


class APIToken(Base):
    """API tokens for programmatic access."""
    __tablename__ = "api_tokens"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Token details
    token_name = Column(String(255), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)  # Hashed token
    token_prefix = Column(String(20), nullable=False)  # First few chars for identification
    
    # Permissions
    scopes = Column(JSONB, nullable=False, default=lambda: [])  # List of allowed scopes - use lambda to avoid shared mutable default
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_used_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), index=True)

    # Relationships
    user = relationship("User", back_populates="api_tokens")


# ============================================
# BINANCE ACCOUNTS (Per-User)
# ============================================

class Account(Base):
    """Exchange account configuration (per-user)."""
    __tablename__ = "accounts"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String(50), nullable=False, index=True)  # User's local account identifier
    name = Column(String(255))
    exchange_platform = Column(String(50), nullable=False, default="binance", index=True)  # Exchange platform name (binance, bybit, etc.)
    api_key_encrypted = Column(Text, nullable=False)
    api_secret_encrypted = Column(Text, nullable=False)
    testnet = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_default = Column(Boolean, nullable=False, default=False)  # Default account for user
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_used_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="accounts")
    strategies = relationship("Strategy", back_populates="account", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("account_id ~ '^[a-z0-9_-]+$'", name="accounts_account_id_check"),
        # Ensure account_id is unique per user
        Index("idx_accounts_user_account_id", "user_id", "account_id", unique=True),
    )


class Strategy(Base):
    """Trading strategy configuration and state (per-user)."""
    __tablename__ = "strategies"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String(100), nullable=False, index=True)  # User's local strategy identifier
    name = Column(String(255), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    strategy_type = Column(String(50), nullable=False, index=True)

    # Risk Management
    leverage = Column(Integer, nullable=False)
    risk_per_trade = Column(Numeric(10, 6), nullable=False)
    fixed_amount = Column(Numeric(20, 8))
    max_positions = Column(Integer, nullable=False, default=1)

    # Strategy Parameters
    params = Column(JSONB, nullable=False, default=lambda: {})  # Use lambda to avoid shared mutable default

    # Account Association (user's Binance account)
    account_id = Column(PGUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Status
    status = Column(String(20), nullable=False, default="stopped", index=True)
    last_signal = Column(String(10))

    # Current Position State
    entry_price = Column(Numeric(20, 8))
    current_price = Column(Numeric(20, 8))
    position_size = Column(Numeric(20, 8))
    position_side = Column(String(10), index=True)
    unrealized_pnl = Column(Numeric(20, 8))

    # Metadata
    meta = Column(JSONB, default=lambda: {})  # Use lambda to avoid shared mutable default

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_trade_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    stopped_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="strategies")
    account = relationship("Account", back_populates="strategies")
    trades = relationship("Trade", back_populates="strategy", cascade="all, delete-orphan")
    trade_pairs = relationship("TradePair", back_populates="strategy", cascade="all, delete-orphan")
    metrics = relationship("StrategyMetric", back_populates="strategy", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("leverage >= 1 AND leverage <= 50", name="strategies_leverage_check"),
        CheckConstraint("risk_per_trade > 0 AND risk_per_trade < 1", name="strategies_risk_check"),
        CheckConstraint("max_positions >= 1 AND max_positions <= 5", name="strategies_max_positions_check"),
        CheckConstraint("status IN ('stopped', 'running', 'error')", name="strategies_status_check"),
        CheckConstraint("position_side IS NULL OR position_side IN ('LONG', 'SHORT')", name="strategies_position_side_check"),
        CheckConstraint("last_signal IS NULL OR last_signal IN ('BUY', 'SELL', 'HOLD')", name="strategies_last_signal_check"),
        Index("idx_strategies_params", "params", postgresql_using="gin"),
        # Ensure strategy_id is unique per user
        Index("idx_strategies_user_strategy_id", "user_id", "strategy_id", unique=True),
    )


class Trade(Base):
    """Live trading order execution record."""
    __tablename__ = "trades"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id = Column(PGUUID(as_uuid=True), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # Denormalized for performance

    # Order Identification
    order_id = Column(BigInteger, nullable=False, index=True)  # Binance order IDs are 64-bit
    client_order_id = Column(String(100))
    symbol = Column(String(20), nullable=False, index=True)
    
    # Relationships
    user = relationship("User")

    # Order Details
    side = Column(String(10), nullable=False)
    order_type = Column(String(20))
    status = Column(String(20), nullable=False, index=True)

    # Pricing
    price = Column(Numeric(20, 8), nullable=False)
    avg_price = Column(Numeric(20, 8))
    executed_qty = Column(Numeric(20, 8), nullable=False)

    # Financial Details
    notional_value = Column(Numeric(20, 8))
    cummulative_quote_qty = Column(Numeric(20, 8))
    initial_margin = Column(Numeric(20, 8))
    commission = Column(Numeric(20, 8))
    commission_asset = Column(String(10))
    realized_pnl = Column(Numeric(20, 8))

    # Position Details
    position_side = Column(String(10), index=True)
    leverage = Column(Integer)
    margin_type = Column(String(20))

    # Strategy Context
    exit_reason = Column(String(50), index=True)

    # Timestamps
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    update_time = Column(DateTime(timezone=True))

    # Additional Binance Fields
    time_in_force = Column(String(10))
    working_type = Column(String(20))
    stop_price = Column(Numeric(20, 8))

    # Metadata
    meta = Column(JSONB, default=lambda: {})  # Use lambda to avoid shared mutable default

    # Relationships
    strategy = relationship("Strategy", back_populates="trades")
    entry_pairs = relationship("TradePair", foreign_keys="TradePair.entry_trade_id", back_populates="entry_trade")
    exit_pairs = relationship("TradePair", foreign_keys="TradePair.exit_trade_id", back_populates="exit_trade")

    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name="trades_side_check"),
        CheckConstraint("position_side IS NULL OR position_side IN ('LONG', 'SHORT')", name="trades_position_side_check"),
        Index("idx_trades_strategy_timestamp", "strategy_id", "timestamp", postgresql_ops={"timestamp": "DESC"}),
        Index("idx_trades_user_timestamp", "user_id", "timestamp", postgresql_ops={"timestamp": "DESC"}),
        # Prevent duplicate inserts from WebSocket retries
        Index("idx_trades_strategy_order_id", "strategy_id", "order_id", unique=True),
    )


class TradePair(Base):
    """Entry/Exit trade matching for PnL calculation."""
    __tablename__ = "trade_pairs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id = Column(PGUUID(as_uuid=True), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # Denormalized for performance

    # Entry Trade
    entry_trade_id = Column(PGUUID(as_uuid=True), ForeignKey("trades.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_price = Column(Numeric(20, 8), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False, index=True)
    entry_side = Column(String(10), nullable=False)
    position_side = Column(String(10), nullable=False)

    # Exit Trade
    exit_trade_id = Column(PGUUID(as_uuid=True), ForeignKey("trades.id", ondelete="SET NULL"))
    exit_price = Column(Numeric(20, 8))
    exit_time = Column(DateTime(timezone=True))
    exit_reason = Column(String(50))

    # PnL Calculation
    pnl = Column(Numeric(20, 8))
    net_pnl = Column(Numeric(20, 8))
    entry_fee = Column(Numeric(20, 8))
    exit_fee = Column(Numeric(20, 8))

    # Status
    is_open = Column(Boolean, nullable=False, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at = Column(DateTime(timezone=True))

    # Relationships
    strategy = relationship("Strategy", back_populates="trade_pairs")
    user = relationship("User")
    entry_trade = relationship("Trade", foreign_keys=[entry_trade_id], back_populates="entry_pairs")
    exit_trade = relationship("Trade", foreign_keys=[exit_trade_id], back_populates="exit_pairs")

    __table_args__ = (
        CheckConstraint("entry_side IN ('BUY', 'SELL')", name="trade_pairs_entry_side_check"),
        CheckConstraint("position_side IN ('LONG', 'SHORT')", name="trade_pairs_position_side_check"),
        Index("idx_trade_pairs_strategy_open", "strategy_id", "is_open"),
    )


class Backtest(Base):
    """Backtesting execution and results (per-user)."""
    __tablename__ = "backtests"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # User-friendly identification
    name = Column(String(255))  # e.g., "BTC 1m EMA 8/21 – Jan2025"
    label = Column(String(255))  # Optional label for UI organization

    # Configuration
    symbol = Column(String(20), nullable=False, index=True)
    strategy_type = Column(String(50), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False)
    leverage = Column(Integer, nullable=False)
    risk_per_trade = Column(Numeric(10, 6), nullable=False)
    initial_balance = Column(Numeric(20, 8), nullable=False)

    # Strategy Parameters
    params = Column(JSONB, nullable=False, default=lambda: {})  # Use lambda to avoid shared mutable default
    
    # Retention settings
    keep_details = Column(Boolean, nullable=False, default=True)  # Whether to keep backtest_trades

    # Results
    total_trades = Column(Integer, nullable=False, default=0)
    completed_trades = Column(Integer, nullable=False, default=0)
    winning_trades = Column(Integer, nullable=False, default=0)
    losing_trades = Column(Integer, nullable=False, default=0)
    total_pnl = Column(Numeric(20, 8), nullable=False, default=0)
    win_rate = Column(Numeric(5, 2), nullable=False, default=0)
    avg_profit_per_trade = Column(Numeric(20, 8), nullable=False, default=0)
    largest_win = Column(Numeric(20, 8))
    largest_loss = Column(Numeric(20, 8))
    max_drawdown = Column(Numeric(20, 8))
    max_drawdown_pct = Column(Numeric(5, 2))
    final_balance = Column(Numeric(20, 8))
    roi = Column(Numeric(10, 4))

    # Execution Metadata
    execution_time_ms = Column(Integer)
    candles_processed = Column(Integer)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="backtests")
    trades = relationship("BacktestTrade", back_populates="backtest", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("leverage >= 1 AND leverage <= 50", name="backtests_leverage_check"),
        CheckConstraint("risk_per_trade > 0 AND risk_per_trade < 1", name="backtests_risk_check"),
        Index("idx_backtests_params", "params", postgresql_using="gin"),
    )


class BacktestTrade(Base):
    """Individual trade within a backtest."""
    __tablename__ = "backtest_trades"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    backtest_id = Column(PGUUID(as_uuid=True), ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False, index=True)

    # Trade Details
    entry_time = Column(DateTime(timezone=True), nullable=False, index=True)
    exit_time = Column(DateTime(timezone=True))
    entry_price = Column(Numeric(20, 8), nullable=False)
    exit_price = Column(Numeric(20, 8))

    # Position
    position_side = Column(String(10), nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)

    # PnL
    pnl = Column(Numeric(20, 8))
    net_pnl = Column(Numeric(20, 8))
    entry_fee = Column(Numeric(20, 8))
    exit_fee = Column(Numeric(20, 8))

    # Exit Reason
    exit_reason = Column(String(50))

    # Status
    is_open = Column(Boolean, nullable=False, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    backtest = relationship("Backtest", back_populates="trades")

    __table_args__ = (
        CheckConstraint("position_side IN ('LONG', 'SHORT')", name="backtest_trades_position_side_check"),
    )


class StrategyMetric(Base):
    """Time-series performance metrics for strategies."""
    __tablename__ = "strategy_metrics"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id = Column(PGUUID(as_uuid=True), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Time Period
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    period_type = Column(String(20), nullable=False, index=True)

    # Metrics
    total_trades = Column(Integer, nullable=False, default=0)
    completed_trades = Column(Integer, nullable=False, default=0)
    winning_trades = Column(Integer, nullable=False, default=0)
    losing_trades = Column(Integer, nullable=False, default=0)
    total_pnl = Column(Numeric(20, 8), nullable=False, default=0)
    win_rate = Column(Numeric(5, 2), nullable=False, default=0)
    avg_profit_per_trade = Column(Numeric(20, 8), nullable=False, default=0)
    largest_win = Column(Numeric(20, 8))
    largest_loss = Column(Numeric(20, 8))
    max_drawdown = Column(Numeric(20, 8))

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    strategy = relationship("Strategy", back_populates="metrics")

    __table_args__ = (
        CheckConstraint("period_type IN ('hourly', 'daily', 'weekly', 'monthly')", name="strategy_metrics_period_type_check"),
        Index("idx_strategy_metrics_period", "period_start", "period_end"),
        Index("idx_strategy_metrics_period_type", "period_type", "period_start", postgresql_ops={"period_start": "DESC"}),
    )


class SystemEvent(Base):
    """System events and audit log."""
    __tablename__ = "system_events"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Event Details
    event_type = Column(String(50), nullable=False, index=True)
    event_level = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=False)

    # Context
    strategy_id = Column(PGUUID(as_uuid=True), ForeignKey("strategies.id", ondelete="SET NULL"), index=True)
    account_id = Column(PGUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"))
    event_metadata = Column(JSONB, default=lambda: {})  # Use lambda to avoid shared mutable default (renamed from 'metadata' to avoid SQLAlchemy reserved name)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint("event_level IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')", name="system_events_event_level_check"),
    )

