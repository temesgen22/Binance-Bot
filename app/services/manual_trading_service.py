"""Service for standalone manual trading with Binance TP/SL features."""

import asyncio
import uuid as uuid_lib
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from app.core.mark_price_stream_manager import MarkPriceStreamManager

from loguru import logger
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.binance_client_manager import BinanceClientManager
from app.core.my_binance_client import BinanceClient
from app.core.paper_binance_client import PaperBinanceClient
from app.core.position_broadcast import PositionBroadcastService
from app.models.db_models import ManualPosition, ManualTrade, Account
from app.services.account_service import AccountService
from app.services.database_service import DatabaseService
from app.models.manual_trading import (
    ManualOpenRequest,
    ManualCloseRequest,
    ManualModifyTPSLRequest,
    ManualOpenResponse,
    ManualCloseResponse,
    ManualModifyResponse,
    ManualPositionResponse,
    ManualPositionListResponse,
    ManualTradeResponse,
)
from app.services.notifier import NotificationService


def get_open_manual_position(
    db: Session,
    user_id: UUID,
    account_id: str,
    symbol: str,
    position_side: str,
) -> Optional[ManualPosition]:
    """Return the open ManualPosition for this user/account/symbol/side, or None.
    Used by StrategyRunner when User Data Stream reports a position with no matching strategy.
    """
    return (
        db.query(ManualPosition)
        .filter(
            ManualPosition.user_id == user_id,
            ManualPosition.account_id == (account_id or "default"),
            ManualPosition.symbol == (symbol or "").strip().upper(),
            ManualPosition.side == (position_side or "").upper(),
            ManualPosition.status == "OPEN",
        )
        .first()
    )


def _close_open_manual_positions_externally_sync(
    db: Session,
    user_id: UUID,
    account_id: str,
    symbol: str,
    position_side: str,
) -> List[UUID]:
    """Find open manual positions for this user/account/symbol/side, set status=CLOSED, commit; return their ids."""
    positions = (
        db.query(ManualPosition)
        .filter(
            ManualPosition.user_id == user_id,
            ManualPosition.account_id == (account_id or "default"),
            ManualPosition.symbol == (symbol or "").strip().upper(),
            ManualPosition.side == (position_side or "").upper(),
            ManualPosition.status == "OPEN",
        )
        .all()
    )
    ids: List[UUID] = [p.id for p in positions]
    now = datetime.now(timezone.utc)
    for p in positions:
        p.status = "CLOSED"
        p.closed_at = now
    if ids:
        db.commit()
    return ids


async def notify_manual_positions_closed_externally(
    db: Session,
    user_id: UUID,
    account_id: str,
    symbol: str,
    position_side: str,
    broadcast_service: Optional[PositionBroadcastService],
    mark_price_stream_manager: Optional["MarkPriceStreamManager"] = None,
) -> None:
    """When Binance sends position_amt=0 and no strategy matched: close matching manual positions in DB,
    broadcast position_size=0 for each manual_<id>, and broadcast strategy_id=null so the GUI removes the row.
    Optionally unregisters from mark price stream so PnL stops updating.
    """
    closed_ids = await asyncio.to_thread(
        _close_open_manual_positions_externally_sync,
        db,
        user_id,
        account_id or "default",
        symbol,
        position_side,
    )
    if broadcast_service:
        for pid in closed_ids:
            await broadcast_service.broadcast_position_update(
                user_id=user_id,
                strategy_id=f"manual_{pid}",
                symbol=symbol,
                account_id=account_id or "default",
                position_size=0,
                position_side=position_side,
                strategy_name="Manual Trade",
            )
        await broadcast_service.broadcast_position_update(
            user_id=user_id,
            strategy_id=f"external_{position_side}",
            symbol=symbol,
            account_id=account_id or "default",
            position_size=0,
            position_side=position_side,
            strategy_name="External",
        )
    # Unregister from mark price stream so real-time PnL stops for closed manual positions
    if mark_price_stream_manager and closed_ids:
        try:
            for pid in closed_ids:
                mark_price_stream_manager.unregister_position(symbol, f"manual_{pid}")
            await mark_price_stream_manager.maybe_unsubscribe(symbol)
        except Exception as exc:
            logger.debug(f"[ManualTrade] mark price unregister (external close) failed: {exc}")


