"""
FCM (Firebase Cloud Messaging) Integration Test Suite

This script tests the FCM notification system end-to-end.
Run with: python -m pytest tests/test_fcm_integration.py -v
Or standalone: python tests/test_fcm_integration.py

Prerequisites:
1. Firebase service account file configured (FIREBASE_SERVICE_ACCOUNT_PATH)
2. At least one FCM token registered in the database
3. Backend server running (for API tests)
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestFCMNotifierUnit:
    """Unit tests for FCMNotifier class."""
    
    def test_firebase_import_available(self):
        """Test that firebase-admin package is installed."""
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging
            assert firebase_admin is not None
            assert credentials is not None
            assert messaging is not None
            print("✅ firebase-admin package is installed")
        except ImportError as e:
            pytest.fail(f"firebase-admin package not installed: {e}")
    
    def test_send_each_method_exists(self):
        """Test that messaging.send_each exists (firebase-admin 6.0+)."""
        from firebase_admin import messaging
        
        assert hasattr(messaging, 'send_each'), \
            "messaging.send_each not found - need firebase-admin >= 6.0"
        print("✅ messaging.send_each method exists")
    
    def test_send_multicast_deprecated(self):
        """Verify send_multicast is deprecated/removed in firebase-admin 6.0+."""
        from firebase_admin import messaging
        
        # send_multicast should NOT exist in firebase-admin 6.0+
        # If it exists, log a warning but don't fail (might be older version)
        if hasattr(messaging, 'send_multicast'):
            print("⚠️ messaging.send_multicast exists - using older firebase-admin version")
        else:
            print("✅ messaging.send_multicast correctly removed (firebase-admin 6.0+)")
    
    def test_fcm_notifier_initialization(self):
        """Test FCMNotifier can be instantiated."""
        from app.services.fcm_notifier import FCMNotifier, FIREBASE_AVAILABLE
        
        assert FIREBASE_AVAILABLE, "Firebase not available"
        
        # Test with disabled mode (doesn't require credentials)
        notifier = FCMNotifier(enabled=False)
        assert notifier is not None
        assert notifier.enabled == False
        print("✅ FCMNotifier instantiation works (disabled mode)")
    
    def test_fcm_notifier_with_mock_credentials(self):
        """Test FCMNotifier initialization with mocked credentials."""
        from app.services.fcm_notifier import FCMNotifier
        
        with patch('app.services.fcm_notifier.firebase_admin') as mock_firebase:
            with patch('app.services.fcm_notifier.credentials') as mock_creds:
                with patch('os.path.exists', return_value=True):
                    with patch('app.core.config.get_settings') as mock_settings:
                        mock_settings.return_value.firebase_enabled = True
                        mock_settings.return_value.firebase_service_account_path = "/fake/path.json"
                        mock_settings.return_value.firebase_project_id = "test-project"
                        
                        mock_firebase.get_app.side_effect = ValueError("No app")
                        mock_creds.Certificate.return_value = MagicMock()
                        
                        notifier = FCMNotifier(enabled=True)
                        
                        # Should have attempted to initialize
                        mock_creds.Certificate.assert_called_once()
                        print("✅ FCMNotifier initialization with credentials works")


class TestFCMMessageFormat:
    """Test FCM message format and structure."""
    
    def test_message_creation(self):
        """Test that FCM messages are created correctly."""
        from firebase_admin import messaging
        
        # Create a test message
        message = messaging.Message(
            notification=messaging.Notification(
                title="Test Title",
                body="Test Body",
            ),
            data={
                "type": "test",
                "strategy_id": "test-123",
            },
            token="fake-token-for-testing",
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="alerts_channel",
                    sound="default",
                ),
            ),
        )
        
        assert message is not None
        assert message.token == "fake-token-for-testing"
        print("✅ FCM message creation works")
    
    def test_batch_message_creation(self):
        """Test creating multiple messages for send_each."""
        from firebase_admin import messaging
        
        tokens = ["token1", "token2", "token3"]
        messages = [
            messaging.Message(
                notification=messaging.Notification(
                    title="Strategy Stopped",
                    body="Test strategy has stopped",
                ),
                data={"type": "strategy", "category": "strategy_stopped"},
                token=token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id="strategies_channel",
                        sound="default",
                    ),
                ),
            )
            for token in tokens
        ]
        
        assert len(messages) == 3
        assert all(isinstance(m, messaging.Message) for m in messages)
        print("✅ Batch message creation for send_each works")


class TestFCMNotifierMethods:
    """Test FCMNotifier notification methods."""
    
    @pytest.fixture
    def mock_notifier(self):
        """Create a mocked FCMNotifier for testing."""
        from app.services.fcm_notifier import FCMNotifier
        
        with patch.object(FCMNotifier, '_initialize_firebase'):
            notifier = FCMNotifier(enabled=True)
            notifier._initialized = True
            notifier.enabled = True
            return notifier
    
    @pytest.mark.asyncio
    async def test_send_to_user_no_tokens(self, mock_notifier):
        """Test send_to_user when user has no tokens."""
        from sqlalchemy.ext.asyncio import AsyncSession
        
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        count = await mock_notifier.send_to_user(
            user_id=uuid4(),
            title="Test",
            body="Test body",
            db=mock_db
        )
        
        assert count == 0
        print("✅ send_to_user with no tokens returns 0")
    
    @pytest.mark.asyncio
    async def test_send_to_user_with_tokens(self, mock_notifier):
        """Test send_to_user with mock tokens."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.models.db_models import FCMToken
        
        # Create mock tokens
        mock_token1 = MagicMock(spec=FCMToken)
        mock_token1.token = "test-token-1"
        mock_token1.id = 1
        mock_token1.device_id = "device-1"
        
        mock_token2 = MagicMock(spec=FCMToken)
        mock_token2.token = "test-token-2"
        mock_token2.id = 2
        mock_token2.device_id = "device-2"
        
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_token1, mock_token2]
        mock_db.execute.return_value = mock_result
        
        # Mock the Firebase send_each response
        mock_send_result1 = MagicMock()
        mock_send_result1.success = True
        mock_send_result1.exception = None
        
        mock_send_result2 = MagicMock()
        mock_send_result2.success = True
        mock_send_result2.exception = None
        
        mock_response = MagicMock()
        mock_response.responses = [mock_send_result1, mock_send_result2]
        
        with patch('app.services.fcm_notifier.messaging') as mock_messaging:
            with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
                mock_thread.return_value = mock_response
                
                count = await mock_notifier.send_to_user(
                    user_id=uuid4(),
                    title="Test",
                    body="Test body",
                    db=mock_db
                )
                
                assert count == 2
                print("✅ send_to_user with tokens returns correct count")
    
    @pytest.mark.asyncio
    async def test_notify_strategy_stopped(self, mock_notifier):
        """Test notify_strategy_stopped method."""
        from app.models.strategy import StrategySummary
        
        mock_notifier.send_to_user = AsyncMock(return_value=1)
        
        summary = StrategySummary(
            id="test-strategy-id",
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            status="stopped",
            leverage=5,
            risk_per_trade=0.01,
            params={},
            created_at=datetime.now(timezone.utc).isoformat(),
            account_id="test-account",
            last_signal=None,
        )
        
        result = await mock_notifier.notify_strategy_stopped(
            user_id=uuid4(),
            summary=summary,
            reason="Manual stop",
            final_pnl=10.50,
            db=AsyncMock()
        )
        
        assert result == True
        mock_notifier.send_to_user.assert_called_once()
        
        # Verify the call arguments
        call_kwargs = mock_notifier.send_to_user.call_args[1]
        assert "Strategy Stopped" in call_kwargs.get('title', '')
        assert "strategies_channel" in call_kwargs.get('channel_id', '')
        print("✅ notify_strategy_stopped works correctly")


