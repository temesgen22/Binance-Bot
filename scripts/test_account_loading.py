#!/usr/bin/env python3
"""Test script to verify account loading from .env file."""
import os
import sys
from pathlib import Path

# Ensure stdout can handle Unicode characters for emojis
sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from app.core.config import get_settings

def test_account_loading():
    print("\n" + "="*60)
    print("Testing Account Loading from .env file")
    print("="*60 + "\n")
    
    # Load .env file explicitly
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ Error: .env file not found!")
        return False
    
    print(f"📄 Loading .env file: {env_file.absolute()}")
    load_dotenv(env_file, override=False)
    
    # Check environment variables directly
    print("\n🔍 Checking environment variables in os.environ:")
    account_vars = [k for k in os.environ.keys() if 'BINANCE_ACCOUNT' in k]
    if account_vars:
        for var in sorted(account_vars):
            value = os.environ[var]
            if 'SECRET' in var:
                value = value[:20] + "..." if len(value) > 20 else value
            print(f"  ✅ {var}: {value}")
    else:
        print("  ⚠️  No BINANCE_ACCOUNT_* variables found in os.environ")
    
    # Clear settings cache and load
    print("\n🔄 Loading settings (clearing cache)...")
    get_settings.cache_clear()
    settings = get_settings()
    
    # Get accounts
    print("📦 Getting accounts from settings...")
    accounts = settings.get_binance_accounts()
    
    print(f"\n✅ Found {len(accounts)} account(s):")
    for account_id, account_config in sorted(accounts.items()):
        print(f"  - {account_id}:")
        print(f"      Name: {account_config.name}")
        print(f"      Testnet: {account_config.testnet}")
        print(f"      API Key: {account_config.api_key[:20]}...")
    
    expected_min = 1  # At least default account
    if len(accounts) < expected_min:
        print(f"\n❌ Expected at least {expected_min} account(s), got {len(accounts)}")
        return False
    
    print(f"\n✅ Account loading test passed! ({len(accounts)} account(s) loaded)")
    return True

if __name__ == "__main__":
    success = test_account_loading()
    sys.exit(0 if success else 1)

