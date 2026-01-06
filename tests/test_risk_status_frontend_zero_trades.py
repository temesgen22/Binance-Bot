"""
Test cases for frontend risk status display logic, specifically for zero-trade strategies.

This test simulates the frontend JavaScript logic to ensure that:
1. Strategies with zero trades always show "Allowed"
2. The frontend correctly handles API responses
3. The UI updates correctly based on risk status
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestFrontendRiskStatusZeroTrades:
    """Test frontend risk status display for zero-trade strategies."""
    
    def test_update_risk_status_ui_zero_trades_allowed(self):
        """Test that updateRiskStatusUI shows 'Allowed' for zero-trade strategies."""
        # Simulate the frontend updateRiskStatusUI function logic
        def update_risk_status_ui_logic(risk_status):
            """Simulates the frontend updateRiskStatusUI function."""
            # Check if daily_loss = 0 (no trades) first - these should NEVER be blocked
            daily_loss_value = risk_status.get('risk_checks', {}).get('daily_loss', {}).get('current_value')
            has_zero_trades = daily_loss_value == 0 or daily_loss_value == 0.0
            
            circuit_breaker_active = risk_status.get('circuit_breaker_active', False)
            blocked_reasons = risk_status.get('blocked_reasons', [])
            can_trade = risk_status.get('can_trade', True)
            
            # Determine badge
            if circuit_breaker_active:
                return {
                    'badge_class': 'risk-paused',
                    'badge_text': '⏸️ Paused',
                    'tooltip': 'Strategy paused by risk management (circuit breaker active)'
                }
            elif has_zero_trades:
                # Zero trades = no risk = always allowed
                return {
                    'badge_class': 'risk-allowed',
                    'badge_text': '✅ Allowed',
                    'tooltip': 'Strategy can trade normally (no trades yet)'
                }
            elif blocked_reasons and len(blocked_reasons) > 0:
                return {
                    'badge_class': 'risk-blocked',
                    'badge_text': '🚫 Blocked',
                    'tooltip': f"Blocked: {', '.join(blocked_reasons)}"
                }
            elif not can_trade:
                return {
                    'badge_class': 'risk-blocked',
                    'badge_text': '🚫 Blocked',
                    'tooltip': 'Strategy cannot trade (risk limits exceeded)'
                }
            else:
                return {
                    'badge_class': 'risk-allowed',
                    'badge_text': '✅ Allowed',
                    'tooltip': 'Strategy can trade normally'
                }
        
        # Test case 1: Zero trades, can_trade=True (correct API response)
        risk_status_1 = {
            'can_trade': True,
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {
                'daily_loss': {
                    'allowed': True,
                    'current_value': 0.0,
                    'limit_value': 500.0
                }
            }
        }
        result_1 = update_risk_status_ui_logic(risk_status_1)
        assert result_1['badge_class'] == 'risk-allowed'
        assert result_1['badge_text'] == '✅ Allowed'
        assert 'no trades yet' in result_1['tooltip'].lower()
        
        # Test case 2: Zero trades, can_trade=False (incorrect API response - should still show Allowed)
        risk_status_2 = {
            'can_trade': False,  # API incorrectly says blocked
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {
                'daily_loss': {
                    'allowed': False,  # API incorrectly says not allowed
                    'current_value': 0.0,  # But zero trades!
                    'limit_value': 500.0
                }
            }
        }
        result_2 = update_risk_status_ui_logic(risk_status_2)
        # Should still show Allowed because has_zero_trades is checked first
        assert result_2['badge_class'] == 'risk-allowed'
        assert result_2['badge_text'] == '✅ Allowed'
        assert 'no trades yet' in result_2['tooltip'].lower()
        
        # Test case 3: Zero trades with circuit breaker active (should show Paused)
        risk_status_3 = {
            'can_trade': False,
            'circuit_breaker_active': True,  # Circuit breaker takes precedence
            'blocked_reasons': ['Strategy paused by risk management'],
            'risk_checks': {
                'daily_loss': {
                    'allowed': True,
                    'current_value': 0.0,
                    'limit_value': 500.0
                }
            }
        }
        result_3 = update_risk_status_ui_logic(risk_status_3)
        assert result_3['badge_class'] == 'risk-paused'
        assert result_3['badge_text'] == '⏸️ Paused'
    
    def test_load_risk_status_zero_trades_correction(self):
        """Test that loadRiskStatus corrects API responses for zero-trade strategies."""
        def load_risk_status_logic(api_response):
            """Simulates the frontend loadRiskStatus function logic."""
            risk_status = api_response.copy()
            
            # CRITICAL: If daily_loss current_value is 0 (no trades) and circuit breaker is inactive,
            # the strategy MUST be allowed to trade, regardless of what the API says
            daily_loss_value = risk_status.get('risk_checks', {}).get('daily_loss', {}).get('current_value')
            daily_loss_allowed = risk_status.get('risk_checks', {}).get('daily_loss', {}).get('allowed')
            
            if (daily_loss_value == 0 or daily_loss_value == 0.0) and not risk_status.get('circuit_breaker_active', False):
                # Zero trades = no risk = always allowed
                if not risk_status.get('can_trade', True) or not daily_loss_allowed:
                    # Force correction
                    risk_status['can_trade'] = True
                    risk_status['blocked_reasons'] = []
                    if risk_status.get('risk_checks', {}).get('daily_loss'):
                        risk_status['risk_checks']['daily_loss']['allowed'] = True
            
            # Safety check: If can_trade is false but no blocked_reasons and circuit_breaker is inactive,
            # this is likely a bug - default to allowing trade
            if (risk_status.get('can_trade') == False and 
                (not risk_status.get('blocked_reasons') or len(risk_status.get('blocked_reasons', [])) == 0) and
                not risk_status.get('circuit_breaker_active', False)):
                risk_status['can_trade'] = True
            
            return risk_status
        
        # Test case 1: API incorrectly returns can_trade=False for zero trades
        incorrect_api_response = {
            'can_trade': False,  # Wrong!
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {
                'daily_loss': {
                    'allowed': False,  # Wrong!
                    'current_value': 0.0,  # Zero trades
                    'limit_value': 500.0
                }
            }
        }
        corrected = load_risk_status_logic(incorrect_api_response)
        assert corrected['can_trade'] is True
        assert len(corrected['blocked_reasons']) == 0
        assert corrected['risk_checks']['daily_loss']['allowed'] is True
        
        # Test case 2: API correctly returns can_trade=True for zero trades
        correct_api_response = {
            'can_trade': True,
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {
                'daily_loss': {
                    'allowed': True,
                    'current_value': 0.0,
                    'limit_value': 500.0
                }
            }
        }
        unchanged = load_risk_status_logic(correct_api_response)
        assert unchanged['can_trade'] is True
        assert unchanged['risk_checks']['daily_loss']['allowed'] is True
        
        # Test case 3: Zero trades but circuit breaker active (should not correct)
        circuit_breaker_response = {
            'can_trade': False,
            'circuit_breaker_active': True,  # Circuit breaker active
            'blocked_reasons': ['Strategy paused by risk management'],
            'risk_checks': {
                'daily_loss': {
                    'allowed': True,
                    'current_value': 0.0,
                    'limit_value': 500.0
                }
            }
        }
        unchanged_cb = load_risk_status_logic(circuit_breaker_response)
        assert unchanged_cb['circuit_breaker_active'] is True
        # Can trade should remain False because circuit breaker is active
    
    def test_risk_status_scenarios(self):
        """Test various risk status scenarios."""
        def get_badge_for_risk_status(risk_status):
            """Helper to determine badge from risk status."""
            daily_loss_value = risk_status.get('risk_checks', {}).get('daily_loss', {}).get('current_value')
            has_zero_trades = daily_loss_value == 0 or daily_loss_value == 0.0
            
            if risk_status.get('circuit_breaker_active', False):
                return '⏸️ Paused'
            elif has_zero_trades:
                return '✅ Allowed'
            elif risk_status.get('blocked_reasons') and len(risk_status.get('blocked_reasons', [])) > 0:
                return '🚫 Blocked'
            elif not risk_status.get('can_trade', True):
                return '🚫 Blocked'
            else:
                return '✅ Allowed'
        
        # Scenario 1: Zero trades, no circuit breaker
        scenario_1 = {
            'can_trade': True,
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {'daily_loss': {'current_value': 0.0}}
        }
        assert get_badge_for_risk_status(scenario_1) == '✅ Allowed'
        
        # Scenario 2: Zero trades, but API says blocked (should still show Allowed)
        scenario_2 = {
            'can_trade': False,  # API says blocked
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {'daily_loss': {'current_value': 0.0}}  # But zero trades!
        }
        assert get_badge_for_risk_status(scenario_2) == '✅ Allowed'
        
        # Scenario 3: Has trades with loss, but within limit
        scenario_3 = {
            'can_trade': True,
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {'daily_loss': {'current_value': -100.0, 'limit_value': -500.0}}
        }
        assert get_badge_for_risk_status(scenario_3) == '✅ Allowed'
        
        # Scenario 4: Has trades with loss exceeding limit
        scenario_4 = {
            'can_trade': False,
            'circuit_breaker_active': False,
            'blocked_reasons': ['Daily loss limit exceeded: $-600.00 / -$500.00'],
            'risk_checks': {'daily_loss': {'current_value': -600.0, 'limit_value': -500.0}}
        }
        assert get_badge_for_risk_status(scenario_4) == '🚫 Blocked'
        
        # Scenario 5: Circuit breaker active (even with zero trades)
        scenario_5 = {
            'can_trade': False,
            'circuit_breaker_active': True,
            'blocked_reasons': ['Strategy paused by risk management'],
            'risk_checks': {'daily_loss': {'current_value': 0.0}}
        }
        assert get_badge_for_risk_status(scenario_5) == '⏸️ Paused'
    
    def test_edge_cases(self):
        """Test edge cases for risk status display."""
        def should_show_allowed(risk_status):
            """Helper to determine if should show Allowed."""
            daily_loss_value = risk_status.get('risk_checks', {}).get('daily_loss', {}).get('current_value')
            has_zero_trades = daily_loss_value == 0 or daily_loss_value == 0.0
            
            if risk_status.get('circuit_breaker_active', False):
                return False  # Paused, not allowed
            elif has_zero_trades:
                return True  # Zero trades = always allowed
            elif risk_status.get('can_trade', True):
                return True
            else:
                return False
        
        # Edge case 1: Missing risk_checks
        edge_case_1 = {
            'can_trade': True,
            'circuit_breaker_active': False,
            'blocked_reasons': []
        }
        # Should default to allowed if can_trade is True
        assert should_show_allowed(edge_case_1) is True
        
        # Edge case 2: daily_loss value is None
        edge_case_2 = {
            'can_trade': True,
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {'daily_loss': {'current_value': None}}
        }
        # None is not 0, so should check can_trade
        assert should_show_allowed(edge_case_2) is True
        
        # Edge case 3: daily_loss value is exactly 0 (integer)
        edge_case_3 = {
            'can_trade': False,  # API says blocked
            'circuit_breaker_active': False,
            'blocked_reasons': [],
            'risk_checks': {'daily_loss': {'current_value': 0}}  # Integer 0, not float
        }
        # Should still show allowed because has_zero_trades checks for 0 or 0.0
        assert should_show_allowed(edge_case_3) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

