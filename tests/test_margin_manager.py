"""
Tests for MarginManager - Phase 3 Week 6: Margin Protection
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone

from app.risk.margin_manager import MarginManager, MarginStatus
from app.core.my_binance_client import BinanceClient


@pytest.fixture
def mock_client():
    """Create a mock BinanceClient."""
    client = MagicMock()
    # Set up futures_account_balance
    client.futures_account_balance.return_value = 10000.0
    # Set up futures_account method
    client.futures_account = MagicMock(return_value={
        'totalWalletBalance': '10000.0',
        'availableBalance': '5000.0',
        'totalMaintMargin': '1000.0'
    })
    return client


@pytest.fixture
def margin_manager(mock_client):
    """Create a MarginManager instance."""
    return MarginManager(
        client=mock_client,
        warning_threshold=0.6,
        danger_threshold=0.75,
        critical_threshold=0.85,
        auto_reduce_enabled=True,
        min_available_balance_pct=0.15
    )


class TestMarginManager:
    """Tests for MarginManager."""
    
    def test_get_margin_status(self, margin_manager, mock_client):
        """Test getting margin status."""
        status = margin_manager.get_margin_status("test_account")
        
        assert status is not None
        assert status.account_id == "test_account"
        assert status.total_balance == 10000.0
        assert status.available_balance == 5000.0
        assert status.used_margin == 5000.0
        assert status.margin_ratio == 0.5  # 50%
        assert status.status == "safe"
    
    def test_get_margin_status_warning(self, margin_manager, mock_client):
        """Test margin status in warning zone."""
        # Set available balance to trigger warning (60% used)
        mock_client.futures_account.return_value = {
            'totalWalletBalance': '10000.0',
            'availableBalance': '4000.0',  # 60% used
            'totalMaintMargin': '1000.0'
        }
        
        status = margin_manager.get_margin_status("test_account")
        
        assert status is not None
        assert status.margin_ratio == 0.6
        assert status.status == "warning"
    
    def test_get_margin_status_danger(self, margin_manager, mock_client):
        """Test margin status in danger zone."""
        # Set available balance to trigger danger (75% used)
        mock_client.futures_account = MagicMock(return_value={
            'totalWalletBalance': '10000.0',
            'availableBalance': '2500.0',  # 75% used
            'totalMaintMargin': '1000.0'
        })
        
        status = margin_manager.get_margin_status("test_account")
        
        assert status is not None
        assert status.margin_ratio == 0.75
        assert status.status == "danger"
    
    def test_get_margin_status_critical(self, margin_manager, mock_client):
        """Test margin status in critical zone."""
        # Set available balance to trigger critical (85% used)
        mock_client.futures_account = MagicMock(return_value={
            'totalWalletBalance': '10000.0',
            'availableBalance': '1500.0',  # 85% used
            'totalMaintMargin': '1000.0'
        })
        
        status = margin_manager.get_margin_status("test_account")
        
        assert status is not None
        assert status.margin_ratio == 0.85
        assert status.status == "critical"
    
    def test_check_margin_available_sufficient(self, margin_manager, mock_client):
        """Test margin check with sufficient margin."""
        allowed, reason, status = margin_manager.check_margin_available(
            "test_account",
            required_margin=1000.0
        )
        
        assert allowed is True
        assert reason is None
        assert status is not None
    
    def test_check_margin_available_insufficient(self, margin_manager, mock_client):
        """Test margin check with insufficient margin."""
        # Set low available balance
        mock_client.futures_account = MagicMock(return_value={
            'totalWalletBalance': '10000.0',
            'availableBalance': '500.0',  # Low available
            'totalMaintMargin': '1000.0'
        })
        
        allowed, reason, status = margin_manager.check_margin_available(
            "test_account",
            required_margin=1000.0  # More than available
        )
        
        assert allowed is False
        assert reason is not None
        assert "Insufficient margin" in reason
    
    def test_check_margin_available_breaches_threshold(self, margin_manager, mock_client):
        """Test margin check that would breach critical threshold."""
        # Set available balance so adding required would breach critical
        mock_client.futures_account = MagicMock(return_value={
            'totalWalletBalance': '10000.0',
            'availableBalance': '2000.0',  # 80% used
            'totalMaintMargin': '1000.0'
        })
        
        allowed, reason, status = margin_manager.check_margin_available(
            "test_account",
            required_margin=1000.0  # Would push to 90% (above 85% critical)
        )
        
        assert allowed is False
        assert reason is not None
        assert "critical" in reason.lower()
    
    def test_should_reduce_positions_critical(self, margin_manager, mock_client):
        """Test should_reduce_positions when critical."""
        # Set critical margin status
        mock_client.futures_account = MagicMock(return_value={
            'totalWalletBalance': '10000.0',
            'availableBalance': '1000.0',  # 90% used (critical)
            'totalMaintMargin': '1000.0'
        })
        
        should_reduce, reason, status = margin_manager.should_reduce_positions("test_account")
        
        assert should_reduce is True
        assert reason is not None
        assert "critical" in reason.lower()
    
    def test_should_reduce_positions_danger(self, margin_manager, mock_client):
        """Test should_reduce_positions when in danger."""
        # Set danger margin status
        mock_client.futures_account = MagicMock(return_value={
            'totalWalletBalance': '10000.0',
            'availableBalance': '2500.0',  # 75% used (danger)
            'totalMaintMargin': '1000.0'
        })
        
        should_reduce, reason, status = margin_manager.should_reduce_positions("test_account")
        
        assert should_reduce is True
        assert reason is not None
        assert "danger" in reason.lower()
    
    def test_should_reduce_positions_safe(self, margin_manager, mock_client):
        """Test should_reduce_positions when safe."""
        # Set safe margin status
        mock_client.futures_account = MagicMock(return_value={
            'totalWalletBalance': '10000.0',
            'availableBalance': '6000.0',  # 40% used (safe)
            'totalMaintMargin': '1000.0'
        })
        
        should_reduce, reason, status = margin_manager.should_reduce_positions("test_account")
        
        assert should_reduce is False
        assert reason is None
    
    def test_calculate_max_allowed_exposure(self, margin_manager, mock_client):
        """Test calculating max allowed exposure."""
        # Set margin status
        mock_client.futures_account = MagicMock(return_value={
            'totalWalletBalance': '10000.0',
            'availableBalance': '5000.0',  # 50% used
            'totalMaintMargin': '1000.0'
        })
        
        max_exposure = margin_manager.calculate_max_allowed_exposure(
            "test_account",
            current_exposure=5000.0
        )
        
        assert max_exposure > 0
        assert max_exposure <= 10000.0  # Can't exceed total balance


class TestMarginStatus:
    """Tests for MarginStatus."""
    
    def test_margin_status_creation(self):
        """Test creating a MarginStatus."""
        status = MarginStatus(
            account_id="test_account",
            total_balance=10000.0,
            available_balance=5000.0,
            used_margin=5000.0,
            margin_ratio=0.5,
            maintenance_margin=1000.0,
            margin_call_ratio=0.8,
            liquidation_ratio=1.0,
            status="safe",
            timestamp=datetime.now(timezone.utc)
        )
        
        assert status.account_id == "test_account"
        assert status.total_balance == 10000.0
        assert status.margin_ratio == 0.5
        assert status.status == "safe"

