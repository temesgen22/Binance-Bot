"""Tests for risk management utility functions.

This test file verifies the shared utility functions in app/risk/utils.py that
eliminate repetitive code and ensure consistency across risk services.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.risk.utils import get_pnl_from_completed_trade, get_timestamp_from_completed_trade
from app.models.report import TradeReport
from app.services.trade_matcher import CompletedTradeMatch


class TestGetPnlFromCompletedTrade:
    """Test get_pnl_from_completed_trade function with different trade types."""
    
    def test_trade_report_with_pnl_usd(self):
        """Test with TradeReport object that has pnl_usd."""
        trade = TradeReport(
            trade_id="test-1",
            strategy_id="strategy-1",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=datetime.now(timezone.utc),
            entry_price=40000.0,
            exit_time=datetime.now(timezone.utc) + timedelta(hours=1),
            exit_price=41000.0,
            quantity=0.1,
            leverage=5,
            fee_paid=3.2,
            funding_fee=0.0,
            pnl_usd=996.8,  # TradeReport uses pnl_usd
            pnl_pct=2.49,
            exit_reason="TP"
        )
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == 996.8, f"Expected 996.8, got {pnl}"
    
    def test_trade_report_with_zero_pnl(self):
        """Test with TradeReport object with zero PnL."""
        trade = TradeReport(
            trade_id="test-2",
            strategy_id="strategy-1",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=datetime.now(timezone.utc),
            entry_price=40000.0,
            exit_time=datetime.now(timezone.utc) + timedelta(hours=1),
            exit_price=40000.0,
            quantity=0.1,
            leverage=5,
            fee_paid=3.2,
            funding_fee=0.0,
            pnl_usd=0.0,
            pnl_pct=0.0,
            exit_reason="MANUAL"
        )
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == 0.0, f"Expected 0.0, got {pnl}"
    
    def test_trade_report_with_negative_pnl(self):
        """Test with TradeReport object with negative PnL (loss)."""
        trade = TradeReport(
            trade_id="test-3",
            strategy_id="strategy-1",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=datetime.now(timezone.utc),
            entry_price=40000.0,
            exit_time=datetime.now(timezone.utc) + timedelta(hours=1),
            exit_price=39000.0,
            quantity=0.1,
            leverage=5,
            fee_paid=3.2,
            funding_fee=0.0,
            pnl_usd=-1003.2,  # Loss
            pnl_pct=-2.51,
            exit_reason="SL"
        )
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == -1003.2, f"Expected -1003.2, got {pnl}"
    
    def test_completed_trade_match_with_net_pnl(self):
        """Test with CompletedTradeMatch object that has net_pnl."""
        trade = CompletedTradeMatch(
            entry_price=40000.0,
            exit_price=41000.0,
            quantity=0.1,
            side="LONG",
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc) + timedelta(hours=1),
            entry_order_id=1001,
            exit_order_id=1002,
            gross_pnl=1000.0,
            fee_paid=3.2,
            net_pnl=996.8,  # CompletedTradeMatch uses net_pnl
            exit_reason="TP"
        )
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == 996.8, f"Expected 996.8, got {pnl}"
    
    def test_completed_trade_match_with_negative_net_pnl(self):
        """Test with CompletedTradeMatch object with negative net_pnl (loss)."""
        trade = CompletedTradeMatch(
            entry_price=40000.0,
            exit_price=39000.0,
            quantity=0.1,
            side="LONG",
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc) + timedelta(hours=1),
            entry_order_id=1001,
            exit_order_id=1002,
            gross_pnl=-1000.0,
            fee_paid=3.2,
            net_pnl=-1003.2,  # Loss
            exit_reason="SL"
        )
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == -1003.2, f"Expected -1003.2, got {pnl}"
    
    def test_raw_trade_with_realized_pnl(self):
        """Test with raw trade object that has realized_pnl (fallback)."""
        # Use a simple object instead of MagicMock to avoid hasattr() issues
        class RawTrade:
            def __init__(self):
                self.realized_pnl = 500.0
        
        trade = RawTrade()
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == 500.0, f"Expected 500.0, got {pnl}"
    
    def test_raw_trade_with_none_realized_pnl(self):
        """Test with raw trade object with None realized_pnl."""
        class RawTrade:
            def __init__(self):
                self.realized_pnl = None
        
        trade = RawTrade()
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == 0.0, f"Expected 0.0, got {pnl}"
    
    def test_trade_with_no_pnl_attributes(self):
        """Test with trade object that has no recognized PnL attributes."""
        # Create a mock without any PnL attributes
        trade = MagicMock(spec=[])  # Empty spec means no attributes by default
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == 0.0, f"Expected 0.0 (default), got {pnl}"
    
    def test_precedence_pnl_usd_over_net_pnl(self):
        """Test that pnl_usd takes precedence over net_pnl when both exist."""
        trade = MagicMock()
        trade.pnl_usd = 100.0
        trade.net_pnl = 200.0
        trade.realized_pnl = 300.0
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == 100.0, f"Expected 100.0 (pnl_usd), got {pnl}"
    
    def test_precedence_net_pnl_over_realized_pnl(self):
        """Test that net_pnl takes precedence over realized_pnl when pnl_usd doesn't exist."""
        class RawTrade:
            def __init__(self):
                # No pnl_usd
                self.net_pnl = 200.0
                self.realized_pnl = 300.0
        
        trade = RawTrade()
        
        pnl = get_pnl_from_completed_trade(trade)
        assert pnl == 200.0, f"Expected 200.0 (net_pnl), got {pnl}"


