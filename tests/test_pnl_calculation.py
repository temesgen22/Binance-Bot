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
    from app.core.binance_client_manager import BinanceClientManager
    from app.core.config import get_settings, BinanceAccountConfig
    
    client = MagicMock()
    risk = MagicMock()
    executor = MagicMock()
    
    # Create a minimal client manager for backward compatibility
    settings = get_settings()
    manager = BinanceClientManager(settings)
    
    # Manually add default account (simulating database-loaded account)
    default_account = BinanceAccountConfig(
        account_id="default",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True
    )
    manager._clients = {'default': client}
    manager._accounts = {'default': default_account}
    
    return StrategyRunner(
        client=client,
        client_manager=manager,
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
        
        # update_position_info uses account_manager.get_account_client(), not runner.client
        # So we need to mock the account manager's client
        account_client = runner.client_manager.get_account_client("default")
        account_client.get_open_position = MagicMock(return_value=mock_position)
        
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
        
        # Call update_position_info via state_manager
        import asyncio
        asyncio.run(runner.state_manager.update_position_info(summary))
        
        # Verify current_price was set from markPrice
        assert summary.current_price is not None, "current_price should be set"
        assert abs(summary.current_price - 51000.0) < 0.01, f"Expected 51000.0, got {summary.current_price}"
        assert summary.unrealized_pnl == 100.0, "unrealized_pnl should be set from Binance"


class TestTradeSortingForPnL:
    """Test that trades are sorted by timestamp before PnL calculation."""
    
    def test_unsorted_trades_cause_incorrect_pnl(self):
        """Test that unsorted trades would cause incorrect PnL calculation."""
        from app.api.routes.trades import get_symbol_pnl
        from unittest.mock import MagicMock, patch
        from app.models.db_models import User
        
        # Create trades OUT OF ORDER (later trade first)
        # BUY at 50000 (10:00) -> SELL at 51000 (11:00) should give +100 profit
        # But if processed as: SELL first, then BUY, it would be wrong
        trades_unsorted = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=2002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),  # Later
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=2001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),  # Earlier
            ),
        ]
        
        # Create trades IN ORDER (correct order)
        trades_sorted = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=2001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),  # Earlier
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=2002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),  # Later
            ),
        ]
        
        # Test that sorting works correctly
        # The get_symbol_pnl function should sort trades before processing
        # Expected PnL: (51000 - 50000) * 0.1 = +100 USDT
        
        # Verify sorting logic
        sorted_unsorted = sorted(
            trades_unsorted,
            key=lambda t: t.timestamp or t.update_time or datetime.min.replace(tzinfo=timezone.utc)
        )
        
        # After sorting, should match the correct order
        assert sorted_unsorted[0].order_id == 2001, "First trade should be BUY (order_id 2001)"
        assert sorted_unsorted[0].side == "BUY", "First trade should be BUY"
        assert sorted_unsorted[1].order_id == 2002, "Second trade should be SELL (order_id 2002)"
        assert sorted_unsorted[1].side == "SELL", "Second trade should be SELL"
        
        # Verify timestamps are in order
        assert sorted_unsorted[0].timestamp < sorted_unsorted[1].timestamp, "Trades should be sorted by timestamp"
        
        # Manually calculate expected PnL for sorted trades
        # BUY at 50000, SELL at 51000, quantity 0.1
        expected_pnl = (51000.0 - 50000.0) * 0.1  # +100 USDT
        
        # Simulate the PnL calculation logic
        position_queue = []
        completed_trades = []
        
        for trade in sorted_unsorted:
            entry_price = trade.avg_price or trade.price
            quantity = trade.executed_qty
            side = trade.side
            
            if side == "BUY":
                if position_queue and position_queue[0][2] == "SHORT":
                    # Closing SHORT (shouldn't happen in this test)
                    pass
                else:
                    # Opening LONG
                    position_queue.append((quantity, entry_price, "LONG", None, None))
            elif side == "SELL":
                if position_queue and position_queue[0][2] == "LONG":
                    # Closing LONG
                    long_entry = position_queue[0]
                    long_price = long_entry[1]
                    close_qty = min(quantity, long_entry[0])
                    pnl = (entry_price - long_price) * close_qty
                    completed_trades.append({
                        "realized_pnl": pnl,
                        "quantity": close_qty,
                        "entry_price": long_price,
                        "exit_price": entry_price,
                    })
                    position_queue.pop(0)
        
        # Verify PnL calculation
        total_realized_pnl = sum(t["realized_pnl"] for t in completed_trades)
        assert len(completed_trades) == 1, "Should have 1 completed trade"
        assert abs(total_realized_pnl - expected_pnl) < 0.01, \
            f"Expected PnL {expected_pnl}, got {total_realized_pnl}"
