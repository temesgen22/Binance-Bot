"""
Tests for TradeFrequencyLimiter - Phase 3 Week 6: Trade Frequency Limits
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.risk.trade_frequency_limiter import (
    TradeFrequencyLimiter,
    TradeFrequencyLimit,
    TradeFrequencyStatus,
)


@pytest.fixture
def frequency_limiter():
    """Create a TradeFrequencyLimiter with test limits."""
    account_limits = TradeFrequencyLimit(
        max_trades_per_minute=10,
        max_trades_per_hour=100,
        max_trades_per_day=500,
        max_trades_per_week=2000
    )
    
    strategy_limits = TradeFrequencyLimit(
        max_trades_per_minute=5,
        max_trades_per_hour=50,
        max_trades_per_day=200,
        max_trades_per_week=1000
    )
    
    return TradeFrequencyLimiter(
        account_limits=account_limits,
        strategy_limits=strategy_limits
    )


class TestTradeFrequencyLimiter:
    """Tests for TradeFrequencyLimiter."""
    
    def test_record_trade(self, frequency_limiter):
        """Test recording a trade."""
        account_id = "test_account"
        strategy_id = "test_strategy"
        
        frequency_limiter.record_trade(account_id, strategy_id)
        
        assert account_id in frequency_limiter._trade_timestamps
        assert strategy_id in frequency_limiter._trade_timestamps[account_id]
        assert len(frequency_limiter._trade_timestamps[account_id][strategy_id]) == 1
    
    def test_check_trade_allowed_under_limit(self, frequency_limiter):
        """Test trade allowed when under limit."""
        account_id = "test_account"
        strategy_id = "test_strategy"
        
        # Record a few trades (under limit)
        for i in range(3):
            frequency_limiter.record_trade(
                account_id,
                strategy_id,
                datetime.now(timezone.utc) - timedelta(seconds=i * 10)
            )
        
        allowed, reason = frequency_limiter.check_trade_allowed(account_id, strategy_id)
        
        assert allowed is True
        assert reason is None
    
    def test_check_trade_allowed_exceeds_minute_limit(self, frequency_limiter):
        """Test trade blocked when exceeds minute limit."""
        account_id = "test_account"
        strategy_id = "test_strategy"
        
        # Record trades within last minute (exceeds strategy limit of 5)
        now = datetime.now(timezone.utc)
        for i in range(6):  # 6 trades > 5 limit
            frequency_limiter.record_trade(
                account_id,
                strategy_id,
                now - timedelta(seconds=i * 5)
            )
        
        allowed, reason = frequency_limiter.check_trade_allowed(account_id, strategy_id)
        
        assert allowed is False
        assert reason is not None
        assert "minute" in reason.lower()
    
    def test_check_trade_allowed_exceeds_hour_limit(self, frequency_limiter):
        """Test trade blocked when exceeds hour limit."""
        account_id = "test_account"
        strategy_id = "test_strategy"
        
        # Record trades within last hour (exceeds strategy limit of 50)
        now = datetime.now(timezone.utc)
        for i in range(51):  # 51 trades > 50 limit
            frequency_limiter.record_trade(
                account_id,
                strategy_id,
                now - timedelta(minutes=i)
            )
        
        allowed, reason = frequency_limiter.check_trade_allowed(account_id, strategy_id)
        
        assert allowed is False
        assert reason is not None
        assert "hour" in reason.lower()
    
    def test_get_frequency_status(self, frequency_limiter):
        """Test getting frequency status."""
        account_id = "test_account"
        strategy_id = "test_strategy"
        
        # Record some trades
        now = datetime.now(timezone.utc)
        for i in range(5):
            frequency_limiter.record_trade(
                account_id,
                strategy_id,
                now - timedelta(minutes=i)
            )
        
        status = frequency_limiter.get_frequency_status(account_id, strategy_id)
        
        assert status.account_id == account_id
        assert status.strategy_id == strategy_id
        assert status.trades_last_minute >= 0
        assert status.trades_last_hour >= 0
        assert status.trades_last_day >= 0
        assert status.trades_last_week >= 0
    
    def test_cleanup_old_entries(self, frequency_limiter):
        """Test cleanup of old entries."""
        account_id = "test_account"
        strategy_id = "test_strategy"
        
        # Record old trades (more than 2 weeks ago)
        old_time = datetime.now(timezone.utc) - timedelta(weeks=3)
        frequency_limiter.record_trade(account_id, strategy_id, old_time)
        
        # Record recent trade
        recent_time = datetime.now(timezone.utc)
        frequency_limiter.record_trade(account_id, strategy_id, recent_time)
        
        # Cleanup
        frequency_limiter._cleanup_old_entries()
        
        # Old trade should be removed, recent should remain
        trades = frequency_limiter._trade_timestamps[account_id][strategy_id]
        assert len(trades) == 1
        assert trades[0] == recent_time
    
    def test_account_level_limits(self, frequency_limiter):
        """Test account-level limits are enforced."""
        account_id = "test_account"
        strategy_id1 = "strategy_1"
        strategy_id2 = "strategy_2"
        
        # Record trades from multiple strategies (exceeds account minute limit of 10)
        now = datetime.now(timezone.utc)
        for i in range(6):
            frequency_limiter.record_trade(account_id, strategy_id1, now - timedelta(seconds=i * 5))
        for i in range(6):
            frequency_limiter.record_trade(account_id, strategy_id2, now - timedelta(seconds=i * 5))
        
        # Total: 12 trades > 10 account limit
        allowed, reason = frequency_limiter.check_trade_allowed(account_id, strategy_id1)
        
        assert allowed is False
        assert reason is not None
        assert "account" in reason.lower()


class TestTradeFrequencyLimit:
    """Tests for TradeFrequencyLimit."""
    
    def test_trade_frequency_limit_creation(self):
        """Test creating a TradeFrequencyLimit."""
        limit = TradeFrequencyLimit(
            max_trades_per_minute=10,
            max_trades_per_hour=100,
            max_trades_per_day=500,
            max_trades_per_week=2000
        )
        
        assert limit.max_trades_per_minute == 10
        assert limit.max_trades_per_hour == 100
        assert limit.max_trades_per_day == 500
        assert limit.max_trades_per_week == 2000
    
    def test_trade_frequency_limit_partial(self):
        """Test creating a TradeFrequencyLimit with partial limits."""
        limit = TradeFrequencyLimit(
            max_trades_per_hour=50,
            max_trades_per_day=200
        )
        
        assert limit.max_trades_per_minute is None
        assert limit.max_trades_per_hour == 50
        assert limit.max_trades_per_day == 200
        assert limit.max_trades_per_week is None










