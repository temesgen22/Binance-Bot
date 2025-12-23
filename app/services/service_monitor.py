"""Service monitoring for database, FastAPI, and Docker services."""

from __future__ import annotations

import asyncio
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from loguru import logger

from app.services.notifier import NotificationService


class ServiceMonitor:
    """Monitor services and send notifications on failures."""
    
    def __init__(
        self,
        notification_service: Optional[NotificationService] = None,
        check_interval: int = 60,  # Check every 60 seconds
    ):
        """Initialize service monitor.
        
        Args:
            notification_service: Notification service instance
            check_interval: Interval in seconds between health checks
        """
        self.notification_service = notification_service
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Track service states to avoid duplicate notifications
        self._last_states: Dict[str, bool] = {
            "database": None,
            "fastapi": None,
            "docker_postgres": None,
            "docker_api": None,
            "docker_redis": None,
        }
        
        # Track notification cooldown (don't spam notifications)
        self._last_notification_time: Dict[str, float] = {}
        self._notification_cooldown = 300  # 5 minutes between notifications for same service
    
    async def notify_database_connection_failed(
        self,
        error: Exception,
        retry_count: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        """Notify about database connection failure."""
        if not self.notification_service:
            return
        
        # Check cooldown
        now = time.time()
        last_notif = self._last_notification_time.get("database_failed", 0)
        if now - last_notif < self._notification_cooldown:
            return
        
        try:
            await self.notification_service.notify_database_connection_failed(
                error, retry_count, max_retries
            )
            self._last_notification_time["database_failed"] = now
            self._last_states["database"] = False
        except Exception as e:
            logger.warning(f"Failed to send database failure notification: {e}")
    
    async def notify_database_connection_restored(self) -> None:
        """Notify about database connection restoration."""
        if not self.notification_service:
            return
        
        # Only notify if database was previously down
        if self._last_states.get("database") is not False:
            return
        
        try:
            await self.notification_service.notify_database_connection_restored()
            self._last_states["database"] = True
        except Exception as e:
            logger.warning(f"Failed to send database restored notification: {e}")
    
    async def notify_fastapi_service_down(self, error: Optional[str] = None) -> None:
        """Notify about FastAPI service being down."""
        if not self.notification_service:
            return
        
        # Check cooldown
        now = time.time()
        last_notif = self._last_notification_time.get("fastapi_down", 0)
        if now - last_notif < self._notification_cooldown:
            return
        
        try:
            message = (
                "🚨 <b>FastAPI Service Down</b>\n\n"
                "The FastAPI application service is not responding.\n\n"
            )
            if error:
                error_msg = str(error)[:300]
                message += f"Error: <code>{error_msg}</code>\n\n"
            
            message += "⚠️ <b>The API is unavailable</b>\n"
            message += "All API endpoints may be unreachable.\n\n"
            
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"⏰ {timestamp}"
            
            if self.notification_service.telegram:
                await self.notification_service.telegram.send_message(
                    message, disable_notification=False
                )
            
            self._last_notification_time["fastapi_down"] = now
            self._last_states["fastapi"] = False
        except Exception as e:
            logger.warning(f"Failed to send FastAPI down notification: {e}")
    
    async def notify_fastapi_service_restored(self) -> None:
        """Notify about FastAPI service restoration."""
        if not self.notification_service:
            return
        
        # Only notify if FastAPI was previously down
        if self._last_states.get("fastapi") is not False:
            return
        
        try:
            message = (
                "✅ <b>FastAPI Service Restored</b>\n\n"
                "The FastAPI application service is now responding.\n"
                "All API endpoints are available again.\n\n"
            )
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"⏰ {timestamp}"
            
            if self.notification_service.telegram:
                await self.notification_service.telegram.send_message(
                    message, disable_notification=False
                )
            
            self._last_states["fastapi"] = True
        except Exception as e:
            logger.warning(f"Failed to send FastAPI restored notification: {e}")
    
    async def notify_docker_service_down(
        self,
        service_name: str,
        error: Optional[str] = None,
    ) -> None:
        """Notify about Docker service being down.
        
        Args:
            service_name: Name of the Docker service (e.g., "postgres", "api", "redis")
            error: Optional error message
        """
        if not self.notification_service:
            return
        
        # Check cooldown
        now = time.time()
        key = f"docker_{service_name}_down"
        last_notif = self._last_notification_time.get(key, 0)
        if now - last_notif < self._notification_cooldown:
            return
        
        try:
            service_display_names = {
                "postgres": "PostgreSQL Database",
                "api": "FastAPI Application",
                "redis": "Redis Cache",
            }
            display_name = service_display_names.get(service_name, service_name)
            
            message = (
                f"🚨 <b>Docker Service Down: {display_name}</b>\n\n"
                f"The Docker container '{service_name}' is not running.\n\n"
            )
            if error:
                error_msg = str(error)[:300]
                message += f"Error: <code>{error_msg}</code>\n\n"
            
            message += "⚠️ <b>Service is unavailable</b>\n"
            message += "Check Docker container status and logs.\n\n"
            
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"⏰ {timestamp}"
            
            if self.notification_service.telegram:
                await self.notification_service.telegram.send_message(
                    message, disable_notification=False
                )
            
            self._last_notification_time[key] = now
            self._last_states[f"docker_{service_name}"] = False
        except Exception as e:
            logger.warning(f"Failed to send Docker service down notification: {e}")
    
    async def notify_docker_service_restored(self, service_name: str) -> None:
        """Notify about Docker service restoration.
        
        Args:
            service_name: Name of the Docker service
        """
        if not self.notification_service:
            return
        
        # Only notify if service was previously down
        key = f"docker_{service_name}"
        if self._last_states.get(key) is not False:
            return
        
        try:
            service_display_names = {
                "postgres": "PostgreSQL Database",
                "api": "FastAPI Application",
                "redis": "Redis Cache",
            }
            display_name = service_display_names.get(service_name, service_name)
            
            message = (
                f"✅ <b>Docker Service Restored: {display_name}</b>\n\n"
                f"The Docker container '{service_name}' is now running.\n"
                "Service is available again.\n\n"
            )
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"⏰ {timestamp}"
            
            if self.notification_service.telegram:
                await self.notification_service.telegram.send_message(
                    message, disable_notification=False
                )
            
            self._last_states[key] = True
        except Exception as e:
            logger.warning(f"Failed to send Docker service restored notification: {e}")
    
    async def check_docker_service(self, container_name: str) -> bool:
        """Check if a Docker container is running.
        
        Args:
            container_name: Name of the Docker container
            
        Returns:
            True if container is running, False otherwise
        """
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            is_running = container_name in result.stdout
            return is_running
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"Error checking Docker container {container_name}: {e}")
            return False
    
    async def check_fastapi_health(self) -> bool:
        """Check if FastAPI service is responding.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            import httpx
            from app.core.config import get_settings
            
            settings = get_settings()
            api_url = f"http://localhost:{settings.api_port}/health/quick"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(api_url)
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"FastAPI health check failed: {e}")
            return False
    
    async def check_database_connection(self) -> bool:
        """Check if database connection is working.
        
        Returns:
            True if database is connected, False otherwise
        """
        try:
            from app.core.database import get_engine
            from sqlalchemy import text
            
            engine = get_engine()
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            return True
        except Exception:
            return False
    
    async def monitor_loop(self) -> None:
        """Main monitoring loop."""
        logger.info("Service monitor started")
        
        while self._running:
            try:
                # Check Docker services
                docker_services = {
                    "binance-bot-postgres": "postgres",
                    "binance-bot-api": "api",
                    "binance-bot-redis": "redis",
                }
                
                for container_name, service_name in docker_services.items():
                    is_running = await self.check_docker_service(container_name)
                    key = f"docker_{service_name}"
                    
                    if not is_running:
                        if self._last_states.get(key) is not False:
                            await self.notify_docker_service_down(service_name)
                    else:
                        if self._last_states.get(key) is False:
                            await self.notify_docker_service_restored(service_name)
                    
                    self._last_states[key] = is_running
                
                # Check FastAPI service
                fastapi_healthy = await self.check_fastapi_health()
                if not fastapi_healthy:
                    if self._last_states.get("fastapi") is not False:
                        await self.notify_fastapi_service_down("Health check failed")
                else:
                    if self._last_states.get("fastapi") is False:
                        await self.notify_fastapi_service_restored()
                
                self._last_states["fastapi"] = fastapi_healthy
                
                # Check database connection
                db_connected = await self.check_database_connection()
                if not db_connected:
                    if self._last_states.get("database") is not False:
                        # Database connection check failed
                        error = Exception("Database connection check failed")
                        await self.notify_database_connection_failed(error)
                else:
                    if self._last_states.get("database") is False:
                        await self.notify_database_connection_restored()
                
                self._last_states["database"] = db_connected
                
            except Exception as e:
                logger.error(f"Error in service monitor loop: {e}")
            
            # Wait before next check
            await asyncio.sleep(self.check_interval)
    
    def start(self) -> None:
        """Start the monitoring service."""
        if self._running:
            logger.warning("Service monitor is already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self.monitor_loop())
        logger.info("Service monitor started")
    
    def stop(self) -> None:
        """Stop the monitoring service."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            logger.info("Service monitor stopped")



