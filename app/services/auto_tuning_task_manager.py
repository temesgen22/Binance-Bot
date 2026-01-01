"""
Auto-Tuning Task Manager

Manages background auto-tuning tasks with per-strategy locks (singleflight pattern).
"""
from __future__ import annotations

import asyncio
from typing import Dict, Optional
from uuid import UUID

from loguru import logger

from app.services.auto_tuning_service import AutoTuningService


class AutoTuningTaskManager:
    """Manages background auto-tuning tasks.
    
    Uses per-strategy locks (singleflight pattern) to prevent concurrent tuning.
    """
    
    def __init__(self, auto_tuning_service: AutoTuningService):
        """Initialize AutoTuningTaskManager.
        
        Args:
            auto_tuning_service: AutoTuningService instance
        """
        self.auto_tuning_service = auto_tuning_service
        self._monitoring_tasks: Dict[UUID, asyncio.Task] = {}
        self._tuning_tasks: Dict[UUID, asyncio.Task] = {}
        self._tuning_locks: Dict[UUID, asyncio.Lock] = {}  # Per-strategy locks
        self._lock = asyncio.Lock()  # Global lock for dict access
    
    async def start_monitoring(self, strategy_uuid: UUID) -> None:
        """Start monitoring a strategy.
        
        Args:
            strategy_uuid: Strategy UUID
        """
        async with self._lock:
            if strategy_uuid in self._monitoring_tasks:
                existing_task = self._monitoring_tasks[strategy_uuid]
                if not existing_task.done():
                    logger.warning(f"Monitoring already running for strategy {strategy_uuid}")
                    return
                # Clean up done task
                del self._monitoring_tasks[strategy_uuid]
            
            # Create monitoring task
            task = asyncio.create_task(self._monitor_strategy(strategy_uuid))
            self._monitoring_tasks[strategy_uuid] = task
            logger.info(f"Started monitoring for strategy {strategy_uuid}")
    
    async def stop_monitoring(self, strategy_uuid: UUID) -> None:
        """Stop monitoring a strategy.
        
        Args:
            strategy_uuid: Strategy UUID
        """
        async with self._lock:
            task = self._monitoring_tasks.pop(strategy_uuid, None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.info(f"Stopped monitoring for strategy {strategy_uuid}")
    
    async def trigger_tuning(self, strategy_uuid: UUID) -> Optional[str]:
        """Trigger tuning with singleflight pattern (one tuning per strategy at a time).
        
        Args:
            strategy_uuid: Strategy UUID
            
        Returns:
            Task ID if tuning started, None if already tuning
        """
        # Get or create per-strategy lock
        async with self._lock:
            if strategy_uuid not in self._tuning_locks:
                self._tuning_locks[strategy_uuid] = asyncio.Lock()
            tuning_lock = self._tuning_locks[strategy_uuid]
            
            # Check if already tuning
            if strategy_uuid in self._tuning_tasks:
                existing_task = self._tuning_tasks[strategy_uuid]
                if not existing_task.done():
                    logger.info(f"Strategy {strategy_uuid} already tuning, returning existing task")
                    return f"tuning_{strategy_uuid}"  # Return existing task ID
                # Clean up done task
                del self._tuning_tasks[strategy_uuid]
        
        # Acquire per-strategy lock and create task
        async with tuning_lock:
            # Double-check (another task might have started)
            async with self._lock:
                if strategy_uuid in self._tuning_tasks:
                    existing_task = self._tuning_tasks[strategy_uuid]
                    if not existing_task.done():
                        return f"tuning_{strategy_uuid}"
            
            # Create tuning task
            task = asyncio.create_task(self._execute_tuning(strategy_uuid))
            
            async with self._lock:
                self._tuning_tasks[strategy_uuid] = task
            
            return f"tuning_{strategy_uuid}"
    
    async def _execute_tuning(self, strategy_uuid: UUID) -> dict:
        """Execute tuning with retry logic for transient failures.
        
        CRITICAL: Always cleanup task in finally block.
        
        Args:
            strategy_uuid: Strategy UUID
            
        Returns:
            Tuning result dictionary
            
        Raises:
            Exception: If tuning fails after all retries
        """
        task_id = f"tuning_{strategy_uuid}"
        max_retries = 3
        retry_delays = [60, 300, 900]  # 1 min, 5 min, 15 min (exponential backoff)
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                    logger.info(
                        f"Retrying tuning for strategy {strategy_uuid} "
                        f"(attempt {attempt + 1}/{max_retries}) after {wait_time}s delay"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.info(f"Starting tuning for strategy {strategy_uuid}")
                
                # Run tuning logic
                result = await self.auto_tuning_service.tune_strategy(str(strategy_uuid))
                
                logger.info(f"Tuning completed for strategy {strategy_uuid}: {result.get('status')}")
                return result
                
            except asyncio.CancelledError:
                # Don't retry on cancellation
                logger.info(f"Tuning cancelled for strategy {strategy_uuid}")
                raise
            except Exception as e:
                last_error = str(e)
                error_type = type(e).__name__
                
                # Log error with attempt information
                logger.error(
                    f"Tuning failed for strategy {strategy_uuid} "
                    f"(attempt {attempt + 1}/{max_retries}): {error_type}: {e}",
                    exc_info=True
                )
                
                # Store error in database for debugging
                await self.auto_tuning_service._log_tuning_failure(
                    strategy_uuid,
                    reason=f"execution_error_attempt_{attempt + 1}",
                    message=f"{error_type}: {last_error}"
                )
                
                # Check if this is a transient error that should be retried
                is_transient = self._is_transient_error(e)
                
                if attempt < max_retries - 1 and is_transient:
                    # Will retry on next iteration
                    continue
                else:
                    # Final attempt failed or non-transient error
                    logger.error(
                        f"Tuning failed permanently for strategy {strategy_uuid} "
                        f"after {attempt + 1} attempts. Last error: {last_error}"
                    )
                    raise
            
        finally:
            # Always cleanup task entry
            async with self._lock:
                self._tuning_tasks.pop(strategy_uuid, None)
            
            logger.debug(f"Cleaned up tuning task for strategy {strategy_uuid}")
    
    def _is_transient_error(self, error: Exception) -> bool:
        """Check if error is transient and should be retried.
        
        Args:
            error: Exception to check
            
        Returns:
            True if error is transient, False otherwise
        """
        transient_errors = (
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
            OSError,  # Network errors
        )
        
        # Check exception type
        if isinstance(error, transient_errors):
            return True
        
        # Check error message for common transient issues
        error_msg = str(error).lower()
        transient_keywords = [
            "connection",
            "timeout",
            "network",
            "temporary",
            "retry",
            "rate limit",
            "too many requests",
            "service unavailable",
            "502",
            "503",
            "504"
        ]
        
        return any(keyword in error_msg for keyword in transient_keywords)
    
    async def _monitor_strategy(self, strategy_uuid: UUID) -> None:
        """Monitor strategy and enqueue tuning requests with improved error handling.
        
        Args:
            strategy_uuid: Strategy UUID
        """
        strategy_id = str(strategy_uuid)
        consecutive_errors = 0
        max_consecutive_errors = 5
        base_retry_delay = 60  # Start with 1 minute
        
        while True:
            try:
                # Check if should tune
                if await self.auto_tuning_service.should_tune(strategy_id):
                    # Enqueue tuning request (does not block)
                    await self.trigger_tuning(strategy_uuid)
                
                # Reset error counter on success
                consecutive_errors = 0
                
                # Check every hour
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                logger.info(f"Monitoring cancelled for strategy {strategy_uuid}")
                break
            except Exception as e:
                consecutive_errors += 1
                error_type = type(e).__name__
                
                logger.error(
                    f"Error in monitor loop for {strategy_uuid} "
                    f"(consecutive errors: {consecutive_errors}/{max_consecutive_errors}): "
                    f"{error_type}: {e}",
                    exc_info=True
                )
                
                # Exponential backoff for retries
                retry_delay = min(base_retry_delay * (2 ** (consecutive_errors - 1)), 3600)  # Max 1 hour
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"Monitoring stopped for strategy {strategy_uuid} after "
                        f"{max_consecutive_errors} consecutive errors. "
                        f"Manual intervention may be required."
                    )
                    # Wait longer before retrying (15 minutes)
                    await asyncio.sleep(900)
                    consecutive_errors = 0  # Reset after long wait
                else:
                    await asyncio.sleep(retry_delay)
    
    async def get_tuning_status(self, strategy_uuid: UUID) -> dict:
        """Get tuning status for a strategy with health check information.
        
        Args:
            strategy_uuid: Strategy UUID
            
        Returns:
            Status dictionary with health information
        """
        async with self._lock:
            is_monitoring = strategy_uuid in self._monitoring_tasks
            is_tuning = strategy_uuid in self._tuning_tasks
            
            monitoring_task = self._monitoring_tasks.get(strategy_uuid)
            tuning_task = self._tuning_tasks.get(strategy_uuid)
            
            # Health check: Check if tasks have exceptions
            monitoring_healthy = True
            tuning_healthy = True
            monitoring_error = None
            tuning_error = None
            
            if monitoring_task and monitoring_task.done():
                try:
                    await monitoring_task  # Re-raise exception if any
                except Exception as e:
                    monitoring_healthy = False
                    monitoring_error = str(e)
                    logger.warning(f"Monitoring task for {strategy_uuid} has error: {e}")
            
            if tuning_task and tuning_task.done():
                try:
                    await tuning_task  # Re-raise exception if any
                except Exception as e:
                    tuning_healthy = False
                    tuning_error = str(e)
                    logger.warning(f"Tuning task for {strategy_uuid} has error: {e}")
            
            return {
                "strategy_uuid": str(strategy_uuid),
                "is_monitoring": is_monitoring and (not monitoring_task or not monitoring_task.done()),
                "is_tuning": is_tuning and (not tuning_task or not tuning_task.done()),
                "monitoring_done": monitoring_task.done() if monitoring_task else None,
                "tuning_done": tuning_task.done() if tuning_task else None,
                "monitoring_healthy": monitoring_healthy,
                "tuning_healthy": tuning_healthy,
                "monitoring_error": monitoring_error,
                "tuning_error": tuning_error,
            }






