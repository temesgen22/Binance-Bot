"""
Verification script to demonstrate safe dual strategy configuration.

This script shows:
1. Safe configuration: Different strategy_id values
2. Dangerous configuration: Same strategy_id values (will fail)
"""

def verify_safe_configuration():
    """Demonstrate safe configuration with different strategy_id values."""
    print("=" * 70)
    print("SAFE CONFIGURATION: Different strategy_id values")
    print("=" * 70)
    
    # Strategy 1: Scalping
    strategy_1 = {
        "strategy_id": "scalping_btcusdt_account_a",  # ✅ Unique
        "strategy_type": "scalping",
        "symbol": "BTCUSDT",
        "account_id": "account_a",
        "name": "BTC Scalping (Account A)"
    }
    
    # Strategy 2: Reverse Scalping
    strategy_2 = {
        "strategy_id": "reverse_scalping_btcusdt_account_b",  # ✅ Unique
        "strategy_type": "reverse_scalping",
        "symbol": "BTCUSDT",
        "account_id": "account_b",
        "name": "BTC Reverse Scalping (Account B)"
    }
    
    print(f"\nStrategy 1:")
    print(f"  ID: {strategy_1['strategy_id']}")
    print(f"  Type: {strategy_1['strategy_type']}")
    print(f"  Account: {strategy_1['account_id']}")
    
    print(f"\nStrategy 2:")
    print(f"  ID: {strategy_2['strategy_id']}")
    print(f"  Type: {strategy_2['strategy_type']}")
    print(f"  Account: {strategy_2['account_id']}")
    
    print(f"\n[SAFE] Different strategy_id values")
    print(f"   - Database: No unique constraint violation")
    print(f"   - Redis: Different keys (binance_bot:user:{{user_id}}:strategy:{{strategy_id}})")
    print(f"   - Memory: Different dictionary keys")
    print(f"   - Accounts: Different Binance accounts (isolated execution)")
    
    return True


def verify_dangerous_configuration():
    """Demonstrate dangerous configuration with same strategy_id value."""
    print("\n" + "=" * 70)
    print("DANGEROUS CONFIGURATION: Same strategy_id value")
    print("=" * 70)
    
    # Strategy 1: Scalping
    strategy_1 = {
        "strategy_id": "btc_strategy",  # ❌ Same ID
        "strategy_type": "scalping",
        "symbol": "BTCUSDT",
        "account_id": "account_a",
        "name": "BTC Scalping (Account A)"
    }
    
    # Strategy 2: Reverse Scalping
    strategy_2 = {
        "strategy_id": "btc_strategy",  # ❌ Same ID
        "strategy_type": "reverse_scalping",
        "symbol": "BTCUSDT",
        "account_id": "account_b",
        "name": "BTC Reverse Scalping (Account B)"
    }
    
    print(f"\nStrategy 1:")
    print(f"  ID: {strategy_1['strategy_id']}")
    print(f"  Type: {strategy_1['strategy_type']}")
    print(f"  Account: {strategy_1['account_id']}")
    
    print(f"\nStrategy 2:")
    print(f"  ID: {strategy_2['strategy_id']}")  # ❌ Same as Strategy 1
    print(f"  Type: {strategy_2['strategy_type']}")
    print(f"  Account: {strategy_2['account_id']}")
    
    print(f"\n[DANGEROUS] Same strategy_id value")
    print(f"   - Database: Unique constraint violation (will FAIL)")
    print(f"   - Redis: Key collision (second overwrites first)")
    print(f"   - Memory: Dictionary overwrite (second overwrites first)")
    print(f"   - Result: Strategy 1 becomes inaccessible, potential crashes")
    
    return False


def show_best_practices():
    """Show recommended naming patterns."""
    print("\n" + "=" * 70)
    print("RECOMMENDED NAMING PATTERNS")
    print("=" * 70)
    
    patterns = [
        {
            "pattern": "{strategy_type}_{symbol}_{account_id}",
            "examples": [
                "scalping_btcusdt_account_a",
                "reverse_scalping_btcusdt_account_b",
                "scalping_ethusdt_main",
                "reverse_scalping_ethusdt_test"
            ]
        },
        {
            "pattern": "{strategy_type}_{symbol}_{account_id}_{timestamp}",
            "examples": [
                "scalping_btcusdt_account_a_20250101",
                "reverse_scalping_btcusdt_account_b_20250101"
            ]
        },
        {
            "pattern": "{account_id}_{strategy_type}_{symbol}",
            "examples": [
                "account_a_scalping_btcusdt",
                "account_b_reverse_scalping_btcusdt"
            ]
        }
    ]
    
    for i, pattern_info in enumerate(patterns, 1):
        print(f"\n{i}. Pattern: {pattern_info['pattern']}")
        print("   Examples:")
        for example in pattern_info['examples']:
            print(f"      - {example}")


def main():
    """Run verification demonstrations."""
    print("\n" + "=" * 70)
    print("DUAL STRATEGY CONFLICT VERIFICATION")
    print("=" * 70)
    print("\nThis script demonstrates safe vs dangerous configurations")
    print("for running Scalping and Reverse Scalping strategies")
    print("on the same symbol with different Binance accounts.\n")
    
    # Show safe configuration
    verify_safe_configuration()
    
    # Show dangerous configuration
    verify_dangerous_configuration()
    
    # Show best practices
    show_best_practices()
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("\n[SAFE] Use different strategy_id values")
    print("   Example: 'scalping_btcusdt_account_a' vs 'reverse_scalping_btcusdt_account_b'")
    print("\n[DANGEROUS] Use same strategy_id value")
    print("   Example: Both using 'btc_strategy'")
    print("\n[RECOMMENDATION] Always use descriptive, unique strategy_id values")
    print("   Include: strategy_type, symbol, and account_id in the name")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()

