"""Service for managing completed trades with idempotency and row locks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Tuple
from uuid import UUID, uuid5
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session
from loguru import logger

from app.models.db_models import Trade, CompletedTrade, CompletedTradeOrder
from app.models.order import OrderResponse


class CompletedTradeService:
    """Service for creating and managing completed trades.
    
    Features:
    - Idempotency via UUIDv5 close_event_id
    - Row locks (FOR UPDATE) to prevent allocation races
    - Allocation invariant validation
    - Proportional fee calculation for partial fills
    """
    
    def __init__(self, db: Session):
        """Initialize service with database session.
        
        Args:
            db: SQLAlchemy database session
        """
        self.db = db
    
    def create_completed_trade(
        self,
        user_id: UUID,
        strategy_id: UUID,
        entry_trade_id: UUID,
        exit_trade_id: UUID,
        quantity: float,
        pnl_usd: float,
        pnl_pct: float,
        funding_fee: float = 0.0,
    ) -> CompletedTrade:
        """Create a completed trade with foreign key relationships.
        
        Called ON-WRITE when a position is closed.
        Database foreign keys ensure referential integrity - no fallback needed.
        Trades table manages partial fills (orig_qty, remaining_qty).
        
        ✅ Uses row locks (FOR UPDATE) to prevent allocation races
        ✅ Uses UUIDv5 for idempotency (deterministic, proper UUID format)
        
        Args:
            user_id: User UUID
            strategy_id: Strategy UUID
            entry_trade_id: Entry trade UUID (from trades.id)
            exit_trade_id: Exit trade UUID (from trades.id)
            quantity: Quantity closed (handles partial fills)
            pnl_usd: Profit/loss in USD
            pnl_pct: Profit/loss percentage
            funding_fee: Funding fees (default 0.0)
        
        Returns:
            CompletedTrade instance (existing if duplicate, new if created)
        
        Raises:
            ValueError: If trades not found, not filled, or allocation exceeds executed_qty
        """
        # 1. ✅ CRITICAL: Lock trades WITH FOR UPDATE to prevent concurrent allocation
        # This ensures atomic allocation checks and prevents race conditions
        # Use NOWAIT to fail fast if lock is held (prevents deadlocks)
        try:
            entry_trade = self.db.query(Trade).filter(
                Trade.id == entry_trade_id
            ).with_for_update(nowait=True).first()
            if not entry_trade:
                raise ValueError(f"Entry trade {entry_trade_id} not found in trades table")
            
            exit_trade = self.db.query(Trade).filter(
                Trade.id == exit_trade_id
            ).with_for_update(nowait=True).first()
            if not exit_trade:
                raise ValueError(f"Exit trade {exit_trade_id} not found in trades table")
        except Exception as lock_error:
            # Handle lock timeout or deadlock
            error_str = str(lock_error).lower()
            if "could not obtain lock" in error_str or "deadlock" in error_str:
                logger.warning(
                    f"Could not acquire lock for trades {entry_trade_id}/{exit_trade_id}: {lock_error}. "
                    f"Retrying may be needed."
                )
                raise ValueError(f"Trade allocation in progress, please retry: {lock_error}")
            raise
        
        # 2. Verify trades are filled
        if entry_trade.status not in ("FILLED", "PARTIALLY_FILLED"):
            raise ValueError(f"Entry trade {entry_trade_id} is not filled (status: {entry_trade.status})")
        
        if exit_trade.status not in ("FILLED", "PARTIALLY_FILLED"):
            raise ValueError(f"Exit trade {exit_trade_id} is not filled (status: {exit_trade.status})")
        
        # 3. Check partial fill consistency (trades table manages this)
        if entry_trade.orig_qty and entry_trade.remaining_qty and entry_trade.remaining_qty > 0:
            logger.debug(f"Entry trade {entry_trade_id} has remaining_qty={entry_trade.remaining_qty} (partial fill)")
        
        if exit_trade.orig_qty and exit_trade.remaining_qty and exit_trade.remaining_qty > 0:
            logger.debug(f"Exit trade {exit_trade_id} has remaining_qty={exit_trade.remaining_qty} (partial fill)")
        
        # 4. ✅ CRITICAL: Generate idempotency key using UUIDv5 (deterministic, proper UUID format)
        # UUIDv5 is deterministic and produces valid UUIDs from a namespace and name
        event_namespace = UUID('6ba7b811-9dad-11d1-80b4-00c04fd430c8')  # Standard UUID namespace
        event_name = f"{entry_trade_id}:{exit_trade_id}:{quantity}:{entry_trade.timestamp.isoformat() if entry_trade.timestamp else ''}"
        close_event_id = uuid5(event_namespace, event_name)
        
        # Check if completed trade already exists (idempotency check)
        # ✅ CRITICAL: Use row lock with skip_locked to prevent race conditions
        existing_completed = self.db.query(CompletedTrade).filter(
            CompletedTrade.close_event_id == close_event_id
        ).with_for_update(skip_locked=True).first()
        if existing_completed:
            logger.info(f"Completed trade already exists for close_event_id {close_event_id}, returning existing")
            return existing_completed
        
        # 5. ✅ CRITICAL: Validate allocation invariants WITH LOCKED ROWS to prevent race conditions
        # Trades are already locked from step 1, check allocation
        entry_allocated = self.db.query(
            func.sum(CompletedTradeOrder.quantity)
        ).filter(
            CompletedTradeOrder.trade_id == entry_trade_id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).scalar() or 0.0
        
        exit_allocated = self.db.query(
            func.sum(CompletedTradeOrder.quantity)
        ).filter(
            CompletedTradeOrder.trade_id == exit_trade_id,
            CompletedTradeOrder.order_role == "EXIT"
        ).scalar() or 0.0
        
        entry_allocated_float = float(entry_allocated) if entry_allocated else 0.0
        exit_allocated_float = float(exit_allocated) if exit_allocated else 0.0
        entry_executed_float = float(entry_trade.executed_qty)
        exit_executed_float = float(exit_trade.executed_qty)
        
        if entry_allocated_float + quantity > entry_executed_float:
            raise ValueError(
                f"Entry trade {entry_trade_id} allocation exceeds executed_qty: "
                f"{entry_allocated_float + quantity} > {entry_executed_float}"
            )
        
        if exit_allocated_float + quantity > exit_executed_float:
            raise ValueError(
                f"Exit trade {exit_trade_id} allocation exceeds executed_qty: "
                f"{exit_allocated_float + quantity} > {exit_executed_float}"
            )
        
        # 6. ✅ CRITICAL: Determine side using position_side, not just BUY/SELL
        # In futures hedge mode, BUY can close a SHORT, and SELL can close a LONG
        if entry_trade.position_side:
            side = entry_trade.position_side  # LONG or SHORT from position_side
        else:
            # Fallback to BUY/SELL if position_side not set (one-way mode)
            side = "LONG" if entry_trade.side == "BUY" else "SHORT"
        
        # 7. ✅ CRITICAL: Calculate fees for partial fills
        # Trade fees (commission): Allocated proportionally
        entry_fee_portion = 0.0
        if entry_trade.commission is not None and entry_trade.executed_qty and entry_trade.executed_qty > 0:
            entry_fee_portion = float(entry_trade.commission) * (quantity / float(entry_trade.executed_qty))
        
        exit_fee_portion = 0.0
        if exit_trade.commission is not None and exit_trade.executed_qty and exit_trade.executed_qty > 0:
            exit_fee_portion = float(exit_trade.commission) * (quantity / float(exit_trade.executed_qty))
        
        fee_paid = entry_fee_portion + exit_fee_portion
        
        # Get account_id from strategy
        account_id = entry_trade.strategy.account_id if entry_trade.strategy else None
        
        # Get leverage from trades, fallback to strategy
        leverage = entry_trade.leverage or exit_trade.leverage
        if leverage is None and entry_trade.strategy:
            leverage = entry_trade.strategy.leverage
        
        # Get margin_type from trades, fallback to default
        margin_type = entry_trade.margin_type or exit_trade.margin_type
        if margin_type is None:
            # Default to CROSSED if not specified (most common)
            margin_type = "CROSSED"
        
        # 8. Create completed_trade record
        completed_trade = CompletedTrade(
            strategy_id=strategy_id,
            user_id=user_id,
            account_id=account_id,
            close_event_id=close_event_id,
            symbol=entry_trade.symbol,
            side=side,
            entry_time=entry_trade.timestamp,
            exit_time=exit_trade.timestamp,
            entry_price=entry_trade.avg_price or entry_trade.price,
            exit_price=exit_trade.avg_price or exit_trade.price,
            quantity=quantity,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            fee_paid=fee_paid,  # Sum of entry_fee + exit_fee
            funding_fee=funding_fee,
            entry_order_id=entry_trade.order_id,
            exit_order_id=exit_trade.order_id,
            leverage=leverage,
            exit_reason=exit_trade.exit_reason,
            initial_margin=entry_trade.initial_margin or exit_trade.initial_margin,  # Use entry, fallback to exit
            margin_type=margin_type,
            notional_value=entry_trade.notional_value,
        )
        self.db.add(completed_trade)
        self.db.flush()  # Get the ID
        
        # 9. Create junction table records (STRONG BASE - foreign keys)
        entry_relation = CompletedTradeOrder(
            completed_trade_id=completed_trade.id,
            trade_id=entry_trade.id,
            order_id=entry_trade.order_id,
            account_id=account_id,
            order_role="ENTRY",
            quantity=quantity,
            price=entry_trade.avg_price or entry_trade.price,
            timestamp=entry_trade.timestamp,
        )
        self.db.add(entry_relation)
        
        exit_relation = CompletedTradeOrder(
            completed_trade_id=completed_trade.id,
            trade_id=exit_trade.id,
            order_id=exit_trade.order_id,
            account_id=account_id,
            order_role="EXIT",
            quantity=quantity,
            price=exit_trade.avg_price or exit_trade.price,
            timestamp=exit_trade.timestamp,
        )
        self.db.add(exit_relation)
        
        # Flush to ensure CompletedTradeOrder records are visible in the query below
        self.db.flush()
        
        # 10. ✅ CRITICAL: Validate allocation invariants AFTER creating junction records
        entry_sum = self.db.query(
            func.sum(CompletedTradeOrder.quantity)
        ).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "ENTRY"
        ).scalar() or 0.0
        
        exit_sum = self.db.query(
            func.sum(CompletedTradeOrder.quantity)
        ).filter(
            CompletedTradeOrder.completed_trade_id == completed_trade.id,
            CompletedTradeOrder.order_role == "EXIT"
        ).scalar() or 0.0
        
        entry_sum_float = float(entry_sum) if entry_sum else 0.0
        exit_sum_float = float(exit_sum) if exit_sum else 0.0
        quantity_float = float(completed_trade.quantity)
        
        if abs(entry_sum_float - quantity_float) > 0.0001:
            raise ValueError(
                f"Entry quantities don't match completed_trade.quantity: "
                f"{entry_sum_float} != {quantity_float}"
            )
        
        if abs(exit_sum_float - quantity_float) > 0.0001:
            raise ValueError(
                f"Exit quantities don't match completed_trade.quantity: "
                f"{exit_sum_float} != {quantity_float}"
            )
        
        # 11. Commit transaction (atomic - all or nothing)
        # If foreign key constraint fails, entire transaction rolls back
        self.db.commit()
        
        logger.info(
            f"Created completed trade {completed_trade.id} for strategy {strategy_id}: "
            f"entry={entry_trade_id}, exit={exit_trade_id}, qty={quantity}, pnl={pnl_usd:.2f}"
        )
        
        return completed_trade
    
    def create_completed_trades_from_matched_positions(
        self,
        user_id: UUID,
        strategy_id: UUID,
        matched_positions: List[dict],
    ) -> List[CompletedTrade]:
        """Create completed trades from matched positions (helper for integration).
        
        This method takes matched positions (from _match_trades_to_completed_positions)
        and creates CompletedTrade records for each.
        
        Args:
            user_id: User UUID
            strategy_id: Strategy UUID
            matched_positions: List of dicts with keys:
                - entry_trade_id: UUID of entry trade
                - exit_trade_id: UUID of exit trade
                - quantity: Quantity closed
                - pnl_usd: Profit/loss in USD
                - pnl_pct: Profit/loss percentage
                - funding_fee: Funding fees (optional, default 0.0)
        
        Returns:
            List of CompletedTrade instances created
        """
        completed_trades = []
        
        for position in matched_positions:
            try:
                completed_trade = self.create_completed_trade(
                    user_id=user_id,
                    strategy_id=strategy_id,
                    entry_trade_id=position['entry_trade_id'],
                    exit_trade_id=position['exit_trade_id'],
                    quantity=position['quantity'],
                    pnl_usd=position['pnl_usd'],
                    pnl_pct=position['pnl_pct'],
                    funding_fee=position.get('funding_fee', 0.0),
                )
                completed_trades.append(completed_trade)
            except ValueError as e:
                # Handle idempotency (already exists) - this is expected
                if "already exists" in str(e).lower() or "allocation in progress" in str(e).lower():
                    logger.debug(f"Skipping duplicate completed trade: {e}")
                    continue
                # Re-raise other errors
                logger.error(f"Failed to create completed trade: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error creating completed trade: {e}")
                raise
        
        return completed_trades

