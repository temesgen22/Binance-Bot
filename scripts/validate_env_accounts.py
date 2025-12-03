#!/usr/bin/env python3
"""Validate .env file account configuration."""
import os
import re
from pathlib import Path


def validate_accounts():
    """Validate account configuration in .env file."""
    print("=" * 60)
    print("Validating .env Account Configuration")
    print("=" * 60)
    print()
    
    issues = []
    warnings = []
    accounts_found = []
    
    # Check for default account
    if os.environ.get('BINANCE_API_KEY') and os.environ.get('BINANCE_API_SECRET'):
        print("[OK] Default account configured")
        accounts_found.append('default')
    else:
        warnings.append("Default account (BINANCE_API_KEY/SECRET) not configured")
    
    # Check for numbered accounts (1-8)
    pattern = re.compile(r'^BINANCE_ACCOUNT_([0-9]+)_API_KEY$')
    account_numbers = set()
    
    for env_key in os.environ.keys():
        match = pattern.match(env_key)
        if match:
            account_num = match.group(1)
            account_numbers.add(account_num)
    
    print(f"\nFound {len(account_numbers)} numbered account(s): {sorted(account_numbers)}")
    print()
    
    # Validate each account
    for account_num in sorted(account_numbers):
        account_id = account_num
        api_key = os.environ.get(f'BINANCE_ACCOUNT_{account_num}_API_KEY')
        api_secret = os.environ.get(f'BINANCE_ACCOUNT_{account_num}_API_SECRET')
        name = os.environ.get(f'BINANCE_ACCOUNT_{account_num}_NAME')
        testnet = os.environ.get(f'BINANCE_ACCOUNT_{account_num}_TESTNET')
        
        print(f"Account {account_num}:")
        
        # Check required fields
        if not api_key:
            issues.append(f"Account {account_num}: BINANCE_ACCOUNT_{account_num}_API_KEY is missing")
            print(f"  [ERROR] API_KEY missing")
        else:
            print(f"  [OK] API_KEY: {api_key[:10]}...")
        
        if not api_secret:
            issues.append(f"Account {account_num}: BINANCE_ACCOUNT_{account_num}_API_SECRET is missing")
            print(f"  [ERROR] API_SECRET missing")
        else:
            print(f"  [OK] API_SECRET: {api_secret[:10]}...")
        
        # Check optional fields
        if name:
            print(f"  [OK] NAME: {name}")
        else:
            warnings.append(f"Account {account_num}: No NAME set (will use '{account_id}' as display name)")
            print(f"  [WARNING] No NAME set")
        
        if testnet:
            testnet_val = testnet.lower()
            if testnet_val in ('true', '1', 'yes'):
                print(f"  [OK] TESTNET: true (Testnet mode)")
            elif testnet_val in ('false', '0', 'no'):
                print(f"  [OK] TESTNET: false (Mainnet mode)")
            else:
                warnings.append(f"Account {account_num}: Invalid TESTNET value '{testnet}' (should be true/false)")
                print(f"  [WARNING] Invalid TESTNET value: {testnet}")
        else:
            global_testnet = os.environ.get('BINANCE_TESTNET', 'true').lower()
            print(f"  [INFO] TESTNET: not set (will use global BINANCE_TESTNET={global_testnet})")
        
        accounts_found.append(account_id)
        print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total accounts found: {len(accounts_found)}")
    print(f"  - Default: {'Yes' if 'default' in accounts_found else 'No'}")
    print(f"  - Numbered: {len([a for a in accounts_found if a != 'default'])}")
    print()
    
    if issues:
        print(f"[ERROR] Found {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        print()
    
    if warnings:
        print(f"[WARNING] Found {len(warnings)} warning(s):")
        for warning in warnings:
            print(f"  - {warning}")
        print()
    
    if not issues:
        print("[OK] Configuration is valid!")
        return True
    else:
        print("[ERROR] Configuration has issues that need to be fixed")
        return False


if __name__ == '__main__':
    # Try to load .env file if python-dotenv is available
    try:
        from dotenv import load_dotenv
        env_path = Path('.env')
        if env_path.exists():
            load_dotenv(env_path)
            print("Loaded .env file\n")
        else:
            print("Warning: .env file not found. Checking environment variables only.\n")
    except ImportError:
        print("Note: python-dotenv not installed. Checking environment variables only.\n")
    
    success = validate_accounts()
    exit(0 if success else 1)

