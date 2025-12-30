"""
Task Manager for Walk-Forward Analysis

Manages running walk-forward analyses, tracks progress, and handles cancellation.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class WalkForwardProgress:
    """Progress information for a walk-forward analysis."""
    task_id: str
    user_id: str  # User who created this task (for isolation)
    status: str  # "running", "completed", "cancelled", "error"
    current_window: int = 0
    total_windows: int = 0
    current_phase: str = ""  # "fetching_klines", "optimizing", "training", "testing", "aggregating"
    message: str = ""
    start_time: Optional[datetime] = None
    estimated_time_remaining_seconds: Optional[float] = None
    error: Optional[str] = None
    result: Optional[dict] = None  # Store final result when completed
    # Sub-progress tracking for better accuracy
    phase_progress: float = 0.0  # 0.0-1.0 progress within current phase
    
    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage with phase-based sub-progress."""
        if self.total_windows == 0:
            return 0.0
        if self.status == "completed":
            return 100.0
        if self.status in ("cancelled", "error"):
            # For cancelled/error, show progress up to current window
            base_progress = (self.current_window / self.total_windows) * 100.0
            # Add partial progress for current phase if we have phase_progress
            if self.phase_progress > 0 and self.current_window < self.total_windows:
                phase_weight = 1.0 / self.total_windows  # Each window is 1/total_windows
                return min(100.0, base_progress + (phase_weight * self.phase_progress * 100.0))
            return base_progress
        
        # For running status, calculate based on completed windows + current phase progress
        if self.current_window >= self.total_windows:
            return 100.0
        
        # Base progress: completed windows
        base_progress = (self.current_window / self.total_windows) * 100.0
        
        # Add progress for current phase
        # Phase weights (estimated time distribution):
        # - fetching_klines: 5%
        # - optimizing: 40% (can be long with many combinations)
        # - training: 25%
        # - testing: 25%
        # - aggregating: 5%
        phase_weights = {
            "fetching_klines": 0.05,
            "optimizing": 0.40,
            "training": 0.25,
            "testing": 0.25,
            "aggregating": 0.05,
            "processing_windows": 0.0  # Transition phase, no weight
        }
        
        phase_weight = phase_weights.get(self.current_phase, 0.25)  # Default to 25% if unknown
        phase_progress = self.phase_progress * phase_weight
        
        # Calculate progress: base + (phase_progress * phase_weight) / total_windows
        window_progress = (phase_progress / self.total_windows) * 100.0
        
        return min(100.0, base_progress + window_progress)


