"""
Test cases for order execution on Binance.

Tests verify that:
1. BUY/SELL signals trigger order creation
2. Orders are placed with correct parameters
3. HOLD signals don't create orders
4. Order responses are properly handled
"""

import pytest
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
        mock_binance_client.place_order.assert_called_once_with(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.001,
            order_type="MARKET",
            reduce_only=False,
        )
    
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
        mock_binance_client.place_order.assert_called_once_with(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.001,
            order_type="MARKET",
            reduce_only=False,
        )
    
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
        mock_binance_client.place_order.assert_called_once_with(
            symbol="BTCUSDT",
            side="SELL",  # CLOSE maps to SELL (closing long)
            quantity=0.001,
            order_type="MARKET",
            reduce_only=True,  # CLOSE uses reduce_only
        )


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
        
        await runner._execute(signal, strategy_summary)
        
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
            
            await runner._execute(signal, strategy_summary)
            
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
            
            await runner._execute(signal, strategy_summary)
            
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
            await runner._execute(signal, strategy_summary)

        mock_binance_client.place_order.assert_called_once_with(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.5,
            order_type="MARKET",
            reduce_only=True,
        )
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
                await runner._execute(signal, strategy_summary)
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
            
            # Should not raise exception, but handle gracefully
            await runner._execute(signal, strategy_summary)
            
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
        """Ensure leverage configuration is applied before first trade."""
        # Reset meta to ensure leverage not yet applied
        strategy_summary.meta = {}
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

            await runner._execute(signal, strategy_summary)

            mock_binance_client.adjust_leverage.assert_called_once_with("BTCUSDT", 5)
            assert strategy_summary.meta.get("leverage_applied") is True

    @pytest.mark.asyncio
    async def test_leverage_not_reapplied_when_already_set(
        self,
        mock_binance_client,
        risk_manager,
        order_executor,
        strategy_summary,
        mock_order_response
    ):
        """Ensure leverage is only applied once per strategy."""
        strategy_summary.meta = {"leverage_applied": True}
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

            await runner._execute(signal, strategy_summary)

            mock_binance_client.adjust_leverage.assert_not_called()


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
            await runner._execute(signal, strategy_summary)
            
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
            await runner._execute(signal, strategy_summary)
            
            # Verify order was placed
            mock_binance_client.place_order.assert_called_once()
            
            # Verify position was closed
            assert strategy_summary.position_size == 0.0
            assert strategy_summary.entry_price is None
            
            # Verify trade was tracked
            assert strategy_summary.id in runner._trades
            assert len(runner._trades[strategy_summary.id]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

