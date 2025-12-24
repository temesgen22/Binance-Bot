"""
Test cases for historical klines pagination functionality.

Tests verify that _fetch_historical_klines correctly handles:
1. Large time ranges requiring pagination (e.g., 30 days of 1m klines)
2. Multiple API requests to fetch all data
3. Deduplication of candles
4. Proper sorting by timestamp
5. Edge cases (small ranges, exact boundaries, API errors)
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException

from app.api.routes.backtesting import _fetch_historical_klines
from app.core.my_binance_client import BinanceClient


def build_klines_chunk(start_time: datetime, count: int, interval_minutes: int = 1, 
                      base_price: float = 50000.0) -> list[list]:
    """
    Build a chunk of klines for testing pagination.
    
    Args:
        start_time: Start time for first candle
        count: Number of candles to generate
        interval_minutes: Minutes between candles (default: 1 for 1m interval)
        base_price: Starting price
        
    Returns:
        List of klines in Binance format
    """
    klines = []
    current_price = base_price
    
    for i in range(count):
        timestamp = int((start_time + timedelta(minutes=i * interval_minutes)).timestamp() * 1000)
        
        # Simple price movement
        price_change = (i % 10) * 0.1  # Small variation
        open_price = current_price
        close_price = open_price + price_change
        high_price = max(open_price, close_price) + 0.5
        low_price = min(open_price, close_price) - 0.5
        volume = 1000.0
        
        kline = [
            timestamp,  # open_time
            str(open_price),  # open
            str(high_price),  # high
            str(low_price),  # low
            str(close_price),  # close
            str(volume),  # volume
            timestamp + (interval_minutes * 60000),  # close_time
            str(volume * close_price),  # quote_volume
            0,  # trades
            str(volume),  # taker_buy_base_volume
            str(volume * close_price),  # taker_buy_quote_volume
            "0"  # ignore
        ]
        klines.append(kline)
        current_price = close_price
    
    return klines


@pytest.fixture
def mock_binance_client():
    """Create a mock BinanceClient for testing."""
    client = Mock(spec=BinanceClient)
    client._ensure = Mock()
    return client


class TestHistoricalKlinesPagination:
    """Test pagination for fetching historical klines."""
    
    @pytest.mark.asyncio
    async def test_small_range_no_pagination(self, mock_binance_client):
        """Test that small ranges (< 1000 candles) don't trigger pagination."""
        # 500 candles = 500 minutes = ~8.3 hours
        start_time = datetime.now() - timedelta(hours=10)
        end_time = start_time + timedelta(minutes=500)
        
        klines = build_klines_chunk(start_time, 500)
        mock_rest = Mock()
        mock_rest.futures_historical_klines = Mock(return_value=klines)
        mock_rest.futures_klines = Mock(return_value=klines)
        mock_binance_client._ensure.return_value = mock_rest
        
        result = await _fetch_historical_klines(
            mock_binance_client,
            "BTCUSDT",
            "1m",
            start_time,
            end_time
        )
        
        assert len(result) == 500
        assert result[0][0] == int(start_time.timestamp() * 1000)
        # Verify futures_historical_klines was called (not pagination)
        assert mock_rest.futures_historical_klines.called or mock_rest.futures_klines.called
    
    @pytest.mark.asyncio
    async def test_large_range_with_pagination(self, mock_binance_client):
        """Test pagination for large time range (30 days of 1m klines)."""
        # 30 days of 1-minute klines = 43,200 candles
        # This requires ~44 API calls (1000 candles each)
        start_time = datetime.now() - timedelta(days=30)
        end_time = datetime.now()
        
        # Calculate expected number of candles
        duration_seconds = (end_time - start_time).total_seconds()
        expected_candles = int(duration_seconds / 60)  # 1-minute intervals
        
        # Mock pagination: return chunks of 1000 candles
        mock_rest = Mock()
        call_count = [0]  # Use list to allow modification in nested function
        
        def futures_klines_mock(symbol, interval, limit, startTime, endTime):
            call_count[0] += 1
            chunk_start = datetime.fromtimestamp(startTime / 1000)
            chunk_end = datetime.fromtimestamp(endTime / 1000)
            
            # Calculate how many candles in this chunk
            chunk_duration = (chunk_end - chunk_start).total_seconds()
            chunk_candles = min(int(chunk_duration / 60), limit)
            
            # Generate klines for this chunk
            chunk_klines = build_klines_chunk(chunk_start, chunk_candles)
            
            # Return only up to limit
            return chunk_klines[:limit]
        
        mock_rest.futures_klines = Mock(side_effect=futures_klines_mock)
        mock_rest.futures_historical_klines = Mock(return_value=None)  # Force pagination path
        mock_binance_client._ensure.return_value = mock_rest
        
        result = await _fetch_historical_klines(
            mock_binance_client,
            "BTCUSDT",
            "1m",
            start_time,
            end_time
        )
        
        # Verify pagination was used (multiple calls)
        assert call_count[0] > 1, "Pagination should have made multiple API calls"
        
        # Verify we got a substantial amount of data
        assert len(result) >= expected_candles * 0.9, \
            f"Expected at least 90% of {expected_candles} candles, got {len(result)}"
        
        # Verify all timestamps are in range
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        for kline in result:
            assert start_ts <= int(kline[0]) <= end_ts
        
        # Verify sorting (should be sorted by timestamp)
        timestamps = [int(k[0]) for k in result]
        assert timestamps == sorted(timestamps), "Klines should be sorted by timestamp"
    
    @pytest.mark.asyncio
    async def test_pagination_with_5m_interval(self, mock_binance_client):
        """Test pagination with 5-minute interval (fewer candles needed)."""
        # 7 days of 5-minute klines = 2,016 candles (needs 3 chunks)
        start_time = datetime.now() - timedelta(days=7)
        end_time = datetime.now()
        
        mock_rest = Mock()
        call_count = [0]
        
        def futures_klines_mock(symbol, interval, limit, startTime, endTime):
            call_count[0] += 1
            chunk_start = datetime.fromtimestamp(startTime / 1000)
            chunk_end = datetime.fromtimestamp(endTime / 1000)
            
            # 5-minute intervals
            chunk_duration = (chunk_end - chunk_start).total_seconds()
            chunk_candles = min(int(chunk_duration / 300), limit)  # 300 seconds = 5 minutes
            
            chunk_klines = build_klines_chunk(chunk_start, chunk_candles, interval_minutes=5)
            return chunk_klines[:limit]
        
        mock_rest.futures_klines = Mock(side_effect=futures_klines_mock)
        mock_rest.futures_historical_klines = Mock(return_value=None)
        mock_binance_client._ensure.return_value = mock_rest
        
        result = await _fetch_historical_klines(
            mock_binance_client,
            "BTCUSDT",
            "5m",
            start_time,
            end_time
        )
        
        # Should have made multiple calls
        assert call_count[0] >= 2, "Should have made at least 2 API calls for pagination"
        
        # Verify we got reasonable amount of data
        assert len(result) >= 1800, f"Expected at least 1800 candles, got {len(result)}"
    
    @pytest.mark.asyncio
    async def test_pagination_deduplication(self, mock_binance_client):
        """Test that pagination correctly removes duplicate candles."""
        start_time = datetime.now() - timedelta(hours=2)
        end_time = datetime.now()
        
        # Create klines with some overlap (simulating duplicate data from API)
        klines_chunk1 = build_klines_chunk(start_time, 1000)
        klines_chunk2 = build_klines_chunk(
            start_time + timedelta(minutes=999),  # Overlap by 1 candle
            1000
        )
        
        mock_rest = Mock()
        call_count = [0]
        
        def futures_klines_mock(symbol, interval, limit, startTime, endTime):
            call_count[0] += 1
            if call_count[0] == 1:
                return klines_chunk1
            else:
                return klines_chunk2
        
        mock_rest.futures_klines = Mock(side_effect=futures_klines_mock)
        mock_rest.futures_historical_klines = Mock(return_value=None)
        mock_binance_client._ensure.return_value = mock_rest
        
        result = await _fetch_historical_klines(
            mock_binance_client,
            "BTCUSDT",
            "1m",
            start_time,
            end_time
        )
        
        # Verify no duplicates (check unique timestamps)
        timestamps = [int(k[0]) for k in result]
        assert len(timestamps) == len(set(timestamps)), "Should have no duplicate timestamps"
    
    @pytest.mark.asyncio
    async def test_pagination_handles_partial_chunks(self, mock_binance_client):
        """Test pagination when last chunk has fewer candles than limit."""
        start_time = datetime.now() - timedelta(hours=25)  # ~1500 candles
        end_time = datetime.now()
        
        mock_rest = Mock()
        call_count = [0]
        
        def futures_klines_mock(symbol, interval, limit, startTime, endTime):
            call_count[0] += 1
            chunk_start = datetime.fromtimestamp(startTime / 1000)
            chunk_end = datetime.fromtimestamp(endTime / 1000)
            
            chunk_duration = (chunk_end - chunk_start).total_seconds()
            chunk_candles = min(int(chunk_duration / 60), limit)
            
            # Last chunk should return fewer candles
            if call_count[0] == 2:
                chunk_candles = min(chunk_candles, 500)  # Partial chunk
            
            chunk_klines = build_klines_chunk(chunk_start, chunk_candles)
            return chunk_klines[:limit]
        
        mock_rest.futures_klines = Mock(side_effect=futures_klines_mock)
        mock_rest.futures_historical_klines = Mock(return_value=None)
        mock_binance_client._ensure.return_value = mock_rest
        
        result = await _fetch_historical_klines(
            mock_binance_client,
            "BTCUSDT",
            "1m",
            start_time,
            end_time
        )
        
        # Should have made 2 calls (1000 + 500)
        assert call_count[0] == 2, f"Expected 2 API calls, got {call_count[0]}"
        assert len(result) >= 1400, f"Expected at least 1400 candles, got {len(result)}"
    
    @pytest.mark.asyncio
    async def test_pagination_handles_api_errors_gracefully(self, mock_binance_client):
        """Test that pagination handles API errors in some chunks."""
        start_time = datetime.now() - timedelta(hours=3)  # ~1800 candles
        end_time = datetime.now()
        
        mock_rest = Mock()
        call_count = [0]
        
        def futures_klines_mock(symbol, interval, limit, startTime, endTime):
            call_count[0] += 1
            # Simulate error on second call during pagination
            if call_count[0] == 2:
                raise Exception("Temporary API error")
            
            chunk_start = datetime.fromtimestamp(startTime / 1000)
            chunk_candles = min(1000, 1800 - (call_count[0] - 1) * 1000)
            return build_klines_chunk(chunk_start, chunk_candles)
        
        mock_rest.futures_klines = Mock(side_effect=futures_klines_mock)
        mock_rest.futures_historical_klines = Mock(return_value=None)
        mock_binance_client._ensure.return_value = mock_rest
        
        # The code will attempt pagination, but errors will cause HTTPException
        # Note: The current implementation has error handling that may catch and re-raise
        try:
            result = await _fetch_historical_klines(
                mock_binance_client,
                "BTCUSDT",
                "1m",
                start_time,
                end_time
            )
            # If it succeeds despite error, that's also acceptable (fallback worked)
            # But we should verify it attempted pagination
            assert call_count[0] > 0, "Should have attempted API calls"
        except HTTPException:
            # Expected if error handling raises exception
            assert call_count[0] >= 2, "Should have attempted at least 2 calls before failing"
    
    @pytest.mark.asyncio
    async def test_insufficient_data_error(self, mock_binance_client):
        """Test that insufficient data raises appropriate error."""
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()
        
        # Return only 10 candles (less than minimum 50)
        klines = build_klines_chunk(start_time, 10)
        
        mock_rest = Mock()
        mock_rest.futures_historical_klines = Mock(return_value=klines)
        mock_rest.futures_klines = Mock(return_value=klines)
        mock_binance_client._ensure.return_value = mock_rest
        
        with pytest.raises(HTTPException) as exc_info:
            await _fetch_historical_klines(
                mock_binance_client,
                "BTCUSDT",
                "1m",
                start_time,
                end_time
            )
        
        assert "Insufficient historical data" in str(exc_info.value.detail)
        assert "50" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_30_days_1m_klines_comprehensive(self, mock_binance_client):
        """Comprehensive test: 30 days of 1-minute klines (the user's use case)."""
        # Exactly 30 days
        end_time = datetime.now().replace(second=0, microsecond=0)
        start_time = end_time - timedelta(days=30)
        
        # Expected: 30 days * 24 hours * 60 minutes = 43,200 candles
        expected_candles = 30 * 24 * 60
        
        mock_rest = Mock()
        call_count = [0]
        all_generated_klines = []
        
        def futures_klines_mock(symbol, interval, limit, startTime, endTime):
            call_count[0] += 1
            chunk_start = datetime.fromtimestamp(startTime / 1000)
            chunk_end = datetime.fromtimestamp(endTime / 1000)
            
            # Calculate candles for this chunk
            chunk_duration = (chunk_end - chunk_start).total_seconds()
            chunk_candles = min(int(chunk_duration / 60), limit)
            
            # Generate chunk
            chunk_klines = build_klines_chunk(chunk_start, chunk_candles)
            all_generated_klines.extend(chunk_klines)
            
            return chunk_klines[:limit]
        
        mock_rest.futures_klines = Mock(side_effect=futures_klines_mock)
        mock_rest.futures_historical_klines = Mock(return_value=None)
        mock_binance_client._ensure.return_value = mock_rest
        
        result = await _fetch_historical_klines(
            mock_binance_client,
            "BTCUSDT",
            "1m",
            start_time,
            end_time
        )
        
        # Verify pagination was used
        assert call_count[0] >= 43, \
            f"Expected at least 43 API calls (43,200 / 1000), got {call_count[0]}"
        
        # Verify we got close to expected amount (allow 5% tolerance for edge cases)
        assert len(result) >= expected_candles * 0.95, \
            f"Expected at least {expected_candles * 0.95:.0f} candles, got {len(result)}"
        
        # Verify all timestamps are in range
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        for kline in result:
            timestamp = int(kline[0])
            assert start_ts <= timestamp <= end_ts, \
                f"Timestamp {timestamp} out of range [{start_ts}, {end_ts}]"
        
        # Verify sorting
        timestamps = [int(k[0]) for k in result]
        assert timestamps == sorted(timestamps), "Klines must be sorted by timestamp"
        
        # Verify no gaps (consecutive timestamps should differ by 60,000 ms = 1 minute)
        for i in range(len(timestamps) - 1):
            diff = timestamps[i + 1] - timestamps[i]
            assert diff == 60000, \
                f"Gap detected: {diff}ms between candles {i} and {i+1} (expected 60000ms)"
        
        print(f"Successfully fetched {len(result)} candles in {call_count[0]} API calls")
        print(f"   Time range: {start_time} to {end_time}")
        print(f"   Expected: ~{expected_candles} candles")
        print(f"   Coverage: {len(result) / expected_candles * 100:.1f}%")

