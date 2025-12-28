"""
Test cases for order execution on Binance.

Tests verify that:
1. BUY/SELL signals trigger order creation
2. Orders are placed with correct parameters
3. HOLD signals don't create orders
4. Order responses are properly handled
"""

import pytest
pytestmark = pytest.mark.ci  # Order execution tests are critical (except TestOrderExecutionIntegration which is marked slow)

from unittest.mock import MagicMock, AsyncMock, patch, call
from datetime import datetime

from app.services.order_executor import OrderExecutor
from app.services.strategy_runner import StrategyRunner
from app.strategies.base import StrategySignal
from app.core.my_binance_client import BinanceClient
from app.models.order import OrderResponse
from app.risk.manager import RiskManager, PositionSizingResult
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams


@pytest.fixture
def mock_binance_client():
    """Create a mock BinanceClient."""
    client = MagicMock(spec=BinanceClient)
    client.get_price = MagicMock(return_value=40000.0)
    client.get_klines = MagicMock(return_value=[])
    client.get_open_position = MagicMock(return_value=None)
    client.adjust_leverage = MagicMock(return_value={"leverage": 5})
    return client


@pytest.fixture
def mock_order_response():
    """Create a mock OrderResponse."""
    return OrderResponse(
        symbol="BTCUSDT",
        side="BUY",
        order_id=12345,
        price=40000.0,
        executed_qty=0.001,
        avg_price=40000.0,
        status="FILLED",
        order_type="MARKET",
    )


@pytest.fixture
def risk_manager(mock_binance_client):
    """Create a RiskManager instance."""
    return RiskManager(client=mock_binance_client)


@pytest.fixture
def order_executor(mock_binance_client):
    """Create an OrderExecutor instance."""
    return OrderExecutor(client=mock_binance_client)


@pytest.fixture
def strategy_summary():
    """Create a strategy summary for testing."""
    return StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.01,
        fixed_amount=1000.0,
        params=StrategyParams(
            ema_fast=8,
            ema_slow=21,
            take_profit_pct=0.004,
            stop_loss_pct=0.002,
            interval_seconds=10,
        ),
        created_at=datetime.now(),
        last_signal="HOLD",
        current_price=40000.0,
        entry_price=None,
        position_size=None,
    )


