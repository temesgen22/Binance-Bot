#!/usr/bin/env python3
"""
Test script: Circuit breaker (consecutive/sequence loss) works correctly.

Run from project root:
  python scripts/test_circuit_breaker_sequence_loss.py

Verifies:
1. check_consecutive_losses() triggers when max_consecutive_losses is reached.
2. Trades with pnl_usd (CompletedTrade-style) are counted as losses.
3. is_active() returns True after the breaker triggers.
4. Win or breakeven breaks the streak (no trigger below threshold).

Root cause fix (in app): Circuit breaker was never running because
order_response.realized_pnl was always None (Binance REST order response
often doesn't include it). We now run the check on any closing order and
use summary.unrealized_pnl at close when realized_pnl is missing.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

# Add project root
sys.path.insert(0, str(__file__).replace("\\", "/").rsplit("/", 1)[0].rsplit("/", 1)[0])

from unittest.mock import Mock


def test_consecutive_losses_trigger():
    """Sequence of N losses triggers the circuit breaker."""
    from app.risk.circuit_breaker import CircuitBreaker
    from app.models.risk_management import RiskManagementConfigResponse

    config = Mock(spec=RiskManagementConfigResponse)
    config.circuit_breaker_enabled = True
    config.max_consecutive_losses = 5
    config.circuit_breaker_cooldown_minutes = 60
    config.rapid_loss_threshold_pct = 0.05

    breaker = CircuitBreaker(
        account_id="test_account",
        config=config,
        db_service=None,
        user_id=uuid4(),
        strategy_runner=Mock(_strategies={}, state_manager=Mock(update_strategy_in_db=Mock())),
        trade_service=None,
    )

    strategy_id = "test-strategy-id"
    # CompletedTrade-style: pnl_usd and exit_time
    trades = [
        SimpleNamespace(pnl_usd=-10.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-5.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-2.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-8.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-3.0, exit_time=datetime.now(timezone.utc)),
    ]

    state = breaker.check_consecutive_losses(strategy_id, trades)
    assert state is not None, "Circuit breaker should trigger after 5 consecutive losses"
    assert state.breaker_type == "consecutive_losses"
    assert state.trigger_value == 5
    assert state.threshold_value == 5
    assert state.strategy_id == strategy_id
    assert breaker.is_active("test_account", strategy_id) is True
    print("OK: Consecutive loss circuit breaker triggers and is_active is True")
    return True


def test_consecutive_losses_no_trigger_below_threshold():
    """Fewer than max_consecutive_losses does not trigger."""
    from app.risk.circuit_breaker import CircuitBreaker
    from app.models.risk_management import RiskManagementConfigResponse

    config = Mock(spec=RiskManagementConfigResponse)
    config.circuit_breaker_enabled = True
    config.max_consecutive_losses = 5
    config.circuit_breaker_cooldown_minutes = 60
    config.rapid_loss_threshold_pct = 0.05

    breaker = CircuitBreaker(
        account_id="test_account",
        config=config,
        db_service=None,
        user_id=uuid4(),
        strategy_runner=Mock(_strategies={}, state_manager=Mock(update_strategy_in_db=Mock())),
        trade_service=None,
    )

    strategy_id = "strategy-2"
    trades = [
        SimpleNamespace(pnl_usd=-1.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-2.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-3.0, exit_time=datetime.now(timezone.utc)),
    ]
    state = breaker.check_consecutive_losses(strategy_id, trades)
    assert state is None, "Should not trigger with only 3 consecutive losses (threshold 5)"
    assert breaker.is_active("test_account", strategy_id) is False
    print("OK: No trigger below threshold")
    return True


def test_win_breaks_streak():
    """A win in the sequence breaks the streak; only trailing losses count."""
    from app.risk.circuit_breaker import CircuitBreaker
    from app.models.risk_management import RiskManagementConfigResponse

    config = Mock(spec=RiskManagementConfigResponse)
    config.circuit_breaker_enabled = True
    config.max_consecutive_losses = 5
    config.circuit_breaker_cooldown_minutes = 60
    config.rapid_loss_threshold_pct = 0.05

    breaker = CircuitBreaker(
        account_id="test_account",
        config=config,
        db_service=None,
        user_id=uuid4(),
        strategy_runner=Mock(_strategies={}, state_manager=Mock(update_strategy_in_db=Mock())),
        trade_service=None,
    )

    strategy_id = "strategy-3"
    # Most recent first: 4 losses then 1 win -> only 4 consecutive losses from latest
    trades = [
        SimpleNamespace(pnl_usd=-1.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-2.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-3.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=-4.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(pnl_usd=10.0, exit_time=datetime.now(timezone.utc)),  # win
    ]
    state = breaker.check_consecutive_losses(strategy_id, trades)
    assert state is None, "Win should break streak; 4 consecutive losses should not trigger (threshold 5)"
    print("OK: Win breaks streak")
    return True


def test_net_pnl_trades():
    """Trades with net_pnl (CompletedTradeMatch style) are counted."""
    from app.risk.circuit_breaker import CircuitBreaker
    from app.models.risk_management import RiskManagementConfigResponse

    config = Mock(spec=RiskManagementConfigResponse)
    config.circuit_breaker_enabled = True
    config.max_consecutive_losses = 3
    config.circuit_breaker_cooldown_minutes = 60
    config.rapid_loss_threshold_pct = 0.05

    breaker = CircuitBreaker(
        account_id="test_account",
        config=config,
        db_service=None,
        user_id=uuid4(),
        strategy_runner=Mock(_strategies={}, state_manager=Mock(update_strategy_in_db=Mock())),
        trade_service=None,
    )

    strategy_id = "strategy-4"
    trades = [
        SimpleNamespace(net_pnl=-5.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(net_pnl=-3.0, exit_time=datetime.now(timezone.utc)),
        SimpleNamespace(net_pnl=-1.0, exit_time=datetime.now(timezone.utc)),
    ]
    state = breaker.check_consecutive_losses(strategy_id, trades)
    assert state is not None
    assert state.trigger_value == 3
    print("OK: net_pnl trades counted for consecutive loss")
    return True


def main():
    print("Testing circuit breaker (sequence / consecutive loss)...")
    test_consecutive_losses_trigger()
    test_consecutive_losses_no_trigger_below_threshold()
    test_win_breaks_streak()
    test_net_pnl_trades()
    print("\nAll circuit breaker sequence-loss checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
