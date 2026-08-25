"""
Focused verification for iteration 25: cart + checkout mobile strict-fit audit.

This file mirrors the Playwright body executed via the browser automation tool.
It logs in as the demo buyer, adds one live listing to the cart, and measures
/cart plus /checkout/<listing_id> at 320x568, 375x812, and 390x844.
"""

async def run(page):
    base = "https://marketplace-dropship.preview.emergentagent.com"
    widths = [
        {"width": 320, "height": 568},
        {"width": 375, "height": 812},
        {"width": 390, "height": 844},
    ]

    async def measure(label, path, viewport):
        await page.set_viewport_size(viewport)
        await page.goto(base + path, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        if label == "cart":
            await page.locator('[data-testid="cart-page"]').wait_for(timeout=15000)
            await page.locator('[data-testid^="cart-item-"]').first.wait_for(timeout=15000)
        else:
            await page.locator('[data-testid="checkout-page"]').wait_for(timeout=15000)
            await page.locator('[data-testid="sticky-checkout-bar"]').wait_for(timeout=15000)

        await page.wait_for_timeout(500)
        return await page.evaluate("""(label) => {
            const vw = window.innerWidth;
            const visible = (el) => {
              const s = getComputedStyle(el);
              const r = el.getBoundingClientRect();
              return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
            };
            const bounds = (el) => {
              if (!el) return null;
              const r = el.getBoundingClientRect();
              return {
                tag: el.tagName,
                testid: el.dataset?.testid || '',
                className: String(el.className || '').slice(0, 160),
                text: String(el.innerText || el.value || '').trim().slice(0, 120),
                left: Math.round(r.left * 100) / 100,
                right: Math.round(r.right * 100) / 100,
                width: Math.round(r.width * 100) / 100,
                visible: visible(el),
                fits: r.left >= -1 && r.right <= vw + 1
              };
            };
            const selectors = label === 'cart'
              ? ['[data-testid^="cart-seller-link-"]', '[data-testid^="cart-item-"]', '[data-testid="order-summary"]', '[data-testid="checkout-btn"]']
              : ['[data-testid="checkout-page"] input', '[data-testid="sticky-checkout-bar"]', '[data-testid="place-order-mobile-btn"]', '[data-testid="coupon-input"]'];
            const keyElements = selectors.flatMap((sel) => Array.from(document.querySelectorAll(sel)).map(bounds));
            const overflowingElements = Array.from(document.querySelectorAll('body *')).filter(visible).map(bounds)
              .filter((b) => b && (b.left < -1 || b.right > vw + 1))
              .sort((a, b) => (b.right - vw) - (a.right - vw))
              .slice(0, 12);
            const sticky = document.querySelector('[data-testid="sticky-checkout-bar"]');
            return {
              label,
              url: location.href,
              innerWidth: vw,
              documentElementScrollWidth: document.documentElement.scrollWidth,
              bodyScrollWidth: document.body.scrollWidth,
              passStrictScrollWidth: document.documentElement.scrollWidth <= vw + 1 && document.body.scrollWidth <= vw + 1,
              keyElements,
              keyElementsFit: keyElements.every((b) => !b || !b.visible || b.fits),
              overflowingElements,
              stickyVisible: sticky ? visible(sticky) : null,
              stickyBounds: sticky ? bounds(sticky) : null,
              elementsAtRightEdge: document.elementsFromPoint(vw - 1, Math.min(200, window.innerHeight - 1)).slice(0, 5).map((el) => ({
                tag: el.tagName,
                testid: el.dataset?.testid || '',
                className: String(el.className || '').slice(0, 120),
                text: String(el.innerText || '').trim().slice(0, 80)
              }))
            };
        }""", label)

    try:
        print("Starting cart + checkout mobile strict-fit verification")
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(base, wait_until="domcontentloaded")
        await page.evaluate("sessionStorage.setItem('mercari_splash_seen','1')")

        setup = await page.evaluate("""async () => {
            const api = location.origin + '/api';
            const loginRes = await fetch(api + '/auth/login', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({email: 'sophia_style@demo.local', password: 'demo1234'})
            });
            if (!loginRes.ok) throw new Error('login failed ' + loginRes.status + ': ' + await loginRes.text());
            const login = await loginRes.json();
            localStorage.setItem('mercari_token', login.token);
            localStorage.setItem('mercari_username', login.user?.username || '');
            const listingsRes = await fetch(api + '/listings?limit=50');
            if (!listingsRes.ok) throw new Error('listings failed ' + listingsRes.status + ': ' + await listingsRes.text());
            const listingData = await listingsRes.json();
            const listings = Array.isArray(listingData) ? listingData : (listingData.items || listingData.results || []);
            const candidates = listings.filter((l) => l && l.id && l.seller_id !== login.user?.id && (l.status || 'active') !== 'sold');
            const fallback = listings.filter((l) => l && l.id);
            let chosen = null;
            let addStatus = null;
            let addText = '';
            for (const listing of [...candidates, ...fallback]) {
              const res = await fetch(api + '/cart/' + listing.id, { method: 'POST', headers: { Authorization: 'Bearer ' + login.token } });
              addStatus = res.status;
              addText = await res.text();
              if (res.ok || addText.toLowerCase().includes('already')) { chosen = listing; break; }
            }
            if (!chosen) throw new Error('could not add any listing to cart; last status=' + addStatus + ' body=' + addText);
            return { buyer: login.user?.email, buyer_id: login.user?.id, listing_id: chosen.id, listing_title: chosen.title, addStatus, addText: addText.slice(0, 200) };
        }""")
        print(f"Setup complete: {setup}")

        results = []
        for viewport in widths:
            cart_result = await measure("cart", "/cart", viewport)
            print(f"Measured cart {viewport['width']}x{viewport['height']}: html={cart_result['documentElementScrollWidth']} body={cart_result['bodyScrollWidth']} inner={cart_result['innerWidth']} keyFit={cart_result['keyElementsFit']}")
            results.append(cart_result)
            checkout_result = await measure("checkout", f"/checkout/{setup['listing_id']}", viewport)
            print(f"Measured checkout {viewport['width']}x{viewport['height']}: html={checkout_result['documentElementScrollWidth']} body={checkout_result['bodyScrollWidth']} inner={checkout_result['innerWidth']} keyFit={checkout_result['keyElementsFit']} stickyVisible={checkout_result['stickyVisible']}")
            results.append(checkout_result)

        failures = [r for r in results if not r['passStrictScrollWidth'] or not r['keyElementsFit'] or (r['label'] == 'checkout' and not r['stickyVisible'])]
        if failures:
            print(f"TEST FAILED: {failures}")
            raise AssertionError(f"Mobile strict-fit failures: {len(failures)}")
        print(f"TEST PASSED: all {len(results)} cart/checkout mobile strict-fit checks passed")
    except Exception as exc:
        print(f"TEST ERROR: {exc}")
        raise