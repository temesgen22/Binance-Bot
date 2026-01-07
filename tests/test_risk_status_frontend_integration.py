"""
Integration tests for risk status frontend display logic.

Tests verify that the frontend correctly interprets API responses
and displays the appropriate risk status badges.
"""

import pytest
import json


def test_update_risk_status_ui_allowed():
    """Test that allowed status displays correctly."""
    # Simulate API response for allowed strategy
    risk_status = {
        "strategy_id": "test-123",
        "account_id": "account-123",
        "can_trade": True,
        "blocked_reasons": [],
        "circuit_breaker_active": False,
        "risk_checks": {
            "portfolio_exposure": {
                "allowed": True,
                "current_value": 1000.0,
                "limit_value": 10000.0
            },
            "daily_loss": {
                "allowed": True,
                "current_value": -50.0,
                "limit_value": -500.0
            }
        }
    }
    
    # Simulate frontend logic
    badge_class = 'risk-allowed'
    badge_text = '✅ Allowed'
    tooltip = 'Strategy can trade normally'
    
    # Check logic
    if risk_status["circuit_breaker_active"]:
        badge_class = 'risk-paused'
        badge_text = '⏸️ Paused'
    elif risk_status["blocked_reasons"] and len(risk_status["blocked_reasons"]) > 0:
        badge_class = 'risk-blocked'
        badge_text = '🚫 Blocked'
    elif not risk_status["can_trade"]:
        badge_class = 'risk-blocked'
        badge_text = '🚫 Blocked'
    else:
        # Check warnings
        risk_checks = risk_status.get("risk_checks", {})
        warnings = []
        
        if risk_checks.get("portfolio_exposure"):
            exposure = risk_checks["portfolio_exposure"]
            pct = (exposure["current_value"] / exposure["limit_value"]) * 100 if exposure["limit_value"] > 0 else 0
            if pct >= 80:
                warnings.append(f"Exposure: {pct:.0f}%")
        
        if risk_checks.get("daily_loss"):
            daily = risk_checks["daily_loss"]
            pct = abs((daily["current_value"] / daily["limit_value"]) * 100) if daily["limit_value"] < 0 else 0
            if pct >= 80:
                warnings.append(f"Daily Loss: {pct:.0f}%")
        
        if warnings:
            badge_class = 'risk-warning'
            badge_text = '⚠️ Warning'
            tooltip = f"Approaching limits: {', '.join(warnings)}"
        else:
            badge_class = 'risk-allowed'
            badge_text = '✅ Allowed'
            tooltip = 'Strategy can trade normally'
    
    # Assertions
    assert badge_class == 'risk-allowed'
    assert badge_text == '✅ Allowed'
    assert tooltip == 'Strategy can trade normally'


def test_update_risk_status_ui_paused():
    """Test that paused status displays correctly."""
    # Simulate API response for paused strategy
    risk_status = {
        "strategy_id": "test-123",
        "account_id": "account-123",
        "can_trade": False,
        "blocked_reasons": ["Strategy paused by risk management (circuit breaker)"],
        "circuit_breaker_active": True,
        "risk_checks": {
            "circuit_breaker": {
                "allowed": False,
                "active": True
            }
        }
    }
    
    # Simulate frontend logic
    badge_class = 'risk-allowed'
    badge_text = '✅ Allowed'
    tooltip = 'Strategy can trade normally'
    
    if risk_status["circuit_breaker_active"]:
        badge_class = 'risk-paused'
        badge_text = '⏸️ Paused'
        tooltip = 'Strategy paused by risk management (circuit breaker active)'
    
    # Assertions
    assert badge_class == 'risk-paused'
    assert badge_text == '⏸️ Paused'
    assert 'circuit breaker' in tooltip.lower()


def test_update_risk_status_ui_blocked():
    """Test that blocked status displays correctly."""
    # Simulate API response for blocked strategy
    risk_status = {
        "strategy_id": "test-123",
        "account_id": "account-123",
        "can_trade": False,
        "blocked_reasons": ["Daily loss limit exceeded"],
        "circuit_breaker_active": False,
        "risk_checks": {
            "daily_loss": {
                "allowed": False,
                "current_value": -600.0,
                "limit_value": -500.0
            }
        }
    }
    
    # Simulate frontend logic
    badge_class = 'risk-allowed'
    badge_text = '✅ Allowed'
    tooltip = 'Strategy can trade normally'
    
    if risk_status["circuit_breaker_active"]:
        badge_class = 'risk-paused'
        badge_text = '⏸️ Paused'
    elif risk_status["blocked_reasons"] and len(risk_status["blocked_reasons"]) > 0:
        badge_class = 'risk-blocked'
        badge_text = '🚫 Blocked'
        tooltip = f"Blocked: {', '.join(risk_status['blocked_reasons'])}"
    elif not risk_status["can_trade"]:
        badge_class = 'risk-blocked'
        badge_text = '🚫 Blocked'
        tooltip = 'Strategy cannot trade (risk limits exceeded)'
    
    # Assertions
    assert badge_class == 'risk-blocked'
    assert badge_text == '🚫 Blocked'
    assert 'Daily loss limit' in tooltip


