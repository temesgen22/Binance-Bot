#!/usr/bin/env python3
"""Test script to verify the accounts endpoint works correctly."""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app.main import create_app


def test_accounts_endpoint():
    """Test the /accounts/list endpoint."""
    print("=" * 60)
    print("Testing /accounts/list endpoint")
    print("=" * 60)
    print()
    
    # Check environment
    print("Environment check:")
    print(f"  BINANCE_API_KEY: {'SET' if os.environ.get('BINANCE_API_KEY') else 'NOT SET'}")
    print(f"  BINANCE_API_SECRET: {'SET' if os.environ.get('BINANCE_API_SECRET') else 'NOT SET'}")
    
    # Check for numbered accounts
    account_count = 0
    for i in range(1, 9):
        if os.environ.get(f'BINANCE_ACCOUNT_{i}_API_KEY'):
            account_count += 1
            print(f"  BINANCE_ACCOUNT_{i}_API_KEY: SET")
    
    print(f"  Numbered accounts found: {account_count}")
    print()
    
    # Test endpoint
    print("Testing endpoint...")
    app = create_app()
    client = TestClient(app)
    
    try:
        response = client.get("/accounts/list")
        print(f"  Status Code: {response.status_code}")
        
        if response.status_code == 200:
            accounts = response.json()
            print(f"  Response Type: {type(accounts)}")
            print(f"  Account Count: {len(accounts) if isinstance(accounts, dict) else 'Invalid format'}")
            print()
            
            if isinstance(accounts, dict) and len(accounts) > 0:
                print("  Accounts found:")
                for account_id, account_info in accounts.items():
                    print(f"    - {account_id}: {account_info.get('name', 'N/A')} (Testnet: {account_info.get('testnet', 'N/A')})")
                print()
                print("[OK] Endpoint is working correctly!")
                return True
            else:
                print("  [WARNING] No accounts found in response")
                print(f"  Response: {accounts}")
                print()
                print("[ERROR] Endpoint returned empty result")
                return False
        else:
            print(f"  [ERROR] HTTP {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"  [ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_accounts_endpoint()
    sys.exit(0 if success else 1)

