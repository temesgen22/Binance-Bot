"""
Trade service with cache-aside pattern (PostgreSQL + Redis).
Handles trade CRUD operations with Redis caching for recent trades.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.redis_storage import RedisStorage
from app.services.database_service import DatabaseService
from app.models.order import OrderResponse
from app.models.db_models import Trade as DBTrade, Strategy
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_not_exception_type
from sqlalchemy.exc import IntegrityError


class TradeService:
    """Service for managing trades with database + Redis cache-aside pattern.
    
    Supports both sync (Session) and async (AsyncSession) database operations.
    """
    
    def __init__(self, db: Session | AsyncSession, redis_storage: Optional[RedisStorage] = None):
        self.db_service = DatabaseService(db)
        self.redis = redis_storage
        self._cache_ttl = 86400  # 24 hours cache TTL for recent trades
        self._is_async = isinstance(db, AsyncSession)
    
    def _redis_key(self, user_id: UUID, strategy_id: str) -> str:
        """Generate Redis key for recent trades with user_id."""
        return f"binance_bot:user:{user_id}:trades:recent:{strategy_id}"
    
    def _order_response_to_trade_dict(self, order: OrderResponse, strategy_id: UUID, user_id: UUID) -> dict:
        """Convert OrderResponse to Trade database model dict."""
        return {
            "strategy_id": strategy_id,
            "user_id": user_id,
            "order_id": order.order_id,
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "status": order.status,
            "price": order.price,
            "avg_price": order.avg_price,
            "executed_qty": order.executed_qty,
            "notional_value": order.notional_value,
            "cummulative_quote_qty": order.cummulative_quote_qty,
            "initial_margin": order.initial_margin,
            "commission": order.commission,
            "commission_asset": order.commission_asset,
            "realized_pnl": order.realized_pnl,
            "position_side": order.position_side,
            "leverage": order.leverage,
            "margin_type": order.margin_type,
            "exit_reason": order.exit_reason,
            "timestamp": order.timestamp or datetime.now(timezone.utc),
            "update_time": order.update_time,
            "time_in_force": order.time_in_force,
            "working_type": order.working_type,
            "stop_price": order.stop_price,
            "meta": {}  # Can be extended later
        }
    
    def _db_trade_to_order_response(self, db_trade: DBTrade) -> OrderResponse:
        """Convert database Trade model to OrderResponse."""
        return OrderResponse(
            symbol=db_trade.symbol,
            order_id=db_trade.order_id,
            status=db_trade.status,
            side=db_trade.side,
            price=float(db_trade.price),
            avg_price=float(db_trade.avg_price) if db_trade.avg_price else None,
            executed_qty=float(db_trade.executed_qty),
            timestamp=db_trade.timestamp,
            commission=float(db_trade.commission) if db_trade.commission else None,
            commission_asset=db_trade.commission_asset,
            leverage=db_trade.leverage,
            position_side=db_trade.position_side,
            update_time=db_trade.update_time,
            time_in_force=db_trade.time_in_force,
            order_type=db_trade.order_type,
            notional_value=float(db_trade.notional_value) if db_trade.notional_value else None,
            cummulative_quote_qty=float(db_trade.cummulative_quote_qty) if db_trade.cummulative_quote_qty else None,
            initial_margin=float(db_trade.initial_margin) if db_trade.initial_margin else None,
            margin_type=db_trade.margin_type,
            client_order_id=db_trade.client_order_id,
            working_type=db_trade.working_type,
            realized_pnl=float(db_trade.realized_pnl) if db_trade.realized_pnl else None,
            stop_price=float(db_trade.stop_price) if db_trade.stop_price else None,
            exit_reason=db_trade.exit_reason,
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(IntegrityError),  # Don't retry on IntegrityError (duplicates)
        reraise=True
    )
    def save_trade(
        self,
        user_id: UUID,
        strategy_id: UUID,
        order: OrderResponse
    ) -> DBTrade:
        """Save a trade to database and cache in Redis.
        
        Uses transaction management: database save is atomic. If database succeeds
        but Redis fails, database is kept (database is source of truth, Redis is cache).
        
        Includes retry logic with exponential backoff for transient database errors.
        Handles duplicate orders gracefully by returning existing trade.
        
        Args:
            user_id: User ID
            strategy_id: Strategy UUID (not strategy_id string)
            order: OrderResponse to save
        
        Returns:
            DBTrade model instance (existing if duplicate)
        
        Raises:
            Exception: If database save fails after retries (transaction will rollback)
        """
        # Convert OrderResponse to trade dict
        trade_data = self._order_response_to_trade_dict(order, strategy_id, user_id)
        
        try:
            # Save to database within transaction (DatabaseService.create_trade handles this)
            # If this fails, exception is raised and transaction is rolled back
            db_trade = self.db_service.create_trade(trade_data)
        except IntegrityError as e:
            # Handle duplicate order gracefully
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower() or 'idx_trades_strategy_order_id' in error_msg:
                # Duplicate order detected - get existing trade
                logger.warning(
                    f"Duplicate order {order.order_id} for strategy {strategy_id}. "
                    f"Returning existing trade from database."
                )
                # Query existing trade
                existing_trade = self.db_service.db.query(DBTrade).filter(
                    DBTrade.strategy_id == strategy_id,
                    DBTrade.order_id == order.order_id
                ).first()
                if existing_trade:
                    logger.info(
                        f"Found existing trade {existing_trade.id} for order {order.order_id}. "
                        f"This is expected for idempotent order execution."
                    )
                    return existing_trade
                else:
                    # Should not happen, but handle gracefully
                    logger.error(
                        f"IntegrityError for duplicate order {order.order_id}, but existing trade not found. "
                        f"This may indicate a race condition."
                    )
                    raise
            else:
                # Not a duplicate error, re-raise
                logger.error(f"IntegrityError saving trade {order.order_id}: {error_msg}")
                raise
        
        # Cache in Redis (sorted set by timestamp for recent trades)
        # Note: Redis is cache, so if it fails, we don't rollback database
        # Database is source of truth, Redis is just for performance
        if self.redis and self.redis.enabled:
            try:
                key = self._redis_key(user_id, str(strategy_id))
                # Use sorted set with timestamp as score
                trade_dict = order.model_dump(mode='json')
                timestamp_score = order.timestamp.timestamp() if order.timestamp else datetime.now(timezone.utc).timestamp()
                
                if self.redis._client:
                    # Add to sorted set
                    self.redis._client.zadd(
                        key,
                        {json.dumps(trade_dict, default=str): timestamp_score}
                    )
                    # Set TTL
                    self.redis._client.expire(key, self._cache_ttl)
                    # Keep only last 1000 trades (remove oldest)
                    self.redis._client.zremrangebyrank(key, 0, -1001)
            except Exception as e:
                logger.warning(
                    f"Database save succeeded for trade {order.order_id}, "
                    f"but Redis cache write failed: {e}. "
                    f"Database is source of truth, continuing."
                )
        
        return db_trade
    
    def get_recent_trades(
        self,
        user_id: UUID,
        strategy_id: Optional[UUID] = None,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[OrderResponse]:
        """Get recent trades using cache-aside pattern.
        
        1. Check Redis cache (last 24 hours)
        2. If not enough, query database
        3. Cache results in Redis
        
        Args:
            user_id: User ID
            strategy_id: Optional strategy UUID to filter
            limit: Maximum number of trades to return
        
        Returns:
            List of OrderResponse
        """
        # Try Redis first (for recent trades)
        if self.redis and self.redis.enabled and strategy_id:
            try:
                key = self._redis_key(user_id, str(strategy_id))
                if self.redis._client:
                    # Get recent trades from sorted set (last 24 hours)
                    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()
                    cached_trades = self.redis._client.zrangebyscore(
                        key,
                        min=cutoff_time,
                        max="+inf",
                        withscores=False,
                        start=0,
                        num=limit
                    )
                    
                    if cached_trades:
                        orders = []
                        for trade_json in cached_trades:
                            try:
                                trade_dict = json.loads(trade_json)
                                # Convert timestamp string back to datetime
                                if "timestamp" in trade_dict and isinstance(trade_dict["timestamp"], str):
                                    trade_dict["timestamp"] = datetime.fromisoformat(trade_dict["timestamp"])
                                if "update_time" in trade_dict and isinstance(trade_dict["update_time"], str):
                                    trade_dict["update_time"] = datetime.fromisoformat(trade_dict["update_time"])
                                orders.append(OrderResponse(**trade_dict))
                            except Exception as e:
                                logger.warning(f"Failed to parse cached trade: {e}")
                                continue
                        
                        if len(orders) >= limit:
                            logger.debug(f"Cache HIT: Found {len(orders)} recent trades in Redis")
                            return orders[:limit]
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")
        
        # Cache miss or not enough trades: query database
        logger.debug(f"Cache MISS or insufficient trades, querying database")
        db_trades = self.db_service.get_user_trades(
            user_id=user_id,
            strategy_id=strategy_id,
            limit=limit
        )
        
        orders = [self._db_trade_to_order_response(trade) for trade in db_trades]
        
        # Filter by time range if provided
        if start_time or end_time:
            filtered_orders = []
            for order in orders:
                if order.timestamp:
                    if start_time and order.timestamp < start_time:
                        continue
                    if end_time and order.timestamp > end_time:
                        continue
                filtered_orders.append(order)
            orders = filtered_orders
        
        # Cache recent trades in Redis
        if self.redis and self.redis.enabled and strategy_id and orders:
            try:
                key = self._redis_key(user_id, str(strategy_id))
                if self.redis._client:
                    # Add all trades to sorted set
                    for order in orders:
                        trade_dict = order.model_dump(mode='json')
                        timestamp_score = order.timestamp.timestamp() if order.timestamp else datetime.now(timezone.utc).timestamp()
                        self.redis._client.zadd(
                            key,
                            {json.dumps(trade_dict, default=str): timestamp_score}
                        )
                    self.redis._client.expire(key, self._cache_ttl)
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")
        
        return orders
    
    def get_strategy_trades(
        self,
        user_id: UUID,
        strategy_id: UUID,
        limit: int = 100
    ) -> List[OrderResponse]:
        """Get trades for a specific strategy."""
        return self.get_recent_trades(user_id, strategy_id, limit)
    
    def get_trades_batch(
        self,
        user_id: UUID,
        strategy_ids: List[UUID],
        limit_per_strategy: int = 1000
    ) -> Dict[UUID, List[OrderResponse]]:
        """Get trades for multiple strategies in a single batch query (sync).
        
        This method optimizes the N+1 query problem by fetching trades
        for all strategies in a single database query.
        
        Args:
            user_id: User ID
            strategy_ids: List of strategy UUIDs
            limit_per_strategy: Maximum trades per strategy
            
        Returns:
            Dictionary mapping strategy_id to list of trades
        """
        if self._is_async:
            raise RuntimeError("Use async_get_trades_batch() with AsyncSession")
        
        if not strategy_ids:
            return {}
        
        # Batch query from database (single query for all strategies)
        db_trades = self.db_service.get_user_trades_batch(
            user_id=user_id,
            strategy_ids=strategy_ids,
            limit=limit_per_strategy * len(strategy_ids)  # Total limit for all strategies
        )
        
        # Group trades by strategy_id
        trades_by_strategy: Dict[UUID, List[OrderResponse]] = {sid: [] for sid in strategy_ids}
        
        for db_trade in db_trades:
            strategy_id = db_trade.strategy_id
            if strategy_id in trades_by_strategy:
                # Limit per strategy
                if len(trades_by_strategy[strategy_id]) < limit_per_strategy:
                    trades_by_strategy[strategy_id].append(
                        self._db_trade_to_order_response(db_trade)
                    )
        
        return trades_by_strategy
    
    def get_trades_by_account(
        self,
        user_id: UUID,
        account_id: str,
        limit: int = 1000,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[OrderResponse]:
        """Get all trades for a specific account.
        
        Args:
            user_id: User ID
            account_id: Account ID (string identifier)
            limit: Maximum number of trades to return
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            List of OrderResponse for all strategies in the account
        """
        # Get account UUID from account_id string
        from app.models.db_models import Account
        if self._is_async:
            from sqlalchemy import select
            stmt = select(Account).filter(
                Account.user_id == user_id,
                Account.account_id == account_id.lower(),
                Account.is_active == True
            )
            result = self.db_service.db.execute(stmt)
            account = result.scalar_one_or_none()
        else:
            account = self.db_service.db.query(Account).filter(
                Account.user_id == user_id,
                Account.account_id == account_id.lower(),
                Account.is_active == True
            ).first()
        
        if not account:
            return []
        
        # Get all strategies for this account
        from app.models.db_models import Strategy
        if self._is_async:
            from sqlalchemy import select
            stmt = select(Strategy).filter(
                Strategy.user_id == user_id,
                Strategy.account_id == account.id
            )
            result = self.db_service.db.execute(stmt)
            strategies = list(result.scalars().all())
        else:
            strategies = self.db_service.db.query(Strategy).filter(
                Strategy.user_id == user_id,
                Strategy.account_id == account.id
            ).all()
        
        if not strategies:
            return []
        
        # Get strategy UUIDs
        strategy_ids = [s.id for s in strategies]
        
        # Get trades for all strategies
        # Note: get_trades_by_account is sync, so we use sync methods
        trades_dict = self.get_trades_batch(user_id, strategy_ids, limit_per_strategy=limit)
        
        # Flatten to single list
        all_trades = []
        for strategy_trades in trades_dict.values():
            all_trades.extend(strategy_trades)
        
        # Filter by time range if provided
        if start_time or end_time:
            filtered_trades = []
            for trade in all_trades:
                if trade.timestamp:
                    if start_time and trade.timestamp < start_time:
                        continue
                    if end_time and trade.timestamp > end_time:
                        continue
                filtered_trades.append(trade)
            all_trades = filtered_trades
        
        # Sort by timestamp descending
        all_trades.sort(key=lambda t: t.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        
        return all_trades[:limit]
    
    def get_all_trades(
        self,
        user_id: UUID,
        limit: int = 1000,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[OrderResponse]:
        """Get all trades for a user across all accounts.
        
        Args:
            user_id: User ID
            limit: Maximum number of trades to return
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            List of OrderResponse for all user's trades
        """
        # Get all trades directly from database (no strategy filter)
        db_trades = self.db_service.get_user_trades(
            user_id=user_id,
            strategy_id=None,
            limit=limit
        )
        
        orders = [self._db_trade_to_order_response(trade) for trade in db_trades]
        
        # Filter by time range if provided
        if start_time or end_time:
            filtered_orders = []
            for order in orders:
                if order.timestamp:
                    if start_time and order.timestamp < start_time:
                        continue
                    if end_time and order.timestamp > end_time:
                        continue
                filtered_orders.append(order)
            orders = filtered_orders
        
        return orders
    
    async def async_get_trades_batch(
        self,
        user_id: UUID,
        strategy_ids: List[UUID],
        limit_per_strategy: int = 1000
    ) -> Dict[UUID, List[OrderResponse]]:
        """Get trades for multiple strategies in a single batch query (async).
        
        This method optimizes the N+1 query problem by fetching trades
        for all strategies in a single database query.
        
        Args:
            user_id: User ID
            strategy_ids: List of strategy UUIDs
            limit_per_strategy: Maximum trades per strategy
            
        Returns:
            Dictionary mapping strategy_id to list of trades
        """
        if not self._is_async:
            raise RuntimeError("Use get_trades_batch() with Session")
        
        if not strategy_ids:
            return {}
        
        # Batch query from database (single query for all strategies) - async
        db_trades = await self.db_service.async_get_user_trades_batch(
            user_id=user_id,
            strategy_ids=strategy_ids,
            limit=limit_per_strategy * len(strategy_ids)  # Total limit for all strategies
        )
        
        # Group trades by strategy_id
        trades_by_strategy: Dict[UUID, List[OrderResponse]] = {sid: [] for sid in strategy_ids}
        
        for db_trade in db_trades:
            strategy_id = db_trade.strategy_id
            if strategy_id in trades_by_strategy:
                # Limit per strategy
                if len(trades_by_strategy[strategy_id]) < limit_per_strategy:
                    trades_by_strategy[strategy_id].append(
                        self._db_trade_to_order_response(db_trade)
                    )
        
        return trades_by_strategy