class TestOrderExecutor:
    """Test OrderExecutor functionality."""
    
    def test_hold_signal_skips_order(self, order_executor, mock_binance_client):
        """Test that HOLD signals don't create orders."""
        signal = StrategySignal(
            action="HOLD",
            symbol="BTCUSDT",
            confidence=0.2,
            price=40000.0
        )
        sizing = PositionSizingResult(quantity=0.001, notional=40.0)
        
        result = order_executor.execute(signal=signal, sizing=sizing)
        
        assert result is None
        mock_binance_client.place_order.assert_not_called()
    
    def test_buy_signal_creates_order(self, order_executor, mock_binance_client, mock_order_response):
        """Test that BUY signals create orders."""
        mock_binance_client.place_order.return_value = mock_order_response
        
        signal = StrategySignal(
            action="BUY",
            symbol="BTCUSDT",
            confidence=0.75,
            price=40000.0
        )
        sizing = PositionSizingResult(quantity=0.001, notional=40.0)
        
        result = order_executor.execute(signal=signal, sizing=sizing)
        
        assert result is not None
        assert result.symbol == "BTCUSDT"
        assert result.side == "BUY"
        # Verify place_order was called with client_order_id (for idempotency)
        mock_binance_client.place_order.assert_called_once()
        call_args = mock_binance_client.place_order.call_args
        assert call_args.kwargs["symbol"] == "BTCUSDT"
        assert call_args.kwargs["side"] == "BUY"
        assert call_args.kwargs["quantity"] == 0.001
        assert call_args.kwargs["order_type"] == "MARKET"
        assert call_args.kwargs["reduce_only"] is False
        assert "client_order_id" in call_args.kwargs
        assert call_args.kwargs["client_order_id"].startswith("IDEMP_")
    
    def test_sell_signal_creates_order(self, order_executor, mock_binance_client, mock_order_response):
        """Test that SELL signals create orders."""
        mock_order_response.side = "SELL"
        mock_binance_client.place_order.return_value = mock_order_response
        
        signal = StrategySignal(
            action="SELL",
            symbol="BTCUSDT",
            confidence=0.75,
            price=40000.0
        )
        sizing = PositionSizingResult(quantity=0.001, notional=40.0)
        
        result = order_executor.execute(signal=signal, sizing=sizing)
        
        assert result is not None
        assert result.side == "SELL"
        # Verify place_order was called with client_order_id (for idempotency)
        mock_binance_client.place_order.assert_called_once()
        call_args = mock_binance_client.place_order.call_args
        assert call_args.kwargs["symbol"] == "BTCUSDT"
        assert call_args.kwargs["side"] == "SELL"
        assert call_args.kwargs["quantity"] == 0.001
        assert call_args.kwargs["order_type"] == "MARKET"
        assert call_args.kwargs["reduce_only"] is False
        assert "client_order_id" in call_args.kwargs
        assert call_args.kwargs["client_order_id"].startswith("IDEMP_")
    
    def test_close_signal_uses_reduce_only(self, order_executor, mock_binance_client, mock_order_response):
        """Test that CLOSE signals use reduce_only=True."""
        # CLOSE action maps to SELL side (to close long position)
        mock_order_response.side = "SELL"
        mock_binance_client.place_order.return_value = mock_order_response
        
        signal = StrategySignal(
            action="CLOSE",
            symbol="BTCUSDT",
            confidence=0.85,
            price=40000.0
        )
        sizing = PositionSizingResult(quantity=0.001, notional=40.0)
        
        result = order_executor.execute(signal=signal, sizing=sizing)
        
        assert result is not None
        # CLOSE maps to SELL (to close position), but reduce_only=True
        # Verify place_order was called with client_order_id (for idempotency)
        mock_binance_client.place_order.assert_called_once()
        call_args = mock_binance_client.place_order.call_args
        assert call_args.kwargs["symbol"] == "BTCUSDT"
        assert call_args.kwargs["side"] == "SELL"  # CLOSE maps to SELL (closing long)
        assert call_args.kwargs["quantity"] == 0.001
        assert call_args.kwargs["order_type"] == "MARKET"
        assert call_args.kwargs["reduce_only"] is True  # CLOSE uses reduce_only
        assert "client_order_id" in call_args.kwargs
        assert call_args.kwargs["client_order_id"].startswith("IDEMP_")


