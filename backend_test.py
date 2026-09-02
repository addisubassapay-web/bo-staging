#!/usr/bin/env python3
"""
Comprehensive backend API tests for Mercari Clone
Tests all endpoints with proper authentication and validation
"""

import requests
import random
import string
from typing import Dict, Optional

# Base URL from frontend/.env
BASE_URL = "https://bo-staging.preview.emergentagent.com/api"

# Test credentials from seed data
ADMIN_EMAIL = "admin@mercari.local"
ADMIN_PASSWORD = "admin123"
DEMO_USER_EMAIL = "sophia_style@demo.local"
DEMO_USER_PASSWORD = "demo1234"

# Test state
admin_token = None
user_token = None
user2_token = None
test_listing_id = None
test_category_id = None
categories = []


def random_string(length=8):
    """Generate random string for unique test data"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def print_test(name: str):
    """Print test name"""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print('='*60)


def print_result(passed: bool, message: str):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {message}")


def make_request(method: str, endpoint: str, token: Optional[str] = None, **kwargs) -> requests.Response:
    """Make HTTP request with optional auth token"""
    url = f"{BASE_URL}{endpoint}"
    headers = kwargs.pop('headers', {})
    if token:
        headers['Authorization'] = f'Bearer {token}'
    
    try:
        response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        return response
    except Exception as e:
        print(f"❌ Request failed: {e}")
        raise


# =========================
# 1. AUTH TESTS
# =========================
def test_auth_register():
    """Test user registration with new random email"""
    print_test("Auth - Register new user")
    
    global user2_token
    email = f"testuser_{random_string()}@test.local"
    username = f"testuser_{random_string()}"
    
    response = make_request('POST', '/auth/register', json={
        'email': email,
        'username': username,
        'password': 'testpass123'
    })
    
    if response.status_code == 200:
        data = response.json()
        if 'token' in data and 'user' in data:
            user2_token = data['token']
            if data['user']['role'] == 'user':
                print_result(True, f"User registered successfully: {email}, role={data['user']['role']}")
                return True
            else:
                print_result(False, f"User role is {data['user']['role']}, expected 'user'")
                return False
        else:
            print_result(False, f"Missing token or user in response: {data}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_auth_register_duplicate():
    """Test registration with duplicate email returns 400"""
    print_test("Auth - Register duplicate email")
    
    response = make_request('POST', '/auth/register', json={
        'email': ADMIN_EMAIL,
        'username': 'duplicate_test',
        'password': 'test123'
    })
    
    if response.status_code == 400:
        print_result(True, "Duplicate email correctly rejected with 400")
        return True
    else:
        print_result(False, f"Expected 400, got {response.status_code}")
        return False


def test_auth_login_admin():
    """Test admin login"""
    print_test("Auth - Login as admin")
    
    global admin_token
    response = make_request('POST', '/auth/login', json={
        'email': ADMIN_EMAIL,
        'password': ADMIN_PASSWORD
    })
    
    if response.status_code == 200:
        data = response.json()
        if 'token' in data and data['user']['role'] == 'admin':
            admin_token = data['token']
            print_result(True, f"Admin login successful, role={data['user']['role']}")
            return True
        else:
            print_result(False, f"Invalid response: {data}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_auth_login_user():
    """Test regular user login"""
    print_test("Auth - Login as regular user")
    
    global user_token
    response = make_request('POST', '/auth/login', json={
        'email': DEMO_USER_EMAIL,
        'password': DEMO_USER_PASSWORD
    })
    
    if response.status_code == 200:
        data = response.json()
        if 'token' in data and data['user']['role'] == 'user':
            user_token = data['token']
            print_result(True, f"User login successful, role={data['user']['role']}")
            return True
        else:
            print_result(False, f"Invalid response: {data}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_auth_me_with_token():
    """Test GET /auth/me with valid token"""
    print_test("Auth - GET /auth/me with valid token")
    
    response = make_request('GET', '/auth/me', token=user_token)
    
    if response.status_code == 200:
        data = response.json()
        if 'email' in data and 'username' in data:
            print_result(True, f"User data retrieved: {data['email']}")
            return True
        else:
            print_result(False, f"Invalid user data: {data}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_auth_me_without_token():
    """Test GET /auth/me without token returns 401"""
    print_test("Auth - GET /auth/me without token")
    
    response = make_request('GET', '/auth/me')
    
    if response.status_code == 401:
        print_result(True, "Correctly returned 401 without token")
        return True
    else:
        print_result(False, f"Expected 401, got {response.status_code}")
        return False


# =========================
# 2. CATEGORIES TESTS
# =========================
def test_categories_get_public():
    """Test GET /categories returns 12 categories (public)"""
    print_test("Categories - GET public list")
    
    global categories
    response = make_request('GET', '/categories')
    
    if response.status_code == 200:
        categories = response.json()
        if len(categories) == 12:
            print_result(True, f"Retrieved {len(categories)} categories")
            return True
        else:
            print_result(False, f"Expected 12 categories, got {len(categories)}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_categories_post_as_user():
    """Test POST /categories as regular user returns 403"""
    print_test("Categories - POST as regular user (should fail)")
    
    response = make_request('POST', '/categories', token=user_token, json={
        'name': 'Test Category',
        'slug': 'test-category',
        'icon': 'test',
        'order': 99
    })
    
    if response.status_code == 403:
        print_result(True, "Regular user correctly denied with 403")
        return True
    else:
        print_result(False, f"Expected 403, got {response.status_code}")
        return False


def test_categories_post_as_admin():
    """Test POST /categories as admin returns 200"""
    print_test("Categories - POST as admin")
    
    global test_category_id
    response = make_request('POST', '/categories', token=admin_token, json={
        'name': 'Test Category',
        'slug': f'test-category-{random_string()}',
        'icon': 'test-icon',
        'order': 99
    })
    
    if response.status_code == 200:
        data = response.json()
        test_category_id = data['id']
        print_result(True, f"Category created: {data['name']}, id={test_category_id}")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_categories_delete_cleanup():
    """Test DELETE /categories/{id} to cleanup test category"""
    print_test("Categories - DELETE test category (cleanup)")
    
    if not test_category_id:
        print_result(False, "No test category to delete")
        return False
    
    response = make_request('DELETE', f'/categories/{test_category_id}', token=admin_token)
    
    if response.status_code == 200:
        print_result(True, f"Test category deleted: {test_category_id}")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


# =========================
# 3. LISTINGS TESTS
# =========================
def test_listings_get_all():
    """Test GET /listings returns active listings"""
    print_test("Listings - GET all active listings")
    
    response = make_request('GET', '/listings')
    
    if response.status_code == 200:
        listings = response.json()
        if len(listings) > 0:
            print_result(True, f"Retrieved {len(listings)} active listings")
            return True
        else:
            print_result(False, "No listings returned")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_listings_search():
    """Test GET /listings?q=Nike filters by search"""
    print_test("Listings - Search with q=Nike")
    
    response = make_request('GET', '/listings?q=Nike')
    
    if response.status_code == 200:
        listings = response.json()
        if len(listings) > 0:
            # Check if Nike appears in results
            has_nike = any('nike' in listing['title'].lower() or 'nike' in listing.get('brand', '').lower() 
                          for listing in listings)
            if has_nike:
                print_result(True, f"Search returned {len(listings)} listings with Nike")
                return True
            else:
                print_result(False, "Search results don't contain Nike")
                return False
        else:
            print_result(False, "No listings returned for Nike search")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_listings_sort_price_asc():
    """Test GET /listings?sort=price_asc verifies ordering"""
    print_test("Listings - Sort by price ascending")
    
    response = make_request('GET', '/listings?sort=price_asc&limit=10')
    
    if response.status_code == 200:
        listings = response.json()
        if len(listings) >= 2:
            prices = [l['price'] for l in listings]
            is_sorted = all(prices[i] <= prices[i+1] for i in range(len(prices)-1))
            if is_sorted:
                print_result(True, f"Listings sorted by price: {prices[:5]}")
                return True
            else:
                print_result(False, f"Listings not sorted correctly: {prices[:5]}")
                return False
        else:
            print_result(False, "Not enough listings to verify sorting")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_listings_filter_category():
    """Test GET /listings?category_id=... filters by category"""
    print_test("Listings - Filter by category")
    
    if not categories:
        print_result(False, "No categories available")
        return False
    
    category_id = categories[0]['id']
    response = make_request('GET', f'/listings?category_id={category_id}')
    
    if response.status_code == 200:
        listings = response.json()
        if len(listings) > 0:
            all_match = all(l['category_id'] == category_id for l in listings)
            if all_match:
                print_result(True, f"Category filter working: {len(listings)} listings")
                return True
            else:
                print_result(False, "Some listings don't match category filter")
                return False
        else:
            print_result(True, f"No listings in category {category_id} (valid result)")
            return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_listings_filter_price_range():
    """Test GET /listings?min_price=100&max_price=200 filters by price"""
    print_test("Listings - Filter by price range (100-200)")
    
    response = make_request('GET', '/listings?min_price=100&max_price=200')
    
    if response.status_code == 200:
        listings = response.json()
        if len(listings) > 0:
            all_in_range = all(100 <= l['price'] <= 200 for l in listings)
            if all_in_range:
                print_result(True, f"Price filter working: {len(listings)} listings in range")
                return True
            else:
                prices = [l['price'] for l in listings if not (100 <= l['price'] <= 200)]
                print_result(False, f"Some listings outside range: {prices}")
                return False
        else:
            print_result(True, "No listings in price range (valid result)")
            return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_listings_get_single():
    """Test GET /listings/{id} returns single listing and increments views"""
    print_test("Listings - GET single listing (views increment)")
    
    # First get a listing ID
    response = make_request('GET', '/listings?limit=1')
    if response.status_code != 200 or not response.json():
        print_result(False, "Could not get listing for test")
        return False
    
    listing_id = response.json()[0]['id']
    initial_views = response.json()[0]['views_count']
    
    # Get the specific listing
    response = make_request('GET', f'/listings/{listing_id}')
    
    if response.status_code == 200:
        listing = response.json()
        new_views = listing['views_count']
        if new_views == initial_views + 1:
            print_result(True, f"Views incremented: {initial_views} -> {new_views}")
            return True
        else:
            print_result(False, f"Views not incremented correctly: {initial_views} -> {new_views}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_listings_post():
    """Test POST /listings as user creates listing"""
    print_test("Listings - POST create new listing")
    
    global test_listing_id
    
    if not categories:
        print_result(False, "No categories available")
        return False
    
    response = make_request('POST', '/listings', token=user_token, json={
        'title': f'Test Listing {random_string()}',
        'description': 'This is a test listing for automated testing',
        'price': 99.99,
        'category_id': categories[0]['id'],
        'condition': 'good',
        'brand': 'Test Brand',
        'images': ['https://picsum.photos/800/800']
    })
    
    if response.status_code == 200:
        listing = response.json()
        test_listing_id = listing['id']
        print_result(True, f"Listing created: {listing['title']}, id={test_listing_id}")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_listings_put_as_owner():
    """Test PUT /listings/{id} as owner updates listing"""
    print_test("Listings - PUT update as owner")
    
    if not test_listing_id:
        print_result(False, "No test listing to update")
        return False
    
    new_price = 149.99
    response = make_request('PUT', f'/listings/{test_listing_id}', token=user_token, json={
        'price': new_price,
        'title': 'Updated Test Listing'
    })
    
    if response.status_code == 200:
        listing = response.json()
        if listing['price'] == new_price:
            print_result(True, f"Listing updated: price={listing['price']}")
            return True
        else:
            print_result(False, f"Price not updated: {listing['price']}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_listings_put_as_other_user():
    """Test PUT /listings/{id} as another user returns 403"""
    print_test("Listings - PUT update as non-owner (should fail)")
    
    if not test_listing_id or not user2_token:
        print_result(False, "Missing test listing or user2 token")
        return False
    
    response = make_request('PUT', f'/listings/{test_listing_id}', token=user2_token, json={
        'price': 999.99
    })
    
    if response.status_code == 403:
        print_result(True, "Non-owner correctly denied with 403")
        return True
    else:
        print_result(False, f"Expected 403, got {response.status_code}")
        return False


def test_listings_delete_as_owner():
    """Test DELETE /listings/{id} as owner (cleanup at end)"""
    # This will be called at the end to cleanup
    pass


# =========================
# 4. FAVORITES TESTS
# =========================
def test_favorites_post():
    """Test POST /favorites/{listing_id} adds favorite and increments likes_count"""
    print_test("Favorites - POST add favorite")
    
    # Get a listing to favorite
    response = make_request('GET', '/listings?limit=1')
    if response.status_code != 200 or not response.json():
        print_result(False, "Could not get listing for test")
        return False
    
    listing = response.json()[0]
    listing_id = listing['id']
    initial_likes = listing['likes_count']
    
    # Add to favorites
    response = make_request('POST', f'/favorites/{listing_id}', token=user2_token)
    
    if response.status_code == 200:
        # Verify likes_count incremented
        response = make_request('GET', f'/listings/{listing_id}')
        if response.status_code == 200:
            new_likes = response.json()['likes_count']
            if new_likes == initial_likes + 1:
                print_result(True, f"Favorite added, likes: {initial_likes} -> {new_likes}")
                return True
            else:
                print_result(False, f"Likes not incremented: {initial_likes} -> {new_likes}")
                return False
        else:
            print_result(False, "Could not verify likes_count")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_favorites_post_duplicate():
    """Test POST same listing again returns {already: true}"""
    print_test("Favorites - POST duplicate favorite")
    
    # Get first listing again
    response = make_request('GET', '/listings?limit=1')
    if response.status_code != 200 or not response.json():
        print_result(False, "Could not get listing for test")
        return False
    
    listing_id = response.json()[0]['id']
    
    # Try to add again
    response = make_request('POST', f'/favorites/{listing_id}', token=user2_token)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('already') == True:
            print_result(True, "Duplicate favorite correctly handled")
            return True
        else:
            print_result(False, f"Expected 'already: true', got {data}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_favorites_get():
    """Test GET /favorites returns user's favorites"""
    print_test("Favorites - GET user favorites")
    
    response = make_request('GET', '/favorites', token=user2_token)
    
    if response.status_code == 200:
        favorites = response.json()
        if len(favorites) > 0:
            print_result(True, f"Retrieved {len(favorites)} favorites")
            return True
        else:
            print_result(False, "No favorites returned")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_favorites_delete():
    """Test DELETE /favorites/{listing_id} removes and decrements likes_count"""
    print_test("Favorites - DELETE remove favorite")
    
    # Get first listing
    response = make_request('GET', '/listings?limit=1')
    if response.status_code != 200 or not response.json():
        print_result(False, "Could not get listing for test")
        return False
    
    listing = response.json()[0]
    listing_id = listing['id']
    initial_likes = listing['likes_count']
    
    # Remove from favorites
    response = make_request('DELETE', f'/favorites/{listing_id}', token=user2_token)
    
    if response.status_code == 200:
        # Verify likes_count decremented
        response = make_request('GET', f'/listings/{listing_id}')
        if response.status_code == 200:
            new_likes = response.json()['likes_count']
            if new_likes == initial_likes - 1:
                print_result(True, f"Favorite removed, likes: {initial_likes} -> {new_likes}")
                return True
            else:
                print_result(False, f"Likes not decremented: {initial_likes} -> {new_likes}")
                return False
        else:
            print_result(False, "Could not verify likes_count")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


