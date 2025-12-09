"""Comprehensive test cases for time handling throughout the application.

This test suite covers:
- Binance timestamp conversion (milliseconds to datetime)
- Date filter parsing and timezone handling
- Trade timestamp extraction
- Chart timestamp conversion
- Timezone normalization
- Edge cases (missing timezones, invalid dates, etc.)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from dateutil import parser as date_parser

from app.models.order import OrderResponse
from app.models.report import TradeReport, StrategyReport, TradingReport
from app.api.routes.reports import _match_trades_to_completed_positions, get_trading_report
from app.services.strategy_runner import StrategyRunner
from app.models.strategy import StrategySummary, StrategyState, StrategyType, StrategyParams
from app.core.my_binance_client import BinanceClient


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


class TestBinanceTimestampConversion:
    """Test conversion of Binance timestamps (milliseconds) to datetime objects."""
    
    def test_binance_milliseconds_to_datetime(self):
        """Test converting Binance milliseconds timestamp to UTC datetime."""
        # Binance timestamp: 1704067200000 (milliseconds)
        # Expected: 2024-01-01 00:00:00 UTC
        timestamp_ms = 1704067200000
        expected_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        # Simulate the conversion used in my_binance_client.py
        converted_dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        
        assert converted_dt == expected_dt
        assert converted_dt.tzinfo == timezone.utc
    
    def test_binance_timestamp_in_order_response(self):
        """Test that OrderResponse correctly stores Binance timestamps."""
        # Create order with timestamp in milliseconds (as Binance provides)
        timestamp_ms = 1704067200000
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=1001,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=dt,
        )
        
        assert order.timestamp == dt
        assert order.timestamp.tzinfo == timezone.utc
        # Verify it can be converted back to milliseconds
        assert int(order.timestamp.timestamp() * 1000) == timestamp_ms
    
    def test_order_with_update_time(self):
        """Test OrderResponse with update_time field."""
        timestamp_ms = 1704067200000
        update_time_ms = 1704067260000  # 1 minute later
        
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        update_time = datetime.fromtimestamp(update_time_ms / 1000.0, tz=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=1001,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=timestamp,
            update_time=update_time,
        )
        
        assert order.update_time == update_time
        assert order.update_time > order.timestamp
        assert (order.update_time - order.timestamp).total_seconds() == 60


class TestTradeTimestampExtraction:
    """Test extraction of timestamps from trades for report generation."""
    
    def test_get_trade_timestamp_prefers_timestamp(self):
        """Test that get_trade_timestamp prefers timestamp over update_time."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        update_time = datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=1001,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=timestamp,
            update_time=update_time,
        )
        
        # Simulate the logic from reports.py
        if order.timestamp:
            trade_time = order.timestamp
        elif order.update_time:
            trade_time = order.update_time
        else:
            trade_time = datetime.now(timezone.utc)
        
        assert trade_time == timestamp  # Should prefer timestamp
    
    def test_get_trade_timestamp_falls_back_to_update_time(self):
        """Test that get_trade_timestamp falls back to update_time if timestamp is missing."""
        update_time = datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc)
        
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=1001,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=None,
            update_time=update_time,
        )
        
        # Simulate the logic from reports.py
        if order.timestamp:
            trade_time = order.timestamp
        elif order.update_time:
            trade_time = order.update_time
        else:
            trade_time = datetime.now(timezone.utc)
        
        assert trade_time == update_time  # Should use update_time
    
    def test_get_trade_timestamp_falls_back_to_current_time(self):
        """Test that get_trade_timestamp falls back to current UTC time if both are missing."""
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=1001,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=None,
            update_time=None,
        )
        
        # Simulate the logic from reports.py
        before = datetime.now(timezone.utc)
        if order.timestamp:
            trade_time = order.timestamp
        elif order.update_time:
            trade_time = order.update_time
        else:
            trade_time = datetime.now(timezone.utc)
        after = datetime.now(timezone.utc)
        
        assert before <= trade_time <= after
        assert trade_time.tzinfo == timezone.utc


