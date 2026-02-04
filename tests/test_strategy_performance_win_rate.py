"""Test win rate calculation in strategy performance endpoint."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4

from app.models.strategy import StrategySummary, StrategyState
from app.models.report import TradeReport
from app.models.db_models import User


class TestStrategyPerformanceWinRate:
    """Test win rate calculation in /api/strategies/performance endpoint."""
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = MagicMock(spec=User)
        user.id = uuid4()
        return user
    
    @pytest.fixture
    def mock_strategy_summary(self):
        """Create a mock strategy summary."""
        return StrategySummary(
            id="test-strategy-123",
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            status=StrategyState.stopped,
            account_id="default",
            leverage=5,
            risk_per_trade=1.0,
            fixed_amount=1000.0,
            position_size=0.0,
            position_side=None,
            entry_price=None,
            current_price=50000.0,
            unrealized_pnl=0.0,
            params={},
            created_at=datetime.now(timezone.utc),
            last_signal=None,
        )
    
    @pytest.fixture
    def base_time(self):
        """Base time for trade timestamps."""
        return datetime.now(timezone.utc)
    
    def create_trade_report(self, trade_id: str, pnl_usd: float, base_time: datetime, offset_hours: int = 0):
        """Helper to create a TradeReport."""
        return TradeReport(
            trade_id=trade_id,
            strategy_id="test-strategy-123",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=base_time - timedelta(hours=offset_hours + 2),
            entry_price=50000.0,
            exit_time=base_time - timedelta(hours=offset_hours),
            exit_price=50010.0 if pnl_usd > 0 else 50003.0,
            quantity=1.0,
            leverage=5,
            fee_paid=2.0,
            funding_fee=0.0,
            pnl_usd=pnl_usd,
            pnl_pct=0.02 if pnl_usd > 0 else -0.01,
            exit_reason="TP" if pnl_usd > 0 else "SL",
            initial_margin=None,
            margin_type="CROSSED",
            notional_value=50000.0,
            entry_order_id=1000 + int(trade_id),
            exit_order_id=2000 + int(trade_id),
        )
    
    @pytest.mark.asyncio
    async def test_win_rate_single_winning_trade(self, mock_user, mock_strategy_summary, base_time):
        """Test win rate with 1 winning trade (should be 100%)."""
        from app.api.routes.strategy_performance import get_strategy_performance
        from app.services.strategy_runner import StrategyRunner
        from app.services.database_service import DatabaseService
        
        # Create trade with positive PnL
        completed_trades = [
            self.create_trade_report("1", pnl_usd=2.22, base_time=base_time)
        ]
        
        # Mock database service
        mock_db_service = MagicMock(spec=DatabaseService)
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        
        # Mock strategy runner
        mock_runner = MagicMock(spec=StrategyRunner)
        mock_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_runner.get_trades.return_value = []
        mock_runner.strategy_service = MagicMock()
        mock_runner.strategy_service.db_service = mock_db_service
        mock_runner.user_id = mock_user.id
        
        # Mock the _get_completed_trades_from_database function (imported from reports)
        with patch('app.api.routes.reports._get_completed_trades_from_database') as mock_get_trades:
            mock_get_trades.return_value = completed_trades
            
            # Call the endpoint
            result = get_strategy_performance(
                strategy_name=None,
                symbol=None,
                status=None,
                rank_by="total_pnl",
                start_date=None,
                end_date=None,
                account_id=None,
                current_user=mock_user,
                runner=mock_runner,
                db_service=mock_db_service,
            )
        
        # Verify results
        assert result is not None
        assert len(result.strategies) == 1
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.strategy_id == "test-strategy-123"
        assert strategy_perf.completed_trades == 1
        assert strategy_perf.winning_trades == 1
        assert strategy_perf.losing_trades == 0
        assert strategy_perf.win_rate == 100.0, f"Expected 100% win rate, got {strategy_perf.win_rate}%"
        assert abs(strategy_perf.total_realized_pnl - 2.22) < 0.01
    
    @pytest.mark.asyncio
    async def test_win_rate_single_losing_trade(self, mock_user, mock_strategy_summary, base_time):
        """Test win rate with 1 losing trade (should be 0%)."""
        from app.api.routes.strategy_performance import get_strategy_performance
        from app.services.strategy_runner import StrategyRunner
        from app.services.database_service import DatabaseService
        
        # Create trade with negative PnL
        completed_trades = [
            self.create_trade_report("1", pnl_usd=-1.50, base_time=base_time)
        ]
        
        # Mock database service
        mock_db_service = MagicMock(spec=DatabaseService)
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        
        # Mock strategy runner
        mock_runner = MagicMock(spec=StrategyRunner)
        mock_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_runner.get_trades.return_value = []
        mock_runner.strategy_service = MagicMock()
        mock_runner.strategy_service.db_service = mock_db_service
        mock_runner.user_id = mock_user.id
        
        # Mock the _get_completed_trades_from_database function (imported from reports)
        with patch('app.api.routes.reports._get_completed_trades_from_database') as mock_get_trades:
            mock_get_trades.return_value = completed_trades
            
            # Call the endpoint
            result = get_strategy_performance(
                strategy_name=None,
                symbol=None,
                status=None,
                rank_by="total_pnl",
                start_date=None,
                end_date=None,
                account_id=None,
                current_user=mock_user,
                runner=mock_runner,
                db_service=mock_db_service,
            )
        
        # Verify results
        assert result is not None
        assert len(result.strategies) == 1
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.completed_trades == 1
        assert strategy_perf.winning_trades == 0
        assert strategy_perf.losing_trades == 1
        assert strategy_perf.win_rate == 0.0, f"Expected 0% win rate, got {strategy_perf.win_rate}%"
        assert abs(strategy_perf.total_realized_pnl - (-1.50)) < 0.01
    
    @pytest.mark.asyncio
    async def test_win_rate_mixed_trades(self, mock_user, mock_strategy_summary, base_time):
        """Test win rate with mixed winning and losing trades."""
        from app.api.routes.strategy_performance import get_strategy_performance
        from app.services.strategy_runner import StrategyRunner
        from app.services.database_service import DatabaseService
        
        # Create trades: 2 wins, 1 loss
        completed_trades = [
            self.create_trade_report("1", pnl_usd=5.00, base_time=base_time, offset_hours=3),
            self.create_trade_report("2", pnl_usd=-2.00, base_time=base_time, offset_hours=2),
            self.create_trade_report("3", pnl_usd=3.00, base_time=base_time, offset_hours=1),
        ]
        
        # Mock database service
        mock_db_service = MagicMock(spec=DatabaseService)
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        
        # Mock strategy runner
        mock_runner = MagicMock(spec=StrategyRunner)
        mock_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_runner.get_trades.return_value = []
        mock_runner.strategy_service = MagicMock()
        mock_runner.strategy_service.db_service = mock_db_service
        mock_runner.user_id = mock_user.id
        
        # Mock the _get_completed_trades_from_database function (imported from reports)
        with patch('app.api.routes.reports._get_completed_trades_from_database') as mock_get_trades:
            mock_get_trades.return_value = completed_trades
            
            # Call the endpoint
            result = get_strategy_performance(
                strategy_name=None,
                symbol=None,
                status=None,
                rank_by="total_pnl",
                start_date=None,
                end_date=None,
                account_id=None,
                current_user=mock_user,
                runner=mock_runner,
                db_service=mock_db_service,
            )
        
        # Verify results
        assert result is not None
        assert len(result.strategies) == 1
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.completed_trades == 3
        assert strategy_perf.winning_trades == 2
        assert strategy_perf.losing_trades == 1
        # Win rate = 2/3 * 100 = 66.67%
        assert abs(strategy_perf.win_rate - 66.67) < 0.01, f"Expected ~66.67% win rate, got {strategy_perf.win_rate}%"
        # Total PnL = 5.00 - 2.00 + 3.00 = 6.00
        assert abs(strategy_perf.total_realized_pnl - 6.00) < 0.01
    
    @pytest.mark.asyncio
    async def test_win_rate_positive_pnl_but_zero_win_rate(self, mock_user, mock_strategy_summary, base_time):
        """Test edge case: positive total PnL but 0% win rate (should not happen with correct calculation)."""
        from app.api.routes.strategy_performance import get_strategy_performance
        from app.services.strategy_runner import StrategyRunner
        from app.services.database_service import DatabaseService
        
        # This scenario should not occur, but if it does, it means there's a bug
        # Create trades where fees make net PnL negative even though gross is positive
        # Trade 1: Gross $2.22, Fees $2.50, Net -$0.28 (loss)
        # Trade 2: Gross $1.00, Fees $0.50, Net $0.50 (win)
        # Total: $0.22 (positive), but if only Trade 1 is counted, win rate = 0%
        
        completed_trades = [
            self.create_trade_report("1", pnl_usd=-0.28, base_time=base_time, offset_hours=2),
            self.create_trade_report("2", pnl_usd=0.50, base_time=base_time, offset_hours=1),
        ]
        
        # Mock database service
        mock_db_service = MagicMock(spec=DatabaseService)
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        
        # Mock strategy runner
        mock_runner = MagicMock(spec=StrategyRunner)
        mock_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_runner.get_trades.return_value = []
        mock_runner.strategy_service = MagicMock()
        mock_runner.strategy_service.db_service = mock_db_service
        mock_runner.user_id = mock_user.id
        
        # Mock the _get_completed_trades_from_database function (imported from reports)
        with patch('app.api.routes.reports._get_completed_trades_from_database') as mock_get_trades:
            mock_get_trades.return_value = completed_trades
            
            # Call the endpoint
            result = get_strategy_performance(
                strategy_name=None,
                symbol=None,
                status=None,
                rank_by="total_pnl",
                start_date=None,
                end_date=None,
                account_id=None,
                current_user=mock_user,
                runner=mock_runner,
                db_service=mock_db_service,
            )
        
        # Verify results
        assert result is not None
        assert len(result.strategies) == 1
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.completed_trades == 2
        # Should have 1 win, 1 loss
        assert strategy_perf.winning_trades == 1
        assert strategy_perf.losing_trades == 1
        # Win rate = 1/2 * 100 = 50%
        assert abs(strategy_perf.win_rate - 50.0) < 0.01, f"Expected 50% win rate, got {strategy_perf.win_rate}%"
        # Total PnL = -0.28 + 0.50 = 0.22
        assert abs(strategy_perf.total_realized_pnl - 0.22) < 0.01
    
    @pytest.mark.asyncio
    async def test_win_rate_zero_pnl_trade(self, mock_user, mock_strategy_summary, base_time):
        """Test win rate with break-even trade (pnl_usd = 0)."""
        from app.api.routes.strategy_performance import get_strategy_performance
        from app.services.strategy_runner import StrategyRunner
        from app.services.database_service import DatabaseService
        
        # Create break-even trade
        completed_trades = [
            self.create_trade_report("1", pnl_usd=0.0, base_time=base_time)
        ]
        
        # Mock database service
        mock_db_service = MagicMock(spec=DatabaseService)
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        
        # Mock strategy runner
        mock_runner = MagicMock(spec=StrategyRunner)
        mock_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_runner.get_trades.return_value = []
        mock_runner.strategy_service = MagicMock()
        mock_runner.strategy_service.db_service = mock_db_service
        mock_runner.user_id = mock_user.id
        
        # Mock the _get_completed_trades_from_database function (imported from reports)
        with patch('app.api.routes.reports._get_completed_trades_from_database') as mock_get_trades:
            mock_get_trades.return_value = completed_trades
            
            # Call the endpoint
            result = get_strategy_performance(
                strategy_name=None,
                symbol=None,
                status=None,
                rank_by="total_pnl",
                start_date=None,
                end_date=None,
                account_id=None,
                current_user=mock_user,
                runner=mock_runner,
                db_service=mock_db_service,
            )
        
        # Verify results
        assert result is not None
        assert len(result.strategies) == 1
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.completed_trades == 1
        # Break-even trade should not count as win or loss
        assert strategy_perf.winning_trades == 0
        assert strategy_perf.losing_trades == 0
        assert strategy_perf.win_rate == 0.0, f"Expected 0% win rate for break-even, got {strategy_perf.win_rate}%"
    
    @pytest.mark.asyncio
    async def test_win_rate_type_conversion(self, mock_user, mock_strategy_summary, base_time):
        """Test win rate calculation handles different data types correctly."""
        from app.api.routes.strategy_performance import get_strategy_performance
        from app.services.strategy_runner import StrategyRunner
        from app.services.database_service import DatabaseService
        
        # Create trades with different pnl_usd types (simulating database Decimal types)
        trade1 = self.create_trade_report("1", pnl_usd=2.22, base_time=base_time, offset_hours=2)
        trade2 = self.create_trade_report("2", pnl_usd=-1.50, base_time=base_time, offset_hours=1)
        
        # Simulate Decimal type from database (common in SQLAlchemy)
        from decimal import Decimal
        trade1.pnl_usd = Decimal("2.22")
        trade2.pnl_usd = Decimal("-1.50")
        
        completed_trades = [trade1, trade2]
        
        # Mock database service
        mock_db_service = MagicMock(spec=DatabaseService)
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        
        # Mock strategy runner
        mock_runner = MagicMock(spec=StrategyRunner)
        mock_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_runner.get_trades.return_value = []
        mock_runner.strategy_service = MagicMock()
        mock_runner.strategy_service.db_service = mock_db_service
        mock_runner.user_id = mock_user.id
        
        # Mock the _get_completed_trades_from_database function (imported from reports)
        with patch('app.api.routes.reports._get_completed_trades_from_database') as mock_get_trades:
            mock_get_trades.return_value = completed_trades
            
            # Call the endpoint
            result = get_strategy_performance(
                strategy_name=None,
                symbol=None,
                status=None,
                rank_by="total_pnl",
                start_date=None,
                end_date=None,
                account_id=None,
                current_user=mock_user,
                runner=mock_runner,
                db_service=mock_db_service,
            )
        
        # Verify results
        assert result is not None
        assert len(result.strategies) == 1
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.completed_trades == 2
        assert strategy_perf.winning_trades == 1
        assert strategy_perf.losing_trades == 1
        assert abs(strategy_perf.win_rate - 50.0) < 0.01, f"Expected 50% win rate, got {strategy_perf.win_rate}%"
    
    @pytest.mark.asyncio
    async def test_win_rate_no_trades(self, mock_user, mock_strategy_summary):
        """Test win rate with no completed trades."""
        from app.api.routes.strategy_performance import get_strategy_performance
        from app.services.strategy_runner import StrategyRunner
        from app.services.database_service import DatabaseService
        from app.models.strategy import StrategyStats
        
        # No completed trades
        completed_trades = []
        
        # Mock database service
        mock_db_service = MagicMock(spec=DatabaseService)
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        
        # Mock strategy runner
        mock_runner = MagicMock(spec=StrategyRunner)
        mock_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_runner.get_trades.return_value = []
        mock_runner.strategy_service = MagicMock()
        mock_runner.strategy_service.db_service = mock_db_service
        mock_runner.user_id = mock_user.id
        
        # Mock calculate_strategy_stats for fallback path (when no completed trades)
        mock_stats = StrategyStats(
            strategy_id="test-strategy-123",
            strategy_name="Test Strategy",
            symbol="BTCUSDT",
            total_trades=0,
            completed_trades=0,
            total_pnl=0.0,
            win_rate=0.0,
            winning_trades=0,
            losing_trades=0,
            avg_profit_per_trade=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            created_at=datetime.now(timezone.utc),
            last_trade_at=None
        )
        mock_runner.calculate_strategy_stats.return_value = mock_stats
        
        # Mock the _get_completed_trades_from_database function (imported from reports)
        with patch('app.api.routes.reports._get_completed_trades_from_database') as mock_get_trades:
            mock_get_trades.return_value = completed_trades
            
            # Call the endpoint
            result = get_strategy_performance(
                strategy_name=None,
                symbol=None,
                status=None,
                rank_by="total_pnl",
                start_date=None,
                end_date=None,
                account_id=None,
                current_user=mock_user,
                runner=mock_runner,
                db_service=mock_db_service,
            )
        
        # Verify results
        assert result is not None
        assert len(result.strategies) == 1
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.completed_trades == 0
        assert strategy_perf.winning_trades == 0
        assert strategy_perf.losing_trades == 0
        assert strategy_perf.win_rate == 0.0, f"Expected 0% win rate with no trades, got {strategy_perf.win_rate}%"
    
    @pytest.mark.asyncio
    async def test_win_rate_all_winning_trades(self, mock_user, mock_strategy_summary, base_time):
        """Test win rate with all winning trades (should be 100%)."""
        from app.api.routes.strategy_performance import get_strategy_performance
        from app.services.strategy_runner import StrategyRunner
        from app.services.database_service import DatabaseService
        
        # Create 5 winning trades
        completed_trades = [
            self.create_trade_report(str(i), pnl_usd=5.0 + i, base_time=base_time, offset_hours=5-i)
            for i in range(1, 6)
        ]
        
        # Mock database service
        mock_db_service = MagicMock(spec=DatabaseService)
        mock_db_service.get_strategy.return_value = MagicMock(id=uuid4())
        
        # Mock strategy runner
        mock_runner = MagicMock(spec=StrategyRunner)
        mock_runner.list_strategies.return_value = [mock_strategy_summary]
        mock_runner.get_trades.return_value = []
        mock_runner.strategy_service = MagicMock()
        mock_runner.strategy_service.db_service = mock_db_service
        mock_runner.user_id = mock_user.id
        
        # Mock the _get_completed_trades_from_database function (imported from reports)
        with patch('app.api.routes.reports._get_completed_trades_from_database') as mock_get_trades:
            mock_get_trades.return_value = completed_trades
            
            # Call the endpoint
            result = get_strategy_performance(
                strategy_name=None,
                symbol=None,
                status=None,
                rank_by="total_pnl",
                start_date=None,
                end_date=None,
                account_id=None,
                current_user=mock_user,
                runner=mock_runner,
                db_service=mock_db_service,
            )
        
        # Verify results
        assert result is not None
        assert len(result.strategies) == 1
        
        strategy_perf = result.strategies[0]
        assert strategy_perf.completed_trades == 5
        assert strategy_perf.winning_trades == 5
        assert strategy_perf.losing_trades == 0
        assert strategy_perf.win_rate == 100.0, f"Expected 100% win rate, got {strategy_perf.win_rate}%"