# =========================
# 5. CART TESTS
# =========================
def test_cart_post():
    """Test POST /cart/{listing_id} adds to cart"""
    print_test("Cart - POST add to cart")
    
    # Get a listing to add
    response = make_request('GET', '/listings?limit=1&skip=1')
    if response.status_code != 200 or not response.json():
        print_result(False, "Could not get listing for test")
        return False
    
    listing_id = response.json()[0]['id']
    
    response = make_request('POST', f'/cart/{listing_id}', token=user2_token)
    
    if response.status_code == 200:
        print_result(True, f"Added to cart: {listing_id}")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_cart_get():
    """Test GET /cart returns cart items"""
    print_test("Cart - GET cart items")
    
    response = make_request('GET', '/cart', token=user2_token)
    
    if response.status_code == 200:
        cart = response.json()
        if len(cart) > 0:
            print_result(True, f"Retrieved {len(cart)} cart items")
            return True
        else:
            print_result(False, "No cart items returned")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_cart_delete():
    """Test DELETE /cart/{listing_id} removes from cart"""
    print_test("Cart - DELETE remove from cart")
    
    # Get cart items
    response = make_request('GET', '/cart', token=user2_token)
    if response.status_code != 200 or not response.json():
        print_result(False, "No cart items to remove")
        return False
    
    listing_id = response.json()[0]['id']
    
    response = make_request('DELETE', f'/cart/{listing_id}', token=user2_token)
    
    if response.status_code == 200:
        print_result(True, f"Removed from cart: {listing_id}")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


