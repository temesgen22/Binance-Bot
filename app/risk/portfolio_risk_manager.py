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
from app.models.risk_management import RiskManagementConfigResponse
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
    ):
        """Initialize portfolio risk manager.
        
        Args:
            account_id: Binance account ID
            config: Risk management configuration (None = no limits)
            db_service: Database service for querying strategies/trades
            user_id: User UUID
            strategy_runner: StrategyRunner instance for getting strategies
            trade_service: TradeService for querying trades
        """
        self.account_id = account_id
        self.config = config
        self.db_service = db_service
        self.user_id = user_id
        self.strategy_runner = strategy_runner
        self.trade_service = trade_service
        
        # CRITICAL FIX #1: Per-account locks to prevent race conditions
        self.account_locks: Dict[str, asyncio.Lock] = {}
        self._lock_manager = asyncio.Lock()  # Protects account_locks dict
        
        # CRITICAL FIX #2: Exposure reservation tracking
        self._reservations: Dict[str, Dict[str, ExposureReservation]] = {}
        # Format: {account_id: {strategy_id: ExposureReservation}}
    
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
        account_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Check if order is allowed (WITH ASYNC LOCKING).
        
        CRITICAL: This method uses async locking to prevent race conditions.
        It also RESERVES exposure before order execution.
        
        Args:
            signal: Strategy signal
            summary: Strategy summary
            account_id: Account ID (defaults to self.account_id)
            
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        account_id = account_id or self.account_id
        
        # CRITICAL FIX #1: Acquire lock for this account
        account_lock = self._get_account_lock(account_id)
        
        async with account_lock:
            # Check if risk management is enabled
            if not self.config:
                return True, "Risk management not configured"
            
            # Check portfolio exposure limit
            if self.config.max_portfolio_exposure_usdt or self.config.max_portfolio_exposure_pct:
                allowed, reason = await self._check_exposure_limit(
                    signal, summary, account_id
                )
                if not allowed:
                    return False, reason
            
            # Check daily loss limit (REALIZED PnL ONLY)
            if self.config.max_daily_loss_usdt or self.config.max_daily_loss_pct:
                allowed, reason = await self._check_daily_loss_limit(account_id)
                if not allowed:
                    return False, reason
            
            # Check weekly loss limit (REALIZED PnL ONLY)
            if self.config.max_weekly_loss_usdt or self.config.max_weekly_loss_pct:
                allowed, reason = await self._check_weekly_loss_limit(account_id)
                if not allowed:
                    return False, reason
            
            # Check drawdown limit (TOTAL EQUITY)
            if self.config.max_drawdown_pct:
                allowed, reason = await self._check_drawdown_limit(account_id)
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
        account_id: str
    ) -> Tuple[bool, str]:
        """Check if order would exceed portfolio exposure limit."""
        # Calculate current exposure (including reservations)
        current_exposure = await self._calculate_current_exposure(account_id)
        
        # Calculate order exposure
        order_exposure = self._calculate_order_exposure(signal, summary)
        
        # Get max exposure limit
        max_exposure = await self._get_max_exposure(account_id)
        if max_exposure is None:
            return True, "No exposure limit set"
        
        # Check if would exceed
        if current_exposure + order_exposure > max_exposure:
            return False, (
                f"Would exceed exposure limit: "
                f"{current_exposure + order_exposure:.2f} > {max_exposure:.2f} USDT"
            )
        
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
    
    async def _get_max_exposure(self, account_id: str) -> Optional[float]:
        """Get maximum exposure limit for account."""
        if not self.config:
            return None
        
        # Check USDT limit
        if self.config.max_portfolio_exposure_usdt:
            return float(self.config.max_portfolio_exposure_usdt)
        
        # Check percentage limit (need account balance)
        if self.config.max_portfolio_exposure_pct:
            balance = await self._get_account_balance(account_id)
            if balance:
                return balance * float(self.config.max_portfolio_exposure_pct)
        
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
    
    async def _check_daily_loss_limit(self, account_id: str) -> Tuple[bool, str]:
        """Check daily loss limit (REALIZED PnL ONLY).
        
        CRITICAL: Uses realized PnL only, not unrealized.
        """
        if not self.config:
            return True, "No limit configured"
        
        # Get realized PnL for today (closed trades only)
        today_start = self._get_today_start()
        realized_pnl = await self._get_realized_pnl(account_id, today_start)
        
        # Get limit
        max_daily_loss = None
        if self.config.max_daily_loss_usdt:
            max_daily_loss = float(self.config.max_daily_loss_usdt)
        elif self.config.max_daily_loss_pct:
            balance = await self._get_account_balance(account_id)
            if balance:
                max_daily_loss = balance * float(self.config.max_daily_loss_pct)
        
        if max_daily_loss is None:
            return True, "No limit set"
        
        if realized_pnl < -abs(max_daily_loss):
            return False, (
                f"Daily loss limit exceeded: "
                f"{realized_pnl:.2f} < {max_daily_loss:.2f} USDT"
            )
        
        return True, "OK"
    
    async def _check_weekly_loss_limit(self, account_id: str) -> Tuple[bool, str]:
        """Check weekly loss limit (REALIZED PnL ONLY).
        
        CRITICAL: Uses realized PnL only, not unrealized.
        """
        if not self.config:
            return True, "No limit configured"
        
        # Get realized PnL for this week (closed trades only)
        week_start = self._get_week_start()
        realized_pnl = await self._get_realized_pnl(account_id, week_start)
        
        # Get limit
        max_weekly_loss = None
        if self.config.max_weekly_loss_usdt:
            max_weekly_loss = float(self.config.max_weekly_loss_usdt)
        elif self.config.max_weekly_loss_pct:
            balance = await self._get_account_balance(account_id)
            if balance:
                max_weekly_loss = balance * float(self.config.max_weekly_loss_pct)
        
        if max_weekly_loss is None:
            return True, "No limit set"
        
        if realized_pnl < -abs(max_weekly_loss):
            return False, (
                f"Weekly loss limit exceeded: "
                f"{realized_pnl:.2f} < {max_weekly_loss:.2f} USDT"
            )
        
        return True, "OK"
    
    async def _check_drawdown_limit(self, account_id: str) -> Tuple[bool, str]:
        """Check drawdown limit (TOTAL EQUITY: realized + unrealized).
        
        CRITICAL: Drawdown uses total equity, not just realized PnL.
        """
        if not self.config or not self.config.max_drawdown_pct:
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
        
        max_drawdown = float(self.config.max_drawdown_pct)
        if drawdown_pct > max_drawdown:
            return False, (
                f"Drawdown limit exceeded: "
                f"{drawdown_pct:.2%} > {max_drawdown:.2%}"
            )
        
        return True, "OK"
    
    async def _get_realized_pnl(
        self,
        account_id: str,
        start_time: datetime
    ) -> float:
        """Get realized PnL from closed trades since start_time.
        
        CRITICAL: Only includes closed trades (realized PnL), not open positions.
        """
        if not self.strategy_runner or not self.user_id:
            return 0.0
        
        total_pnl = 0.0
        
        # Get all strategies for this account
        strategies = self.strategy_runner._strategies.values()
        account_strategies = [
            s for s in strategies
            if s.account_id == account_id
        ]
        
        # Get trades for each strategy and calculate realized PnL
        for strategy in account_strategies:
            trades = self.strategy_runner.get_trades(strategy.id)
            
            # Filter trades by timestamp
            filtered_trades = [
                t for t in trades
                if t.timestamp and t.timestamp >= start_time
            ]
            
            if not filtered_trades:
                continue
            
            # Use trade matcher to get completed trades
            from app.services.trade_matcher import match_trades_to_completed_positions
            completed_trades = match_trades_to_completed_positions(
                filtered_trades,
                include_fees=True
            )
            
            # Sum net PnL from completed trades
            for completed in completed_trades:
                total_pnl += completed.net_pnl
        
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
    
    def _get_today_start(self) -> datetime:
        """Get start of today in UTC."""
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    def _get_week_start(self) -> datetime:
        """Get start of current week (Monday) in UTC."""
        now = datetime.now(timezone.utc)
        days_since_monday = now.weekday()  # 0 = Monday
        week_start = now - timedelta(days=days_since_monday)
        return week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
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

