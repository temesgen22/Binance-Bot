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
    walk_forward_analyses = relationship("WalkForwardAnalysis", back_populates="user", cascade="all, delete-orphan")
    sensitivity_analyses = relationship("SensitivityAnalysis", back_populates="user", cascade="all, delete-orphan")
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
    
    # Auto-Tuning Configuration
    auto_tuning_enabled = Column(Boolean, nullable=False, default=False, index=True)
    auto_tuning_config = Column(JSONB, nullable=True)  # Per-strategy auto-tuning configuration

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


# ============================================
# WALK-FORWARD ANALYSIS (Per-User)
# ============================================

class WalkForwardAnalysis(Base):
    """Walk-forward analysis execution and results (per-user)."""
    __tablename__ = "walk_forward_analyses"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # CRITICAL: User isolation - all queries must filter by this
    
    # User-friendly identification
    name = Column(String(255))  # e.g., "BTC EMA 8/21 WFA - Jan 2025"
    label = Column(String(255))  # Optional label for UI organization
    
    # Configuration
    symbol = Column(String(20), nullable=False, index=True)
    strategy_type = Column(String(50), nullable=False, index=True)
    overall_start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    overall_end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Walk-forward specific configuration
    training_period_days = Column(Integer, nullable=False)
    test_period_days = Column(Integer, nullable=False)
    step_size_days = Column(Integer, nullable=False)
    window_type = Column(String(20), nullable=False)  # "rolling" or "expanding"
    total_windows = Column(Integer, nullable=False)
    
    # Risk management
    leverage = Column(Integer, nullable=False)
    risk_per_trade = Column(Numeric(10, 6), nullable=False)
    fixed_amount = Column(Numeric(20, 8))  # Optional fixed amount per trade (if None, uses risk_per_trade)
    initial_balance = Column(Numeric(20, 8), nullable=False)
    
    # Strategy Parameters (base parameters)
    params = Column(JSONB, nullable=False, default=lambda: {})  # Use lambda to avoid shared mutable default
    
    # Optimization settings (if optimization was used)
    optimization_enabled = Column(Boolean, nullable=False, default=False)
    optimization_method = Column(String(50))  # "grid_search", "random_search"
    optimization_metric = Column(String(50))  # "robust_score", "sharpe_ratio", etc.
    optimize_params = Column(JSONB, default=lambda: {})  # Parameters to optimize with ranges
    min_trades_guardrail = Column(Integer)  # Minimum trades required
    max_drawdown_cap = Column(Numeric(5, 2))  # Max drawdown cap (%)
    lottery_trade_threshold = Column(Numeric(5, 4))  # Lottery trade threshold (0.0-1.0)
    
    # Overall Results (aggregated across all windows)
    total_return_pct = Column(Numeric(10, 4), nullable=False)
    avg_window_return_pct = Column(Numeric(10, 4), nullable=False)
    consistency_score = Column(Numeric(5, 2), nullable=False)  # % of windows with positive returns
    sharpe_ratio = Column(Numeric(10, 4))
    max_drawdown_pct = Column(Numeric(5, 2))
    total_trades = Column(Integer, nullable=False, default=0)
    avg_win_rate = Column(Numeric(5, 2), nullable=False, default=0)
    return_std_dev = Column(Numeric(10, 4))  # Standard deviation of window returns
    best_window = Column(Integer)  # Window number with best performance
    worst_window = Column(Integer)  # Window number with worst performance
    final_balance = Column(Numeric(20, 8))
    
    # Execution Metadata
    execution_time_ms = Column(Integer)
    candles_processed = Column(Integer)
    
    # Retention settings
    keep_details = Column(Boolean, nullable=False, default=True)  # Whether to keep window details
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="walk_forward_analyses")
    windows = relationship("WalkForwardWindow", back_populates="analysis", cascade="all, delete-orphan")
    equity_points = relationship("WalkForwardEquityPoint", back_populates="analysis", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("leverage >= 1 AND leverage <= 50", name="wf_analyses_leverage_check"),
        CheckConstraint("risk_per_trade > 0 AND risk_per_trade < 1", name="wf_analyses_risk_check"),
        CheckConstraint("window_type IN ('rolling', 'expanding')", name="wf_analyses_window_type_check"),
        Index("idx_wf_analyses_params", "params", postgresql_using="gin"),
        Index("idx_wf_analyses_created_at", "created_at", postgresql_ops={"created_at": "DESC"}),
    )


