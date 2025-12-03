"""API routes for managing Binance accounts."""
import os
import re
from fastapi import APIRouter, Depends, Request
from typing import Dict

from app.core.binance_client_manager import BinanceClientManager
from app.core.config import BinanceAccountConfig


router = APIRouter(prefix="/accounts", tags=["accounts"])


def get_client_manager(request: Request) -> BinanceClientManager:
    """Dependency to get BinanceClientManager from app state."""
    if not hasattr(request.app.state, 'binance_client_manager'):
        from loguru import logger
        logger.warning("binance_client_manager not found in app state, creating fallback")
        # Try to create one as fallback
        from app.core.binance_client_manager import BinanceClientManager
        from app.core.config import get_settings
        # Clear cache to ensure fresh settings from .env
        get_settings.cache_clear()
        settings = get_settings()
        # Force reload accounts
        settings._binance_accounts = None
        manager = BinanceClientManager(settings)
        request.app.state.binance_client_manager = manager
        logger.info(f"Created BinanceClientManager as fallback with {len(manager.list_accounts())} accounts")
    return request.app.state.binance_client_manager


@router.get("/debug")
def debug_accounts(
    client_manager: BinanceClientManager = Depends(get_client_manager)
) -> Dict:
    """Debug endpoint to check account loading status."""
    from app.core.config import get_settings
    import os
    
    settings = get_settings()
    accounts_from_settings = settings.get_binance_accounts()
    accounts_from_manager = client_manager.list_accounts()
    
    # Check environment variables
    env_accounts = {}
    pattern = re.compile(r'^BINANCE_ACCOUNT_([A-Za-z0-9_]+)_API_KEY$')
    for env_key in os.environ.keys():
        match = pattern.match(env_key)
        if match:
            account_id = match.group(1).lower()
            if account_id not in env_accounts:
                env_accounts[account_id] = {
                    'api_key_set': True,
                    'api_secret_set': bool(os.environ.get(f'BINANCE_ACCOUNT_{match.group(1)}_API_SECRET')),
                }
    
    return {
        'settings_accounts_count': len(accounts_from_settings),
        'settings_account_ids': list(accounts_from_settings.keys()),
        'manager_accounts_count': len(accounts_from_manager),
        'manager_account_ids': list(accounts_from_manager.keys()),
        'env_accounts_found': len(env_accounts),
        'env_account_ids': list(env_accounts.keys()),
        'env_account_details': env_accounts,
        'default_api_key_set': bool(os.environ.get('BINANCE_API_KEY')),
        'default_api_secret_set': bool(os.environ.get('BINANCE_API_SECRET')),
    }


@router.get("/list")
def list_accounts(
    client_manager: BinanceClientManager = Depends(get_client_manager)
) -> Dict[str, Dict[str, str]]:
    """List all configured Binance accounts.
    
    Returns:
        Dictionary mapping account_id to account configuration
        
    Example response:
        {
            "default": {
                "account_id": "default",
                "name": "Default Account",
                "testnet": "True"
            },
            "1": {
                "account_id": "1",
                "name": "Account 1",
                "testnet": "False"
            }
        }
    """
    try:
        accounts = client_manager.list_accounts()
        from loguru import logger
        logger.debug(f"Client manager has {len(accounts)} accounts: {list(accounts.keys())}")
        
        if not accounts or len(accounts) == 0:
            logger.warning("No accounts found in client_manager, checking settings directly")
            from app.core.config import get_settings
            settings = get_settings()
            settings._binance_accounts = None  # Force reload
            direct_accounts = settings.get_binance_accounts()
            logger.info(f"Settings has {len(direct_accounts)} accounts: {list(direct_accounts.keys())}")
            # If settings has accounts but manager doesn't, recreate manager
            if len(direct_accounts) > len(accounts):
                logger.warning("Recreating client manager to load missing accounts")
                from app.core.binance_client_manager import BinanceClientManager
                client_manager = BinanceClientManager(settings)
                accounts = client_manager.list_accounts()
                logger.info(f"After recreation, manager has {len(accounts)} accounts")
        
        result = {
            account_id: {
                "account_id": config.account_id,
                "name": config.name or config.account_id,
                "testnet": str(config.testnet),
            }
            for account_id, config in accounts.items()
        }
        # Log for debugging
        logger.info(f"Returning {len(result)} accounts: {list(result.keys())}")
        return result
    except Exception as e:
        from loguru import logger
        logger.error(f"Error listing accounts: {e}", exc_info=True)
        # Return at least default account if available
        return {
            "default": {
                "account_id": "default",
                "name": "Default Account",
                "testnet": "True"
            }
        }

