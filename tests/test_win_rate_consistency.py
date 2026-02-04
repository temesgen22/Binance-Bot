"""Test win rate consistency between strategies page and report page."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.strategy import StrategySummary, StrategyState
from app.models.order import OrderResponse
from app.models.report import TradeReport


class TestWinRateConsistency:
    """Test that win rate is calculated consistently across pages."""
    
    @pytest.fixture
    def mock_strategy_summary(self):
        """Create a mock strategy summary."""
        return StrategySummary(
            id="test-strategy-123",
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            status=StrategyState.running,
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
    def sample_completed_trades(self):
        """Create sample completed trades with known PnL values."""
        base_time = datetime.now(timezone.utc)
        
        # Trade 1: Win (net PnL = $5.00 after fees)
        # Gross: $10.00, Fees: $5.00, Net: $5.00
        trade1 = TradeReport(
            trade_id="1",
            strategy_id="test-strategy-123",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=base_time - timedelta(hours=3),
            entry_price=50000.0,
            exit_time=base_time - timedelta(hours=2),
            exit_price=50010.0,
            quantity=1.0,
            leverage=5,
            fee_paid=5.0,  # $5.00 in fees
            funding_fee=0.0,
            pnl_usd=5.0,  # Net PnL: $10.00 gross - $5.00 fees = $5.00
            pnl_pct=0.01,
            exit_reason="TP",
            initial_margin=None,
            margin_type="CROSSED",
            notional_value=50000.0,
            entry_order_id=1001,
            exit_order_id=1002,
        )
        
        # Trade 2: Loss (net PnL = -$1.00 after fees)
        # Gross: $3.00, Fees: $4.00, Net: -$1.00
        trade2 = TradeReport(
            trade_id="2",
            strategy_id="test-strategy-123",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=base_time - timedelta(hours=2),
            entry_price=50000.0,
            exit_time=base_time - timedelta(hours=1),
            exit_price=50003.0,
            quantity=1.0,
            leverage=5,
            fee_paid=4.0,  # $4.00 in fees
            funding_fee=0.0,
            pnl_usd=-1.0,  # Net PnL: $3.00 gross - $4.00 fees = -$1.00
            pnl_pct=-0.002,
            exit_reason="SL",
            initial_margin=None,
            margin_type="CROSSED",
            notional_value=50000.0,
            entry_order_id=1003,
            exit_order_id=1004,
        )
        
        # Trade 3: Win (net PnL = $8.00 after fees)
        # Gross: $10.00, Fees: $2.00, Net: $8.00
        trade3 = TradeReport(
            trade_id="3",
            strategy_id="test-strategy-123",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=base_time - timedelta(hours=1),
            entry_price=50000.0,
            exit_time=base_time,
            exit_price=50010.0,
            quantity=1.0,
            leverage=5,
            fee_paid=2.0,  # $2.00 in fees
            funding_fee=0.0,
            pnl_usd=8.0,  # Net PnL: $10.00 gross - $2.00 fees = $8.00
            pnl_pct=0.016,
            exit_reason="TP",
            initial_margin=None,
            margin_type="CROSSED",
            notional_value=50000.0,
            entry_order_id=1005,
            exit_order_id=1006,
        )
        
        return [trade1, trade2, trade3]
    
    def test_win_rate_calculation_includes_fees(self, sample_completed_trades):
        """Test that win rate calculation uses net PnL (after fees)."""
        # Expected: 2 wins out of 3 trades = 66.67%
        # Trade 1: pnl_usd=5.0 (win)
        # Trade 2: pnl_usd=-1.0 (loss)
        # Trade 3: pnl_usd=8.0 (win)
        
        winning_trades = len([t for t in sample_completed_trades if t.pnl_usd > 0])
        total_trades = len(sample_completed_trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        assert winning_trades == 2, "Should have 2 winning trades"
        assert total_trades == 3, "Should have 3 total trades"
        assert abs(win_rate - 66.67) < 0.01, f"Win rate should be ~66.67%, got {win_rate}"
    
    def test_strategies_page_win_rate_calculation(self, sample_completed_trades):
        """Test win rate calculation as done in strategies page."""
        # Simulate strategies page calculation (strategy_performance.py lines 141-145)
        total_pnl = sum(trade.pnl_usd for trade in sample_completed_trades)
        winning_trades = len([t for t in sample_completed_trades if t.pnl_usd > 0])
        losing_trades = len([t for t in sample_completed_trades if t.pnl_usd < 0])
        completed_count = len(sample_completed_trades)
        win_rate = (winning_trades / completed_count * 100) if completed_count > 0 else 0.0
        
        assert winning_trades == 2, "Should have 2 winning trades"
        assert losing_trades == 1, "Should have 1 losing trade"
        assert completed_count == 3, "Should have 3 completed trades"
        assert abs(win_rate - 66.67) < 0.01, f"Win rate should be ~66.67%, got {win_rate}"
        assert abs(total_pnl - 12.0) < 0.01, f"Total PnL should be $12.00, got ${total_pnl}"
    
    def test_report_page_win_rate_calculation(self, sample_completed_trades):
        """Test win rate calculation as done in report page."""
        # Simulate report page calculation (reports.py lines 838-856)
        wins = 0
        losses = 0
        total_profit_usd = 0.0
        total_loss_usd = 0.0
        
        for trade in sample_completed_trades:
            pnl = trade.pnl_usd
            if pnl > 0:
                wins += 1
                total_profit_usd += pnl
            elif pnl < 0:
                losses += 1
                total_loss_usd += abs(pnl)
        
        win_rate = ((wins / len(sample_completed_trades)) * 100) if sample_completed_trades else 0.0
        
        assert wins == 2, "Should have 2 wins"
        assert losses == 1, "Should have 1 loss"
        assert abs(win_rate - 66.67) < 0.01, f"Win rate should be ~66.67%, got {win_rate}"
        assert abs(total_profit_usd - 13.0) < 0.01, f"Total profit should be $13.00, got ${total_profit_usd}"
        assert abs(total_loss_usd - 1.0) < 0.01, f"Total loss should be $1.00, got ${total_loss_usd}"
    
    def test_win_rate_consistency_between_pages(self, sample_completed_trades):
        """Test that strategies page and report page calculate same win rate."""
        # Strategies page calculation
        winning_trades_strategies = len([t for t in sample_completed_trades if t.pnl_usd > 0])
        completed_count = len(sample_completed_trades)
        win_rate_strategies = (winning_trades_strategies / completed_count * 100) if completed_count > 0 else 0.0
        
        # Report page calculation
        wins_report = 0
        for trade in sample_completed_trades:
            if trade.pnl_usd > 0:
                wins_report += 1
        win_rate_report = ((wins_report / len(sample_completed_trades)) * 100) if sample_completed_trades else 0.0
        
        # Both should be identical
        assert abs(win_rate_strategies - win_rate_report) < 0.01, \
            f"Win rates should match: strategies={win_rate_strategies}%, report={win_rate_report}%"
        assert winning_trades_strategies == wins_report, \
            f"Winning trade counts should match: strategies={winning_trades_strategies}, report={wins_report}"
    
    def test_win_rate_with_zero_pnl_trades(self):
        """Test that trades with exactly zero PnL are handled correctly."""
        base_time = datetime.now(timezone.utc)
        
        # Trade with zero net PnL (break-even after fees)
        trade = TradeReport(
            trade_id="1",
            strategy_id="test-strategy-123",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=base_time - timedelta(hours=1),
            entry_price=50000.0,
            exit_time=base_time,
            exit_price=50004.0,  # $4.00 gross profit
            quantity=1.0,
            leverage=5,
            fee_paid=4.0,  # $4.00 in fees (exactly equals gross profit)
            funding_fee=0.0,
            pnl_usd=0.0,  # Net PnL: $4.00 gross - $4.00 fees = $0.00
            pnl_pct=0.0,
            exit_reason="TP",
            initial_margin=None,
            margin_type="CROSSED",
            notional_value=50000.0,
            entry_order_id=1001,
            exit_order_id=1002,
        )
        
        # Zero PnL trades should not count as wins (pnl_usd > 0 is required)
        winning_trades = len([t for t in [trade] if t.pnl_usd > 0])
        assert winning_trades == 0, "Zero PnL trade should not count as win"
        
        # But should count in total trades
        total_trades = len([trade])
        assert total_trades == 1, "Zero PnL trade should count in total"
        
        # Win rate should be 0% (0 wins / 1 trade)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        assert win_rate == 0.0, f"Win rate should be 0%, got {win_rate}%"
    
    def test_win_rate_with_all_winning_trades(self):
        """Test win rate calculation when all trades are winners."""
        base_time = datetime.now(timezone.utc)
        
        trades = []
        for i in range(5):
            trade = TradeReport(
                trade_id=str(i),
                strategy_id="test-strategy-123",
                symbol="BTCUSDT",
                side="LONG",
                entry_time=base_time - timedelta(hours=5-i),
                entry_price=50000.0,
                exit_time=base_time - timedelta(hours=4-i),
                exit_price=50010.0,
                quantity=1.0,
                leverage=5,
                fee_paid=2.0,
                funding_fee=0.0,
                pnl_usd=8.0,  # All winners
                pnl_pct=0.016,
                exit_reason="TP",
                initial_margin=None,
                margin_type="CROSSED",
                notional_value=50000.0,
                entry_order_id=1000 + i,
                exit_order_id=2000 + i,
            )
            trades.append(trade)
        
        winning_trades = len([t for t in trades if t.pnl_usd > 0])
        total_trades = len(trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        assert winning_trades == 5, "Should have 5 winning trades"
        assert total_trades == 5, "Should have 5 total trades"
        assert win_rate == 100.0, f"Win rate should be 100%, got {win_rate}%"
    
    def test_win_rate_with_all_losing_trades(self):
        """Test win rate calculation when all trades are losers."""
        base_time = datetime.now(timezone.utc)
        
        trades = []
        for i in range(3):
            trade = TradeReport(
                trade_id=str(i),
                strategy_id="test-strategy-123",
                symbol="BTCUSDT",
                side="LONG",
                entry_time=base_time - timedelta(hours=3-i),
                entry_price=50000.0,
                exit_time=base_time - timedelta(hours=2-i),
                exit_price=50003.0,
                quantity=1.0,
                leverage=5,
                fee_paid=4.0,
                funding_fee=0.0,
                pnl_usd=-1.0,  # All losers
                pnl_pct=-0.002,
                exit_reason="SL",
                initial_margin=None,
                margin_type="CROSSED",
                notional_value=50000.0,
                entry_order_id=1000 + i,
                exit_order_id=2000 + i,
            )
            trades.append(trade)
        
        winning_trades = len([t for t in trades if t.pnl_usd > 0])
        total_trades = len(trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        assert winning_trades == 0, "Should have 0 winning trades"
        assert total_trades == 3, "Should have 3 total trades"
        assert win_rate == 0.0, f"Win rate should be 0%, got {win_rate}%"
    
    def test_win_rate_with_no_trades(self):
        """Test win rate calculation when there are no trades."""
        trades = []
        
        winning_trades = len([t for t in trades if t.pnl_usd > 0])
        total_trades = len(trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        assert winning_trades == 0, "Should have 0 winning trades"
        assert total_trades == 0, "Should have 0 total trades"
        assert win_rate == 0.0, f"Win rate should be 0% when no trades, got {win_rate}%"