class WalkForwardWindow(Base):
    """Individual window within a walk-forward analysis."""
    __tablename__ = "walk_forward_windows"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_id = Column(PGUUID(as_uuid=True), ForeignKey("walk_forward_analyses.id", ondelete="CASCADE"), nullable=False, index=True)  # CASCADE ensures user isolation via parent
    
    # Window identification
    window_number = Column(Integer, nullable=False)  # 1, 2, 3, etc.
    
    # Time periods
    training_start = Column(DateTime(timezone=True), nullable=False)
    training_end = Column(DateTime(timezone=True), nullable=False)
    test_start = Column(DateTime(timezone=True), nullable=False)
    test_end = Column(DateTime(timezone=True), nullable=False)
    
    # Optimized parameters (if optimization was used)
    optimized_params = Column(JSONB, default=lambda: {})  # Parameters found during training optimization
    
    # Training results (summary)
    training_return_pct = Column(Numeric(10, 4))
    training_sharpe = Column(Numeric(10, 4))
    training_win_rate = Column(Numeric(5, 2))
    training_trades = Column(Integer, default=0)
    
    # Test results (summary)
    test_return_pct = Column(Numeric(10, 4))
    test_sharpe = Column(Numeric(10, 4))
    test_win_rate = Column(Numeric(5, 2))
    test_trades = Column(Integer, default=0)
    test_final_balance = Column(Numeric(20, 8))
    
    # Optimization results (if optimization was used)
    # Store summary of all combinations tested during training
    optimization_results = Column(JSONB, default=lambda: [])  # List of all tested combinations with scores
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    analysis = relationship("WalkForwardAnalysis", back_populates="windows")
    
    __table_args__ = (
        Index("idx_wf_windows_analysis_window", "analysis_id", "window_number"),
        CheckConstraint("window_number > 0", name="wf_windows_window_number_check"),
    )


class WalkForwardEquityPoint(Base):
    """Equity curve data points for walk-forward analysis."""
    __tablename__ = "walk_forward_equity_points"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_id = Column(PGUUID(as_uuid=True), ForeignKey("walk_forward_analyses.id", ondelete="CASCADE"), nullable=False, index=True)  # CASCADE ensures user isolation via parent
    
    # Time and balance
    time = Column(DateTime(timezone=True), nullable=False, index=True)
    balance = Column(Numeric(20, 8), nullable=False)
    
    # Optional: Window reference
    window_number = Column(Integer)  # Which window this point belongs to
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    analysis = relationship("WalkForwardAnalysis", back_populates="equity_points")
    
    __table_args__ = (
        Index("idx_wf_equity_analysis_time", "analysis_id", "time"),
    )


# ============================================
# PARAMETER SENSITIVITY ANALYSIS
# ============================================

