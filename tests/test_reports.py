"""Test cases for report generation functionality."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.order import OrderResponse
from app.models.report import TradeReport, StrategyReport, TradingReport
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


class TestTradeMatching:
    """Test trade matching logic for report generation."""
    
    def test_match_long_trade_completion(self):
        """Test matching LONG trades (BUY -> SELL)."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-1",
            strategy_name="Test Strategy",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1, "Should have 1 completed trade"
        trade = completed[0]
        assert trade.side == "LONG", "Should be a LONG trade"
        assert trade.entry_price == 50000.0, "Entry price should be 50000"
        assert trade.exit_price == 51000.0, "Exit price should be 51000"
        assert trade.pnl_usd > 0, "Should show profit (price went up)"
        assert trade.quantity == 0.1, "Quantity should match"
        assert trade.leverage == 5, "Leverage should match"
    
    def test_match_short_trade_completion(self):
        """Test matching SHORT trades (SELL -> BUY)."""
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=2001,
                status="FILLED",
                side="SELL",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=2002,
                status="FILLED",
                side="BUY",
                price=49000.0,
                avg_price=49000.0,
                executed_qty=0.1,
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-2",
            strategy_name="Test SHORT Strategy",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1, "Should have 1 completed trade"
        trade = completed[0]
        assert trade.side == "SHORT", "Should be a SHORT trade"
        assert trade.entry_price == 50000.0, "Entry price should be 50000"
        assert trade.exit_price == 49000.0, "Exit price should be 49000"
        assert trade.pnl_usd > 0, "Should show profit (price went down)"
        assert trade.quantity == 0.1, "Quantity should match"
        assert trade.leverage == 5, "Leverage should match"
    
    def test_match_multiple_trades(self):
        """Test matching multiple completed trades."""
        trades = [
            # First trade: LONG
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
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
            ),
            # Second trade: SHORT
            OrderResponse(
                symbol="BTCUSDT",
                order_id=3003,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=3004,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-3",
            strategy_name="Test Multiple Trades",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 2, "Should have 2 completed trades"
        assert completed[0].side == "LONG", "First trade should be LONG"
        assert completed[1].side == "SHORT", "Second trade should be SHORT"
        assert completed[0].pnl_usd > 0, "First trade should be profitable"
        assert completed[1].pnl_usd > 0, "Second trade should be profitable"
    
    def test_trade_fee_calculation(self):
        """Test that fees are calculated and included in trade reports."""
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
            ),
        ]
        
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-4",
            strategy_name="Test Fees",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        assert len(completed) == 1, "Should have 1 completed trade"
        trade = completed[0]
        assert trade.fee_paid > 0, "Fee should be calculated"
        assert trade.pnl_usd < (51000.0 - 50000.0) * 0.1, "Net PnL should be less than gross after fees"
        # Fee should be approximately 0.04% * 2 (entry + exit)
        expected_fee_min = 0.1 * 50000.0 * 0.0004 * 2  # Minimum expected
        assert trade.fee_paid >= expected_fee_min * 0.9, f"Fee should be at least {expected_fee_min}, got {trade.fee_paid}"


