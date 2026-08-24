#!/usr/bin/env python3
"""Reference Playwright scenario for the retired Stripe PaymentSuccess page.

Executed through the MCP browser automation tool for this verification pass.
The scenario asserts the static retired-payment UI is visible and that the page
does not request /api/payments/status/* for stale Stripe session IDs.
"""

SCRIPT = r'''
try:
    await page.set_viewport_size({"width": 1920, "height": 1080})
    network_urls = []
    console_errors = []
    page.on("request", lambda request: network_urls.append(request.url))
    page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text}") if msg.type in ["error", "warning"] else None)

    await page.goto("https://seller-health-portal.preview.emergentagent.com/payment/success?session_id=cs_test_retired_stripe", wait_until="networkidle")
    await page.wait_for_timeout(1000)

    page_root = page.locator('[data-testid="payment-success-page"]')
    await page_root.wait_for(state="visible", timeout=10000)
    text = await page_root.inner_text()
    assert "Card payments are offline" in text
    assert "Card checkout has been retired" in text
    assert await page.locator('[data-testid="ps-view-orders"]').is_visible()
    assert await page.locator('[data-testid="ps-back-home"]').is_visible()

    status_calls = [u for u in network_urls if "/api/payments/status/" in u]
    status_console = [e for e in console_errors if "/api/payments/status/" in e]
    assert not status_calls, f"Unexpected payment status polling: {status_calls}"
    assert not status_console, f"Unexpected payment-status console noise: {status_console}"

    # Get error messages using specific selectors
    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
    print("PASS payment success retired page visible with no payment-status polling")
except Exception as e:
    print(f"FAIL payment success retired page: {e}")
    raise
'''
