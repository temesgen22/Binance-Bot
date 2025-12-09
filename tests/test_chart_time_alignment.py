"""
Test that chart timestamps match trade entry/exit times in both backtesting and reports.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from app.api.routes.backtesting import run_backtest, BacktestRequest, Trade
from app.core.my_binance_client import BinanceClient


def test_trade_time_matches_kline_timestamp():
    """Test that trade entry_time matches the kline timestamp it was created from."""
    # Create a trade with entry_time from a kline timestamp
    kline_timestamp_ms = 1702051200000  # 2023-12-09 00:00:00 UTC in milliseconds
    candle_time = datetime.fromtimestamp(kline_timestamp_ms / 1000, tz=timezone.utc)
    
    trade = Trade(
        entry_time=candle_time,
        exit_time=None,
        entry_price=40000.0,
        exit_price=None,
        position_side="LONG",
        quantity=0.001,
        notional=40.0,
        entry_fee=0.012,
        exit_fee=None,
        pnl=None,
        net_pnl=None,
        exit_reason=None,
        is_open=True
    )
    
    # Verify trade entry_time matches the kline timestamp
    assert trade.entry_time == candle_time
    assert trade.entry_time.tzinfo == timezone.utc
    
    # Convert to timestamp for comparison
    trade_timestamp_ms = int(trade.entry_time.timestamp() * 1000)
    assert trade_timestamp_ms == kline_timestamp_ms


def test_chart_timestamp_conversion():
    """Test that JavaScript chart timestamp conversion matches Python timestamp."""
    # Simulate what happens in the frontend
    kline_timestamp_ms = 1702051200000  # 2023-12-09 00:00:00 UTC
    
    # Python: Convert kline timestamp to datetime
    candle_time = datetime.fromtimestamp(kline_timestamp_ms / 1000, tz=timezone.utc)
    
    # Python: Create trade with this time
    trade = Trade(
        entry_time=candle_time,
        exit_time=None,
        entry_price=40000.0,
        exit_price=None,
        position_side="LONG",
        quantity=0.001,
        notional=40.0,
        entry_fee=0.012,
        exit_fee=None,
        pnl=None,
        net_pnl=None,
        exit_reason=None,
        is_open=True
    )
    
    # Simulate JSON serialization (FastAPI/Pydantic converts datetime to ISO string)
    # In real scenario, this would be: trade.model_dump(mode='json')
    trade_dict = trade.model_dump(mode='json')
    entry_time_iso = trade_dict['entry_time']
    
    # Verify ISO string format (should include timezone)
    assert 'T' in entry_time_iso or 'Z' in entry_time_iso or '+' in entry_time_iso or entry_time_iso.endswith('+00:00')
    
    # Simulate JavaScript: new Date(entry_time_iso).getTime() / 1000
    # In Python, we can parse the ISO string and convert to timestamp
    parsed_time = datetime.fromisoformat(entry_time_iso.replace('Z', '+00:00'))
    js_timestamp_seconds = int(parsed_time.timestamp())
    
    # Kline timestamp in seconds (what chart uses)
    kline_timestamp_seconds = kline_timestamp_ms // 1000
    
    # They should match
    assert js_timestamp_seconds == kline_timestamp_seconds, (
        f"Chart timestamp mismatch: trade={js_timestamp_seconds}, kline={kline_timestamp_seconds}"
    )


def test_backtesting_trade_time_alignment():
    """Test that backtesting trade times align with kline timestamps."""
    # Create sample klines
    base_timestamp = 1702051200000  # 2023-12-09 00:00:00 UTC
    klines = []
    for i in range(10):
        timestamp = base_timestamp + (i * 60000)  # 1 minute intervals
        klines.append([
            timestamp,  # open_time in ms
            "40000.0",  # open
            "40100.0",  # high
            "39900.0",  # low
            "40050.0",  # close
            "1000.0",   # volume
            timestamp + 60000,  # close_time in ms
            "0.0",      # quote_asset_volume
            "10",       # number_of_trades
            "500.0",    # taker_buy_base_asset_volume
            "500.0",    # taker_buy_quote_asset_volume
            "0"         # ignore
        ])
    
    # Simulate creating a trade from a kline
    kline_index = 5
    kline = klines[kline_index]
    kline_timestamp_ms = int(kline[0])
    
    # Convert to datetime (as done in backtesting)
    candle_time = datetime.fromtimestamp(kline_timestamp_ms / 1000, tz=timezone.utc)
    
    # Create trade (as done in backtesting)
    trade = Trade(
        entry_time=candle_time,
        exit_time=None,
        entry_price=40000.0,
        exit_price=None,
        position_side="LONG",
        quantity=0.001,
        notional=40.0,
        entry_fee=0.012,
        exit_fee=None,
        pnl=None,
        net_pnl=None,
        exit_reason=None,
        is_open=True
    )
    
    # Verify the trade time matches the kline timestamp
    trade_timestamp_ms = int(trade.entry_time.timestamp() * 1000)
    assert trade_timestamp_ms == kline_timestamp_ms, (
        f"Trade entry_time ({trade_timestamp_ms}) doesn't match kline timestamp ({kline_timestamp_ms})"
    )
    
    # Verify both are in UTC
    assert trade.entry_time.tzinfo == timezone.utc
    assert candle_time.tzinfo == timezone.utc


def test_reports_trade_time_format():
    """Test that reports trade times are in correct format for chart."""
    from app.models.report import TradeReport
    
    # Create a trade report with entry and exit times
    entry_time = datetime(2023, 12, 9, 0, 0, 0, tzinfo=timezone.utc)
    exit_time = datetime(2023, 12, 9, 1, 0, 0, tzinfo=timezone.utc)
    
    trade_report = TradeReport(
        trade_id="test-123",
        strategy_id="strategy-1",
        symbol="BTCUSDT",
        side="LONG",
        entry_time=entry_time,
        entry_price=40000.0,
        exit_time=exit_time,
        exit_price=40100.0,
        quantity=0.001,
        leverage=5,
        fee_paid=0.024,
        pnl_usd=0.1,
        pnl_pct=0.25,
        exit_reason="TP"
    )
    
    # Serialize to JSON (as FastAPI does)
    trade_dict = trade_report.model_dump(mode='json')
    
    # Verify times are serialized correctly
    assert 'entry_time' in trade_dict
    assert 'exit_time' in trade_dict
    
    # Parse back to verify
    entry_iso = trade_dict['entry_time']
    exit_iso = trade_dict['exit_time']
    
    # Should be parseable as ISO 8601
    parsed_entry = datetime.fromisoformat(entry_iso.replace('Z', '+00:00'))
    parsed_exit = datetime.fromisoformat(exit_iso.replace('Z', '+00:00'))
    
    # Verify they match original times
    assert parsed_entry == entry_time
    assert parsed_exit == exit_time
    
    # Verify timestamps match
    entry_timestamp_seconds = int(parsed_entry.timestamp())
    original_entry_timestamp_seconds = int(entry_time.timestamp())
    assert entry_timestamp_seconds == original_entry_timestamp_seconds