class TestGetTimestampFromCompletedTrade:
    """Test get_timestamp_from_completed_trade function with different scenarios."""
    
    def test_trade_with_exit_time(self):
        """Test with trade that has exit_time (preferred)."""
        trade = MagicMock()
        exit_time = datetime.now(timezone.utc) + timedelta(hours=1)
        trade.exit_time = exit_time
        trade.entry_time = datetime.now(timezone.utc)
        
        timestamp = get_timestamp_from_completed_trade(trade)
        assert timestamp == exit_time, f"Expected exit_time, got {timestamp}"
    
    def test_trade_with_entry_time_only(self):
        """Test with trade that only has entry_time."""
        trade = MagicMock()
        entry_time = datetime.now(timezone.utc)
        trade.exit_time = None
        trade.entry_time = entry_time
        
        timestamp = get_timestamp_from_completed_trade(trade)
        assert timestamp == entry_time, f"Expected entry_time, got {timestamp}"
    
    def test_trade_with_no_timestamps(self):
        """Test with trade that has no timestamps (uses fallback)."""
        trade = MagicMock()
        trade.exit_time = None
        trade.entry_time = None
        
        custom_fallback = datetime(2024, 1, 1, tzinfo=timezone.utc)
        timestamp = get_timestamp_from_completed_trade(trade, fallback=custom_fallback)
        assert timestamp == custom_fallback, f"Expected fallback, got {timestamp}"
    
    def test_trade_with_no_timestamps_default_fallback(self):
        """Test with trade that has no timestamps (uses default fallback)."""
        trade = MagicMock()
        trade.exit_time = None
        trade.entry_time = None
        
        timestamp = get_timestamp_from_completed_trade(trade)
        # Should be close to now (within 1 second)
        now = datetime.now(timezone.utc)
        time_diff = abs((timestamp - now).total_seconds())
        assert time_diff < 1.0, f"Expected timestamp close to now, got {timestamp}"
    
    def test_trade_report_object(self):
        """Test with TradeReport object."""
        exit_time = datetime.now(timezone.utc) + timedelta(hours=1)
        entry_time = datetime.now(timezone.utc)
        
        trade = TradeReport(
            trade_id="test-1",
            strategy_id="strategy-1",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=entry_time,
            entry_price=40000.0,
            exit_time=exit_time,
            exit_price=41000.0,
            quantity=0.1,
            leverage=5,
            fee_paid=3.2,
            funding_fee=0.0,
            pnl_usd=996.8,
            pnl_pct=2.49,
            exit_reason="TP"
        )
        
        timestamp = get_timestamp_from_completed_trade(trade)
        assert timestamp == exit_time, f"Expected exit_time, got {timestamp}"
    
    def test_completed_trade_match_object(self):
        """Test with CompletedTradeMatch object."""
        exit_time = datetime.now(timezone.utc) + timedelta(hours=1)
        entry_time = datetime.now(timezone.utc)
        
        trade = CompletedTradeMatch(
            entry_price=40000.0,
            exit_price=41000.0,
            quantity=0.1,
            side="LONG",
            entry_time=entry_time,
            exit_time=exit_time,
            entry_order_id=1001,
            exit_order_id=1002,
            gross_pnl=1000.0,
            fee_paid=3.2,
            net_pnl=996.8,
            exit_reason="TP"
        )
        
        timestamp = get_timestamp_from_completed_trade(trade)
        assert timestamp == exit_time, f"Expected exit_time, got {timestamp}"


class TestRiskUtilsIntegration:
    """Integration tests for risk utilities with real trade objects."""
    
    def test_trade_report_full_cycle(self):
        """Test complete cycle with TradeReport: PnL extraction and timestamp extraction."""
        trade = TradeReport(
            trade_id="test-integration-1",
            strategy_id="strategy-1",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            entry_price=40000.0,
            exit_time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
            exit_price=41000.0,
            quantity=0.1,
            leverage=5,
            fee_paid=3.2,
            funding_fee=0.0,
            pnl_usd=996.8,
            pnl_pct=2.49,
            exit_reason="TP"
        )
        
        pnl = get_pnl_from_completed_trade(trade)
        timestamp = get_timestamp_from_completed_trade(trade)
        
        assert pnl == 996.8
        assert timestamp == datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    
    def test_completed_trade_match_full_cycle(self):
        """Test complete cycle with CompletedTradeMatch: PnL extraction and timestamp extraction."""
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        
        trade = CompletedTradeMatch(
            entry_price=40000.0,
            exit_price=41000.0,
            quantity=0.1,
            side="LONG",
            entry_time=entry_time,
            exit_time=exit_time,
            entry_order_id=1001,
            exit_order_id=1002,
            gross_pnl=1000.0,
            fee_paid=3.2,
            net_pnl=996.8,
            exit_reason="TP"
        )
        
        pnl = get_pnl_from_completed_trade(trade)
        timestamp = get_timestamp_from_completed_trade(trade)
        
        assert pnl == 996.8
        assert timestamp == exit_time

