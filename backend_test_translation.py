#!/usr/bin/env python3
"""
Backend test for NEW translation endpoints and updated sync status.
Tests ONLY the new translation features added in the latest phase.
"""
import requests
import time
import json
from typing import Dict, Any

BASE_URL = "https://bo-staging.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"

# Test credentials for non-admin user
USER_EMAIL = "sophia_style@demo.local"
USER_PASSWORD = "demo1234"


def login(email: str, password: str) -> str:
    """Login and return JWT token."""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data["token"]


def test_sync_status_includes_translation_keys():
    """Test 1: GET /api/sync/status includes new translation keys."""
    print("\n=== Test 1: GET /api/sync/status includes translation keys ===")
    resp = requests.get(f"{BASE_URL}/sync/status")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    # Verify all required keys exist
    required_keys = [
        "translated_count",
        "total_listings",
        "translation_pct",
        "translation_running",
        "translation_progress"
    ]
    
    for key in required_keys:
        assert key in data, f"Missing key: {key}"
        print(f"✓ Key '{key}' present: {data[key]}")
    
    # Verify types
    assert isinstance(data["translated_count"], int), "translated_count should be int"
    assert isinstance(data["total_listings"], int), "total_listings should be int"
    assert isinstance(data["translation_pct"], (int, float)), "translation_pct should be numeric"
    assert isinstance(data["translation_running"], bool), "translation_running should be bool"
    assert data["translation_progress"] is None or isinstance(data["translation_progress"], dict), \
        "translation_progress should be dict or null"
    
    # Verify translation_pct is in range 0-100
    assert 0 <= data["translation_pct"] <= 100, f"translation_pct should be 0-100, got {data['translation_pct']}"
    
    print(f"✅ Test 1 PASSED: All translation keys present and valid")
    print(f"   - translated_count: {data['translated_count']}")
    print(f"   - total_listings: {data['total_listings']}")
    print(f"   - translation_pct: {data['translation_pct']}%")
    print(f"   - translation_running: {data['translation_running']}")
    
    return data


