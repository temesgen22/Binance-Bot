"""Test cases for Binance trade parameter capture and validation."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.order import OrderResponse
from app.models.trade import TradeWithTimestamp
from app.models.report import TradeReport, StrategyReport
from app.api.routes.trades import _convert_order_to_trade_with_timestamp
from app.api.routes.reports import _match_trades_to_completed_positions


class TestOrderResponseBinanceParameters:
    """Test OrderResponse model with Binance trade parameters."""
    
    def test_order_response_with_all_binance_parameters(self):
        """Test OrderResponse creation with all new Binance parameters."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        update_time = datetime(2024, 1, 15, 10, 30, 50, tzinfo=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.5,
            executed_qty=0.1,
            timestamp=order_time,
            commission=0.0195,
            commission_asset="USDT",
            leverage=10,
            position_side="LONG",
            update_time=update_time,
            time_in_force="GTC",
            order_type="MARKET",
            notional_value=5000.05,
            cummulative_quote_qty=5000.05,
            initial_margin=50.25,
            margin_type="ISOLATED",
            client_order_id="my_order_123",
            working_type="MARK_PRICE",
            realized_pnl=None,
            stop_price=None,
        )
        
        # Verify all fields
        assert order.symbol == "BTCUSDT"
        assert order.order_id == 12345
        assert order.timestamp == order_time
        assert order.commission == 0.0195
        assert order.commission_asset == "USDT"
        assert order.leverage == 10
        assert order.position_side == "LONG"
        assert order.initial_margin == 50.25
        assert order.margin_type == "ISOLATED"
        assert order.notional_value == 5000.05
        assert order.client_order_id == "my_order_123"
    
    def test_order_response_backward_compatibility(self):
        """Test that OrderResponse works without new optional fields (backward compatibility)."""
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            # All new fields omitted - should still work
        )
        
        assert order.symbol == "BTCUSDT"
        assert order.order_id == 12345
        assert order.timestamp is None
        assert order.commission is None
        assert order.leverage is None
        assert order.initial_margin is None
        # All optional fields should default to None


