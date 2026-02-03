"""
Portfolio-level risk management with async locking and exposure reservation.

CRITICAL: This module implements mandatory fixes from CRITICAL_RISK_MANAGEMENT_FIXES.md:
1. Async locking for concurrent order checks (prevents race conditions)
2. Exposure reservation system (handles partial fills, failures, delays)
3. Realized PnL only for daily/weekly limits (not unrealized)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, time, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from loguru import logger

from app.core.exceptions import RiskLimitExceededError
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary
from app.models.risk_management import (
    RiskManagementConfigResponse,
    StrategyRiskConfigResponse
)
from app.strategies.base import StrategySignal


@dataclass
class ExposureReservation:
    """Tracks exposure reservation lifecycle."""
    account_id: str
    strategy_id: str
    reserved_exposure: float
    order_id: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "reserved"  # reserved, partial, confirmed, released


class PortfolioRiskManager:
    """Portfolio-level risk manager with async locking and exposure reservation.
    
    CRITICAL FEATURES:
    - Per-account async locking prevents race conditions
    - Exposure reservation handles partial fills and failures
    - Realized PnL only for daily/weekly limits
    - Drawdown uses total equity (realized + unrealized)
    """
    
    def __init__(
        self,
        account_id: str,
        config: Optional[RiskManagementConfigResponse],
        db_service: Optional[any] = None,
        user_id: Optional[UUID] = None,
        strategy_runner: Optional[any] = None,
        trade_service: Optional[any] = None,
        notification_service: Optional[any] = None,
    ):
        """Initialize portfolio risk manager.
        
        Args:
            account_id: Binance account ID
            config: Risk management configuration (None = no limits)
            db_service: Database service for querying strategies/trades
            user_id: User UUID
            strategy_runner: StrategyRunner instance for getting strategies
            trade_service: TradeService for querying trades
            notification_service: Notification service for risk alerts
        """
        self.account_id = account_id
        self.config = config
        self.db_service = db_service
        self.user_id = user_id
        self.strategy_runner = strategy_runner
        self.trade_service = trade_service
        self.notification_service = notification_service or (
            getattr(strategy_runner, 'notifications', None) if strategy_runner else None
        )
        
        # CRITICAL FIX #1: Per-account locks to prevent race conditions
        self.account_locks: Dict[str, asyncio.Lock] = {}
        self._lock_manager = asyncio.Lock()  # Protects account_locks dict
        
        # CRITICAL FIX #2: Exposure reservation tracking
        self._reservations: Dict[str, Dict[str, ExposureReservation]] = {}
        # Format: {account_id: {strategy_id: ExposureReservation}}
        
        # Track notified warnings to prevent spam (80% threshold)
        # Format: {account_id: {warning_type: last_notified_value}}
        self._warning_notified: Dict[str, Dict[str, float]] = {}
    
    def _safe_create_notification_task(self, coro):
        """Safely create a notification task, handling both real coroutines and mocks in tests.
        
        Args:
            coro: Coroutine or mock object
            
        Returns:
            Task if coro is a coroutine, None otherwise
        """
        try:
            if asyncio.iscoroutine(coro):
                return asyncio.create_task(coro)
        except Exception:
            # In tests, mocks might not be coroutines - that's OK
            pass
        return None
    
    def _get_account_lock(self, account_id: str) -> asyncio.Lock:
        """Get or create lock for account (thread-safe).
        
        CRITICAL: This prevents race conditions when multiple strategies
        check exposure simultaneously.
        """
        # Use a sync lock to protect the account_locks dict
        # This is safe because we're only creating locks, not holding them
        if account_id not in self.account_locks:
            self.account_locks[account_id] = asyncio.Lock()
        return self.account_locks[account_id]
    
    async def check_order_allowed(
        self,
        signal: StrategySignal,
        summary: StrategySummary,
        account_id: Optional[str] = None,
        strategy_config: Optional[StrategyRiskConfigResponse] = None,
        strategy_uuid: Optional[UUID] = None
    ) -> Tuple[bool, str]:
        """Check if order is allowed (WITH ASYNC LOCKING).
        
        CRITICAL: This method uses async locking to prevent race conditions.
        It also RESERVES exposure before order execution.
        
        Args:
            signal: Strategy signal
            summary: Strategy summary
            account_id: Account ID (defaults to self.account_id)
            strategy_config: Strategy-level risk config (optional)
            strategy_uuid: Strategy UUID for strategy-specific PnL calculation (optional)
            
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        account_id = account_id or self.account_id
        
        # CRITICAL FIX #1: Acquire lock for this account
        account_lock = self._get_account_lock(account_id)
        
        async with account_lock:
            # Get effective risk config (merged account + strategy configs)
            effective_config = self.get_effective_risk_config(strategy_config)
            
            # Check if risk management is enabled
            if not effective_config:
                return True, "Risk management not configured"
            
            # Check portfolio exposure limit
            if effective_config.max_portfolio_exposure_usdt or effective_config.max_portfolio_exposure_pct:
                allowed, reason = await self._check_exposure_limit(
                    signal, summary, account_id, effective_config
                )
                if not allowed:
                    return False, reason
            
            # Check daily loss limit (REALIZED PnL ONLY)
            if effective_config.max_daily_loss_usdt or effective_config.max_daily_loss_pct:
                allowed, reason = await self._check_daily_loss_limit(
                    account_id, effective_config, strategy_config, strategy_uuid
                )
                if not allowed:
                    return False, reason
            
            # Check weekly loss limit (REALIZED PnL ONLY)
            if effective_config.max_weekly_loss_usdt or effective_config.max_weekly_loss_pct:
                allowed, reason = await self._check_weekly_loss_limit(
                    account_id, effective_config, strategy_config, strategy_uuid
                )
                if not allowed:
                    return False, reason
            
            # Check drawdown limit (TOTAL EQUITY)
            if effective_config.max_drawdown_pct:
                allowed, reason = await self._check_drawdown_limit(
                    account_id, effective_config
                )
                if not allowed:
                    return False, reason
            
            # All checks passed - reserve exposure
            # CRITICAL FIX #2: Reserve exposure BEFORE order execution
            order_exposure = self._calculate_order_exposure(signal, summary)
            await self._reserve_exposure(account_id, order_exposure, summary.id)
            
            return True, "OK"
    
    async def _check_exposure_limit(
        self,
        signal: StrategySignal,
        summary: StrategySummary,
        account_id: str,
        config: Optional[RiskManagementConfigResponse] = None
    ) -> Tuple[bool, str]:
        """Check if order would exceed portfolio exposure limit.
        
        Args:
            signal: Strategy signal
            summary: Strategy summary
            account_id: Account ID
            config: Risk config to use (defaults to self.config)
        """
        config = config or self.config
        if not config:
            return True, "No exposure limit configured"
        
        # Calculate current exposure (including reservations)
        current_exposure = await self._calculate_current_exposure(account_id)
        
        # Calculate order exposure
        order_exposure = self._calculate_order_exposure(signal, summary)
        
        # Get max exposure limit
        max_exposure = await self._get_max_exposure(account_id, config)
        if max_exposure is None:
            return True, "No exposure limit set"
        
        total_exposure = current_exposure + order_exposure
        
        # Check if would exceed
        if total_exposure > max_exposure:
            # Send breach notification
            if self.notification_service:
                from app.services.notifier import NotificationType
                strategy_id_str = summary.id
                notification_coro = self.notification_service.notify_risk_breach(
                    NotificationType.EXPOSURE_LIMIT_BREACH,
                    account_id=account_id,
                    current_value=total_exposure,
                    limit_value=max_exposure,
                    breach_level="account",
                    strategy_id=strategy_id_str,
                    strategy_name=summary.name,
                    action_taken="Order blocked",
                    summary=summary,
                )
                self._safe_create_notification_task(notification_coro)
            
            return False, (
                f"Would exceed exposure limit: "
                f"{total_exposure:.2f} > {max_exposure:.2f} USDT"
            )
        
        # Check for warning (80% threshold) - only notify once per threshold
        warning_threshold = max_exposure * 0.8
        if current_exposure >= warning_threshold and self.notification_service:
            warning_key = f"exposure_{account_id}"
            last_notified = self._warning_notified.get(account_id, {}).get(warning_key, 0.0)
            
            # Only notify if exposure increased
            if current_exposure > last_notified:
                from app.services.notifier import NotificationType
                notification_coro = self.notification_service.notify_risk_warning(
                    NotificationType.EXPOSURE_LIMIT_WARNING,
                    account_id=account_id,
                    current_value=current_exposure,
                    limit_value=max_exposure,
                    strategy_id=summary.id,
                    strategy_name=summary.name,
                    summary=summary,
                )
                self._safe_create_notification_task(notification_coro)
                
                # Track notification
                if account_id not in self._warning_notified:
                    self._warning_notified[account_id] = {}
                self._warning_notified[account_id][warning_key] = current_exposure
        
        return True, "OK"
    
    async def _calculate_current_exposure(self, account_id: str) -> float:
        """Calculate current portfolio exposure including reservations.
        
        CRITICAL: This includes both real positions AND reservations.
        """
        # Get real exposure from positions
        real_exposure = await self._get_real_exposure(account_id)
        
        # Add reserved exposure
        reserved_exposure = sum(
            r.reserved_exposure
            for r in self._reservations.get(account_id, {}).values()
            if r.status in ("reserved", "partial")
        )
        
        return real_exposure + reserved_exposure
    
    async def _get_real_exposure(self, account_id: str) -> float:
        """Get real exposure from actual positions (not reservations).
        
        CRITICAL: Exposure = position_size * price * leverage
        """
        if not self.strategy_runner:
            return 0.0
        
        total_exposure = 0.0
        
        # Get all strategies for this account
        strategies = self.strategy_runner._strategies.values()
        account_strategies = [
            s for s in strategies
            if s.account_id == account_id and s.position_size and abs(s.position_size) > 0
        ]
        
        for strategy in account_strategies:
            # Get current price
            current_price = strategy.current_price
            if not current_price:
                # Fallback: try to get price from signal or use entry price
                current_price = strategy.entry_price or 0.0
                if not current_price:
                    logger.warning(
                        f"Cannot calculate exposure for {strategy.id}: no price available"
                    )
                    continue
            
            # Calculate notional WITH leverage
            # CRITICAL: Exposure = position_size * price * leverage
            notional = abs(strategy.position_size) * current_price * strategy.leverage
            total_exposure += notional
        
        return total_exposure
    
    def _calculate_order_exposure(
        self,
        signal: StrategySignal,
        summary: StrategySummary
    ) -> float:
        """Calculate exposure for a new order.
        
        Args:
            signal: Strategy signal
            summary: Strategy summary
            
        Returns:
            Exposure in USDT (quantity * price * leverage)
        """
        # Get order quantity from signal or summary
        # This is a simplified calculation - actual quantity comes from RiskManager
        # For now, estimate based on fixed_amount or risk_per_trade
        
        price = signal.price or summary.current_price or 0.0
        if price == 0.0:
            logger.warning(f"Cannot calculate order exposure: no price available")
            return 0.0
        
        # Estimate quantity (this will be refined when we have actual sizing)
        if summary.fixed_amount:
            quantity = summary.fixed_amount / price
        else:
            # Use risk_per_trade estimate (rough)
            # This is just for pre-check - actual sizing happens in RiskManager
            quantity = 0.0  # Will be calculated later
        
        # Calculate exposure with leverage
        notional = quantity * price * summary.leverage
        return notional
    
    async def _get_max_exposure(
        self,
        account_id: str,
        config: Optional[RiskManagementConfigResponse] = None
    ) -> Optional[float]:
        """Get maximum exposure limit for account.
        
        Args:
            account_id: Account ID
            config: Risk config to use (defaults to self.config)
        """
        config = config or self.config
        if not config:
            return None
        
        # Check USDT limit
        if config.max_portfolio_exposure_usdt:
            return float(config.max_portfolio_exposure_usdt)
        
        # Check percentage limit (need account balance)
        if config.max_portfolio_exposure_pct:
            balance = await self._get_account_balance(account_id)
            if balance:
                return balance * float(config.max_portfolio_exposure_pct)
        
        return None
    
    async def _get_account_balance(self, account_id: str) -> Optional[float]:
        """Get account balance in USDT.
        
        Bug #2 Fix: Properly fetch balance from BinanceClient using async wrapper.
        """
        if not self.strategy_runner:
            return None
        
        try:
            # Get client for this account
            if hasattr(self.strategy_runner, 'client_manager'):
                client = self.strategy_runner.client_manager.get_client(account_id)
            elif hasattr(self.strategy_runner, 'client'):
                client = self.strategy_runner.client
            else:
                return None
            
            if not client:
                return None
            
            # Bug #2 Fix: Wrap sync BinanceClient call in to_thread to avoid blocking event loop
            import asyncio
            balance = await asyncio.to_thread(client.futures_account_balance)
            return balance
        except Exception as e:
            logger.warning(f"Failed to get account balance for {account_id}: {e}")
            return None
    
    async def _check_daily_loss_limit(
        self,
        account_id: str,
        config: Optional[RiskManagementConfigResponse] = None,
        strategy_config: Optional[StrategyRiskConfigResponse] = None,
        strategy_uuid: Optional[UUID] = None
    ) -> Tuple[bool, str]:
        """Check daily loss limit (REALIZED PnL ONLY).
        
        CRITICAL: Uses realized PnL only, not unrealized.
        
        Args:
            account_id: Account ID
            config: Risk config to use (defaults to self.config)
            strategy_config: Strategy risk config (for strategy-specific limits)
            strategy_uuid: Strategy UUID (for strategy-specific PnL calculation)
        """
        config = config or self.config
        if not config:
            return True, "No limit configured"
        
        # Determine if checking strategy-specific or account-level limit
        use_strategy_specific = strategy_config and strategy_uuid and (
            strategy_config.max_daily_loss_usdt or strategy_config.max_daily_loss_pct
        )
        
        if use_strategy_specific and strategy_config.use_more_restrictive:
            # More restrictive mode: check BOTH account and strategy limits
            # Get account PnL
            today_start = self._get_today_start_for_strategy(strategy_config)
            account_pnl = await self._get_realized_pnl(account_id, today_start)
            
            # Get strategy PnL
            strategy_pnl = await self._get_strategy_realized_pnl(strategy_uuid, today_start)
            
            # Check account limit
            account_limit = None
            if config.max_daily_loss_usdt:
                account_limit = float(config.max_daily_loss_usdt)
            elif config.max_daily_loss_pct:
                balance = await self._get_account_balance(account_id)
                if balance:
                    account_limit = balance * float(config.max_daily_loss_pct)
            
            if account_limit and account_pnl < -abs(account_limit):
                return False, (
                    f"Daily loss limit exceeded (account): "
                    f"{account_pnl:.2f} < {account_limit:.2f} USDT"
                )
            
            # Check strategy limit
            strategy_limit = None
            if strategy_config.max_daily_loss_usdt:
                strategy_limit = float(strategy_config.max_daily_loss_usdt)
            elif strategy_config.max_daily_loss_pct:
                balance = await self._get_account_balance(account_id)
                if balance:
                    strategy_limit = balance * float(strategy_config.max_daily_loss_pct)
            
            if strategy_limit and strategy_pnl < -abs(strategy_limit):
                return False, (
                    f"Daily loss limit exceeded (strategy): "
                    f"{strategy_pnl:.2f} < {strategy_limit:.2f} USDT"
                )
            
            return True, "OK"
        else:
            # Use effective config limits (already merged)
            today_start = self._get_today_start_for_strategy(strategy_config) if strategy_config else self._get_today_start()
            
            # Get PnL: strategy-specific if strategy_uuid provided, otherwise account-level
            if use_strategy_specific and strategy_uuid:
                realized_pnl = await self._get_strategy_realized_pnl(strategy_uuid, today_start)
                # CRITICAL: Mark as strategy-level breach so only this strategy is stopped
                breach_type = "(strategy)"
            else:
                realized_pnl = await self._get_realized_pnl(account_id, today_start)
                # Mark as account-level breach so all strategies are stopped
                breach_type = "(account)"
            
            # Get limit from effective config
            max_daily_loss = None
            if config.max_daily_loss_usdt:
                max_daily_loss = float(config.max_daily_loss_usdt)
            elif config.max_daily_loss_pct:
                balance = await self._get_account_balance(account_id)
                if balance:
                    max_daily_loss = balance * float(config.max_daily_loss_pct)
            
            if max_daily_loss is None:
                return True, "No limit set"
            
            # Check for breach
            if realized_pnl < -abs(max_daily_loss):
                # Send breach notification
                if self.notification_service:
                    from app.services.notifier import NotificationType
                    breach_level = "strategy" if breach_type == "(strategy)" else "account"
                    strategy_id_str = str(strategy_uuid) if strategy_uuid else None
                    strategy_name = None
                    summary = None
                    
                    # Try to get strategy summary for better notification
                    if strategy_uuid and self.strategy_runner:
                        try:
                            strategies = self.strategy_runner.list_strategies()
                            for s in strategies:
                                if s.id == strategy_id_str:
                                    summary = s
                                    strategy_name = s.name
                                    break
                        except:
                            pass
                    
                    # Create notification task (handle both real coroutines and mocks in tests)
                    notification_coro = self.notification_service.notify_risk_breach(
                        NotificationType.DAILY_LOSS_LIMIT_BREACH,
                        account_id=account_id,
                        current_value=realized_pnl,
                        limit_value=-abs(max_daily_loss),
                        breach_level=breach_level,
                        strategy_id=strategy_id_str,
                        strategy_name=strategy_name,
                        action_taken="Trading blocked" if breach_level == "account" else "Strategy stopped",
                        summary=summary,
                    )
                    self._safe_create_notification_task(notification_coro)
                
                return False, (
                    f"Daily loss limit exceeded {breach_type}: "
                    f"{realized_pnl:.2f} < {max_daily_loss:.2f} USDT"
                )
            
            # Check for warning (80% threshold) - only notify once per threshold
            warning_threshold = -abs(max_daily_loss) * 0.8
            if realized_pnl <= warning_threshold and self.notification_service:
                warning_key = f"daily_loss_{account_id}_{strategy_uuid or 'account'}"
                last_notified = self._warning_notified.get(account_id, {}).get(warning_key, float('inf'))
                
                # Only notify if we haven't notified for this threshold or if loss increased
                if abs(realized_pnl) > abs(last_notified):
                    from app.services.notifier import NotificationType
                    strategy_id_str = str(strategy_uuid) if strategy_uuid else None
                    strategy_name = None
                    summary = None
                    
                    # Try to get strategy summary for better notification
                    if strategy_uuid and self.strategy_runner:
                        try:
                            strategies = self.strategy_runner.list_strategies()
                            for s in strategies:
                                if s.id == strategy_id_str:
                                    summary = s
                                    strategy_name = s.name
                                    break
                        except:
                            pass
                    
                    notification_coro = self.notification_service.notify_risk_warning(
                        NotificationType.DAILY_LOSS_LIMIT_WARNING,
                        account_id=account_id,
                        current_value=abs(realized_pnl),
                        limit_value=abs(max_daily_loss),
                        strategy_id=strategy_id_str,
                        strategy_name=strategy_name,
                        summary=summary,
                    )
                    self._safe_create_notification_task(notification_coro)
                    
                    # Track notification
                    if account_id not in self._warning_notified:
                        self._warning_notified[account_id] = {}
                    self._warning_notified[account_id][warning_key] = realized_pnl
            
            return True, "OK"
    
    async def _check_weekly_loss_limit(
        self,
        account_id: str,
        config: Optional[RiskManagementConfigResponse] = None,
        strategy_config: Optional[StrategyRiskConfigResponse] = None,
        strategy_uuid: Optional[UUID] = None
    ) -> Tuple[bool, str]:
        """Check weekly loss limit (REALIZED PnL ONLY).
        
        CRITICAL: Uses realized PnL only, not unrealized.
        
        Args:
            account_id: Account ID
            config: Risk config to use (defaults to self.config)
            strategy_config: Strategy risk config (for strategy-specific limits)
            strategy_uuid: Strategy UUID (for strategy-specific PnL calculation)
        """
        config = config or self.config
        if not config:
            return True, "No limit configured"
        
        # Determine if checking strategy-specific or account-level limit
        use_strategy_specific = strategy_config and strategy_uuid and (
            strategy_config.max_weekly_loss_usdt or strategy_config.max_weekly_loss_pct
        )
        
        # Get week start with strategy config timezone/reset day if available
        if strategy_config:
            tz_str = strategy_config.timezone or "UTC"
            reset_day = strategy_config.weekly_loss_reset_day or 1
            week_start = self._get_week_start(tz_str, reset_day)
        elif config:
            tz_str = config.timezone or "UTC"
            reset_day = config.weekly_loss_reset_day or 1
            week_start = self._get_week_start(tz_str, reset_day)
        else:
            week_start = self._get_week_start()
        
        if use_strategy_specific and strategy_config.use_more_restrictive:
            # More restrictive mode: check BOTH account and strategy limits
            # Get account PnL
            account_pnl = await self._get_realized_pnl(account_id, week_start)
            
            # Get strategy PnL
            strategy_pnl = await self._get_strategy_realized_pnl(strategy_uuid, week_start)
            
            # Check account limit
            account_limit = None
            if config.max_weekly_loss_usdt:
                account_limit = float(config.max_weekly_loss_usdt)
            elif config.max_weekly_loss_pct:
                balance = await self._get_account_balance(account_id)
                if balance:
                    account_limit = balance * float(config.max_weekly_loss_pct)
            
            if account_limit and account_pnl < -abs(account_limit):
                return False, (
                    f"Weekly loss limit exceeded (account): "
                    f"{account_pnl:.2f} < {account_limit:.2f} USDT"
                )
            
            # Check strategy limit
            strategy_limit = None
            if strategy_config.max_weekly_loss_usdt:
                strategy_limit = float(strategy_config.max_weekly_loss_usdt)
            elif strategy_config.max_weekly_loss_pct:
                balance = await self._get_account_balance(account_id)
                if balance:
                    strategy_limit = balance * float(strategy_config.max_weekly_loss_pct)
            
            if strategy_limit and strategy_pnl < -abs(strategy_limit):
                return False, (
                    f"Weekly loss limit exceeded (strategy): "
                    f"{strategy_pnl:.2f} < {strategy_limit:.2f} USDT"
                )
            
            return True, "OK"
        else:
            # Use effective config limits (already merged)
            # Get PnL: strategy-specific if strategy_uuid provided, otherwise account-level
            if use_strategy_specific and strategy_uuid:
                realized_pnl = await self._get_strategy_realized_pnl(strategy_uuid, week_start)
                # CRITICAL: Mark as strategy-level breach so only this strategy is stopped
                breach_type = "(strategy)"
            else:
                realized_pnl = await self._get_realized_pnl(account_id, week_start)
                # Mark as account-level breach so all strategies are stopped
                breach_type = "(account)"
            
            # Get limit from effective config
            max_weekly_loss = None
            if config.max_weekly_loss_usdt:
                max_weekly_loss = float(config.max_weekly_loss_usdt)
            elif config.max_weekly_loss_pct:
                balance = await self._get_account_balance(account_id)
                if balance:
                    max_weekly_loss = balance * float(config.max_weekly_loss_pct)
            
            if max_weekly_loss is None:
                return True, "No limit set"
            
            # Check for breach
            if realized_pnl < -abs(max_weekly_loss):
                # Send breach notification
                if self.notification_service:
                    from app.services.notifier import NotificationType
                    breach_level = "strategy" if breach_type == "(strategy)" else "account"
                    strategy_id_str = str(strategy_uuid) if strategy_uuid else None
                    strategy_name = None
                    summary = None
                    
                    # Try to get strategy summary for better notification
                    if strategy_uuid and self.strategy_runner:
                        try:
                            strategies = self.strategy_runner.list_strategies()
                            for s in strategies:
                                if s.id == strategy_id_str:
                                    summary = s
                                    strategy_name = s.name
                                    break
                        except:
                            pass
                    
                    notification_coro = self.notification_service.notify_risk_breach(
                        NotificationType.WEEKLY_LOSS_LIMIT_BREACH,
                        account_id=account_id,
                        current_value=realized_pnl,
                        limit_value=-abs(max_weekly_loss),
                        breach_level=breach_level,
                        strategy_id=strategy_id_str,
                        strategy_name=strategy_name,
                        action_taken="Trading blocked" if breach_level == "account" else "Strategy stopped",
                        summary=summary,
                    )
                    self._safe_create_notification_task(notification_coro)
                
                return False, (
                    f"Weekly loss limit exceeded {breach_type}: "
                    f"{realized_pnl:.2f} < {max_weekly_loss:.2f} USDT"
                )
            
            # Check for warning (80% threshold) - only notify once per threshold
            warning_threshold = -abs(max_weekly_loss) * 0.8
            if realized_pnl <= warning_threshold and self.notification_service:
                warning_key = f"weekly_loss_{account_id}_{strategy_uuid or 'account'}"
                last_notified = self._warning_notified.get(account_id, {}).get(warning_key, float('inf'))
                
                # Only notify if we haven't notified for this threshold or if loss increased
                if abs(realized_pnl) > abs(last_notified):
                    from app.services.notifier import NotificationType
                    strategy_id_str = str(strategy_uuid) if strategy_uuid else None
                    strategy_name = None
                    summary = None
                    
                    # Try to get strategy summary for better notification
                    if strategy_uuid and self.strategy_runner:
                        try:
                            strategies = self.strategy_runner.list_strategies()
                            for s in strategies:
                                if s.id == strategy_id_str:
                                    summary = s
                                    strategy_name = s.name
                                    break
                        except:
                            pass
                    
                    notification_coro = self.notification_service.notify_risk_warning(
                        NotificationType.WEEKLY_LOSS_LIMIT_WARNING,
                        account_id=account_id,
                        current_value=abs(realized_pnl),
                        limit_value=abs(max_weekly_loss),
                        strategy_id=strategy_id_str,
                        strategy_name=strategy_name,
                        summary=summary,
                    )
                    self._safe_create_notification_task(notification_coro)
                    
                    # Track notification
                    if account_id not in self._warning_notified:
                        self._warning_notified[account_id] = {}
                    self._warning_notified[account_id][warning_key] = realized_pnl
            
            return True, "OK"
    
    async def _check_drawdown_limit(
        self,
        account_id: str,
        config: Optional[RiskManagementConfigResponse] = None
    ) -> Tuple[bool, str]:
        """Check drawdown limit (TOTAL EQUITY: realized + unrealized).
        
        CRITICAL: Drawdown uses total equity, not just realized PnL.
        
        Args:
            account_id: Account ID
            config: Risk config to use (defaults to self.config)
        """
        config = config or self.config
        if not config or not config.max_drawdown_pct:
            return True, "No limit configured"
        
        # Get current balance (total equity)
        current_balance = await self._get_account_balance(account_id)
        if not current_balance:
            return True, "Cannot calculate drawdown: balance unavailable"
        
        # Get peak balance
        peak_balance = await self._get_peak_balance(account_id)
        if not peak_balance or peak_balance <= 0:
            return True, "No peak balance yet"
        
        # Calculate drawdown
        drawdown_pct = (peak_balance - current_balance) / peak_balance
        
        max_drawdown = float(config.max_drawdown_pct)
        
        # Check for breach
        if drawdown_pct > max_drawdown:
            # Send breach notification
            if self.notification_service:
                from app.services.notifier import NotificationType
                notification_coro = self.notification_service.notify_risk_breach(
                    NotificationType.DRAWDOWN_LIMIT_BREACH,
                    account_id=account_id,
                    current_value=drawdown_pct * 100,  # Convert to percentage
                    limit_value=max_drawdown * 100,  # Convert to percentage
                    breach_level="account",
                    action_taken="Trading blocked",
                )
                self._safe_create_notification_task(notification_coro)
            
            return False, (
                f"Drawdown limit exceeded: "
                f"{drawdown_pct:.2%} > {max_drawdown:.2%}"
            )
        
        # Check for warning (80% threshold) - only notify once per threshold
        warning_threshold = max_drawdown * 0.8
        if drawdown_pct >= warning_threshold and self.notification_service:
            warning_key = f"drawdown_{account_id}"
            last_notified = self._warning_notified.get(account_id, {}).get(warning_key, 0.0)
            
            # Only notify if drawdown increased
            if drawdown_pct > last_notified:
                from app.services.notifier import NotificationType
                notification_coro = self.notification_service.notify_risk_warning(
                    NotificationType.DRAWDOWN_LIMIT_WARNING,
                    account_id=account_id,
                    current_value=drawdown_pct * 100,  # Convert to percentage
                    limit_value=max_drawdown * 100,  # Convert to percentage
                )
                self._safe_create_notification_task(notification_coro)
                
                # Track notification
                if account_id not in self._warning_notified:
                    self._warning_notified[account_id] = {}
                self._warning_notified[account_id][warning_key] = drawdown_pct
        
        return True, "OK"
    
    async def _get_realized_pnl(
        self,
        account_id: str,
        start_time: datetime
    ) -> float:
        """Get realized PnL from closed trades since start_time.
        
        CRITICAL: Only includes closed trades (realized PnL), not open positions.
        Uses CompletedTrade table directly for consistency and performance.
        """
        if not self.db_service or not self.user_id:
            return 0.0
        
        total_pnl = 0.0
        
        # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
        # This is much faster and more consistent with other endpoints
        from app.models.db_models import CompletedTrade, Account, Strategy
        
        # Get account UUID from account_id string
        try:
            account = self.db_service.get_account_by_id(self.user_id, account_id)
            if not account:
                return 0.0
        except Exception as e:
            logger.warning(f"Failed to get account {account_id}: {e}")
            return 0.0
        
        # Get all strategies for this account
        try:
            strategies = self.db_service.db.query(Strategy).filter(
                Strategy.user_id == self.user_id,
                Strategy.account_id == account.id
            ).all()
        except Exception as e:
            logger.warning(f"Failed to get strategies for account {account_id}: {e}")
            return 0.0
        
        # Query completed trades from CompletedTrade table (pre-computed)
        for strategy in strategies:
            try:
                # Query completed trades with exit_time >= start_time
                # ✅ NEW: Exclude paper trades from risk calculations
                completed_trades = self.db_service.db.query(CompletedTrade).filter(
                    CompletedTrade.user_id == self.user_id,
                    CompletedTrade.strategy_id == strategy.id,
                    CompletedTrade.exit_time >= start_time,
                    CompletedTrade.paper_trading == False  # Exclude paper trades
                ).all()
                
                # Sum net PnL from completed trades
                for completed in completed_trades:
                    total_pnl += float(completed.pnl_usd)
            except Exception as e:
                logger.warning(f"Failed to get completed trades for strategy {strategy.id}: {e}")
                continue
        
        return total_pnl
    
    async def _get_peak_balance(self, account_id: str) -> Optional[float]:
        """Get peak balance for account.
        
        Peak balance is the highest balance ever reached.
        Used for drawdown calculation.
        """
        # Get current balance
        current_balance = await self._get_account_balance(account_id)
        if not current_balance:
            return None
        
        # TODO: Query from risk_metrics table for historical peak
        # For now, use current balance as peak (will be updated as balance increases)
        # In production, this should query the risk_metrics table
        
        # Simple implementation: track peak in memory
        # In production, this should be persisted in risk_metrics table
        if not hasattr(self, '_peak_balances'):
            self._peak_balances: Dict[str, float] = {}
        
        peak = self._peak_balances.get(account_id, current_balance)
        if current_balance > peak:
            peak = current_balance
            self._peak_balances[account_id] = peak
        
        return peak
    
    def _get_today_start(self, timezone_str: str = "UTC", reset_time: Optional[time] = None) -> datetime:
        """Get start of today in specified timezone.
        
        Args:
            timezone_str: Timezone string (default: "UTC")
            reset_time: Optional reset time (default: 00:00:00)
        """
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone_str)
        now = datetime.now(tz)
        
        if reset_time:
            today_start = now.replace(hour=reset_time.hour, minute=reset_time.minute, second=reset_time.second, microsecond=0)
            # If reset_time is in the future today, use yesterday's reset
            if today_start > now:
                today_start = today_start - timedelta(days=1)
        else:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return today_start.astimezone(timezone.utc)  # Convert to UTC for internal use
    
    def _get_today_start_for_strategy(self, strategy_config: Optional[StrategyRiskConfigResponse] = None) -> datetime:
        """Get today start for a strategy using its config, or default to account config."""
        if strategy_config and strategy_config.daily_loss_reset_time:
            tz_str = strategy_config.timezone or "UTC"
            return self._get_today_start(tz_str, strategy_config.daily_loss_reset_time)
        elif self.config and self.config.daily_loss_reset_time:
            tz_str = self.config.timezone or "UTC"
            return self._get_today_start(tz_str, self.config.daily_loss_reset_time)
        else:
            return self._get_today_start()
    
    def _get_week_start(self, timezone_str: str = "UTC", reset_day: int = 1) -> datetime:
        """Get start of current week in specified timezone.
        
        Args:
            timezone_str: Timezone string (default: "UTC")
            reset_day: Day of week when week resets (1=Monday, 7=Sunday, default: 1)
        """
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone_str)
        now = datetime.now(tz)
        
        # Calculate days to subtract to get to reset day
        # reset_day: 1=Monday, 7=Sunday
        current_weekday = now.weekday() + 1  # Convert to 1=Monday, 7=Sunday
        days_to_subtract = (current_weekday - reset_day) % 7
        
        week_start = now - timedelta(days=days_to_subtract)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        return week_start.astimezone(timezone.utc)  # Convert to UTC for internal use
    
    # CRITICAL FIX #2: Exposure Reservation Methods
    
    async def _reserve_exposure(
        self,
        account_id: str,
        exposure: float,
        strategy_id: str
    ) -> None:
        """Reserve exposure BEFORE order execution.
        
        CRITICAL: This prevents "ghost exposure" from failed/delayed orders.
        """
        if account_id not in self._reservations:
            self._reservations[account_id] = {}
        
        reservation = ExposureReservation(
            account_id=account_id,
            strategy_id=strategy_id,
            reserved_exposure=exposure
        )
        self._reservations[account_id][strategy_id] = reservation
        
        logger.debug(
            f"Reserved exposure: {exposure:.2f} USDT for {strategy_id} "
            f"(account: {account_id})"
        )
    
    async def confirm_exposure(
        self,
        account_id: str,
        strategy_id: str,
        order_response: OrderResponse
    ) -> None:
        """Convert reservation to real exposure after successful execution.
        
        CRITICAL: Handles partial fills by adjusting reservation.
        """
        if account_id not in self._reservations:
            return
        
        reservation = self._reservations[account_id].get(strategy_id)
        if not reservation:
            return
        
        # Calculate actual executed exposure
        avg_price = order_response.avg_price or order_response.price
        actual_exposure = self._calculate_executed_exposure(order_response)
        
        # Handle partial fills
        # Compare actual executed exposure to reserved exposure
        # If executed < reserved, it's a partial fill
        if order_response.status == "FILLED":
            # Full fill - convert to confirmed
            reservation.status = "confirmed"
            reservation.order_id = order_response.order_id
            # Update reserved exposure to match actual (in case of price changes)
            reservation.reserved_exposure = actual_exposure
        elif actual_exposure < reservation.reserved_exposure * 0.95:  # 5% tolerance for rounding
            # Partial fill - adjust reservation to match actual executed exposure
            reservation.status = "partial"
            reservation.reserved_exposure = actual_exposure
            reservation.order_id = order_response.order_id
        else:
            # Close enough to full fill - mark as confirmed
            reservation.status = "confirmed"
            reservation.order_id = order_response.order_id
            reservation.reserved_exposure = actual_exposure
        
        logger.debug(
            f"Confirmed exposure: {actual_exposure:.2f} USDT for {strategy_id} "
            f"(account: {account_id}, status: {reservation.status})"
        )
    
    async def release_reservation(
        self,
        account_id: str,
        strategy_id: str
    ) -> None:
        """Release reservation if order failed.
        
        CRITICAL: Prevents "ghost exposure" from failed orders.
        """
        if account_id not in self._reservations:
            return
        
        reservation = self._reservations[account_id].pop(strategy_id, None)
        if reservation:
            reservation.status = "released"
            logger.debug(
                f"Released reservation: {reservation.reserved_exposure:.2f} USDT "
                f"for {strategy_id} (account: {account_id})"
            )
    
    def _calculate_executed_exposure(self, order_response: OrderResponse) -> float:
        """Calculate exposure from executed order."""
        # Use executed quantity and average price
        executed_qty = order_response.executed_qty
        avg_price = order_response.avg_price or order_response.price
        
        # Get leverage from order or default to 1
        leverage = order_response.leverage or 1
        
        # Calculate notional with leverage
        notional = executed_qty * avg_price * leverage
        return notional
    
    def calculate_max_allowed_size(
        self,
        signal: StrategySignal,
        summary: StrategySummary,
        account_id: Optional[str] = None
    ) -> Optional[float]:
        """Calculate maximum allowed order size that fits within limits.
        
        Used when auto_reduce_order_size is enabled.
        """
        account_id = account_id or self.account_id
        
        # Get current exposure
        # Note: This should be called within a lock, but for simplicity
        # we'll calculate synchronously (lock should be acquired by caller)
        # TODO: Make this async and use lock
        
        max_exposure = None  # Will be calculated
        current_exposure = 0.0  # Will be calculated
        
        if max_exposure:
            available = max_exposure - current_exposure
            if available > 0:
                # Calculate max quantity
                price = signal.price or summary.current_price or 0.0
                if price > 0:
                    max_quantity = available / (price * summary.leverage)
                    return max_quantity
        
        return None
    
    # ============================================
    # STRATEGY-LEVEL RISK CONFIG HELPERS
    # ============================================
    
    def _convert_strategy_to_risk_config(
        self,
        strategy_config: StrategyRiskConfigResponse
    ) -> RiskManagementConfigResponse:
        """Convert StrategyRiskConfigResponse to RiskManagementConfigResponse.
        
        This is needed because PortfolioRiskManager uses RiskManagementConfigResponse
        internally, but we need to work with StrategyRiskConfigResponse.
        
        Args:
            strategy_config: Strategy risk config to convert
        
        Returns:
            RiskManagementConfigResponse with strategy limits
        """
        # Use account config as base for required fields, then override with strategy limits
        base_config = self.config  # Use current account config as base
        
        return RiskManagementConfigResponse(
            id=strategy_config.id,  # Use strategy config ID
            user_id=strategy_config.user_id,  # Use strategy config user_id
            account_id=base_config.account_id,  # Use account_id from base config
            max_portfolio_exposure_usdt=strategy_config.max_exposure_usdt,
            max_portfolio_exposure_pct=strategy_config.max_exposure_pct,
            max_daily_loss_usdt=strategy_config.max_daily_loss_usdt,
            max_daily_loss_pct=strategy_config.max_daily_loss_pct,
            max_weekly_loss_usdt=strategy_config.max_weekly_loss_usdt,
            max_weekly_loss_pct=strategy_config.max_weekly_loss_pct,
            max_drawdown_pct=strategy_config.max_drawdown_pct,
            daily_loss_reset_time=strategy_config.daily_loss_reset_time,
            weekly_loss_reset_day=strategy_config.weekly_loss_reset_day,
            timezone=strategy_config.timezone or "UTC",
            circuit_breaker_enabled=False,  # Strategy config doesn't have circuit breaker
            max_consecutive_losses=base_config.max_consecutive_losses if base_config.max_consecutive_losses else 5,  # Use account default or 5
            rapid_loss_threshold_pct=base_config.rapid_loss_threshold_pct if base_config.rapid_loss_threshold_pct else 0.05,
            rapid_loss_timeframe_minutes=base_config.rapid_loss_timeframe_minutes if base_config.rapid_loss_timeframe_minutes else 60,  # Must be >= 1
            circuit_breaker_cooldown_minutes=base_config.circuit_breaker_cooldown_minutes if base_config.circuit_breaker_cooldown_minutes else 60,  # Must be >= 1
            volatility_based_sizing_enabled=False,
            performance_based_adjustment_enabled=False,
            kelly_criterion_enabled=False,
            kelly_fraction=0.0,
            correlation_limits_enabled=False,
            max_correlation_exposure_pct=0.0,
            margin_call_protection_enabled=False,
            min_margin_ratio=0.0,
            max_trades_per_day_per_strategy=None,
            max_trades_per_day_total=None,
            auto_reduce_order_size=False,
            created_at=strategy_config.created_at,  # Use strategy config timestamps
            updated_at=strategy_config.updated_at,
        )
    
    def _merge_configs_most_restrictive(
        self,
        account_config: Optional[RiskManagementConfigResponse],
        strategy_config: Optional[RiskManagementConfigResponse]
    ) -> Optional[RiskManagementConfigResponse]:
        """Merge account and strategy configs using most restrictive limits.
        
        For each limit field, takes the more restrictive (lower) value.
        If one config has a limit and the other doesn't, uses the one with the limit.
        
        Args:
            account_config: Account-level risk config
            strategy_config: Strategy-level risk config (already converted to RiskManagementConfigResponse)
        
        Returns:
            Merged config with most restrictive limits, or None if both are None
        """
        if not account_config and not strategy_config:
            return None
        
        if not account_config:
            return strategy_config
        
        if not strategy_config:
            return account_config
        
        # Helper to get more restrictive value (lower is more restrictive for limits)
        def more_restrictive(val1: Optional[float], val2: Optional[float]) -> Optional[float]:
            if val1 is None:
                return val2
            if val2 is None:
                return val1
            return min(val1, val2)
        
        # Merge limits - take most restrictive (lower values)
        return RiskManagementConfigResponse(
            max_portfolio_exposure_usdt=more_restrictive(
                float(account_config.max_portfolio_exposure_usdt) if account_config.max_portfolio_exposure_usdt else None,
                float(strategy_config.max_portfolio_exposure_usdt) if strategy_config.max_portfolio_exposure_usdt else None
            ),
            max_portfolio_exposure_pct=more_restrictive(
                float(account_config.max_portfolio_exposure_pct) if account_config.max_portfolio_exposure_pct else None,
                float(strategy_config.max_portfolio_exposure_pct) if strategy_config.max_portfolio_exposure_pct else None
            ),
            max_daily_loss_usdt=more_restrictive(
                float(account_config.max_daily_loss_usdt) if account_config.max_daily_loss_usdt else None,
                float(strategy_config.max_daily_loss_usdt) if strategy_config.max_daily_loss_usdt else None
            ),
            max_daily_loss_pct=more_restrictive(
                float(account_config.max_daily_loss_pct) if account_config.max_daily_loss_pct else None,
                float(strategy_config.max_daily_loss_pct) if strategy_config.max_daily_loss_pct else None
            ),
            max_weekly_loss_usdt=more_restrictive(
                float(account_config.max_weekly_loss_usdt) if account_config.max_weekly_loss_usdt else None,
                float(strategy_config.max_weekly_loss_usdt) if strategy_config.max_weekly_loss_usdt else None
            ),
            max_weekly_loss_pct=more_restrictive(
                float(account_config.max_weekly_loss_pct) if account_config.max_weekly_loss_pct else None,
                float(strategy_config.max_weekly_loss_pct) if strategy_config.max_weekly_loss_pct else None
            ),
            max_drawdown_pct=more_restrictive(
                float(account_config.max_drawdown_pct) if account_config.max_drawdown_pct else None,
                float(strategy_config.max_drawdown_pct) if strategy_config.max_drawdown_pct else None
            ),
            # Use strategy timezone/reset times if available, otherwise account
            daily_loss_reset_time=strategy_config.daily_loss_reset_time or account_config.daily_loss_reset_time,
            weekly_loss_reset_day=strategy_config.weekly_loss_reset_day or account_config.weekly_loss_reset_day,
            timezone=strategy_config.timezone or account_config.timezone or "UTC",
            # Circuit breaker and other settings come from account config only
            circuit_breaker_enabled=account_config.circuit_breaker_enabled,
            max_consecutive_losses=account_config.max_consecutive_losses,
            rapid_loss_threshold_pct=account_config.rapid_loss_threshold_pct,
            rapid_loss_timeframe_minutes=account_config.rapid_loss_timeframe_minutes,
            circuit_breaker_cooldown_minutes=account_config.circuit_breaker_cooldown_minutes,
            volatility_based_sizing_enabled=account_config.volatility_based_sizing_enabled,
            performance_based_adjustment_enabled=account_config.performance_based_adjustment_enabled,
            kelly_criterion_enabled=account_config.kelly_criterion_enabled,
            kelly_fraction=account_config.kelly_fraction,
            correlation_limits_enabled=account_config.correlation_limits_enabled,
            max_correlation_exposure_pct=account_config.max_correlation_exposure_pct,
            margin_call_protection_enabled=account_config.margin_call_protection_enabled,
            min_margin_ratio=account_config.min_margin_ratio,
            max_trades_per_day_per_strategy=account_config.max_trades_per_day_per_strategy,
            max_trades_per_day_total=account_config.max_trades_per_day_total,
            auto_reduce_order_size=account_config.auto_reduce_order_size,
            # Required fields - use account config values
            id=account_config.id,
            user_id=account_config.user_id,
            account_id=account_config.account_id,
            created_at=account_config.created_at,
            updated_at=account_config.updated_at,
        )
    
    async def _get_strategy_realized_pnl(
        self,
        strategy_uuid: UUID,
        start_time: datetime
    ) -> float:
        """Get realized PnL for a specific strategy from closed trades since start_time.
        
        CRITICAL: Only includes closed trades (realized PnL), not open positions.
        Uses CompletedTrade table directly for consistency and performance.
        
        Args:
            strategy_uuid: Strategy UUID (from Strategy.id, not strategy_id string)
            start_time: Start time for PnL calculation
        
        Returns:
            Realized PnL in USDT
        """
        if not self.db_service or not self.user_id:
            return 0.0
        
        # ✅ PREFER: Get completed trades from pre-computed CompletedTrade table (ON-WRITE)
        # This is much faster and more consistent with other endpoints
        from app.models.db_models import CompletedTrade
        
        try:
            # Query completed trades from CompletedTrade table (pre-computed)
            # Filter by exit_time >= start_time to get trades closed since start_time
            # ✅ NEW: Exclude paper trades from risk calculations
            completed_trades = self.db_service.db.query(CompletedTrade).filter(
                CompletedTrade.user_id == self.user_id,
                CompletedTrade.strategy_id == strategy_uuid,
                CompletedTrade.exit_time >= start_time,
                CompletedTrade.paper_trading == False  # Exclude paper trades
            ).all()
            
            # Sum net PnL from completed trades
            total_pnl = 0.0
            for completed in completed_trades:
                total_pnl += float(completed.pnl_usd)
            
            return total_pnl
        except Exception as e:
            logger.warning(f"Failed to get completed trades for strategy {strategy_uuid}: {e}")
            return 0.0
    
    def get_effective_risk_config(
        self,
        strategy_config: Optional[StrategyRiskConfigResponse] = None
    ) -> Optional[RiskManagementConfigResponse]:
        """Get effective risk config by merging account and strategy configs.
        
        Priority rules:
        1. If strategy_config.override_account_limits = True: use strategy limits only
        2. If strategy_config.use_more_restrictive = True: use most restrictive of both
        3. Otherwise (both flags False): use strategy limits only (strategy-only mode)
        
        Args:
            strategy_config: Strategy-level risk config (optional)
        
        Returns:
            Effective risk config to use for checks
        """
        # If no strategy config, use account config
        if not strategy_config:
            return self.config
        
        # Convert strategy config to RiskManagementConfigResponse format
        strategy_config_conv = self._convert_strategy_to_risk_config(strategy_config)
        
        # Priority Rule 1: Override mode - strategy limits replace account limits
        if strategy_config.override_account_limits:
            return strategy_config_conv
        
        # Priority Rule 2: More restrictive mode - use most restrictive of both
        if strategy_config.use_more_restrictive:
            return self._merge_configs_most_restrictive(self.config, strategy_config_conv)
        
        # Priority Rule 3: Strategy-only mode - use strategy limits, ignore account limits
        return strategy_config_conv

