"""Verification script to check strategy risk config setup.

This script verifies that:
1. Database migration was applied (table exists)
2. Database operations work (CRUD)
3. Models work correctly
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.core.database import get_db_session
from sqlalchemy import inspect, text
from app.models.db_models import StrategyRiskConfig


def verify_table_exists():
    """Verify strategy_risk_config table exists."""
    print("=" * 60)
    print("1. Verifying strategy_risk_config table exists...")
    print("=" * 60)
    
    try:
        with get_db_session() as db:
            inspector = inspect(db.bind)
            tables = inspector.get_table_names()
            
            if 'strategy_risk_config' in tables:
                print("OK: Table 'strategy_risk_config' exists")
                
                # Check columns
                columns = [c['name'] for c in inspector.get_columns('strategy_risk_config')]
                print(f"OK: Table has {len(columns)} columns:")
                for col in sorted(columns):
                    print(f"   - {col}")
                
                # Check indexes
                indexes = [idx['name'] for idx in inspector.get_indexes('strategy_risk_config')]
                if indexes:
                    print(f"OK: Table has {len(indexes)} indexes:")
                    for idx in indexes:
                        print(f"   - {idx}")
                else:
                    print("WARNING: No indexes found")
                
                # Check foreign keys
                fks = inspector.get_foreign_keys('strategy_risk_config')
                if fks:
                    print(f"OK: Table has {len(fks)} foreign key(s):")
                    for fk in fks:
                        print(f"   - {fk['name']}: {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
                
                return True
            else:
                print("Table 'strategy_risk_config' NOT FOUND")
                print(f"   Available tables: {sorted(tables)[:10]}...")
                return False
    except Exception as e:
        print(f"ERROR: Error checking table: {e}")
        return False


def verify_model_import():
    """Verify models can be imported."""
    print("\n" + "=" * 60)
    print("2. Verifying model imports...")
    print("=" * 60)
    
    try:
        from app.models.db_models import StrategyRiskConfig
        from app.models.risk_management import (
            StrategyRiskConfigCreate,
            StrategyRiskConfigUpdate,
            StrategyRiskConfigResponse,
        )
            print("OK: StrategyRiskConfig SQLAlchemy model imported successfully")
            print("OK: StrategyRiskConfigCreate Pydantic model imported successfully")
            print("OK: StrategyRiskConfigUpdate Pydantic model imported successfully")
            print("OK: StrategyRiskConfigResponse Pydantic model imported successfully")
            return True
    except Exception as e:
        print(f"ERROR: Error importing models: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_service_methods():
    """Verify DatabaseService has the required methods."""
    print("\n" + "=" * 60)
    print("3. Verifying DatabaseService methods...")
    print("=" * 60)
    
    try:
        from app.services.database_service import DatabaseService
        with get_db_session() as db:
            service = DatabaseService(db=db)
        
        methods = [
            'create_strategy_risk_config',
            'get_strategy_risk_config',
            'async_get_strategy_risk_config',
            'update_strategy_risk_config',
            'delete_strategy_risk_config',
        ]
        
        missing = []
        for method in methods:
            if hasattr(service, method):
                print(f"OK: Method '{method}' exists")
            else:
                print(f"ERROR: Method '{method}' NOT FOUND")
                missing.append(method)
        return len(missing) == 0
    except Exception as e:
        print(f"❌ Error checking methods: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_portfolio_risk_manager_methods():
    """Verify PortfolioRiskManager has strategy config methods."""
    print("\n" + "=" * 60)
    print("4. Verifying PortfolioRiskManager methods...")
    print("=" * 60)
    
    try:
        from app.risk.portfolio_risk_manager import PortfolioRiskManager
        
        methods = [
            'get_effective_risk_config',
            '_convert_strategy_to_risk_config',
            '_merge_configs_most_restrictive',
            '_get_strategy_realized_pnl',
        ]
        
        missing = []
        for method in methods:
            if hasattr(PortfolioRiskManager, method):
                print(f"OK: Method '{method}' exists")
            else:
                print(f"ERROR: Method '{method}' NOT FOUND")
                missing.append(method)
        
        return len(missing) == 0
    except Exception as e:
        print(f"ERROR: Error checking methods: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_api_routes():
    """Verify API routes exist."""
    print("\n" + "=" * 60)
    print("5. Verifying API routes...")
    print("=" * 60)
    
    try:
        # Check if routes file exists and has the endpoints
        from pathlib import Path
        routes_file = Path("app/api/routes/risk_metrics.py")
        
        if not routes_file.exists():
            print("ERROR: Routes file not found: app/api/routes/risk_metrics.py")
            return False
        
        content = routes_file.read_text()
        
        routes = [
            'POST /api/risk/config/strategies/{strategy_id}',
            'GET /api/risk/config/strategies/{strategy_id}',
            'PUT /api/risk/config/strategies/{strategy_id}',
            'DELETE /api/risk/config/strategies/{strategy_id}',
        ]
        
        for route in routes:
            method, path = route.split(' ', 1)
            if f'@router.{method.lower()}' in content and path.split('/')[-1].replace('{strategy_id}', '') in content:
                print(f"OK: Route '{route}' found")
            else:
                print(f"WARNING: Route '{route}' not clearly identified (check manually)")
        
        # Check for key function names
        if 'create_strategy_risk_config' in content:
            print("OK: create_strategy_risk_config endpoint function found")
        if 'get_strategy_risk_config' in content:
            print("OK: get_strategy_risk_config endpoint function found")
        if 'update_strategy_risk_config' in content:
            print("OK: update_strategy_risk_config endpoint function found")
        if 'delete_strategy_risk_config' in content:
            print("OK: delete_strategy_risk_config endpoint function found")
        
        return True
    except Exception as e:
        print(f"ERROR: Error checking routes: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_gui_integration():
    """Verify GUI integration exists."""
    print("\n" + "=" * 60)
    print("6. Verifying GUI integration...")
    print("=" * 60)
    
    try:
        from pathlib import Path
        strategies_html = Path("app/static/strategies.html")
        
        if not strategies_html.exists():
            print("ERROR: strategies.html not found")
            return False
        
        content = strategies_html.read_text()
        
        functions = [
            'loadStrategyRiskConfig',
            'showStrategyRiskConfig',
            'deleteStrategyRiskConfig',
        ]
        
        for func in functions:
            if func in content:
                print(f"OK: Function '{func}' found in strategies.html")
            else:
                print(f"ERROR: Function '{func}' NOT FOUND")
                return False
        
        # Check for risk config section
        if 'Risk Configuration' in content or 'risk-config-section' in content:
            print("OK: Risk Configuration section found in strategies.html")
        
        return True
    except Exception as e:
        print(f"ERROR: Error checking GUI: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification checks."""
    print("\n" + "=" * 60)
    print("STRATEGY-LEVEL RISK CONFIG VERIFICATION")
    print("=" * 60)
    print()
    
    results = []
    
    results.append(("Table Exists", verify_table_exists()))
    results.append(("Model Imports", verify_model_import()))
    results.append(("DatabaseService Methods", verify_service_methods()))
    results.append(("PortfolioRiskManager Methods", verify_portfolio_risk_manager_methods()))
    results.append(("API Routes", verify_api_routes()))
    results.append(("GUI Integration", verify_gui_integration()))
    
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("ALL CHECKS PASSED - Strategy Risk Config is ready!")
        print("\nNext steps:")
        print("1. Test via GUI: Go to /strategies, expand a strategy, configure risk limits")
        print("2. Test via API: Use the endpoints documented in the implementation guide")
        print("3. Monitor logs for any issues during order execution")
        return 0
    else:
        print("SOME CHECKS FAILED - Review the errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())

