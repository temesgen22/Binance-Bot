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
        logger.info(f"Registered strategy {strategy_id} ({payload.strategy_type})")
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
        trades = self._trades.get(strategy_id, [])
        
        # Calculate basic stats
        total_trades = len(trades)
        
        # Pair BUY and SELL trades to calculate PnL
        completed_trades = []
        open_positions = []
        
        for trade in trades:
            if trade.side == "BUY":
                open_positions.append(trade)
            elif trade.side == "SELL" and open_positions:
                # Match with the oldest BUY (FIFO)
                buy_trade = open_positions.pop(0)
                pnl = (trade.avg_price or trade.price) * trade.executed_qty - (buy_trade.avg_price or buy_trade.price) * buy_trade.executed_qty
                completed_trades.append({
                    "buy_trade": buy_trade,
                    "sell_trade": trade,
                    "pnl": pnl,
                    "quantity": min(trade.executed_qty, buy_trade.executed_qty)
                })
        
        # Calculate PnL statistics
        total_pnl = sum(t["pnl"] for t in completed_trades)
        winning_trades = len([t for t in completed_trades if t["pnl"] > 0])
        losing_trades = len([t for t in completed_trades if t["pnl"] < 0])
        win_rate = (winning_trades / len(completed_trades) * 100) if completed_trades else 0
        avg_profit_per_trade = total_pnl / len(completed_trades) if completed_trades else 0
        
        largest_win = max((t["pnl"] for t in completed_trades), default=0)
        largest_loss = min((t["pnl"] for t in completed_trades), default=0)
        
        # Get last trade timestamp (OrderResponse doesn't have created_at, use current time as placeholder)
        last_trade_at = datetime.utcnow() if trades else None
        
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
        current_side = summary.position_side
        current_size = float(summary.position_size or 0)
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
            else:
                # Ensure leverage configuration is applied before placing orders (Binance default is 20x)
                if summary.meta is None:
                    summary.meta = {}
                leverage_applied = summary.meta.get("leverage_applied", False)
                if not leverage_applied:
                    try:
                        self.client.adjust_leverage(summary.symbol, summary.leverage)
                        summary.meta["leverage_applied"] = True
                        self._save_to_redis(summary.id, summary)
                        logger.info(
                            f"[{summary.id}] Applied leverage {summary.leverage}x for {summary.symbol}"
                        )
                    except Exception as exc:
                        logger.warning(
                            f"[{summary.id}] Failed to apply leverage {summary.leverage}x for {summary.symbol}: {exc}"
                        )
                sizing = self.risk.size_position(
                    symbol=signal.symbol, 
                    risk_per_trade=summary.risk_per_trade, 
                    price=signal.price or self.client.get_price(signal.symbol),
                    fixed_amount=summary.fixed_amount
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
            # Track the executed trade
            if summary.id not in self._trades:
                self._trades[summary.id] = []
            self._trades[summary.id].append(order_response)
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