class TestTradeWithTimestampBinanceParameters:
    """Test TradeWithTimestamp model with Binance parameters."""
    
    def test_trade_with_timestamp_with_binance_parameters(self):
        """Test TradeWithTimestamp with all Binance parameters."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        
        trade = TradeWithTimestamp(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.5,
            executed_qty=0.1,
            timestamp=order_time,
            strategy_id="test-1",
            strategy_name="Test Strategy",
            commission=0.0195,
            commission_asset="USDT",
            leverage=10,
            initial_margin=50.25,
            margin_type="ISOLATED",
            notional_value=5000.05,
            client_order_id="my_order_123",
        )
        
        assert trade.timestamp == order_time
        assert trade.commission == 0.0195
        assert trade.commission_asset == "USDT"
        assert trade.leverage == 10
        assert trade.initial_margin == 50.25
        assert trade.margin_type == "ISOLATED"
        assert trade.notional_value == 5000.05
    
    def test_trade_with_timestamp_backward_compatibility(self):
        """Test TradeWithTimestamp works without new fields."""
        trade = TradeWithTimestamp(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            # New fields omitted
        )
        
        assert trade.commission is None
        assert trade.leverage is None
        assert trade.initial_margin is None


class TestConvertOrderToTradeWithTimestamp:
    """Test conversion function uses actual Binance timestamps."""
    
    def test_uses_actual_timestamp_from_order(self):
        """Test that conversion uses actual timestamp from OrderResponse."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=order_time,  # Actual Binance timestamp
        )
        
        trade = _convert_order_to_trade_with_timestamp(
            order=order,
            strategy_id="test-1",
            strategy_name="Test Strategy"
        )
        
        assert trade.timestamp == order_time, "Should use actual timestamp from order"
        assert trade.timestamp != datetime.now(timezone.utc).replace(microsecond=0), "Should not use current time"
    
    def test_uses_update_time_as_fallback(self):
        """Test that conversion uses update_time if timestamp not available."""
        update_time = datetime(2024, 1, 15, 10, 30, 50, tzinfo=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=None,  # Not available
            update_time=update_time,  # Use this as fallback
        )
        
        trade = _convert_order_to_trade_with_timestamp(
            order=order,
            strategy_id="test-1",
            strategy_name="Test Strategy"
        )
        
        assert trade.timestamp == update_time, "Should use update_time as fallback"
    
    def test_includes_binance_parameters_in_conversion(self):
        """Test that conversion includes all Binance parameters."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=12345,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=order_time,
            commission=0.0195,
            commission_asset="USDT",
            leverage=10,
            initial_margin=50.25,
            margin_type="ISOLATED",
            notional_value=5000.0,
        )
        
        trade = _convert_order_to_trade_with_timestamp(
            order=order,
            strategy_id="test-1",
            strategy_name="Test Strategy"
        )
        
        assert trade.commission == 0.0195
        assert trade.commission_asset == "USDT"
        assert trade.leverage == 10
        assert trade.initial_margin == 50.25
        assert trade.margin_type == "ISOLATED"
        assert trade.notional_value == 5000.0


class TestTradeReportBinanceParameters:
    """Test TradeReport model with Binance parameters."""
    
    def test_trade_report_with_all_binance_parameters(self):
        """Test TradeReport creation with all Binance parameters."""
        entry_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 15, 11, 30, 45, tzinfo=timezone.utc)
        
        trade = TradeReport(
            trade_id="1001",
            strategy_id="test-1",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=entry_time,
            entry_price=50000.0,
            exit_time=exit_time,
            exit_price=51000.0,
            quantity=0.1,
            leverage=10,
            fee_paid=4.0,
            pnl_usd=96.0,
            pnl_pct=1.92,
            exit_reason="TP",
            initial_margin=50.25,
            margin_type="ISOLATED",
            notional_value=5000.0,
            entry_order_id=1001,
            exit_order_id=1002,
        )
        
        assert trade.initial_margin == 50.25
        assert trade.margin_type == "ISOLATED"
        assert trade.notional_value == 5000.0
        assert trade.entry_order_id == 1001
        assert trade.exit_order_id == 1002
        assert trade.entry_time == entry_time
        assert trade.exit_time == exit_time
    
    def test_trade_report_backward_compatibility(self):
        """Test TradeReport works without new optional fields."""
        trade = TradeReport(
            trade_id="1001",
            strategy_id="test-1",
            symbol="BTCUSDT",
            side="LONG",
            entry_price=50000.0,
            exit_price=51000.0,
            quantity=0.1,
            leverage=5,
            fee_paid=4.0,
            pnl_usd=96.0,
            pnl_pct=1.92,
            # New fields omitted
        )
        
        assert trade.initial_margin is None
        assert trade.margin_type is None
        assert trade.notional_value is None
        assert trade.entry_order_id is None
        assert trade.exit_order_id is None


class TestReportGenerationWithBinanceParameters:
    """Test report generation includes Binance parameters."""
    
    def test_trade_matching_includes_binance_parameters(self):
        """Test that trade matching includes Binance parameters in TradeReport."""
        entry_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 15, 11, 30, 45, tzinfo=timezone.utc)
        
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=entry_time,
                commission=0.02,
                commission_asset="USDT",
                leverage=10,
                initial_margin=50.25,
                margin_type="ISOLATED",
                notional_value=5000.0,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=exit_time,
                commission=0.0204,
                commission_asset="USDT",
                leverage=10,
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-1",
            strategy_name="Test Strategy",
            symbol="BTCUSDT",
            leverage=10,
        )
        
        assert len(completed) == 1
        trade_report = completed[0]
        
        # Verify Binance parameters are included
        assert trade_report.entry_time == entry_time
        assert trade_report.exit_time == exit_time
        assert trade_report.entry_order_id == 1001
        assert trade_report.exit_order_id == 1002
        assert trade_report.leverage == 10  # From entry order
        # Initial margin and margin type should be from entry order
        assert trade_report.initial_margin == 50.25
        assert trade_report.margin_type == "ISOLATED"
        assert trade_report.notional_value == 5000.0
        # Fee should be sum of entry and exit fees
        assert trade_report.fee_paid > 0
        assert abs(trade_report.fee_paid - (0.02 + 0.0204)) < 0.001
    
    def test_trade_matching_uses_actual_leverage_from_order(self):
        """Test that trade matching uses actual leverage from order, not strategy default."""
        entry_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=entry_time,
                leverage=20,  # Actual leverage from Binance (different from strategy default)
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=entry_time.replace(hour=11),
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-1",
            strategy_name="Test Strategy",
            symbol="BTCUSDT",
            leverage=5,  # Strategy default leverage
        )
        
        assert len(completed) == 1
        # Should use actual leverage from order (20), not strategy default (5)
        assert completed[0].leverage == 20


class TestActualBinanceTimestampUsage:
    """Test that actual Binance timestamps are used instead of fallbacks."""
    
    def test_timestamp_priority_order(self):
        """Test timestamp priority: timestamp > update_time > current_time fallback."""
        order_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        update_time = datetime(2024, 1, 15, 10, 30, 50, tzinfo=timezone.utc)
        
        # Test 1: timestamp takes priority
        order1 = OrderResponse(
            symbol="BTCUSDT",
            order_id=1,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=order_time,
            update_time=update_time,
        )
        trade1 = _convert_order_to_trade_with_timestamp(order1)
        assert trade1.timestamp == order_time, "timestamp should take priority"
        
        # Test 2: update_time used when timestamp is None
        order2 = OrderResponse(
            symbol="BTCUSDT",
            order_id=2,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=None,
            update_time=update_time,
        )
        trade2 = _convert_order_to_trade_with_timestamp(order2)
        assert trade2.timestamp == update_time, "update_time should be used when timestamp is None"
    
    def test_commission_calculation_uses_actual_value(self):
        """Test that fee calculations use actual commission from orders."""
        entry_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=entry_time,
                commission=0.0195,  # Actual commission from Binance
                commission_asset="USDT",
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=entry_time.replace(hour=11),
                commission=0.0199,  # Actual commission from Binance
                commission_asset="USDT",
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-1",
            strategy_name="Test Strategy",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        # Fee should be actual commission from orders (approximately 0.0195 + 0.0199)
        assert abs(completed[0].fee_paid - (0.0195 + 0.0199)) < 0.001, \
            f"Fee should use actual commission values, got {completed[0].fee_paid}"


class TestStrategyReportSymbolField:
    """Test StrategyReport includes symbol field."""
    
    def test_strategy_report_includes_symbol(self):
        """Test that StrategyReport includes symbol field."""
        report = StrategyReport(
            strategy_id="test-1",
            strategy_name="Test Strategy",
            symbol="BTCUSDT",
            created_at=datetime.now(timezone.utc),
            stopped_at=None,
            total_trades=2,
            wins=1,
            losses=0,
            win_rate=100.0,
            total_profit_usd=96.0,
            total_loss_usd=0.0,
            net_pnl=96.0,
            trades=[],
        )
        
        assert report.symbol == "BTCUSDT"
        assert report.strategy_id == "test-1"

