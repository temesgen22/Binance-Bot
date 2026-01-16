"""Helper functions for creating completed trades when positions close."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session
from loguru import logger

from app.models.db_models import Trade, CompletedTradeOrder, Strategy, Account
from app.services.completed_trade_service import CompletedTradeService
from app.core.database import get_session_factory
from app.core.my_binance_client import BinanceClient


def create_completed_trades_on_position_close(
    user_id: UUID,
    strategy_id: str,  # Strategy ID string (not UUID)
    exit_trade_id: UUID,  # Exit trade UUID (just saved)
    exit_order_id: int,  # Exit order ID (Binance order ID)
    exit_quantity: float,  # Quantity closed
    exit_price: float,  # Exit price
    position_side: str,  # "LONG" or "SHORT"
    exit_reason: Optional[str] = None,
    db: Optional[Session] = None,  # Optional: for testing only (thread-unsafe if shared)
) -> List[UUID]:
    """Create completed trades when a position is closed.
    
    This function:
    1. Finds entry trades for the closed position
    2. Matches entry/exit trades (handling partial fills)
    3. Calculates PnL for each match
    4. Creates CompletedTrade records
    
    Called ON-WRITE when a position is closed.
    
    CRITICAL: Creates its own database session (thread-safe) unless `db` is provided.
    SQLAlchemy sessions are NOT thread-safe and should not be shared.
    The `db` parameter is ONLY for testing - never pass a session in production!
    
    Args:
        user_id: User UUID
        strategy_id: Strategy ID string (will be converted to UUID)
        exit_trade_id: Exit trade UUID (just saved to database)
        exit_order_id: Exit order ID (Binance order ID)
        exit_quantity: Quantity closed in this exit trade
        exit_price: Exit price
        position_side: Position side ("LONG" or "SHORT")
        exit_reason: Exit reason (optional)
        db: Optional database session (FOR TESTING ONLY - never use in production!)
    
    Returns:
        List of CompletedTrade UUIDs created
    
    Raises:
        ValueError: If strategy not found or trades cannot be matched
    """
    start_time = datetime.now(timezone.utc)
    logger.info(
        f"[{strategy_id}] 🔵 Starting completed trade creation: "
        f"exit_trade_id={exit_trade_id}, exit_order_id={exit_order_id}, "
        f"exit_quantity={exit_quantity}, position_side={position_side}, exit_reason={exit_reason}"
    )
    
    # CRITICAL FIX: Create a new database session for this thread (unless provided for testing)
    # SQLAlchemy sessions are NOT thread-safe and should not be shared across threads
    # Use session factory to create a new session in this thread
    # NOTE: `db` parameter is ONLY for testing - production code should never pass it
    should_close_db = False
    if db is None:
        session_factory = get_session_factory()
        db = session_factory()
        should_close_db = True
    
    try:
        # Get strategy UUID from database
        # Note: strategy_id can be either UUID string or strategy_id string
        # Try UUID first, then strategy_id string
        from uuid import UUID as UUIDType
        db_strategy = None
        try:
            strategy_uuid_obj = UUIDType(str(strategy_id))
            db_strategy = db.query(Strategy).filter(
                Strategy.id == strategy_uuid_obj,
                Strategy.user_id == user_id
            ).first()
            if db_strategy:
                logger.debug(
                    f"[{strategy_id}] Found strategy by UUID: id={db_strategy.id}, strategy_id={db_strategy.strategy_id}"
                )
        except (ValueError, TypeError) as e:
            logger.debug(
                f"[{strategy_id}] Not a valid UUID ({e}), trying strategy_id string lookup"
            )
            # Not a UUID, try strategy_id string
            db_strategy = db.query(Strategy).filter(
                Strategy.strategy_id == strategy_id,
                Strategy.user_id == user_id
            ).first()
            if db_strategy:
                logger.debug(
                    f"[{strategy_id}] Found strategy by strategy_id string: id={db_strategy.id}, strategy_id={db_strategy.strategy_id}"
                )
        
        if not db_strategy:
            # Log more details to help debug
            logger.warning(
                f"[{strategy_id}] Cannot create completed trades: Strategy not found in database. "
                f"user_id={user_id}, strategy_id_type={type(strategy_id)}. "
                f"Trying to query database for strategy..."
            )
            # Try to see if strategy exists at all (for debugging)
            all_strategies = db.query(Strategy).filter(Strategy.user_id == user_id).all()
            logger.debug(
                f"[{strategy_id}] Found {len(all_strategies)} strategies for user {user_id}. "
                f"Strategy IDs: {[s.strategy_id for s in all_strategies[:5]]}"
            )
            return []
        
        strategy_uuid = db_strategy.id
        
        # Get exit trade and validate it belongs to the same strategy
        exit_trade = db.query(Trade).filter(
            Trade.id == exit_trade_id,
            Trade.strategy_id == strategy_uuid  # ✅ CRITICAL: Ensure exit trade belongs to same strategy
        ).first()
        if not exit_trade:
            logger.warning(
                f"[{strategy_id}] Cannot create completed trades: Exit trade {exit_trade_id} not found "
                f"or does not belong to strategy {strategy_uuid}"
            )
            return []
        
        # Log exit trade details for debugging
        logger.debug(
            f"[{strategy_id}] Exit trade validation: order_id={exit_trade.order_id}, "
            f"strategy_id={exit_trade.strategy_id}, timestamp={exit_trade.timestamp}, "
            f"side={exit_trade.side}, price={exit_trade.avg_price or exit_trade.price}"
        )
        
        # ✅ CRITICAL: Validate position_side matches exit trade side
        # LONG position closes with SELL, SHORT position closes with BUY
        # NOTE: This validation helps catch state sync issues, but we log as warning instead of error
        # to allow the system to continue and use the exit trade side as the source of truth
        if position_side == "LONG" and exit_trade.side != "SELL":
            logger.warning(
                f"[{strategy_id}] ⚠️ Position side mismatch: LONG position but exit trade is {exit_trade.side} "
                f"(expected SELL). Order ID: {exit_trade.order_id}. "
                f"Using exit trade side as source of truth. This may indicate a state sync issue."
            )
            # Don't return - continue with exit trade side as source of truth
            # Update position_side to match exit trade
            if exit_trade.side == "BUY":
                position_side = "SHORT"  # BUY closes SHORT
                logger.info(f"[{strategy_id}] Corrected position_side to SHORT based on exit trade")
        elif position_side == "SHORT" and exit_trade.side != "BUY":
            logger.warning(
                f"[{strategy_id}] ⚠️ Position side mismatch: SHORT position but exit trade is {exit_trade.side} "
                f"(expected BUY). Order ID: {exit_trade.order_id}. "
                f"Using exit trade side as source of truth. This may indicate a state sync issue."
            )
            # Don't return - continue with exit trade side as source of truth
            # Update position_side to match exit trade
            if exit_trade.side == "SELL":
                position_side = "LONG"  # SELL closes LONG
                logger.info(f"[{strategy_id}] Corrected position_side to LONG based on exit trade")
        
        # Determine entry side based on position_side
        # LONG position: entry was BUY, exit is SELL
        # SHORT position: entry was SELL, exit is BUY
        if position_side == "LONG":
            entry_side = "BUY"
        elif position_side == "SHORT":
            entry_side = "SELL"
        else:
            logger.warning(
                f"[{strategy_id}] Cannot create completed trades: Invalid position_side {position_side}"
            )
            return []
        
        # Find entry trades that haven't been fully allocated
        # Query for entry trades with same strategy, opposite side, and remaining allocation
        entry_trades = db.query(Trade).filter(
            Trade.strategy_id == strategy_uuid,
            Trade.side == entry_side,
            Trade.status.in_(["FILLED", "PARTIALLY_FILLED"]),
        ).order_by(Trade.timestamp.asc()).all()
        
        if not entry_trades:
            logger.debug(
                f"No entry trades found for strategy {strategy_id} to match with exit trade {exit_order_id}"
            )
            return []
        
        # Calculate remaining allocation for each entry trade
        entry_trades_with_allocation = []
        for entry_trade in entry_trades:
            # Get already allocated quantity for this entry trade
            allocated = db.query(
                func.sum(CompletedTradeOrder.quantity)
            ).filter(
                CompletedTradeOrder.trade_id == entry_trade.id,
                CompletedTradeOrder.order_role == "ENTRY"
            ).scalar() or 0.0
            
            allocated_float = float(allocated) if allocated else 0.0
            executed_float = float(entry_trade.executed_qty) if entry_trade.executed_qty else 0.0
            remaining = executed_float - allocated_float
            
            if remaining > 0.0001:  # Has remaining allocation
                entry_trades_with_allocation.append({
                    "trade": entry_trade,
                    "remaining": remaining,
                    "allocated": allocated_float,
                })
        
        if not entry_trades_with_allocation:
            logger.debug(
                f"No entry trades with remaining allocation for strategy {strategy_id}"
            )
            return []
        
        # Match exit quantity to entry trades (FIFO - first in, first out)
        completed_trade_service = CompletedTradeService(db)
        completed_trade_ids = []
        remaining_exit_qty = exit_quantity
        
        for entry_info in entry_trades_with_allocation:
            if remaining_exit_qty <= 0:
                break
            
            entry_trade = entry_info["trade"]
            entry_remaining = entry_info["remaining"]
            
            # Quantity to close: min of remaining exit qty and entry remaining
            close_qty = min(remaining_exit_qty, entry_remaining)
            
            # Calculate PnL
            entry_price = float(entry_trade.avg_price or entry_trade.price)
            
            if position_side == "LONG":
                # LONG: (exit_price - entry_price) * quantity - fees
                gross_pnl = (exit_price - entry_price) * close_qty
            else:  # SHORT
                # SHORT: (entry_price - exit_price) * quantity - fees
                gross_pnl = (entry_price - exit_price) * close_qty
            
            # Calculate fees (proportional) - sum of entry + exit fees
            entry_fee = 0.0
            if entry_trade.commission is not None and entry_trade.executed_qty and entry_trade.executed_qty > 0:
                entry_fee = float(entry_trade.commission) * (close_qty / float(entry_trade.executed_qty))
            
            exit_fee = 0.0
            if exit_trade.commission is not None and exit_trade.executed_qty and exit_trade.executed_qty > 0:
                exit_fee = float(exit_trade.commission) * (close_qty / float(exit_trade.executed_qty))
            
            total_fee = entry_fee + exit_fee  # Sum of entry + exit fees
            net_pnl = gross_pnl - total_fee
            
            # Calculate PnL percentage
            entry_notional = entry_price * close_qty
            pnl_pct = (net_pnl / entry_notional) * 100 if entry_notional > 0 else 0.0
            
            # Fetch funding fees from Binance API
            funding_fee = 0.0
            try:
                # Get account_id from strategy
                account_id = db_strategy.account_id if db_strategy else None
                if account_id:
                    # Get account from database
                    account = db.query(Account).filter(Account.id == account_id).first()
                    if account:
                        # Create BinanceClient from account config
                        from app.services.account_service import AccountService
                        account_service = AccountService(db)
                        
                        # Get account config (decrypted)
                        account_config = account_service._db_account_to_config(account)
                        
                        # Create BinanceClient
                        binance_client = BinanceClient(
                            api_key=account_config.api_key,
                            api_secret=account_config.api_secret,
                            testnet=account_config.testnet
                        )
                        
                        # Fetch funding fees for the period between entry and exit
                        entry_time_ms = int(entry_trade.timestamp.timestamp() * 1000)
                        exit_time_ms = int(exit_trade.timestamp.timestamp() * 1000)
                        
                        funding_fees = binance_client.get_funding_fees(
                            symbol=entry_trade.symbol,
                            start_time=entry_time_ms,
                            end_time=exit_time_ms,
                            limit=1000
                        )
                        
                        # Sum funding fees (negative = paid, positive = received)
                        # For completed trades, we sum all funding fees (absolute value)
                        # Negative income = we paid funding fees (LONG position)
                        # Positive income = we received funding fees (SHORT position)
                        # For reporting, we track the absolute value of all funding fees
                        for fee_record in funding_fees:
                            income = float(fee_record.get("income", 0))
                            # Sum absolute value of all funding fees (both paid and received)
                            funding_fee += abs(income)
                        
                        if funding_fee > 0:
                            logger.debug(
                                f"[{strategy_id}] Fetched funding fees: {funding_fee:.8f} USDT "
                                f"for period {entry_trade.timestamp} to {exit_trade.timestamp}"
                            )
            except Exception as exc:
                logger.warning(
                    f"[{strategy_id}] Could not fetch funding fees: {exc}. "
                    f"Using default 0.0. This is non-critical.",
                    exc_info=True
                )
                funding_fee = 0.0
            
            # Create completed trade
            try:
                # Log entry/exit trade details for debugging
                logger.debug(
                    f"[{strategy_id}] Matching entry/exit trades: "
                    f"entry_order_id={entry_trade.order_id}, entry_timestamp={entry_trade.timestamp}, "
                    f"entry_price={entry_price}, exit_order_id={exit_order_id}, "
                    f"exit_timestamp={exit_trade.timestamp}, exit_price={exit_price}, "
                    f"close_qty={close_qty}, position_side={position_side}"
                )
                
                completed_trade = completed_trade_service.create_completed_trade(
                    user_id=user_id,
                    strategy_id=strategy_uuid,
                    entry_trade_id=entry_trade.id,
                    exit_trade_id=exit_trade_id,
                    quantity=close_qty,
                    pnl_usd=net_pnl,
                    pnl_pct=pnl_pct,
                    funding_fee=funding_fee,  # Fetched from Binance API
                )
                completed_trade_ids.append(completed_trade.id)
                logger.info(
                    f"[{strategy_id}] ✅ Created completed trade {completed_trade.id}: "
                    f"entry={entry_trade.order_id} (ts={entry_trade.timestamp}), "
                    f"exit={exit_order_id} (ts={exit_trade.timestamp}), "
                    f"qty={close_qty}, pnl={net_pnl:.2f}"
                )
            except ValueError as e:
                # Handle idempotency (already exists) - this is expected
                error_msg = str(e).lower()
                if "already exists" in error_msg or "allocation in progress" in error_msg or "duplicate" in error_msg or "idempotency" in error_msg:
                    logger.debug(
                        f"[{strategy_id}] Skipping duplicate/idempotent completed trade: {e}. "
                        f"Entry={entry_trade.order_id}, Exit={exit_order_id}"
                    )
                    continue
                # Re-raise other validation errors with full context
                logger.error(
                    f"[{strategy_id}] ❌ Failed to create completed trade: {e}. "
                    f"Entry trade: order_id={entry_trade.order_id}, side={entry_trade.side}, "
                    f"Exit trade: order_id={exit_order_id}, side={exit_trade.side}, "
                    f"Position side: {position_side}, Close qty: {close_qty}",
                    exc_info=True
                )
                raise
            except Exception as e:
                # Catch any other unexpected errors
                logger.error(
                    f"[{strategy_id}] ❌ Unexpected error creating completed trade: {e}. "
                    f"Entry trade: order_id={entry_trade.order_id}, Exit trade: order_id={exit_order_id}",
                    exc_info=True
                )
                raise
            
            remaining_exit_qty -= close_qty
        
        if remaining_exit_qty > 0.0001:
            logger.warning(
                f"[{strategy_id}] Unmatched exit quantity remaining after processing all entry trades: "
                f"{remaining_exit_qty} for exit order {exit_order_id}. "
                f"This may indicate a data inconsistency or an unmatched entry trade."
            )
        
        # Log completion metrics
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.info(
            f"[{strategy_id}] ✅ Completed trade creation finished: "
            f"created={len(completed_trade_ids)} completed trades, "
            f"duration={duration_ms:.2f}ms, "
            f"exit_order_id={exit_order_id}"
        )
        
        return completed_trade_ids
        
    except Exception as e:
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.error(
            f"[{strategy_id}] ❌ CRITICAL: Error in create_completed_trades_on_position_close "
            f"(duration={duration_ms:.2f}ms): {e}",
            exc_info=True
        )
        # Rollback on error
        try:
            db.rollback()
        except Exception:
            pass
        # Don't fail position closing if completed trade creation fails
        return []
    finally:
        # Only close database if we created it (not if it was passed for testing)
        if should_close_db:
            try:
                db.close()
            except Exception:
                pass

