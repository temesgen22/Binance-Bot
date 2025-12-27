"""Strategy registry for building strategy instances from types."""

from typing import Dict, TYPE_CHECKING

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.models.strategy import StrategyType
from app.strategies.base import Strategy, StrategyContext

if TYPE_CHECKING:
    pass


class StrategyRegistry:
    """Registry for mapping strategy types to their implementations."""
    
    def __init__(self) -> None:
        """Initialize the strategy registry with available strategy types."""
        # Lazy import to avoid circular dependencies
        from app.strategies.scalping import EmaScalpingStrategy
        from app.strategies.range_mean_reversion import RangeMeanReversionStrategy
        
        self._registry: Dict[str, type[Strategy]] = {
            StrategyType.scalping.value: EmaScalpingStrategy,
            # ema_crossover is now an alias for scalping with default 5/20 EMA
            # Users can achieve the same by setting ema_fast=5, ema_slow=20 in params
            StrategyType.ema_crossover.value: EmaScalpingStrategy,
            StrategyType.range_mean_reversion.value: RangeMeanReversionStrategy,
        }

    def build(self, strategy_type: StrategyType, context: StrategyContext, client: BinanceClient) -> Strategy:
        """Build a strategy instance from type.
        
        Args:
            strategy_type: The type of strategy to build
            context: Strategy context with configuration
            client: Binance client for the strategy
            
        Returns:
            Strategy instance
            
        Raises:
            ValueError: If strategy type is not supported or initialization fails
        """
        try:
            implementation = self._registry[strategy_type.value]
        except KeyError as exc:
            available = list(self._registry.keys())
            raise ValueError(
                f"Unsupported strategy type: {strategy_type}. "
                f"Available types: {', '.join(available)}"
            ) from exc
        try:
            return implementation(context, client)
        except Exception as exc:
            logger.exception(f"Failed to build strategy {strategy_type}: {exc}")
            raise ValueError(f"Failed to initialize strategy {strategy_type}: {exc}") from exc