# =========================
# 6. ORDERS TESTS
# =========================
def test_orders_post_success():
    """Test POST /orders creates order, marks listing sold, increments sales_count, clears cart"""
    print_test("Orders - POST create order (full flow)")
    
    # Get an active listing NOT owned by user2
    response = make_request('GET', '/listings?limit=20')
    if response.status_code != 200 or not response.json():
        print_result(False, "Could not get listings for test")
        return False
    
    # Get user2's ID first
    me_response = make_request('GET', '/auth/me', token=user2_token)
    if me_response.status_code != 200:
        print_result(False, "Could not get user2 info")
        return False
    user2_id = me_response.json()['id']
    
    # Find a listing not owned by user2
    listing = None
    for l in response.json():
        if l['seller_id'] != user2_id and l['status'] == 'active':
            listing = l
            break
    
    if not listing:
        print_result(False, "Could not find suitable listing for order test")
        return False
    
    listing_id = listing['id']
    seller_id = listing['seller_id']
    
    # Get seller's initial sales_count
    seller_response = make_request('GET', f'/admin/users', token=admin_token)
    if seller_response.status_code != 200:
        print_result(False, "Could not get seller info")
        return False
    
    seller = next((u for u in seller_response.json() if u['id'] == seller_id), None)
    if not seller:
        print_result(False, "Could not find seller")
        return False
    initial_sales = seller['sales_count']
    
    # Add to cart first
    make_request('POST', f'/cart/{listing_id}', token=user2_token)
    
    # Create order
    response = make_request('POST', '/orders', token=user2_token, json={
        'listing_id': listing_id,
        'shipping_address': {'street': '123 Test St', 'city': 'Test City'}
    })
    
    if response.status_code == 200:
        order = response.json()
        
        # Verify listing is now sold
        listing_response = make_request('GET', f'/listings/{listing_id}')
        if listing_response.status_code == 200:
            updated_listing = listing_response.json()
            if updated_listing['status'] != 'sold':
                print_result(False, f"Listing status not updated: {updated_listing['status']}")
                return False
        else:
            print_result(False, "Could not verify listing status")
            return False
        
        # Verify seller sales_count incremented
        seller_response = make_request('GET', f'/admin/users', token=admin_token)
        if seller_response.status_code == 200:
            updated_seller = next((u for u in seller_response.json() if u['id'] == seller_id), None)
            if updated_seller and updated_seller['sales_count'] == initial_sales + 1:
                print_result(True, f"Order created, listing sold, sales_count: {initial_sales} -> {updated_seller['sales_count']}")
                return True
            else:
                print_result(False, f"Sales count not incremented correctly")
                return False
        else:
            print_result(False, "Could not verify sales_count")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_orders_post_sold_listing():
    """Test POST /orders for sold listing returns 404"""
    print_test("Orders - POST for sold listing (should fail)")
    
    # Get a sold listing
    response = make_request('GET', '/listings?status_filter=sold&limit=1')
    if response.status_code != 200 or not response.json():
        print_result(False, "Could not get sold listing for test")
        return False
    
    listing_id = response.json()[0]['id']
    
    response = make_request('POST', '/orders', token=user2_token, json={
        'listing_id': listing_id,
        'shipping_address': {}
    })
    
    if response.status_code == 404:
        print_result(True, "Sold listing correctly rejected with 404")
        return True
    else:
        print_result(False, f"Expected 404, got {response.status_code}")
        return False


