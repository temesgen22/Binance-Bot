"""
Tests for Dynamic Trailing Stop Manager
"""

import pytest
from app.strategies.trailing_stop import TrailingStopManager


def test_trailing_stop_long_initial():
    """Test initial setup for long position."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,  # 5%
        stop_loss_pct=0.02,     # 2%
        position_type="LONG",
        enabled=True
    )
    
    tp, sl = manager.get_levels()
    assert tp == 105000.0  # 100,000 * 1.05
    assert sl == 98000.0   # 100,000 * 0.98
    assert manager.get_best_price() == 100000.0


def test_trailing_stop_long_doesnt_trail_down():
    """Test that trailing stop doesn't trail down for long positions."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="LONG",
        enabled=True
    )
    
    # Price goes up first
    manager.update(101100.0)  # +1.1%
    tp1, sl1 = manager.get_levels()
    
    # Price goes down (should not trail back)
    manager.update(100500.0)  # Still above entry but below previous
    tp2, sl2 = manager.get_levels()
    
    # TP and SL should remain at the higher levels
    assert tp2 == tp1  # Should not decrease
    assert sl2 == sl1  # Should not decrease
    assert manager.get_best_price() == 101100.0  # Best price unchanged


def test_trailing_stop_long_trails_up():
    """Test that trailing stop trails up for long positions."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="LONG",
        enabled=True
    )
    
    # Initial levels
    tp0, sl0 = manager.get_levels()
    assert tp0 == 105000.0
    assert sl0 == 98000.0
    
    # Price moves to 101,100 (+1.1%)
    manager.update(101100.0)
    tp1, sl1 = manager.get_levels()
    
    # Should trail up
    assert tp1 == 101100.0 * 1.05  # 106,155
    assert sl1 == 101100.0 * 0.98  # 99,078
    assert tp1 > tp0  # TP increased
    assert sl1 > sl0  # SL increased
    
    # Price moves further up to 103,000 (+3%)
    manager.update(103000.0)
    tp2, sl2 = manager.get_levels()
    
    # Should trail up again
    assert tp2 == 103000.0 * 1.05  # 108,150
    assert sl2 == 103000.0 * 0.98  # 100,940
    assert tp2 > tp1  # TP increased further
    assert sl2 > sl1  # SL increased further


def test_trailing_stop_long_take_profit():
    """Test take profit trigger for long position."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="LONG",
        enabled=True
    )
    
    # Trail up first
    manager.update(101000.0)
    tp, sl = manager.get_levels()
    
    # Price hits TP
    result = manager.check_exit(106050.0)  # Above new TP
    assert result == "TP"


def test_trailing_stop_long_stop_loss():
    """Test stop loss trigger for long position."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="LONG",
        enabled=True
    )
    
    # Trail up first
    manager.update(101000.0)
    tp, sl = manager.get_levels()
    
    # Price drops to hit SL
    result = manager.check_exit(98980.0)  # Below new SL
    assert result == "SL"


def test_trailing_stop_short_initial():
    """Test initial setup for short position."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,  # 5%
        stop_loss_pct=0.02,     # 2%
        position_type="SHORT",
        enabled=True
    )
    
    tp, sl = manager.get_levels()
    assert tp == 95000.0   # 100,000 * 0.95 (price must drop)
    assert sl == 102000.0  # 100,000 * 1.02 (price must rise)
    assert manager.get_best_price() == 100000.0


def test_trailing_stop_short_trails_down():
    """Test that trailing stop trails down for short positions."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="SHORT",
        enabled=True
    )
    
    # Initial levels
    tp0, sl0 = manager.get_levels()
    assert tp0 == 95000.0
    assert sl0 == 102000.0
    
    # Price moves to 98,900 (-1.1%)
    manager.update(98900.0)
    tp1, sl1 = manager.get_levels()
    
    # Should trail down
    assert tp1 == 98900.0 * 0.95  # 93,955
    assert sl1 == 98900.0 * 1.02  # 100,878
    assert tp1 < tp0  # TP decreased
    assert sl1 < sl0  # SL decreased
    
    # Price moves further down to 97,000 (-3%)
    manager.update(97000.0)
    tp2, sl2 = manager.get_levels()
    
    # Should trail down again
    assert tp2 == 97000.0 * 0.95  # 92,150
    assert sl2 == 97000.0 * 1.02  # 98,940
    assert tp2 < tp1  # TP decreased further
    assert sl2 < sl1  # SL decreased further


def test_trailing_stop_short_doesnt_trail_up():
    """Test that trailing stop doesn't trail up for short positions."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="SHORT",
        enabled=True
    )
    
    # Price goes down first
    manager.update(98900.0)  # -1.1%
    tp1, sl1 = manager.get_levels()
    
    # Price goes up (should not trail back)
    manager.update(99500.0)  # Still below entry but above previous
    tp2, sl2 = manager.get_levels()
    
    # TP and SL should remain at the lower levels
    assert tp2 == tp1  # Should not increase
    assert sl2 == sl1  # Should not increase
    assert manager.get_best_price() == 98900.0  # Best price unchanged


