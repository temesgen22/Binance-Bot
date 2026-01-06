"""
Automated test script for Risk Management GUI functionality.

This script tests the API endpoints that the GUI uses.
Run with: python test_risk_management_gui.py
"""

import requests
import json
from typing import Optional, Dict, Any
import sys
import os

# Fix Windows console encoding for emoji characters
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Configuration
BASE_URL = "http://localhost:8000"
TEST_USERNAME = "test_user"
TEST_PASSWORD = "test_password"

class RiskManagementTester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.access_token: Optional[str] = None
        self.test_accounts = []
        self.test_results = []
        
    def log(self, message: str, status: str = "INFO"):
        """Log test message."""
        status_symbol = {
            "PASS": "✅",
            "FAIL": "❌",
            "INFO": "ℹ️",
            "WARN": "⚠️"
        }.get(status, "ℹ️")
        print(f"{status_symbol} {message}")
        
    def test_result(self, test_name: str, passed: bool, details: str = ""):
        """Record test result."""
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        if passed:
            self.log(f"{test_name}: PASSED", "PASS")
        else:
            self.log(f"{test_name}: FAILED - {details}", "FAIL")
    
    def auth_fetch(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> requests.Response:
        """Make authenticated API request."""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        
        if method == "GET":
            return requests.get(url, headers=headers)
        elif method == "POST":
            return requests.post(url, headers=headers, json=data)
        elif method == "PUT":
            return requests.put(url, headers=headers, json=data)
        elif method == "DELETE":
            return requests.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
    
    def login(self) -> bool:
        """Login and get access token."""
        try:
            # First check if server is running (try multiple health endpoints)
            server_running = False
            health_endpoints = ["/health", "/api/health", "/"]
            for endpoint in health_endpoints:
                try:
                    health_response = requests.get(f"{self.base_url}{endpoint}", timeout=2)
                    if health_response.status_code in [200, 404]:  # 404 means server is up, endpoint might not exist
                        server_running = True
                        self.log(f"Server is running (checked {endpoint})", "INFO")
                        break
                except requests.exceptions.RequestException:
                    continue
            
            if not server_running:
                self.log(f"Server appears to be down or unreachable", "WARN")
                self.log("Please ensure the server is running on " + self.base_url, "INFO")
                return False
            
            self.log(f"Attempting login with username: {TEST_USERNAME}", "INFO")
            try:
                response = requests.post(
                    f"{self.base_url}/api/auth/login",
                    json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
                    timeout=10
                )
            except requests.exceptions.Timeout:
                self.log(f"Login request timed out. Server may be slow or unresponsive.", "FAIL")
                self.log("Try using your actual credentials:", "INFO")
                self.log(f"   python test_risk_management_gui.py --username YOUR_USERNAME --password YOUR_PASSWORD", "INFO")
                return False
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                self.log("Login successful", "PASS")
                return True
            elif response.status_code == 401:
                self.log(f"Login failed: Invalid credentials for '{TEST_USERNAME}'", "FAIL")
                self.log("", "INFO")
                self.log("To fix this, you have two options:", "INFO")
                self.log("1. Use your existing credentials:", "INFO")
                self.log(f"   python test_risk_management_gui.py --username YOUR_USERNAME --password YOUR_PASSWORD", "INFO")
                self.log("", "INFO")
                self.log("2. Create a test user with username 'test_user' and password 'test_password'", "INFO")
                self.log("   (Register at: http://localhost:8000/register.html)", "INFO")
                return False
            else:
                self.log(f"Login failed: {response.status_code} - {response.text}", "FAIL")
                return False
        except requests.exceptions.ConnectionError as e:
            self.log(f"Connection error: Server may not be running", "FAIL")
            self.log(f"Please start the server: python -m uvicorn app.main:app --reload", "INFO")
            return False
        except Exception as e:
            self.log(f"Login error: {e}", "FAIL")
            return False
    
    def test_get_accounts(self) -> bool:
        """Test 1.1: Get all accounts."""
        try:
            response = self.auth_fetch("/accounts/list")
            if response.status_code == 200:
                accounts = response.json()
                self.test_accounts = accounts
                self.log(f"Found {len(accounts)} accounts", "INFO")
                self.test_result("Test 1.1: Get Accounts", True, f"Found {len(accounts)} accounts")
                return True
            else:
                self.test_result("Test 1.1: Get Accounts", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.test_result("Test 1.1: Get Accounts", False, str(e))
            return False
    
    def test_get_risk_config(self, account_id: str) -> bool:
        """Test getting risk config for account."""
        try:
            response = self.auth_fetch(f"/api/risk/config?account_id={account_id}")
            if response.status_code == 200:
                config = response.json()
                self.test_result(f"Test: Get Config for {account_id}", True, "Config exists")
                return True
            elif response.status_code == 404:
                self.test_result(f"Test: Get Config for {account_id}", True, "No config (expected for new account)")
                return True
            else:
                self.test_result(f"Test: Get Config for {account_id}", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.test_result(f"Test: Get Config for {account_id}", False, str(e))
            return False
    
    def test_create_risk_config(self, account_id: str) -> bool:
        """Test 2.1 & 2.2: Create risk configuration."""
        config_data = {
            "account_id": account_id,
            "max_portfolio_exposure_usdt": 10000.0,
            "max_daily_loss_usdt": 500.0,
            "max_daily_loss_pct": 0.05,
            "max_weekly_loss_usdt": 2000.0,
            "max_weekly_loss_pct": 0.1,
            "max_drawdown_pct": 0.2,
            "circuit_breaker_enabled": True,
            "max_consecutive_losses": 5,
            "rapid_loss_threshold_pct": 0.05,
            "rapid_loss_timeframe_minutes": 60,
            "circuit_breaker_cooldown_minutes": 60,
            "volatility_based_sizing_enabled": False,
            "performance_based_adjustment_enabled": False,
            "kelly_criterion_enabled": False,
            "kelly_fraction": 0.25,
            "correlation_limits_enabled": False,
            "max_correlation_exposure_pct": 0.5,
            "margin_call_protection_enabled": True,
            "min_margin_ratio": 0.1,
            "auto_reduce_order_size": False,
            "timezone": "UTC",
            "daily_loss_reset_time": "00:00:00",
            "weekly_loss_reset_day": 1
        }
        
        try:
            response = self.auth_fetch("/api/risk/config", "POST", config_data)
            if response.status_code == 201:
                config = response.json()
                self.test_result(f"Test 2.x: Create Config for {account_id}", True, "Config created")
                return True
            else:
                error = response.json() if response.text else {}
                self.test_result(f"Test 2.x: Create Config for {account_id}", False, 
                               f"Status: {response.status_code}, Error: {error.get('detail', 'Unknown')}")
                return False
        except Exception as e:
            self.test_result(f"Test 2.x: Create Config for {account_id}", False, str(e))
            return False
    
    def test_update_risk_config(self, account_id: str) -> bool:
        """Test 2.3: Update risk configuration."""
        update_data = {
            "max_daily_loss_usdt": 600.0,  # Changed from 500
            "max_consecutive_losses": 6  # Changed from 5
        }
        
        try:
            response = self.auth_fetch(f"/api/risk/config?account_id={account_id}", "PUT", update_data)
            if response.status_code == 200:
                config = response.json()
                # Verify changes
                if config.get("max_daily_loss_usdt") == 600.0 and config.get("max_consecutive_losses") == 6:
                    self.test_result(f"Test 2.3: Update Config for {account_id}", True, "Config updated correctly")
                    return True
                else:
                    self.test_result(f"Test 2.3: Update Config for {account_id}", False, "Values not updated correctly")
                    return False
            else:
                error = response.json() if response.text else {}
                self.test_result(f"Test 2.3: Update Config for {account_id}", False, 
                               f"Status: {response.status_code}, Error: {error.get('detail', 'Unknown')}")
                return False
        except Exception as e:
            self.test_result(f"Test 2.3: Update Config for {account_id}", False, str(e))
            return False
    
    def test_delete_risk_config(self, account_id: str) -> bool:
        """Test 2.4: Delete risk configuration."""
        try:
            response = self.auth_fetch(f"/api/risk/config?account_id={account_id}", "DELETE")
            if response.status_code == 204:
                # Verify deletion
                get_response = self.auth_fetch(f"/api/risk/config?account_id={account_id}")
                if get_response.status_code == 404:
                    self.test_result(f"Test 2.4: Delete Config for {account_id}", True, "Config deleted")
                    return True
                else:
                    self.test_result(f"Test 2.4: Delete Config for {account_id}", False, "Config still exists")
                    return False
            else:
                error = response.json() if response.text else {}
                self.test_result(f"Test 2.4: Delete Config for {account_id}", False, 
                               f"Status: {response.status_code}, Error: {error.get('detail', 'Unknown')}")
                return False
        except Exception as e:
            self.test_result(f"Test 2.4: Delete Config for {account_id}", False, str(e))
            return False
    
    def test_portfolio_status(self, account_id: Optional[str] = None) -> bool:
        """Test 3.1 & 3.2: Get portfolio status."""
        endpoint = f"/api/risk/status/portfolio"
        if account_id:
            endpoint += f"?account_id={account_id}"
        
        try:
            response = self.auth_fetch(endpoint)
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                if status in ["active", "warning", "danger", "critical", "no_config"]:
                    self.test_result(f"Test 3.x: Portfolio Status ({account_id or 'All'})", True, f"Status: {status}")
                    return True
                else:
                    self.test_result(f"Test 3.x: Portfolio Status ({account_id or 'All'})", False, f"Invalid status: {status}")
                    return False
            else:
                self.test_result(f"Test 3.x: Portfolio Status ({account_id or 'All'})", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.test_result(f"Test 3.x: Portfolio Status ({account_id or 'All'})", False, str(e))
            return False
    
    def test_portfolio_metrics(self, account_id: Optional[str] = None) -> bool:
        """Test 3.3 & 3.4: Get portfolio metrics."""
        endpoint = f"/api/risk/metrics/portfolio"
        if account_id:
            endpoint += f"?account_id={account_id}"
        
        try:
            response = self.auth_fetch(endpoint)
            if response.status_code == 200:
                data = response.json()
                if "metrics" in data or "message" in data:
                    self.test_result(f"Test 3.x: Portfolio Metrics ({account_id or 'All'})", True, "Metrics retrieved")
                    return True
                else:
                    self.test_result(f"Test 3.x: Portfolio Metrics ({account_id or 'All'})", False, "Invalid response format")
                    return False
            else:
                self.test_result(f"Test 3.x: Portfolio Metrics ({account_id or 'All'})", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.test_result(f"Test 3.x: Portfolio Metrics ({account_id or 'All'})", False, str(e))
            return False
    
    def test_daily_report(self) -> bool:
        """Test 3.6: Get daily report."""
        try:
            response = self.auth_fetch("/api/risk/reports/daily")
            if response.status_code == 200:
                data = response.json()
                if "date" in data and "summary" in data:
                    self.test_result("Test 3.6: Daily Report", True, "Report retrieved")
                    return True
                else:
                    self.test_result("Test 3.6: Daily Report", False, "Invalid response format")
                    return False
            else:
                self.test_result("Test 3.6: Daily Report", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.test_result("Test 3.6: Daily Report", False, str(e))
            return False
    
    def test_weekly_report(self) -> bool:
        """Test 3.7: Get weekly report."""
        try:
            response = self.auth_fetch("/api/risk/reports/weekly")
            if response.status_code == 200:
                data = response.json()
                if "week_start" in data and "summary" in data:
                    self.test_result("Test 3.7: Weekly Report", True, "Report retrieved")
                    return True
                else:
                    self.test_result("Test 3.7: Weekly Report", False, "Invalid response format")
                    return False
            else:
                self.test_result("Test 3.7: Weekly Report", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.test_result("Test 3.7: Weekly Report", False, str(e))
            return False
    
    def run_all_tests(self):
        """Run all test cases."""
        self.log("=" * 60)
        self.log("Starting Risk Management GUI Tests")
        self.log("=" * 60)
        
        # Login
        if not self.login():
            self.log("Cannot proceed without authentication", "FAIL")
            return
        
        # Test 1: Get accounts
        self.test_get_accounts()
        
        # Get account IDs for testing
        account_ids = ["default"]
        if self.test_accounts:
            for acc in self.test_accounts[:2]:  # Test with first 2 accounts
                acc_id = acc.get("account_id") or acc.get("id")
                if acc_id and acc_id != "default":
                    account_ids.append(acc_id)
        
        self.log(f"Testing with accounts: {account_ids}", "INFO")
        
        # Test 2: Configuration Management
        for account_id in account_ids[:2]:  # Test with 2 accounts
            # Check if config exists
            self.test_get_risk_config(account_id)
            
            # Create config
            if self.test_create_risk_config(account_id):
                # Update config
                self.test_update_risk_config(account_id)
                
                # Test 7.2: Delete and recreate
                if self.test_delete_risk_config(account_id):
                    self.test_create_risk_config(account_id)  # Recreate
        
        # Test 3: Dashboard
        self.test_portfolio_status()  # All accounts
        self.test_portfolio_metrics()  # All accounts
        
        for account_id in account_ids[:2]:
            self.test_portfolio_status(account_id)
            self.test_portfolio_metrics(account_id)
        
        # Test Reports
        self.test_daily_report()
        self.test_weekly_report()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        self.log("=" * 60)
        self.log("Test Summary")
        self.log("=" * 60)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["passed"])
        failed = total - passed
        
        self.log(f"Total Tests: {total}")
        self.log(f"Passed: {passed} ✅")
        self.log(f"Failed: {failed} ❌")
        
        if failed > 0:
            self.log("\nFailed Tests:", "WARN")
            for result in self.test_results:
                if not result["passed"]:
                    self.log(f"  - {result['test']}: {result['details']}", "FAIL")
        
        self.log("=" * 60)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Risk Management GUI API endpoints")
    parser.add_argument("--url", default=BASE_URL, help="Base URL of the API")
    parser.add_argument("--username", default=TEST_USERNAME, help="Test username")
    parser.add_argument("--password", default=TEST_PASSWORD, help="Test password")
    
    args = parser.parse_args()
    
    BASE_URL = args.url
    TEST_USERNAME = args.username
    TEST_PASSWORD = args.password
    
    tester = RiskManagementTester(BASE_URL)
    tester.run_all_tests()
    
    # Exit with error code if any tests failed
    failed = sum(1 for r in tester.test_results if not r["passed"])
    sys.exit(1 if failed > 0 else 0)