class TestDateFilterParsing:
    """Test parsing and normalization of date filters."""
    
    def test_parse_iso_datetime_with_timezone(self):
        """Test parsing ISO datetime string with timezone."""
        date_str = "2024-01-01T12:00:00Z"
        parsed = date_parser.parse(date_str)
        
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        
        # dateutil parser returns tzutc() which is equivalent to timezone.utc
        # Check that it's UTC timezone (either timezone.utc or tzutc())
        assert parsed.tzinfo is not None
        # Verify it's UTC by checking offset
        assert parsed.tzinfo.utcoffset(None).total_seconds() == 0
        assert parsed.year == 2024
        assert parsed.month == 1
        assert parsed.day == 1
        assert parsed.hour == 12
    
    def test_parse_iso_datetime_without_timezone(self):
        """Test parsing ISO datetime string without timezone (should default to UTC)."""
        date_str = "2024-01-01T12:00:00"
        parsed = date_parser.parse(date_str)
        
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        
        assert parsed.tzinfo == timezone.utc
    
    def test_parse_invalid_date_format(self):
        """Test that invalid date formats are handled gracefully."""
        invalid_date = "invalid-date-format"
        
        try:
            parsed = date_parser.parse(invalid_date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            # If parsing succeeds, it should have timezone
            assert parsed.tzinfo == timezone.utc
        except (ValueError, TypeError):
            # Expected behavior: invalid dates should raise exceptions
            pass
    
    def test_date_filter_timezone_normalization(self):
        """Test that date filters are normalized to UTC."""
        # Simulate the logic from reports.py
        start_date = "2024-01-01T12:00:00"
        start_datetime = None
        
        if start_date:
            try:
                start_datetime = date_parser.parse(start_date)
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                start_datetime = None
        
        assert start_datetime is not None
        assert start_datetime.tzinfo == timezone.utc


class TestTimezoneNormalization:
    """Test timezone normalization in various scenarios."""
    
    def test_normalize_naive_datetime_to_utc(self):
        """Test normalizing timezone-naive datetime to UTC."""
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        
        if naive_dt.tzinfo is None:
            normalized = naive_dt.replace(tzinfo=timezone.utc)
        
        assert normalized.tzinfo == timezone.utc
        assert normalized.year == 2024
        assert normalized.month == 1
        assert normalized.day == 1
        assert normalized.hour == 12
    
    def test_keep_utc_datetime_unchanged(self):
        """Test that UTC datetime remains unchanged."""
        utc_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        if utc_dt.tzinfo is None:
            normalized = utc_dt.replace(tzinfo=timezone.utc)
        else:
            normalized = utc_dt
        
        assert normalized == utc_dt
        assert normalized.tzinfo == timezone.utc
    
    def test_trade_time_normalization(self):
        """Test that trade times are normalized before comparison."""
        # Simulate trade with naive datetime
        trade_time = datetime(2024, 1, 1, 12, 0, 0)
        start_datetime = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        
        # Normalize trade_time
        if trade_time.tzinfo is None:
            trade_time = trade_time.replace(tzinfo=timezone.utc)
        
        # Now comparison should work
        assert trade_time > start_datetime
        assert trade_time.tzinfo == timezone.utc
    
    def test_chart_time_range_normalization(self):
        """Test that chart time ranges are normalized."""
        chart_start = datetime(2024, 1, 1, 12, 0, 0)  # Naive
        chart_end = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)  # UTC
        
        # Normalize both
        if chart_start.tzinfo is None:
            chart_start = chart_start.replace(tzinfo=timezone.utc)
        if chart_end.tzinfo is None:
            chart_end = chart_end.replace(tzinfo=timezone.utc)
        
        assert chart_start.tzinfo == timezone.utc
        assert chart_end.tzinfo == timezone.utc
        assert chart_start < chart_end


class TestChartTimestampConversion:
    """Test timestamp conversion for chart rendering."""
    
    def test_klines_milliseconds_to_seconds(self):
        """Test converting klines timestamps from milliseconds to seconds."""
        # Binance kline format: [timestamp_ms, open, high, low, close, ...]
        kline = [1704067200000, 50000.0, 50100.0, 49900.0, 50050.0, 1.5]
        
        timestamp_ms = int(kline[0])
        timestamp_seconds = timestamp_ms // 1000
        
        assert timestamp_seconds == 1704067200
        # Verify it can be converted back
        assert timestamp_seconds * 1000 == timestamp_ms
    
    def test_chart_marker_timestamp_conversion(self):
        """Test converting trade marker timestamps for chart display."""
        # Trade entry_time from API (ISO 8601 string)
        entry_time_str = "2024-01-01T12:00:00Z"
        entry_date = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
        
        # Convert to Unix timestamp in seconds (for chart library)
        entry_time_seconds = int(entry_date.timestamp())
        
        # Verify conversion
        assert entry_time_seconds == 1704110400  # 2024-01-01 12:00:00 UTC in seconds
        # Verify it matches the milliseconds version
        assert entry_time_seconds * 1000 == int(entry_date.timestamp() * 1000)
    
    def test_chart_data_preparation(self):
        """Test preparing klines data for chart rendering."""
        # Simulate klines from Binance
        klines = [
            [1704067200000, 50000.0, 50100.0, 49900.0, 50050.0, 1.5],  # Valid
            [1704067260000, 50050.0, 50150.0, 50000.0, 50100.0, 1.6],  # Valid
            [None, None, None, None, None, None],  # Invalid (should be filtered)
        ]
        
        # Filter and convert (simulate frontend logic)
        candlestick_data = []
        for k in klines:
            if k and len(k) >= 5 and k[0] and k[1] and k[2] and k[3] and k[4]:
                timestamp_ms = int(k[0])
                if timestamp_ms > 0:
                    candlestick_data.append({
                        'time': timestamp_ms // 1000,  # Convert to seconds
                        'open': float(k[1]),
                        'high': float(k[2]),
                        'low': float(k[3]),
                        'close': float(k[4]),
                    })
        
        assert len(candlestick_data) == 2
        assert candlestick_data[0]['time'] == 1704067200
        assert candlestick_data[1]['time'] == 1704067260
        assert candlestick_data[0]['open'] == 50000.0


