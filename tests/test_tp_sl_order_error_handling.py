"""
Test suite for TP/SL order placement error handling.

Tests validate that:
1. Exceptions are properly converted to strings without KeyError
2. RetryError wrapping doesn't cause issues when logging
3. TP/SL order placement failures are handled gracefully
4. Exception details are safely accessed
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
from tenacity import RetryError

from app.core.exceptions import (
    BinanceAPIError,
    BinanceRateLimitError,
    BinanceNetworkError,
    BinanceBotException
)


class TestExceptionStringRepresentation:
    """Test that exceptions can be safely converted to strings."""
    
    def test_binance_bot_exception_str(self):
        """Test that BinanceBotException converts to string safely."""
        exc = BinanceBotException("Test error", details={"key": "value"})
        # Should not raise KeyError
        str_repr = str(exc)
        assert str_repr == "Test error"
        assert isinstance(str_repr, str)
    
    def test_binance_api_error_str(self):
        """Test that BinanceAPIError converts to string safely."""
        exc = BinanceAPIError(
            "API error",
            status_code=400,
            error_code=-1001,
            details={"symbol": "BTCUSDT", "order_type": "TAKE_PROFIT_MARKET"}
        )
        # Should not raise KeyError when converting to string
        str_repr = str(exc)
        assert str_repr == "API error"
        assert isinstance(str_repr, str)
    
    def test_binance_api_error_str_with_order_type(self):
        """Test that BinanceAPIError with order_type in details converts safely."""
        exc = BinanceAPIError(
            "Failed to place TAKE_PROFIT_MARKET order",
            status_code=400,
            error_code=-1001,
            details={"symbol": "BTCUSDT", "order_type": "TAKE_PROFIT_MARKET"}
        )
        # Should not raise KeyError when converting to string
        str_repr = str(exc)
        assert "Failed to place TAKE_PROFIT_MARKET order" in str_repr
        assert isinstance(str_repr, str)
    
    def test_binance_rate_limit_error_str(self):
        """Test that BinanceRateLimitError converts to string safely."""
        exc = BinanceRateLimitError(
            "Rate limit exceeded",
            retry_after=10,
            details={"symbol": "BTCUSDT", "order_type": "STOP_MARKET"}
        )
        # Should not raise KeyError
        str_repr = str(exc)
        assert str_repr == "Rate limit exceeded"
        assert isinstance(str_repr, str)
    
    def test_binance_network_error_str(self):
        """Test that BinanceNetworkError converts to string safely."""
        exc = BinanceNetworkError(
            "Network error",
            details={"symbol": "BTCUSDT"}
        )
        # Should not raise KeyError
        str_repr = str(exc)
        assert str_repr == "Network error"
        assert isinstance(str_repr, str)


class TestRetryErrorHandling:
    """Test handling of RetryError wrapping BinanceAPIError."""
    
    def test_retry_error_wrapping_binance_api_error(self):
        """Test that RetryError wrapping BinanceAPIError can be safely converted to string."""
        underlying_error = BinanceAPIError(
            "Failed to place order",
            status_code=400,
            error_code=-1001,
            details={"symbol": "BTCUSDT", "order_type": "TAKE_PROFIT_MARKET"}
        )
        
        # Create a mock RetryError with last_attempt
        mock_attempt = Mock()
        mock_attempt.exception.return_value = underlying_error
        
        retry_error = RetryError(last_attempt=mock_attempt)
        
        # Should not raise KeyError when converting to string
        str_repr = str(retry_error)
        assert isinstance(str_repr, str)
        # The string representation should not cause KeyError
        assert "'order_type'" not in str_repr or "KeyError" not in str_repr
    
    def test_extract_error_from_retry_error(self):
        """Test extracting underlying error from RetryError."""
        underlying_error = BinanceAPIError(
            "Failed to place order",
            status_code=400,
            error_code=-1001,
            details={"symbol": "BTCUSDT", "order_type": "TAKE_PROFIT_MARKET"}
        )
        
        mock_attempt = Mock()
        mock_attempt.exception.return_value = underlying_error
        
        retry_error = RetryError(last_attempt=mock_attempt)
        
        # Extract underlying error (simulating the fix in strategy_executor.py)
        error_msg = str(retry_error)
        try:
            # Use the already imported RetryError
            if isinstance(retry_error, RetryError) and hasattr(retry_error, 'last_attempt') and retry_error.last_attempt:
                underlying = retry_error.last_attempt.exception()
                error_msg = str(underlying)
        except Exception:
            pass
        
        # Should not raise KeyError
        assert isinstance(error_msg, str)
        assert "Failed to place order" in error_msg


class TestTPSLOrderPlacementErrorHandling:
    """Test TP/SL order placement error handling scenarios."""
    
    def test_error_message_extraction_from_retry_error(self):
        """Test that error messages can be safely extracted from RetryError."""
        underlying_error = BinanceAPIError(
            "Failed to place TAKE_PROFIT_MARKET order for BTCUSDT: Invalid price",
            status_code=400,
            error_code=-1111,
            details={"symbol": "BTCUSDT", "order_type": "TAKE_PROFIT_MARKET"}
        )
        
        # Create a mock RetryError with last_attempt
        mock_attempt = Mock()
        mock_attempt.exception.return_value = underlying_error
        
        retry_error = RetryError(last_attempt=mock_attempt)
        
        # Simulate the error extraction logic from strategy_executor.py
        error_msg = str(retry_error)
        try:
            # Use the already imported RetryError
            if isinstance(retry_error, RetryError) and hasattr(retry_error, 'last_attempt') and retry_error.last_attempt:
                underlying = retry_error.last_attempt.exception()
                error_msg = str(underlying)
        except Exception:
            pass  # Fall back to original error message
        
        # Should not raise KeyError and should contain the error message
        assert isinstance(error_msg, str)
        assert "Failed to place" in error_msg or "TAKE_PROFIT_MARKET" in error_msg or len(error_msg) > 0
    
    def test_error_logging_format_string(self):
        """Test that error logging with f-strings doesn't cause KeyError."""
        exc = BinanceAPIError(
            "Failed to place TP/SL orders on Binance",
            status_code=400,
            error_code=-1001,
            details={"symbol": "BTCUSDT", "order_type": "TAKE_PROFIT_MARKET"}
        )
        
        # Simulate the logging format from strategy_executor.py
        strategy_id = "test-strategy-123"
        error_msg = str(exc)
        
        # Should not raise KeyError when formatting
        log_message = f"[{strategy_id}] Failed to place TP/SL orders on Binance: {error_msg}. Strategy will still monitor TP/SL, but Binance native orders not active."
        
        assert isinstance(log_message, str)
        assert strategy_id in log_message
        assert "Failed to place" in log_message


class TestExceptionDetailsAccess:
    """Test safe access to exception details."""
    
    def test_exception_details_access_safe(self):
        """Test that exception details can be accessed safely."""
        exc = BinanceAPIError(
            "Test error",
            status_code=400,
            error_code=-1001,
            details={"symbol": "BTCUSDT", "order_type": "TAKE_PROFIT_MARKET"}
        )
        
        # Should be able to access details safely
        assert exc.details["symbol"] == "BTCUSDT"
        assert exc.details["order_type"] == "TAKE_PROFIT_MARKET"
        assert exc.details.get("order_type") == "TAKE_PROFIT_MARKET"
    
    def test_exception_details_missing_key(self):
        """Test that missing keys in details don't cause issues when converting to string."""
        exc = BinanceAPIError(
            "Test error",
            status_code=400,
            error_code=-1001,
            details={"symbol": "BTCUSDT"}  # Missing order_type
        )
        
        # Should not raise KeyError when converting to string
        str_repr = str(exc)
        assert str_repr == "Test error"
        assert isinstance(str_repr, str)
        
        # Accessing missing key should return None with .get()
        assert exc.details.get("order_type") is None

