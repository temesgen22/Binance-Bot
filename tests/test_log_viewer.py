"""Test cases for the log viewer GUI and API endpoints."""
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes.logs import parse_log_line, filter_logs, LogEntry


def setup_mock_file(mock_file_func, content: str):
    """Helper function to setup mock file for reading lines.
    
    The file is opened with 'with open(...) as f:' and then iterated with 'for line in f:'.
    We need to make the mock file object iterable.
    """
    lines = content.splitlines(keepends=False)  # Split into lines without newlines
    if not lines:  # Handle empty content
        lines = ['']
    
    # Create a mock that acts like a file object
    mock_file_obj = MagicMock()
    # Make it iterable - Python's for loop calls iter() which should return an iterator
    # We'll make __iter__ return an iterator over the lines
    mock_file_obj.__iter__ = MagicMock(return_value=iter(lines))
    mock_file_obj.__enter__ = MagicMock(return_value=mock_file_obj)
    mock_file_obj.__exit__ = MagicMock(return_value=None)
    
    # Set the mock_open to return our mock file object
    mock_file_func.return_value = mock_file_obj
    return mock_file_obj


class TestLogParsing:
    """Test log line parsing functionality."""

    def test_parse_valid_log_line(self):
        """Test parsing a valid log line."""
        line = "2025-11-24 01:18:35 | INFO     | app.services.strategy_runner:_load_from_redis:299 | Redis not enabled"
        entry = parse_log_line(line)
        
        assert entry is not None
        assert entry.timestamp == "2025-11-24 01:18:35"
        assert entry.level == "INFO"
        assert entry.module == "app.services.strategy_runner"
        assert entry.function == "_load_from_redis"
        assert entry.line == 299
        assert entry.message == "Redis not enabled"
        assert entry.raw_line == line.strip()

    def test_parse_debug_log_line(self):
        """Test parsing a DEBUG level log line."""
        line = "2025-11-24 10:30:45 | DEBUG    | app.strategies.scalping:evaluate:142 | Fast EMA: 50000.5, Slow EMA: 49980.3"
        entry = parse_log_line(line)
        
        assert entry is not None
        assert entry.level == "DEBUG"
        assert entry.module == "app.strategies.scalping"
        assert entry.function == "evaluate"

    def test_parse_error_log_line(self):
        """Test parsing an ERROR level log line."""
        line = "2025-11-24 15:45:20 | ERROR    | app.core.my_binance_client:place_order:89 | Order execution failed: Insufficient balance"
        entry = parse_log_line(line)
        
        assert entry is not None
        assert entry.level == "ERROR"
        assert "Order execution failed" in entry.message

    def test_parse_log_with_symbol(self):
        """Test parsing a log line containing cryptocurrency symbol."""
        line = "2025-11-24 12:00:00 | INFO     | app.services.strategy_runner:_run_loop:277 | Signal: BUY | Symbol: BTCUSDT | Price: 42000.5"
        entry = parse_log_line(line)
        
        assert entry is not None
        assert "BTCUSDT" in entry.message
        assert "BUY" in entry.message

    def test_parse_invalid_log_line(self):
        """Test parsing an invalid log line returns None."""
        invalid_lines = [
            "This is not a valid log line",
            "2025-11-24 | INFO | message",
            "2025-11-24 01:18:35 | INFO | message",
            "",
            "   ",
        ]
        
        for line in invalid_lines:
            entry = parse_log_line(line)
            assert entry is None

    def test_parse_log_with_special_characters(self):
        """Test parsing log line with special characters in message."""
        line = "2025-11-24 01:18:35 | INFO     | app.services.strategy_runner:_execute:374 | Order placed: BUY BTCUSDT @ $42,000.50 (Leverage: 5x)"
        entry = parse_log_line(line)
        
        assert entry is not None
        assert "$42,000.50" in entry.message
        assert "5x" in entry.message