def test_trailing_stop_disabled():
    """Test that trailing stop doesn't update when disabled."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="LONG",
        enabled=False
    )
    
    tp0, sl0 = manager.get_levels()
    
    # Price moves up
    manager.update(101000.0)
    tp1, sl1 = manager.get_levels()
    
    # Should not change
    assert tp1 == tp0
    assert sl1 == sl0


def test_trailing_stop_reset():
    """Test resetting trailing stop for new position."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="LONG",
        enabled=True
    )
    
    # Trail up
    manager.update(101000.0)
    
    # Reset for new entry
    manager.reset(95000.0)
    tp, sl = manager.get_levels()
    
    assert tp == 95000.0 * 1.05  # New entry * 1.05
    assert sl == 95000.0 * 0.98  # New entry * 0.98
    assert manager.get_best_price() == 95000.0


def test_trailing_stop_activation_threshold_long():
    """Test activation threshold for long position."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="LONG",
        enabled=True,
        activation_pct=0.01  # 1% activation
    )
    
    # Initial levels (not activated yet)
    tp0, sl0 = manager.get_levels()
    assert tp0 == 105000.0
    assert sl0 == 98000.0
    assert not manager.activated
    
    # Price moves 0.5% (below activation threshold)
    manager.update(100500.0)
    tp1, sl1 = manager.get_levels()
    assert tp1 == tp0  # Should not change
    assert sl1 == sl0  # Should not change
    assert not manager.activated  # Still not activated
    
    # Price moves 1% (reaches activation threshold)
    manager.update(101000.0)
    assert manager.activated  # Should be activated now
    tp2, sl2 = manager.get_levels()
    assert tp2 == 101000.0 * 1.05  # Should trail
    assert sl2 == 101000.0 * 0.98  # Should trail
    
    # Price moves further up
    manager.update(102000.0)
    tp3, sl3 = manager.get_levels()
    assert tp3 == 102000.0 * 1.05  # Should continue trailing
    assert sl3 == 102000.0 * 0.98


def test_trailing_stop_activation_threshold_short():
    """Test activation threshold for short position."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="SHORT",
        enabled=True,
        activation_pct=0.01  # 1% activation
    )
    
    # Initial levels (not activated yet)
    tp0, sl0 = manager.get_levels()
    assert tp0 == 95000.0
    assert sl0 == 102000.0
    assert not manager.activated
    
    # Price moves 0.5% down (below activation threshold)
    manager.update(99500.0)
    tp1, sl1 = manager.get_levels()
    assert tp1 == tp0  # Should not change
    assert sl1 == sl0  # Should not change
    assert not manager.activated  # Still not activated
    
    # Price moves 1% down (reaches activation threshold)
    manager.update(99000.0)
    assert manager.activated  # Should be activated now
    tp2, sl2 = manager.get_levels()
    assert tp2 == 99000.0 * 0.95  # Should trail
    assert sl2 == 99000.0 * 1.02  # Should trail
    
    # Price moves further down
    manager.update(98000.0)
    tp3, sl3 = manager.get_levels()
    assert tp3 == 98000.0 * 0.95  # Should continue trailing
    assert sl3 == 98000.0 * 1.02


def test_trailing_stop_activation_zero():
    """Test that activation_pct=0 starts immediately."""
    manager = TrailingStopManager(
        entry_price=100000.0,
        take_profit_pct=0.05,
        stop_loss_pct=0.02,
        position_type="LONG",
        enabled=True,
        activation_pct=0.0  # No activation threshold
    )
    
    assert manager.activated  # Should be activated immediately
    
    # Should trail on first update
    manager.update(100500.0)
    tp, sl = manager.get_levels()
    assert tp == 100500.0 * 1.05
    assert sl == 100500.0 * 0.98

