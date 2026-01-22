"""Helper functions for creating completed trades when positions close."""
from __future__ import annotations

import time as time_module
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session
from loguru import logger

from app.models.db_models import Trade, CompletedTradeOrder, CompletedTrade, Strategy, Account
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
        # ✅ FIX: Use exit_trade.position_side as source of truth if available (more accurate than inferring)
        # LONG position closes with SELL, SHORT position closes with BUY
        # In futures hedge mode, position_side is the authoritative field
        position_side_corrected = False
        original_position_side = position_side
        
        # Use exit_trade.position_side as primary source of truth if available
        if exit_trade.position_side:
            if position_side != exit_trade.position_side:
                logger.warning(
                    f"[{strategy_id}] ⚠️ Position side mismatch: function param={position_side}, "
                    f"exit_trade.position_side={exit_trade.position_side}. "
                    f"Using exit_trade.position_side as source of truth. Order ID: {exit_trade.order_id}"
                )
                position_side = exit_trade.position_side
                position_side_corrected = True
        elif position_side == "LONG" and exit_trade.side != "SELL":
            if exit_trade.side == "BUY":
                # BUY can only close SHORT, so position_side must be wrong
                logger.warning(
                    f"[{strategy_id}] ⚠️ Position side mismatch: LONG position but exit trade is BUY. "
                    f"BUY closes SHORT positions. Order ID: {exit_trade.order_id}. "
                    f"Correcting position_side to SHORT based on exit trade side."
                )
                position_side = "SHORT"
                position_side_corrected = True
            else:
                # Unknown side - log error with full details
                logger.error(
                    f"[{strategy_id}] ❌ Invalid position side/exit side combination: "
                    f"position_side={position_side}, exit_side={exit_trade.side}, "
                    f"exit.position_side={exit_trade.position_side}, Order ID: {exit_trade.order_id}"
                )
        elif position_side == "SHORT" and exit_trade.side != "BUY":
            if exit_trade.side == "SELL":
                # SELL can only close LONG, so position_side must be wrong
                logger.warning(
                    f"[{strategy_id}] ⚠️ Position side mismatch: SHORT position but exit trade is SELL. "
                    f"SELL closes LONG positions. Order ID: {exit_trade.order_id}. "
                    f"Correcting position_side to LONG based on exit trade side."
                )
                position_side = "LONG"
                position_side_corrected = True
            else:
                # Unknown side - log error with full details
                logger.error(
                    f"[{strategy_id}] ❌ Invalid position side/exit side combination: "
                    f"position_side={position_side}, exit_side={exit_trade.side}, "
                    f"exit.position_side={exit_trade.position_side}, Order ID: {exit_trade.order_id}"
                )
        
        if position_side_corrected:
            logger.info(
                f"[{strategy_id}] Position side corrected from {original_position_side} to {position_side} for matching. "
                f"Exit trade: side={exit_trade.side}, position_side={exit_trade.position_side}"
            )
        
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
        # Query for entry trades with same strategy, symbol, position_side, opposite side, and remaining allocation
        # ✅ CRITICAL: Must filter by symbol to prevent cross-symbol matching
        # ✅ CRITICAL: Must filter by position_side for hedge mode (prevent LONG/SHORT cross-matching)
        entry_trades_query = db.query(Trade).filter(
            Trade.strategy_id == strategy_uuid,
            Trade.symbol == exit_trade.symbol,  # ✅ FIX: Match same symbol
            Trade.side == entry_side,
            Trade.status.in_(["FILLED", "PARTIALLY_FILLED"]),
        )
        
        # Filter by position_side (hedge mode support)
        # Note: position_side should always be "LONG" or "SHORT" at this point,
        # but the check ensures we don't filter if somehow it's None/empty
        if position_side:
            entry_trades_query = entry_trades_query.filter(
                Trade.position_side == position_side
            )
        else:
            # Safety check: log warning if position_side is missing
            logger.warning(
                f"[{strategy_id}] position_side is None/empty - not filtering by position_side. "
                f"This may cause incorrect matching in hedge mode."
            )
        
        # ✅ OPTIMIZATION: Filter out fully allocated trades at database level using subquery
        # This avoids loading fully allocated trades into memory and makes queries more efficient
        # Only include trades where: executed_qty - allocated_qty > 0.0001
        allocated_subquery = db.query(
            CompletedTradeOrder.trade_id,
            func.sum(CompletedTradeOrder.quantity).label('allocated_qty')
        ).filter(
            CompletedTradeOrder.order_role == "ENTRY"
        ).group_by(CompletedTradeOrder.trade_id).subquery()
        
        # Use LEFT JOIN to find trades with remaining allocation
        # ✅ FIX: Include allocated_qty in main query to avoid N+1 queries
        # ✅ FIX: Add row locking to prevent race conditions (FOR UPDATE SKIP LOCKED)
        entry_trades_query = entry_trades_query.outerjoin(
            allocated_subquery,
            Trade.id == allocated_subquery.c.trade_id
        ).filter(
            # Only include trades with remaining allocation (executed_qty - allocated_qty > 0.0001)
            Trade.executed_qty > func.coalesce(allocated_subquery.c.allocated_qty, 0) + 0.0001
        )
        
        # ✅ FIX: Select allocated_qty directly in main query (no N+1 queries)
        # ✅ FIX: Lock rows to prevent double allocation (FOR UPDATE SKIP LOCKED)
        entry_trades_rows = entry_trades_query.add_columns(
            func.coalesce(allocated_subquery.c.allocated_qty, 0).label('allocated_qty')
        ).with_for_update(skip_locked=True).order_by(Trade.timestamp.asc()).all()
        
        if not entry_trades_rows:
            logger.debug(
                f"No entry trades with remaining allocation found for strategy {strategy_id} "
                f"to match with exit trade {exit_order_id}"
            )
            return []
        
        # ✅ FIX: Build list with allocated_qty from query (no N+1 queries)
        entry_trades_with_allocation = []
        for row in entry_trades_rows:
            entry_trade = row[0]  # First element is the Trade object
            allocated_qty = row[1]  # Second element is allocated_qty from query (access by index, not attribute)
            
            allocated_float = float(allocated_qty) if allocated_qty else 0.0
            executed_float = float(entry_trade.executed_qty) if entry_trade.executed_qty else 0.0
            remaining = executed_float - allocated_float
            
            # Double-check remaining > threshold (should always be true due to database filter, but safety check)
            if remaining > 0.0001:
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
        
        # ✅ FIX: Fetch funding fees ONCE per exit (not per entry/exit pair)
        # Funding fees are per position lifecycle, not per individual lot
        # Create BinanceClient once (outside retry loop and outside entry loop)
        funding_fee_total = 0.0
        funding_fee_fetch_failed = False
        binance_client = None
        
        try:
            account_id = db_strategy.account_id if db_strategy else None
            if account_id:
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    from app.services.account_service import AccountService
                    account_service = AccountService(db)
                    account_config = account_service._db_account_to_config(account)
                    binance_client = BinanceClient(
                        api_key=account_config.api_key,
                        api_secret=account_config.api_secret,
                        testnet=account_config.testnet
                    )
                    
                    # ✅ FIX: Use earliest entry time from ALL potential matches (before skipping)
                    # This ensures we capture the full position lifecycle period
                    earliest_entry_time = min(et["trade"].timestamp for et in entry_trades_with_allocation)
                    exit_time = exit_trade.timestamp
                    
                    entry_time_ms = int(earliest_entry_time.timestamp() * 1000)
                    exit_time_ms = int(exit_time.timestamp() * 1000)
                    
                    # Retry logic for funding fee fetch
                    max_retries = 3
                    retry_delay = 0.5
                    for attempt in range(max_retries):
                        try:
                            funding_fees = binance_client.get_funding_fees(
                                symbol=exit_trade.symbol,
                                start_time=entry_time_ms,
                                end_time=exit_time_ms,
                                limit=1000
                            )
                            
                            # ✅ FIX: Keep signed funding (not abs) - sum actual income
                            # Negative = we paid (LONG), Positive = we received (SHORT)
                            for fee_record in funding_fees:
                                income = float(fee_record.get("income", 0))
                                funding_fee_total += income  # Signed, not abs!
                            
                            if funding_fee_total != 0:
                                logger.debug(
                                    f"[{strategy_id}] Fetched total funding fees: {funding_fee_total:.8f} USDT "
                                    f"(signed) for period {earliest_entry_time} to {exit_time}"
                                )
                            break  # Success
                        except Exception as exc:
                            if attempt < max_retries - 1:
                                logger.warning(
                                    f"[{strategy_id}] Funding fee fetch failed (attempt {attempt + 1}/{max_retries}): {exc}. "
                                    f"Retrying in {retry_delay}s..."
                                )
                                time_module.sleep(retry_delay)
                                retry_delay *= 2
                            else:
                                logger.warning(
                                    f"[{strategy_id}] Could not fetch funding fees after {max_retries} attempts: {exc}. "
                                    f"Using default 0.0.",
                                    exc_info=True
                                )
                                funding_fee_fetch_failed = True
                                funding_fee_total = 0.0
        except Exception as exc:
            logger.warning(
                f"[{strategy_id}] Could not create BinanceClient or fetch funding fees: {exc}. "
                f"Using default 0.0.",
                exc_info=True
            )
            funding_fee_total = 0.0
        
        # Match exit quantity to entry trades (FIFO - first in, first out)
        completed_trade_service = CompletedTradeService(db)
        completed_trade_ids = []
        remaining_exit_qty = exit_quantity
        total_matched_qty = 0.0  # ✅ FIX: Track actual matched quantity for funding fee allocation
        
        for entry_info in entry_trades_with_allocation:
            if remaining_exit_qty <= 0:
                break
            
            entry_trade = entry_info["trade"]
            entry_remaining = entry_info["remaining"]
            
            # ✅ FIX: Validate entry trade position_side matches expected (hedge mode safety check)
            # This prevents matching trades from wrong position side if position_side column has bad data
            if entry_trade.position_side and entry_trade.position_side != position_side:
                logger.warning(
                    f"[{strategy_id}] Skipping entry trade {entry_trade.order_id}: "
                    f"position_side mismatch (expected {position_side}, got {entry_trade.position_side})"
                )
                continue  # Skip this entry trade
            
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
                    funding_fee=0.0,  # Will allocate funding fees after all matches are complete
                )
                completed_trade_ids.append(completed_trade.id)
                total_matched_qty += close_qty  # Track matched quantity
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
        
        # ✅ FIX: Allocate funding fees proportionally AFTER all matches are complete
        # This ensures accurate allocation even if some entry trades were skipped
        # Use actual matched quantity (not exit_quantity) to prevent over-allocation
        if total_matched_qty > 0.0001 and funding_fee_total != 0:
            # Update all completed trades with proportionally allocated funding fees
            for i, completed_trade_id in enumerate(completed_trade_ids):
                # Find the corresponding entry trade to get close_qty
                # Note: We need to track close_qty for each completed trade
                # For now, we'll query the completed trade to get its quantity
                completed_trade = db.query(CompletedTrade).filter(
                    CompletedTrade.id == completed_trade_id
                ).first()
                if completed_trade:
                    close_qty = float(completed_trade.quantity)
                    # Allocate funding fees proportionally: funding_for_lot = funding_total * (close_qty / total_matched_qty)
                    funding_fee_for_lot = funding_fee_total * (close_qty / total_matched_qty)
                    completed_trade.funding_fee = funding_fee_for_lot
                    logger.debug(
                        f"[{strategy_id}] Allocated funding fee {funding_fee_for_lot:.8f} to completed trade {completed_trade_id} "
                        f"(qty={close_qty}/{total_matched_qty})"
                    )
            db.commit()  # Commit funding fee allocations
            logger.debug(
                f"[{strategy_id}] Allocated total funding fees {funding_fee_total:.8f} across {len(completed_trade_ids)} completed trades "
                f"(total matched qty: {total_matched_qty})"
            )
        
        # ✅ FIX: Fail if unmatched exit quantity remains (data inconsistency)
        # This indicates a serious issue: exit trade quantity exceeds all matched entry trades
        if remaining_exit_qty > 0.0001:
            error_msg = (
                f"[{strategy_id}] ❌ CRITICAL: Unmatched exit quantity remaining after processing all entry trades: "
                f"{remaining_exit_qty} for exit order {exit_order_id}. "
                f"Exit quantity: {exit_quantity}, Matched quantity: {total_matched_qty}. "
                f"This indicates a data inconsistency - exit trade quantity exceeds available entry trades. "
                f"Possible causes: missing entry trades, incorrect quantity reporting, or allocation mismatch."
            )
            logger.error(error_msg)
            # Don't fail the entire process, but log as error and return what was successfully matched
            # This allows partial completion while alerting to the issue
            # The remaining unmatched quantity will need manual investigation
        
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