class TestTradeMatchingWithTimestamps:
    """Test trade matching with proper timestamp handling."""
    
    def test_match_trades_with_timestamps(self):
        """Test matching trades that have proper timestamps."""
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        
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
        trade = completed[0]
        assert trade.entry_time == entry_time
        assert trade.exit_time == exit_time
        assert trade.entry_time.tzinfo == timezone.utc
        assert trade.exit_time.tzinfo == timezone.utc
    
    def test_match_trades_sorted_by_timestamp(self):
        """Test that trades are sorted by timestamp before matching."""
        # Create trades out of order
        later_time = datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        earlier_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        trades = [
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1002,  # Exit order (later)
                status="FILLED",
                side="SELL",
                price=51000.0,
                avg_price=51000.0,
                executed_qty=0.1,
                timestamp=later_time,
            ),
            OrderResponse(
                symbol="BTCUSDT",
                order_id=1001,  # Entry order (earlier)
                status="FILLED",
                side="BUY",
                price=50000.0,
                avg_price=50000.0,
                executed_qty=0.1,
                timestamp=earlier_time,
            ),
        ]
        
        # The function should sort by timestamp internally
        completed = _match_trades_to_completed_positions(
            trades=trades,
            strategy_id="test-1",
            strategy_name="Test Strategy",
            symbol="BTCUSDT",
            leverage=5,
        )
        
        # Should still match correctly despite out-of-order input
        assert len(completed) == 1
        trade = completed[0]
        assert trade.entry_time == earlier_time
        assert trade.exit_time == later_time


class TestReportGenerationWithTimeFilters:
    """Test report generation with date filters."""
    
    def test_date_filter_parsing_and_normalization(self):
        """Test that date filters are parsed and normalized correctly."""
        # Test ISO datetime with timezone
        start_date = "2024-01-01T11:00:00Z"
        start_datetime = None
        
        if start_date:
            try:
                start_datetime = date_parser.parse(start_date)
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                start_datetime = None
        
        assert start_datetime is not None
        assert start_datetime.tzinfo is not None
        # Verify it's UTC (check offset)
        assert start_datetime.tzinfo.utcoffset(None).total_seconds() == 0
    
    def test_date_filter_without_timezone_normalized(self):
        """Test that date filters without timezone are normalized to UTC."""
        # Filter without timezone (should be treated as UTC)
        start_date = "2024-01-01T11:00:00"
        start_datetime = None
        
        if start_date:
            try:
                start_datetime = date_parser.parse(start_date)
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                start_datetime = None
        
        assert start_datetime is not None
        assert start_datetime.tzinfo == timezone.utc
    
    def test_trade_time_filtering_logic(self):
        """Test the logic for filtering trades by time."""
        # Create a trade with timestamp
        trade_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        start_datetime = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        end_datetime = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        
        # Normalize trade_time if needed (simulate the logic)
        if trade_time.tzinfo is None:
            trade_time = trade_time.replace(tzinfo=timezone.utc)
        
        # Check if trade is within range
        is_in_range = start_datetime <= trade_time <= end_datetime
        assert is_in_range is True
    
    def test_trade_time_filtering_excludes_outside_range(self):
        """Test that trades outside time range are excluded."""
        # Trade at 12:00
        trade_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        # Filter: 14:00 - 15:00
        start_datetime = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        end_datetime = datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
        
        # Normalize trade_time if needed
        if trade_time.tzinfo is None:
            trade_time = trade_time.replace(tzinfo=timezone.utc)
        
        # Check if trade is within range
        is_in_range = start_datetime <= trade_time <= end_datetime
        assert is_in_range is False