def test_admin_translate_endpoint_as_admin(admin_token: str):
    """Test 2: POST /api/admin/sync/translate as admin."""
    print("\n=== Test 2: POST /api/admin/sync/translate as admin ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.post(f"{BASE_URL}/admin/sync/translate", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    # Should return either started=true or already_running=true
    assert data.get("ok") is True, "Response should have ok=true"
    assert data.get("started") is True or data.get("already_running") is True, \
        "Response should have started=true OR already_running=true"
    
    if data.get("started"):
        print("✅ Test 2 PASSED: Translation started successfully")
    else:
        print("✅ Test 2 PASSED: Translation already running (expected if called previously)")
    
    return data


def test_admin_translate_endpoint_second_call(admin_token: str):
    """Test 3: POST /api/admin/sync/translate second call (should return already_running)."""
    print("\n=== Test 3: POST /api/admin/sync/translate (second call) ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.post(f"{BASE_URL}/admin/sync/translate", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert data.get("ok") is True, "Response should have ok=true"
    # Should return already_running=true since translation is in progress
    assert data.get("already_running") is True, \
        "Second call should return already_running=true"
    
    print("✅ Test 3 PASSED: Second call correctly returns already_running=true")
    return data


def test_admin_translate_endpoint_as_non_admin(user_token: str):
    """Test 4: POST /api/admin/sync/translate as non-admin (should be rejected)."""
    print("\n=== Test 4: POST /api/admin/sync/translate as non-admin ===")
    headers = {"Authorization": f"Bearer {user_token}"}
    resp = requests.post(f"{BASE_URL}/admin/sync/translate", headers=headers)
    
    # Should be rejected with 401 or 403
    assert resp.status_code in [401, 403], \
        f"Expected 401 or 403 for non-admin, got {resp.status_code}"
    
    print(f"✅ Test 4 PASSED: Non-admin correctly rejected with {resp.status_code}")


def test_translation_progress_advancement(initial_status: Dict[str, Any]):
    """Test 5: Wait 45 seconds and verify translated_count has increased."""
    print("\n=== Test 5: Translation progress advancement ===")
    
    initial_count = initial_status["translated_count"]
    print(f"Initial translated_count: {initial_count}")
    print(f"Waiting 45 seconds for translation to progress...")
    
    time.sleep(45)
    
    resp = requests.get(f"{BASE_URL}/sync/status")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    data = resp.json()
    new_count = data["translated_count"]
    print(f"After 45s translated_count: {new_count}")
    print(f"Translation progress: {data.get('translation_progress')}")
    
    # Verify count has increased
    assert new_count > initial_count, \
        f"translated_count should have increased from {initial_count}, but got {new_count}"
    
    increase = new_count - initial_count
    print(f"✅ Test 5 PASSED: translated_count increased by {increase} (from {initial_count} to {new_count})")
    print(f"   - translation_pct: {data['translation_pct']}%")
    print(f"   - translation_running: {data['translation_running']}")


def test_data_quality_spot_check():
    """Test 6: Spot-check data quality - find 3 listings with English titles and real images."""
    print("\n=== Test 6: Data quality spot-check ===")
    
    # Query listings with translated=true
    resp = requests.get(f"{BASE_URL}/listings", params={"limit": 50})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    listings = resp.json()
    
    print(f"Fetched {len(listings)} listings")
    
    # Find listings with English titles (containing letters/spaces, not just Japanese)
    english_listings = []
    for listing in listings:
        title = listing.get("title", "")
        # Check if title contains English letters (a-z, A-Z)
        if any(c.isalpha() and ord(c) < 128 for c in title):
            english_listings.append(listing)
            if len(english_listings) >= 3:
                break
    
    assert len(english_listings) >= 3, \
        f"Expected at least 3 listings with English titles, found {len(english_listings)}"
    
    print(f"Found {len(english_listings)} listings with English titles")
    
    # Verify each listing has real image URLs
    for i, listing in enumerate(english_listings[:3], 1):
        print(f"\n--- Listing {i} ---")
        print(f"ID: {listing['id']}")
        print(f"Title: {listing['title'][:80]}...")
        print(f"Translated: {listing.get('translated', False)}")
        
        # Check image URLs
        images = listing.get("images", [])
        assert len(images) > 0, f"Listing {listing['id']} has no images"
        
        for img_url in images:
            # Verify it's from unsplash.com or pexels.com (not picsum.photos)
            assert "unsplash.com" in img_url or "pexels.com" in img_url, \
                f"Image URL should be from unsplash.com or pexels.com, got: {img_url}"
            print(f"✓ Image URL: {img_url[:60]}...")
        
        print(f"✓ Listing has {len(images)} real image(s) from unsplash/pexels")
    
    print(f"\n✅ Test 6 PASSED: Found 3+ listings with English titles and real images from unsplash/pexels")


def main():
    """Run all translation endpoint tests."""
    print("=" * 80)
    print("TRANSLATION ENDPOINTS TESTING")
    print("=" * 80)
    
    try:
        # Login as admin and regular user
        print("\n--- Logging in ---")
        admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
        print(f"✓ Admin logged in")
        
        user_token = login(USER_EMAIL, USER_PASSWORD)
        print(f"✓ Regular user logged in")
        
        # Test 1: Verify sync status includes translation keys
        initial_status = test_sync_status_includes_translation_keys()
        
        # Test 2: Trigger translation as admin
        test_admin_translate_endpoint_as_admin(admin_token)
        
        # Test 3: Second call should return already_running
        test_admin_translate_endpoint_second_call(admin_token)
        
        # Test 4: Non-admin should be rejected
        test_admin_translate_endpoint_as_non_admin(user_token)
        
        # Test 5: Wait and verify progress
        test_translation_progress_advancement(initial_status)
        
        # Test 6: Data quality spot-check
        test_data_quality_spot_check()
        
        print("\n" + "=" * 80)
        print("✅ ALL TRANSLATION TESTS PASSED (6/6)")
        print("=" * 80)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