class SensitivityAnalysis(Base):
    """Parameter sensitivity analysis execution and results (per-user)."""
    __tablename__ = "sensitivity_analyses"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Identification
    name = Column(String(255), nullable=True)
    symbol = Column(String(20), nullable=False, index=True)
    strategy_type = Column(String(50), nullable=False, index=True)
    
    # Time period
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Configuration
    base_params = Column(JSONB, nullable=False, default=lambda: {})
    analyze_params = Column(JSONB, nullable=False)  # Which parameters were analyzed
    metric = Column(String(50), nullable=False)  # Which metric was used
    kline_interval = Column(String(10), nullable=False)  # Kline interval used (e.g., '5m', '1h')
    
    # Risk settings
    leverage = Column(Integer, nullable=False)
    risk_per_trade = Column(Numeric(10, 6), nullable=False)
    fixed_amount = Column(Numeric(20, 8), nullable=True)
    initial_balance = Column(Numeric(20, 8), nullable=False)
    
    # Results summary
    most_sensitive_param = Column(String(100), nullable=True)
    least_sensitive_param = Column(String(100), nullable=True)
    recommended_params = Column(JSONB, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="sensitivity_analyses")
    parameter_results = relationship("SensitivityParameterResult", back_populates="analysis", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_sensitivity_analyses_user_id", "user_id"),
        Index("idx_sensitivity_analyses_symbol", "symbol"),
        Index("idx_sensitivity_analyses_strategy_type", "strategy_type"),
        Index("idx_sensitivity_analyses_created_at", "created_at"),
    )


class SensitivityParameterResult(Base):
    """Results for a single parameter in sensitivity analysis."""
    __tablename__ = "sensitivity_parameter_results"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_id = Column(PGUUID(as_uuid=True), ForeignKey("sensitivity_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Parameter info
    parameter_name = Column(String(100), nullable=False)
    base_value = Column(JSONB, nullable=True)  # Original value
    tested_values = Column(JSONB, nullable=False)  # Array of tested values
    
    # Sensitivity metrics
    sensitivity_score = Column(Numeric(5, 4), nullable=False)  # 0.0 to 1.0
    optimal_value = Column(JSONB, nullable=True)
    worst_value = Column(JSONB, nullable=True)
    impact_range = Column(Numeric(20, 8), nullable=True)  # Difference between best and worst
    impact_range_display = Column(String(255), nullable=True)  # Formatted display string
    
    # Detailed results (stored as JSONB for flexibility)
    results = Column(JSONB, nullable=False)  # Array of {value, metric, summary, is_invalid, is_capped}
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    analysis = relationship("SensitivityAnalysis", back_populates="parameter_results")
    
    __table_args__ = (
        Index("idx_sensitivity_param_results_analysis_id", "analysis_id"),
    )


class StrategyParameterHistory(Base):
    """History of strategy parameter changes for auto-tuning."""
    __tablename__ = "strategy_parameter_history"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_uuid = Column(PGUUID(as_uuid=True), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    strategy_label = Column(String(100), nullable=True)  # Optional human-readable label (NOT used for joins)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Parameter changes
    old_params = Column(JSONB, nullable=False)
    new_params = Column(JSONB, nullable=False)
    changed_params = Column(JSONB, nullable=False)  # Only changed params
    reason = Column(String(255), nullable=True)  # "auto_tuning", "manual", "auto_tuning_failed_*", etc.
    status = Column(String(20), nullable=False, default="applied")  # applied|rolled_back|aborted|failed
    failure_reason = Column(Text, nullable=True)  # Error message if failed
    
    # Performance tracking
    performance_before = Column(JSONB, nullable=True)  # Metrics before change
    performance_after = Column(JSONB, nullable=True)  # Metrics after change (updated later)
    performance_after_updated_at = Column(DateTime(timezone=True), nullable=True)
    
    # Tuning run tracking
    tuning_run_id = Column(String(100), nullable=True)  # Link related tuning runs
    rollback_of_history_id = Column(PGUUID(as_uuid=True), ForeignKey("strategy_parameter_history.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    strategy = relationship("Strategy", foreign_keys=[strategy_uuid])
    rollback_of = relationship("StrategyParameterHistory", remote_side=[id], foreign_keys=[rollback_of_history_id])
    
    __table_args__ = (
        # Composite index for most common query pattern
        Index('idx_param_history_user_strategy_created', 'user_id', 'strategy_uuid', 'created_at'),
        # Separate index if querying by strategy only
        Index('idx_param_history_strategy_uuid', 'strategy_uuid'),
        Index('idx_param_history_status', 'status'),
        Index('idx_param_history_reason', 'reason'),
    )