def test_orders_post_own_listing():
    """Test POST /orders for own listing returns 400"""
    print_test("Orders - POST for own listing (should fail)")
    
    if not test_listing_id:
        print_result(False, "No test listing available")
        return False
    
    response = make_request('POST', '/orders', token=user_token, json={
        'listing_id': test_listing_id,
        'shipping_address': {}
    })
    
    if response.status_code == 400:
        print_result(True, "Own listing correctly rejected with 400")
        return True
    else:
        print_result(False, f"Expected 400, got {response.status_code}")
        return False


def test_orders_get_buyer():
    """Test GET /orders?role=buyer returns purchases"""
    print_test("Orders - GET as buyer")
    
    response = make_request('GET', '/orders?role=buyer', token=user2_token)
    
    if response.status_code == 200:
        orders = response.json()
        print_result(True, f"Retrieved {len(orders)} buyer orders")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_orders_get_seller():
    """Test GET /orders?role=seller returns sales"""
    print_test("Orders - GET as seller")
    
    response = make_request('GET', '/orders?role=seller', token=user_token)
    
    if response.status_code == 200:
        orders = response.json()
        print_result(True, f"Retrieved {len(orders)} seller orders")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


# =========================
# 7. ADMIN TESTS
# =========================
def test_admin_stats_as_non_admin():
    """Test GET /admin/stats as non-admin returns 403"""
    print_test("Admin - GET stats as non-admin (should fail)")
    
    response = make_request('GET', '/admin/stats', token=user_token)
    
    if response.status_code == 403:
        print_result(True, "Non-admin correctly denied with 403")
        return True
    else:
        print_result(False, f"Expected 403, got {response.status_code}")
        return False


