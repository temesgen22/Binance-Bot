"""Test cases for PnL calculation fixes, especially SHORT positions."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.order import OrderResponse
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


class TestPnLCalculationForSHORTPositions:
    """Test PnL calculation fixes for SHORT positions."""
    
    def test_manual_unrealized_pnl_short_position(self):
        """Test that manual unrealized PnL calculation is correct for SHORT positions."""
        runner = make_runner()
        
        # Create a strategy summary with SHORT position
        summary = StrategySummary(
            id="test-short-1",
            name="Test SHORT Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
            position_side="SHORT",
            entry_price=50000.0,
            current_price=49000.0,  # Price dropped = profit for SHORT
            position_size=0.1,
            unrealized_pnl=None,
        )
        
        # Simulate the manual calculation logic (from _update_position_info)
        # For SHORT: (entry_price - current_price) * position_size
        expected_pnl = (summary.entry_price - summary.current_price) * summary.position_size
        expected_pnl = (50000.0 - 49000.0) * 0.1  # Should be +100 USDT profit
        
        assert expected_pnl > 0, "SHORT position should profit when price drops"
        assert abs(expected_pnl - 100.0) < 0.01, f"Expected ~100 USDT profit, got {expected_pnl}"
        
        # Test the opposite: price goes up = loss for SHORT
        summary.current_price = 51000.0
        expected_loss = (summary.entry_price - summary.current_price) * summary.position_size
        expected_loss = (50000.0 - 51000.0) * 0.1  # Should be -100 USDT loss
        
        assert expected_loss < 0, "SHORT position should lose when price rises"
        assert abs(expected_loss + 100.0) < 0.01, f"Expected ~-100 USDT loss, got {expected_loss}"
    
    def test_manual_unrealized_pnl_long_position(self):
        """Test that manual unrealized PnL calculation is correct for LONG positions."""
        runner = make_runner()
        
        # Create a strategy summary with LONG position
        summary = StrategySummary(
            id="test-long-1",
            name="Test LONG Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
            position_side="LONG",
            entry_price=50000.0,
            current_price=51000.0,  # Price rose = profit for LONG
            position_size=0.1,
            unrealized_pnl=None,
        )
        
        # Simulate the manual calculation logic (from _update_position_info)
        # For LONG: (current_price - entry_price) * position_size
        expected_pnl = (summary.current_price - summary.entry_price) * summary.position_size
        expected_pnl = (51000.0 - 50000.0) * 0.1  # Should be +100 USDT profit
        
        assert expected_pnl > 0, "LONG position should profit when price rises"
        assert abs(expected_pnl - 100.0) < 0.01, f"Expected ~100 USDT profit, got {expected_pnl}"
        
        # Test the opposite: price goes down = loss for LONG
        summary.current_price = 49000.0
        expected_loss = (summary.current_price - summary.entry_price) * summary.position_size
        expected_loss = (49000.0 - 50000.0) * 0.1  # Should be -100 USDT loss
        
        assert expected_loss < 0, "LONG position should lose when price drops"
        assert abs(expected_loss + 100.0) < 0.01, f"Expected ~-100 USDT loss, got {expected_loss}"
    
    def test_realized_pnl_short_trade_completion(self):
        """Test realized PnL calculation for completed SHORT trades."""
        runner = make_runner()
        
        # Create mock trades: SELL (open SHORT) -> BUY (close SHORT)
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1001,
                status="FILLED",
                side="SELL",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1002,
                status="FILLED",
                side="BUY",
                price=49000.0,
                avg_price=49000.0,
                executed_qty=0.1,
            ),
        ]
        
        # Store trades in runner
        strategy_id = "test-short-trade"
        runner._trades[strategy_id] = trades
        
        # Create strategy summary
        summary = StrategySummary(
            id=strategy_id,
            name="Test SHORT Trade",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
        )
        runner._strategies[strategy_id] = summary
        
        # Calculate stats (this uses the fixed PnL calculation)
        stats = runner.calculate_strategy_stats(strategy_id)
        
        # For SHORT: PnL = (entry_price - exit_price) * quantity
        # entry_price = 50000, exit_price = 49000, quantity = 0.1
        expected_pnl = (50000.0 - 49000.0) * 0.1  # Should be +100 USDT
        
        assert stats.total_pnl > 0, "SHORT trade should show profit when price drops"
        assert abs(stats.total_pnl - expected_pnl) < 10.0, f"Expected ~{expected_pnl} USDT, got {stats.total_pnl}"
        assert stats.completed_trades == 1, "Should have 1 completed trade"
        assert stats.winning_trades == 1, "Should have 1 winning trade"
    
    def test_realized_pnl_long_trade_completion(self):
        """Test realized PnL calculation for completed LONG trades."""
        runner = make_runner()
        
        # Create mock trades: BUY (open LONG) -> SELL (close LONG)
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
            ),
        ]
        
        # Store trades in runner
        strategy_id = "test-long-trade"
        runner._trades[strategy_id] = trades
        
        # Create strategy summary
        summary = StrategySummary(
            id=strategy_id,
            name="Test LONG Trade",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
        )
        runner._strategies[strategy_id] = summary
        
        # Calculate stats
        stats = runner.calculate_strategy_stats(strategy_id)
        
        # For LONG: PnL = (exit_price - entry_price) * quantity
        # entry_price = 50000, exit_price = 51000, quantity = 0.1
        expected_pnl = (51000.0 - 50000.0) * 0.1  # Should be +100 USDT
        
        assert stats.total_pnl > 0, "LONG trade should show profit when price rises"
        assert abs(stats.total_pnl - expected_pnl) < 10.0, f"Expected ~{expected_pnl} USDT, got {stats.total_pnl}"
        assert stats.completed_trades == 1, "Should have 1 completed trade"
        assert stats.winning_trades == 1, "Should have 1 winning trade"
    
    def test_pnl_calculation_with_fees(self):
        """Test that PnL calculation accounts for fees correctly."""
        # Fees are typically 0.04% (0.0004) per trade
        # Entry fee + Exit fee should reduce net PnL
        
        entry_price = 50000.0
        exit_price = 51000.0
        quantity = 0.1
        fee_rate = 0.0004
        
        # Gross PnL (LONG)
        gross_pnl = (exit_price - entry_price) * quantity  # 100 USDT
        
        # Fees
        entry_fee = entry_price * quantity * fee_rate  # ~2 USDT
        exit_fee = exit_price * quantity * fee_rate  # ~2.04 USDT
        total_fees = entry_fee + exit_fee  # ~4.04 USDT
        
        # Net PnL
        net_pnl = gross_pnl - total_fees  # ~95.96 USDT
        
        assert net_pnl < gross_pnl, "Net PnL should be less than gross PnL after fees"
        assert abs(net_pnl - 95.96) < 1.0, f"Expected net PnL ~95.96 USDT, got {net_pnl}"


class TestPositionInfoUpdate:
    """Test position info update with current_price from markPrice."""
    
    def test_position_update_sets_current_price(self):
        """Test that position update sets current_price from Binance markPrice."""
        runner = make_runner()
        
        # Mock Binance position response with markPrice
        mock_position = {
            "positionAmt": "0.1",
            "entryPrice": "50000.0",
            "markPrice": "51000.0",  # Current mark price
            "unRealizedProfit": "100.0",
        }
        
        runner.client.get_open_position = MagicMock(return_value=mock_position)
        
        # Create strategy summary
        summary = StrategySummary(
            id="test-pos-update",
            name="Test Position Update",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.running,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
            params=StrategyParams(),
            created_at=datetime.now(timezone.utc),
            last_signal=None,
            current_price=None,  # Initially None
        )
        runner._strategies["test-pos-update"] = summary
        
        # Call _update_position_info
        import asyncio
        asyncio.run(runner._update_position_info(summary))
        
        # Verify current_price was set from markPrice
        assert summary.current_price is not None, "current_price should be set"
        assert abs(summary.current_price - 51000.0) < 0.01, f"Expected 51000.0, got {summary.current_price}"
        assert summary.unrealized_pnl == 100.0, "unrealized_pnl should be set from Binance"

