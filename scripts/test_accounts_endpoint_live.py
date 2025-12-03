#!/usr/bin/env python3
"""Test the accounts endpoint with actual .env file."""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from app.main import create_app

# Load .env file
load_dotenv('.env')

print("=" * 60)
print("Testing /accounts/list endpoint with .env file")
print("=" * 60)
print()

# Check what's in environment
print("Environment variables found:")
for key in sorted(os.environ.keys()):
    if 'BINANCE' in key and 'ACCOUNT' in key:
        value = os.environ[key]
        if 'SECRET' in key:
            print(f"  {key}: {value[:10]}...")
        else:
            print(f"  {key}: {value}")
print()

# Test endpoint
app = create_app()
client = TestClient(app)

print("Calling /accounts/list endpoint...")
response = client.get("/accounts/list")
print(f"Status Code: {response.status_code}")
print()

if response.status_code == 200:
    accounts = response.json()
    print(f"Response Type: {type(accounts)}")
    print(f"Account Count: {len(accounts) if isinstance(accounts, dict) else 'Invalid'}")
    print()
    
    if isinstance(accounts, dict):
        print("Accounts returned:")
        for account_id, account_info in accounts.items():
            print(f"  - {account_id}:")
            print(f"      name: {account_info.get('name', 'N/A')}")
            print(f"      testnet: {account_info.get('testnet', 'N/A')}")
            print(f"      account_id: {account_info.get('account_id', 'N/A')}")
        print()
        
        if len(accounts) > 0:
            print(f"[OK] Endpoint returned {len(accounts)} account(s)")
        else:
            print("[ERROR] Endpoint returned empty dictionary")
    else:
        print(f"[ERROR] Unexpected response format: {accounts}")
else:
    print(f"[ERROR] HTTP {response.status_code}")
    print(f"Response: {response.text}")

