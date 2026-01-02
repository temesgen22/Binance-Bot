"""
Performance Evaluation Service for Auto-Tuning

Evaluates performance after parameter changes to update performance_after fields.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from loguru import logger

from app.services.auto_tuning_service import AutoTuningService, PerformanceSnapshot
from app.services.database_service import DatabaseService
from app.models.db_models import StrategyParameterHistory


class AutoTuningEvaluator:
    """Evaluates performance after parameter changes.
    
    Periodically checks parameter history records and updates performance_after
    when the hold period has elapsed.
    """
    
    def __init__(
        self,
        auto_tuning_service: AutoTuningService,
        db_service: DatabaseService
    ):
        """Initialize AutoTuningEvaluator.
        
        Args:
            auto_tuning_service: AutoTuningService instance
            db_service: DatabaseService instance
        """
        self.auto_tuning_service = auto_tuning_service
        self.db_service = db_service
        self._evaluation_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self, interval_hours: int = 6) -> None:
        """Start background evaluation task.
        
        Args:
            interval_hours: How often to check for evaluations (default: 6 hours)
        """
        if self._running:
            logger.warning("AutoTuningEvaluator already running")
            return
        
        self._running = True
        self._evaluation_task = asyncio.create_task(
            self._evaluation_loop(interval_hours)
        )
        logger.info(f"Started AutoTuningEvaluator (check interval: {interval_hours}h)")
    
    async def stop(self) -> None:
        """Stop background evaluation task."""
        if not self._running:
            return
        
        self._running = False
        if self._evaluation_task:
            self._evaluation_task.cancel()
            try:
                await self._evaluation_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped AutoTuningEvaluator")
    
    async def _evaluation_loop(self, interval_hours: int) -> None:
        """Main evaluation loop.
        
        Args:
            interval_hours: How often to check for evaluations
        """
        while self._running:
            try:
                await self.evaluate_pending_records()
                await asyncio.sleep(interval_hours * 3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in evaluation loop: {e}", exc_info=True)
                # Retry after 1 hour on error
                await asyncio.sleep(3600)
    
    async def evaluate_pending_records(self) -> int:
        """Evaluate all pending parameter history records.
        
        Returns:
            Number of records evaluated
        """
        logger.info("Starting evaluation of pending parameter history records")
        
        # Get all records that:
        # 1. Have status='applied' (successful parameter change)
        # 2. Have performance_before (we can compare)
        # 3. Don't have performance_after yet (not evaluated)
        # 4. Were created at least hold_period_days ago
        
        # Default hold period: 7 days
        hold_period_days = 7
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=hold_period_days)
        
        # Query database for pending records
        # Note: We'll need to add a method to DatabaseService for this query
        pending_records = await self._get_pending_evaluation_records(cutoff_date)
        
        if not pending_records:
            logger.debug("No pending evaluation records found")
            return 0
        
        logger.info(f"Found {len(pending_records)} pending evaluation records")
        
        evaluated_count = 0
        for record in pending_records:
            try:
                success = await self.evaluate_record(record)
                if success:
                    evaluated_count += 1
            except Exception as e:
                logger.error(
                    f"Error evaluating record {record.id}: {e}",
                    exc_info=True
                )
        
        logger.info(f"Evaluated {evaluated_count}/{len(pending_records)} records")
        return evaluated_count
    
    async def _get_pending_evaluation_records(
        self,
        cutoff_date: datetime
    ) -> List[StrategyParameterHistory]:
        """Get pending evaluation records from database.
        
        Args:
            cutoff_date: Only evaluate records older than this date
            
        Returns:
            List of StrategyParameterHistory records
        """
        # Query for records that need evaluation
        # This is a simplified query - in production, you'd want to add
        # a proper method to DatabaseService
        
        if self.db_service._is_async:
            from sqlalchemy import select
            from sqlalchemy import and_
            
            stmt = select(StrategyParameterHistory).filter(
                and_(
                    StrategyParameterHistory.status == "applied",
                    StrategyParameterHistory.performance_before.isnot(None),
                    StrategyParameterHistory.performance_after.is_(None),
                    StrategyParameterHistory.created_at <= cutoff_date
                )
            ).order_by(StrategyParameterHistory.created_at.asc())
            
            result = await self.db_service.db.execute(stmt)
            return list(result.scalars().all())
        else:
            # Sync version
            return self.db_service.db.query(StrategyParameterHistory).filter(
                StrategyParameterHistory.status == "applied",
                StrategyParameterHistory.performance_before.isnot(None),
                StrategyParameterHistory.performance_after.is_(None),
                StrategyParameterHistory.created_at <= cutoff_date
            ).order_by(StrategyParameterHistory.created_at.asc()).all()
    
    async def evaluate_record(
        self,
        record: StrategyParameterHistory
    ) -> bool:
        """Evaluate a single parameter history record.
        
        Args:
            record: StrategyParameterHistory record to evaluate
            
        Returns:
            True if evaluation successful, False otherwise
        """
        logger.info(f"Evaluating parameter change record {record.id} for strategy {record.strategy_uuid}")
        
        try:
            # Calculate days since parameter change
            days_since_change = (datetime.now(timezone.utc) - record.created_at).days
            
            # Use same evaluation period as before (30 days) or since change, whichever is smaller
            evaluation_days = min(30, days_since_change)
            
            if evaluation_days < 7:
                logger.debug(
                    f"Record {record.id} only {days_since_change} days old, "
                    f"skipping (minimum 7 days required)"
                )
                return False
            
            # Create performance snapshot after change
            performance_after = await self.auto_tuning_service._create_performance_snapshot(
                record.strategy_uuid,
                days=evaluation_days
            )
            
            # Update record with performance_after
            updated_record = await self.db_service.async_update_parameter_history(
                history_id=record.id,
                performance_after=performance_after.model_dump()
            )
            
            if updated_record:
                logger.info(
                    f"Updated performance_after for record {record.id}: "
                    f"return={performance_after.validation_return_pct_30d:.2f}%, "
                    f"sharpe={performance_after.validation_sharpe_30d:.2f}"
                )
                
                # Optional: Compare before/after and log result
                if record.performance_before:
                    before_dict = record.performance_before
                    after_dict = performance_after.model_dump()
                    
                    before_return = before_dict.get('validation_return_pct_30d', 0.0)
                    after_return = after_dict.get('validation_return_pct_30d', 0.0)
                    
                    improvement = after_return - before_return
                    logger.info(
                        f"Performance comparison for record {record.id}: "
                        f"before={before_return:.2f}%, after={after_return:.2f}%, "
                        f"improvement={improvement:+.2f}%"
                    )
                
                return True
            else:
                logger.warning(f"Failed to update record {record.id}")
                return False
                
        except Exception as e:
            logger.error(
                f"Error evaluating record {record.id}: {e}",
                exc_info=True
            )
            return False
    
    async def evaluate_strategy(
        self,
        strategy_uuid: UUID,
        force: bool = False
    ) -> Optional[dict]:
        """Manually evaluate a specific strategy's recent parameter changes.
        
        Args:
            strategy_uuid: Strategy UUID
            force: If True, evaluate even if hold period hasn't elapsed
            
        Returns:
            Evaluation result dictionary, or None if no records found
        """
        logger.info(f"Manual evaluation requested for strategy {strategy_uuid}")
        
        # Get most recent applied parameter change
        record = await self.db_service.async_get_last_parameter_change(
            strategy_uuid=strategy_uuid,
            user_id=self.auto_tuning_service.user_id,
            reason=None,  # Any reason
            status="applied"
        )
        
        if not record:
            logger.info(f"No applied parameter changes found for strategy {strategy_uuid}")
            return None
        
        # Check if already evaluated
        if record.performance_after and not force:
            logger.info(f"Record {record.id} already evaluated")
            return {
                "record_id": str(record.id),
                "already_evaluated": True,
                "performance_after": record.performance_after
            }
        
        # Check hold period
        days_since_change = (datetime.now(timezone.utc) - record.created_at).days
        if days_since_change < 7 and not force:
            logger.info(
                f"Record {record.id} only {days_since_change} days old, "
                f"hold period not elapsed (use force=True to override)"
            )
            return {
                "record_id": str(record.id),
                "hold_period_not_elapsed": True,
                "days_since_change": days_since_change,
                "required_days": 7
            }
        
        # Evaluate
        success = await self.evaluate_record(record)
        
        if success:
            # Refresh record to get updated performance_after
            updated_record = await self.db_service.async_get_last_parameter_change(
                strategy_uuid=strategy_uuid,
                user_id=self.auto_tuning_service.user_id,
                reason=None,
                status="applied"
            )
            
            return {
                "record_id": str(record.id),
                "evaluated": True,
                "performance_after": updated_record.performance_after if updated_record else None,
                "days_since_change": days_since_change
            }
        else:
            return {
                "record_id": str(record.id),
                "evaluated": False,
                "error": "Evaluation failed"
            }














