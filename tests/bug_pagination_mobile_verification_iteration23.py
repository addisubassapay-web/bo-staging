"""
Focused bug verification for iteration 23.

Bug under test:
1) /search pagination controls must navigate correctly.
2) Mobile layouts must not horizontally overflow at 390, 375, or 320px.

Run with: python /app/tests/bug_pagination_mobile_verification_iteration23.py
Requires Playwright browsers in the test environment.
"""

import asyncio
from playwright.async_api import async_playwright, expect


BASE_URL = "https://mercari-clone-1.preview.emergentagent.com"
ROUTES = ["/search", "/", "/cart", "/marketplace/stores"]
VIEWPORTS = [(390, 844), (375, 812), (320, 568)]


async def go(page, path: str):
    await page.goto(BASE_URL + path, wait_until="domcontentloaded")
    await page.evaluate("sessionStorage.setItem('mercari_splash_seen','1')")
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(1200)


async def verify_pagination(page):
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await go(page, "/search")
    await page.wait_for_selector('[data-testid="pagination"]', timeout=15000)

    await page.locator('[data-testid="page-3"]').click()
    await page.wait_for_function("() => new URL(location.href).searchParams.get('page') === '3'")
    await expect(page.locator('[data-testid="page-3"][aria-current="page"]')).to_have_count(1)

    await page.locator('[data-testid="page-next"]').click()
    await page.wait_for_function("() => new URL(location.href).searchParams.get('page') === '4'")
    await expect(page.locator('[data-testid="page-4"][aria-current="page"]')).to_have_count(1)

    await page.locator('[data-testid="page-jump-input"]').fill("7")
    await page.locator('[data-testid="page-jump-btn"]').click()
    await page.wait_for_function("() => new URL(location.href).searchParams.get('page') === '7'")
    await expect(page.locator('[data-testid="page-7"][aria-current="page"]')).to_have_count(1)

    await page.get_by_role("button", name="New", exact=True).first.click()
    await page.wait_for_function(
        """() => {
            const u = new URL(location.href);
            return u.searchParams.get('condition') === 'new' &&
              (u.searchParams.get('page') === '1' || u.searchParams.get('page') === null);
        }"""
    )


async def measure_overflow(page, path: str, width: int, height: int):
    await page.set_viewport_size({"width": width, "height": height})
    await go(page, path)
    return await page.evaluate(
        """() => ({
            route: location.pathname,
            innerWidth: window.innerWidth,
            docScrollWidth: document.documentElement.scrollWidth,
            bodyScrollWidth: document.body.scrollWidth
        })"""
    )


async def verify_newsletter_stacks(page):
    await page.set_viewport_size({"width": 390, "height": 844})
    await go(page, "/search")
    await page.locator('[data-testid="newsletter-form"]').scroll_into_view_if_needed()
    data = await page.evaluate(
        """() => {
            const form = document.querySelector('[data-testid="newsletter-form"]');
            const input = document.querySelector('[data-testid="newsletter-email-input"]');
            const btn = document.querySelector('[data-testid="newsletter-submit-btn"]');
            const fr = form.getBoundingClientRect();
            const ir = input.getBoundingClientRect();
            const br = btn.getBoundingClientRect();
            return {
              flexDirection: getComputedStyle(form).flexDirection,
              innerWidth: window.innerWidth,
              formRight: fr.right,
              inputBottom: ir.bottom,
              buttonTop: br.top,
              buttonRight: br.right
            };
        }"""
    )
    assert data["flexDirection"] == "column"
    assert data["buttonTop"] >= data["inputBottom"] - 1
    assert data["formRight"] <= data["innerWidth"] + 1
    assert data["buttonRight"] <= data["innerWidth"] + 1


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.add_init_script("sessionStorage.setItem('mercari_splash_seen','1');")

        await verify_pagination(page)
        await verify_newsletter_stacks(page)

        failures = []
        for width, height in VIEWPORTS:
            for route in ROUTES:
                data = await measure_overflow(page, route, width, height)
                print(data)
                if (
                    data["docScrollWidth"] > data["innerWidth"] + 1
                    or data["bodyScrollWidth"] > data["innerWidth"] + 1
                ):
                    failures.append(data)

        await browser.close()
        if failures:
            raise AssertionError(f"Horizontal overflow failures: {failures}")


if __name__ == "__main__":
    asyncio.run(main())