"""
Firebase Cloud Messaging (FCM) Notifier for push notifications.

This service handles sending push notifications to Android mobile devices
via Firebase Cloud Messaging.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

# Firebase imports (optional - gracefully handle if not installed)
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    credentials = None
    messaging = None

from app.models.strategy import StrategySummary


class FCMNotifier:
    """FCM notifier for sending push notifications to mobile devices."""
    
    # Class-level flag to track Firebase initialization (singleton pattern)
    _firebase_initialized = False
    
    def __init__(self, enabled: bool = True):
        """Initialize FCM notifier.
        
        Args:
            enabled: Whether FCM notifications are enabled
        """
        self.enabled = enabled
        self._initialized = False
        
        if not FIREBASE_AVAILABLE:
            logger.warning("firebase-admin package not installed. FCM notifications disabled.")
            self.enabled = False
            return
        
        if enabled:
            self._initialize_firebase()
    
    def _initialize_firebase(self) -> None:
        """Initialize Firebase Admin SDK (singleton pattern - only once per process)."""
        if self._initialized:
            return
        
        # Check if Firebase is already initialized (singleton pattern)
        if FCMNotifier._firebase_initialized:
            self._initialized = True
            logger.debug("Firebase Admin SDK already initialized (from class-level check)")
            return
        
        try:
            # Try to get existing app - if it exists, Firebase is already initialized
            firebase_admin.get_app()
            FCMNotifier._firebase_initialized = True
            self._initialized = True
            logger.info("Firebase Admin SDK already initialized")
            return
        except ValueError:
            # No app exists yet - proceed with initialization
            pass
        
        try:
            from app.core.config import get_settings
            settings = get_settings()
            
            if not settings.firebase_enabled:
                logger.info("FCM disabled in settings (FIREBASE_ENABLED=false)")
                self.enabled = False
                return
            
            if not settings.firebase_service_account_path:
                logger.warning("Firebase service account path not configured (FIREBASE_SERVICE_ACCOUNT_PATH)")
                self.enabled = False
                return
            
            # Check if service account file exists
            import os
            if not os.path.exists(settings.firebase_service_account_path):
                logger.warning(f"Firebase service account file not found: {settings.firebase_service_account_path}")
                self.enabled = False
                return
            
            # Initialize Firebase Admin SDK (only if not already initialized)
            cred = credentials.Certificate(settings.firebase_service_account_path)
            firebase_admin.initialize_app(cred)
            FCMNotifier._firebase_initialized = True
            self._initialized = True
            logger.info(f"Firebase Admin SDK initialized successfully (project: {settings.firebase_project_id or 'unknown'})")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            self.enabled = False
            self._initialized = False
    
    async def send_to_user(
        self,
        user_id: UUID,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
        db: Optional[AsyncSession] = None,
        channel_id: str = "alerts_channel",
        client_types: Optional[List[str]] = None,
    ) -> int:
        """Send FCM notification to all active tokens for a user.
        
        Args:
            user_id: User UUID
            title: Notification title
            body: Notification body
            data: Additional data payload
            db: Async database session
            channel_id: Android notification channel ID
            client_types: Optional list of client types to filter (e.g., ["android_app", "web_app"])
                          If None, sends to all client types
            
        Returns:
            Number of successful sends
        """
        if not self.enabled or not self._initialized:
            logger.debug("FCM notifier disabled, skipping")
            return 0
        
        if not db:
            logger.warning("Database session required for FCM notification")
            return 0
        
        try:
            from sqlalchemy import select
            from app.models.db_models import FCMToken
            
            # Build query conditions
            conditions = [
                FCMToken.user_id == user_id,
                FCMToken.is_active == True
            ]
            
            # Optionally filter by client types
            if client_types:
                conditions.append(FCMToken.client_type.in_(client_types))
            
            # Get all active FCM tokens for user (async)
            stmt = select(FCMToken).where(*conditions)
            result = await db.execute(stmt)
            tokens = result.scalars().all()
            
            if not tokens:
                filter_info = f" (client_types={client_types})" if client_types else ""
                logger.debug(f"No FCM tokens found for user {user_id}{filter_info}")
                return 0
            
            # Prepare messages for each token (firebase-admin 6.0+ uses send_each instead of send_multicast)
            token_list = [token.token for token in tokens]
            messages = [
                messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data=data or {},
                    token=token_str,
                    android=messaging.AndroidConfig(
                        priority="high",
                        notification=messaging.AndroidNotification(
                            channel_id=channel_id,
                            sound="default",
                        ),
                    ),
                )
                for token_str in token_list
            ]
            
            # Send notifications (run in thread pool to avoid blocking event loop)
            # Use send_each for firebase-admin 6.0+
            response = await asyncio.to_thread(messaging.send_each, messages)
            
            # Update token status based on results
            successful = 0
            for i, send_result in enumerate(response.responses):
                token = tokens[i]
                if send_result.success:
                    successful += 1
                    # Update last_used_at
                    token.last_used_at = datetime.now(timezone.utc)
                else:
                    # Handle invalid tokens
                    error_str = str(send_result.exception) if send_result.exception else ""
                    invalid_patterns = [
                        "InvalidRegistration",
                        "NotRegistered", 
                        "registration token is not valid",
                        "registration-token-not-registered",
                        "invalid-registration-token"
                    ]
                    if any(pattern.lower() in error_str.lower() for pattern in invalid_patterns):
                        logger.warning(f"Invalid FCM token for user {user_id}, device {token.device_id}. Marking inactive.")
                        token.is_active = False
                    else:
                        # Log other errors but don't deactivate (might be temporary)
                        logger.warning(f"FCM send failed for token {token.id}: {error_str}")
            
            await db.commit()
            logger.info(f"Sent FCM notification to {successful}/{len(tokens)} devices for user {user_id}")
            return successful
            
        except Exception as e:
            logger.error(f"Failed to send FCM notification: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            return 0
    
    async def notify_strategy_started(
        self,
        user_id: UUID,
        summary: StrategySummary,
        reason: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Send FCM notification when strategy starts.
        
        Args:
            user_id: User UUID
            summary: Strategy summary
            reason: Optional reason for starting
            db: Async database session
            
        Returns:
            True if notification was sent successfully
        """
        title = "Strategy Started"
        body = f"{summary.name} ({summary.symbol}) has started"
        if reason:
            body += f" - {reason}"
        
        data = {
            "type": "strategy",
            "category": "strategy_started",
            "strategy_id": summary.id,
            "strategy_name": summary.name,
            "symbol": summary.symbol,
            "status": "running",
        }
        
        sent_count = await self.send_to_user(
            user_id, title, body, data, db, channel_id="strategies_channel"
        )
        return sent_count > 0
    
    async def notify_strategy_stopped(
        self,
        user_id: UUID,
        summary: StrategySummary,
        reason: Optional[str] = None,
        final_pnl: Optional[float] = None,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Send FCM notification when strategy stops.
        
        Args:
            user_id: User UUID
            summary: Strategy summary
            reason: Optional reason for stopping
            final_pnl: Final profit/loss if available
            db: Async database session
            
        Returns:
            True if notification was sent successfully
        """
        title = "Strategy Stopped"
        body = f"{summary.name} ({summary.symbol}) has stopped"
        if reason:
            body += f" - {reason}"
        if final_pnl is not None:
            pnl_sign = "+" if final_pnl >= 0 else ""
            body += f" | Final PnL: {pnl_sign}${final_pnl:.2f}"
        
        data = {
            "type": "strategy",
            "category": "strategy_stopped",
            "strategy_id": summary.id,
            "strategy_name": summary.name,
            "symbol": summary.symbol,
            "status": "stopped",
        }
        if final_pnl is not None:
            data["final_pnl"] = str(final_pnl)
        
        sent_count = await self.send_to_user(
            user_id, title, body, data, db, channel_id="strategies_channel"
        )
        return sent_count > 0
    
    async def notify_strategy_error(
        self,
        user_id: UUID,
        summary: StrategySummary,
        error: Exception,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Send FCM notification when strategy encounters error.
        
        Args:
            user_id: User UUID
            summary: Strategy summary
            error: The exception that occurred
            db: Async database session
            
        Returns:
            True if notification was sent successfully
        """
        title = "Strategy Error"
        error_msg = str(error)[:100]  # Truncate long error messages
        body = f"{summary.name} ({summary.symbol}): {error_msg}"
        
        # Keep data payload small - FCM has size limits (~4KB total)
        error_id = f"err_{summary.id[:8]}_{int(datetime.now(timezone.utc).timestamp())}"
        logger.error(f"Strategy error [{error_id}]: {summary.id} - {str(error)}")
        
        data = {
            "type": "strategy",
            "category": "strategy_error",
            "strategy_id": summary.id,
            "strategy_name": summary.name[:50],  # Truncate to keep small
            "symbol": summary.symbol,
            "error_id": error_id,
        }
        
        sent_count = await self.send_to_user(
            user_id, title, body, data, db, channel_id="alerts_channel"
        )
        return sent_count > 0
    
    async def notify_trade_executed(
        self,
        user_id: UUID,
        trade_id: str,
        strategy_id: str,
        strategy_name: str,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        pnl: Optional[float] = None,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Send FCM notification when trade is executed.
        
        Args:
            user_id: User UUID
            trade_id: Trade ID
            strategy_id: Strategy ID
            strategy_name: Strategy name
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Trade quantity
            price: Trade price
            pnl: Profit/loss if available
            db: Async database session
            
        Returns:
            True if notification was sent successfully
        """
        title = f"Trade Executed - {strategy_name}"
        body = f"{side} {quantity} {symbol} @ {price}"
        if pnl is not None:
            pnl_sign = "+" if pnl >= 0 else ""
            body += f" | PnL: {pnl_sign}${pnl:.2f}"
        
        data = {
            "type": "trade",
            "category": "trade_executed",
            "trade_id": trade_id,
            "strategy_id": strategy_id,
            "strategy_name": strategy_name[:50],
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
        }
        if pnl is not None:
            data["pnl"] = str(pnl)
        
        sent_count = await self.send_to_user(
            user_id, title, body, data, db, channel_id="trades_channel"
        )
        return sent_count > 0
    
    async def notify_risk_alert(
        self,
        user_id: UUID,
        alert_type: str,
        account_id: str,
        message: str,
        current_value: Optional[float] = None,
        limit_value: Optional[float] = None,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Send FCM notification for risk alert.
        
        Args:
            user_id: User UUID
            alert_type: Type of risk alert
            account_id: Account ID
            message: Alert message
            current_value: Current value
            limit_value: Limit value
            db: Async database session
            
        Returns:
            True if notification was sent successfully
        """
        title_map = {
            "daily_loss_limit": "Daily Loss Limit Reached",
            "weekly_loss_limit": "Weekly Loss Limit Reached",
            "max_drawdown": "Max Drawdown Alert",
            "circuit_breaker": "Circuit Breaker Activated",
            "position_size_limit": "Position Size Limit Exceeded",
            "exposure_limit": "Exposure Limit Warning",
        }
        title = title_map.get(alert_type, "Risk Alert")
        
        body = message
        if current_value is not None and limit_value is not None:
            body += f" | Current: ${current_value:.2f} / Limit: ${limit_value:.2f}"
        
        data = {
            "type": "alert",
            "category": "risk_alert",
            "alert_type": alert_type,
            "account_id": account_id,
        }
        if current_value is not None:
            data["current_value"] = str(current_value)
        if limit_value is not None:
            data["limit_value"] = str(limit_value)
        
        sent_count = await self.send_to_user(
            user_id, title, body, data, db, channel_id="alerts_channel"
        )
        return sent_count > 0
    
    async def notify_pnl_threshold(
        self,
        user_id: UUID,
        summary: StrategySummary,
        pnl: float,
        threshold: float,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Send FCM notification when PnL threshold is reached.
        
        Args:
            user_id: User UUID
            summary: Strategy summary
            pnl: Current PnL
            threshold: Threshold that was reached
            db: Async database session
            
        Returns:
            True if notification was sent successfully
        """
        is_profit = pnl >= 0
        title = "Profit Target Reached" if is_profit else "Loss Threshold Reached"
        
        pnl_sign = "+" if pnl >= 0 else ""
        body = f"{summary.name} ({summary.symbol}): {pnl_sign}${pnl:.2f}"
        
        data = {
            "type": "alert",
            "category": "pnl_threshold",
            "strategy_id": summary.id,
            "strategy_name": summary.name[:50],
            "symbol": summary.symbol,
            "pnl": str(pnl),
            "threshold": str(threshold),
            "is_profit": str(is_profit).lower(),
        }
        
        sent_count = await self.send_to_user(
            user_id, title, body, data, db, channel_id="alerts_channel"
        )
        return sent_count > 0