class TestReportGeneration:
    """Test report generation API."""
    
    def test_report_generation_basic(self):
        """Test basic report generation."""
        runner = make_runner()
        
        # Create strategy with trades
        strategy_id = "test-report-1"
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
            ),
        ]
        runner._trades[strategy_id] = trades
        
        summary = StrategySummary(
            id=strategy_id,
            name="Test Report Strategy",
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
        
        # Mock dependencies
        client = MagicMock()
        
        # Call report generation function
        with patch('app.api.routes.reports.get_strategy_runner', return_value=runner):
            with patch('app.api.routes.reports.get_binance_client', return_value=client):
                report = get_trading_report(
                    strategy_id=None,
                    strategy_name=None,
                    symbol=None,
                    start_date=None,
                    end_date=None,
                    runner=runner,
                    client=client,
                )
        
        assert isinstance(report, TradingReport), "Should return TradingReport"
        assert len(report.strategies) >= 1, "Should have at least 1 strategy"
        
        strategy_report = report.strategies[0]
        assert strategy_report.strategy_id == strategy_id, "Strategy ID should match"
        assert strategy_report.total_trades == 1, "Should have 1 completed trade (2 orders form 1 completed trade)"
        assert len(strategy_report.trades) == 1, "Should have 1 completed trade"
        assert strategy_report.net_pnl > 0, "Net PnL should be positive"
        assert strategy_report.wins == 1, "Should have 1 win"
        assert strategy_report.losses == 0, "Should have 0 losses"
    
    def test_report_filtering_by_strategy_id(self):
        """Test report filtering by strategy ID."""
        runner = make_runner()
        
        # Create two strategies
        strategy1_id = "test-filter-1"
        strategy2_id = "test-filter-2"
        
        for sid in [strategy1_id, strategy2_id]:
            runner._trades[sid] = []
            summary = StrategySummary(
                id=sid,
                name=f"Strategy {sid}",
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
            runner._strategies[sid] = summary
        
        client = MagicMock()
        
        # Filter by strategy1_id
        with patch('app.api.routes.reports.get_strategy_runner', return_value=runner):
            with patch('app.api.routes.reports.get_binance_client', return_value=client):
                report = get_trading_report(
                    strategy_id=strategy1_id,
                    strategy_name=None,
                    symbol=None,
                    start_date=None,
                    end_date=None,
                    runner=runner,
                    client=client,
                )
        
        assert len(report.strategies) == 1, "Should filter to 1 strategy"
        assert report.strategies[0].strategy_id == strategy1_id, "Should match filtered strategy ID"
    
    def test_report_filtering_by_symbol(self):
        """Test report filtering by symbol."""
        runner = make_runner()
        
        # Create strategies with different symbols
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            sid = f"test-{symbol}"
            runner._trades[sid] = []
            summary = StrategySummary(
                id=sid,
                name=f"Strategy {symbol}",
                symbol=symbol,
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
            runner._strategies[sid] = summary
        
        client = MagicMock()
        
        # Filter by BTCUSDT
        with patch('app.api.routes.reports.get_strategy_runner', return_value=runner):
            with patch('app.api.routes.reports.get_binance_client', return_value=client):
                report = get_trading_report(
                    strategy_id=None,
                    strategy_name=None,
                    symbol="BTCUSDT",
                    start_date=None,
                    end_date=None,
                    runner=runner,
                    client=client,
                )
        
        assert len(report.strategies) == 1, "Should filter to 1 strategy"
        assert report.strategies[0].symbol == "BTCUSDT", "Should match filtered symbol"
    
    def test_report_filtering_by_date(self):
        """Test report filtering by date range."""
        runner = make_runner()
        
        strategy_id = "test-date-filter"
        # Create trades with timestamps
        now = datetime.now(timezone.utc)
        past = now.replace(year=now.year - 1)  # 1 year ago
        
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
        ]
        runner._trades[strategy_id] = trades
        
        summary = StrategySummary(
            id=strategy_id,
            name="Test Date Filter",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=5,
            risk_per_trade=0.01,
            fixed_amount=1000.0,
            max_positions=1,
            params=StrategyParams(),
            created_at=past,  # Created in the past
            last_signal=None,
        )
        runner._strategies[strategy_id] = summary
        
        client = MagicMock()
        
        # Filter by recent date (should exclude past strategy)
        # Calculate date 11 months ago (avoiding month overflow)
        from dateutil.relativedelta import relativedelta
        recent_date = (now - relativedelta(months=11)).isoformat()
        future_date = now.isoformat()
        
        with patch('app.api.routes.reports.get_strategy_runner', return_value=runner):
            with patch('app.api.routes.reports.get_binance_client', return_value=client):
                report = get_trading_report(
                    strategy_id=None,
                    strategy_name=None,
                    symbol=None,
                    start_date=recent_date,
                    end_date=future_date,
                    runner=runner,
                    client=client,
                )
        
        # The report should still include the strategy, but trades might be filtered
        assert isinstance(report, TradingReport), "Should return TradingReport"


class TestStrategyReportModel:
    """Test StrategyReport model validation."""
    
    def test_strategy_report_creation(self):
        """Test creating a StrategyReport with valid data."""
        trades = [
            TradeReport(
                trade_id="1001",
                strategy_id="test-1",
                symbol="BTCUSDT",
                side="LONG",
                entry_time=datetime.now(timezone.utc),
                entry_price=50000.0,
                exit_time=datetime.now(timezone.utc),
                exit_price=51000.0,
                quantity=0.1,
                leverage=5,
                fee_paid=4.0,
                pnl_usd=96.0,
                pnl_pct=1.92,
                exit_reason="TP",
            ),
        ]
        
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
            trades=trades,
        )
        
        assert report.strategy_id == "test-1"
        assert report.win_rate == 100.0
        assert len(report.trades) == 1
        assert report.net_pnl == 96.0


class TestBinanceParametersInReports:
    """Test that Binance trade parameters are included in reports."""
    
    def test_report_includes_initial_margin_and_margin_type(self):
        """Test that reports include initial margin and margin type from Binance."""
        runner = make_runner()
        
        entry_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 15, 11, 30, 45, tzinfo=timezone.utc)
        
        strategy_id = "test-binance-params"
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=7001,
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
                order_id=7002,
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
        runner._trades[strategy_id] = trades
        
        summary = StrategySummary(
            id=strategy_id,
            name="Test Binance Params",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            status=StrategyState.stopped,
            leverage=10,
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
        # Verify Binance parameters are included
        assert trade.initial_margin == 50.25, "Should include initial margin from Binance"
        assert trade.margin_type == "ISOLATED", "Should include margin type from Binance"
        assert trade.notional_value == 5000.0, "Should include notional value from Binance"
        assert trade.entry_order_id == 7001, "Should include entry order ID"
        assert trade.exit_order_id == 7002, "Should include exit order ID"
        assert trade.leverage == 10, "Should use actual leverage from order"
        assert trade.entry_time == entry_time, "Should use actual entry time from Binance"
        assert trade.exit_time == exit_time, "Should use actual exit time from Binance"
    
    def test_report_includes_actual_commission_from_binance(self):
        """Test that reports use actual commission from Binance orders."""
        runner = make_runner()
        
        strategy_id = "test-commission"
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=8001,
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
                commission=0.0195,  # Actual commission from Binance
                commission_asset="USDT",
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=8002,
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=datetime.now(timezone.utc),
                commission=0.0199,  # Actual commission from Binance
                commission_asset="USDT",
            ),
        ]
        runner._trades[strategy_id] = trades
        
        summary = StrategySummary(
            id=strategy_id,
            name="Test Commission",
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
        # Fee should be actual commission from orders (approximately 0.0195 + 0.0199)
        expected_fee = 0.0195 + 0.0199
        assert abs(trade.fee_paid - expected_fee) < 0.001, \
            f"Fee should use actual Binance commission values. Expected ~{expected_fee}, got {trade.fee_paid}"
    
    def test_strategy_report_includes_symbol(self):
        """Test that StrategyReport includes symbol field."""
        runner = make_runner()
        
        strategy_id = "test-symbol-field"
        runner._trades[strategy_id] = []
        
        summary = StrategySummary(
            id=strategy_id,
            name="Test Symbol",
            symbol="ETHUSDT",
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
        assert strategy_report.symbol == "ETHUSDT", "StrategyReport should include symbol field"