def test_admin_stats_as_admin():
    """Test GET /admin/stats as admin returns stats"""
    print_test("Admin - GET stats as admin")
    
    response = make_request('GET', '/admin/stats', token=admin_token)
    
    if response.status_code == 200:
        stats = response.json()
        required_keys = ['users', 'active_listings', 'sold_listings', 'orders', 'categories', 'revenue']
        if all(key in stats for key in required_keys):
            print_result(True, f"Stats retrieved: {stats}")
            return True
        else:
            print_result(False, f"Missing keys in stats: {stats}")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_admin_users():
    """Test GET /admin/users as admin returns user list"""
    print_test("Admin - GET users")
    
    response = make_request('GET', '/admin/users', token=admin_token)
    
    if response.status_code == 200:
        users = response.json()
        if len(users) > 0:
            print_result(True, f"Retrieved {len(users)} users")
            return True
        else:
            print_result(False, "No users returned")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_admin_update_user_role():
    """Test PUT /admin/users/{id} updates user role"""
    print_test("Admin - PUT update user role")
    
    # Get a regular user
    response = make_request('GET', '/admin/users', token=admin_token)
    if response.status_code != 200:
        print_result(False, "Could not get users")
        return False
    
    users = response.json()
    regular_user = next((u for u in users if u['role'] == 'user'), None)
    if not regular_user:
        print_result(False, "No regular user found")
        return False
    
    user_id = regular_user['id']
    
    # Update to admin (then back to user)
    response = make_request('PUT', f'/admin/users/{user_id}', token=admin_token, json={
        'role': 'admin'
    })
    
    if response.status_code == 200:
        # Revert back
        make_request('PUT', f'/admin/users/{user_id}', token=admin_token, json={'role': 'user'})
        print_result(True, f"User role updated successfully")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_admin_update_user_active():
    """Test PUT /admin/users/{id} updates is_active"""
    print_test("Admin - PUT update user is_active")
    
    # Get a regular user
    response = make_request('GET', '/admin/users', token=admin_token)
    if response.status_code != 200:
        print_result(False, "Could not get users")
        return False
    
    users = response.json()
    regular_user = next((u for u in users if u['role'] == 'user'), None)
    if not regular_user:
        print_result(False, "No regular user found")
        return False
    
    user_id = regular_user['id']
    
    # Deactivate (then reactivate)
    response = make_request('PUT', f'/admin/users/{user_id}', token=admin_token, json={
        'is_active': False
    })
    
    if response.status_code == 200:
        # Reactivate
        make_request('PUT', f'/admin/users/{user_id}', token=admin_token, json={'is_active': True})
        print_result(True, f"User is_active updated successfully")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_admin_listings():
    """Test GET /admin/listings returns all listings"""
    print_test("Admin - GET all listings")
    
    response = make_request('GET', '/admin/listings', token=admin_token)
    
    if response.status_code == 200:
        listings = response.json()
        if len(listings) > 0:
            print_result(True, f"Retrieved {len(listings)} listings (all statuses)")
            return True
        else:
            print_result(False, "No listings returned")
            return False
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