class WalkForwardTaskManager:
    """Manages walk-forward analysis tasks and their progress."""
    
    def __init__(self):
        self._tasks: Dict[str, WalkForwardProgress] = {}
        self._cancellation_flags: Dict[str, bool] = {}
        self._lock = asyncio.Lock()
    
    async def create_task(self, total_windows: int, user_id: str) -> str:
        """Create a new task and return its ID.
        
        Args:
            total_windows: Total number of windows in the analysis
            user_id: ID of the user creating this task (for isolation)
        
        Returns:
            Task ID (UUID string)
        """
        async with self._lock:
            task_id = str(uuid.uuid4())
            self._tasks[task_id] = WalkForwardProgress(
                task_id=task_id,
                user_id=user_id,
                status="running",
                total_windows=total_windows,
                start_time=datetime.now()
            )
            self._cancellation_flags[task_id] = False
            logger.info(f"Created walk-forward task {task_id} for user {user_id} with {total_windows} windows")
            return task_id
    
    async def update_progress(
        self,
        task_id: str,
        current_window: Optional[int] = None,
        current_phase: Optional[str] = None,
        message: Optional[str] = None,
        phase_progress: Optional[float] = None
    ) -> None:
        """Update progress for a task.
        
        All updates are atomic and protected by asyncio.Lock to ensure thread-safety
        when multiple coroutines update progress concurrently (e.g., optimization loop,
        window runner, SSE reader).
        
        Args:
            task_id: Task ID
            current_window: Current window number (0-indexed)
            current_phase: Current phase name
            message: Progress message
            phase_progress: Progress within current phase (0.0-1.0)
        """
        async with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Task {task_id} not found for progress update")
                return
            
            # Atomic update: all fields updated within the same lock
            progress = self._tasks[task_id]
            if current_window is not None:
                progress.current_window = current_window
            if current_phase is not None:
                progress.current_phase = current_phase
                # Reset phase_progress when phase changes
                if phase_progress is None:
                    progress.phase_progress = 0.0
            if message is not None:
                progress.message = message
            if phase_progress is not None:
                progress.phase_progress = max(0.0, min(1.0, phase_progress))  # Clamp to 0.0-1.0
            
            # Calculate estimated time remaining (atomic calculation)
            if progress.current_window > 0 and progress.start_time:
                elapsed = (datetime.now() - progress.start_time).total_seconds()
                avg_time_per_window = elapsed / progress.current_window
                remaining_windows = progress.total_windows - progress.current_window
                
                # Adjust for current phase progress
                if progress.phase_progress > 0:
                    # Estimate: remaining windows + (1 - phase_progress) of current window
                    remaining_work = remaining_windows + (1.0 - progress.phase_progress)
                else:
                    remaining_work = remaining_windows
                
                progress.estimated_time_remaining_seconds = avg_time_per_window * remaining_work
    
    async def get_progress(self, task_id: str) -> Optional[WalkForwardProgress]:
        """Get progress for a task."""
        async with self._lock:
            # Return a copy to avoid issues with comparison
            progress = self._tasks.get(task_id)
            if progress:
                # Create a new instance with same values for comparison
                return WalkForwardProgress(
                    task_id=progress.task_id,
                    user_id=progress.user_id,
                    status=progress.status,
                    current_window=progress.current_window,
                    total_windows=progress.total_windows,
                    current_phase=progress.current_phase,
                    message=progress.message,
                    start_time=progress.start_time,
                    estimated_time_remaining_seconds=progress.estimated_time_remaining_seconds,
                    error=progress.error,
                    result=progress.result
                )
            return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task. Returns True if task was found and cancelled."""
        async with self._lock:
            if task_id in self._cancellation_flags:
                self._cancellation_flags[task_id] = True
                if task_id in self._tasks:
                    self._tasks[task_id].status = "cancelled"
                    self._tasks[task_id].message = "Cancelled by user"
                logger.info(f"Cancelled walk-forward task {task_id}")
                return True
            return False
    
    def is_cancelled(self, task_id: str) -> bool:
        """Check if a task is cancelled (non-async for use in tight loops).
        
        Note: This is a read-only operation on a dict. In CPython, dict reads are atomic
        due to GIL, but for true thread-safety across event loops, consider using
        async is_cancelled_async() instead.
        """
        # Read-only dict access is generally safe in CPython due to GIL
        # but for cross-event-loop safety, this should be protected
        # For now, we rely on GIL for read safety in tight loops
        return self._cancellation_flags.get(task_id, False)
    
    async def is_cancelled_async(self, task_id: str) -> bool:
        """Thread-safe async version of is_cancelled."""
        async with self._lock:
            return self._cancellation_flags.get(task_id, False)
    
    async def complete_task(self, task_id: str, result: Optional[dict] = None) -> None:
        """Mark a task as completed."""
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = "completed"
                self._tasks[task_id].current_window = self._tasks[task_id].total_windows
                self._tasks[task_id].estimated_time_remaining_seconds = 0.0
                if result is not None:
                    self._tasks[task_id].result = result
                logger.info(f"Completed walk-forward task {task_id}")
    
    async def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = "error"
                self._tasks[task_id].error = error
                logger.error(f"Failed walk-forward task {task_id}: {error}")
    
    async def cleanup_task(self, task_id: str) -> None:
        """Remove a task (cleanup after completion or cancellation)."""
        async with self._lock:
            self._tasks.pop(task_id, None)
            self._cancellation_flags.pop(task_id, None)
            logger.debug(f"Cleaned up walk-forward task {task_id}")
    
    async def count_running_tasks(self) -> int:
        """Count the number of currently running tasks (across all users)."""
        async with self._lock:
            return sum(
                1 for task in self._tasks.values()
                if task.status == "running"
            )
    
    async def count_user_running_tasks(self, user_id: str) -> int:
        """Count the number of currently running tasks for a specific user."""
        async with self._lock:
            return sum(
                1 for task in self._tasks.values()
                if task.status == "running" and task.user_id == user_id
            )
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """Remove completed/cancelled/error tasks older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours for completed tasks to keep
        
        Returns:
            Number of tasks cleaned up
        """
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        async with self._lock:
            to_remove = [
                task_id for task_id, progress in self._tasks.items()
                if progress.status in ("completed", "cancelled", "error")
                and progress.start_time is not None
                and progress.start_time < cutoff
            ]
            for task_id in to_remove:
                self._tasks.pop(task_id, None)
                self._cancellation_flags.pop(task_id, None)
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old walk-forward tasks (older than {max_age_hours} hours)")
            return len(to_remove)
    
    async def get_user_tasks(self, user_id: str) -> list[WalkForwardProgress]:
        """Get all tasks for a specific user."""
        async with self._lock:
                return [
                    WalkForwardProgress(
                        task_id=task.task_id,
                        user_id=task.user_id,
                        status=task.status,
                        current_window=task.current_window,
                        total_windows=task.total_windows,
                        current_phase=task.current_phase,
                        message=task.message,
                        start_time=task.start_time,
                        estimated_time_remaining_seconds=task.estimated_time_remaining_seconds,
                        error=task.error,
                        result=task.result,
                        phase_progress=task.phase_progress
                    )
                    for task in self._tasks.values()
                    if task.user_id == user_id
                ]


# Global task manager instance
_task_manager = WalkForwardTaskManager()


def get_task_manager() -> WalkForwardTaskManager:
    """Get the global task manager instance."""
    return _task_manager

