import asyncio
import re

try:
    await page.set_viewport_size({"width": 1920, "height": 1080})
    print("PASS - viewport configured")

    page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
    await page.goto("https://apify-catalog.preview.emergentagent.com", wait_until="domcontentloaded")
    await page.evaluate("localStorage.removeItem('merchari-global_token'); localStorage.removeItem('merchari-global_username');")
    print("PASS - cleared existing auth state")

    await page.goto("https://apify-catalog.preview.emergentagent.com/login", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="login-email"]', timeout=30000)
    await page.fill('[data-testid="login-email"]', "admin@mercari.local")
    await page.fill('[data-testid="login-password"] input, [data-testid="login-password"]', "admin123")
    async with page.expect_response(lambda r: "/api/auth/login" in r.url, timeout=30000) as login_response:
        await page.locator('[data-testid="login-password"]').press("Enter")
    resp = await login_response.value
    print(f"PASS - submitted admin login (HTTP {resp.status})")
    await page.wait_for_timeout(1500)

    await page.goto("https://apify-catalog.preview.emergentagent.com/admin", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="apify-ticker-rebalance-btn"]', timeout=45000)
    print("PASS - admin dashboard rebalance button visible")

    await page.click('[data-testid="apify-ticker-rebalance-btn"]', force=True)
    print("PASS - clicked rebalance button and accepted confirmation dialog")

    result = page.locator('[data-testid="apify-ticker-rebalance-result"]').first
    await result.wait_for(state="visible", timeout=120000)
    result_text = await result.inner_text()
    print(f"PASS - rebalance result card visible: {result_text}")
    await result.screenshot(path="/app/test_reports/browser_apify_rebalance_idempotency/result_card.jpg", quality=40)
    print("PASS - result card screenshot captured")

    match = re.search(r"(\d+)\s+listings\s+cross-tagged", result_text)
    if match:
        cross_tagged = int(match.group(1))
        if cross_tagged < 5:
            print(f"PASS - frontend result reports small/zero cross-tagging: {cross_tagged}")
        else:
            print(f"FAIL - frontend result reports non-idempotent cross-tagging: {cross_tagged}")
    else:
        print("FAIL - could not parse listings cross-tagged count from result card")

    error_text = await page.evaluate("""() => {
const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
return errorElements.map(el => el.textContent).join(", ");
}""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
except Exception as exc:
    print(f"FAIL - frontend rebalance smoke test error: {exc}")
    error_text = await page.evaluate("""() => {
const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
return errorElements.map(el => el.textContent).join(", ");
}""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
    raise