class TestStrategyRunnerOrderExecution:
    """Test StrategyRunner order execution flow."""
    
    @pytest.mark.asyncio
    async def test_hold_signal_does_not_execute_order(
        self, 
        mock_binance_client, 
        risk_manager, 
        order_executor,
        strategy_summary
    ):
        """Test that HOLD signals don't trigger order execution."""
        runner = StrategyRunner(
            client=mock_binance_client,
            risk=risk_manager,
            executor=order_executor,
            max_concurrent=3,
        )
        
        signal = StrategySignal(
            action="HOLD",
            symbol="BTCUSDT",
            confidence=0.2,
            price=40000.0
        )
        
        await runner.order_manager.execute_order(signal, strategy_summary)
        
        # Verify no order was placed
        mock_binance_client.place_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_buy_signal_executes_order(
        self, 
        mock_binance_client, 
        risk_manager, 
        order_executor,
        strategy_summary,
        mock_order_response
    ):
        """Test that BUY signals execute orders."""
        # Mock position sizing
        with patch.object(risk_manager, 'size_position', return_value=PositionSizingResult(quantity=0.001, notional=40.0)):
            mock_binance_client.place_order.return_value = mock_order_response
            # Mock get_open_position to return a position after BUY order
            # This simulates Binance having the position after order execution
            mock_binance_client.get_open_position.return_value = {
                "positionAmt": "0.001",
                "entryPrice": "40000.0",
                "unRealizedProfit": "0.0",
                "markPrice": "40000.0"
            }
            # Mock get_open_orders to return empty (no TP/SL orders yet)
            mock_binance_client.get_open_orders = MagicMock(return_value=[])
            
            runner = StrategyRunner(
                client=mock_binance_client,
                risk=risk_manager,
                executor=order_executor,
                max_concurrent=3,
            )
            
            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0
            )
            
            await runner.order_manager.execute_order(signal, strategy_summary)
            
            # Verify order was placed
            mock_binance_client.place_order.assert_called_once()
            assert strategy_summary.entry_price == 40000.0
            assert strategy_summary.position_size == 0.001
    
    @pytest.mark.asyncio
    async def test_sell_signal_executes_order(
        self, 
        mock_binance_client, 
        risk_manager, 
        order_executor,
        strategy_summary,
        mock_order_response
    ):
        """Test that SELL signals execute orders."""
        # Set up existing position
        strategy_summary.position_size = 0.001
        strategy_summary.position_side = "LONG"
        strategy_summary.entry_price = 39000.0
        
        mock_order_response.side = "SELL"
        
        # Mock position sizing
        with patch.object(risk_manager, 'size_position', return_value=PositionSizingResult(quantity=0.001, notional=40.0)):
            mock_binance_client.place_order.return_value = mock_order_response
            
            runner = StrategyRunner(
                client=mock_binance_client,
                risk=risk_manager,
                executor=order_executor,
                max_concurrent=3,
            )
            
            signal = StrategySignal(
                action="SELL",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0
            )
            
            await runner.order_manager.execute_order(signal, strategy_summary)
            
            # Verify order was placed
            mock_binance_client.place_order.assert_called_once()
            # Position should be reduced
            assert strategy_summary.position_size == 0.0
            assert strategy_summary.entry_price is None

    @pytest.mark.asyncio
    async def test_sell_signal_closes_entire_position_without_risk_sizing(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
        mock_order_response,
    ):
        """SELL while long should close the full position without re-sizing."""
        strategy_summary.position_size = 0.5
        strategy_summary.position_side = "LONG"
        strategy_summary.entry_price = 30000.0
        mock_order_response.side = "SELL"
        mock_order_response.executed_qty = 0.5

        runner = StrategyRunner(
            client=mock_binance_client,
            risk=risk_manager,
            executor=order_executor,
            max_concurrent=3,
        )

        signal = StrategySignal(
            action="SELL",
            symbol="BTCUSDT",
            confidence=0.85,
            price=31000.0,
        )

        with patch.object(
            risk_manager,
            "size_position",
            side_effect=AssertionError("size_position should not be called when closing"),
        ):
            mock_binance_client.place_order.return_value = mock_order_response
            await runner.order_manager.execute_order(signal, strategy_summary)

        # Verify place_order was called with client_order_id (for idempotency)
        mock_binance_client.place_order.assert_called_once()
        call_args = mock_binance_client.place_order.call_args
        assert call_args.kwargs["symbol"] == "BTCUSDT"
        assert call_args.kwargs["side"] == "SELL"
        assert call_args.kwargs["quantity"] == 0.5
        assert call_args.kwargs["order_type"] == "MARKET"
        assert call_args.kwargs["reduce_only"] is True
        assert "client_order_id" in call_args.kwargs
        assert call_args.kwargs["client_order_id"].startswith("IDEMP_")
        assert strategy_summary.position_size == 0
        assert strategy_summary.position_side is None
        assert strategy_summary.entry_price is None
    
    @pytest.mark.asyncio
    async def test_order_execution_failure_handled(
        self, 
        mock_binance_client, 
        risk_manager, 
        order_executor,
        strategy_summary
    ):
        """Test that order execution failures are handled gracefully."""
        # Mock position sizing
        with patch.object(risk_manager, 'size_position', return_value=PositionSizingResult(quantity=0.001, notional=40.0)):
            # Mock order placement to raise an exception
            mock_binance_client.place_order.side_effect = Exception("Binance API error")
            
            runner = StrategyRunner(
                client=mock_binance_client,
                risk=risk_manager,
                executor=order_executor,
                max_concurrent=3,
            )
            
            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0
            )
            
            # Should not raise exception, but handle gracefully
            try:
                await runner.order_manager.execute_order(signal, strategy_summary)
            except Exception:
                # If exception is raised, it should be caught and logged
                pass
            
            # Verify order was attempted
            mock_binance_client.place_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_position_sizing_failure_handled(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary
    ):
        """Test that position sizing failures are handled gracefully."""
        from app.core.exceptions import PositionSizingError
        
        # Mock position sizing to raise ValueError (e.g., minimum notional)
        with patch.object(risk_manager, 'size_position', side_effect=ValueError("Notional too small")):
            runner = StrategyRunner(
                client=mock_binance_client,
                risk=risk_manager,
                executor=order_executor,
                max_concurrent=3,
            )
            
            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0
            )
            
            # Should raise PositionSizingError (converted from ValueError)
            with pytest.raises(PositionSizingError, match="Notional too small"):
                await runner.order_manager.execute_order(signal, strategy_summary)
            
            # Verify no order was placed
            mock_binance_client.place_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_leverage_applied_before_first_trade(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
        mock_order_response
    ):
        """Ensure leverage configuration is checked and applied before first trade."""
        # Mock get_current_leverage to return None (no position yet)
        mock_binance_client.get_current_leverage.return_value = None
        with patch.object(
            risk_manager,
            "size_position",
            return_value=PositionSizingResult(quantity=0.001, notional=40.0),
        ):
            mock_binance_client.place_order.return_value = mock_order_response

            runner = StrategyRunner(
                client=mock_binance_client,
                risk=risk_manager,
                executor=order_executor,
                max_concurrent=3,
            )

            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0,
            )

            await runner.order_manager.execute_order(signal, strategy_summary)

            # Should check current leverage and set it to target
            mock_binance_client.get_current_leverage.assert_called_once_with("BTCUSDT")
            mock_binance_client.adjust_leverage.assert_called_once_with("BTCUSDT", 5)

    @pytest.mark.asyncio
    async def test_leverage_applied_when_closing_position(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
        mock_order_response
    ):
        """Ensure leverage is checked and applied even when closing a position (not just opening)."""
        strategy_summary.position_size = 0.5
        strategy_summary.position_side = "LONG"
        
        # Mock current leverage as different (20x instead of 5x)
        mock_binance_client.get_current_leverage.return_value = 20
        
        # Mock Binance position
        mock_binance_client.get_open_position.return_value = {
            "positionAmt": "0.5",
            "entryPrice": "39000.0",
            "unRealizedProfit": "500.0"
        }
        
        mock_order_response.side = "SELL"
        mock_binance_client.place_order.return_value = mock_order_response

        runner = StrategyRunner(
            client=mock_binance_client,
            risk=risk_manager,
            executor=order_executor,
            max_concurrent=3,
        )

        signal = StrategySignal(
            action="SELL",
            symbol="BTCUSDT",
            confidence=0.85,
            price=40000.0,
        )

        await runner.order_manager.execute_order(signal, strategy_summary)

        # Leverage should be checked and reset to target even when closing
        mock_binance_client.get_current_leverage.assert_called_once_with("BTCUSDT")
        mock_binance_client.adjust_leverage.assert_called_once_with("BTCUSDT", 5)
        # Verify order was placed with reduce_only
        mock_binance_client.place_order.assert_called_once()
        call_args = mock_binance_client.place_order.call_args
        assert call_args.kwargs["reduce_only"] is True
        assert call_args.kwargs["quantity"] == 0.5  # Exact position size

    @pytest.mark.asyncio
    async def test_leverage_not_reapplied_when_already_set(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
        mock_order_response
    ):
        """Ensure leverage is checked but not reset if already at target."""
        # Mock current leverage as already correct (5x)
        mock_binance_client.get_current_leverage.return_value = 5
        with patch.object(
            risk_manager,
            "size_position",
            return_value=PositionSizingResult(quantity=0.001, notional=40.0),
        ):
            mock_binance_client.place_order.return_value = mock_order_response

            runner = StrategyRunner(
                client=mock_binance_client,
                risk=risk_manager,
                executor=order_executor,
                max_concurrent=3,
            )

            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0,
            )

            await runner.order_manager.execute_order(signal, strategy_summary)

            # Should check leverage but not adjust since it's already correct
            mock_binance_client.get_current_leverage.assert_called_once_with("BTCUSDT")
            mock_binance_client.adjust_leverage.assert_not_called()


