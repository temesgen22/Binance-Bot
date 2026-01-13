"""
Backfill script to create CompletedTrade records for historical trades.

This script:
1. Finds all closed positions (entry trades with matching exit trades)
2. Creates CompletedTrade records for historical data
3. Handles partial fills correctly
4. Can be run incrementally (idempotent)

Usage:
    python scripts/backfill_completed_trades.py [--strategy-id STRATEGY_ID] [--dry-run]
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID
import argparse

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker
from loguru import logger

from app.core.config import get_settings
from app.models.db_models import (
    Base, Trade, CompletedTrade, CompletedTradeOrder, Strategy, User
)
from app.services.completed_trade_service import CompletedTradeService


def find_closed_positions(
    db: Session,
    user_id: UUID,
    strategy_id: Optional[str] = None,
    limit: Optional[int] = None
) -> List[dict]:
    """Find closed positions (entry trades with matching exit trades).
    
    Returns list of dicts with:
    - entry_trade: Trade object
    - exit_trade: Trade object
    - quantity: Quantity closed
    - position_side: "LONG" or "SHORT"
    """
    # Get all strategies for user
    query = db.query(Strategy).filter(Strategy.user_id == user_id)
    if strategy_id:
        # Try UUID first, then strategy_id string
        try:
            strategy_uuid = UUID(str(strategy_id))
            query = query.filter(Strategy.id == strategy_uuid)
        except ValueError:
            query = query.filter(Strategy.strategy_id == strategy_id)
    
    strategies = query.all()
    if not strategies:
        logger.warning(f"No strategies found for user {user_id}")
        return []
    
    strategy_uuids = [s.id for s in strategies]
    
    # Get all FILLED or PARTIALLY_FILLED trades
    all_trades = db.query(Trade).filter(
        Trade.user_id == user_id,
        Trade.strategy_id.in_(strategy_uuids),
        Trade.status.in_(["FILLED", "PARTIALLY_FILLED"])
    ).order_by(Trade.timestamp.asc()).all()
    
    # Match entry/exit trades using FIFO
    closed_positions = []
    position_queue = []  # (quantity, entry_trade, side)
    
    for trade in all_trades:
        if trade.side == "BUY":
            # Check if this closes a SHORT position
            if position_queue and position_queue[0][2] == "SHORT":
                entry_info = position_queue[0]
                entry_qty = entry_info[0]
                entry_trade = entry_info[1]
                
                close_qty = min(trade.executed_qty, entry_qty)
                
                closed_positions.append({
                    "entry_trade": entry_trade,
                    "exit_trade": trade,
                    "quantity": float(close_qty),
                    "position_side": "SHORT",
                })
                
                # Update queue
                if close_qty >= entry_qty:
                    position_queue.pop(0)
                else:
                    position_queue[0] = (entry_qty - close_qty, entry_trade, "SHORT")
            
            # Add remaining quantity to LONG position queue
            remaining_qty = trade.executed_qty
            for entry_info in position_queue:
                if entry_info[2] == "SHORT":
                    close_qty = min(remaining_qty, entry_info[0])
                    remaining_qty -= close_qty
                    if close_qty > 0:
                        closed_positions.append({
                            "entry_trade": entry_info[1],
                            "exit_trade": trade,
                            "quantity": float(close_qty),
                            "position_side": "SHORT",
                        })
                        if close_qty >= entry_info[0]:
                            position_queue.remove(entry_info)
                        else:
                            idx = position_queue.index(entry_info)
                            position_queue[idx] = (entry_info[0] - close_qty, entry_info[1], "SHORT")
            
            if remaining_qty > 0:
                position_queue.append((remaining_qty, trade, "LONG"))
        
        elif trade.side == "SELL":
            # Check if this closes a LONG position
            if position_queue and position_queue[0][2] == "LONG":
                entry_info = position_queue[0]
                entry_qty = entry_info[0]
                entry_trade = entry_info[1]
                
                close_qty = min(trade.executed_qty, entry_qty)
                
                closed_positions.append({
                    "entry_trade": entry_trade,
                    "exit_trade": trade,
                    "quantity": float(close_qty),
                    "position_side": "LONG",
                })
                
                # Update queue
                if close_qty >= entry_qty:
                    position_queue.pop(0)
                else:
                    position_queue[0] = (entry_qty - close_qty, entry_trade, "LONG")
            
            # Add remaining quantity to SHORT position queue
            remaining_qty = trade.executed_qty
            for entry_info in position_queue:
                if entry_info[2] == "LONG":
                    close_qty = min(remaining_qty, entry_info[0])
                    remaining_qty -= close_qty
                    if close_qty > 0:
                        closed_positions.append({
                            "entry_trade": entry_info[1],
                            "exit_trade": trade,
                            "quantity": float(close_qty),
                            "position_side": "LONG",
                        })
                        if close_qty >= entry_info[0]:
                            position_queue.remove(entry_info)
                        else:
                            idx = position_queue.index(entry_info)
                            position_queue[idx] = (entry_info[0] - close_qty, entry_info[1], "LONG")
            
            if remaining_qty > 0:
                position_queue.append((remaining_qty, trade, "SHORT"))
    
    if limit:
        closed_positions = closed_positions[:limit]
    
    return closed_positions


def backfill_completed_trades(
    db: Session,
    user_id: UUID,
    strategy_id: Optional[str] = None,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> dict:
    """Backfill CompletedTrade records for historical trades.
    
    Args:
        db: Database session
        user_id: User UUID
        strategy_id: Optional strategy ID to filter
        dry_run: If True, don't create records, just report
        limit: Optional limit on number of positions to process
    
    Returns:
        Dict with statistics
    """
    logger.info(f"Starting backfill for user {user_id}, strategy={strategy_id or 'all'}, dry_run={dry_run}")
    
    # Find closed positions
    closed_positions = find_closed_positions(db, user_id, strategy_id, limit)
    logger.info(f"Found {len(closed_positions)} closed positions to process")
    
    if not closed_positions:
        return {
            "total_positions": 0,
            "created": 0,
            "skipped": 0,
            "errors": 0
        }
    
    # Get strategy info
    strategy_info = {}
    if strategy_id:
        try:
            strategy_uuid = UUID(str(strategy_id))
            db_strategy = db.query(Strategy).filter(
                Strategy.id == strategy_uuid,
                Strategy.user_id == user_id
            ).first()
        except ValueError:
            db_strategy = db.query(Strategy).filter(
                Strategy.strategy_id == strategy_id,
                Strategy.user_id == user_id
            ).first()
        
        if db_strategy:
            strategy_info[str(db_strategy.id)] = {
                "strategy_id": db_strategy.strategy_id,
                "name": db_strategy.name,
                "symbol": db_strategy.symbol,
                "leverage": db_strategy.leverage or 1,
            }
    else:
        # Get all strategies
        strategies = db.query(Strategy).filter(Strategy.user_id == user_id).all()
        for s in strategies:
            strategy_info[str(s.id)] = {
                "strategy_id": s.strategy_id,
                "name": s.name,
                "symbol": s.symbol,
                "leverage": s.leverage or 1,
            }
    
    # Process each closed position
    completed_trade_service = CompletedTradeService(db)
    stats = {
        "total_positions": len(closed_positions),
        "created": 0,
        "skipped": 0,
        "errors": 0
    }
    
    for i, position in enumerate(closed_positions):
        entry_trade = position["entry_trade"]
        exit_trade = position["exit_trade"]
        quantity = position["quantity"]
        position_side = position["position_side"]
        
        strategy_uuid = entry_trade.strategy_id
        strategy_data = strategy_info.get(str(strategy_uuid), {})
        
        if not strategy_data:
            logger.warning(f"Skipping position: strategy {strategy_uuid} not found")
            stats["skipped"] += 1
            continue
        
        # Check if CompletedTrade already exists (idempotency)
        # Use close_event_id based on exit_trade.id and quantity
        from uuid import uuid5, UUID as UUIDType
        namespace = UUIDType('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # Standard namespace
        close_event_id = uuid5(namespace, f"{exit_trade.id}:{entry_trade.id}:{quantity}")
        
        existing = db.query(CompletedTrade).filter(
            CompletedTrade.close_event_id == close_event_id
        ).first()
        
        if existing:
            logger.debug(f"Skipping existing CompletedTrade: {close_event_id}")
            stats["skipped"] += 1
            continue
        
        if dry_run:
            logger.info(
                f"[DRY RUN] Would create CompletedTrade: "
                f"entry={entry_trade.order_id}, exit={exit_trade.order_id}, "
                f"qty={quantity}, side={position_side}"
            )
            stats["created"] += 1
            continue
        
        # Create CompletedTrade
        try:
            entry_price = float(entry_trade.avg_price or entry_trade.price)
            exit_price = float(exit_trade.avg_price or exit_trade.price)
            
            # Calculate PnL
            if position_side == "LONG":
                gross_pnl = (exit_price - entry_price) * quantity
            else:  # SHORT
                gross_pnl = (entry_price - exit_price) * quantity
            
            pnl_pct = (gross_pnl / (entry_price * quantity)) * 100 if (entry_price * quantity) != 0 else 0.0
            
            # Calculate fees (proportional)
            entry_fee = float(entry_trade.commission or 0.0) * (quantity / float(entry_trade.executed_qty)) if entry_trade.executed_qty else 0.0
            exit_fee = float(exit_trade.commission or 0.0) * (quantity / float(exit_trade.executed_qty)) if exit_trade.executed_qty else 0.0
            total_fee = entry_fee + exit_fee
            
            completed_trade = completed_trade_service.create_completed_trade(
                user_id=user_id,
                strategy_id=strategy_uuid,
                entry_trade_id=entry_trade.id,
                exit_trade_id=exit_trade.id,
                quantity=quantity,
                pnl_usd=gross_pnl,
                pnl_pct=pnl_pct,
                funding_fee=0.0,  # Historical funding fees not available
                exit_reason=exit_trade.exit_reason,
                symbol=entry_trade.symbol,
                side=position_side,
                entry_time=entry_trade.timestamp,
                exit_time=exit_trade.timestamp,
                entry_price=entry_price,
                exit_price=exit_price,
                leverage=entry_trade.leverage,
                initial_margin=entry_trade.initial_margin,
                margin_type=entry_trade.margin_type,
                notional_value=entry_trade.notional_value,
                entry_order_id=entry_trade.order_id,
                exit_order_id=exit_trade.order_id,
            )
            
            stats["created"] += 1
            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i + 1}/{len(closed_positions)} positions processed")
        
        except Exception as e:
            logger.error(
                f"Error creating CompletedTrade for entry={entry_trade.order_id}, "
                f"exit={exit_trade.order_id}: {e}",
                exc_info=True
            )
            stats["errors"] += 1
    
    logger.info(
        f"Backfill complete: {stats['created']} created, "
        f"{stats['skipped']} skipped, {stats['errors']} errors"
    )
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill CompletedTrade records for historical trades")
    parser.add_argument("--strategy-id", type=str, help="Strategy ID to filter (optional)")
    parser.add_argument("--user-id", type=str, help="User UUID (optional, defaults to first user)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (don't create records)")
    parser.add_argument("--limit", type=int, help="Limit number of positions to process")
    
    args = parser.parse_args()
    
    # Get database connection
    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Get user ID
        if args.user_id:
            user_id = UUID(args.user_id)
        else:
            # Get first user
            user = db.query(User).first()
            if not user:
                logger.error("No users found in database")
                return
            user_id = user.id
        
        # Run backfill
        stats = backfill_completed_trades(
            db=db,
            user_id=user_id,
            strategy_id=args.strategy_id,
            dry_run=args.dry_run,
            limit=args.limit
        )
        
        print(f"\nBackfill Statistics:")
        print(f"  Total positions: {stats['total_positions']}")
        print(f"  Created: {stats['created']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Errors: {stats['errors']}")
        
        if not args.dry_run:
            db.commit()
            logger.info("Backfill committed to database")
        else:
            db.rollback()
            logger.info("Dry run completed (no changes committed)")
    
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()












