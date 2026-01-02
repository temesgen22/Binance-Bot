"""Test cases for strategies page position display functionality.

Tests cover:
1. LONG position display
2. SHORT position display
3. No position display
4. Position update logic
5. Position close logic
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.models.strategy_performance import StrategyPerformance
from app.api.routes.strategy_performance import get_strategy_performance
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_persistence import StrategyPersistence
from app.services.strategy_account_manager import StrategyAccountManager


class DummyRedis:
    enabled = False


def make_runner():
    """Create a mock StrategyRunner for testing."""
    client = MagicMock()
    client_manager = MagicMock()
    risk = MagicMock()
    executor = MagicMock()
    account_manager = MagicMock()
    
    runner = StrategyRunner(
        client=client,
        client_manager=client_manager,
        risk=risk,
        executor=executor,
        max_concurrent=2,
        redis_storage=DummyRedis(),
    )
    
    # Mock account manager
    runner.state_manager = MagicMock()
    runner.state_manager.account_manager = account_manager
    
    return runner


def make_strategy_summary(
    strategy_id: str = "test-strategy-1",
    name: str = "Test Strategy",
    symbol: str = "BTCUSDT",
    position_size: float = None,
    position_side: str = None,
    entry_price: float = None,
    current_price: float = None,
    unrealized_pnl: float = None,
    status: StrategyState = StrategyState.running,
) -> StrategySummary:
    """Create a StrategySummary with position data."""
    return StrategySummary(
        id=strategy_id,
        name=name,
        symbol=symbol,
        strategy_type=StrategyType.scalping,
        status=status,
        leverage=5,
        risk_per_trade=0.01,
        fixed_amount=1000.0,
        max_positions=1,
        params=StrategyParams(),
        created_at=datetime.now(timezone.utc),
        last_signal=None,
        position_size=position_size,
        position_side=position_side,
        entry_price=entry_price,
        current_price=current_price,
        unrealized_pnl=unrealized_pnl,
    )


class TestLONGPositionDisplay:
    """Test LONG position display on strategies page."""
    
    def test_long_position_displayed_correctly(self):
        """Test that LONG position is displayed with correct data."""
        runner = make_runner()
        
        # Create strategy with LONG position
        summary = make_strategy_summary(
            position_size=0.001,
            position_side="LONG",
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=10.0,
        )
        runner._strategies[summary.id] = summary
        
        # Mock calculate_strategy_stats
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=50.0,
            total_trades=10,
            completed_trades=8,
            win_rate=75.0,
            winning_trades=6,
            losing_trades=2,
            avg_profit_per_trade=6.25,
            largest_win=20.0,
            largest_loss=-5.0,
            last_trade_at=datetime.now(timezone.utc),
        ))
        
        # Mock client_manager
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        # Get performance data
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        # Verify position data is included
        assert len(result.strategies) == 1
        strategy_perf = result.strategies[0]
        
        assert strategy_perf.position_side == "LONG"
        assert strategy_perf.position_size == 0.001
        assert strategy_perf.entry_price == 50000.0
        assert strategy_perf.current_price == 51000.0
        assert strategy_perf.total_unrealized_pnl == 10.0
    
    def test_long_position_with_profit(self):
        """Test LONG position with profit displays correctly."""
        runner = make_runner()
        
        summary = make_strategy_summary(
            position_size=0.1,
            position_side="LONG",
            entry_price=50000.0,
            current_price=52000.0,  # Profit
            unrealized_pnl=200.0,
        )
        runner._strategies[summary.id] = summary
        
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=0.0,
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
            avg_profit_per_trade=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            last_trade_at=None,
        ))
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.position_side == "LONG"
        assert strategy_perf.total_unrealized_pnl == 200.0
        assert strategy_perf.total_pnl == 200.0  # Only unrealized PnL
    
    def test_long_position_with_loss(self):
        """Test LONG position with loss displays correctly."""
        runner = make_runner()
        
        summary = make_strategy_summary(
            position_size=0.1,
            position_side="LONG",
            entry_price=50000.0,
            current_price=48000.0,  # Loss
            unrealized_pnl=-200.0,
        )
        runner._strategies[summary.id] = summary
        
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=0.0,
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
            avg_profit_per_trade=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            last_trade_at=None,
        ))
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.position_side == "LONG"
        assert strategy_perf.total_unrealized_pnl == -200.0
        assert strategy_perf.total_pnl == -200.0


class TestSHORTPositionDisplay:
    """Test SHORT position display on strategies page."""
    
    def test_short_position_displayed_correctly(self):
        """Test that SHORT position is displayed with correct data."""
        runner = make_runner()
        
        # Create strategy with SHORT position
        summary = make_strategy_summary(
            position_size=0.001,
            position_side="SHORT",
            entry_price=50000.0,
            current_price=49000.0,
            unrealized_pnl=10.0,
        )
        runner._strategies[summary.id] = summary
        
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=50.0,
            total_trades=10,
            completed_trades=8,
            win_rate=75.0,
            winning_trades=6,
            losing_trades=2,
            avg_profit_per_trade=6.25,
            largest_win=20.0,
            largest_loss=-5.0,
            last_trade_at=datetime.now(timezone.utc),
        ))
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        # Verify SHORT position data is included
        assert len(result.strategies) == 1
        strategy_perf = result.strategies[0]
        
        assert strategy_perf.position_side == "SHORT"
        assert strategy_perf.position_size == 0.001
        assert strategy_perf.entry_price == 50000.0
        assert strategy_perf.current_price == 49000.0
        assert strategy_perf.total_unrealized_pnl == 10.0
    
    def test_short_position_with_profit(self):
        """Test SHORT position with profit (price went down) displays correctly."""
        runner = make_runner()
        
        summary = make_strategy_summary(
            position_size=0.1,
            position_side="SHORT",
            entry_price=50000.0,
            current_price=48000.0,  # Profit for SHORT
            unrealized_pnl=200.0,
        )
        runner._strategies[summary.id] = summary
        
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=0.0,
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
            avg_profit_per_trade=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            last_trade_at=None,
        ))
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.position_side == "SHORT"
        assert strategy_perf.total_unrealized_pnl == 200.0
    
    def test_short_position_with_loss(self):
        """Test SHORT position with loss (price went up) displays correctly."""
        runner = make_runner()
        
        summary = make_strategy_summary(
            position_size=0.1,
            position_side="SHORT",
            entry_price=50000.0,
            current_price=52000.0,  # Loss for SHORT
            unrealized_pnl=-200.0,
        )
        runner._strategies[summary.id] = summary
        
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=0.0,
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
            avg_profit_per_trade=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            last_trade_at=None,
        ))
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.position_side == "SHORT"
        assert strategy_perf.total_unrealized_pnl == -200.0


class TestNoPositionDisplay:
    """Test display when no position exists."""
    
    def test_no_position_displayed_correctly(self):
        """Test that 'No open position' is displayed when position_size is 0 or None."""
        runner = make_runner()
        
        # Strategy with no position (position_size = 0)
        summary = make_strategy_summary(
            position_size=0,
            position_side=None,
            entry_price=None,
            current_price=50000.0,
            unrealized_pnl=0.0,
        )
        runner._strategies[summary.id] = summary
        
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=100.0,
            total_trades=5,
            completed_trades=5,
            win_rate=80.0,
            winning_trades=4,
            losing_trades=1,
            avg_profit_per_trade=20.0,
            largest_win=50.0,
            largest_loss=-10.0,
            last_trade_at=datetime.now(timezone.utc),
        ))
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.position_side is None
        assert strategy_perf.position_size == 0
        assert strategy_perf.entry_price is None
        assert strategy_perf.total_unrealized_pnl == 0.0
    
    def test_no_position_when_position_size_none(self):
        """Test that no position is displayed when position_size is None."""
        runner = make_runner()
        
        summary = make_strategy_summary(
            position_size=None,
            position_side=None,
            entry_price=None,
            current_price=50000.0,
            unrealized_pnl=None,
        )
        runner._strategies[summary.id] = summary
        
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=0.0,
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
            avg_profit_per_trade=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            last_trade_at=None,
        ))
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.position_side is None
        assert strategy_perf.position_size is None
        assert strategy_perf.entry_price is None


class TestPositionUpdate:
    """Test position update logic."""
    
    @pytest.mark.asyncio
    async def test_position_update_from_binance_long(self):
        """Test that position info is updated correctly from Binance for LONG position."""
        from app.services.strategy_persistence import StrategyPersistence
        from app.services.strategy_account_manager import StrategyAccountManager
        
        # Create mocks
        account_manager = MagicMock(spec=StrategyAccountManager)
        account_client = MagicMock()
        account_manager.get_account_client = MagicMock(return_value=account_client)
        
        # Mock Binance position response (LONG)
        mock_position = {
            "positionAmt": "0.001",  # Positive = LONG
            "entryPrice": "50000.0",
            "markPrice": "51000.0",
            "unRealizedProfit": "10.0",
        }
        account_client.get_open_position = MagicMock(return_value=mock_position)
        
        # Create persistence manager
        persistence = StrategyPersistence(
            account_manager=account_manager,
            strategy_service=None,
            redis_storage=None,
        )
        
        # Create strategy summary
        summary = make_strategy_summary(
            position_size=None,
            position_side=None,
        )
        
        # Update position info
        await persistence.update_position_info(summary)
        
        # Verify position was updated
        assert summary.position_size == 0.001
        assert summary.position_side == "LONG"
        assert summary.entry_price == 50000.0
        assert summary.current_price == 51000.0
        assert summary.unrealized_pnl == 10.0
    
    @pytest.mark.asyncio
    async def test_position_update_from_binance_short(self):
        """Test that position info is updated correctly from Binance for SHORT position."""
        from app.services.strategy_persistence import StrategyPersistence
        from app.services.strategy_account_manager import StrategyAccountManager
        
        # Create mocks
        account_manager = MagicMock(spec=StrategyAccountManager)
        account_client = MagicMock()
        account_manager.get_account_client = MagicMock(return_value=account_client)
        
        # Mock Binance position response (SHORT)
        mock_position = {
            "positionAmt": "-0.001",  # Negative = SHORT
            "entryPrice": "50000.0",
            "markPrice": "49000.0",
            "unRealizedProfit": "10.0",
        }
        account_client.get_open_position = MagicMock(return_value=mock_position)
        
        # Create persistence manager
        persistence = StrategyPersistence(
            account_manager=account_manager,
            strategy_service=None,
            redis_storage=None,
        )
        
        # Create strategy summary
        summary = make_strategy_summary(
            position_size=None,
            position_side=None,
        )
        
        # Update position info
        await persistence.update_position_info(summary)
        
        # Verify position was updated (position_size is always positive)
        assert summary.position_size == 0.001  # Absolute value
        assert summary.position_side == "SHORT"
        assert summary.entry_price == 50000.0
        assert summary.current_price == 49000.0
        assert summary.unrealized_pnl == 10.0
    
    @pytest.mark.asyncio
    async def test_position_update_when_no_position(self):
        """Test that position is cleared when no position exists in Binance."""
        from app.services.strategy_persistence import StrategyPersistence
        from app.services.strategy_account_manager import StrategyAccountManager
        
        # Create mocks
        account_manager = MagicMock(spec=StrategyAccountManager)
        account_client = MagicMock()
        account_manager.get_account_client = MagicMock(return_value=account_client)
        
        # Mock Binance: no position
        account_client.get_open_position = MagicMock(return_value=None)
        
        # Create persistence manager
        persistence = StrategyPersistence(
            account_manager=account_manager,
            strategy_service=None,
            redis_storage=None,
        )
        
        # Create strategy summary with existing position
        summary = make_strategy_summary(
            position_size=0.001,
            position_side="LONG",
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=10.0,
        )
        
        # Update position info
        await persistence.update_position_info(summary)
        
        # Verify position was cleared
        assert summary.position_size == 0
        assert summary.position_side is None
        assert summary.entry_price is None
        assert summary.unrealized_pnl == 0


class TestPositionClose:
    """Test position close logic."""
    
    @pytest.mark.asyncio
    async def test_position_close_clears_state(self):
        """Test that position state is cleared when position is closed."""
        from app.services.strategy_persistence import StrategyPersistence
        from app.services.strategy_account_manager import StrategyAccountManager
        
        # Create mocks
        account_manager = MagicMock(spec=StrategyAccountManager)
        account_client = MagicMock()
        account_manager.get_account_client = MagicMock(return_value=account_client)
        
        # Mock Binance: position was closed (no position)
        account_client.get_open_position = MagicMock(return_value=None)
        
        # Create persistence manager
        persistence = StrategyPersistence(
            account_manager=account_manager,
            strategy_service=None,
            redis_storage=None,
        )
        
        # Create strategy summary with open position
        summary = make_strategy_summary(
            position_size=0.001,
            position_side="LONG",
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=10.0,
        )
        
        # Update position info (simulates position close)
        await persistence.update_position_info(summary)
        
        # Verify position state was cleared
        assert summary.position_size == 0
        assert summary.position_side is None
        assert summary.entry_price is None
        assert summary.unrealized_pnl == 0


class TestPositionDisplayEdgeCases:
    """Test edge cases for position display."""
    
    def test_position_side_set_but_position_size_zero(self):
        """Test edge case: position_side is set but position_size is 0."""
        runner = make_runner()
        
        # Edge case: position_side set but position_size is 0 (shouldn't happen, but test it)
        summary = make_strategy_summary(
            position_size=0,
            position_side="LONG",  # Should be None if position_size is 0
            entry_price=None,
            current_price=50000.0,
            unrealized_pnl=0.0,
        )
        runner._strategies[summary.id] = summary
        
        runner.calculate_strategy_stats = MagicMock(return_value=MagicMock(
            total_pnl=0.0,
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
            avg_profit_per_trade=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            last_trade_at=None,
        ))
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        strategy_perf = result.strategies[0]
        # Even if position_side is set, if position_size is 0, it should be treated as no position
        # Frontend should check both position_side AND position_size !== 0
        assert strategy_perf.position_size == 0
    
    def test_multiple_strategies_with_different_positions(self):
        """Test multiple strategies with different position states."""
        runner = make_runner()
        
        # Strategy 1: LONG position
        summary1 = make_strategy_summary(
            strategy_id="strategy-1",
            name="Strategy 1",
            position_size=0.001,
            position_side="LONG",
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=10.0,
        )
        runner._strategies[summary1.id] = summary1
        
        # Strategy 2: SHORT position
        summary2 = make_strategy_summary(
            strategy_id="strategy-2",
            name="Strategy 2",
            position_size=0.002,
            position_side="SHORT",
            entry_price=50000.0,
            current_price=49000.0,
            unrealized_pnl=20.0,
        )
        runner._strategies[summary2.id] = summary2
        
        # Strategy 3: No position
        summary3 = make_strategy_summary(
            strategy_id="strategy-3",
            name="Strategy 3",
            position_size=0,
            position_side=None,
            entry_price=None,
            current_price=50000.0,
            unrealized_pnl=0.0,
        )
        runner._strategies[summary3.id] = summary3
        
        # Mock stats for all strategies
        mock_stats = MagicMock(
            total_pnl=0.0,
            total_trades=0,
            completed_trades=0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
            avg_profit_per_trade=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            last_trade_at=None,
        )
        runner.calculate_strategy_stats = MagicMock(return_value=mock_stats)
        runner.client_manager.get_account_config = MagicMock(return_value=None)
        
        result = get_strategy_performance(
            strategy_name=None,
            symbol=None,
            status=None,
            rank_by="total_pnl",
            start_date=None,
            end_date=None,
            account_id=None,
            runner=runner,
        )
        
        # Verify all strategies are returned with correct position data
        assert len(result.strategies) == 3
        
        # Find each strategy
        perf1 = next(s for s in result.strategies if s.strategy_id == "strategy-1")
        perf2 = next(s for s in result.strategies if s.strategy_id == "strategy-2")
        perf3 = next(s for s in result.strategies if s.strategy_id == "strategy-3")
        
        # Verify Strategy 1 (LONG)
        assert perf1.position_side == "LONG"
        assert perf1.position_size == 0.001
        assert perf1.total_unrealized_pnl == 10.0
        
        # Verify Strategy 2 (SHORT)
        assert perf2.position_side == "SHORT"
        assert perf2.position_size == 0.002
        assert perf2.total_unrealized_pnl == 20.0
        
        # Verify Strategy 3 (No position)
        assert perf3.position_side is None
        assert perf3.position_size == 0
        assert perf3.total_unrealized_pnl == 0.0




