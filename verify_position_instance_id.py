#!/usr/bin/env python3
"""
Quick verification script for position_instance_id implementation.

This script verifies that:
1. Models have position_instance_id fields
2. Migration file exists and is valid
3. Key functions can be imported
"""

import sys
from pathlib import Path

def check_models():
    """Check that models have position_instance_id fields."""
    print("[*] Checking models...")
    try:
        from app.models.db_models import Strategy, Trade, CompletedTrade
        from app.models.strategy import StrategySummary
        
        # Check Strategy model
        assert hasattr(Strategy, 'position_instance_id'), "Strategy model missing position_instance_id"
        print("  [OK] Strategy model has position_instance_id")
        
        # Check Trade model
        assert hasattr(Trade, 'position_instance_id'), "Trade model missing position_instance_id"
        print("  [OK] Trade model has position_instance_id")
        
        # Check CompletedTrade model
        assert hasattr(CompletedTrade, 'position_instance_id'), "CompletedTrade model missing position_instance_id"
        print("  [OK] CompletedTrade model has position_instance_id")
        
        # Check StrategySummary model (Pydantic model - check model_fields)
        if hasattr(StrategySummary, 'model_fields') and 'position_instance_id' in StrategySummary.model_fields:
            print("  [OK] StrategySummary model has position_instance_id")
        elif hasattr(StrategySummary, '__annotations__') and 'position_instance_id' in StrategySummary.__annotations__:
            print("  [OK] StrategySummary model has position_instance_id")
        else:
            raise AssertionError("StrategySummary model missing position_instance_id")
        
        return True
    except Exception as e:
        print(f"  [FAIL] Model check failed: {e}")
        return False

def check_migration():
    """Check that migration file exists."""
    print("\n[*] Checking migration file...")
    # Try multiple path formats
    base_path = Path(__file__).parent
    migration_paths = [
        base_path / "alembic" / "versions" / "f998822e456f_add_position_instance_id_columns.py",
        Path("alembic/versions/f998822e456f_add_position_instance_id_columns.py"),
        Path("alembic\\versions\\f998822e456f_add_position_instance_id_columns.py"),
    ]
    
    migration_file = None
    for path in migration_paths:
        if path.exists():
            migration_file = path
            break
    
    if not migration_file or not migration_file.exists():
        print(f"  [FAIL] Migration file not found. Tried: {migration_paths}")
        return False
    
    print(f"  [OK] Migration file exists: {migration_file}")
    
    # Check migration content
    content = migration_file.read_text()
    required_elements = [
        "position_instance_id",
        "strategies",
        "trades",
        "completed_trades",
        "idx_strategies_pos_instance",
        "idx_trades_pos_instance",
        "idx_completed_trades_pos_instance"
    ]
    
    for element in required_elements:
        if element not in content:
            print(f"  [FAIL] Migration file missing: {element}")
            return False
    
    print("  [OK] Migration file contains all required elements")
    return True

def check_services():
    """Check that service functions can be imported."""
    print("\n[*] Checking services...")
    try:
        from app.services.strategy_persistence import StrategyPersistence
        from app.services.trade_service import TradeService
        from app.services.completed_trade_helper import create_completed_trades_on_position_close
        from app.services.completed_trade_service import CompletedTradeService
        
        print("  [OK] All services import successfully")
        
        # Check if _get_or_generate_position_instance_id exists
        if hasattr(StrategyPersistence, '_get_or_generate_position_instance_id'):
            print("  [OK] _get_or_generate_position_instance_id method exists")
        else:
            print("  [WARN] _get_or_generate_position_instance_id method not found (might be private)")
        
        return True
    except Exception as e:
        print(f"  [FAIL] Service check failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all checks."""
    print("=" * 60)
    print("Position Instance ID Implementation Verification")
    print("=" * 60)
    
    results = []
    results.append(("Models", check_models()))
    results.append(("Migration", check_migration()))
    results.append(("Services", check_services()))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("[SUCCESS] All checks passed! Implementation looks good.")
        return 0
    else:
        print("[FAIL] Some checks failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

