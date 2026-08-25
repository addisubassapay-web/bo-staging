import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


BASE_URL = "https://marketplace-dropship.preview.emergentagent.com"
OUT_PATH = Path("/app/test_reports/iteration_24_runtime_results.json")


async def wait_for_search_loaded(page):
    await page.wait_for_selector('[data-testid="search-page"]', timeout=20000)
    await page.wait_for_selector('[data-testid="results-summary"]', timeout=20000)
    await page.wait_for_function(
        """() => {
            const el = document.querySelector('[data-testid="results-summary"]');
            return el && !/Loading/.test(el.textContent || '');
        }""",
        timeout=20000,
    )


async def wait_for_page_param(page, expected):
    await page.wait_for_function(
        """expected => {
            const value = new URL(window.location.href).searchParams.get('page') || '1';
            return value === String(expected);
        }""",
        arg=expected,
        timeout=10000,
    )
    await wait_for_search_loaded(page)


async def summary_first_index(page):
    text = (await page.locator('[data-testid="results-summary"]').inner_text()).strip()
    match = re.search(r"Showing\s+([\d,]+)", text)
    first = int(match.group(1).replace(",", "")) if match else None
    return text, first


async def test_desktop_pagination(browser, failures, evidence):
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    await context.add_init_script("sessionStorage.setItem('mercari_splash_seen','1')")
    page = await context.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: console_errors.append(str(exc)))

    try:
        await page.goto(f"{BASE_URL}/search?size=24", wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except PlaywrightTimeoutError:
            pass
        await wait_for_search_loaded(page)
        await page.wait_for_selector('[data-testid="pagination"]', timeout=20000)

        initial_summary, initial_first = await summary_first_index(page)
        evidence["desktop_initial_summary"] = initial_summary

        page3 = page.locator('[data-testid="page-3"]')
        if await page3.count() == 0:
            failures.append("Desktop pagination: page-3 button was not present on /search?size=24.")
            return

        await page3.click()
        await wait_for_page_param(page, 3)
        summary, first = await summary_first_index(page)
        evidence["after_click_page_3"] = {"url": page.url, "summary": summary, "first_index": first}
        if first != 49:
            failures.append(f"Desktop pagination: clicking page 3 did not show first item 49; got {summary!r}.")

        await page.locator('[data-testid="page-next"]').click()
        await wait_for_page_param(page, 4)
        summary, first = await summary_first_index(page)
        evidence["after_next_from_page_3"] = {"url": page.url, "summary": summary, "first_index": first}
        if first != 73:
            failures.append(f"Desktop pagination: Next from page 3 did not show first item 73; got {summary!r}.")

        jump = page.locator('[data-testid="page-jump-input"]')
        if await jump.count() == 0:
            failures.append("Desktop pagination: jump-to-page input was not present.")
        else:
            await jump.fill("2")
            await page.locator('[data-testid="page-jump-btn"]').click()
            await wait_for_page_param(page, 2)
            summary, first = await summary_first_index(page)
            evidence["after_jump_to_page_2"] = {"url": page.url, "summary": summary, "first_index": first}
            if first != 25:
                failures.append(f"Desktop pagination: jump to page 2 did not show first item 25; got {summary!r}.")

        buttons = page.locator('aside [data-testid^="filter-category-"]')
        count = await buttons.count()
        if count <= 1:
            failures.append("Filter reset: no non-All category filter was available to click.")
        else:
            await buttons.nth(1).click()

        if not any("Filter reset" in f for f in failures):
            await page.wait_for_function(
                """() => {
                    const u = new URL(window.location.href);
                    return !!u.searchParams.get('category') && ((u.searchParams.get('page') || '1') === '1');
                }""",
                timeout=12000,
            )
            await wait_for_search_loaded(page)
            summary, first = await summary_first_index(page)
            evidence["after_filter_reset"] = {"url": page.url, "summary": summary, "first_index": first}
            if first not in (1, None):
                failures.append(f"Filter reset: applying a category did not reset results to page 1; got {summary!r}.")

        evidence["desktop_console_errors"] = console_errors[:10]
    finally:
        await context.close()


async def test_mobile_overflow(browser, failures, evidence):
    viewports = [
        {"width": 320, "height": 568},
        {"width": 375, "height": 812},
        {"width": 390, "height": 844},
    ]
    routes = ["/", "/search"]
    evidence["mobile_overflow"] = []

    for viewport in viewports:
        for route in routes:
            context = await browser.new_context(viewport=viewport, is_mobile=True)
            await context.add_init_script("sessionStorage.setItem('mercari_splash_seen','1')")
            page = await context.new_page()
            try:
                await page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    pass
                if route == "/":
                    await page.wait_for_selector('[data-testid="hero-carousel"]', timeout=20000)
                else:
                    await wait_for_search_loaded(page)
                await page.wait_for_timeout(800)
                metrics = await page.evaluate(
                    """() => {
                        const w = window.innerWidth;
                        const offenders = Array.from(document.querySelectorAll('body *')).map((el) => {
                            const r = el.getBoundingClientRect();
                            return {
                                tag: el.tagName.toLowerCase(),
                                testid: el.getAttribute('data-testid') || '',
                                cls: String(el.className || '').slice(0, 120),
                                left: Math.round(r.left),
                                right: Math.round(r.right),
                                width: Math.round(r.width),
                                scrollWidth: el.scrollWidth || 0,
                            };
                        }).filter((x) => x.right > w + 1 || x.left < -1).slice(0, 8);
                        return {
                            route: window.location.pathname,
                            innerWidth: w,
                            docScrollWidth: document.documentElement.scrollWidth,
                            bodyScrollWidth: document.body.scrollWidth,
                            clientWidth: document.documentElement.clientWidth,
                            bodyClientWidth: document.body.clientWidth,
                            offenders,
                        };
                    }"""
                )
                record = {"viewport": viewport, **metrics}
                evidence["mobile_overflow"].append(record)
                allowed = metrics["innerWidth"] + 1
                if metrics["docScrollWidth"] > allowed or metrics["bodyScrollWidth"] > allowed:
                    failures.append(
                        f"Mobile overflow {route} at {viewport['width']}x{viewport['height']}: "
                        f"doc={metrics['docScrollWidth']}, body={metrics['bodyScrollWidth']}, allowed={allowed}, offenders={metrics['offenders']}"
                    )
            finally:
                await context.close()


async def main():
    failures = []
    evidence = {
        "base_url": BASE_URL,
        "skill_lookup": "No relevant testing skill found.",
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            await test_desktop_pagination(browser, failures, evidence)
            await test_mobile_overflow(browser, failures, evidence)
        finally:
            await browser.close()

    result = {"passed": not failures, "failures": failures, "evidence": evidence}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())