class TestLogFiltering:
    """Test log filtering functionality."""

    @pytest.fixture
    def sample_entries(self):
        """Create sample log entries for testing."""
        return [
            LogEntry(
                timestamp="2025-11-24 01:00:00",
                level="INFO",
                module="app.services.strategy_runner",
                function="_execute",
                line=100,
                message="Order placed for BTCUSDT",
                raw_line=""
            ),
            LogEntry(
                timestamp="2025-11-24 02:00:00",
                level="DEBUG",
                module="app.strategies.scalping",
                function="evaluate",
                line=50,
                message="EMA calculation for ETHUSDT",
                raw_line=""
            ),
            LogEntry(
                timestamp="2025-11-24 03:00:00",
                level="ERROR",
                module="app.core.my_binance_client",
                function="place_order",
                line=200,
                message="Failed to place order for BTCUSDT: Insufficient funds",
                raw_line=""
            ),
            LogEntry(
                timestamp="2025-11-25 01:00:00",
                level="INFO",
                module="app.services.strategy_runner",
                function="_run_loop",
                line=150,
                message="Strategy started for ETHUSDT",
                raw_line=""
            ),
        ]

    def test_filter_by_symbol(self, sample_entries):
        """Test filtering logs by cryptocurrency symbol."""
        filtered = filter_logs(sample_entries, symbol="BTCUSDT")
        
        assert len(filtered) == 2
        assert all("BTCUSDT" in entry.message.upper() for entry in filtered)

    def test_filter_by_level(self, sample_entries):
        """Test filtering logs by level."""
        filtered = filter_logs(sample_entries, level="ERROR")
        
        assert len(filtered) == 1
        assert filtered[0].level == "ERROR"

    def test_filter_by_date_from(self, sample_entries):
        """Test filtering logs by start date."""
        filtered = filter_logs(sample_entries, date_from="2025-11-25")
        
        assert len(filtered) == 1
        assert filtered[0].timestamp.startswith("2025-11-25")

    def test_filter_by_date_to(self, sample_entries):
        """Test filtering logs by end date."""
        filtered = filter_logs(sample_entries, date_to="2025-11-24")
        
        assert len(filtered) == 3
        assert all(entry.timestamp.startswith("2025-11-24") for entry in filtered)

    def test_filter_by_date_range(self, sample_entries):
        """Test filtering logs by date range."""
        filtered = filter_logs(
            sample_entries,
            date_from="2025-11-24",
            date_to="2025-11-24"
        )
        
        assert len(filtered) == 3

    def test_filter_by_module(self, sample_entries):
        """Test filtering logs by module."""
        filtered = filter_logs(sample_entries, module="strategy_runner")
        
        assert len(filtered) == 2
        assert all("strategy_runner" in entry.module for entry in filtered)

    def test_filter_by_function(self, sample_entries):
        """Test filtering logs by function name."""
        filtered = filter_logs(sample_entries, function="_execute")
        
        assert len(filtered) == 1
        assert filtered[0].function == "_execute"

    def test_filter_by_search_text(self, sample_entries):
        """Test filtering logs by search text."""
        filtered = filter_logs(sample_entries, search_text="order")
        
        assert len(filtered) == 2
        assert all("order" in entry.message.lower() for entry in filtered)

    def test_filter_multiple_criteria(self, sample_entries):
        """Test filtering logs with multiple criteria."""
        filtered = filter_logs(
            sample_entries,
            symbol="BTCUSDT",
            level="INFO",
            date_from="2025-11-24"
        )
        
        assert len(filtered) == 1
        assert "BTCUSDT" in filtered[0].message
        assert filtered[0].level == "INFO"

    def test_filter_case_insensitive_symbol(self, sample_entries):
        """Test that symbol filtering is case-insensitive."""
        filtered_lower = filter_logs(sample_entries, symbol="btcusdt")
        filtered_upper = filter_logs(sample_entries, symbol="BTCUSDT")
        
        assert len(filtered_lower) == len(filtered_upper) == 2

    def test_filter_no_matches(self, sample_entries):
        """Test filtering with criteria that match nothing."""
        filtered = filter_logs(sample_entries, symbol="DOGECOIN")
        
        assert len(filtered) == 0


class TestLogAPIEndpoints:
    """Test the log viewer API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from app.main import app as test_app
        # Mock binance client for app state
        class StubBinanceClient:
            def get_price(self, symbol: str) -> float:  # noqa: ARG002
                return 42000.0
        test_app.state.binance_client = StubBinanceClient()
        return TestClient(test_app)

    @pytest.fixture
    def sample_log_content(self):
        """Sample log file content for testing."""
        return """2025-11-24 01:00:00 | INFO     | app.services.strategy_runner:_execute:100 | Order placed for BTCUSDT
