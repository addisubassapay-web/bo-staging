"""Focused Playwright verification for Search pagination bug.

This file records the exact browser automation used by the testing agent.
It is not part of the product code.
"""

BASE_URL = "https://seller-health-portal.preview.emergentagent.com/search"


async def verify_search_pagination(page):
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.add_init_script("sessionStorage.setItem('mercari_splash_seen','1')")
    await page.goto(BASE_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="pagination"]', timeout=30000)

    # Fresh visit pagination shape.
    for test_id in ["page-1", "page-2", "page-last", "page-jump-input", "page-jump-btn"]:
        assert await page.locator(f'[data-testid="{test_id}"]').count() > 0, f"missing {test_id}"

    # Primary regression: page 3 must persist and update item range.
    await page.locator('[data-testid="page-3"]').click()
    await page.wait_for_url(lambda url: "page=3" in url, timeout=10000)
    await page.wait_for_function("""() => document.querySelector('[data-testid="results-summary"]')?.textContent?.includes('49')""", timeout=10000)
    await page.wait_for_timeout(1000)
    assert "page=3" in page.url

    # Navigation controls.
    await page.locator('[data-testid="page-next"]').click()
    await page.wait_for_url(lambda url: "page=4" in url, timeout=10000)
    await page.locator('[data-testid="page-prev"]').click()
    await page.wait_for_url(lambda url: "page=3" in url, timeout=10000)
    await page.locator('[data-testid="page-first"]').click()
    await page.wait_for_function("""() => !new URL(location.href).searchParams.has('page')""", timeout=10000)
    await page.locator('[data-testid="page-last"]').click()
    await page.wait_for_function("""() => Number(new URL(location.href).searchParams.get('page') || '1') > 7""", timeout=10000)
    await page.wait_for_function("""() => {
      const txt = document.querySelector('[data-testid="results-summary"]')?.textContent || '';
      return !txt.includes('Loading') && /Showing\s+2,689/.test(txt);
    }""", timeout=15000)

    # Jump to a high page.
    await page.locator('[data-testid="page-jump-input"]').fill("57")
    await page.locator('[data-testid="page-jump-btn"]').click()
    await page.wait_for_url(lambda url: "page=57" in url, timeout=10000)
    await page.wait_for_function("""() => document.querySelector('[data-testid="results-summary"]')?.textContent?.includes('1,345')""", timeout=10000)

    # Filter/sort changes must still reset to page 1.
    await page.locator('[data-testid="sort-select"]').click()
    await page.wait_for_timeout(200)
    await page.get_by_text("Price: low to high", exact=True).click(force=True)
    await page.wait_for_function("""() => Number(new URL(location.href).searchParams.get('page') || '1') === 1 && document.querySelector('[data-testid="results-summary"]')?.textContent?.includes('1–24')""", timeout=10000)

    # Mobile layout/touch targets.
    await page.set_viewport_size({"width": 390, "height": 844})
    await page.goto(BASE_URL, wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="pagination"]', timeout=30000)
    metrics = await page.evaluate("""() => {
      const nav = document.querySelector('[data-testid="pagination"]');
      const form = document.querySelector('[data-testid="page-jump-form"]');
      const input = document.querySelector('[data-testid="page-jump-input"]');
      const buttons = Array.from(nav.querySelectorAll('button'));
      return {
        noOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        minButtonHeight: Math.min(...buttons.map(b => b.getBoundingClientRect().height)),
        formOwnRow: form.getBoundingClientRect().width >= nav.getBoundingClientRect().width * 0.95,
        inputType: input.getAttribute('type'),
        inputMode: input.getAttribute('inputmode') || input.getAttribute('inputMode')
      };
    }""")
    assert metrics["noOverflow"]
    assert metrics["minButtonHeight"] >= 40
    assert metrics["formOwnRow"]
    assert metrics["inputType"] == "number"
    assert metrics["inputMode"] == "numeric"