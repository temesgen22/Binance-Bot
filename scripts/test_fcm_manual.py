#!/usr/bin/env python3
"""
Manual FCM Test Script

This script tests FCM notifications directly without needing pytest.
Run on the server: python scripts/test_fcm_manual.py

Tests:
1. Firebase SDK initialization
2. FCM token lookup in database
3. Sending a test notification
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def print_result(success: bool, message: str):
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")


async def test_firebase_sdk():
    """Test 1: Firebase SDK availability and initialization."""
    print_header("Test 1: Firebase SDK")
    
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        print_result(True, "firebase-admin package imported")
    except ImportError as e:
        print_result(False, f"firebase-admin not installed: {e}")
        return False
    
    # Check send_each method exists
    if hasattr(messaging, 'send_each'):
        print_result(True, "messaging.send_each method exists (firebase-admin 6.0+)")
    else:
        print_result(False, "messaging.send_each not found - need firebase-admin >= 6.0")
        return False
    
    # Check send_multicast is removed
    if not hasattr(messaging, 'send_multicast'):
        print_result(True, "messaging.send_multicast correctly removed")
    else:
        print_result(False, "messaging.send_multicast still exists (older version)")
    
    return True


async def test_firebase_initialization():
    """Test 2: Firebase initialization with credentials."""
    print_header("Test 2: Firebase Initialization")
    
    from app.core.config import get_settings
    settings = get_settings()
    
    print(f"   FIREBASE_ENABLED: {settings.firebase_enabled}")
    print(f"   FIREBASE_SERVICE_ACCOUNT_PATH: {settings.firebase_service_account_path}")
    print(f"   FIREBASE_PROJECT_ID: {settings.firebase_project_id}")
    
    if not settings.firebase_enabled:
        print_result(False, "Firebase is disabled in settings")
        return False
    
    if not settings.firebase_service_account_path:
        print_result(False, "Service account path not configured")
        return False
    
    if not os.path.exists(settings.firebase_service_account_path):
        print_result(False, f"Service account file not found: {settings.firebase_service_account_path}")
        return False
    
    print_result(True, f"Service account file exists: {settings.firebase_service_account_path}")
    
    # Try to initialize FCM notifier
    from app.services.fcm_notifier import FCMNotifier
    
    notifier = FCMNotifier(enabled=True)
    
    if notifier.enabled and notifier._initialized:
        print_result(True, f"FCMNotifier initialized successfully")
        return True
    else:
        print_result(False, "FCMNotifier failed to initialize")
        return False


async def test_fcm_tokens_in_database():
    """Test 3: Check FCM tokens in database."""
    print_header("Test 3: FCM Tokens in Database")
    
    from app.core.database import get_async_db
    from app.models.db_models import FCMToken
    from sqlalchemy import select, func
    
    async for db in get_async_db():
        try:
            # Count all tokens
            stmt = select(func.count(FCMToken.id))
            result = await db.execute(stmt)
            total_count = result.scalar()
            print(f"   Total FCM tokens: {total_count}")
            
            # Count active tokens
            stmt = select(func.count(FCMToken.id)).where(FCMToken.is_active == True)
            result = await db.execute(stmt)
            active_count = result.scalar()
            print(f"   Active FCM tokens: {active_count}")
            
            if total_count == 0:
                print_result(False, "No FCM tokens in database")
                print("\n   To register a token, the Android app must:")
                print("   1. Login successfully")
                print("   2. Get FCM token from Firebase")
                print("   3. Call POST /api/notifications/fcm/register")
                return False
            
            # Show sample tokens (masked)
            stmt = select(FCMToken).where(FCMToken.is_active == True).limit(5)
            result = await db.execute(stmt)
            tokens = result.scalars().all()
            
            print(f"\n   Active tokens ({len(tokens)} shown):")
            for token in tokens:
                masked_token = token.token[:20] + "..." if len(token.token) > 20 else token.token
                print(f"   - User: {token.user_id}")
                print(f"     Device: {token.device_name or 'Unknown'} ({token.device_type})")
                print(f"     Client: {token.client_type}")
                print(f"     Token: {masked_token}")
                print(f"     Last used: {token.last_used_at}")
            
            print_result(True, f"Found {active_count} active FCM token(s)")
            return active_count > 0
            
        except Exception as e:
            print_result(False, f"Database error: {e}")
            return False


async def test_send_notification(user_id: str = None):
    """Test 4: Send a test notification."""
    print_header("Test 4: Send Test Notification")
    
    if not user_id:
        # Get first user with FCM tokens
        from app.core.database import get_async_db
        from app.models.db_models import FCMToken
        from sqlalchemy import select
        
        async for db in get_async_db():
            stmt = select(FCMToken.user_id).where(FCMToken.is_active == True).limit(1)
            result = await db.execute(stmt)
            row = result.first()
            if row:
                user_id = str(row[0])
            break
    
    if not user_id:
        print_result(False, "No user with FCM tokens found")
        return False
    
    print(f"   Sending test notification to user: {user_id}")
    
    from app.services.fcm_notifier import FCMNotifier
    from app.core.database import get_async_db
    
    notifier = FCMNotifier(enabled=True)
    
    if not notifier.enabled:
        print_result(False, "FCMNotifier is disabled")
        return False
    
    async for db in get_async_db():
        try:
            sent_count = await notifier.send_to_user(
                user_id=UUID(user_id),
                title="FCM Test Notification",
                body=f"This is a test notification sent at {datetime.now(timezone.utc).isoformat()}",
                data={
                    "type": "test",
                    "category": "fcm_test",
                    "timestamp": str(datetime.now(timezone.utc).timestamp()),
                },
                db=db,
                channel_id="alerts_channel"
            )
            
            if sent_count > 0:
                print_result(True, f"Sent notification to {sent_count} device(s)")
                print("\n   Check your Android device for the notification!")
                return True
            else:
                print_result(False, "No notifications sent (0 successful)")
                return False
                
        except Exception as e:
            print_result(False, f"Error sending notification: {e}")
            import traceback
            traceback.print_exc()
            return False


async def run_all_tests():
    """Run all FCM tests."""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " FCM Integration Test Suite ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    
    results = []
    
    # Test 1: Firebase SDK
    results.append(("Firebase SDK", await test_firebase_sdk()))
    
    # Test 2: Firebase initialization
    results.append(("Firebase Init", await test_firebase_initialization()))
    
    # Test 3: FCM tokens in database
    results.append(("FCM Tokens", await test_fcm_tokens_in_database()))
    
    # Test 4: Send test notification (only if previous tests passed)
    if all(r[1] for r in results):
        results.append(("Send Notification", await test_send_notification()))
    else:
        print_header("Test 4: Send Test Notification")
        print_result(False, "Skipped (previous tests failed)")
        results.append(("Send Notification", False))
    
    # Summary
    print_header("Test Summary")
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    for name, success in results:
        icon = "✅" if success else "❌"
        print(f"   {icon} {name}")
    
    print()
    if failed == 0:
        print(f"   All {passed} tests passed! FCM is working correctly.")
    else:
        print(f"   {passed} passed, {failed} failed")
        print("\n   To fix FCM issues:")
        print("   1. Ensure firebase-service-account.json is in app/config/")
        print("   2. Set FIREBASE_SERVICE_ACCOUNT_PATH=app/config/firebase-service-account.json")
        print("   3. Set FIREBASE_ENABLED=true")
        print("   4. Restart the backend: docker compose restart api")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