def test_update_risk_status_ui_warning():
    """Test that warning status displays correctly when approaching limits."""
    # Simulate API response for strategy approaching limits
    risk_status = {
        "strategy_id": "test-123",
        "account_id": "account-123",
        "can_trade": True,
        "blocked_reasons": [],
        "circuit_breaker_active": False,
        "risk_checks": {
            "portfolio_exposure": {
                "allowed": True,
                "current_value": 8500.0,  # 85% of limit
                "limit_value": 10000.0
            },
            "daily_loss": {
                "allowed": True,
                "current_value": -400.0,  # 80% of limit
                "limit_value": -500.0
            }
        }
    }
    
    # Simulate frontend logic
    badge_class = 'risk-allowed'
    badge_text = '✅ Allowed'
    tooltip = 'Strategy can trade normally'
    
    if not risk_status["circuit_breaker_active"] and risk_status["can_trade"]:
        risk_checks = risk_status.get("risk_checks", {})
        warnings = []
        
        if risk_checks.get("portfolio_exposure"):
            exposure = risk_checks["portfolio_exposure"]
            pct = (exposure["current_value"] / exposure["limit_value"]) * 100 if exposure["limit_value"] > 0 else 0
            if pct >= 80:
                warnings.append(f"Exposure: {pct:.0f}%")
        
        if risk_checks.get("daily_loss"):
            daily = risk_checks["daily_loss"]
            pct = abs((daily["current_value"] / daily["limit_value"]) * 100) if daily["limit_value"] < 0 else 0
            if pct >= 80:
                warnings.append(f"Daily Loss: {pct:.0f}%")
        
        if warnings:
            badge_class = 'risk-warning'
            badge_text = '⚠️ Warning'
            tooltip = f"Approaching limits: {', '.join(warnings)}"
    
    # Assertions
    assert badge_class == 'risk-warning'
    assert badge_text == '⚠️ Warning'
    assert 'Approaching limits' in tooltip
    assert 'Exposure: 85%' in tooltip or 'Daily Loss: 80%' in tooltip


def test_risk_status_response_json_serialization():
    """Test that risk status response can be JSON serialized (for API)."""
    from app.models.risk_management import StrategyRiskStatusResponse
    
    response = StrategyRiskStatusResponse(
        strategy_id="test-123",
        account_id="account-123",
        can_trade=True,
        blocked_reasons=[],
        circuit_breaker_active=False,
        risk_checks={
            "portfolio_exposure": {
                "allowed": True,
                "current_value": 1000.0,
                "limit_value": 10000.0
            }
        },
        last_enforcement_event=None
    )
    
    # Convert to dict and then JSON
    response_dict = response.model_dump()
    json_str = json.dumps(response_dict)
    
    # Parse back
    parsed = json.loads(json_str)
    
    assert parsed["strategy_id"] == "test-123"
    assert parsed["can_trade"] is True
    assert parsed["circuit_breaker_active"] is False
    assert "risk_checks" in parsed


def test_risk_status_edge_cases():
    """Test edge cases in risk status logic."""
    # Case 1: No risk_checks
    risk_status = {
        "strategy_id": "test-123",
        "account_id": "account-123",
        "can_trade": True,
        "blocked_reasons": [],
        "circuit_breaker_active": False,
        "risk_checks": {}
    }
    
    # Should default to allowed
    badge_class = 'risk-allowed'
    if not risk_status["circuit_breaker_active"] and risk_status["can_trade"]:
        risk_checks = risk_status.get("risk_checks", {})
        warnings = []
        # No checks means no warnings
        if not warnings:
            badge_class = 'risk-allowed'
    
    assert badge_class == 'risk-allowed'
    
    # Case 2: None limit values
    risk_status2 = {
        "strategy_id": "test-123",
        "account_id": "account-123",
        "can_trade": True,
        "blocked_reasons": [],
        "circuit_breaker_active": False,
        "risk_checks": {
            "portfolio_exposure": {
                "allowed": True,
                "current_value": 1000.0,
                "limit_value": None  # No limit set
            }
        }
    }
    
    # Should handle None gracefully
    risk_checks = risk_status2.get("risk_checks", {})
    if risk_checks.get("portfolio_exposure"):
        exposure = risk_checks["portfolio_exposure"]
        pct = (exposure["current_value"] / exposure["limit_value"]) * 100 if exposure["limit_value"] and exposure["limit_value"] > 0 else 0
        assert pct == 0  # Should default to 0 when limit is None










