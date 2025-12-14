# Migration Guide: .env to Database Accounts

This guide explains how to migrate accounts from `.env` file to the database.

## Overview

The system now supports storing exchange accounts in the database instead of the `.env` file. This provides:
- ✅ Multi-user support
- ✅ Exchange platform identification (Binance, Bybit, OKX, etc.)
- ✅ Better security (encrypted storage)
- ✅ Easier management via GUI

## Migration Steps

### 1. Add Exchange Platform Column

First, add the `exchange_platform` column to the accounts table:

```bash
python scripts/migrate_add_exchange_platform.py
```

### 2. Migrate .env Accounts to Database

Migrate all accounts from `.env` file to database for user `teme.2000@gmail.com`:

```bash
python scripts/migrate_env_to_database.py
```

This script will:
- Find or create user with email `teme.2000@gmail.com`
- Read all accounts from `.env` file
- Migrate them to database
- Set the first account as default
- Skip accounts that already exist

### 3. Verify Migration

1. Log in to the application with `teme.2000@gmail.com`
2. Go to `/test-accounts` page
3. Verify all accounts are listed
4. Test each account to ensure credentials work

### 4. Remove .env Accounts (Optional)

After verifying everything works, you can remove API keys from `.env` file:

```env
# Remove or comment out these lines:
# BINANCE_API_KEY=...
# BINANCE_API_SECRET=...
# BINANCE_ACCOUNT_*_API_KEY=...
# BINANCE_ACCOUNT_*_API_SECRET=...
```

**Note:** Keep other configuration in `.env` (database URL, Redis, etc.)

## Exchange Platform Support

The system now supports multiple exchange platforms:
- **Binance** (default)
- **Bybit**
- **OKX**
- **Kraken**
- **Coinbase**
- **Other** (custom)

When creating accounts via the GUI, select the appropriate exchange platform.

## API URLs Reference

Exchange API URLs are documented in `env.example` for reference:
- Binance: https://fapi.binance.com (Production), https://testnet.binancefuture.com (Testnet)
- Bybit: https://api.bybit.com (Production), https://api-testnet.bybit.com (Testnet)
- OKX: https://www.okx.com
- Kraken: https://api.kraken.com
- Coinbase: https://api.coinbase.com

## Default Password

The migration script creates a user with default password: `changeme123`

**⚠️ IMPORTANT:** Change this password immediately after migration!

## Troubleshooting

### Migration fails with "Column already exists"
- The column was already added. This is fine, continue to step 2.

### Migration fails with "User already exists"
- The user already exists. Accounts will be added to the existing user.

### Account already exists in database
- The script will skip accounts that already exist. This prevents duplicates.

### Can't log in after migration
- Default password is `changeme123`
- Use the email `teme.2000@gmail.com` to log in
- Change password after first login

