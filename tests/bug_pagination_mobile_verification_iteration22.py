"""
Focused Playwright verification for the reported /search pagination and 390px
mobile horizontal overflow bug. This file records the exact browser steps run by
the testing agent in iteration 22.

Run inside an async Playwright context with an existing `page` object.
"""

LIVE_URL = "https://mercari-clone-1.preview.emergentagent.com/search"


async def run(page):
    async def wait_for_cards(label):
        await page.wait_for_selector('[data-testid^="product-card-"]', timeout=30000)
        await page.wait_for_function(
            """() => {
                const summary = document.querySelector('[data-testid="results-summary"]')?.textContent || '';
                return !summary.includes('Loading') && document.querySelectorAll('[data-testid^="product-card-"]').length > 0;
            }""",
            timeout=30000,
        )
        ids = await page.eval_on_selector_all(
            '[data-testid^="product-card-"]',
            "els => els.map(e => e.getAttribute('data-testid').replace('product-card-', ''))",
        )
        print(f"{label}: {len(ids)} product cards, first={ids[0] if ids else 'none'}")
        return ids

    try:
        await page.set_viewport_size({"width": 1440, "height": 900})
        await page.add_init_script("sessionStorage.setItem('mercari_splash_seen','1')")
        await page.goto(LIVE_URL, wait_until="domcontentloaded")
        ids_page1 = await wait_for_cards("desktop page 1")
        assert len(ids_page1) == 24, f"Expected 24 cards on page 1, got {len(ids_page1)}"

        await page.get_by_test_id("page-3").click()
        await page.wait_for_function(
            """prev => {
                const p = new URL(location.href).searchParams;
                const ids = Array.from(document.querySelectorAll('[data-testid^="product-card-"]')).map(e => e.getAttribute('data-testid')).join(',');
                return p.get('page') === '3' && ids && ids !== prev;
            }""",
            arg=",".join(f"product-card-{x}" for x in ids_page1),
            timeout=30000,
        )
        ids_page3 = await wait_for_cards("desktop page 3")
        assert len(ids_page3) == 24, f"Expected 24 cards on page 3, got {len(ids_page3)}"
        assert ids_page3 != ids_page1, "Page 3 rendered the same product IDs as page 1"

        await page.get_by_test_id("page-next").click()
        await page.wait_for_function("() => new URL(location.href).searchParams.get('page') === '4'", timeout=30000)
        ids_page4 = await wait_for_cards("desktop page 4")
        assert ids_page4 != ids_page3, "Next did not render a different product page"

        await page.get_by_test_id("page-jump-input").fill("57")
        await page.get_by_test_id("page-jump-btn").click()
        await page.wait_for_function("() => new URL(location.href).searchParams.get('page') === '57'", timeout=30000)
        ids_page57 = await wait_for_cards("desktop page 57")
        assert len(ids_page57) == 24, f"Expected 24 cards on page 57, got {len(ids_page57)}"
        assert ids_page57 != ids_page4, "Page jump to 57 did not render a different product page"

        await page.get_by_test_id("sort-select").click()
        await page.wait_for_timeout(200)
        await page.get_by_text("Price: low to high", exact=True).click(force=True)
        await page.wait_for_function(
            """() => {
                const p = new URL(location.href).searchParams;
                return p.get('sort') === 'price_asc' && (!p.get('page') || p.get('page') === '1');
            }""",
            timeout=30000,
        )
        print(f"sort reset URL: {page.url}")

        await page.get_by_test_id("page-jump-input").fill("57")
        await page.get_by_test_id("page-jump-btn").click()
        await page.wait_for_function("() => new URL(location.href).searchParams.get('page') === '57'", timeout=30000)
        category_buttons = page.locator('aside [data-testid^="filter-category-"]')
        assert await category_buttons.count() >= 2, "No sidebar category button available for reset regression"
        clicked_category = await category_buttons.nth(1).get_attribute("data-testid")
        await category_buttons.nth(1).click()
        await page.wait_for_function(
            """() => {
                const p = new URL(location.href).searchParams;
                return !!p.get('category') && (!p.get('page') || p.get('page') === '1');
            }""",
            timeout=30000,
        )
        print(f"category reset via {clicked_category}: {page.url}")

        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(LIVE_URL, wait_until="domcontentloaded")
        await wait_for_cards("mobile page 1")
        metrics = await page.evaluate(
            """() => {
                const vw = window.innerWidth;
                const box = (el) => {
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return {left: r.left, right: r.right, width: r.width, top: r.top, bottom: r.bottom, height: r.height};
                };
                const nav = document.querySelector('[data-testid="pagination"]');
                const form = document.querySelector('[data-testid="page-jump-form"]');
                const first = document.querySelector('[data-testid="page-first"]');
                const catContainer = document.querySelector('[data-testid="cat-pill-all"]')?.parentElement;
                const buttons = Array.from(document.querySelectorAll('[data-testid="pagination"] button')).map((b) => {
                    const r = b.getBoundingClientRect();
                    return {testid: b.getAttribute('data-testid'), height: r.height, width: r.width};
                });
                return {
                    innerWidth: vw,
                    htmlScrollWidth: document.documentElement.scrollWidth,
                    bodyScrollWidth: document.body.scrollWidth,
                    header: box(document.querySelector('header')),
                    searchForm: box(document.querySelector('[data-testid="header-search-form"]')),
                    categoryRibbon: box(catContainer),
                    pagination: box(nav),
                    jumpForm: box(form),
                    firstButton: box(first),
                    buttonRects: buttons,
                    jumpOwnRow: !!(form && first && form.getBoundingClientRect().top >= first.getBoundingClientRect().bottom - 1 && form.getBoundingClientRect().width >= Math.min((nav?.getBoundingClientRect().width || 0) - 2, vw - 2)),
                };
            }"""
        )
        print(f"mobile metrics: {metrics}")
        assert metrics["htmlScrollWidth"] <= metrics["innerWidth"] + 1, metrics
        assert metrics["bodyScrollWidth"] <= metrics["innerWidth"] + 1, metrics
        for name in ["header", "searchForm", "categoryRibbon", "pagination"]:
            rect = metrics[name]
            assert rect, f"Missing mobile {name} rect"
            assert rect["left"] >= -1 and rect["right"] <= metrics["innerWidth"] + 1, f"{name} exceeds viewport: {rect}"
        short_buttons = [b for b in metrics["buttonRects"] if b["height"] < 40]
        assert not short_buttons, f"Pagination touch targets below 40px: {short_buttons}"
        assert metrics["jumpOwnRow"], "Go-to-page form did not wrap to its own row on mobile"

        error_text = await page.evaluate(
            """() => {
                const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
                return errorElements.map(el => el.textContent).join(', ');
            }"""
        )
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")
        print("BUG VERIFICATION PASSED")
    except Exception as exc:
        print(f"BUG VERIFICATION FAILED: {exc}")
        raise