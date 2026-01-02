"""Strategy persistence operations for Redis and database."""

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional

from loguru import logger

from app.core.redis_storage import RedisStorage
from app.models.order import OrderResponse
from app.models.strategy import StrategySummary, StrategyState

if TYPE_CHECKING:
    from app.services.strategy_service import StrategyService
    from app.services.strategy_account_manager import StrategyAccountManager
    from app.services.strategy_order_manager import StrategyOrderManager


class StrategyPersistence:
    """Handles persistence operations for strategies and trades."""
    
    def __init__(
        self,
        redis_storage: Optional[RedisStorage] = None,
        strategy_service: Optional["StrategyService"] = None,
        user_id: Optional["UUID"] = None,
        strategies: Optional[Dict[str, StrategySummary]] = None,
        trades: Optional[Dict[str, List[OrderResponse]]] = None,
        account_manager: Optional["StrategyAccountManager"] = None,
        order_manager: Optional["StrategyOrderManager"] = None,
    ):
        """Initialize persistence handler.
        
        Args:
            redis_storage: Redis storage instance
            strategy_service: Strategy service for database operations
            user_id: User ID for multi-user mode
            strategies: Reference to strategies dictionary
            trades: Reference to trades dictionary
            account_manager: Account manager for getting clients (optional)
            order_manager: Order manager for canceling TP/SL orders (optional)
        """
        self.redis = redis_storage
        self.strategy_service = strategy_service
        self.user_id = user_id
        self._strategies = strategies or {}
        self._trades = trades or {}
        self.account_manager = account_manager
        self.order_manager = order_manager
    
    def save_to_redis(self, strategy_id: str, summary: StrategySummary) -> None:
        """Save strategy to Redis."""
        if not self.redis or not self.redis.enabled:
            return
        
        try:
            # Convert StrategySummary to dict
            strategy_data = summary.model_dump(mode='json')
            self.redis.save_strategy(strategy_id, strategy_data)
        except Exception as exc:
            logger.warning(f"Failed to save strategy {strategy_id} to Redis: {exc}")
    
    def save_trades_to_redis(self, strategy_id: str) -> None:
        """Save trades for a strategy to Redis."""
        if not self.redis or not self.redis.enabled:
            return
        
        try:
            trades = self._trades.get(strategy_id, [])
            # Convert OrderResponse to dict
            trades_data = [trade.model_dump(mode='json') for trade in trades]
            self.redis.save_trades(strategy_id, trades_data)
        except Exception as exc:
            logger.warning(f"Failed to save trades for {strategy_id} to Redis: {exc}")
    
    def update_strategy_in_db(self, strategy_id: str, save_to_redis: bool = False, **updates) -> bool:
        """Helper method to update strategy in database if service is available.
        
        Uses transaction management to ensure atomicity. If database update succeeds
        but Redis update fails, the database update is kept (database is source of truth).
        
        Args:
            strategy_id: Strategy ID to update
            save_to_redis: Whether to save to Redis after successful database update
            **updates: Keyword arguments to pass to update_strategy (e.g., status, started_at, stopped_at)
        
        Returns:
            True if update was successful (or not needed), False if update failed
        """
        if not (self.strategy_service and self.user_id):
            return False
        
        try:
            # Update database within transaction (DatabaseService handles this)
            self.strategy_service.update_strategy(
                user_id=self.user_id,
                strategy_id=strategy_id,
                **updates
            )
            
            # Optionally save to Redis after successful database update
            # Note: Redis is cache, so if it fails, we don't rollback database
            # Database is source of truth, Redis is just for performance
            if save_to_redis and strategy_id in self._strategies:
                try:
                    summary = self._strategies[strategy_id]
                    self.save_to_redis(strategy_id, summary)
                except Exception as redis_exc:
                    logger.warning(
                        f"Database update succeeded for strategy {strategy_id}, "
                        f"but Redis cache update failed: {redis_exc}. "
                        f"Database is source of truth, continuing."
                    )
            
            return True
        except Exception as e:
            logger.error(f"Failed to update strategy {strategy_id} in database: {e}")
            # Database update failed - don't save to Redis (would be inconsistent)
            # Only save to Redis if we're in single-user mode (no database)
            if not (self.strategy_service and self.user_id) and save_to_redis and strategy_id in self._strategies:
                summary = self._strategies[strategy_id]
                self.save_to_redis(strategy_id, summary)
            return False
    
    def load_from_database(self) -> None:
        """Load all strategies from database via StrategyService (multi-user mode)."""
        if not self.strategy_service or not self.user_id:
            return
        
        try:
            strategies = self.strategy_service.list_strategies(self.user_id)
            logger.info(f"Loading {len(strategies)} strategies from database for user {self.user_id}")
            
            # Note: This is a sync method, so we can't use async locks
            # Dictionary writes are protected by GIL in CPython, but not guaranteed
            # TODO: Consider making this method async for better thread safety
            for summary in strategies:
                self._strategies[summary.id] = summary
                # Also cache in Redis for fast access
                if self.redis:
                    self.save_to_redis(summary.id, summary)
            
            running_count = len([s for s in self._strategies.values() if s.status == StrategyState.running])
            logger.info(
                f"Successfully loaded {len(strategies)} strategies from database. "
                f"Strategies in memory: {len(self._strategies)}, "
                f"Running strategies (to be restored): {running_count}"
            )
        except Exception as exc:
            logger.error(f"Failed to load strategies from database: {exc!s}", exc_info=True)
    
    def load_from_redis(self) -> None:
        """Load all strategies and trades from Redis on startup."""
        if not self.redis or not self.redis.enabled:
            logger.info("Redis not enabled, skipping load from Redis")
            return
        
        try:
            # Load all strategies
            strategies_data = self.redis.get_all_strategies()
            logger.info(f"Loading {len(strategies_data)} strategies from Redis")
            
            loaded_count = 0
            trades_loaded_count = 0
            for strategy_id, data in strategies_data.items():
                try:
                    # Convert datetime strings back to datetime objects
                    if "created_at" in data and isinstance(data["created_at"], str):
                        data["created_at"] = datetime.fromisoformat(data["created_at"])
                    if "last_trade_at" in data and isinstance(data["last_trade_at"], str):
                        data["last_trade_at"] = datetime.fromisoformat(data["last_trade_at"])
                    
                    # Ensure account_id exists (for backward compatibility with old strategies)
                    if "account_id" not in data or data.get("account_id") is None:
                        data["account_id"] = "default"
                    
                    # Reconstruct StrategySummary from dict
                    summary = StrategySummary(**data)
                    self._strategies[strategy_id] = summary
                    loaded_count += 1
                    
                    # Load trades for this strategy
                    trades_data = self.redis.get_trades(strategy_id)
                    if trades_data:
                        trades = []
                        for trade_data in trades_data:
                            try:
                                # Handle any datetime fields if present
                                if "created_at" in trade_data and isinstance(trade_data["created_at"], str):
                                    trade_data["created_at"] = datetime.fromisoformat(trade_data["created_at"])
                                if "timestamp" in trade_data and isinstance(trade_data["timestamp"], str):
                                    trade_data["timestamp"] = datetime.fromisoformat(trade_data["timestamp"])
                                if "update_time" in trade_data and isinstance(trade_data["update_time"], str):
                                    trade_data["update_time"] = datetime.fromisoformat(trade_data["update_time"])
                                trades.append(OrderResponse(**trade_data))
                            except Exception as trade_exc:
                                logger.warning(f"Failed to load trade for strategy {strategy_id}: {trade_exc}")
                                continue
                        if trades:
                            self._trades[strategy_id] = trades
                            trades_loaded_count += len(trades)
                            logger.debug(f"Loaded {len(trades)} trades for strategy {strategy_id} from Redis")
                    
                    logger.debug(f"Loaded strategy {strategy_id} from Redis (status: {summary.status.value})")
                except Exception as exc:
                    logger.warning(f"Failed to load strategy {strategy_id} from Redis: {exc}", exc_info=True)
                    continue
            
            running_count = len([s for s in self._strategies.values() if s.status == StrategyState.running])
            logger.info(
                f"Successfully loaded {loaded_count} strategies and {trades_loaded_count} trades from Redis. "
                f"Strategies in memory: {len(self._strategies)}, "
                f"Running strategies (to be restored): {running_count}"
            )
        except Exception as exc:
            logger.error(f"Failed to load strategies from Redis: {exc}", exc_info=True)
    
    async def update_position_info(self, summary: StrategySummary) -> None:
        """Update position information and unrealized PnL for a strategy.
        
        CRITICAL: Database is single source of truth. Position state is synced:
        1. From Binance (reality)
        2. To database (source of truth)
        3. To Redis (cache)
        4. To memory (in-memory cache)
        
        This ensures consistency across all state stores.
        
        Args:
            summary: Strategy summary to update
        """
        if not self.account_manager:
            logger.warning("Cannot update position info: account_manager not available")
            return
        
        try:
            # Get account-specific client
            account_id = summary.account_id or "default"
            logger.debug(f"Getting position for {summary.symbol} using account_id: {account_id}")
            
            try:
                account_client = self.account_manager.get_account_client(account_id)
            except RuntimeError as e:
                logger.error(
                    f"❌ Failed to get account client for account_id '{account_id}' when getting position for {summary.symbol}: {e}. "
                    f"This usually means the account is not configured in the database or has invalid API keys."
                )
                return
            
            # Get current position from Binance (reality)
            # Wrap sync BinanceClient call in to_thread to avoid blocking event loop
            position = await asyncio.to_thread(account_client.get_open_position, summary.symbol)
            
            # Track previous state for change detection (capture BEFORE overwriting)
            previous_position_size = summary.position_size
            previous_position_side = summary.position_side
            previous_entry_price = summary.entry_price
            
            if position and abs(float(position["positionAmt"])) > 0:
                # Update position info from Binance (reality)
                position_amt = float(position["positionAmt"])
                new_position_size = abs(position_amt)
                new_entry_price = float(position["entryPrice"])
                new_unrealized_pnl = float(position["unRealizedProfit"])
                new_position_side = "LONG" if position_amt > 0 else "SHORT"
                
                # Update current price from mark price for consistency
                new_current_price = summary.current_price  # Keep existing if update fails
                if "markPrice" in position:
                    new_current_price = float(position["markPrice"])
                else:
                    # Fallback to getting current price if markPrice not available
                    try:
                        new_current_price = await asyncio.to_thread(account_client.get_price, summary.symbol)
                    except Exception:
                        pass  # Keep existing current_price if update fails
                
                # Update summary (memory)
                summary.position_size = new_position_size
                summary.entry_price = new_entry_price
                summary.unrealized_pnl = new_unrealized_pnl
                summary.position_side = new_position_side
                summary.current_price = new_current_price
                
                # CRITICAL: Update database FIRST (single source of truth)
                # Only update if state actually changed (avoid unnecessary DB writes)
                state_changed = (
                    previous_position_size != new_position_size or
                    previous_position_side != new_position_side or
                    previous_entry_price != new_entry_price
                )
                
                if state_changed:
                    self.update_strategy_in_db(
                        summary.id,
                        save_to_redis=True,
                        position_size=new_position_size,
                        entry_price=new_entry_price,
                        current_price=new_current_price,
                        position_side=new_position_side,
                        unrealized_pnl=new_unrealized_pnl,
                    )
            else:
                # No open position
                # Check None first - if position_size is None, it means no position was ever opened
                position_was_closed = summary.position_size is not None and summary.position_size != 0
                if position_was_closed:
                    # CRITICAL: Update database FIRST (single source of truth)
                    # Clear position state in database
                    self.update_strategy_in_db(
                        summary.id,
                        save_to_redis=True,
                        entry_price=None,
                        position_size=0,
                        unrealized_pnl=0,
                        position_side=None,
                    )
                    
                    # Update summary (memory)
                    summary.entry_price = None
                    summary.position_size = 0
                    summary.unrealized_pnl = 0
                    summary.position_side = None
                    
                    # Clear TP/SL order IDs when position closes
                    has_existing_orders = bool(summary.meta.get("tp_sl_orders", {}).get("tp_order_id") or 
                                              summary.meta.get("tp_sl_orders", {}).get("sl_order_id"))
                    if has_existing_orders:
                        # Check if any TP/SL orders were filled
                        try:
                            open_orders = await asyncio.to_thread(account_client.get_open_orders, summary.symbol)
                            open_order_ids = {o.get("orderId") for o in open_orders}
                            tp_order_id = summary.meta.get("tp_sl_orders", {}).get("tp_order_id")
                            sl_order_id = summary.meta.get("tp_sl_orders", {}).get("sl_order_id")
                            
                            tp_filled = tp_order_id and tp_order_id not in open_order_ids
                            sl_filled = sl_order_id and sl_order_id not in open_order_ids
                            
                            exit_reason = "TP" if tp_filled else ("SL" if sl_filled else "UNKNOWN")
                            logger.info(
                                f"[{summary.id}] 🔴 Position CLOSED via Binance native {exit_reason} order "
                                f"(TP_filled: {tp_filled}, SL_filled: {sl_filled}). "
                                f"Clearing TP/SL order metadata."
                            )
                        except Exception as exc:
                            logger.info(
                                f"[{summary.id}] 🔴 Position CLOSED (possibly via native TP/SL, unable to verify): {exc}. "
                                f"Clearing TP/SL order metadata."
                            )
                        
                        # Try to cancel orders (they may already be filled/executed)
                        if self.order_manager:
                            try:
                                await self.order_manager.cancel_tp_sl_orders(summary)
                            except Exception as exc:
                                logger.debug(f"[{summary.id}] Error cancelling TP/SL orders (may already be filled): {exc}")
                        
                        # Clear metadata regardless
                        if "tp_sl_orders" in summary.meta:
                            summary.meta["tp_sl_orders"] = {}
                            # Update database with cleared metadata
                            self.update_strategy_in_db(
                                summary.id,
                                save_to_redis=True,
                                meta=summary.meta,
                            )
        except Exception as exc:
            logger.debug(f"Failed to update position info for {summary.symbol}: {exc}")
            # Calculate unrealized PnL manually if we have entry price and current price
            if summary.entry_price and summary.current_price and summary.position_size:
                # Update current price for manual calculation
                try:
                    account_id = summary.account_id or "default"
                    account_client = self.account_manager.get_account_client(account_id)
                    summary.current_price = await asyncio.to_thread(account_client.get_price, summary.symbol)
                except Exception as price_exc:
                    logger.debug(f"Failed to get current price for {summary.symbol}: {price_exc}")
                
                # Calculate unrealized PnL based on position side
                if summary.position_side == "SHORT":
                    summary.unrealized_pnl = (summary.entry_price - summary.current_price) * summary.position_size
                else:
                    summary.unrealized_pnl = (summary.current_price - summary.entry_price) * summary.position_size
                
                # Update database with calculated PnL
                self.update_strategy_in_db(
                    summary.id,
                    save_to_redis=True,
                    current_price=summary.current_price,
                    unrealized_pnl=summary.unrealized_pnl,
                )
    
    async def reconcile_position_state(self, summary: StrategySummary) -> None:
        """Periodically reconcile position state between Binance, database, and memory.
        
        This ensures all state stores are consistent:
        - Binance (reality)
        - Database (source of truth)
        - Redis (cache)
        - Memory (in-memory cache)
        
        Args:
            summary: Strategy summary to reconcile
        """
        if not self.account_manager:
            logger.warning("Cannot reconcile position state: account_manager not available")
            return
        
        try:
            # Get account-specific client
            account_id = summary.account_id or "default"
            account_client = self.account_manager.get_account_client(account_id)
            
            # Get current position from Binance (reality)
            position = await asyncio.to_thread(account_client.get_open_position, summary.symbol)
            
            # Get database state (source of truth)
            db_state = None
            if self.strategy_service and self.user_id:
                try:
                    db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, summary.id)
                    if db_strategy:
                        db_state = {
                            "position_size": float(db_strategy.position_size) if db_strategy.position_size else 0,
                            "position_side": db_strategy.position_side,
                            "entry_price": float(db_strategy.entry_price) if db_strategy.entry_price else None,
                            "unrealized_pnl": float(db_strategy.unrealized_pnl) if db_strategy.unrealized_pnl else 0,
                        }
                except Exception as db_exc:
                    logger.warning(f"Failed to get database state for reconciliation: {db_exc}")
            
            # Get Binance position (reality)
            binance_position_size = 0
            binance_position_side = None
            binance_entry_price = None
            binance_unrealized_pnl = 0
            
            if position and abs(float(position["positionAmt"])) > 0:
                position_amt = float(position["positionAmt"])
                binance_position_size = abs(position_amt)
                binance_position_side = "LONG" if position_amt > 0 else "SHORT"
                binance_entry_price = float(position["entryPrice"])
                binance_unrealized_pnl = float(position["unRealizedProfit"])
            
            # Compare Binance (reality) with database (source of truth)
            state_mismatch = False
            if db_state:
                # Check for mismatches
                if abs(db_state["position_size"] - binance_position_size) > 0.0001:
                    state_mismatch = True
                    logger.warning(
                        f"[{summary.id}] Position size mismatch detected: "
                        f"Database={db_state['position_size']}, Binance={binance_position_size}"
                    )
                elif db_state["position_side"] != binance_position_side:
                    state_mismatch = True
                    logger.warning(
                        f"[{summary.id}] Position side mismatch detected: "
                        f"Database={db_state['position_side']}, Binance={binance_position_side}"
                    )
            
            # If mismatch detected, update database with Binance reality
            if state_mismatch:
                logger.info(
                    f"[{summary.id}] Reconciling position state: "
                    f"Updating database to match Binance reality"
                )
                self.update_strategy_in_db(
                    summary.id,
                    save_to_redis=True,
                    position_size=binance_position_size,
                    position_side=binance_position_side,
                    entry_price=binance_entry_price,
                    unrealized_pnl=binance_unrealized_pnl,
                )
                
                # Update memory cache from database (single source of truth)
                summary.position_size = binance_position_size
                summary.position_side = binance_position_side
                summary.entry_price = binance_entry_price
                summary.unrealized_pnl = binance_unrealized_pnl
                
                logger.info(
                    f"[{summary.id}] Position state reconciled: "
                    f"Database and memory updated to match Binance"
                )
        except Exception as exc:
            logger.warning(f"Failed to reconcile position state for {summary.id}: {exc}")
    
    async def check_state_consistency(self, strategy_id: str) -> dict:
        """Check consistency between database, Redis, and memory state.
        
        Args:
            strategy_id: Strategy ID to check
            
        Returns:
            Dictionary with consistency check results:
            {
                "consistent": bool,
                "mismatches": list of mismatch descriptions,
                "database_state": dict,
                "memory_state": dict,
                "redis_state": dict (if available)
            }
        """
        result = {
            "consistent": True,
            "mismatches": [],
            "database_state": None,
            "memory_state": None,
            "redis_state": None,
        }
        
        try:
            # Get memory state
            if strategy_id in self._strategies:
                summary = self._strategies[strategy_id]
                result["memory_state"] = {
                    "position_size": summary.position_size,
                    "position_side": summary.position_side,
                    "entry_price": summary.entry_price,
                    "status": summary.status.value if hasattr(summary.status, 'value') else str(summary.status),
                }
            
            # Get database state (source of truth)
            if self.strategy_service and self.user_id:
                try:
                    db_strategy = self.strategy_service.db_service.get_strategy(self.user_id, strategy_id)
                    if db_strategy:
                        result["database_state"] = {
                            "position_size": float(db_strategy.position_size) if db_strategy.position_size else 0,
                            "position_side": db_strategy.position_side,
                            "entry_price": float(db_strategy.entry_price) if db_strategy.entry_price else None,
                            "status": db_strategy.status,
                        }
                except Exception as db_exc:
                    result["mismatches"].append(f"Failed to get database state: {db_exc}")
            
            # Get Redis state (cache)
            if self.redis and self.redis.enabled:
                try:
                    redis_data = self.redis.get_strategy(strategy_id)
                    if redis_data:
                        result["redis_state"] = {
                            "position_size": redis_data.get("position_size"),
                            "position_side": redis_data.get("position_side"),
                            "entry_price": redis_data.get("entry_price"),
                            "status": redis_data.get("status"),
                        }
                except Exception as redis_exc:
                    result["mismatches"].append(f"Failed to get Redis state: {redis_exc}")
            
            # Compare states
            if result["database_state"] and result["memory_state"]:
                db_state = result["database_state"]
                mem_state = result["memory_state"]
                
                # Check position size
                if abs((db_state["position_size"] or 0) - (mem_state["position_size"] or 0)) > 0.0001:
                    result["consistent"] = False
                    result["mismatches"].append(
                        f"Position size mismatch: DB={db_state['position_size']}, Memory={mem_state['position_size']}"
                    )
                
                # Check position side
                if db_state["position_side"] != mem_state["position_side"]:
                    result["consistent"] = False
                    result["mismatches"].append(
                        f"Position side mismatch: DB={db_state['position_side']}, Memory={mem_state['position_side']}"
                    )
                
                # Check status
                if db_state["status"] != mem_state["status"]:
                    result["consistent"] = False
                    result["mismatches"].append(
                        f"Status mismatch: DB={db_state['status']}, Memory={mem_state['status']}"
                    )
            
            # If inconsistent, log warning
            if not result["consistent"]:
                logger.warning(
                    f"[{strategy_id}] State consistency check failed: {', '.join(result['mismatches'])}"
                )
            
        except Exception as exc:
            logger.warning(f"Failed to check state consistency for {strategy_id}: {exc}")
            result["mismatches"].append(f"Consistency check error: {exc}")
            result["consistent"] = False
        
        return result