@pytest.mark.slow
class TestOrderExecutionIntegration:
    """Integration tests for complete order execution flow."""
    
    @pytest.mark.asyncio
    async def test_complete_buy_order_flow(
        self, 
        mock_binance_client, 
        risk_manager, 
        order_executor,
        strategy_summary,
        mock_order_response
    ):
        """Test complete flow from signal to order execution."""
        # Mock all dependencies
        with patch.object(risk_manager, 'size_position', return_value=PositionSizingResult(quantity=0.001, notional=40.0)):
            mock_binance_client.place_order.return_value = mock_order_response
            # Mock get_open_position to return a position after BUY order
            # This simulates Binance having the position after order execution
            mock_binance_client.get_open_position.return_value = {
                "positionAmt": "0.001",
                "entryPrice": "40000.0",
                "unRealizedProfit": "0.0",
                "markPrice": "40000.0"
            }
            # Mock get_open_orders to return empty (no TP/SL orders yet)
            mock_binance_client.get_open_orders = MagicMock(return_value=[])
            
            runner = StrategyRunner(
                client=mock_binance_client,
                risk=risk_manager,
                executor=order_executor,
                max_concurrent=3,
            )
            
            # Create BUY signal
            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0
            )
            
            # Execute
            await runner.order_manager.execute_order(signal, strategy_summary)
            
            # Verify complete flow
            risk_manager.size_position.assert_called_once_with(
                symbol="BTCUSDT",
                risk_per_trade=0.01,
                price=40000.0,
                fixed_amount=1000.0,
            )
            mock_binance_client.place_order.assert_called_once()
            
            # Verify strategy summary updated
            assert strategy_summary.entry_price == 40000.0
            assert strategy_summary.position_size == 0.001
            
            # Verify trade was tracked
            assert strategy_summary.id in runner._trades
            assert len(runner._trades[strategy_summary.id]) == 1
    
    @pytest.mark.asyncio
    async def test_complete_sell_order_flow(
        self, 
        mock_binance_client, 
        risk_manager, 
        order_executor,
        strategy_summary,
        mock_order_response
    ):
        """Test complete flow for SELL order execution."""
        # Set up existing position
        strategy_summary.position_size = 0.001
        strategy_summary.position_side = "LONG"
        strategy_summary.entry_price = 39000.0
        
        mock_order_response.side = "SELL"
        
        # Mock all dependencies
        with patch.object(risk_manager, 'size_position', return_value=PositionSizingResult(quantity=0.001, notional=40.0)):
            mock_binance_client.place_order.return_value = mock_order_response
            
            runner = StrategyRunner(
                client=mock_binance_client,
                risk=risk_manager,
                executor=order_executor,
                max_concurrent=3,
            )
            
            # Create SELL signal
            signal = StrategySignal(
                action="SELL",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0
            )
            
            # Execute
            await runner.order_manager.execute_order(signal, strategy_summary)
            
            # Verify order was placed
            mock_binance_client.place_order.assert_called_once()
            
            # Verify position was closed
            assert strategy_summary.position_size == 0.0
            assert strategy_summary.entry_price is None
            
            # Verify trade was tracked
            assert strategy_summary.id in runner._trades
            assert len(runner._trades[strategy_summary.id]) == 1


