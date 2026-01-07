"""
End-to-end test for frontend risk status display.

This test simulates the complete frontend flow:
1. Fetching risk status from API
2. Processing the response
3. Displaying the correct badge

Tests verify that strategies with zero trades always show "Allowed".
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
from uuid import uuid4

from app.api.routes.risk_metrics import get_strategy_risk_status
from app.models.risk_management import RiskManagementConfigResponse


class TestFrontendRiskStatusE2E:
    """End-to-end tests for frontend risk status display."""
    
    @pytest.mark.asyncio
    async def test_zero_trades_shows_allowed_in_frontend(self):
        """Test that zero-trade strategies show 'Allowed' in the frontend."""
        
        # Create a mock user
        mock_user = MagicMock()
        mock_user.id = uuid4()
        
        # Create a mock database session
        mock_db = MagicMock()
        
        # Create a mock strategy (stopped, no trades)
        mock_strategy = MagicMock()
        mock_strategy.id = uuid4()
        mock_strategy.status = "stopped"  # Not paused_by_risk
        mock_strategy.account_id = None
        
        # Create a mock account
        mock_account = MagicMock()
        mock_account.account_id = "test-account"
        
        # Create a mock risk config with limits
        mock_risk_config = RiskManagementConfigResponse(
            id=str(uuid4()),
            user_id=str(mock_user.id),
            account_id="test-account",
            max_portfolio_exposure_usdt=10000.0,
            max_daily_loss_usdt=500.0,  # Positive value (means max loss is -500)
            max_weekly_loss_usdt=None,
            max_daily_loss_pct=None,
            max_weekly_loss_pct=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        # Mock database service
        with patch('app.api.routes.risk_metrics.DatabaseService') as MockDBService, \
             patch('app.api.routes.risk_metrics.RiskManagementService') as MockRiskService, \
             patch('app.api.routes.risk_metrics.TradeService') as MockTradeService:
            
            # Setup database service mocks
            mock_db_service = MagicMock()
            mock_db_service.get_strategy.return_value = mock_strategy
            mock_db_service.get_account_by_uuid.return_value = mock_account
            mock_db_service.get_enforcement_events.return_value = ([], 0)  # No enforcement events
            MockDBService.return_value = mock_db_service
            
            # Setup risk service mocks
            mock_risk_service = MagicMock()
            mock_risk_service.get_risk_config.return_value = mock_risk_config
            MockRiskService.return_value = mock_risk_service
            
            # Setup trade service mocks - NO TRADES
            mock_trade_service = MagicMock()
            mock_trade_service.get_trades_by_account.return_value = []  # Empty list = no trades
            MockTradeService.return_value = mock_trade_service
            
            # Call the API endpoint (simulating backend)
            strategy_id = str(mock_strategy.id)
            api_response = await get_strategy_risk_status(
                strategy_id=strategy_id,
                current_user=mock_user,
                db=mock_db
            )
            
            # Simulate frontend processing
            def simulate_frontend_load_risk_status(api_response_dict):
                """Simulates the frontend loadRiskStatus function."""
                risk_status = api_response_dict.copy()
                
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
                
                # Safety check
                if (risk_status.get('can_trade') == False and 
                    (not risk_status.get('blocked_reasons') or len(risk_status.get('blocked_reasons', [])) == 0) and
                    not risk_status.get('circuit_breaker_active', False)):
                    risk_status['can_trade'] = True
                
                return risk_status
            
            def simulate_frontend_update_risk_status_ui(risk_status):
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
            
            # Convert API response to dict (as frontend would receive it)
            api_response_dict = api_response.model_dump()
            
            # Simulate frontend processing
            processed_status = simulate_frontend_load_risk_status(api_response_dict)
            ui_result = simulate_frontend_update_risk_status_ui(processed_status)
            
            # Assertions
            print(f"\n=== E2E Test Results ===")
            print(f"API Response - can_trade: {api_response.can_trade}")
            print(f"API Response - daily_loss: {api_response.risk_checks.get('daily_loss', {}).get('current_value')}")
            print(f"Frontend Processed - can_trade: {processed_status['can_trade']}")
            print(f"Frontend UI Badge: {ui_result['badge_text']}")
            print(f"Frontend UI Class: {ui_result['badge_class']}")
            print("=======================\n")
            
            # CRITICAL: Zero-trade strategies MUST show "Allowed"
            assert api_response.can_trade is True, "API should return can_trade=True for zero trades"
            assert processed_status['can_trade'] is True, "Frontend should process as can_trade=True"
            assert ui_result['badge_class'] == 'risk-allowed', f"UI should show 'risk-allowed', got '{ui_result['badge_class']}'"
            assert ui_result['badge_text'] == '✅ Allowed', f"UI should show '✅ Allowed', got '{ui_result['badge_text']}'"
            assert 'no trades yet' in ui_result['tooltip'].lower() or 'can trade normally' in ui_result['tooltip'].lower()
    
    @pytest.mark.asyncio
    async def test_zero_trades_with_incorrect_api_response(self):
        """Test that frontend corrects incorrect API responses for zero-trade strategies."""
        
        # Simulate an incorrect API response (shouldn't happen with our fixes, but test the frontend correction)
        incorrect_api_response = {
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
        
        def simulate_frontend_load_risk_status(api_response_dict):
            """Simulates the frontend loadRiskStatus function."""
            risk_status = api_response_dict.copy()
            
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
            
            return risk_status
        
        def simulate_frontend_update_risk_status_ui(risk_status):
            """Simulates the frontend updateRiskStatusUI function."""
            daily_loss_value = risk_status.get('risk_checks', {}).get('daily_loss', {}).get('current_value')
            has_zero_trades = daily_loss_value == 0 or daily_loss_value == 0.0
            
            if risk_status.get('circuit_breaker_active', False):
                return {'badge_class': 'risk-paused', 'badge_text': '⏸️ Paused'}
            elif has_zero_trades:
                return {'badge_class': 'risk-allowed', 'badge_text': '✅ Allowed'}
            elif not risk_status.get('can_trade', True):
                return {'badge_class': 'risk-blocked', 'badge_text': '🚫 Blocked'}
            else:
                return {'badge_class': 'risk-allowed', 'badge_text': '✅ Allowed'}
        
        # Process incorrect response
        corrected = simulate_frontend_load_risk_status(incorrect_api_response)
        ui_result = simulate_frontend_update_risk_status_ui(corrected)
        
        # Assertions
        assert corrected['can_trade'] is True, "Frontend should correct can_trade to True"
        assert corrected['risk_checks']['daily_loss']['allowed'] is True, "Frontend should correct daily_loss allowed to True"
        assert ui_result['badge_class'] == 'risk-allowed', "UI should show Allowed even with incorrect API response"
        assert ui_result['badge_text'] == '✅ Allowed', "UI should show ✅ Allowed badge"
    
    def test_frontend_json_parsing(self):
        """Test that frontend can correctly parse API JSON response."""
        import json
        
        # Simulate API response as JSON string (as frontend would receive)
        api_response_json = {
            "strategy_id": "test-123",
            "account_id": "test-account",
            "can_trade": True,
            "blocked_reasons": [],
            "circuit_breaker_active": False,
            "risk_checks": {
                "daily_loss": {
                    "allowed": True,
                    "current_value": 0.0,
                    "limit_value": 500.0
                },
                "portfolio_exposure": {
                    "allowed": True,
                    "current_value": 0.0,
                    "limit_value": 10000.0
                },
                "circuit_breaker": {
                    "allowed": True,
                    "active": False
                }
            },
            "last_enforcement_event": None
        }
        
        # Simulate frontend parsing
        json_str = json.dumps(api_response_json)
        parsed = json.loads(json_str)
        
        # Verify parsing
        assert parsed['can_trade'] is True
        assert parsed['risk_checks']['daily_loss']['current_value'] == 0.0
        assert parsed['circuit_breaker_active'] is False
        
        # Simulate frontend logic
        daily_loss_value = parsed.get('risk_checks', {}).get('daily_loss', {}).get('current_value')
        has_zero_trades = daily_loss_value == 0 or daily_loss_value == 0.0
        
        assert has_zero_trades is True
        assert parsed['can_trade'] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])









