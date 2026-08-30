"""Playwright steps executed via mcp_browser_automation for iteration 41 UI checks."""

async def run(page):
    await page.set_viewport_size({"width": 1920, "height": 1080})
    base = "https://ocean-marketplace.preview.emergentagent.com"

    # Admin UI: login, verify sidebar, verify old Zyte routes do not render legacy pages.
    await page.goto(f"{base}/login")
    await page.wait_for_timeout(1000)
    await page.get_by_test_id("login-email").fill("admin@mercari.local")
    await page.get_by_test_id("login-password").fill("admin123")
    await page.get_by_test_id("login-submit").click()
    await page.wait_for_timeout(1800)
    await page.goto(f"{base}/admin")
    await page.wait_for_timeout(3000)
    sidebar = page.locator('xpath=//div[contains(@class,"max-w-7xl")]//aside[contains(@class,"space-y-1")]')
    await sidebar.wait_for(state="visible", timeout=10000)
    sidebar_text = await sidebar.inner_text()
    assert "Zyte scraper" not in sidebar_text and "Zyte quotas" not in sidebar_text
    assert "Apify sync" in sidebar_text
    await page.screenshot(path="/app/test_reports/browser_iteration41_final/admin_sidebar.jpg", quality=40, full_page=False)

    for legacy_path in ["/admin/scraper", "/admin/quotas"]:
        await page.goto(f"{base}{legacy_path}")
        await page.wait_for_timeout(1200)
        body_text = await page.locator("body").inner_text()
        assert not any(x in body_text for x in ["Zyte scraper", "Zyte quotas", "Scraper jobs", "Quota usage", "Paginated seed scrape"])

    # Seller sell page import deprecation notice and CTA back to catalog mode.
    await page.evaluate("localStorage.clear()")
    await page.goto(f"{base}/login")
    await page.wait_for_timeout(1000)
    await page.get_by_test_id("login-email").fill("sophia_style@demo.local")
    await page.get_by_test_id("login-password").fill("demo1234")
    await page.get_by_test_id("login-submit").click()
    await page.wait_for_timeout(1800)
    await page.goto(f"{base}/sell")
    await page.wait_for_timeout(3000)
    await page.get_by_test_id("sell-mode-import").click()
    await page.wait_for_timeout(1000)
    notice = page.get_by_test_id("import-deprecated-notice")
    await notice.wait_for(state="visible", timeout=10000)
    notice_text = await notice.inner_text()
    assert "Direct URL imports have moved" in notice_text and "Apify" in notice_text and "Browse the catalog" in notice_text
    body_text = await page.locator("body").inner_text()
    assert not any(x in body_text for x in ["ImportFromUrl", "BulkImportFromUrls", "QuotaWidget", "Scrape URL", "Bulk import URLs", "quota"])
    await page.get_by_test_id("import-deprecated-cta").click()
    await page.wait_for_timeout(1500)
    assert "Resell existing" in await page.locator("body").inner_text()

    # Public home loads product cards.
    await page.evaluate("localStorage.clear()")
    await page.goto(base)
    await page.wait_for_timeout(4000)
    assert await page.locator('[data-testid^="product-card-"]').count() > 0