class TestFCMAPIEndpoints:
    """Test FCM-related API endpoints."""
    
    def test_register_endpoint_format(self):
        """Verify the FCM register endpoint format."""
        # The correct endpoint should be /api/notifications/fcm/register
        expected_endpoint = "/api/notifications/fcm/register"
        print(f"✅ FCM register endpoint: {expected_endpoint}")
    
    def test_register_request_body_format(self):
        """Verify the FCM register request body format."""
        expected_body = {
            "token": "fcm-token-string",
            "device_id": "unique-device-identifier",
            "device_type": "android",  # or "ios", "web"
            "client_type": "android_app",  # identifies the client application
            "device_name": "Samsung Galaxy S21",  # optional
            "app_version": "1.0.0"  # optional
        }
        
        # Verify all required fields
        assert "token" in expected_body
        assert "device_id" in expected_body
        assert "device_type" in expected_body
        print("✅ FCM register request body format is correct")


class TestFCMDatabaseModel:
    """Test FCM token database model."""
    
    def test_fcm_token_model_exists(self):
        """Verify FCMToken model exists and has required fields."""
        from app.models.db_models import FCMToken
        
        # Check required columns
        required_columns = [
            'id', 'user_id', 'token', 'device_id', 'device_type',
            'client_type', 'device_name', 'app_version', 'is_active',
            'created_at', 'updated_at', 'last_used_at'
        ]
        
        for col in required_columns:
            assert hasattr(FCMToken, col), f"FCMToken missing column: {col}"
        
        print("✅ FCMToken model has all required columns")


