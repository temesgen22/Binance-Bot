"""
Strategy Auto-Tuning Service

Automatically adjusts strategy parameters based on live performance metrics,
market conditions, and historical analysis.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Deque
from uuid import UUID

from loguru import logger
from pydantic import BaseModel, Field

from app.core.my_binance_client import BinanceClient
from app.services.strategy_service import StrategyService
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_statistics import StrategyStatistics
from app.services.database_service import DatabaseService
from app.models.strategy import StrategySummary
from app.core.exceptions import StrategyNotFoundError


# ============================================================================
# Pydantic Models
# ============================================================================

class PerformanceSnapshot(BaseModel):
    """Standardized performance metrics snapshot for comparison."""
    validation_return_pct_30d: float  # 30-day return in percent
    validation_sharpe_30d: float  # 30-day Sharpe ratio
    validation_win_rate_30d: float  # 30-day win rate (fraction 0.0-1.0)
    validation_drawdown_30d: float  # 30-day max drawdown (fraction 0.0-1.0)
    validation_profit_factor_30d: float  # 30-day profit factor
    total_trades_30d: int  # Number of trades in 30 days
    timestamp: datetime  # When snapshot was taken


class ValidationScore(BaseModel):
    """Composite validation score for parameter comparison."""
    score: float  # Composite score
    return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    
    @classmethod
    def calculate(
        cls,
        return_pct: float,
        sharpe_ratio: float,
        max_drawdown_pct: float,
        win_rate: float,
        weights: Optional[dict] = None
    ) -> "ValidationScore":
        """Calculate composite validation score.
        
        Formula: score = w1*return + w2*sharpe - w3*drawdown + w4*win_rate
        
        Default weights favor return and sharpe, penalize drawdown.
        """
        if weights is None:
            weights = {
                "return": 0.4,
                "sharpe": 0.3,
                "drawdown": 0.2,  # Penalty (subtracted)
                "win_rate": 0.1
            }
        
        # Normalize drawdown to fraction
        drawdown_frac = max_drawdown_pct / 100.0 if max_drawdown_pct > 1.0 else max_drawdown_pct
        
        score = (
            weights["return"] * return_pct +
            weights["sharpe"] * sharpe_ratio -
            weights["drawdown"] * (drawdown_frac * 100.0) +  # Penalty scaled
            weights["win_rate"] * (win_rate * 100.0 if win_rate <= 1.0 else win_rate)
        )
        
        return cls(
            score=score,
            return_pct=return_pct,
            sharpe_ratio=sharpe_ratio,
            max_drawdown_pct=max_drawdown_pct,
            win_rate=win_rate
        )


class AutoTuningConfig(BaseModel):
    """Auto-tuning configuration (per strategy).
    
    All thresholds use fractions (0.0-1.0) for consistency.
    """
    enabled: bool = Field(default=False)
    
    # Performance-based triggers (all in fractions: 0.0-1.0)
    min_trades: int = Field(ge=1, default=20)
    win_rate_threshold_frac: float = Field(ge=0.0, le=1.0, default=0.45)  # 45% as 0.45
    sharpe_threshold: float = Field(default=0.5)
    drawdown_threshold_frac: float = Field(ge=0.0, le=1.0, default=0.15)  # 15% as 0.15
    profit_factor_threshold: float = Field(gt=0.0, default=1.2)
    
    # Time-based triggers
    evaluation_period_days: int = Field(ge=1, default=7)
    min_time_between_tuning_hours: int = Field(ge=1, default=24)  # Cooldown period
    cooldown_from_successful_apply_hours: int = Field(ge=1, default=24)  # After successful apply
    min_hours_between_attempts: int = Field(ge=1, default=1)  # Throttle failed attempts
    
    # Debounce settings
    debounce_evaluations: int = Field(ge=1, default=3)  # Require condition true for N checks
    check_trade_frequency: bool = Field(default=False)  # Check for abnormal patterns
    
    # Tuning behavior
    require_wf_validation: bool = Field(default=False)
    min_improvement_pct: float = Field(ge=0.0, default=5.0)  # Relative improvement %
    min_improvement_abs_pct: float = Field(ge=0.0, default=1.0)  # Absolute minimum (must improve by at least +1%)
    
    # Safety
    wait_for_exit: bool = Field(default=True)
    
    # Market condition triggers
    adapt_to_market_regime: bool = Field(default=False)  # Adapt to trending vs ranging
    
    # Overfitting guardrails
    require_champion_validation: bool = Field(default=True)
    champion_validation_windows: int = Field(ge=1, default=3)
    hold_period_trades: int = Field(ge=1, default=50)
    hold_period_hours: int = Field(ge=1, default=168)  # 7 days
    max_ema_change: int = Field(ge=1, default=2)
    max_tp_sl_change_pct: float = Field(ge=0.0, default=10.0)


# ============================================================================
# Auto-Tuning Service
# ============================================================================

class AutoTuningService:
    """Service for automatically tuning strategy parameters."""
    
    def __init__(
        self,
        strategy_runner: StrategyRunner,
        strategy_service: StrategyService,
        strategy_statistics: StrategyStatistics,
        db_service: DatabaseService,
        client: BinanceClient,
        user_id: UUID
    ):
        """Initialize AutoTuningService.
        
        Args:
            strategy_runner: StrategyRunner instance
            strategy_service: StrategyService instance
            strategy_statistics: StrategyStatistics instance
            db_service: DatabaseService instance
            client: BinanceClient instance
            user_id: User UUID (required for multi-user mode)
        """
        self.strategy_runner = strategy_runner
        self.strategy_service = strategy_service
        self.strategy_statistics = strategy_statistics
        self.db_service = db_service
        self.client = client
        self.user_id = user_id
        
        # Debounce state tracking (per strategy)
        self._debounce_state: Dict[UUID, Deque[bool]] = {}
        self._normalization_logged: set = set()  # Track logged normalizations
    
    async def _resolve_strategy_uuid(self, strategy_id: str) -> UUID:
        """Resolve user-friendly strategy_id to UUID.
        
        Args:
            strategy_id: User's strategy identifier (string)
            
        Returns:
            Strategy UUID
            
        Raises:
            StrategyNotFoundError: If strategy doesn't exist
        """
        strategy = await self.strategy_service.async_get_strategy(self.user_id, strategy_id)
        if not strategy:
            raise StrategyNotFoundError(strategy_id)
        return strategy.id  # UUID from database
    
    def _normalize_fraction(self, value: float, field_name: str = "") -> float:
        """Normalize value to fraction (0.0-1.0).
        
        Rules:
        - If value > 1.0: assume percent, divide by 100
        - If value <= 1.0: assume fraction, use as-is
        - Log conversion once per strategy to help debugging
        
        Args:
            value: Raw value (could be percent or fraction)
            field_name: Field name for logging
            
        Returns:
            Normalized fraction (0.0-1.0)
        """
        if value is None:
            return 0.0
        
        original = value
        
        if value > 1.0:
            # Assume percent, convert to fraction
            normalized = value / 100.0
            # Log once per conversion
            log_key = f"{field_name}_{original}"
            if log_key not in self._normalization_logged:
                logger.info(f"Normalized {field_name} from {original}% to {normalized} (assumed percent)")
                self._normalization_logged.add(log_key)
            
            return normalized
        else:
            # Assume fraction, use as-is
            return value
    
    async def _get_tuning_config(self, strategy_uuid: UUID) -> AutoTuningConfig:
        """Get tuning configuration for a strategy.
        
        Args:
            strategy_uuid: Strategy UUID
            
        Returns:
            AutoTuningConfig instance
        """
        # Get strategy from database
        strategy = await self.strategy_service.async_get_strategy(
            self.user_id, str(strategy_uuid)
        )
        
        if strategy and strategy.meta and 'auto_tuning_config' in strategy.meta:
            try:
                return AutoTuningConfig(**strategy.meta['auto_tuning_config'])
            except Exception as e:
                logger.warning(f"Failed to parse auto_tuning_config for {strategy_uuid}: {e}")
        
        # Return default config
        return AutoTuningConfig()
    
    async def _get_last_tuning_time(self, strategy_uuid: UUID) -> Optional[datetime]:
        """Get timestamp of last successful parameter application (for cooldown).
        
        Args:
            strategy_uuid: Strategy UUID
            
        Returns:
            Timestamp of last successful apply, or None
        """
        last_change = await self.db_service.async_get_last_parameter_change(
            strategy_uuid=strategy_uuid,
            user_id=self.user_id,
            reason="auto_tuning",
            status="applied"
        )
        return last_change.created_at if last_change else None
    
    async def _get_last_attempt_time(self, strategy_uuid: UUID) -> Optional[datetime]:
        """Get timestamp of last tuning attempt (for throttling).
        
        Args:
            strategy_uuid: Strategy UUID
            
        Returns:
            Timestamp of last attempt, or None
        """
        # Get any auto-tuning attempt (including failed)
        last_attempt = await self.db_service.async_get_last_parameter_change(
            strategy_uuid=strategy_uuid,
            user_id=self.user_id,
            reason=None  # Any reason starting with "auto_tuning"
        )
        
        # Filter to auto-tuning reasons only
        if last_attempt and last_attempt.reason and last_attempt.reason.startswith("auto_tuning"):
            return last_attempt.created_at
        
        return None
    
    async def _check_debounce(
        self,
        strategy_uuid: UUID,
        config: AutoTuningConfig
    ) -> bool:
        """Check if condition has been true for N consecutive evaluations.
        
        Args:
            strategy_uuid: Strategy UUID
            config: AutoTuningConfig
            
        Returns:
            True if condition true for N consecutive checks
        """
        # Get or create debounce history
        if strategy_uuid not in self._debounce_state:
            self._debounce_state[strategy_uuid] = deque(maxlen=config.debounce_evaluations)
        
        history = self._debounce_state[strategy_uuid]
        
        # Check if we have enough history
        if len(history) < config.debounce_evaluations:
            # Not enough history, add current evaluation (True = should tune)
            history.append(True)
            logger.debug(f"Debounce: {len(history)}/{config.debounce_evaluations} evaluations")
            return False  # Not enough history, don't tune yet
        
        # Check if last N are all True
        recent = list(history)[-config.debounce_evaluations:]
        all_true = all(recent)
        
        if all_true:
            # Condition true for N consecutive checks, allow tuning
            history.clear()  # Reset after tuning
            return True
        else:
            # Not all true, add current and continue
            history.append(True)
            return False
    
    async def should_tune(self, strategy_id: str) -> bool:
        """Determine if strategy needs tuning with all trigger checks.
        
        Args:
            strategy_id: User's strategy identifier (string)
            
        Returns:
            True if strategy should be tuned
        """
        # Resolve UUID once at start
        strategy_uuid = await self._resolve_strategy_uuid(strategy_id)
        
        # Get current performance (use StrategyStatistics)
        stats = await asyncio.to_thread(
            self.strategy_statistics.calculate_strategy_stats,
            str(strategy_uuid)  # StrategyStatistics may need string ID
        )
        
        # Get tuning config
        config = await self._get_tuning_config(strategy_uuid)
        
        # 1. Check minimum trades
        if stats.total_trades < config.min_trades:
            logger.debug(f"Strategy {strategy_id} has {stats.total_trades} trades, need {config.min_trades}")
            return False
        
        # 2. Check cooldown from successful apply
        last_successful = await self._get_last_tuning_time(strategy_uuid)
        if last_successful:
            hours_since = (datetime.now(timezone.utc) - last_successful).total_seconds() / 3600
            if hours_since < config.cooldown_from_successful_apply_hours:
                logger.debug(f"Strategy {strategy_id} in cooldown: {hours_since:.1f}h < {config.cooldown_from_successful_apply_hours}h")
                return False
        
        # 3. Check throttle for failed attempts
        last_attempt = await self._get_last_attempt_time(strategy_uuid)
        if last_attempt:
            hours_since = (datetime.now(timezone.utc) - last_attempt).total_seconds() / 3600
            if hours_since < config.min_hours_between_attempts:
                logger.debug(f"Strategy {strategy_id} throttled: {hours_since:.1f}h < {config.min_hours_between_attempts}h")
                return False
        
        # 4. Normalize units (ensure fractions 0.0-1.0)
        win_rate = self._normalize_fraction(stats.win_rate, "win_rate")
        drawdown = self._normalize_fraction(
            stats.max_drawdown_pct if hasattr(stats, 'max_drawdown_pct') else 0.0,
            "max_drawdown_pct"
        )
        
        # 5. Check if any trigger condition is true
        trigger_condition = (
            win_rate < config.win_rate_threshold_frac or
            drawdown > config.drawdown_threshold_frac or
            (hasattr(stats, 'sharpe_ratio') and stats.sharpe_ratio < config.sharpe_threshold) or
            (hasattr(stats, 'profit_factor') and stats.profit_factor and stats.profit_factor < config.profit_factor_threshold)
        )
        
        if not trigger_condition:
            # Condition false, add to debounce history
            if strategy_uuid not in self._debounce_state:
                self._debounce_state[strategy_uuid] = deque(maxlen=config.debounce_evaluations)
            self._debounce_state[strategy_uuid].append(False)
            return False
        
        # 6. Condition true, check debounce
        if config.debounce_evaluations > 1:
            if not await self._check_debounce(strategy_uuid, config):
                return False
        
        # All checks passed, should tune
        logger.info(f"Strategy {strategy_id} should be tuned (trigger condition met)")
        return True
    
    async def _create_performance_snapshot(
        self,
        strategy_uuid: UUID,
        days: int = 30
    ) -> PerformanceSnapshot:
        """Create performance snapshot for comparison.
        
        Args:
            strategy_uuid: Strategy UUID
            days: Number of days to look back
            
        Returns:
            PerformanceSnapshot with 30-day metrics
        """
        # Get strategy stats
        stats = await asyncio.to_thread(
            self.strategy_statistics.calculate_strategy_stats,
            str(strategy_uuid)
        )
        
        # Get trades from last N days
        start_time = datetime.now(timezone.utc) - timedelta(days=days)
        end_time = datetime.now(timezone.utc)
        
        # Get trades from database filtered by date
        db_trades = await self.db_service.async_get_user_trades(
            user_id=self.user_id,
            strategy_id=strategy_uuid,
            limit=10000,  # Large limit to get all trades in period
            start_time=start_time,
            end_time=end_time
        )
        
        trades_30d = db_trades
        
        # Calculate metrics
        return_pct = getattr(stats, 'total_return_pct', 0.0) if hasattr(stats, 'total_return_pct') else 0.0
        sharpe = getattr(stats, 'sharpe_ratio', 0.0) if hasattr(stats, 'sharpe_ratio') else 0.0
        win_rate = self._normalize_fraction(stats.win_rate, "win_rate")
        drawdown = self._normalize_fraction(
            stats.max_drawdown_pct if hasattr(stats, 'max_drawdown_pct') else 0.0,
            "max_drawdown_pct"
        )
        profit_factor = getattr(stats, 'profit_factor', 0.0) if hasattr(stats, 'profit_factor') else 0.0
        
        return PerformanceSnapshot(
            validation_return_pct_30d=return_pct,
            validation_sharpe_30d=sharpe,
            validation_win_rate_30d=win_rate,
            validation_drawdown_30d=drawdown,
            validation_profit_factor_30d=profit_factor,
            total_trades_30d=stats.total_trades,
            timestamp=datetime.now(timezone.utc)
        )
    
    def _calculate_required_improvement(
        self,
        baseline_score: float,
        config: AutoTuningConfig
    ) -> float:
        """Calculate required improvement with absolute floor.
        
        Args:
            baseline_score: Current validation score
            config: AutoTuningConfig
            
        Returns:
            Required improvement amount
        """
        # Relative improvement
        relative_improvement = abs(baseline_score) * (config.min_improvement_pct / 100.0)
        
        # Use maximum of relative and absolute
        required = max(config.min_improvement_abs_pct, relative_improvement)
        
        return required
    
    async def _generate_analyze_params(self, current_params: dict) -> dict:
        """Generate parameter value ranges for sensitivity analysis.
        
        Args:
            current_params: Current parameter dictionary
            
        Returns:
            Dictionary of parameter ranges for analysis
        """
        analyze_params = {}
        
        # EMA parameters: test ±20% around current value
        if 'ema_fast' in current_params:
            base = int(current_params['ema_fast'])
            analyze_params['ema_fast'] = [
                max(1, int(base * 0.8)),
                base,
                min(200, int(base * 1.2))
            ]
        
        if 'ema_slow' in current_params:
            base = int(current_params['ema_slow'])
            analyze_params['ema_slow'] = [
                max(2, int(base * 0.8)),
                base,
                min(400, int(base * 1.2))
            ]
        
        # TP/SL: test ±25% around current value
        if 'take_profit_pct' in current_params:
            base = float(current_params['take_profit_pct'])
            analyze_params['take_profit_pct'] = [
                max(0.001, base * 0.75),
                base,
                min(0.1, base * 1.25)
            ]
        
        if 'stop_loss_pct' in current_params:
            base = float(current_params['stop_loss_pct'])
            analyze_params['stop_loss_pct'] = [
                max(0.001, base * 0.75),
                base,
                min(0.1, base * 1.25)
            ]
        
        return analyze_params
    
    async def _build_sensitivity_analysis_request(
        self,
        strategy: StrategySummary,
        current_params: dict,
        days: int = 30
    ):
        """Build SensitivityAnalysisRequest from strategy.
        
        Args:
            strategy: StrategySummary
            current_params: Current parameters
            days: Number of days for analysis
            
        Returns:
            SensitivityAnalysisRequest
        """
        from app.services.sensitivity_analysis import SensitivityAnalysisRequest
        
        # Generate parameter ranges
        analyze_params = await self._generate_analyze_params(current_params)
        
        return SensitivityAnalysisRequest(
            symbol=strategy.symbol,
            strategy_type=strategy.strategy_type,
            name=f"Auto-tuning for {strategy.name}",
            start_time=datetime.now(timezone.utc) - timedelta(days=days),
            end_time=datetime.now(timezone.utc),
            base_params=current_params.copy(),
            analyze_params=analyze_params,
            leverage=strategy.leverage,
            risk_per_trade=float(strategy.risk_per_trade),
            fixed_amount=float(strategy.fixed_amount) if strategy.fixed_amount else None,
            initial_balance=1000.0,  # TODO: Get from config/strategy
            metric="sharpe_ratio",  # Optimize for Sharpe
            kline_interval=current_params.get("kline_interval", "5m")
        )
    
    async def _run_sensitivity_analysis(
        self,
        strategy_uuid: UUID,
        current_params: dict,
        days: int = 30
    ):
        """Run sensitivity analysis to find optimal parameters.
        
        Args:
            strategy_uuid: Strategy UUID
            current_params: Current parameters
            days: Number of days for analysis
            
        Returns:
            SensitivityAnalysisResult
        """
        from app.services.sensitivity_analysis import run_sensitivity_analysis
        
        strategy = await self.strategy_service.async_get_strategy(
            self.user_id, str(strategy_uuid)
        )
        
        # Build request
        request = await self._build_sensitivity_analysis_request(
            strategy, current_params, days=days
        )
        
        # Run analysis
        result = await run_sensitivity_analysis(
            request,
            self.client,
            task_id=None,
            progress_callback=None
        )
        
        return result
    
    async def tune_strategy(self, strategy_id: str) -> dict:
        """Execute full tuning cycle for a strategy.
        
        Args:
            strategy_id: User's strategy identifier (string)
            
        Returns:
            Dictionary with tuning results
        """
        # Resolve UUID once at start
        strategy_uuid = await self._resolve_strategy_uuid(strategy_id)
        
        logger.info(f"Starting auto-tuning for strategy {strategy_id} ({strategy_uuid})")
        
        try:
            # 1. Get current strategy and params
            strategy = await self.strategy_service.async_get_strategy(
                self.user_id, strategy_id
            )
            current_params = strategy.params.model_dump() if hasattr(strategy.params, "model_dump") else dict(strategy.params)
            
            # 2. Create performance snapshot
            performance_metrics = await self._create_performance_snapshot(strategy_uuid, days=30)
            
            # 3. Run sensitivity analysis
            logger.info(f"Running sensitivity analysis for {strategy_id}")
            sensitivity_result = await self._run_sensitivity_analysis(
                strategy_uuid, current_params, days=30
            )
            
            if not sensitivity_result.recommended_params:
                return {
                    "status": "no_recommendations",
                    "strategy_id": strategy_id,
                    "message": "Sensitivity analysis did not produce recommendations"
                }
            
            recommended_params = sensitivity_result.recommended_params
            
            # 4. Create current validation score
            current_score = ValidationScore.calculate(
                return_pct=performance_metrics.validation_return_pct_30d,
                sharpe_ratio=performance_metrics.validation_sharpe_30d,
                max_drawdown_pct=performance_metrics.validation_drawdown_30d * 100.0,  # Convert to percent
                win_rate=performance_metrics.validation_win_rate_30d
            )
            
            # 5. Validate with backtest (quick check)
            logger.info(f"Validating recommended parameters for {strategy_id}")
            from app.services.backtest_service import BacktestService, BacktestRequest
            
            backtest_service = BacktestService(self.client)
            backtest_request = BacktestRequest(
                symbol=strategy.symbol,
                strategy_type=strategy.strategy_type,
                start_time=datetime.now(timezone.utc) - timedelta(days=30),
                end_time=datetime.now(timezone.utc),
                params=recommended_params,
                leverage=strategy.leverage,
                risk_per_trade=float(strategy.risk_per_trade),
                fixed_amount=float(strategy.fixed_amount) if strategy.fixed_amount else None,
                initial_balance=1000.0
            )
            
            backtest_result = await backtest_service.run_backtest(backtest_request, pre_fetched_klines=None)
            
            # Calculate challenger score
            # Normalize win_rate (backtest returns it as percent, convert to fraction)
            win_rate_frac = backtest_result.win_rate / 100.0 if backtest_result.win_rate > 1.0 else backtest_result.win_rate
            
            challenger_score = ValidationScore.calculate(
                return_pct=backtest_result.total_return_pct,
                sharpe_ratio=getattr(backtest_result, 'sharpe_ratio', 0.0),
                max_drawdown_pct=backtest_result.max_drawdown_pct,
                win_rate=win_rate_frac
            )
            
            # Compare scores (with minimum improvement)
            config = await self._get_tuning_config(strategy_uuid)
            required_improvement = self._calculate_required_improvement(
                current_score.score,
                config
            )
            
            if challenger_score.score >= (current_score.score + required_improvement):
                logger.info(
                    f"Challenger wins: {challenger_score.score:.2f} >= "
                    f"{current_score.score + required_improvement:.2f}"
                )
                
                # 6. Apply parameters if better
                success = await self._update_strategy_parameters(
                    strategy_id,
                    recommended_params,
                    reason="auto_tuning"
                )
                
                if success:
                    return {
                        "status": "success",
                        "strategy_id": strategy_id,
                        "recommended_params": recommended_params,
                        "current_score": current_score.score,
                        "challenger_score": challenger_score.score,
                        "improvement": challenger_score.score - current_score.score,
                        "message": "Parameters updated successfully"
                    }
                else:
                    return {
                        "status": "update_failed",
                        "strategy_id": strategy_id,
                        "message": "Parameters validated but update failed"
                    }
            else:
                logger.info(
                    f"Challenger loses: {challenger_score.score:.2f} < "
                    f"{current_score.score + required_improvement:.2f}"
                )
                return {
                    "status": "no_improvement",
                    "strategy_id": strategy_id,
                    "current_score": current_score.score,
                    "challenger_score": challenger_score.score,
                    "required_improvement": required_improvement,
                    "message": "Recommended parameters did not meet improvement threshold"
                }
            
        except Exception as e:
            logger.error(f"Error in tuning cycle for {strategy_id}: {e}", exc_info=True)
            await self._log_tuning_failure(strategy_uuid, reason="execution_error", message=str(e))
            return {
                "status": "error",
                "strategy_id": strategy_id,
                "message": f"Tuning failed: {str(e)}"
            }
    
    async def _update_strategy_parameters(
        self,
        strategy_id: str,
        new_params: dict,
        reason: str
    ) -> bool:
        """Safely update strategy parameters.
        
        Args:
            strategy_id: User's strategy identifier (string)
            new_params: New parameter dictionary
            reason: Reason for update (e.g., "auto_tuning")
            
        Returns:
            True if update successful, False otherwise
        """
        # Resolve UUID once at start
        strategy_uuid = await self._resolve_strategy_uuid(strategy_id)
        
        # Get current strategy state
        strategy = await self.strategy_service.async_get_strategy(
            self.user_id, strategy_id
        )
        
        # Check if in position (optional: wait for exit)
        config = await self._get_tuning_config(strategy_uuid)
        if strategy.position_side and config.wait_for_exit:
            logger.info(f"Strategy {strategy_id} in position, waiting for exit before update")
            exit_ok = await self._wait_for_position_exit(strategy_uuid, timeout=3600)
            if not exit_ok:
                logger.error(f"Aborting parameter update: position did not exit within timeout")
                await self._log_tuning_failure(strategy_uuid, reason="position_timeout")
                return False
        
        # Validate new parameters
        try:
            validated_params = self._validate_parameters(new_params, strategy.strategy_type)
            new_params = validated_params  # Use validated (coerced) params
        except ValueError as e:
            logger.error(f"Parameter validation failed: {e}")
            await self._log_tuning_failure(strategy_uuid, reason="validation_error", message=str(e))
            return False
        
        # Save current params as backup
        old_params = strategy.params.model_dump() if hasattr(strategy.params, "model_dump") else dict(strategy.params)
        changed_params = {
            k: {"old": old_params.get(k), "new": new_params.get(k)}
            for k in set(old_params.keys()) | set(new_params.keys())
            if old_params.get(k) != new_params.get(k)
        }
        
        # Create performance snapshot before change
        performance_before = await self._create_performance_snapshot(strategy_uuid, days=30)
        
        # Save parameter backup to history
        history_record = await self.db_service.async_create_parameter_history(
            strategy_uuid=strategy_uuid,
            user_id=self.user_id,
            old_params=old_params,
            new_params=new_params,
            changed_params=changed_params,
            reason=reason,
            status="applied",
            performance_before=performance_before.model_dump(),
            strategy_label=strategy.strategy_id  # User's strategy identifier
        )
        
        # Hot-swap parameters (if running)
        if strategy.status == "running":
            # Prefer hot-swap if available
            if hasattr(self.strategy_runner, 'update_strategy_params'):
                try:
                    await self.strategy_runner.update_strategy_params(strategy_uuid, new_params)
                    logger.info(f"Hot-swapped parameters for strategy {strategy_id}")
                except Exception as e:
                    logger.error(f"Hot-swap failed for {strategy_id}: {e}")
                    return False
            else:
                # Fallback: stop and restart (with proper state machine checks)
                logger.warning(f"Hot-swap not available, using stop/start for {strategy_id}")
                # TODO: Implement safe stop/start
                return False
        else:
            # Strategy not running, just update DB
            await asyncio.to_thread(
                self.strategy_service.update_strategy,
                self.user_id,
                strategy_id,
                params=new_params
            )
        
        # Parameter change already logged in history_record above
        logger.info(f"Parameter update logged: history_id={history_record.id}")
        
        return True
    
    async def _wait_for_position_exit(
        self,
        strategy_uuid: UUID,
        timeout: int = 3600
    ) -> bool:
        """Wait for strategy to exit position before updating params.
        
        Args:
            strategy_uuid: Strategy UUID
            timeout: Maximum wait time in seconds
            
        Returns:
            True if position exited, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            strategy = await self.strategy_service.async_get_strategy(
                self.user_id, str(strategy_uuid)
            )
            
            if not strategy.position_side:
                logger.info(f"Strategy {strategy_uuid} exited position, safe to update")
                return True
            
            await asyncio.sleep(10)  # Check every 10 seconds
        
        logger.warning(f"Timeout waiting for position exit for {strategy_uuid} after {timeout}s")
        return False
    
    def _validate_parameters(self, params: dict, strategy_type: str) -> dict:
        """Validate parameters are within safe ranges and constraints.
        
        Args:
            params: Parameter dictionary to validate
            strategy_type: Strategy type (e.g., "scalping", "range_mean_reversion")
            
        Returns:
            Validated parameter dictionary
            
        Raises:
            ValueError: If validation fails
        """
        # Basic validation - check required params exist
        if strategy_type == "scalping":
            # Validate EMA parameters
            if "ema_fast" in params:
                ema_fast = int(params["ema_fast"])
                if not (1 <= ema_fast <= 200):
                    raise ValueError(f"ema_fast must be between 1 and 200, got {ema_fast}")
                params["ema_fast"] = ema_fast
            
            if "ema_slow" in params:
                ema_slow = int(params["ema_slow"])
                if not (2 <= ema_slow <= 400):
                    raise ValueError(f"ema_slow must be between 2 and 400, got {ema_slow}")
                params["ema_slow"] = ema_slow
                
                # Check ema_slow > ema_fast
                if "ema_fast" in params and ema_slow <= params["ema_fast"]:
                    raise ValueError(f"ema_slow ({ema_slow}) must be greater than ema_fast ({params['ema_fast']})")
            
            # Validate TP/SL
            if "take_profit_pct" in params:
                tp = float(params["take_profit_pct"])
                if not (0 < tp <= 0.1):
                    raise ValueError(f"take_profit_pct must be between 0 and 0.1, got {tp}")
                params["take_profit_pct"] = tp
            
            if "stop_loss_pct" in params:
                sl = float(params["stop_loss_pct"])
                if not (0 < sl <= 0.1):
                    raise ValueError(f"stop_loss_pct must be between 0 and 0.1, got {sl}")
                params["stop_loss_pct"] = sl
                
                # Check TP > SL
                if "take_profit_pct" in params and params["take_profit_pct"] <= sl:
                    raise ValueError(f"take_profit_pct ({params['take_profit_pct']}) should be greater than stop_loss_pct ({sl})")
        
        elif strategy_type == "range_mean_reversion":
            # Validate range parameters
            if "lookback_period" in params:
                lookback = int(params["lookback_period"])
                if not (50 <= lookback <= 500):
                    raise ValueError(f"lookback_period must be between 50 and 500, got {lookback}")
                params["lookback_period"] = lookback
        
        return params
    
    async def _log_tuning_failure(
        self,
        strategy_uuid: UUID,
        reason: str,
        message: str
    ) -> None:
        """Log tuning failure for debugging.
        
        Args:
            strategy_uuid: Strategy UUID
            reason: Failure reason code
            message: Failure message
        """
        try:
            # Get strategy for label
            strategy = await self.strategy_service.async_get_strategy(
                self.user_id, str(strategy_uuid)
            )
            strategy_label = strategy.strategy_id if strategy else None
            
            # Log to database
            await self.db_service.async_create_parameter_history(
                strategy_uuid=strategy_uuid,
                user_id=self.user_id,
                old_params={},
                new_params={},
                changed_params={},
                reason=f"auto_tuning_failed_{reason}",
                status="failed",
                failure_reason=message,
                strategy_label=strategy_label
            )
            logger.error(f"Tuning failure logged for {strategy_uuid}: {reason} - {message}")
        except Exception as e:
            logger.error(f"Failed to log tuning failure to database: {e}")
            # Still log to console
            logger.error(f"Tuning failed for {strategy_uuid}: {reason} - {message}")

