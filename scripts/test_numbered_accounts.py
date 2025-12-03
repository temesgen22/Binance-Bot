#!/usr/bin/env python3
"""Test script to verify numbered accounts (1-8) work correctly."""
import os
from unittest.mock import patch

from app.core.config import get_settings


def test_numbered_accounts():
    """Test that numbered accounts 1-8 are properly loaded."""
    # Create test environment with accounts 1-8
    test_env = {
        'BINANCE_API_KEY': 'default_key',
        'BINANCE_API_SECRET': 'default_secret',
        'BINANCE_TESTNET': 'true',
    }
    
    # Add accounts 1-8
    for i in range(1, 9):
        test_env[f'BINANCE_ACCOUNT_{i}_API_KEY'] = f'key{i}'
        test_env[f'BINANCE_ACCOUNT_{i}_API_SECRET'] = f'secret{i}'
        test_env[f'BINANCE_ACCOUNT_{i}_NAME'] = f'Account {i}'
        test_env[f'BINANCE_ACCOUNT_{i}_TESTNET'] = 'false' if i % 2 == 0 else 'true'
    
    # Clear cache and test
    get_settings.cache_clear()
    
    with patch.dict(os.environ, test_env, clear=False):
        settings = get_settings()
        accounts = settings.get_binance_accounts()
        
        print(f"[OK] Found {len(accounts)} accounts:")
        print()
        
        # Check default account
        if 'default' in accounts:
            acc = accounts['default']
            print(f"  default: {acc.name} (Testnet: {acc.testnet})")
        
        # Check numbered accounts
        for i in range(1, 9):
            account_id = str(i)
            if account_id in accounts:
                acc = accounts[account_id]
                print(f"  {account_id}: {acc.name} (Testnet: {acc.testnet})")
            else:
                print(f"  [ERROR] Account {i} NOT FOUND!")
        
        print()
        print(f"Total accounts: {len(accounts)} (expected: 9 = 1 default + 8 numbered)")
        
        if len(accounts) == 9:
            print("[OK] All accounts loaded successfully!")
            return True
        else:
            print(f"[ERROR] Expected 9 accounts, found {len(accounts)}")
            return False


if __name__ == '__main__':
    success = test_numbered_accounts()
    exit(0 if success else 1)