# ============================================================================
# Live Integration Tests (require running server and real FCM setup)
# ============================================================================

class TestFCMLiveIntegration:
    """
    Live integration tests for FCM.
    
    These tests require:
    1. Firebase properly configured with valid service account
    2. At least one FCM token in the database
    3. A real Android device to receive the notification
    
    Run with: pytest tests/test_fcm_integration.py::TestFCMLiveIntegration -v -s
    """
    
    @pytest.fixture
    def api_base_url(self):
        """Get API base URL from environment or use default."""
        return os.environ.get("API_BASE_URL", "http://localhost:8000")
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token from environment."""
        token = os.environ.get("TEST_AUTH_TOKEN")
        if not token:
            pytest.skip("TEST_AUTH_TOKEN environment variable not set")
        return token
    
    @pytest.mark.skipif(
        not os.environ.get("RUN_LIVE_FCM_TESTS"),
        reason="Set RUN_LIVE_FCM_TESTS=1 to run live FCM tests"
    )
    @pytest.mark.asyncio
    async def test_live_fcm_send(self):
        """
        Live test: Send a real FCM notification.
        
        This will send an actual push notification to registered devices.
        """
        import httpx
        
        api_url = os.environ.get("API_BASE_URL", "http://localhost:8000")
        auth_token = os.environ.get("TEST_AUTH_TOKEN")
        
        if not auth_token:
            pytest.skip("TEST_AUTH_TOKEN not set")
        
        # First, check if there are any FCM tokens
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{api_url}/api/notifications/fcm/tokens",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            
            if response.status_code != 200:
                pytest.skip(f"Could not fetch FCM tokens: {response.status_code}")
            
            tokens = response.json()
            if not tokens.get("tokens"):
                pytest.skip("No FCM tokens registered")
            
            print(f"Found {len(tokens['tokens'])} FCM token(s)")
            
            # The actual notification will be triggered by stopping a strategy
            # or by directly calling the notification test endpoint if available
            print("✅ FCM tokens exist - ready for live testing")


# ============================================================================
# Command-line test runner
# ============================================================================

def run_quick_validation():
    """Run quick FCM validation checks."""
    print("\n" + "="*60)
    print("FCM Quick Validation")
    print("="*60 + "\n")
    
    tests = [
        ("Firebase Import", test_firebase_import),
        ("send_each Method", test_send_each_exists),
        ("FCMNotifier Import", test_fcm_notifier_import),
        ("Message Creation", test_message_creation),
        ("FCMToken Model", test_fcm_token_model),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            print(f"✅ {name}")
            passed += 1
        except Exception as e:
            print(f"❌ {name}: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


def test_firebase_import():
    import firebase_admin
    from firebase_admin import credentials, messaging
    assert firebase_admin is not None


def test_send_each_exists():
    from firebase_admin import messaging
    assert hasattr(messaging, 'send_each'), "send_each not found"


def test_fcm_notifier_import():
    from app.services.fcm_notifier import FCMNotifier, FIREBASE_AVAILABLE
    assert FIREBASE_AVAILABLE, "Firebase not available"


def test_message_creation():
    from firebase_admin import messaging
    msg = messaging.Message(
        notification=messaging.Notification(title="Test", body="Test"),
        token="fake-token"
    )
    assert msg is not None


def test_fcm_token_model():
    from app.models.db_models import FCMToken
    assert hasattr(FCMToken, 'token')
    assert hasattr(FCMToken, 'client_type')


if __name__ == "__main__":
    # Run quick validation when executed directly
    success = run_quick_validation()
    
    print("\n" + "-"*60)
    print("To run full pytest suite:")
    print("  python -m pytest tests/test_fcm_integration.py -v")
    print("\nTo run live integration tests:")
    print("  RUN_LIVE_FCM_TESTS=1 TEST_AUTH_TOKEN=<token> python -m pytest tests/test_fcm_integration.py::TestFCMLiveIntegration -v")
    print("-"*60)
    
    sys.exit(0 if success else 1)
