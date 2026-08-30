#!/usr/bin/env python3
"""
Backend API tests for NEW Apify integration endpoints.
Tests ONLY the Apify sync endpoints (does NOT re-test previous phases).
"""
import requests
import sys
import time

BASE_URL = "https://ocean-marketplace.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"
USER_EMAIL = "sophia_style@demo.local"
USER_PASSWORD = "demo1234"


def login(email: str, password: str) -> str:
    """Login and return JWT token."""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        print(f"❌ Login failed for {email}: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json()["token"]


def test_public_sync_status():
    """Test 1: GET /api/sync/status (PUBLIC, no auth)"""
    print("\n=== Test 1: GET /api/sync/status (PUBLIC) ===")
    resp = requests.get(f"{BASE_URL}/sync/status")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    data = resp.json()
    print(f"Response: {data}")
    
    # Verify all required keys are present
    required_keys = [
        "source", "last_sync_at", "started_at", "last_live_tick",
        "imported_count", "raw_items", "active_listings", "sold_listings",
        "total_listings", "target_count", "sync_running", "message",
        "per_category", "live_sync_enabled"
    ]
    for key in required_keys:
        assert key in data, f"Missing key: {key}"
    
    # Verify specific values
    assert data["source"] == "junglee/amazon-crawler", f"Expected source='junglee/amazon-crawler', got {data['source']}"
    assert data["sync_running"] == False, f"Expected sync_running=false, got {data['sync_running']}"
    assert data["imported_count"] >= 900, f"Expected imported_count ~971, got {data['imported_count']}"
    assert data["active_listings"] > 500, f"Expected active_listings > 500, got {data['active_listings']}"
    assert data["live_sync_enabled"] == True, f"Expected live_sync_enabled=true, got {data['live_sync_enabled']}"
    
    print(f"✅ PASS: Public sync status endpoint working")
    print(f"   - source: {data['source']}")
    print(f"   - imported_count: {data['imported_count']}")
    print(f"   - active_listings: {data['active_listings']}")
    print(f"   - sync_running: {data['sync_running']}")
    return data


def test_admin_sync_status(admin_token: str):
    """Test 2: GET /api/admin/sync/status (ADMIN)"""
    print("\n=== Test 2: GET /api/admin/sync/status (ADMIN) ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.get(f"{BASE_URL}/admin/sync/status", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    data = resp.json()
    
    # Verify same schema as public endpoint
    required_keys = [
        "source", "last_sync_at", "started_at", "last_live_tick",
        "imported_count", "raw_items", "active_listings", "sold_listings",
        "total_listings", "target_count", "sync_running", "message",
        "per_category", "live_sync_enabled"
    ]
    for key in required_keys:
        assert key in data, f"Missing key: {key}"
    
    print(f"✅ PASS: Admin sync status endpoint working (same schema as public)")
    return data


def test_admin_sync_status_non_admin(user_token: str):
    """Test 3: GET /api/admin/sync/status as non-admin (should return 401/403)"""
    print("\n=== Test 3: GET /api/admin/sync/status as non-admin ===")
    headers = {"Authorization": f"Bearer {user_token}"}
    resp = requests.get(f"{BASE_URL}/admin/sync/status", headers=headers)
    assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
    print(f"✅ PASS: Non-admin correctly rejected with {resp.status_code}")


def test_trigger_apify_sync_valid(admin_token: str):
    """Test 4: POST /api/admin/sync/apify with valid payload"""
    print("\n=== Test 4: POST /api/admin/sync/apify (valid payload) ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Note: Using 100 (minimum valid value) instead of 50 from review request
    # Backend validation requires 100-20000 range
    payload = {"target_count": 100, "replace_existing": False}
    
    resp = requests.post(f"{BASE_URL}/admin/sync/apify", json=payload, headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {data}")
    
    # Should return either started=true or already_running=true
    assert data.get("ok") == True, f"Expected ok=true, got {data}"
    assert "started" in data or "already_running" in data, f"Expected 'started' or 'already_running' key in response"
    
    if data.get("started"):
        print(f"✅ PASS: Sync started successfully")
    elif data.get("already_running"):
        print(f"✅ PASS: Sync already running (expected if another sync is in progress)")
    
    return data


def test_trigger_apify_sync_below_min(admin_token: str):
    """Test 5: POST /api/admin/sync/apify with target_count < 100 (should return 400)"""
    print("\n=== Test 5: POST /api/admin/sync/apify (target_count < 100) ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {"target_count": 10}
    
    resp = requests.post(f"{BASE_URL}/admin/sync/apify", json=payload, headers=headers)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    print(f"✅ PASS: target_count < 100 correctly rejected with 400")


def test_trigger_apify_sync_above_max(admin_token: str):
    """Test 6: POST /api/admin/sync/apify with target_count > 20000 (should return 400)"""
    print("\n=== Test 6: POST /api/admin/sync/apify (target_count > 20000) ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {"target_count": 50000}
    
    resp = requests.post(f"{BASE_URL}/admin/sync/apify", json=payload, headers=headers)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    print(f"✅ PASS: target_count > 20000 correctly rejected with 400")


def test_trigger_apify_sync_non_admin(user_token: str):
    """Test 7: POST /api/admin/sync/apify as non-admin (should return 401/403)"""
    print("\n=== Test 7: POST /api/admin/sync/apify as non-admin ===")
    headers = {"Authorization": f"Bearer {user_token}"}
    payload = {"target_count": 500}
    
    resp = requests.post(f"{BASE_URL}/admin/sync/apify", json=payload, headers=headers)
    assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
    print(f"✅ PASS: Non-admin correctly rejected with {resp.status_code}")


def test_real_amazon_data():
    """Test 8: Verify listings have real Amazon data (m.media-amazon.com images, English titles)"""
    print("\n=== Test 8: Real Amazon data verification ===")
    resp = requests.get(f"{BASE_URL}/listings?limit=5")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    listings = resp.json()
    assert len(listings) >= 5, f"Expected at least 5 listings, got {len(listings)}"
    
    print(f"Checking {len(listings)} listings for real Amazon data...")
    
    for i, listing in enumerate(listings, 1):
        title = listing.get("title", "")
        images = listing.get("images", [])
        brand = listing.get("brand", "")
        
        print(f"\n  Listing {i}:")
        print(f"    Title: {title[:80]}...")
        print(f"    Brand: {brand}")
        print(f"    Images: {len(images)} images")
        
        # Verify title is English (contains latin letters)
        assert any(c.isalpha() and ord(c) < 128 for c in title), f"Title does not contain English letters: {title}"
        
        # Verify at least one image contains m.media-amazon.com
        amazon_images = [img for img in images if "m.media-amazon.com" in img]
        assert len(amazon_images) > 0, f"No Amazon images found. Images: {images}"
        
        print(f"    ✓ Title is English")
        print(f"    ✓ {len(amazon_images)} Amazon image(s) found")
    
    print(f"\n✅ PASS: All {len(listings)} listings have real Amazon data (m.media-amazon.com images, English titles)")


def main():
    print("=" * 80)
    print("APIFY INTEGRATION BACKEND TESTS")
    print("Testing NEW Apify endpoints only (NOT re-testing previous phases)")
    print("=" * 80)
    
    # Login
    print("\n--- Logging in ---")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    print(f"✓ Admin logged in")
    user_token = login(USER_EMAIL, USER_PASSWORD)
    print(f"✓ Demo user logged in")
    
    # Run tests
    test_results = []
    
    try:
        test_public_sync_status()
        test_results.append(("GET /api/sync/status (PUBLIC)", "PASS"))
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
        test_results.append(("GET /api/sync/status (PUBLIC)", "FAIL"))
    
    try:
        test_admin_sync_status(admin_token)
        test_results.append(("GET /api/admin/sync/status (ADMIN)", "PASS"))
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
        test_results.append(("GET /api/admin/sync/status (ADMIN)", "FAIL"))
    
    try:
        test_admin_sync_status_non_admin(user_token)
        test_results.append(("GET /api/admin/sync/status (non-admin rejection)", "PASS"))
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
        test_results.append(("GET /api/admin/sync/status (non-admin rejection)", "FAIL"))
    
    try:
        test_trigger_apify_sync_valid(admin_token)
        test_results.append(("POST /api/admin/sync/apify (valid)", "PASS"))
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
        test_results.append(("POST /api/admin/sync/apify (valid)", "FAIL"))
    
    try:
        test_trigger_apify_sync_below_min(admin_token)
        test_results.append(("POST /api/admin/sync/apify (target < 100)", "PASS"))
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
        test_results.append(("POST /api/admin/sync/apify (target < 100)", "FAIL"))
    
    try:
        test_trigger_apify_sync_above_max(admin_token)
        test_results.append(("POST /api/admin/sync/apify (target > 20000)", "PASS"))
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
        test_results.append(("POST /api/admin/sync/apify (target > 20000)", "FAIL"))
    
    try:
        test_trigger_apify_sync_non_admin(user_token)
        test_results.append(("POST /api/admin/sync/apify (non-admin rejection)", "PASS"))
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
        test_results.append(("POST /api/admin/sync/apify (non-admin rejection)", "FAIL"))
    
    try:
        test_real_amazon_data()
        test_results.append(("Real Amazon data verification", "PASS"))
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
        test_results.append(("Real Amazon data verification", "FAIL"))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result in test_results if result == "PASS")
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅" if result == "PASS" else "❌"
        print(f"{status} {test_name}: {result}")
    
    print(f"\n{passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
