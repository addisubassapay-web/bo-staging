"""MCP Playwright helper for iteration 27 Cart/Checkout mobile-fit verification.

Run through mcp_browser_automation with:
    import importlib.util
    spec = importlib.util.spec_from_file_location('iter27_browser', '/app/tests/bug_cart_checkout_mobile_fit_iteration27_browser.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    await mod.run(page)
"""
import json
from pathlib import Path


async def run(page):
    setup = json.loads(Path('/app/test_reports/iteration_27_runtime_api.json').read_text())
    out = Path('/app/test_reports/iteration_27_runtime_ui.json')
    frontend = setup['frontend_url'].rstrip('/')
    buyer_token = setup['buyer']['token']
    empty_token = setup['empty_buyer']['token']
    listing_id = setup['selected_listings'][0]['id']
    widths = [320, 375, 390]
    results = []

    async def set_token(token):
        await page.goto(frontend, wait_until='domcontentloaded')
        await page.evaluate("""(token) => {
            localStorage.setItem('mercari_token', token);
            localStorage.setItem('mercari_currency', 'USD');
        }""", token)

    async def measure(label, root_selectors, important_selectors, internal_selectors=None):
        internal_selectors = internal_selectors or []
        data = await page.evaluate("""({label, rootSelectors, importantSelectors, internalSelectors}) => {
            const vw = document.documentElement.clientWidth;
            const docSw = document.documentElement.scrollWidth;
            const bodySw = document.body ? document.body.scrollWidth : 0;
            const visible = (el) => {
                const cs = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity) !== 0 && r.width > 0 && r.height > 0;
            };
            const describe = (el, selectorHint) => {
                const r = el.getBoundingClientRect();
                return {
                    selectorHint,
                    tag: el.tagName.toLowerCase(),
                    testid: el.getAttribute('data-testid') || '',
                    text: (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 140),
                    left: Math.round(r.left * 10) / 10,
                    right: Math.round(r.right * 10) / 10,
                    width: Math.round(r.width * 10) / 10,
                    clientWidth: el.clientWidth,
                    scrollWidth: el.scrollWidth,
                    overflowX: getComputedStyle(el).overflowX,
                    className: String(el.className || '').slice(0, 180)
                };
            };
            const important = [];
            importantSelectors.forEach((sel) => document.querySelectorAll(sel).forEach((el) => {
                if (!visible(el)) return;
                const r = el.getBoundingClientRect();
                const offscreen = r.left < -1 || r.right > vw + 1;
                important.push({...describe(el, sel), offscreen});
            }));
            const offscreenDescendants = [];
            rootSelectors.forEach((sel) => document.querySelectorAll(sel).forEach((root) => {
                if (!visible(root)) return;
                root.querySelectorAll('*').forEach((el) => {
                    if (!visible(el)) return;
                    const r = el.getBoundingClientRect();
                    if (r.left < -1 || r.right > vw + 1) offscreenDescendants.push(describe(el, sel + ' *'));
                });
            }));
            const internalOverflow = [];
            internalSelectors.forEach((sel) => document.querySelectorAll(sel).forEach((el) => {
                if (!visible(el)) return;
                if (el.scrollWidth > el.clientWidth + 1) internalOverflow.push(describe(el, sel));
            }));
            return {
                label,
                viewport: vw,
                docClientWidth: vw,
                docScrollWidth: docSw,
                bodyScrollWidth: bodySw,
                docStrictFit: docSw === vw,
                bodyStrictFit: bodySw <= vw,
                important,
                importantOffscreen: important.filter(x => x.offscreen),
                offscreenDescendants: offscreenDescendants.slice(0, 30),
                offscreenCount: offscreenDescendants.length,
                internalOverflow
            };
        }""", {
            'label': label,
            'rootSelectors': root_selectors,
            'importantSelectors': important_selectors,
            'internalSelectors': internal_selectors,
        })
        data['pass'] = data['docStrictFit'] and data['bodyStrictFit'] and len(data['importantOffscreen']) == 0 and len(data['offscreenDescendants']) == 0
        results.append(data)
        print(f"{label}: doc={data['docClientWidth']}/{data['docScrollWidth']} bodySw={data['bodyScrollWidth']} importantOffscreen={len(data['importantOffscreen'])} offscreenDescendants={data['offscreenCount']} internalOverflow={len(data['internalOverflow'])} pass={data['pass']}")
        if data['importantOffscreen']:
            print('Important offscreen sample:', json.dumps(data['importantOffscreen'][:3], indent=2))
        if data['offscreenDescendants']:
            print('Offscreen descendant sample:', json.dumps(data['offscreenDescendants'][:3], indent=2))
        if data['internalOverflow']:
            print('Internal overflow sample:', json.dumps(data['internalOverflow'][:3], indent=2))
        return data

    try:
        for width in widths:
            await page.set_viewport_size({'width': width, 'height': 844})

            print(f"Testing empty cart at {width}px")
            await set_token(empty_token)
            await page.goto(f'{frontend}/cart', wait_until='networkidle')
            await page.wait_for_selector('[data-testid="cart-page"]', timeout=15000)
            await page.wait_for_selector('[data-testid="cart-empty"]', timeout=15000)
            await measure(
                f'cart-empty-{width}',
                ['[data-testid="cart-page"]'],
                ['[data-testid="cart-page"]', '[data-testid="cart-empty"]', '[data-testid="cart-empty"] a', '[data-testid="cart-empty"] button'],
                []
            )

            print(f"Testing filled cart at {width}px")
            await set_token(buyer_token)
            await page.goto(f'{frontend}/cart', wait_until='networkidle')
            await page.wait_for_selector('[data-testid="cart-page"]', timeout=15000)
            await page.wait_for_selector('[data-testid^="cart-item-"]', timeout=15000)
            await measure(
                f'cart-filled-{width}',
                ['[data-testid="cart-page"]'],
                ['[data-testid="cart-page"]', '[data-testid^="cart-item-"]', '[data-testid="order-summary"]', '[data-testid="checkout-btn"]', '[data-testid^="cart-remove-"]', '[data-testid^="cart-seller-link-"]'],
                ['[data-testid="order-summary"]', '[data-testid="checkout-btn"]']
            )

            print(f"Testing checkout card at {width}px")
            await page.goto(f'{frontend}/checkout/{listing_id}', wait_until='networkidle')
            await page.wait_for_selector('[data-testid="checkout-page"]', timeout=15000)
            await page.wait_for_selector('[data-testid="pay-method-card"]', timeout=15000)
            await measure(
                f'checkout-card-{width}',
                ['[data-testid="checkout-page"]', '[data-testid="sticky-checkout-bar"]'],
                ['[data-testid="checkout-page"]', '[data-testid="pay-method-card"]', '[data-testid="pay-method-wallet"]', '[data-testid="pay-method-crypto"]', '[data-testid="pay-method-bank"]', '[data-testid="pay-card-panel"]', '[data-testid="coupon-input"]', '[data-testid="coupon-apply"]', '[data-testid="sticky-checkout-bar"]', '[data-testid="place-order-mobile-btn"]'],
                ['[data-testid="coupon-input"]', '[data-testid="sticky-checkout-bar"]']
            )

            for method in ['wallet', 'crypto', 'bank']:
                print(f"Testing checkout {method} at {width}px")
                await page.evaluate("""(method) => document.querySelector(`[data-testid="pay-method-${method}"]`)?.scrollIntoView({block: 'center', inline: 'center'})""", method)
                await page.wait_for_timeout(200)
                button_selector = f'[data-testid="pay-method-{method}"]'
                panel_selector = f'[data-testid="pay-{method}-panel"]'
                await page.locator(button_selector).click(force=True)
                await page.wait_for_timeout(300)
                if await page.locator(panel_selector).count() == 0:
                    # Fallback for mobile/touch emulation where overlay/scroll positioning can swallow the click.
                    await page.evaluate("""(selector) => document.querySelector(selector)?.click()""", button_selector)
                    await page.wait_for_timeout(300)
                if await page.locator(panel_selector).count() == 0:
                    box = await page.locator(button_selector).bounding_box()
                    if box:
                        await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                        await page.wait_for_timeout(300)
                await page.wait_for_selector(panel_selector, timeout=15000)
                important = ['[data-testid="checkout-page"]', '[data-testid="pay-method-card"]', '[data-testid="pay-method-wallet"]', '[data-testid="pay-method-crypto"]', '[data-testid="pay-method-bank"]', panel_selector, '[data-testid="coupon-input"]', '[data-testid="coupon-apply"]', '[data-testid="sticky-checkout-bar"]', '[data-testid="place-order-mobile-btn"]']
                internal = ['[data-testid="coupon-input"]', '[data-testid="sticky-checkout-bar"]']
                if method == 'crypto':
                    important += ['[data-testid="crypto-detail-card"]', '[data-testid="crypto-qr"]', '[data-testid="crypto-address"]', '[data-testid="crypto-copy"]']
                    internal += ['[data-testid="crypto-detail-card"]', '[data-testid="crypto-address"]']
                if method == 'bank':
                    important += ['[data-testid="bank-instructions"]', '[data-testid="bank-copy"]']
                    internal += ['[data-testid="bank-instructions"]', '[data-testid="bank-instructions"] pre']
                await measure(f'checkout-{method}-{width}', ['[data-testid="checkout-page"]', '[data-testid="sticky-checkout-bar"]'], important, internal)

        error_text = await page.evaluate("""() => {
            const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
            return errorElements.map(el => el.textContent).join(", ");
        }""")
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")

        failures = [r for r in results if not r['pass']]
        out.write_text(json.dumps({'ok': len(failures) == 0, 'failure_count': len(failures), 'failures': failures, 'results': results}, indent=2))
        if failures:
            raise AssertionError(f"Mobile fit failures: {len(failures)}")
        print('Browser mobile fit test completed')
    except Exception as exc:
        if not out.exists():
            out.write_text(json.dumps({'ok': False, 'error': str(exc), 'results': results}, indent=2))
        print(f'Browser mobile fit test failed: {exc}')
        raise