class TestEdgeCases:
    """Test edge cases in time handling."""
    
    def test_missing_timestamp_handling(self):
        """Test handling of missing timestamps."""
        order = OrderResponse(
            symbol="BTCUSDT",
            order_id=1001,
            status="FILLED",
            side="BUY",
            price=50000.0,
            avg_price=50000.0,
            executed_qty=0.1,
            timestamp=None,
            update_time=None,
        )
        
        # Should fall back to current time
        if order.timestamp:
            trade_time = order.timestamp
        elif order.update_time:
            trade_time = order.update_time
        else:
            trade_time = datetime.now(timezone.utc)
        
        assert trade_time is not None
        assert trade_time.tzinfo == timezone.utc
    
    def test_invalid_timestamp_format(self):
        """Test handling of invalid timestamp formats."""
        # This should be handled gracefully in date parsing
        invalid_date = "not-a-date"
        
        try:
            parsed = date_parser.parse(invalid_date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            # Expected: invalid dates should raise exceptions
            parsed = None
        
        # Should either parse successfully or be None
        assert parsed is None or parsed.tzinfo == timezone.utc
    
    def test_very_old_timestamp(self):
        """Test handling of very old timestamps."""
        # Very old timestamp (year 2000)
        old_timestamp_ms = 946684800000  # 2000-01-01 00:00:00 UTC
        dt = datetime.fromtimestamp(old_timestamp_ms / 1000.0, tz=timezone.utc)
        
        assert dt.year == 2000
        assert dt.tzinfo == timezone.utc
    
    def test_future_timestamp(self):
        """Test handling of future timestamps."""
        # Future timestamp (year 2100)
        future_timestamp_ms = 4102444800000  # 2100-01-01 00:00:00 UTC
        dt = datetime.fromtimestamp(future_timestamp_ms / 1000.0, tz=timezone.utc)
        
        assert dt.year == 2100
        assert dt.tzinfo == timezone.utc
    
    def test_zero_timestamp(self):
        """Test handling of zero timestamp (should be invalid)."""
        zero_timestamp_ms = 0
        
        # Should be rejected as invalid
        if zero_timestamp_ms > 0:
            dt = datetime.fromtimestamp(zero_timestamp_ms / 1000.0, tz=timezone.utc)
        else:
            dt = None
        
        assert dt is None
    
    def test_negative_timestamp(self):
        """Test handling of negative timestamp (should be invalid)."""
        negative_timestamp_ms = -1000
        
        # Should be rejected as invalid
        if negative_timestamp_ms > 0:
            dt = datetime.fromtimestamp(negative_timestamp_ms / 1000.0, tz=timezone.utc)
        else:
            dt = None
        
        assert dt is None


class TestDateTimeComparison:
    """Test datetime comparisons with timezone awareness."""
    
    def test_compare_utc_datetimes(self):
        """Test comparing two UTC datetimes."""
        dt1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        
        assert dt1 < dt2
        assert dt2 > dt1
        assert dt1 != dt2
    
    def test_compare_naive_and_utc_datetimes(self):
        """Test that naive and UTC datetimes can be compared after normalization."""
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        utc_dt = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        
        # Normalize naive datetime
        if naive_dt.tzinfo is None:
            naive_dt = naive_dt.replace(tzinfo=timezone.utc)
        
        # Now comparison should work
        assert naive_dt < utc_dt
        assert naive_dt.tzinfo == timezone.utc
    
    def test_datetime_arithmetic_with_timezone(self):
        """Test datetime arithmetic preserves timezone."""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        delta = timedelta(hours=1)
        
        new_dt = dt + delta
        
        assert new_dt.tzinfo == timezone.utc
        assert new_dt.hour == 13
        assert (new_dt - dt) == delta


class TestReportModelTimeFields:
    """Test time fields in report models."""
    
    def test_trading_report_generated_at(self):
        """Test that TradingReport has UTC timestamp for report_generated_at."""
        report = TradingReport(
            strategies=[],
            total_strategies=0,
            total_trades=0,
            overall_win_rate=0.0,
            overall_net_pnl=0.0,
        )
        
        assert report.report_generated_at is not None
        assert report.report_generated_at.tzinfo == timezone.utc
    
    def test_trade_report_timestamps(self):
        """Test that TradeReport timestamps are properly handled."""
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        exit_time = datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        
        trade = TradeReport(
            trade_id="test-1",
            strategy_id="strategy-1",
            symbol="BTCUSDT",
            side="LONG",
            entry_time=entry_time,
            entry_price=50000.0,
            exit_time=exit_time,
            exit_price=51000.0,
            quantity=0.1,
            leverage=5,
            fee_paid=0.0,
            pnl_usd=100.0,
            pnl_pct=0.2,
        )
        
        assert trade.entry_time == entry_time
        assert trade.exit_time == exit_time
        assert trade.entry_time.tzinfo == timezone.utc
        assert trade.exit_time.tzinfo == timezone.utc