class TestTradeTrackingAndPersistence:
    """Test that trade values are properly tracked and saved with all parameters."""
    
    @pytest.fixture
    def mock_binance_client(self):
        """Create a mock BinanceClient that returns proper order responses."""
        client = MagicMock(spec=BinanceClient)
        client.get_price = MagicMock(return_value=40000.0)
        client.get_klines = MagicMock(return_value=[])
        client.get_open_position = MagicMock(return_value=None)
        client.adjust_leverage = MagicMock(return_value={"leverage": 5})
        client.get_current_leverage = MagicMock(return_value=5)
        return client
    
    @pytest.fixture
    def risk_manager(self, mock_binance_client):
        """Create a RiskManager instance."""
        return RiskManager(client=mock_binance_client)
    
    @pytest.fixture
    def order_executor(self, mock_binance_client):
        """Create an OrderExecutor instance."""
        return OrderExecutor(client=mock_binance_client)
    
    @pytest.fixture
    def strategy_summary(self):
        """Create a strategy summary for testing."""
        return StrategySummary(
            id="test-trade-tracking",
            name="Test Trade Tracking",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            params=StrategyParams(
                ema_fast=8,
                ema_slow=21,
                take_profit_pct=0.004,
                stop_loss_pct=0.002,
                interval_seconds=10,
            ),
            created_at=datetime.utcnow(),
            last_signal=None,
            entry_price=None,
            current_price=None,
            position_size=None,
            unrealized_pnl=None,
            meta={},
        )
    
    def test_trade_values_properly_tracked_in_memory(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
    ):
        """Test that all trade parameters are correctly tracked when saved to memory."""
        # Mock order response with all values
        order_response = OrderResponse(
            symbol="BTCUSDT",
            order_id=123456789,
            status="FILLED",
            side="BUY",
            price=40000.0,
            avg_price=40001.5,
            executed_qty=0.025,
        )
        mock_binance_client.place_order.return_value = order_response
        
        runner = StrategyRunner(
            client=mock_binance_client,
            risk=risk_manager,
            executor=order_executor,
            max_concurrent=3,
        )
        
        # Mock position sizing
        with patch.object(
            risk_manager,
            "size_position",
            return_value=PositionSizingResult(quantity=0.025, notional=1000.0),
        ):
            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0,
            )
            
            # Execute order
            import asyncio
            asyncio.run(runner.order_manager.execute_order(signal, strategy_summary))
        
        # Verify trade is tracked in memory
        assert strategy_summary.id in runner._trades
        trades = runner._trades[strategy_summary.id]
        assert len(trades) == 1
        
        # Verify ALL parameters are correctly saved
        tracked_trade = trades[0]
        assert tracked_trade.symbol == "BTCUSDT"
        assert tracked_trade.order_id == 123456789
        assert tracked_trade.status == "FILLED"
        assert tracked_trade.side == "BUY"
        assert tracked_trade.price == 40000.0
        assert tracked_trade.avg_price == 40001.5
        assert tracked_trade.executed_qty == 0.025
    
    def test_multiple_trades_values_tracked_correctly(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
    ):
        """Test that multiple trades are tracked with correct values."""
        runner = StrategyRunner(
            client=mock_binance_client,
            risk=risk_manager,
            executor=order_executor,
            max_concurrent=3,
        )
        
        # Create multiple trades with different values
        trade1 = OrderResponse(
            symbol="BTCUSDT",
            order_id=111111,
            status="FILLED",
            side="BUY",
            price=40000.0,
            avg_price=40001.0,
            executed_qty=0.01,
        )
        trade2 = OrderResponse(
            symbol="BTCUSDT",
            order_id=222222,
            status="FILLED",
            side="SELL",
            price=41000.0,
            avg_price=41001.5,
            executed_qty=0.01,
        )
        
        mock_binance_client.place_order.side_effect = [trade1, trade2]
        
        with patch.object(
            risk_manager,
            "size_position",
            return_value=PositionSizingResult(quantity=0.01, notional=400.0),
        ):
            # Execute BUY order
            signal1 = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0,
            )
            import asyncio
            asyncio.run(runner.order_manager.execute_order(signal1, strategy_summary))
            
            # Update position for SELL
            strategy_summary.position_size = 0.01
            strategy_summary.position_side = "LONG"
            
            # Execute SELL order
            signal2 = StrategySignal(
                action="SELL",
                symbol="BTCUSDT",
                confidence=0.75,
                price=41000.0,
            )
            asyncio.run(runner.order_manager.execute_order(signal2, strategy_summary))
        
        # Verify both trades are tracked
        trades = runner._trades[strategy_summary.id]
        assert len(trades) == 2
        
        # Verify first trade values
        assert trades[0].order_id == 111111
        assert trades[0].side == "BUY"
        assert trades[0].avg_price == 40001.0
        assert trades[0].executed_qty == 0.01
        
        # Verify second trade values
        assert trades[1].order_id == 222222
        assert trades[1].side == "SELL"
        assert trades[1].avg_price == 41001.5
        assert trades[1].executed_qty == 0.01
    
    def test_invalid_trade_filtered_out(self, mock_binance_client, risk_manager, order_executor, strategy_summary):
        """Test that trades with status NEW and zero execution are not tracked."""
        runner = StrategyRunner(
            client=mock_binance_client,
            risk=risk_manager,
            executor=order_executor,
            max_concurrent=3,
        )
        
        # Mock invalid order (status NEW with zero execution)
        invalid_order = OrderResponse(
            symbol="BTCUSDT",
            order_id=999999,
            status="NEW",
            side="BUY",
            price=40000.0,  # Set price to avoid formatting issues
            avg_price=40000.0,  # Set avg_price to avoid formatting issues
            executed_qty=0.0,
        )
        mock_binance_client.place_order.return_value = invalid_order
        # Mock get_order_status to return the same invalid order (still NEW after verification)
        mock_binance_client.get_order_status.return_value = {
            "orderId": 999999,
            "status": "NEW",
            "side": "BUY",
            "symbol": "BTCUSDT",
            "executedQty": "0",
            "price": "40000.0",
            "avgPrice": "40000.0",
        }
        # Mock _parse_order_response to return the invalid order
        mock_binance_client._parse_order_response = MagicMock(return_value=invalid_order)
        
        with patch.object(
            risk_manager,
            "size_position",
            return_value=PositionSizingResult(quantity=0.01, notional=400.0),
        ):
            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0,
            )
            
            import asyncio
            asyncio.run(runner.order_manager.execute_order(signal, strategy_summary))
        
        # Verify invalid trade was NOT tracked
        assert strategy_summary.id not in runner._trades or len(runner._trades[strategy_summary.id]) == 0
    
    def test_trades_can_be_retrieved_after_tracking(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
    ):
        """Test that tracked trades can be retrieved via get_trades()."""
        runner = StrategyRunner(
            client=mock_binance_client,
            risk=risk_manager,
            executor=order_executor,
            max_concurrent=3,
        )
        
        order_response = OrderResponse(
            symbol="ETHUSDT",
            order_id=987654321,
            status="FILLED",
            side="SELL",
            price=3000.0,
            avg_price=3001.25,
            executed_qty=0.5,
        )
        mock_binance_client.place_order.return_value = order_response
        
        with patch.object(
            risk_manager,
            "size_position",
            return_value=PositionSizingResult(quantity=0.5, notional=1500.0),
        ):
            signal = StrategySignal(
                action="SELL",
                symbol="ETHUSDT",
                confidence=0.8,
                price=3000.0,
            )
            
            import asyncio
            asyncio.run(runner.order_manager.execute_order(signal, strategy_summary))
        
        # Retrieve trades via get_trades()
        retrieved_trades = runner.get_trades(strategy_summary.id)
        
        # Verify trade was retrieved with all values
        assert len(retrieved_trades) == 1
        trade = retrieved_trades[0]
        assert trade.symbol == "ETHUSDT"
        assert trade.order_id == 987654321
        assert trade.status == "FILLED"
        assert trade.side == "SELL"
        assert trade.price == 3000.0
        assert trade.avg_price == 3001.25
        assert trade.executed_qty == 0.5
    
    def test_trade_with_none_avg_price_handled_correctly(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
    ):
        """Test that trades with None avg_price are handled correctly."""
        runner = StrategyRunner(
            client=mock_binance_client,
            risk=risk_manager,
            executor=order_executor,
            max_concurrent=3,
        )
        
        # Order with None avg_price (should use price instead)
        order_response = OrderResponse(
            symbol="BTCUSDT",
            order_id=555555,
            status="FILLED",
            side="BUY",
            price=40000.0,
            avg_price=None,
            executed_qty=0.001,
        )
        mock_binance_client.place_order.return_value = order_response
        
        with patch.object(
            risk_manager,
            "size_position",
            return_value=PositionSizingResult(quantity=0.001, notional=40.0),
        ):
            signal = StrategySignal(
                action="BUY",
                symbol="BTCUSDT",
                confidence=0.75,
                price=40000.0,
            )
            
            import asyncio
            asyncio.run(runner.order_manager.execute_order(signal, strategy_summary))
        
        # Verify trade tracked with None avg_price
        trades = runner._trades[strategy_summary.id]
        assert len(trades) == 1
        assert trades[0].avg_price is None
        assert trades[0].price == 40000.0
        assert trades[0].executed_qty == 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