class ManualTradingService:
    """
    Standalone manual trading service with full Binance features.
    
    Features:
    - Open positions with market orders
    - Automatic TP/SL order placement (Binance native)
    - Trailing stop support
    - Partial close support
    - Real-time position tracking
    - Notification integration
    - WebSocket position broadcasts
    """
    
    def __init__(
        self,
        db: Session,
        client_manager: BinanceClientManager,
        user_id: UUID,
        notification_service: Optional[NotificationService] = None,
        broadcast_service: Optional[PositionBroadcastService] = None,
        mark_price_stream_manager: Optional["MarkPriceStreamManager"] = None,
    ):
        self.db = db
        self.client_manager = client_manager
        self.user_id = user_id
        self.notification_service = notification_service
        self.broadcast_service = broadcast_service
        self.mark_price_stream_manager = mark_price_stream_manager
    
    # ==================== Position Opening ====================
    
    async def open_position(self, request: ManualOpenRequest) -> ManualOpenResponse:
        """
        Open a manual position with optional TP/SL orders.
        
        Flow:
        1. Validate inputs and get client
        2. Set leverage and margin type
        3. Place market order
        4. Place TP/SL orders if specified
        5. Save to database
        6. Broadcast position update
        7. Send notification
        """
        client = self._get_client(request.account_id)
        symbol = request.symbol.upper()
        
        # Set leverage
        logger.info(f"[ManualTrade] Setting leverage {request.leverage}x for {symbol}")
        await asyncio.to_thread(client.adjust_leverage, symbol, request.leverage)
        
        # Set margin type if needed
        if request.margin_type:
            try:
                await asyncio.to_thread(
                    client.set_margin_type, symbol, request.margin_type
                )
            except Exception as e:
                logger.debug(f"Margin type setting note: {e}")
        
        # Get current price to calculate quantity from USDT amount
        current_price = await asyncio.to_thread(client.get_price, symbol)
        if not current_price or current_price <= 0:
            raise ValueError(f"Could not get price for {symbol}")
        
        # Calculate quantity from USDT amount
        # With leverage, the position size is: usdt_amount * leverage / price
        # But Binance uses notional value, so: quantity = usdt_amount / price
        # The leverage affects margin, not quantity
        raw_quantity = request.usdt_amount / current_price
        
        # Round to symbol's valid precision using client's built-in method
        quantity = await asyncio.to_thread(client.round_quantity, symbol, raw_quantity)
        
        logger.info(
            f"[ManualTrade] Calculated quantity: ${request.usdt_amount} USDT @ ${current_price} = {quantity} {symbol}"
        )
        
        # Place market order
        order_side = "BUY" if request.side == "LONG" else "SELL"
        logger.info(
            f"[ManualTrade] Opening {request.side} position: "
            f"{quantity} {symbol} @ market (${request.usdt_amount} USDT)"
        )
        
        order_response = await asyncio.to_thread(
            client.place_order,
            symbol=symbol,
            side=order_side,
            quantity=quantity,
            order_type="MARKET",
        )
        
        entry_price = float(order_response.avg_price or order_response.price)
        executed_qty = float(order_response.executed_qty)
        
        logger.info(
            f"[ManualTrade] Entry filled: {executed_qty} @ {entry_price}, "
            f"order_id={order_response.order_id}"
        )
        
        # Calculate TP/SL prices
        tp_price = self._calculate_tp_price(
            entry_price, request.side, request.take_profit_pct, request.tp_price
        )
        sl_price = self._calculate_sl_price(
            entry_price, request.side, request.stop_loss_pct, request.sl_price
        )
        
        logger.info(
            f"[ManualTrade] TP/SL calculated: entry={entry_price}, "
            f"tp_pct={request.take_profit_pct}, tp_price_req={request.tp_price}, tp_price_calc={tp_price}, "
            f"sl_pct={request.stop_loss_pct}, sl_price_req={request.sl_price}, sl_price_calc={sl_price}"
        )
        
        # Place TP/SL orders
        tp_order_id = None
        sl_order_id = None
        
        # Note: Trailing stop feature disabled for now (Binance API changes)
        # Place regular TP/SL orders instead
        if tp_price:
            tp_order_id = await self._place_take_profit_order(
                client, symbol, request.side, executed_qty, tp_price
            )
        if sl_price:
            sl_order_id = await self._place_stop_loss_order(
                client, symbol, request.side, executed_qty, sl_price
            )
        
        # Get position info for margin calculation
        position_info = await asyncio.to_thread(client.get_open_position, symbol)
        initial_margin = 0.0
        liquidation_price = None
        if position_info:
            initial_margin = float(position_info.get("initialMargin", 0) or 0)
            liquidation_price = float(position_info.get("liquidationPrice", 0) or 0)
            if initial_margin <= 0 and request.leverage > 0:
                notional = executed_qty * entry_price
                initial_margin = notional / request.leverage
        
        # Detect paper trading mode
        account = self._get_account(request.account_id)
        is_paper_trading = getattr(account, 'paper_trading', False)
        
        # Save to database
        position = ManualPosition(
            id=uuid_lib.uuid4(),
            user_id=self.user_id,
            account_id=request.account_id,
            symbol=symbol,
            side=request.side,
            quantity=Decimal(str(executed_qty)),
            remaining_quantity=Decimal(str(executed_qty)),
            entry_price=Decimal(str(entry_price)),
            leverage=request.leverage,
            margin_type=request.margin_type or "CROSSED",
            entry_order_id=order_response.order_id,
            tp_order_id=tp_order_id,
            sl_order_id=sl_order_id,
            take_profit_pct=Decimal(str(request.take_profit_pct)) if request.take_profit_pct else None,
            stop_loss_pct=Decimal(str(request.stop_loss_pct)) if request.stop_loss_pct else None,
            tp_price=Decimal(str(tp_price)) if tp_price else None,
            sl_price=Decimal(str(sl_price)) if sl_price else None,
            trailing_stop_enabled=request.trailing_stop_enabled,
            trailing_stop_callback_rate=Decimal(str(request.trailing_stop_callback_rate)) if request.trailing_stop_callback_rate else None,
            status="OPEN",
            notes=request.notes,
            paper_trading=is_paper_trading,
        )
        self.db.add(position)
        
        # Save entry trade
        entry_trade = ManualTrade(
            id=uuid_lib.uuid4(),
            position_id=position.id,
            user_id=self.user_id,
            order_id=order_response.order_id,
            symbol=symbol,
            side=order_side,
            order_type="MARKET",
            quantity=Decimal(str(executed_qty)),
            price=Decimal(str(entry_price)),
            trade_type="ENTRY",
            commission=Decimal(str(order_response.commission or 0)),
            commission_asset=order_response.commission_asset,
            executed_at=order_response.timestamp or datetime.now(timezone.utc),
        )
        self.db.add(entry_trade)
        self.db.commit()
        
        logger.info(f"[ManualTrade] Position saved: {position.id}")
        
        # Broadcast position update
        if self.broadcast_service:
            await self._broadcast_position(position, entry_price)
        
        # Register with mark price stream for real-time PnL (like strategy positions)
        if self.mark_price_stream_manager:
            try:
                qty = float(position.remaining_quantity or position.quantity)
                self.mark_price_stream_manager.register_position(
                    symbol=position.symbol,
                    strategy_id=f"manual_{position.id}",
                    user_id=self.user_id,
                    entry_price=float(position.entry_price),
                    position_size=qty,
                    position_side=position.side,
                    account_id=position.account_id,
                    leverage=position.leverage,
                    initial_margin=float(entry_price * executed_qty / position.leverage) if position.leverage else None,
                    strategy_name="Manual Trade",
                    position_instance_id=position.id,
                )
                await self.mark_price_stream_manager.subscribe(position.symbol)
            except Exception as exc:
                logger.debug(f"[ManualTrade] mark price register/subscribe failed: {exc}")
        
        # Send notification
        if self.notification_service:
            asyncio.create_task(
                self._notify_position_opened(position, entry_price)
            )
        
        return ManualOpenResponse(
            position_id=position.id,
            entry_order_id=order_response.order_id,
            symbol=symbol,
            side=request.side,
            quantity=executed_qty,
            entry_price=entry_price,
            leverage=request.leverage,
            margin_type=request.margin_type or "CROSSED",
            tp_order_id=tp_order_id,
            tp_price=tp_price,
            sl_order_id=sl_order_id,
            sl_price=sl_price,
            trailing_stop_enabled=request.trailing_stop_enabled,
            initial_margin=initial_margin,
            liquidation_price=liquidation_price,
            paper_trading=is_paper_trading,
            created_at=position.created_at,
        )
    
    # ==================== Position Closing ====================
    
    async def close_position(self, request: ManualCloseRequest) -> ManualCloseResponse:
        """Close a manual position (full or partial)."""
        position = self._get_position(request.position_id)
        client = self._get_client(position.account_id)
        
        remaining = float(position.remaining_quantity or position.quantity)
        close_qty = request.quantity if request.quantity else remaining
        close_qty = min(close_qty, remaining)
        is_full_close = close_qty >= remaining
        
        # Cancel existing TP/SL orders
        await self._cancel_tp_sl_orders(client, position)
        
        # Place close order
        close_side = "SELL" if position.side == "LONG" else "BUY"
        logger.info(
            f"[ManualTrade] Closing {close_qty} of {position.symbol} "
            f"({'full' if is_full_close else 'partial'})"
        )
        
        order_response = await asyncio.to_thread(
            client.place_order,
            symbol=position.symbol,
            side=close_side,
            quantity=close_qty,
            order_type="MARKET",
            reduce_only=True,
        )
        
        exit_price = float(order_response.avg_price or order_response.price)
        
        # Calculate PnL
        entry_price = float(position.entry_price)
        realized_pnl = self._calculate_realized_pnl(
            entry_price, exit_price, close_qty, position.side
        )
        fee = float(order_response.commission or 0)
        
        # Update position
        new_remaining = remaining - close_qty
        position.remaining_quantity = Decimal(str(new_remaining))
        
        if is_full_close:
            position.status = "CLOSED"
            position.exit_price = Decimal(str(exit_price))
            position.exit_order_id = order_response.order_id
            position.exit_reason = "MANUAL"
            position.realized_pnl = Decimal(str(realized_pnl))
            position.fee_paid = (position.fee_paid or Decimal(0)) + Decimal(str(fee))
            position.closed_at = datetime.now(timezone.utc)
        else:
            position.status = "PARTIAL_CLOSE"
        
        # Save exit trade
        exit_trade = ManualTrade(
            id=uuid_lib.uuid4(),
            position_id=position.id,
            user_id=self.user_id,
            order_id=order_response.order_id,
            symbol=position.symbol,
            side=close_side,
            order_type="MARKET",
            quantity=Decimal(str(close_qty)),
            price=Decimal(str(exit_price)),
            trade_type="EXIT" if is_full_close else "PARTIAL_CLOSE",
            commission=Decimal(str(fee)),
            commission_asset=order_response.commission_asset,
            realized_pnl=Decimal(str(realized_pnl)),
            executed_at=order_response.timestamp or datetime.now(timezone.utc),
        )
        self.db.add(exit_trade)
        self.db.commit()
        
        logger.info(
            f"[ManualTrade] Position {'closed' if is_full_close else 'partially closed'}: "
            f"PnL={realized_pnl:.2f}"
        )
        
        # Unregister from mark price stream when fully closed
        if is_full_close and self.mark_price_stream_manager:
            try:
                self.mark_price_stream_manager.unregister_position(
                    position.symbol, f"manual_{position.id}"
                )
                await self.mark_price_stream_manager.maybe_unsubscribe(position.symbol)
            except Exception as exc:
                logger.debug(f"[ManualTrade] mark price unregister/unsubscribe failed: {exc}")
        
        # Broadcast update
        if self.broadcast_service:
            if is_full_close:
                await self._broadcast_position_closed(position)
            else:
                await self._broadcast_position(position, exit_price)
        
        # Send notification
        if self.notification_service:
            asyncio.create_task(
                self._notify_position_closed(position, exit_price, realized_pnl)
            )
        
        return ManualCloseResponse(
            position_id=position.id,
            exit_order_id=order_response.order_id,
            symbol=position.symbol,
            side=position.side,
            closed_quantity=close_qty,
            remaining_quantity=new_remaining,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            fee_paid=fee,
            exit_reason="MANUAL",
            closed_at=datetime.now(timezone.utc),
        )
    
    def _calculate_realized_pnl(
        self,
        entry_price: float,
        exit_price: float,
        quantity: float,
        side: str,
    ) -> float:
        """Calculate realized PnL for a closed position."""
        if side == "LONG":
            return (exit_price - entry_price) * quantity
        else:
            return (entry_price - exit_price) * quantity
    
    # ==================== TP/SL Modification ====================
    
    async def modify_tp_sl(self, request: ManualModifyTPSLRequest) -> ManualModifyResponse:
        """Modify TP/SL orders on an existing position."""
        position = self._get_position(request.position_id)
        client = self._get_client(position.account_id)
        
        cancelled_orders = []
        entry_price = float(position.entry_price)
        quantity = float(position.remaining_quantity or position.quantity)
        
        # Calculate new prices
        new_tp_price = self._calculate_tp_price(
            entry_price, position.side, request.take_profit_pct, request.tp_price
        )
        new_sl_price = self._calculate_sl_price(
            entry_price, position.side, request.stop_loss_pct, request.sl_price
        )
        
        # Handle trailing stop changes
        if request.trailing_stop_enabled is not None:
            position.trailing_stop_enabled = request.trailing_stop_enabled
        if request.trailing_stop_callback_rate is not None:
            position.trailing_stop_callback_rate = Decimal(str(request.trailing_stop_callback_rate))
        
        # Cancel TP if requested or if placing new one
        if request.cancel_tp or new_tp_price:
            if position.tp_order_id:
                try:
                    await asyncio.to_thread(
                        client.cancel_order, position.symbol, position.tp_order_id
                    )
                    cancelled_orders.append(position.tp_order_id)
                    position.tp_order_id = None
                    position.tp_price = None
                except Exception as e:
                    logger.debug(f"Failed to cancel TP order: {e}")
        
        # Cancel SL if requested or if placing new one
        if request.cancel_sl or new_sl_price:
            if position.sl_order_id:
                try:
                    await asyncio.to_thread(
                        client.cancel_order, position.symbol, position.sl_order_id
                    )
                    cancelled_orders.append(position.sl_order_id)
                    position.sl_order_id = None
                    position.sl_price = None
                except Exception as e:
                    logger.debug(f"Failed to cancel SL order: {e}")
        
        # Place new TP order
        if new_tp_price and not request.cancel_tp:
            tp_order_id = await self._place_take_profit_order(
                client, position.symbol, position.side, quantity, new_tp_price
            )
            position.tp_order_id = tp_order_id
            position.tp_price = Decimal(str(new_tp_price))
            if request.take_profit_pct:
                position.take_profit_pct = Decimal(str(request.take_profit_pct))
        
        # Place new SL order
        if new_sl_price and not request.cancel_sl:
            sl_order_id = await self._place_stop_loss_order(
                client, position.symbol, position.side, quantity, new_sl_price
            )
            position.sl_order_id = sl_order_id
            position.sl_price = Decimal(str(new_sl_price))
            if request.stop_loss_pct:
                position.stop_loss_pct = Decimal(str(request.stop_loss_pct))
        
        self.db.commit()
        
        return ManualModifyResponse(
            position_id=position.id,
            symbol=position.symbol,
            tp_order_id=position.tp_order_id,
            tp_price=float(position.tp_price) if position.tp_price else None,
            sl_order_id=position.sl_order_id,
            sl_price=float(position.sl_price) if position.sl_price else None,
            trailing_stop_enabled=position.trailing_stop_enabled,
            cancelled_orders=cancelled_orders,
        )
    
    # ==================== Position Queries ====================
    
    async def get_position(self, position_id: UUID) -> ManualPositionResponse:
        """Get a single position with current market data."""
        position = self._get_position(position_id)
        return await self._enrich_position(position)
    
    async def list_positions(
        self,
        status: Optional[str] = None,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> ManualPositionListResponse:
        """List manual positions with optional filters."""
        query = self.db.query(ManualPosition).filter(
            ManualPosition.user_id == self.user_id
        )
        
        if status:
            query = query.filter(ManualPosition.status == status.upper())
        if account_id:
            query = query.filter(ManualPosition.account_id == account_id)
        if symbol:
            query = query.filter(ManualPosition.symbol == symbol.upper())
        
        positions = query.order_by(ManualPosition.created_at.desc()).all()
        
        enriched = []
        for pos in positions:
            enriched.append(await self._enrich_position(pos))
        
        open_count = sum(1 for p in enriched if p.status == "OPEN")
        closed_count = len(enriched) - open_count
        
        return ManualPositionListResponse(
            positions=enriched,
            total=len(enriched),
            open_count=open_count,
            closed_count=closed_count,
        )
    
    # ==================== Private Helpers ====================
    
    def _get_client(self, account_id: str) -> Union[BinanceClient, PaperBinanceClient]:
        """Get Binance client for the account after validating ownership.
        
        If the client is not loaded in the manager, it will be created on-demand
        from the account configuration in the database.
        """
        # First validate ownership
        account = self.db.query(Account).filter(
            and_(
                Account.account_id == account_id,
                Account.user_id == self.user_id,
            )
        ).first()
        if not account:
            raise ValueError(f"Account not found or access denied: {account_id}")
        
        # Try to get existing client
        client = self.client_manager.get_client(account_id)
        if client:
            return client
        
        # Client not loaded - create it on-demand
        logger.info(f"[ManualTrade] Creating client on-demand for account: {account_id}")
        
        # Use AccountService to get the account config (handles decryption)
        db_service = DatabaseService(self.db)
        account_service = AccountService(self.db)
        account_service.db_service = db_service
        
        account_config = account_service.get_account(self.user_id, account_id)
        if not account_config:
            raise ValueError(f"Could not load account config for: {account_id}")
        
        # Add client to manager
        self.client_manager.add_client(account_id, account_config)
        
        # Get the newly created client
        client = self.client_manager.get_client(account_id)
        if not client:
            raise ValueError(f"Failed to create Binance client for account: {account_id}")
        
        return client
    
    def _get_account(self, account_id: str) -> Account:
        """Get account record for paper trading detection etc."""
        account = self.db.query(Account).filter(
            and_(
                Account.account_id == account_id,
                Account.user_id == self.user_id,
            )
        ).first()
        if not account:
            raise ValueError(f"Account not found: {account_id}")
        return account
    
    def _get_position(self, position_id: UUID) -> ManualPosition:
        """Get a position owned by the current user."""
        position = self.db.query(ManualPosition).filter(
            and_(
                ManualPosition.id == position_id,
                ManualPosition.user_id == self.user_id,
            )
        ).first()
        if not position:
            raise ValueError(f"Position not found: {position_id}")
        return position
    
    def _calculate_tp_price(
        self,
        entry: float,
        side: str,
        pct: Optional[float],
        price: Optional[float],
    ) -> Optional[float]:
        """Calculate take profit price from percentage or absolute price.
        Preserves user decimals (e.g. 0.010580); Binance client rounds to tick size when placing."""
        # Validate absolute price - must be within reasonable range of entry
        if price is not None and price > entry * 0.5 and price < entry * 2:
            return float(price)
        # Fall back to percentage calculation
        if not pct:
            return None
        if side == "LONG":
            return round(entry * (1 + pct), 8)
        return round(entry * (1 - pct), 8)
    
    def _calculate_sl_price(
        self,
        entry: float,
        side: str,
        pct: Optional[float],
        price: Optional[float],
    ) -> Optional[float]:
        """Calculate stop loss price from percentage or absolute price.
        Preserves user decimals (e.g. 0.010580); Binance client rounds to tick size when placing."""
        # Validate absolute price - must be within reasonable range of entry
        if price is not None and price > entry * 0.5 and price < entry * 2:
            return float(price)
        # Fall back to percentage calculation
        if not pct:
            return None
        if side == "LONG":
            return round(entry * (1 - pct), 8)
        return round(entry * (1 + pct), 8)
    
    async def _place_take_profit_order(
        self,
        client: Union[BinanceClient, PaperBinanceClient],
        symbol: str,
        side: str,
        quantity: float,
        tp_price: float,
    ) -> Optional[int]:
        """Place Binance native TAKE_PROFIT_MARKET order.
        
        Uses the new Algo Order API (required since Dec 2025) with fallback to legacy API.
        """
        tp_side = "SELL" if side == "LONG" else "BUY"
        try:
            # Try the new Algo Order API first (required since December 2025)
            if hasattr(client, 'place_algo_take_profit'):
                response = await asyncio.to_thread(
                    client.place_algo_take_profit,
                    symbol=symbol,
                    side=tp_side,
                    quantity=quantity,
                    stop_price=tp_price,
                    close_position=True,
                )
            else:
                # Fall back to legacy API (for paper trading or older API)
                response = await asyncio.to_thread(
                    client.place_take_profit_order,
                    symbol=symbol,
                    side=tp_side,
                    quantity=quantity,
                    stop_price=tp_price,
                    close_position=True,
                )
            order_id = response.get("orderId") or response.get("algoId")
            logger.info(f"[ManualTrade] TP order placed: {order_id} @ {tp_price}")
            return order_id
        except Exception as e:
            # Extract the actual error from RetryError if present
            actual_error = e
            if hasattr(e, '__cause__') and e.__cause__:
                actual_error = e.__cause__
            elif hasattr(e, 'last_attempt') and hasattr(e.last_attempt, 'exception'):
                actual_error = e.last_attempt.exception()
            logger.error(f"[ManualTrade] Failed to place TP order @ {tp_price}: {actual_error}")
            return None
    
    async def _place_stop_loss_order(
        self,
        client: Union[BinanceClient, PaperBinanceClient],
        symbol: str,
        side: str,
        quantity: float,
        sl_price: float,
    ) -> Optional[int]:
        """Place Binance native STOP_MARKET order.
        
        Uses the new Algo Order API (required since Dec 2025) with fallback to legacy API.
        """
        sl_side = "SELL" if side == "LONG" else "BUY"
        try:
            # Try the new Algo Order API first (required since December 2025)
            if hasattr(client, 'place_algo_stop_loss'):
                response = await asyncio.to_thread(
                    client.place_algo_stop_loss,
                    symbol=symbol,
                    side=sl_side,
                    quantity=quantity,
                    stop_price=sl_price,
                    close_position=True,
                )
            else:
                # Fall back to legacy API (for paper trading or older API)
                response = await asyncio.to_thread(
                    client.place_stop_loss_order,
                    symbol=symbol,
                    side=sl_side,
                    quantity=quantity,
                    stop_price=sl_price,
                    close_position=True,
                )
            order_id = response.get("orderId") or response.get("algoId")
            logger.info(f"[ManualTrade] SL order placed: {order_id} @ {sl_price}")
            return order_id
        except Exception as e:
            # Extract the actual error from RetryError if present
            actual_error = e
            if hasattr(e, '__cause__') and e.__cause__:
                actual_error = e.__cause__
            elif hasattr(e, 'last_attempt') and hasattr(e.last_attempt, 'exception'):
                actual_error = e.last_attempt.exception()
            logger.error(f"[ManualTrade] Failed to place SL order @ {sl_price}: {actual_error}")
            return None
    
    async def _place_trailing_stop(
        self,
        client: Union[BinanceClient, PaperBinanceClient],
        symbol: str,
        side: str,
        quantity: float,
        tp_price: Optional[float],
        sl_price: Optional[float],
        callback_rate: float,
    ) -> tuple:
        """Place trailing stop orders."""
        tp_order_id = None
        sl_order_id = None
        
        # For trailing stop, place TP as regular order
        if tp_price:
            tp_order_id = await self._place_take_profit_order(
                client, symbol, side, quantity, tp_price
            )
        
        # Place trailing stop as SL
        if sl_price:
            sl_side = "SELL" if side == "LONG" else "BUY"
            try:
                response = await asyncio.to_thread(
                    client.place_trailing_stop_order,
                    symbol=symbol,
                    side=sl_side,
                    quantity=quantity,
                    callback_rate=callback_rate,
                    activation_price=sl_price,
                )
                sl_order_id = response.get("orderId")
                logger.info(f"[ManualTrade] Trailing stop placed: {sl_order_id}")
            except Exception as e:
                logger.error(f"[ManualTrade] Failed to place trailing stop: {e}")
                # Fall back to regular SL
                sl_order_id = await self._place_stop_loss_order(
                    client, symbol, side, quantity, sl_price
                )
        
        return tp_order_id, sl_order_id
    
    async def _cancel_tp_sl_orders(
        self,
        client: Union[BinanceClient, PaperBinanceClient],
        position: ManualPosition,
    ) -> List[int]:
        """Cancel existing TP/SL orders."""
        cancelled = []
        
        if position.tp_order_id:
            try:
                await asyncio.to_thread(
                    client.cancel_order, position.symbol, position.tp_order_id
                )
                cancelled.append(position.tp_order_id)
                logger.info(f"[ManualTrade] Cancelled TP order: {position.tp_order_id}")
            except Exception as e:
                logger.debug(f"Failed to cancel TP: {e}")
        
        if position.sl_order_id:
            try:
                await asyncio.to_thread(
                    client.cancel_order, position.symbol, position.sl_order_id
                )
                cancelled.append(position.sl_order_id)
                logger.info(f"[ManualTrade] Cancelled SL order: {position.sl_order_id}")
            except Exception as e:
                logger.debug(f"Failed to cancel SL: {e}")
        
        return cancelled
    
    async def _enrich_position(self, position: ManualPosition) -> ManualPositionResponse:
        """Add current market data to position response."""
        current_price = None
        unrealized_pnl = None
        liquidation_price = None
        initial_margin = None
        
        if position.status == "OPEN":
            try:
                client = self._get_client(position.account_id)
                pos_info = await asyncio.to_thread(
                    client.get_open_position, position.symbol
                )
                if pos_info:
                    current_price = float(pos_info.get("markPrice", 0) or 0)
                    unrealized_pnl = float(pos_info.get("unrealizedProfit", 0) or 0)
                    liquidation_price = float(pos_info.get("liquidationPrice", 0) or 0)
                    initial_margin = float(pos_info.get("initialMargin", 0) or 0)
            except Exception as e:
                logger.debug(f"Failed to enrich position: {e}")
        
        # Build trades list
        trades = [
            ManualTradeResponse(
                id=t.id,
                order_id=t.order_id,
                symbol=t.symbol,
                side=t.side,
                order_type=t.order_type,
                quantity=float(t.quantity),
                price=float(t.price),
                trade_type=t.trade_type,
                commission=float(t.commission) if t.commission else None,
                commission_asset=t.commission_asset,
                realized_pnl=float(t.realized_pnl) if t.realized_pnl else None,
                executed_at=t.executed_at,
            )
            for t in position.trades
        ]
        
        return ManualPositionResponse(
            id=position.id,
            user_id=position.user_id,
            account_id=position.account_id,
            symbol=position.symbol,
            side=position.side,
            quantity=float(position.quantity),
            remaining_quantity=float(position.remaining_quantity) if position.remaining_quantity else None,
            entry_price=float(position.entry_price),
            leverage=position.leverage,
            margin_type=position.margin_type,
            entry_order_id=position.entry_order_id,
            tp_order_id=position.tp_order_id,
            sl_order_id=position.sl_order_id,
            take_profit_pct=float(position.take_profit_pct) if position.take_profit_pct else None,
            stop_loss_pct=float(position.stop_loss_pct) if position.stop_loss_pct else None,
            tp_price=float(position.tp_price) if position.tp_price else None,
            sl_price=float(position.sl_price) if position.sl_price else None,
            trailing_stop_enabled=position.trailing_stop_enabled,
            trailing_stop_callback_rate=float(position.trailing_stop_callback_rate) if position.trailing_stop_callback_rate else None,
            status=position.status,
            paper_trading=position.paper_trading,
            exit_price=float(position.exit_price) if position.exit_price else None,
            exit_order_id=position.exit_order_id,
            exit_reason=position.exit_reason,
            realized_pnl=float(position.realized_pnl) if position.realized_pnl else None,
            fee_paid=float(position.fee_paid) if position.fee_paid else None,
            funding_fee=float(position.funding_fee) if position.funding_fee else None,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            liquidation_price=liquidation_price,
            initial_margin=initial_margin,
            created_at=position.created_at,
            updated_at=position.updated_at,
            closed_at=position.closed_at,
            notes=position.notes,
            trades=trades,
        )
    
    # ==================== WebSocket Broadcasting ====================
    
    async def _broadcast_position(self, position: ManualPosition, current_price: float):
        """Broadcast position update via WebSocket."""
        if not self.broadcast_service:
            return
        
        entry = float(position.entry_price)
        qty = float(position.remaining_quantity or position.quantity)
        if position.side == "LONG":
            unrealized_pnl = (current_price - entry) * qty
        else:
            unrealized_pnl = (entry - current_price) * qty
        
        manual_strategy_id = f"manual_{position.id}"
        
        await self.broadcast_service.broadcast_position_update(
            user_id=self.user_id,
            strategy_id=manual_strategy_id,
            symbol=position.symbol,
            account_id=position.account_id,
            position_size=qty,
            entry_price=entry,
            unrealized_pnl=unrealized_pnl,
            position_side=position.side,
            current_price=current_price,
            leverage=position.leverage,
            liquidation_price=None,
            initial_margin=entry * qty / position.leverage if position.leverage > 0 else None,
            margin_type=position.margin_type,
            strategy_name=f"Manual: {position.symbol}",
        )
    
    async def _broadcast_position_closed(self, position: ManualPosition):
        """Broadcast position closed (size=0)."""
        if not self.broadcast_service:
            return
        
        manual_strategy_id = f"manual_{position.id}"
        
        await self.broadcast_service.broadcast_position_update(
            user_id=self.user_id,
            strategy_id=manual_strategy_id,
            symbol=position.symbol,
            account_id=position.account_id,
            position_size=0,
            entry_price=0,
            unrealized_pnl=0,
            position_side=position.side,
            current_price=float(position.exit_price or 0),
            leverage=position.leverage,
            liquidation_price=None,
            initial_margin=None,
            margin_type=position.margin_type,
            strategy_name=f"Manual: {position.symbol}",
        )
    
    # ==================== Notifications ====================
    
    async def _notify_position_opened(self, position: ManualPosition, entry_price: float):
        """Send notification for position opened."""
        if not self.notification_service or not self.notification_service.telegram:
            return
        
        try:
            message = (
                f"📈 <b>Manual Position Opened</b>\n"
                f"Symbol: {position.symbol}\n"
                f"Side: {position.side}\n"
                f"Quantity: {float(position.quantity)}\n"
                f"Entry: ${entry_price:.2f}\n"
                f"Leverage: {position.leverage}x"
            )
            
            if position.tp_price:
                message += f"\nTP: ${float(position.tp_price):.2f}"
            if position.sl_price:
                message += f"\nSL: ${float(position.sl_price):.2f}"
            
            await self.notification_service.telegram.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send open notification: {e}")
    
    async def _notify_position_closed(
        self,
        position: ManualPosition,
        exit_price: float,
        realized_pnl: float,
    ):
        """Send notification for position closed."""
        if not self.notification_service or not self.notification_service.telegram:
            return
        
        try:
            emoji = "💰" if realized_pnl > 0 else "📉"
            message = (
                f"{emoji} <b>Manual Position Closed</b>\n"
                f"Symbol: {position.symbol}\n"
                f"Side: {position.side}\n"
                f"Entry: ${float(position.entry_price):.2f}\n"
                f"Exit: ${exit_price:.2f}\n"
                f"PnL: ${realized_pnl:.2f}"
            )
            
            await self.notification_service.telegram.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send close notification: {e}")