2025-11-24 02:00:00 | DEBUG    | app.strategies.scalping:evaluate:50 | EMA calculation for ETHUSDT
2025-11-24 03:00:00 | ERROR    | app.core.my_binance_client:place_order:200 | Failed to place order for BTCUSDT: Insufficient funds
2025-11-25 01:00:00 | INFO     | app.services.strategy_runner:_run_loop:150 | Strategy started for ETHUSDT
"""

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_endpoint(self, mock_file, mock_read_files, client, sample_log_content):
        """Test the GET /logs/ endpoint returns log entries."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total_count" in data
        assert "filtered_count" in data
        assert len(data["entries"]) == 4

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_with_symbol_filter(self, mock_file, mock_read_files, client, sample_log_content):
        """Test filtering logs by symbol."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/?symbol=BTCUSDT")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 2
        assert all("BTCUSDT" in entry["message"].upper() for entry in data["entries"])

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_with_level_filter(self, mock_file, mock_read_files, client, sample_log_content):
        """Test filtering logs by level."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/?level=ERROR")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["level"] == "ERROR"

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_with_date_filter(self, mock_file, mock_read_files, client, sample_log_content):
        """Test filtering logs by date."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/?date_from=2025-11-25")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["timestamp"].startswith("2025-11-25")

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_with_limit(self, mock_file, mock_read_files, client, sample_log_content):
        """Test limiting the number of log entries returned."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/?limit=2")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 2

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_with_search_text(self, mock_file, mock_read_files, client, sample_log_content):
        """Test searching logs by text."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/?search_text=order")
        
        assert response.status_code == 200
        data = response.json()
        assert all("order" in entry["message"].lower() for entry in data["entries"])

    @patch("app.api.routes.logs.read_log_files")
    def test_get_logs_no_files(self, mock_read_files, client):
        """Test getting logs when no log files exist."""
        mock_read_files.return_value = []
        
        response = client.get("/api/logs/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["entries"] == []
        assert data["total_count"] == 0
        assert data["filtered_count"] == 0

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_with_module_filter(self, mock_file, mock_read_files, client, sample_log_content):
        """Test filtering logs by module."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/?module=strategy_runner")
        
        assert response.status_code == 200
        data = response.json()
        assert all("strategy_runner" in entry["module"] for entry in data["entries"])

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_with_function_filter(self, mock_file, mock_read_files, client, sample_log_content):
        """Test filtering logs by function."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/?function=_execute")
        
        assert response.status_code == 200
        data = response.json()
        assert all(entry["function"] == "_execute" for entry in data["entries"])

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_reverse_order(self, mock_file, mock_read_files, client, sample_log_content):
        """Test that logs are returned in reverse chronological order by default."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/")
        
        assert response.status_code == 200
        data = response.json()
        timestamps = [entry["timestamp"] for entry in data["entries"]]
        # Should be in reverse order (newest first)
        assert timestamps == sorted(timestamps, reverse=True)

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_symbols_endpoint(self, mock_file, mock_read_files, client, sample_log_content):
        """Test the GET /logs/symbols endpoint."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/symbols")
        
        assert response.status_code == 200
        symbols = response.json()
        assert isinstance(symbols, list)
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_get_logs_stats_endpoint(self, mock_file, mock_read_files, client, sample_log_content):
        """Test the GET /logs/stats endpoint."""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, sample_log_content)
        
        response = client.get("/api/logs/stats")
        
        assert response.status_code == 200
        stats = response.json()
        assert "total_files" in stats
        assert "levels" in stats
        assert "modules" in stats
        assert stats["levels"]["INFO"] == 2
        assert stats["levels"]["ERROR"] == 1
        assert stats["levels"]["DEBUG"] == 1


class TestStaticFileServing:
    """Test static file serving for the GUI."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from app.main import app as test_app
        class StubBinanceClient:
            def get_price(self, symbol: str) -> float:  # noqa: ARG002
                return 42000.0
        test_app.state.binance_client = StubBinanceClient()
        return TestClient(test_app)

    def test_static_index_html_exists(self, client):
        """Test that the static index.html file is accessible."""
        response = client.get("/static/index.html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Binance Bot - Log Viewer" in response.text

    def test_root_serves_gui(self, client):
        """Test that root URL serves the GUI directly."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Binance Bot - Log Viewer" in response.text


@pytest.mark.slow
class TestLogViewerIntegration:
    """Integration tests for the log viewer GUI functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from app.main import app as test_app
        class StubBinanceClient:
            def get_price(self, symbol: str) -> float:  # noqa: ARG002
                return 42000.0
        test_app.state.binance_client = StubBinanceClient()
        return TestClient(test_app)

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_full_filter_workflow(self, mock_file, mock_read_files, client):
        """Test a complete filtering workflow with multiple filters."""
        log_content = """2025-11-24 01:00:00 | INFO     | app.services.strategy_runner:_execute:100 | Order BUY placed for BTCUSDT at 42000
2025-11-24 02:00:00 | DEBUG    | app.strategies.scalping:evaluate:50 | EMA calculation for ETHUSDT
2025-11-24 03:00:00 | ERROR    | app.core.my_binance_client:place_order:200 | Failed to place order for BTCUSDT
2025-11-25 01:00:00 | INFO     | app.services.strategy_runner:_execute:150 | Order SELL placed for BTCUSDT at 42500
"""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, log_content)
        
        # Test: Filter by symbol, level, and date
        response = client.get("/api/logs/?symbol=BTCUSDT&level=INFO&date_from=2025-11-24&limit=10")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 2
        assert all("BTCUSDT" in entry["message"].upper() for entry in data["entries"])
        assert all(entry["level"] == "INFO" for entry in data["entries"])

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_symbol_extraction(self, mock_file, mock_read_files, client):
        """Test that symbols are correctly extracted from log messages."""
        log_content = """2025-11-24 01:00:00 | INFO | app.services.strategy_runner:_execute:100 | Trading BTCUSDT
2025-11-24 02:00:00 | INFO | app.services.strategy_runner:_execute:100 | Trading ETHUSDT
2025-11-24 03:00:00 | INFO | app.services.strategy_runner:_execute:100 | Trading BNBUSDT
"""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, log_content)
        
        response = client.get("/api/logs/symbols")
        
        assert response.status_code == 200
        symbols = response.json()
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
        assert "BNBUSDT" in symbols

    @patch("app.api.routes.logs.read_log_files")
    @patch("builtins.open")
    def test_statistics_calculation(self, mock_file, mock_read_files, client):
        """Test that statistics are correctly calculated."""
        log_content = """2025-11-24 01:00:00 | INFO     | app.services.strategy_runner:_execute:100 | Message 1
2025-11-24 02:00:00 | DEBUG    | app.strategies.scalping:evaluate:50 | Message 2
2025-11-24 03:00:00 | ERROR    | app.core.my_binance_client:place_order:200 | Message 3
2025-11-24 04:00:00 | INFO     | app.services.strategy_runner:_run_loop:150 | Message 4
"""
        mock_read_files.return_value = ["logs/bot.log"]
        setup_mock_file(mock_file, log_content)
        
        response = client.get("/api/logs/stats")
        
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_entries"] == 4
        assert stats["levels"]["INFO"] == 2
        assert stats["levels"]["DEBUG"] == 1
        assert stats["levels"]["ERROR"] == 1
        assert "app.services.strategy_runner" in stats["modules"]

    def test_invalid_date_format_handled_gracefully(self, client):
        """Test that invalid date formats don't cause errors."""
        # Invalid date format should be ignored (not cause 500 error)
        response = client.get("/api/logs/?date_from=invalid-date")
        
        # Should still return 200, just ignore the invalid date
        assert response.status_code == 200

    def test_limit_validation(self, client):
        """Test that limit parameter is validated correctly."""
        # Limit too high should be capped
        response = client.get("/api/logs/?limit=50000")
        
        # Should either return 422 (validation error) or cap at max
        assert response.status_code in [200, 422]
        
        # Limit too low should return validation error
        response = client.get("/api/logs/?limit=0")
        assert response.status_code == 422