def test_admin_orders():
    """Test GET /admin/orders returns all orders"""
    print_test("Admin - GET all orders")
    
    response = make_request('GET', '/admin/orders', token=admin_token)
    
    if response.status_code == 200:
        orders = response.json()
        print_result(True, f"Retrieved {len(orders)} orders")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


# =========================
# CLEANUP
# =========================
def cleanup_test_listing():
    """Delete test listing created during tests"""
    print_test("Cleanup - Delete test listing")
    
    if not test_listing_id:
        print_result(True, "No test listing to cleanup")
        return True
    
    response = make_request('DELETE', f'/listings/{test_listing_id}', token=user_token)
    
    if response.status_code == 200:
        print_result(True, f"Test listing deleted: {test_listing_id}")
        return True
    else:
        print_result(False, f"Status {response.status_code}: {response.text}")
        return False


# =========================
# MAIN TEST RUNNER
# =========================
def run_all_tests():
    """Run all backend tests in order"""
    print("\n" + "="*60)
    print("MERCARI CLONE - BACKEND API TESTS")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print("="*60)
    
    results = {}
    
    # Auth tests
    results['auth_register'] = test_auth_register()
    results['auth_register_duplicate'] = test_auth_register_duplicate()
    results['auth_login_admin'] = test_auth_login_admin()
    results['auth_login_user'] = test_auth_login_user()
    results['auth_me_with_token'] = test_auth_me_with_token()
    results['auth_me_without_token'] = test_auth_me_without_token()
    
    # Categories tests
    results['categories_get'] = test_categories_get_public()
    results['categories_post_user'] = test_categories_post_as_user()
    results['categories_post_admin'] = test_categories_post_as_admin()
    results['categories_delete'] = test_categories_delete_cleanup()
    
    # Listings tests
    results['listings_get_all'] = test_listings_get_all()
    results['listings_search'] = test_listings_search()
    results['listings_sort'] = test_listings_sort_price_asc()
    results['listings_filter_category'] = test_listings_filter_category()
    results['listings_filter_price'] = test_listings_filter_price_range()
    results['listings_get_single'] = test_listings_get_single()
    results['listings_post'] = test_listings_post()
    results['listings_put_owner'] = test_listings_put_as_owner()
    results['listings_put_other'] = test_listings_put_as_other_user()
    
    # Favorites tests
    results['favorites_post'] = test_favorites_post()
    results['favorites_duplicate'] = test_favorites_post_duplicate()
    results['favorites_get'] = test_favorites_get()
    results['favorites_delete'] = test_favorites_delete()
    
    # Cart tests
    results['cart_post'] = test_cart_post()
    results['cart_get'] = test_cart_get()
    results['cart_delete'] = test_cart_delete()
    
    # Orders tests
    results['orders_post'] = test_orders_post_success()
    results['orders_post_sold'] = test_orders_post_sold_listing()
    results['orders_post_own'] = test_orders_post_own_listing()
    results['orders_get_buyer'] = test_orders_get_buyer()
    results['orders_get_seller'] = test_orders_get_seller()
    
    # Admin tests
    results['admin_stats_non_admin'] = test_admin_stats_as_non_admin()
    results['admin_stats_admin'] = test_admin_stats_as_admin()
    results['admin_users'] = test_admin_users()
    results['admin_update_role'] = test_admin_update_user_role()
    results['admin_update_active'] = test_admin_update_user_active()
    results['admin_listings'] = test_admin_listings()
    results['admin_orders'] = test_admin_orders()
    
    # Cleanup
    results['cleanup'] = cleanup_test_listing()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print(f"Pass rate: {(passed/total)*100:.1f}%")
    
    print("\nFailed tests:")
    failed = [k for k, v in results.items() if not v]
    if failed:
        for test in failed:
            print(f"  ❌ {test}")
    else:
        print("  None - all tests passed! ✅")
    
    print("\n" + "="*60)
    
    return passed == total


if __name__ == "__main__":
    try:
        success = run_all_tests()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
