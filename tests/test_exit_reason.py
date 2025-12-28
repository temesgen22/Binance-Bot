"""Test cases for exit_reason tracking in trades and reports."""

import pytest
pytestmark = pytest.mark.ci  # Exit reason tracking is critical
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.order import OrderResponse
from app.models.report import TradeReport
from app.api.routes.reports import _match_trades_to_completed_positions, get_trading_report
from app.services.strategy_runner import StrategyRunner
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams


class DummyRedis:
    enabled = False


def make_runner():
    """Create a mock StrategyRunner for testing."""
    client = MagicMock()
    risk = MagicMock()
    executor = MagicMock()
    return StrategyRunner(
        client=client,
        risk=risk,
        executor=executor,
        max_concurrent=2,
        redis_storage=DummyRedis(),
    )


class TestExitReasonTracking:
    """Test that exit_reason is correctly tracked and displayed in reports."""
    
    def test_exit_reason_from_signal_is_stored(self):
        """Test that exit_reason from strategy signal is stored in OrderResponse."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                exit_reason=None,  # Entry order has no exit_reason
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                exit_reason="TP",  # Exit order with TP exit_reason
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-exit-1",
            strategy_name="Test Exit Reason",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1, "Should have 1 completed trade"
        trade = completed[0]
        assert trade.exit_reason == "TP", f"Exit reason should be 'TP', got '{trade.exit_reason}'"
    
    def test_exit_reason_tp_from_order(self):
        """Test that TP exit_reason is correctly extracted from exit order."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=2001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=2002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                exit_reason="TP",
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-tp",
            strategy_name="Test TP",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        assert completed[0].exit_reason == "TP", f"Expected 'TP', got '{completed[0].exit_reason}'"
    
    def test_exit_reason_sl_from_order(self):
        """Test that SL exit_reason is correctly extracted from exit order."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=3001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=3002,
                status="FILLED",
                side="SELL",
                price=49000.0,
                avg_price=49000.0,
                executed_qty=0.1,
                exit_reason="SL",
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-sl",
            strategy_name="Test SL",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        assert completed[0].exit_reason == "SL", f"Expected 'SL', got '{completed[0].exit_reason}'"
    
    def test_exit_reason_ema_cross_from_order(self):
        """Test that EMA_CROSS exit_reason is correctly extracted from exit order."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=4001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=4002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                exit_reason="EMA_DEATH_CROSS",
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-ema",
            strategy_name="Test EMA Cross",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        assert completed[0].exit_reason == "EMA_DEATH_CROSS", \
            f"Expected 'EMA_DEATH_CROSS', got '{completed[0].exit_reason}'"
    
    def test_exit_reason_tp_trailing_from_order(self):
        """Test that TP_TRAILING exit_reason is correctly extracted."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=5001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=5002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                exit_reason="TP_TRAILING",
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-trailing",
            strategy_name="Test Trailing Stop",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        assert completed[0].exit_reason == "TP_TRAILING", \
            f"Expected 'TP_TRAILING', got '{completed[0].exit_reason}'"
    
    def test_exit_reason_from_binance_native_tp_order(self):
        """Test that exit_reason is detected from Binance native TP order type."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=6001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=6002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                order_type="TAKE_PROFIT_MARKET",  # Binance native TP order
                exit_reason=None,  # Not set in signal
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-native-tp",
            strategy_name="Test Native TP",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        # Should detect from order_type
        assert completed[0].exit_reason == "TP", \
            f"Expected 'TP' from order_type, got '{completed[0].exit_reason}'"
    
    def test_exit_reason_from_binance_native_sl_order(self):
        """Test that exit_reason is detected from Binance native SL order type."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=7001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=7002,
                status="FILLED",
                side="SELL",
                price=49000.0,
                avg_price=49000.0,
                executed_qty=0.1,
                order_type="STOP_MARKET",  # Binance native SL order
                exit_reason=None,  # Not set in signal
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-native-sl",
            strategy_name="Test Native SL",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        # Should detect from order_type
        assert completed[0].exit_reason == "SL", \
            f"Expected 'SL' from order_type, got '{completed[0].exit_reason}'"
    
    def test_exit_reason_defaults_to_manual_when_missing(self):
        """Test that exit_reason defaults to 'MANUAL' when not set and order_type doesn't indicate TP/SL."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=8001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=8002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                order_type="MARKET",  # Regular market order
                exit_reason=None,  # Not set
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-manual",
            strategy_name="Test Manual",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        # Should default to MANUAL when exit_reason is None and order_type doesn't indicate TP/SL
        assert completed[0].exit_reason == "MANUAL", \
            f"Expected 'MANUAL' when exit_reason is missing, got '{completed[0].exit_reason}'"
    
    def test_exit_reason_prefers_signal_over_order_type(self):
        """Test that exit_reason from signal takes precedence over order_type detection."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=9001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=9002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                order_type="TAKE_PROFIT_MARKET",  # Would suggest TP
                exit_reason="TP_TRAILING",  # But signal says TP_TRAILING
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-preference",
            strategy_name="Test Preference",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1
        # Should prefer exit_reason from signal over order_type
        assert completed[0].exit_reason == "TP_TRAILING", \
            f"Expected 'TP_TRAILING' from signal, got '{completed[0].exit_reason}'"
    
    def test_exit_reason_in_full_report(self):
        """Test that exit_reason appears correctly in full trading reports."""
        runner = make_runner()
        
        strategy_id = "test-exit-report"
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=10001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=10002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
                exit_reason="TP",
            ),
        ]
        runner._trades[strategy_id] = trades
        
        summary = StrategySummary(
            id=strategy_id,
            name="Test Exit Report",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
        )
        runner._strategies[strategy_id] = summary
        
        client = MagicMock()
        
        with patch('app.api.routes.reports.get_strategy_runner', return_value=runner):
            with patch('app.api.routes.reports.get_binance_client', return_value=client):
                report = get_trading_report(
                    strategy_id=strategy_id,
                    strategy_name=None,
                    symbol=None,
                    start_date=None,
                    end_date=None,
                    runner=runner,
                    client=client,
                )
        
        assert len(report.strategies) == 1
        strategy_report = report.strategies[0]
        assert len(strategy_report.trades) == 1
        
        trade = strategy_report.trades[0]
        assert trade.exit_reason == "TP", \
            f"Expected 'TP' in report, got '{trade.exit_reason}'"
    
    def test_multiple_trades_with_different_exit_reasons(self):
        """Test that multiple trades can have different exit reasons."""
        trades = [
            # Trade 1: TP
            OrderResponse(
                symbol="BTCUSDT",
                order_id=11001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=11002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
                exit_reason="TP",
            ),
            # Trade 2: SL
            OrderResponse(
                symbol="BTCUSDT",
                order_id=11003,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=11004,
                status="FILLED",
                side="SELL",
                price=49000.0,
                avg_price=49000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
                exit_reason="SL",
            ),
            # Trade 3: EMA_CROSS
            OrderResponse(
                symbol="BTCUSDT",
                order_id=11005,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=11006,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
                exit_reason="EMA_DEATH_CROSS",
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-multiple-exits",
            strategy_name="Test Multiple Exits",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 3, "Should have 3 completed trades"
        assert completed[0].exit_reason == "TP", f"Trade 1 should be TP, got '{completed[0].exit_reason}'"
        assert completed[1].exit_reason == "SL", f"Trade 2 should be SL, got '{completed[1].exit_reason}'"
        assert completed[2].exit_reason == "EMA_DEATH_CROSS", \
            f"Trade 3 should be EMA_DEATH_CROSS, got '{completed[2].exit_reason}'"

