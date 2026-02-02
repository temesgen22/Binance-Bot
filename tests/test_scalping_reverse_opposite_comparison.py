"""
Comprehensive test to verify Scalping and Reverse Scalping produce opposite values.

This test verifies:
1. Both strategies receive the same market data
2. They take opposite positions on the same signals
3. Their win rates are opposite (when one wins, the other loses)
4. Their profits are opposite (same magnitude, opposite direction)
5. Trade counts match (same number of trades)
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from typing import List, Dict, Tuple
from collections import deque

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.reverse_scalping import ReverseScalpingStrategy
from app.strategies.base import StrategyContext, StrategySignal
from app.core.my_binance_client import BinanceClient


def create_klines(prices: List[float], start_time: int = 0, interval_ms: int = 60000) -> List[List]:
    """Create klines from price list."""
    klines = []
    for idx, price in enumerate(prices):
        open_time = start_time + (idx * interval_ms)
        close_time = open_time + interval_ms
        klines.append([
            open_time,            # open_time
            price,                # open
            price + 0.5,          # high
            price - 0.5,          # low
            price,                # close
            100.0,                # volume
            close_time,           # close_time
            0, 0, 0, 0, 0        # placeholders
        ])
    return klines


@pytest.fixture
def mock_client():
    """Create a mock BinanceClient."""
    client = MagicMock(spec=BinanceClient)
    client.get_price = MagicMock(return_value=50000.0)
    client.get_klines = MagicMock(return_value=[])
    return client


@pytest.fixture
def base_context():
    """Base strategy context for testing."""
    return StrategyContext(
        id="test-comparison",
        name="Test Comparison",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 5,
            "ema_slow": 10,
            "take_profit_pct": 0.01,  # 1% TP
            "stop_loss_pct": 0.005,  # 0.5% SL
            "kline_interval": "1m",
            "enable_short": True,
            "min_ema_separation": 0.0,  # Disable for simpler tests
            "enable_htf_bias": False,  # Disable for simpler tests
            "cooldown_candles": 0,  # Disable for simpler tests
            "enable_ema_cross_exit": True,
            "interval_seconds": 10,
        },
        interval_seconds=10,
    )


class TradeTracker:
    """Track trades for both strategies."""
    
    def __init__(self):
        self.scalping_trades: List[Dict] = []
        self.reverse_trades: List[Dict] = []
        self.scalping_positions: List[Dict] = []
        self.reverse_positions: List[Dict] = []
    
    def record_signal(self, strategy_name: str, signal: StrategySignal, price: float):
        """Record a signal from a strategy."""
        if signal.action in ["BUY", "SELL"]:
            trade = {
                "action": signal.action,
                "position_side": signal.position_side,
                "price": price,
                "exit_reason": signal.exit_reason,
            }
            if strategy_name == "scalping":
                self.scalping_trades.append(trade)
            else:
                self.reverse_trades.append(trade)
    
    def record_position(self, strategy_name: str, position: str, entry_price: float, current_price: float):
        """Record position state."""
        pos_data = {
            "position": position,
            "entry_price": entry_price,
            "current_price": current_price,
        }
        if strategy_name == "scalping":
            self.scalping_positions.append(pos_data)
        else:
            self.reverse_positions.append(pos_data)
    
    def calculate_pnl(self, strategy_name: str) -> float:
        """Calculate total PnL from completed trades."""
        trades = self.scalping_trades if strategy_name == "scalping" else self.reverse_trades
        total_pnl = 0.0
        
        # Pair entry and exit trades
        i = 0
        while i < len(trades) - 1:
            entry = trades[i]
            exit_trade = trades[i + 1]
            
            if entry["action"] == "BUY" and exit_trade["action"] == "SELL":
                # LONG position
                pnl = (exit_trade["price"] - entry["price"]) * 1.0  # Assume quantity = 1
                total_pnl += pnl
                i += 2
            elif entry["action"] == "SELL" and exit_trade["action"] == "BUY":
                # SHORT position
                pnl = (entry["price"] - exit_trade["price"]) * 1.0  # Assume quantity = 1
                total_pnl += pnl
                i += 2
            else:
                i += 1
        
        return total_pnl
    
    def calculate_win_rate(self, strategy_name: str) -> Tuple[float, int, int]:
        """Calculate win rate from completed trades."""
        trades = self.scalping_trades if strategy_name == "scalping" else self.reverse_trades
        wins = 0
        losses = 0
        
        # Pair entry and exit trades
        i = 0
        while i < len(trades) - 1:
            entry = trades[i]
            exit_trade = trades[i + 1]
            
            if entry["action"] == "BUY" and exit_trade["action"] == "SELL":
                # LONG position
                pnl = exit_trade["price"] - entry["price"]
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1
                i += 2
            elif entry["action"] == "SELL" and exit_trade["action"] == "BUY":
                # SHORT position
                pnl = entry["price"] - exit_trade["price"]
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1
                i += 2
            else:
                i += 1
        
        total = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 0.0
        return win_rate, wins, losses


@pytest.mark.ci
class TestScalpingReverseOppositeComparison:
    """Test that scalping and reverse scalping produce opposite values."""
    
    @pytest.mark.asyncio
    async def test_opposite_positions_same_signals(self, mock_client, base_context):
        """Test that both strategies take opposite positions on the same signals."""
        # Create price series with clear EMA crossovers
        # Start with falling trend (death cross), then rising trend (golden cross)
        prices = [50000.0] * 5 + [49900.0] * 5 + [49800.0] * 5 + [49900.0] * 5 + [50000.0] * 5
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        # Create both strategies
        scalping = EmaScalpingStrategy(base_context, mock_client)
        reverse = ReverseScalpingStrategy(base_context, mock_client)
        
        # Initialize both strategies
        scalping.prev_fast = None
        scalping.prev_slow = None
        reverse.prev_fast = None
        reverse.prev_slow = None
        
        tracker = TradeTracker()
        
        # Process candles one by one
        for i in range(len(klines)):
            candle = klines[i]
            current_price = float(candle[4])  # close price
            mock_client.get_price.return_value = current_price
            
            # Update klines to include only up to current candle
            mock_client.get_klines.return_value = klines[:i+1]
            
            # Evaluate both strategies
            scalping_signal = await scalping.evaluate()
            reverse_signal = await reverse.evaluate()
            
            # Record signals
            tracker.record_signal("scalping", scalping_signal, current_price)
            tracker.record_signal("reverse", reverse_signal, current_price)
            
            # Record positions
            tracker.record_position("scalping", scalping.position, scalping.entry_price or 0, current_price)
            tracker.record_position("reverse", reverse.position, reverse.entry_price or 0, current_price)
            
            # Check: If both have signals, they should be opposite
            if scalping_signal.action in ["BUY", "SELL"] and reverse_signal.action in ["BUY", "SELL"]:
                # Same signal time means opposite positions
                if scalping_signal.action == "BUY":
                    assert reverse_signal.action == "SELL", \
                        f"Scalping BUY should have Reverse SELL, got {reverse_signal.action}"
                elif scalping_signal.action == "SELL":
                    assert reverse_signal.action == "BUY", \
                        f"Scalping SELL should have Reverse BUY, got {reverse_signal.action}"
    
    @pytest.mark.asyncio
    async def test_opposite_win_rates_and_profits(self, mock_client, base_context):
        """Test that win rates and profits are opposite."""
        # Create price series with multiple crossovers
        # Pattern: Up trend -> Down trend -> Up trend (creates multiple trades)
        prices = (
            [50000.0] * 5 +  # Initial
            [50100.0] * 5 +  # Up (golden cross)
            [50200.0] * 5 +  # Continue up
            [50100.0] * 5 +  # Down (death cross)
            [50000.0] * 5 +  # Continue down
            [50100.0] * 5 +  # Up again (golden cross)
            [50200.0] * 5   # Continue up
        )
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        # Create both strategies
        scalping = EmaScalpingStrategy(base_context, mock_client)
        reverse = ReverseScalpingStrategy(base_context, mock_client)
        
        # Initialize both strategies
        scalping.prev_fast = None
        scalping.prev_slow = None
        reverse.prev_fast = None
        reverse.prev_slow = None
        
        tracker = TradeTracker()
        
        # Process all candles
        for i in range(len(klines)):
            candle = klines[i]
            current_price = float(candle[4])
            mock_client.get_price.return_value = current_price
            mock_client.get_klines.return_value = klines[:i+1]
            
            # Evaluate both strategies
            scalping_signal = await scalping.evaluate()
            reverse_signal = await reverse.evaluate()
            
            # Record signals
            tracker.record_signal("scalping", scalping_signal, current_price)
            tracker.record_signal("reverse", reverse_signal, current_price)
        
        # Calculate metrics
        scalping_pnl = tracker.calculate_pnl("scalping")
        reverse_pnl = tracker.calculate_pnl("reverse")
        scalping_win_rate, scalping_wins, scalping_losses = tracker.calculate_win_rate("scalping")
        reverse_win_rate, reverse_wins, reverse_losses = tracker.calculate_win_rate("reverse")
        
        # Print results for debugging
        print(f"\n=== Test Results ===")
        print(f"Scalping: {len(tracker.scalping_trades)} signals, PnL={scalping_pnl:.2f}, Win Rate={scalping_win_rate:.1f}% ({scalping_wins}W/{scalping_losses}L)")
        print(f"Reverse: {len(tracker.reverse_trades)} signals, PnL={reverse_pnl:.2f}, Win Rate={reverse_win_rate:.1f}% ({reverse_wins}W/{reverse_losses}L)")
        
        # Verify opposite PnL (should be approximately opposite)
        if abs(scalping_pnl) > 0.01:  # Only check if there's meaningful PnL
            assert abs(scalping_pnl + reverse_pnl) < abs(scalping_pnl) * 0.1, \
                f"PnL should be opposite: Scalping={scalping_pnl:.2f}, Reverse={reverse_pnl:.2f}, Sum={scalping_pnl + reverse_pnl:.2f}"
        
        # Verify opposite win rates (when one wins, other should lose)
        if scalping_wins + scalping_losses > 0 and reverse_wins + reverse_losses > 0:
            # Win rates should be complementary (one high, other low, or both ~50%)
            # If scalping wins more, reverse should lose more
            total_scalping = scalping_wins + scalping_losses
            total_reverse = reverse_wins + reverse_losses
            
            # They should have same number of trades
            assert total_scalping == total_reverse, \
                f"Should have same number of trades: Scalping={total_scalping}, Reverse={total_reverse}"
            
            # Win rates should be opposite (when scalping wins, reverse loses)
            # Check: scalping_wins should equal reverse_losses (and vice versa)
            assert scalping_wins == reverse_losses, \
                f"When Scalping wins, Reverse should lose: Scalping wins={scalping_wins}, Reverse losses={reverse_losses}"
            assert scalping_losses == reverse_wins, \
                f"When Scalping loses, Reverse should win: Scalping losses={scalping_losses}, Reverse wins={reverse_wins}"
    
    @pytest.mark.asyncio
    async def test_same_entry_times_opposite_positions(self, mock_client, base_context):
        """Test that both strategies enter at the same time with opposite positions."""
        # Create clear golden cross scenario
        # Falling prices then rising prices (creates golden cross)
        prices = [50000.0] * 5 + [49900.0] * 5 + [50000.0] * 5 + [50100.0] * 5
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        # Create both strategies
        scalping = EmaScalpingStrategy(base_context, mock_client)
        reverse = ReverseScalpingStrategy(base_context, mock_client)
        
        # Initialize
        scalping.prev_fast = None
        scalping.prev_slow = None
        reverse.prev_fast = None
        reverse.prev_slow = None
        
        entry_times = {"scalping": [], "reverse": []}
        
        # Process candles
        for i in range(len(klines)):
            candle = klines[i]
            current_price = float(candle[4])
            mock_client.get_price.return_value = current_price
            mock_client.get_klines.return_value = klines[:i+1]
            
            # Evaluate both strategies
            scalping_signal = await scalping.evaluate()
            reverse_signal = await reverse.evaluate()
            
            # Record entry times
            if scalping_signal.action == "BUY" and scalping.position == "LONG":
                entry_times["scalping"].append(i)
            if reverse_signal.action == "SELL" and reverse.position == "SHORT":
                entry_times["reverse"].append(i)
            if scalping_signal.action == "SELL" and scalping.position == "SHORT":
                entry_times["scalping"].append(i)
            if reverse_signal.action == "BUY" and reverse.position == "LONG":
                entry_times["reverse"].append(i)
        
        # Verify they enter at the same times
        assert len(entry_times["scalping"]) > 0, "Scalping should have at least one entry"
        assert len(entry_times["reverse"]) > 0, "Reverse should have at least one entry"
        assert entry_times["scalping"] == entry_times["reverse"], \
            f"Should enter at same times: Scalping={entry_times['scalping']}, Reverse={entry_times['reverse']}"
    
    @pytest.mark.asyncio
    async def test_comprehensive_opposite_verification(self, mock_client, base_context):
        """Comprehensive test verifying all opposite behaviors."""
        # Create complex price series with multiple trends
        prices = (
            [50000.0] * 10 +  # Initial stable
            [50100.0] * 10 +  # Up trend (golden cross)
            [50200.0] * 10 +  # Continue up
            [50100.0] * 10 +  # Down trend (death cross)
            [50000.0] * 10 +  # Continue down
            [49900.0] * 10 +  # Further down
            [50000.0] * 10 +  # Recovery (golden cross)
            [50100.0] * 10   # Continue up
        )
        klines = create_klines(prices)
        mock_client.get_klines.return_value = klines
        
        # Create both strategies
        scalping = EmaScalpingStrategy(base_context, mock_client)
        reverse = ReverseScalpingStrategy(base_context, mock_client)
        
        # Initialize
        scalping.prev_fast = None
        scalping.prev_slow = None
        reverse.prev_fast = None
        reverse.prev_slow = None
        
        tracker = TradeTracker()
        signal_pairs = []
        
        # Process all candles
        for i in range(len(klines)):
            candle = klines[i]
            current_price = float(candle[4])
            mock_client.get_price.return_value = current_price
            mock_client.get_klines.return_value = klines[:i+1]
            
            # Evaluate both strategies
            scalping_signal = await scalping.evaluate()
            reverse_signal = await reverse.evaluate()
            
            # Record signals
            tracker.record_signal("scalping", scalping_signal, current_price)
            tracker.record_signal("reverse", reverse_signal, current_price)
            
            # Check opposite positions when both have signals
            if scalping_signal.action in ["BUY", "SELL"] and reverse_signal.action in ["BUY", "SELL"]:
                signal_pairs.append({
                    "candle": i,
                    "price": current_price,
                    "scalping": scalping_signal.action,
                    "reverse": reverse_signal.action,
                    "scalping_position": scalping_signal.position_side,
                    "reverse_position": reverse_signal.position_side,
                })
                
                # Verify opposite actions
                if scalping_signal.action == "BUY":
                    assert reverse_signal.action == "SELL", \
                        f"Candle {i}: Scalping BUY should have Reverse SELL"
                elif scalping_signal.action == "SELL":
                    assert reverse_signal.action == "BUY", \
                        f"Candle {i}: Scalping SELL should have Reverse BUY"
                
                # Verify opposite positions
                if scalping_signal.position_side == "LONG":
                    assert reverse_signal.position_side == "SHORT", \
                        f"Candle {i}: Scalping LONG should have Reverse SHORT"
                elif scalping_signal.position_side == "SHORT":
                    assert reverse_signal.position_side == "LONG", \
                        f"Candle {i}: Scalping SHORT should have Reverse LONG"
        
        # Calculate final metrics
        scalping_pnl = tracker.calculate_pnl("scalping")
        reverse_pnl = tracker.calculate_pnl("reverse")
        scalping_win_rate, scalping_wins, scalping_losses = tracker.calculate_win_rate("scalping")
        reverse_win_rate, reverse_wins, reverse_losses = tracker.calculate_win_rate("reverse")
        
        # Print comprehensive results
        print(f"\n=== Comprehensive Test Results ===")
        print(f"Signal Pairs: {len(signal_pairs)}")
        print(f"Scalping: {len(tracker.scalping_trades)} signals, PnL={scalping_pnl:.2f}, Win Rate={scalping_win_rate:.1f}% ({scalping_wins}W/{scalping_losses}L)")
        print(f"Reverse: {len(tracker.reverse_trades)} signals, PnL={reverse_pnl:.2f}, Win Rate={reverse_win_rate:.1f}% ({reverse_wins}W/{reverse_losses}L)")
        
        if signal_pairs:
            print(f"\nFirst 5 Signal Pairs:")
            for pair in signal_pairs[:5]:
                print(f"  Candle {pair['candle']}: Scalping {pair['scalping']} ({pair['scalping_position']}) "
                      f"vs Reverse {pair['reverse']} ({pair['reverse_position']}) @ {pair['price']:.2f}")
        
        # Final assertions
        assert len(signal_pairs) > 0, "Should have at least one signal pair"
        
        # Verify opposite PnL
        if abs(scalping_pnl) > 0.01:
            pnl_sum = scalping_pnl + reverse_pnl
            pnl_ratio = abs(pnl_sum) / max(abs(scalping_pnl), abs(reverse_pnl), 0.01)
            assert pnl_ratio < 0.2, \
                f"PnL should be opposite: Scalping={scalping_pnl:.2f}, Reverse={reverse_pnl:.2f}, Sum={pnl_sum:.2f}, Ratio={pnl_ratio:.2%}"
        
        # Verify opposite win rates
        total_trades = scalping_wins + scalping_losses
        if total_trades > 0:
            assert scalping_wins == reverse_losses, \
                f"Win/Loss should be opposite: Scalping wins={scalping_wins} should equal Reverse losses={reverse_losses}"
            assert scalping_losses == reverse_wins, \
                f"Win/Loss should be opposite: Scalping losses={scalping_losses} should equal Reverse wins={reverse_wins}"


