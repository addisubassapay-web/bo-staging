#!/usr/bin/env python3
"""
Backend test suite for Kaggle integration endpoints.
Tests the new sync endpoints added for Mercari Japan dataset integration.
"""
import requests
import time
from datetime import datetime

# Configuration
BASE_URL = "https://marketplace-dropship.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"

# Test results
results = []

def log_test(name, passed, details=""):
    """Log test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append({"name": name, "passed": passed, "details": details})
    print(f"{status}: {name}")
    if details:
        print(f"   {details}")

def get_admin_token():
    """Login as admin and return JWT token."""
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        raise Exception(f"Admin login failed: {resp.status_code} {resp.text}")
    return resp.json()["token"]

def test_public_sync_status():
    """Test 1: GET /api/sync/status (PUBLIC, no auth)"""
    resp = requests.get(f"{BASE_URL}/sync/status")
    
    if resp.status_code != 200:
        log_test("GET /api/sync/status (public)", False, f"Status {resp.status_code}")
        return None
    
    data = resp.json()
    required_keys = [
        "source", "last_sync_at", "last_live_tick", "imported_count",
        "active_listings", "sold_listings", "processed_rows", "target_count",
        "live_sync_enabled"
    ]
    
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        log_test("GET /api/sync/status (public)", False, f"Missing keys: {missing_keys}")
        return None
    
    # Verify active_listings is around 10,000
    active = data["active_listings"]
    if active < 9000 or active > 11000:
        log_test("GET /api/sync/status (public)", False, 
                f"active_listings={active}, expected ~10,000")
        return None
    
    log_test("GET /api/sync/status (public)", True, 
            f"All keys present. active_listings={active}, source={data['source']}")
    return data

def test_admin_sync_status(admin_token):
    """Test 2: GET /api/admin/sync/status (ADMIN)"""
    # Test with admin token
    resp = requests.get(f"{BASE_URL}/admin/sync/status", 
                       headers={"Authorization": f"Bearer {admin_token}"})
    
    if resp.status_code != 200:
        log_test("GET /api/admin/sync/status (admin)", False, f"Status {resp.status_code}")
        return False
    
    data = resp.json()
    required_keys = [
        "source", "last_sync_at", "last_live_tick", "imported_count",
        "active_listings", "sold_listings", "processed_rows", "target_count",
        "live_sync_enabled"
    ]
    
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        log_test("GET /api/admin/sync/status (admin)", False, f"Missing keys: {missing_keys}")
        return False
    
    log_test("GET /api/admin/sync/status (admin)", True, 
            f"All keys present. active_listings={data['active_listings']}")
    
    # Test without auth (should fail with 401)
    resp_no_auth = requests.get(f"{BASE_URL}/admin/sync/status")
    if resp_no_auth.status_code == 401:
        log_test("GET /api/admin/sync/status (no auth → 401)", True, "Correctly rejected")
    else:
        log_test("GET /api/admin/sync/status (no auth → 401)", False, 
                f"Expected 401, got {resp_no_auth.status_code}")
    
    return True

def test_sync_kaggle_validations(admin_token):
    """Test 3: POST /api/admin/sync/kaggle validations"""
    
    # Test 3a: target_count < 100 → 400
    resp = requests.post(f"{BASE_URL}/admin/sync/kaggle",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        json={"target_count": 50, "replace_existing": True})
    
    if resp.status_code == 400:
        log_test("POST /api/admin/sync/kaggle (target_count < 100 → 400)", True, 
                "Correctly rejected")
    else:
        log_test("POST /api/admin/sync/kaggle (target_count < 100 → 400)", False,
                f"Expected 400, got {resp.status_code}")
    
    # Test 3b: target_count > 100000 → 400
    resp = requests.post(f"{BASE_URL}/admin/sync/kaggle",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        json={"target_count": 150000, "replace_existing": True})
    
    if resp.status_code == 400:
        log_test("POST /api/admin/sync/kaggle (target_count > 100000 → 400)", True,
                "Correctly rejected")
    else:
        log_test("POST /api/admin/sync/kaggle (target_count > 100000 → 400)", False,
                f"Expected 400, got {resp.status_code}")
    
    # Test 3c: Non-admin → 403
    resp = requests.post(f"{BASE_URL}/admin/sync/kaggle",
                        json={"target_count": 500, "replace_existing": True})
    
    if resp.status_code == 401:  # No auth = 401
        log_test("POST /api/admin/sync/kaggle (no auth → 401)", True,
                "Correctly rejected")
    else:
        log_test("POST /api/admin/sync/kaggle (no auth → 401)", False,
                f"Expected 401, got {resp.status_code}")

def test_sync_kaggle_import(admin_token):
    """Test 4: POST /api/admin/sync/kaggle with target_count=500"""
    print("\n⏳ Starting Kaggle sync with target_count=500 (this may take 10-30 seconds)...")
    
    start_time = time.time()
    resp = requests.post(f"{BASE_URL}/admin/sync/kaggle",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        json={"target_count": 500, "replace_existing": True},
                        timeout=60)
    
    elapsed = time.time() - start_time
    
    if resp.status_code != 200:
        log_test("POST /api/admin/sync/kaggle (target_count=500)", False,
                f"Status {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    
    # Verify response structure
    required_keys = ["ok", "imported", "processed", "per_category", "last_sync_at"]
    missing_keys = [k for k in required_keys if k not in data]
    
    if missing_keys:
        log_test("POST /api/admin/sync/kaggle (target_count=500)", False,
                f"Missing keys: {missing_keys}")
        return False
    
    if not data.get("ok"):
        log_test("POST /api/admin/sync/kaggle (target_count=500)", False,
                f"ok=False: {data}")
        return False
    
    imported = data.get("imported", 0)
    processed = data.get("processed", 0)
    
    # Verify imported count is around 500 (allow some variance)
    if imported < 450 or imported > 550:
        log_test("POST /api/admin/sync/kaggle (target_count=500)", False,
                f"imported={imported}, expected ~500")
        return False
    
    log_test("POST /api/admin/sync/kaggle (target_count=500)", True,
            f"imported={imported}, processed={processed}, elapsed={elapsed:.1f}s, per_category={data['per_category']}")
    
    return True

def test_live_simulation():
    """Test 5: Verify live simulation by checking last_live_tick advancement"""
    print("\n⏳ Testing live simulation (waiting 65 seconds for background scheduler)...")
    
    # Fetch initial status
    resp1 = requests.get(f"{BASE_URL}/sync/status")
    if resp1.status_code != 200:
        log_test("Live simulation verification", False, "Failed to fetch initial status")
        return False
    
    data1 = resp1.json()
    last_live_tick_1 = data1.get("last_live_tick")
    
    if not last_live_tick_1:
        log_test("Live simulation verification", False, "last_live_tick is null initially")
        return False
    
    print(f"   Initial last_live_tick: {last_live_tick_1}")
    
    # Wait 65 seconds
    print("   Waiting 65 seconds...")
    time.sleep(65)
    
    # Fetch status again
    resp2 = requests.get(f"{BASE_URL}/sync/status")
    if resp2.status_code != 200:
        log_test("Live simulation verification", False, "Failed to fetch second status")
        return False
    
    data2 = resp2.json()
    last_live_tick_2 = data2.get("last_live_tick")
    
    if not last_live_tick_2:
        log_test("Live simulation verification", False, "last_live_tick is null after wait")
        return False
    
    print(f"   Second last_live_tick: {last_live_tick_2}")
    
    # Compare timestamps
    if last_live_tick_2 > last_live_tick_1:
        log_test("Live simulation verification", True,
                f"last_live_tick advanced from {last_live_tick_1} to {last_live_tick_2}")
        return True
    else:
        log_test("Live simulation verification", False,
                f"last_live_tick did not advance: {last_live_tick_1} → {last_live_tick_2}")
        return False

def test_kaggle_data_in_listings():
    """Test 6: Verify Kaggle data in listings (USD prices, Japanese titles)"""
    resp = requests.get(f"{BASE_URL}/listings?limit=5")
    
    if resp.status_code != 200:
        log_test("Verify Kaggle data in listings", False, f"Status {resp.status_code}")
        return False
    
    listings = resp.json()
    
    if not isinstance(listings, list) or len(listings) == 0:
        log_test("Verify Kaggle data in listings", False, "No listings returned")
        return False
    
    # Check each listing
    issues = []
    for listing in listings:
        price = listing.get("price")
        title = listing.get("title", "")
        
        # Verify price is numeric and > 0.99
        if not isinstance(price, (int, float)) or price < 0.99:
            issues.append(f"Listing {listing.get('id')}: invalid price {price}")
        
        # Title should exist (may contain Japanese characters)
        if not title:
            issues.append(f"Listing {listing.get('id')}: empty title")
    
    if issues:
        log_test("Verify Kaggle data in listings", False, "; ".join(issues))
        return False
    
    # Show sample data
    sample = listings[0]
    log_test("Verify Kaggle data in listings", True,
            f"5 listings verified. Sample: title='{sample['title'][:50]}...', price=${sample['price']}")
    
    return True

def restore_target_count(admin_token):
    """Restore target_count back to 10000"""
    print("\n⏳ Restoring target_count to 10000 (this may take 30-60 seconds)...")
    
    start_time = time.time()
    resp = requests.post(f"{BASE_URL}/admin/sync/kaggle",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        json={"target_count": 10000, "replace_existing": True},
                        timeout=120)
    
    elapsed = time.time() - start_time
    
    if resp.status_code != 200:
        log_test("Restore target_count to 10000", False,
                f"Status {resp.status_code}: {resp.text}")
        return False
    
    data = resp.json()
    imported = data.get("imported", 0)
    
    log_test("Restore target_count to 10000", True,
            f"imported={imported}, elapsed={elapsed:.1f}s")
    
    return True

def main():
    print("=" * 80)
    print("KAGGLE INTEGRATION BACKEND TESTS")
    print("=" * 80)
    print()
    
    try:
        # Get admin token
        print("🔐 Logging in as admin...")
        admin_token = get_admin_token()
        print("✅ Admin login successful\n")
        
        # Run tests
        print("=" * 80)
        print("TEST 1: GET /api/sync/status (PUBLIC)")
        print("=" * 80)
        test_public_sync_status()
        print()
        
        print("=" * 80)
        print("TEST 2: GET /api/admin/sync/status (ADMIN)")
        print("=" * 80)
        test_admin_sync_status(admin_token)
        print()
        
        print("=" * 80)
        print("TEST 3: POST /api/admin/sync/kaggle VALIDATIONS")
        print("=" * 80)
        test_sync_kaggle_validations(admin_token)
        print()
        
        print("=" * 80)
        print("TEST 4: POST /api/admin/sync/kaggle (target_count=500)")
        print("=" * 80)
        test_sync_kaggle_import(admin_token)
        print()
        
        print("=" * 80)
        print("TEST 5: LIVE SIMULATION VERIFICATION")
        print("=" * 80)
        test_live_simulation()
        print()
        
        print("=" * 80)
        print("TEST 6: VERIFY KAGGLE DATA IN LISTINGS")
        print("=" * 80)
        test_kaggle_data_in_listings()
        print()
        
        print("=" * 80)
        print("CLEANUP: RESTORE TARGET_COUNT TO 10000")
        print("=" * 80)
        restore_target_count(admin_token)
        print()
        
        # Summary
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        print(f"\nTotal: {passed}/{total} tests passed ({100*passed//total}%)\n")
        
        for r in results:
            status = "✅" if r["passed"] else "❌"
            print(f"{status} {r['name']}")
            if r["details"] and not r["passed"]:
                print(f"   {r['details']}")
        
        print()
        
        if passed == total:
            print("🎉 ALL TESTS PASSED!")
        else:
            print(f"⚠️  {total - passed} test(s) failed")
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
