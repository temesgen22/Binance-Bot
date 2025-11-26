from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.models.order import OrderResponse
from app.core.redis_storage import RedisStorage
from app.risk.manager import RiskManager, PositionSizingResult
from app.models.strategy import CreateStrategyRequest, StrategyState, StrategySummary, StrategyType, StrategyStats, OverallStats
from app.services.order_executor import OrderExecutor
from app.strategies.base import Strategy, StrategyContext, StrategySignal
from app.strategies.scalping import EmaScalpingStrategy


class StrategyRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, type[Strategy]] = {
            StrategyType.scalping.value: EmaScalpingStrategy,
            # ema_crossover is now an alias for scalping with default 5/20 EMA
            # Users can achieve the same by setting ema_fast=5, ema_slow=20 in params
            StrategyType.ema_crossover.value: EmaScalpingStrategy,
        }

    def build(self, strategy_type: StrategyType, context: StrategyContext, client: BinanceClient) -> Strategy:
        try:
            implementation = self._registry[strategy_type.value]
        except KeyError as exc:
            raise ValueError(f"Unsupported strategy type: {strategy_type}") from exc
        return implementation(context, client)


class StrategyRunner:
    def __init__(
        self,
        *,
        client: BinanceClient,
        risk: RiskManager,
        executor: OrderExecutor,
        max_concurrent: int,
        redis_storage: Optional[RedisStorage] = None,
    ) -> None:
        self.client = client
        self.risk = risk
        self.executor = executor
        self.registry = StrategyRegistry()
        self.max_concurrent = max_concurrent
        self.redis = redis_storage
        self._strategies: Dict[str, StrategySummary] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._trades: Dict[str, List[OrderResponse]] = {}  # Track trades per strategy
        
        # Load strategies from Redis on startup
        self._load_from_redis()

    def register(self, payload: CreateStrategyRequest) -> StrategySummary:
        # Validate leverage is explicitly provided (Pydantic should catch this, but double-check)
        if payload.leverage is None:
            raise ValueError(
                "leverage is REQUIRED and must be explicitly provided (1-50). "
                "Cannot register strategy without explicit leverage to prevent Binance default 20x."
            )
        if not (1 <= payload.leverage <= 50):
            raise ValueError(
                f"Invalid leverage: {payload.leverage}. Must be between 1 and 50. "
                "Binance futures default is 20x - ensure you explicitly set your desired leverage."
            )
        
        strategy_id = str(uuid.uuid4())
        summary = StrategySummary(
            id=strategy_id,
            name=payload.name,
            symbol=payload.symbol,
            strategy_type=payload.strategy_type,
            status=StrategyState.stopped,
            leverage=payload.leverage,
            risk_per_trade=payload.risk_per_trade,
            fixed_amount=payload.fixed_amount,
            params=payload.params,
            created_at=datetime.utcnow(),
            last_signal=None,
            entry_price=None,
            current_price=None,
            position_size=None,
            unrealized_pnl=None,
            meta={},
        )
        self._strategies[strategy_id] = summary
        self._save_to_redis(strategy_id, summary)
        logger.info(
            f"Registered strategy {strategy_id} ({payload.strategy_type}) "
            f"with explicit leverage={payload.leverage}x for {payload.symbol}"
        )
        # auto_start is handled by the API layer to avoid double-starting the same strategy.
        return summary

    async def start(self, strategy_id: str) -> StrategySummary:
        if strategy_id not in self._strategies:
            raise KeyError(f"Strategy {strategy_id} not found")
        if len(self._tasks) >= self.max_concurrent:
            raise RuntimeError("Maximum concurrent strategies running")
        if strategy_id in self._tasks:
            raise RuntimeError("Strategy already running")

        summary = self._strategies[strategy_id]
        
        # For backward compatibility: if ema_crossover type, set default 5/20 EMA
        params = summary.params.model_dump()
        if summary.strategy_type == StrategyType.ema_crossover:
            if "ema_fast" not in params or params.get("ema_fast") == 8:
                params["ema_fast"] = 5
            if "ema_slow" not in params or params.get("ema_slow") == 21:
                params["ema_slow"] = 20
            # Also set default TP/SL if not specified
            if "take_profit_pct" not in params:
                params["take_profit_pct"] = 0.005  # 0.5%
            if "stop_loss_pct" not in params:
                params["stop_loss_pct"] = 0.003  # 0.3%
        
        context = StrategyContext(
            id=summary.id,
            name=summary.name,
            symbol=summary.symbol,
            leverage=summary.leverage,
            risk_per_trade=summary.risk_per_trade,
            params=params,
            interval_seconds=summary.params.interval_seconds,
            metadata={},
        )
        strategy = self.registry.build(summary.strategy_type, context, self.client)
        task = asyncio.create_task(self._run_loop(strategy, summary))
        self._tasks[strategy_id] = task
        summary.status = StrategyState.running
        self._save_to_redis(strategy_id, summary)
        return summary

    async def stop(self, strategy_id: str) -> StrategySummary:
        if strategy_id not in self._strategies:
            raise KeyError(f"Strategy {strategy_id} not found")
        summary = self._strategies[strategy_id]
        
        # Check for open positions and close them
        try:
            position = self.client.get_open_position(summary.symbol)
            if position:
                logger.info(
                    f"Closing open position for strategy {strategy_id}: "
                    f"{position['positionAmt']} {summary.symbol} @ {position['entryPrice']} "
                    f"(Unrealized PnL: {position['unRealizedProfit']:.2f} USDT)"
                )
                close_order = self.client.close_position(summary.symbol)
                if close_order:
                    logger.info(
                        f"Position closed for strategy {strategy_id}: "
                        f"{close_order.side} {close_order.symbol} qty={close_order.executed_qty} @ {close_order.avg_price or close_order.price}"
                    )
                    # Track the closing trade
                    if strategy_id not in self._trades:
                        self._trades[strategy_id] = []
                    self._trades[strategy_id].append(close_order)
        except Exception as exc:
            logger.warning(f"Error closing position for strategy {strategy_id}: {exc}")
            # Continue with stopping even if position close fails
        
        # Stop the strategy task
        task = self._tasks.pop(strategy_id, None)
        if task:
            task.cancel()
        summary.status = StrategyState.stopped
        self._save_to_redis(strategy_id, summary)
        return summary

    def list_strategies(self) -> list[StrategySummary]:
        return list(self._strategies.values())
    
    def get_trades(self, strategy_id: str) -> List[OrderResponse]:
        """Get all executed trades for a strategy."""
        return self._trades.get(strategy_id, [])

    def calculate_strategy_stats(self, strategy_id: str) -> StrategyStats:
        """Calculate statistics for a specific strategy."""
        if strategy_id not in self._strategies:
            raise KeyError(f"Strategy {strategy_id} not found")
        
        strategy = self._strategies[strategy_id]
        
        # Ensure trades are loaded (from Redis if available, otherwise from memory)
        self._ensure_trades_loaded(strategy_id)
        
        trades = self._trades.get(strategy_id, [])
        
        # Log data source for transparency
        redis_status = "Redis" if (self.redis and self.redis.enabled) else "in-memory only"
        logger.debug(
            f"Calculating stats for {strategy_id} using {len(trades)} trades from {redis_status}"
        )
        
        # Calculate basic stats
        total_trades = len(trades)
        
        # Track positions to calculate PnL correctly for both LONG and SHORT
        # In One-Way mode: net position can be LONG (positive), SHORT (negative), or flat (zero)
        completed_trades = []
        position_queue = []  # List of (quantity, entry_price, side) tuples
        
        for trade in trades:
            entry_price = trade.avg_price or trade.price
            quantity = trade.executed_qty
            side = trade.side
            
            if side == "BUY":
                if position_queue and position_queue[0][2] == "SHORT":
                    # Closing or reducing SHORT position
                    remaining_qty = quantity
                    while remaining_qty > 0 and position_queue and position_queue[0][2] == "SHORT":
                        short_entry = position_queue[0]
                        short_qty = short_entry[0]
                        short_price = short_entry[1]
                        
                        if short_qty <= remaining_qty:
                            # Close entire SHORT position
                            close_qty = short_qty
                            position_queue.pop(0)
                        else:
                            # Partial close
                            close_qty = remaining_qty
                            position_queue[0] = (short_qty - remaining_qty, short_price, "SHORT")
                        
                        # PnL for SHORT: entry_price - exit_price (profit when price drops)
                        pnl = (short_price - entry_price) * close_qty
                        completed_trades.append({
                            "pnl": pnl,
                            "quantity": close_qty,
                            "side": "SHORT"
                        })
                        remaining_qty -= close_qty
                    
                    # If remaining quantity after closing SHORT, open LONG
                    if remaining_qty > 0:
                        position_queue.append((remaining_qty, entry_price, "LONG"))
                else:
                    # Opening or adding to LONG position
                    position_queue.append((quantity, entry_price, "LONG"))
            
            elif side == "SELL":
                if position_queue and position_queue[0][2] == "LONG":
                    # Closing or reducing LONG position
                    remaining_qty = quantity
                    while remaining_qty > 0 and position_queue and position_queue[0][2] == "LONG":
                        long_entry = position_queue[0]
                        long_qty = long_entry[0]
                        long_price = long_entry[1]
                        
                        if long_qty <= remaining_qty:
                            # Close entire LONG position
                            close_qty = long_qty
                            position_queue.pop(0)
                        else:
                            # Partial close
                            close_qty = remaining_qty
                            position_queue[0] = (long_qty - remaining_qty, long_price, "LONG")
                        
                        # PnL for LONG: exit_price - entry_price
                        pnl = (entry_price - long_price) * close_qty
                        completed_trades.append({
                            "pnl": pnl,
                            "quantity": close_qty,
                            "side": "LONG"
                        })
                        remaining_qty -= close_qty
                    
                    # If remaining quantity after closing LONG, open SHORT
                    if remaining_qty > 0:
                        position_queue.append((remaining_qty, entry_price, "SHORT"))
                else:
                    # Opening or adding to SHORT position
                    position_queue.append((quantity, entry_price, "SHORT"))
        
        # Calculate PnL statistics
        total_pnl = sum(t["pnl"] for t in completed_trades)
        winning_trades = len([t for t in completed_trades if t["pnl"] > 0])
        losing_trades = len([t for t in completed_trades if t["pnl"] < 0])
        win_rate = (winning_trades / len(completed_trades) * 100) if completed_trades else 0
        avg_profit_per_trade = total_pnl / len(completed_trades) if completed_trades else 0
        
        largest_win = max((t["pnl"] for t in completed_trades), default=0)
        largest_loss = min((t["pnl"] for t in completed_trades), default=0)
        
        # Get last trade timestamp - try to get from order_id or use current time
        last_trade_at = None
        if trades:
            # If trades have timestamps, use the latest; otherwise use current time
            last_trade_at = datetime.utcnow()
        
        logger.debug(
            f"Stats for {strategy_id}: {len(completed_trades)} completed trades, "
            f"total_pnl={total_pnl:.4f}, win_rate={win_rate:.2f}%"
        )
        
        return StrategyStats(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            symbol=strategy.symbol,
            total_trades=total_trades,
            completed_trades=len(completed_trades),
            total_pnl=round(total_pnl, 4),
            win_rate=round(win_rate, 2),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_profit_per_trade=round(avg_profit_per_trade, 4),
            largest_win=round(largest_win, 4),
            largest_loss=round(largest_loss, 4),
            created_at=strategy.created_at,
            last_trade_at=last_trade_at
        )
    
    def _ensure_trades_loaded(self, strategy_id: str) -> None:
        """Ensure trades for a strategy are available.
        
        Trades are always stored in memory (self._trades). If Redis is enabled,
        this method will attempt to load trades from Redis if they're not already
        in memory (e.g., after server restart). If Redis is disabled, trades are
        only available in memory during the current server session.
        """
        # Check if trades are already in memory
        if strategy_id in self._trades:
            trades_count = len(self._trades[strategy_id])
            logger.debug(
                f"Using {trades_count} in-memory trades for {strategy_id} "
                f"(Redis: {'enabled' if self.redis and self.redis.enabled else 'disabled'})"
            )
            return
        
        # If Redis is disabled, trades are only in memory (will be empty after restart)
        if not self.redis or not self.redis.enabled:
            logger.debug(
                f"No trades in memory for {strategy_id} and Redis is disabled. "
                f"Trades will only be available during current server session."
            )
            return
        
        # Try to load from Redis (e.g., after server restart)
        try:
            trades_data = self.redis.get_trades(strategy_id)
            if trades_data:
                trades = []
                for trade_data in trades_data:
                    try:
                        trade = OrderResponse(**trade_data)
                        # Filter out invalid trades (status NEW with zero execution)
                        if trade.status == "NEW" and trade.executed_qty == 0:
                            logger.debug(
                                f"Skipping invalid trade {trade.order_id} for {strategy_id}: "
                                f"status=NEW with zero execution"
                            )
                            continue
                        trades.append(trade)
                    except Exception as exc:
                        logger.warning(
                            f"Failed to parse trade data for {strategy_id}: {exc}, "
                            f"data: {trade_data}"
                        )
                        continue
                if trades:
                    self._trades[strategy_id] = trades
                    logger.info(f"Loaded {len(trades)} trades for {strategy_id} from Redis")
            else:
                logger.debug(f"No trades found in Redis for {strategy_id}")
        except Exception as exc:
            logger.warning(f"Failed to load trades for {strategy_id} from Redis: {exc}")

    def calculate_overall_stats(self) -> OverallStats:
        """Calculate overall statistics across all strategies."""
        all_stats = []
        for strategy_id in self._strategies.keys():
            try:
                stats = self.calculate_strategy_stats(strategy_id)
                all_stats.append(stats)
            except Exception as exc:
                logger.warning(f"Error calculating stats for strategy {strategy_id}: {exc}")
                continue
        
        total_strategies = len(self._strategies)
        active_strategies = len([s for s in self._strategies.values() if s.status == StrategyState.running])
        
        total_trades = sum(s.total_trades for s in all_stats)
        completed_trades = sum(s.completed_trades for s in all_stats)
        total_pnl = sum(s.total_pnl for s in all_stats)
        
        all_winning = sum(s.winning_trades for s in all_stats)
        all_losing = sum(s.losing_trades for s in all_stats)
        win_rate = (all_winning / (all_winning + all_losing) * 100) if (all_winning + all_losing) > 0 else 0
        avg_profit_per_trade = total_pnl / completed_trades if completed_trades > 0 else 0
        
        # Find best and worst performing strategies
        best_strategy = max(all_stats, key=lambda s: s.total_pnl, default=None)
        worst_strategy = min(all_stats, key=lambda s: s.total_pnl, default=None)
        
        return OverallStats(
            total_strategies=total_strategies,
            active_strategies=active_strategies,
            total_trades=total_trades,
            completed_trades=completed_trades,
            total_pnl=round(total_pnl, 4),
            win_rate=round(win_rate, 2),
            winning_trades=all_winning,
            losing_trades=all_losing,
            avg_profit_per_trade=round(avg_profit_per_trade, 4),
            best_performing_strategy=best_strategy.strategy_name if best_strategy else None,
            worst_performing_strategy=worst_strategy.strategy_name if worst_strategy else None
        )

    async def _run_loop(self, strategy: Strategy, summary: StrategySummary) -> None:
        logger.info(f"Starting loop for {summary.id}")
        try:
            while True:
                signal = await strategy.evaluate()
                summary.last_signal = signal.action  # type: ignore[assignment]
                
                # Log all signals for debugging
                logger.info(
                    f"[{summary.id}] Signal: {signal.action} | "
                    f"Symbol: {signal.symbol} | "
                    f"Price: {signal.price} | "
                    f"Confidence: {signal.confidence}"
                )
                
                # Update current price
                try:
                    summary.current_price = self.client.get_price(summary.symbol)
                except Exception as exc:
                    logger.warning(f"Failed to get current price for {summary.symbol}: {exc}")
                
                # Update position info and unrealized PnL
                await self._update_position_info(summary)
                
                await self._execute(signal, summary)
                await asyncio.sleep(strategy.context.interval_seconds)
        except asyncio.CancelledError:
            logger.info(f"Strategy {summary.id} cancelled")
            await strategy.teardown()
            raise
        except Exception as exc:
            summary.status = StrategyState.error
            self._save_to_redis(summary.id, summary)
            logger.exception(f"Strategy {summary.id} failed: {exc}")
    
    def _load_from_redis(self) -> None:
        """Load all strategies and trades from Redis on startup."""
        if not self.redis or not self.redis.enabled:
            logger.info("Redis not enabled, skipping load from Redis")
            return
        
        try:
            # Load all strategies
            strategies_data = self.redis.get_all_strategies()
            logger.info(f"Loading {len(strategies_data)} strategies from Redis")
            
            for strategy_id, data in strategies_data.items():
                try:
                    # Convert datetime strings back to datetime objects
                    if "created_at" in data and isinstance(data["created_at"], str):
                        data["created_at"] = datetime.fromisoformat(data["created_at"])
                    if "last_trade_at" in data and isinstance(data["last_trade_at"], str):
                        data["last_trade_at"] = datetime.fromisoformat(data["last_trade_at"])
                    
                    # Reconstruct StrategySummary from dict
                    summary = StrategySummary(**data)
                    self._strategies[strategy_id] = summary
                    
                    # Load trades for this strategy
                    trades_data = self.redis.get_trades(strategy_id)
                    if trades_data:
                        trades = []
                        for trade_data in trades_data:
                            # Handle any datetime fields if present
                            if "created_at" in trade_data and isinstance(trade_data["created_at"], str):
                                trade_data["created_at"] = datetime.fromisoformat(trade_data["created_at"])
                            trades.append(OrderResponse(**trade_data))
                        self._trades[strategy_id] = trades
                    
                    logger.debug(f"Loaded strategy {strategy_id} from Redis")
                except Exception as exc:
                    logger.warning(f"Failed to load strategy {strategy_id} from Redis: {exc}")
                    continue
            
            logger.info(f"Successfully loaded {len(self._strategies)} strategies from Redis")
        except Exception as exc:
            logger.error(f"Failed to load strategies from Redis: {exc}")
    
    def _save_to_redis(self, strategy_id: str, summary: StrategySummary) -> None:
        """Save strategy to Redis."""
        if not self.redis or not self.redis.enabled:
            return
        
        try:
            # Convert StrategySummary to dict
            strategy_data = summary.model_dump(mode='json')
            self.redis.save_strategy(strategy_id, strategy_data)
        except Exception as exc:
            logger.warning(f"Failed to save strategy {strategy_id} to Redis: {exc}")
    
    def _save_trades_to_redis(self, strategy_id: str) -> None:
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

    async def _execute(self, signal: StrategySignal, summary: StrategySummary) -> None:
        if signal.action == "HOLD":
            logger.debug(f"[{summary.id}] HOLD signal - skipping order execution")
            return
        
        # CRITICAL: Leverage in Binance is PER SYMBOL, not per strategy.
        # Binance defaults to 20x leverage if not explicitly set.
        # We MUST ensure leverage is explicitly set before every order to avoid accidental 20x.
        
        # Validate leverage is present and valid (should never be None due to model validation)
        if summary.leverage is None or not (1 <= summary.leverage <= 50):
            error_msg = (
                f"[{summary.id}] CRITICAL: Invalid or missing leverage for {summary.symbol}: {summary.leverage}. "
                "Leverage must be explicitly set (1-50) to avoid Binance's default 20x leverage."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            current_leverage = self.client.get_current_leverage(summary.symbol)
            if current_leverage != summary.leverage:
                logger.warning(
                    f"[{summary.id}] Leverage mismatch detected for {summary.symbol}: "
                    f"current={current_leverage}x (may be Binance default), target={summary.leverage}x. "
                    f"Resetting to {summary.leverage}x"
                )
                self.client.adjust_leverage(summary.symbol, summary.leverage)
            elif current_leverage is None:
                # No position yet, set leverage proactively to prevent Binance default
                logger.info(
                    f"[{summary.id}] Setting leverage {summary.leverage}x for {summary.symbol} "
                    f"(no existing position - preventing Binance 20x default)"
                )
                self.client.adjust_leverage(summary.symbol, summary.leverage)
            else:
                logger.debug(
                    f"[{summary.id}] Leverage already correct: {current_leverage}x for {summary.symbol}"
                )
        except Exception as exc:
            error_msg = (
                f"[{summary.id}] CRITICAL: Failed to verify/set leverage {summary.leverage}x for {summary.symbol}: {exc}. "
                "Order execution aborted to prevent accidental 20x leverage."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg) from exc
        
        # Get current position from Binance to ensure accurate size for closing
        current_position = self.client.get_open_position(summary.symbol)
        current_side = summary.position_side
        current_size = float(summary.position_size or 0)
        
        # If Binance has a position, use that size (more accurate than our tracking)
        if current_position and abs(float(current_position["positionAmt"])) > 0:
            position_amt = float(current_position["positionAmt"])
            current_size = abs(position_amt)
            current_side = "LONG" if position_amt > 0 else "SHORT"
        
        is_closing_long = current_side == "LONG" and current_size > 0 and signal.action == "SELL"
        is_closing_short = current_side == "SHORT" and current_size > 0 and signal.action == "BUY"
        force_close_quantity = None
        reduce_only_override: bool | None = None

        try:
            if is_closing_long or is_closing_short:
                price = signal.price or self.client.get_price(signal.symbol)
                force_close_quantity = current_size
                sizing = PositionSizingResult(
                    quantity=force_close_quantity,
                    notional=force_close_quantity * price,
                )
                reduce_only_override = True
                logger.info(
                    f"[{summary.id}] Closing entire position: {current_side} {current_size} {summary.symbol} "
                    f"(reduce_only=True)"
                )
            else:
                # Log sizing parameters for debugging
                price = signal.price or self.client.get_price(signal.symbol)
                logger.info(
                    f"[{summary.id}] Calculating position size: "
                    f"fixed_amount={summary.fixed_amount}, risk_per_trade={summary.risk_per_trade}, "
                    f"price={price}, symbol={signal.symbol}"
                )
                sizing = self.risk.size_position(
                    symbol=signal.symbol, 
                    risk_per_trade=summary.risk_per_trade, 
                    price=price,
                    fixed_amount=summary.fixed_amount
                )
                logger.info(
                    f"[{summary.id}] Position sizing result: qty={sizing.quantity}, notional={sizing.notional:.2f} USDT"
                )
        except ValueError as exc:
            # Handle minimum notional errors gracefully
            logger.error(f"[{summary.id}] Position sizing failed: {exc}")
            logger.error(f"[{summary.id}] Strategy will skip this signal. Please update strategy configuration.")
            return
        
        order_response = self.executor.execute(
            signal=signal,
            sizing=sizing,
            reduce_only_override=reduce_only_override,
        )
        if order_response:
            # Only track filled orders (or orders with execution data)
            # Orders with status "NEW" and zero execution data shouldn't be tracked
            if order_response.status == "NEW" and order_response.executed_qty == 0:
                logger.warning(
                    f"[{summary.id}] Order {order_response.order_id} status is NEW with zero execution. "
                    f"Skipping trade tracking. Order may not be filled yet."
                )
            else:
                # Track the executed trade in memory (always, regardless of Redis)
                if summary.id not in self._trades:
                    self._trades[summary.id] = []
                self._trades[summary.id].append(order_response)
                
                # Log trade tracking
                trades_count = len(self._trades[summary.id])
                redis_status = "enabled" if (self.redis and self.redis.enabled) else "disabled"
                logger.info(
                    f"[{summary.id}] Tracked trade {order_response.side} {order_response.symbol} "
                    f"order_id={order_response.order_id} status={order_response.status} "
                    f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price} "
                    f"(total trades: {trades_count}, Redis: {redis_status})"
                )
                
                # Optionally save to Redis if enabled (for persistence across server restarts)
                self._save_trades_to_redis(summary.id)
            
            # Update entry price and position size
            if order_response.side == "BUY":
                if summary.position_side == "SHORT":
                    remaining = max(0.0, (summary.position_size or 0.0) - order_response.executed_qty)
                    summary.position_size = remaining
                    if remaining == 0:
                        summary.entry_price = None
                        summary.position_side = None
                else:
                    summary.entry_price = order_response.avg_price or order_response.price
                    summary.position_size = order_response.executed_qty
                    summary.position_side = "LONG"
            elif order_response.side == "SELL":
                if summary.position_side == "LONG":
                    remaining = max(0.0, (summary.position_size or 0.0) - order_response.executed_qty)
                    summary.position_size = remaining
                    if remaining == 0:
                        summary.entry_price = None
                        summary.position_side = None
                else:
                    summary.entry_price = order_response.avg_price or order_response.price
                    summary.position_size = order_response.executed_qty
                    summary.position_side = "SHORT"
            
            logger.info(
                f"Trade executed for strategy {summary.id}: "
                f"{order_response.side} {order_response.symbol} "
                f"qty={order_response.executed_qty} @ {order_response.avg_price or order_response.price}"
            )

    async def _update_position_info(self, summary: StrategySummary) -> None:
        """Update position information and unrealized PnL for a strategy."""
        try:
            # Get current position from Binance
            position = self.client.get_open_position(summary.symbol)
            
            if position and abs(float(position["positionAmt"])) > 0:
                # Update position info from Binance
                position_amt = float(position["positionAmt"])
                summary.position_size = abs(position_amt)
                summary.entry_price = float(position["entryPrice"])
                summary.unrealized_pnl = float(position["unRealizedProfit"])
                summary.position_side = "LONG" if position_amt > 0 else "SHORT"
            else:
                # No open position
                if summary.position_size != 0:  # Position was closed
                    summary.entry_price = None
                    summary.position_size = 0
                    summary.unrealized_pnl = 0
                    summary.position_side = None
        except Exception as exc:
            logger.debug(f"Failed to update position info for {summary.symbol}: {exc}")
            # Calculate unrealized PnL manually if we have entry price and current price
            if summary.entry_price and summary.current_price and summary.position_size:
                summary.unrealized_pnl = (summary.current_price - summary.entry_price) * summary.position_size
            
            # Save updated summary to Redis (periodically, not every loop)
            # We'll save on state changes instead to reduce Redis writes

