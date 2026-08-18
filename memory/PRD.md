# Mercari Clone — Product Requirements Document

## Original Problem Statement
Exact replica of Mercari platform (mercari.com) — same color scheme (`#FF211F`), name and function. Full-stack (FastAPI + MongoDB + React), JWT auth with roles (admin/user), product listings, and admin panel controlling every aspect. Extended to include dropshipping features, affiliate marketing, storefronts, multi-level referrals, and live Amazon product scraping via Apify.

## Users
- **Buyers**: browse/search listings, favorite, cart, checkout, review sellers, chat.
- **Sellers** (verified users): create listings, run a storefront, view analytics, receive payouts.
- **Affiliates**: generate referral/affiliate links per listing or store, earn commission on conversions.
- **Referrers**: earn 3-level MLM commissions on new signups' platform fees.
- **Admins**: manage users, listings, orders, categories, withdrawals, seller applications, Apify sync, and settings.

## Core Requirements
- JWT auth with roles.
- Product catalog with categories, favorites, cart, checkout, orders.
- Storefronts with verified tiers (bronze/silver/gold).
- Affiliate program (5% commission, tracked links).
- 3-level referral MLM (3%, 1%, 0.5% of platform fee).
- Reviews & ratings, in-app chat, notifications.
- Wallet + withdrawals.
- Apify Amazon crawler integration.
- Admin panel controlling every aspect.
- **Phase 1 (Trust & Payments)**: Email + phone verification, seller application queue, mock Stripe Connect payouts.

---

## Implemented (with dates)

### Feb 2026 — Paid Zyte Key + Concurrent Image Rehost
- **Zyte paid key** — `ZYTE_API_KEY` rotated to the user's paid $100 plan credential. Amazon extraction now returns full data: verified `amazon_search` for "wireless headphones" pulled 23 real products (correct titles, prices, images) in 28 seconds via one productList call. Prior trial-tier limitations lifted with zero code changes.
- **Concurrent image rehost** — `rehost_many()` now dispatches all fetches via `asyncio.gather` instead of a sequential loop. Benchmark on 8 images: **2.70s → 0.55s = 4.91× speedup**. Critical for 1,000-URL CSV runs where each listing has multiple images.

### Feb 2026 — Local Media Storage + Per-User Zyte Quotas + Paginated Amazon/Mercari Seed Scraper
- **Local media storage** (replaces R2 dependency) — new `/app/backend/uploads/` root, mounted at `/api/uploads/*` so it flows through the same Kubernetes ingress rule as the API. `services/r2_storage.py` now defaults to local disk and falls back to Cloudflare R2 only when `R2_*` env vars are set. Every scraped image gets rehosted to a fully-qualified `{REACT_APP_BACKEND_URL}/api/uploads/scraper/<sha256>[:2]/<sha256>.<ext>` URL — supplier CDN dependencies eliminated with zero external creds.
- **Per-user Zyte quotas** (`services/quotas.py`) — every Zyte call charges 1 credit against the calling user's monthly budget. Global default cap of 500 credits/user/month, per-user override in `users.zyte_monthly_cap`. Pre-flight `assert_can_spend` blocks over-budget requests with HTTP 429. Failed API calls do NOT debit. New endpoints: `GET /api/scraper/quota`, `GET /api/scraper/admin/quota`, `POST /api/scraper/admin/quota/override`, `POST /api/scraper/admin/quota/global-cap`. Frontend: `QuotaWidget` shows used/cap/remaining with red state when < 10%; `/admin/quotas` page for global cap + per-user overrides.
- **Paginated seed scraper** — `POST /api/scraper/jobs/paginated` walks N pages (1-50) of an Amazon search / Amazon bestsellers / Mercari search feed. Each page = 1 Zyte productList call ≈ 30-60 products, so 10 pages ≈ 300-600 live listings for 10 credits. `GET /api/scraper/super-batches/{id}` aggregates progress. Frontend `PaginatedSeedScrape` panel with provider select, pages slider, keyword input, category select, auto-publish + high-fidelity switches, and live per-page progress.
- **Self-healing Redis** — supervised via `scripts/start_redis.sh` which apt-reinstalls the binary on the fly when Emergent's pod restart wipes it. Fixes recurring "redis-server not found" outages.
- **Testing** — iteration_32: 9/9 new + 43/43 regression pytest, full Playwright pass.

### Feb 2026 — Import at Scale: Category URL + CSV Paste + One-Click Auto-Publish
- **Category URL extraction** — `POST /api/scraper/jobs/category` runs a single Zyte `productList` call against an Amazon search / eBay category / Shopify collection / etc. and fans out into N pre-extracted `scraper_jobs` rows (no per-URL Zyte round-trip). Verified: 20 books from books.toscrape.com/mystery_3 in ~10s.
- **CSV paste** — `POST /api/scraper/jobs/csv` accepts up to **1,000 URLs** per submit, reuses the arq `scrape_url_task` pipeline, and returns `{batch_id, queued_count, queued[], rejected[]}` with dedupe + invalid-URL reasons.
- **One-click auto-publish** — when `auto_publish=true` + `category_id` is set on any of `/category`, `/csv`, or `/bulk`, the worker calls `_publish_from_result` which creates a real `Listing` (status='active') with correct `seller_name`, `category_name`, `store_id`. `scraper_jobs.publish_status='published'` and `published_listing_id` point to the live listing.
- **/bulk cap raised** from 20 → 500 URLs, and it now validates `category_id` exists when `auto_publish=true`.
- **Frontend** — new `CategoryScrapeAtScale` component with 2 tabs (Category URL / CSV paste), category select, Auto-Publish Live switch (default ON), Amazon Full Pull switch, live progress + per-job cards with "live" badges, and a "View your N live listings" link when done. Sits atop the existing single + bulk panels on `/sell → Import from URL`.
- **Testing** — iteration_31: 19/19 new + 24/24 regression pytest, full frontend Playwright pass.

### Feb 2026 — Bulk URL Import + Amazon Full Pull toggle
- **Bulk import backend** — `POST /api/scraper/jobs/bulk` accepts up to 20 URLs with a shared `category_id`, dedupes per-request, rejects invalid URLs with a `reason`, and creates a `scraper_batches` document plus one `scraper_jobs` row per URL. `GET /api/scraper/batches/{id}` returns aggregate `counts` + per-job progress (owner or admin only).
- **Amazon Full Pull (`high_fidelity`) toggle** — new query flag on both single and bulk endpoints. When true, `services/zyte.py` skips the fast path and requests `browserHtml:true` with the anti-bot proxy pipeline. `extract_from` field on the result records the mode used (`browserHtml_hi` / `browserHtml` / `httpResponseBody`).
- **Frontend** — new `BulkImportFromUrls` component sits below the single URL panel on `/sell → Import from URL`. Textarea (max 20 lines), category select, "Amazon Full Pull" switch, live-progress bar + per-job cards with a "Use" button on each finished job that prefills the New listing form. Single ImportFromUrl also gained the same Amazon Full Pull switch.
- **Testing** — iteration_30: 25/25 pytest (test_scraper.py + test_scraper_bulk.py), 100% frontend.
- **Note** — the current Zyte free-tier key returns partial data for Amazon even with `browserHtml_hi`; the plumbing is verified and will unlock full extraction once the plan is upgraded.

### Feb 2026 — Zyte Scraper Pipeline with arq Queue + R2 Rehost (Alongside Apify)
- **Zyte extraction service** (`services/zyte.py`) — POSTs to `https://api.zyte.com/v1/extract` with HTTP Basic Auth. Fast `httpResponseBody` mode with automatic fallback to `browserHtml` for JS-heavy sites. Normalizes Zyte's `product` schema → canonical listing shape (title/description/price/images/brand/sku).
- **arq worker** (`services/queue.py`) — Python-native async Redis queue. Redis and arq worker supervised in `/etc/supervisor/conf.d/redis.conf` + `arq_worker.conf`. Worker loads backend/.env explicitly so Mongo/Zyte creds resolve outside FastAPI context.
- **Cloudflare R2 storage** (`services/r2_storage.py`) — S3-compatible client via boto3. Env-gated: when `R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET` are set, images are streamed & rehosted; otherwise the supplier URL is returned unchanged. Deterministic keys prevent duplicate uploads.
- **Scraper API** (`routers/scraper.py`): `POST /api/scraper/jobs` (auth) enqueues, `GET /api/scraper/jobs/{id}` polls, `GET /api/scraper/jobs` lists user's own, `GET /api/scraper/admin/jobs` admin all, `GET /api/scraper/status` health probe (Zyte + Redis + R2).
- **Sell → Import from URL** — third tab on `/sell` with `ImportFromUrl` component; sellers paste any Amazon/Shopify/eBay/etc. URL, watch a live-polling recent-imports list, and click "Use" to prefill the New listing form.
- **Admin Zyte scraper page** (`/admin/scraper`) — health pills for Zyte/arq/R2, per-status filter, auto-refresh every 5s, full jobs table with error surfaces.
- Apify sync remains untouched — Zyte runs alongside as a new source.

### Feb 2026 — Email Preferences UI, Admin Email Log Viewer, and Real Stripe Checkout
- **Email Preferences UI** — new Settings tab on `/profile?tab=settings` renders `EmailPreferences` component with 6 category switches (order, sale, wallet, payout, dispute, system). Toggling calls `PUT /api/me/email-prefs` and persists per user. Backend `notify()` already respects the map — sends email only when the corresponding `email_prefs.<kind>` is not `false`.
- **Admin Email Log** — new sidebar entry `/admin/email-log` (`AdminEmailLog.jsx`) surfaces every `email_log` record with columns for status/kind/recipient/subject/provider/error. Failed rows highlight red; "Failed only" filter and per-kind filter; one-click "Send test" input calls `POST /api/admin/email/test` for pipeline verification.
- **Real Stripe Checkout** — the mock card path is replaced with a real Stripe Checkout Session. New router `routers/stripe_payments.py`:
  - `POST /api/checkout/stripe-session` (auth) — server-side totals, saves pending payload to `stripe_pending_orders`, returns hosted `checkout_url`.
  - `GET /api/payments/status/{session_id}` (public) — polls Stripe; on `paid` finalizes the order by calling `create_order()` idempotently so all existing side-effects (frozen escrow, notifications, ledger) apply.
  - `POST /api/webhook/stripe` — signature-verified webhook that finalizes the same way.
  - Frontend `Checkout.jsx` — when `payMethod === 'card'`, shows a "Secure checkout by Stripe" panel and redirects to the hosted checkout on submit. New `PaymentSuccess.jsx` polls the status endpoint and shows an order-confirmation card; `PaymentCancel.jsx` offers a retry link.
- Uses shared Emergent Stripe sandbox key (`STRIPE_API_KEY=sk_test_emergent`) — no user credential needed. Test card `4242 4242 4242 4242`.

### Feb 2026 — Unified Ledger Service + Wallet ↔ Checkout Deposit Parity
- **New `services/ledger.py`** — single source of truth for balance-affecting events. `apply_entry()` is atomic (`$inc` + guard) and always writes a paired `wallet_txs` row. Wrappers: `deposit_approved`, `purchase_debit`, `refund_credit`, `release_frozen`, `reconcile_reseller`.
- **Every write path now routes through the ledger**: `create_order` wallet payment, dropship wholesale debit, deposit approval, manual + auto dispute refunds. `credit_wallet()` and legacy `release_frozen` are thin wrappers around the ledger for backward compatibility. Extended `WalletTransaction.type` literal with `deposit`, `purchase`, `wholesale_debit`.
- **Wallet ↔ Checkout deposit parity** — Added `GET /api/wallet/deposit-methods` + `POST /api/wallet/deposit/pending` that read the SAME admin config (`crypto_assets` + `manual_payment_methods`) as the Checkout Payment page. Refactored `pages/Wallet.jsx` `DepositDialog` to consume this endpoint. Verified live: dropdown now shows all 5 admin-configured crypto networks (ETH·Ethereum, BNB·Ethereum, BTC·BTC, USDC·Ethereum, USDT·Ethereum) with per-network warning text — identical to Checkout.
- **Reconcile endpoints** — `POST /api/wallet/reconcile` (self-heal) and `POST /api/admin/wallet/reconcile/{user_id}` recompute a user's available balance from the ledger and post an `adjustment` for any drift (useful for reseller earnings sync after external price/inventory events).
- **E2E verified**: manual $100 deposit → tx `deposit`, purchase 2× → tx `purchase` −$44.24 debited atomically, insufficient-funds returns 400 with clear message.

### Feb 2026 — Cart/Checkout Mobile Strict-Fit + Marketplace Data Hygiene
- **Weekly Amazon refresh** — `apify_auto_sync_loop()` in `server.py` rewritten to be resume-safe: on every startup it reads `last_sync_at`, sleeps only until the next 7-day mark (not a fresh full week), and auto-clears stuck `sync_running` locks older than 6 hours. Persists `next_scheduled_at` + `schedule_interval_days` in `sync_state`.
- **Admin controls** — new `POST /api/admin/sync/apify/schedule` accepts `{enabled: bool, run_now: bool}` to pause/resume the loop or force the next tick to run within ~60s. Non-admin blocked (401), empty payload rejected (400).
- **Sync status expanded** — `GET /api/admin/sync/status` now returns `next_scheduled_at`, `schedule_interval_days`, `auto_schedule_enabled` alongside the existing counters.
- **Admin UI** — `/admin/apify-sync` now surfaces the next scheduled datetime, a "Pause/Resume" toggle chip, and a "Run scheduled sync now" button (`data-testid: apify-next-scheduled | apify-schedule-toggle | apify-run-schedule-now`). Verified via screenshot: next scheduled 2026-08-17 20:14 UTC (exactly 7 days after the last successful run).
- **Cart & Checkout mobile clipping (P0) — FIXED and verified by bug_testing_agent (iteration_27, verdict: fixed).** Both pages now strict-fit at 320/375/390 px viewports with `documentElement.scrollWidth === clientWidth` on empty cart, filled cart, and all four checkout payment panels (Card/Wallet/Crypto/Bank).
  - Root cause: `grid lg:grid-cols-[1fr_360px]` had no explicit mobile column, so implicit grid tracks kept `min-content` sizing and any wide child (long product title, payment chip row) pushed the track past viewport width.
  - Fix in `/app/frontend/src/pages/Cart.jsx` + `/app/frontend/src/pages/Checkout.jsx`: explicit `grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]`, `min-w-0` on grid wrapper AND children, `shrink-0` on image + price/trash column, `whitespace-nowrap` on price, `p-3 sm:p-4/5` reduced side padding, `line-clamp-2` retained.
- **Test data purge — DONE.** Marketplace now serves ONLY real Apify Amazon products.
  - `/app/backend/scripts/cleanup_test_data.py` deleted 2,481 test-owned listings + 188 test users + 6 test-titled listings owned by kept sellers. Also strips derivative refs (favorites, cart_items, views, orders, stores, wallets, notifications, disputes, seller_applications).
  - Final state: **236 listings (233 active + 3 sold)** across the 10 real accounts (1 admin + 5 demo sellers + 4 human-registered).
  - `/app/backend/apify_sync.py` `_get_sellers()` is now whitelisted to the 5 curated demo sellers (`sophia_style`, `urban_finds`, `vintage_maven`, `tech_haven`, `cozy_home`) so future Apify runs never distribute products to test users.


### Feb 2026 — Phase 20: Multi-Asset Crypto Checkout + Order Payment Persistence
- **Multi-Asset Crypto Payment Selector** on `/checkout/:id` — Card / Wallet / Crypto / Bank chips. Crypto panel surfaces only admin-active assets (BTC, ETH, SOL, BNB, USDC across networks) with live QR code (`api.qrserver.com`), copyable address + network label. Wallet panel shows available/frozen and disables Pay when insufficient. Bank panel lists admin-configured manual methods with instructions + copy.
- **Admin controller** (`/admin/payment-methods`) — `GET/PUT /api/admin/settings/payment-methods` accept a `crypto_assets` list (`{symbol, network, address, active}`) + `manual_payment_methods` list, sanitized server-side (drops non-dict, requires symbol+network, caps lengths). Non-admin returns 403.
- **User-facing** `GET /api/wallet/payment-methods` returns only active crypto assets + active manual methods, mirroring the admin config.
- **Order model** — added `payment_method` (`card|wallet|crypto|bank`) and `payment_currency` (`ETH`/`SOL`/manual-method-id). `OrderCreate` accepts both. `POST /orders` now persists the chosen method on the order document.
- **Wallet balance validation** — `POST /orders` with `payment_method="wallet"` atomically debits the buyer's `wallet_balance` and rejects with HTTP 400 `"Insufficient wallet balance"` when the balance is under the total. A `wallet_txs` audit row is inserted for every wallet checkout.
- **Order status** — crypto/bank orders open as `status="pending"` so admin can approve after off-chain settlement. Card/wallet remain instant `paid`.
- **Regression** — `testing_agent_v3_fork` iteration 20 reported 28/28 backend tests green (13 new Phase 20 + 15 Phase 19 baseline) and all frontend E2E flows green. Post-report fixes applied and manually re-verified via curl: crypto order returns `payment_method: crypto`, `currency: ETH`, `status: pending`; wallet order with $0 balance rejects with `HTTP 400 · "Insufficient wallet balance. Available $0.00, need $24.15"`.

### Feb 2026 — Checkout Multi-Channel Payment Selector
- **4-way payment method selector** on `/checkout/:id` — Card / Wallet / Crypto / Bank chips with per-method color gradients (sky / emerald / amber / fuchsia), 72px min height, hover `-translate-y-0.5`, `active:scale-95`.
- **Wallet panel** — emerald-tinted card showing available balance, frozen sub-line, and a red "insufficient balance" guard that disables the Pay button.
- **Crypto panel** — currency chips (BTC/ETH/USDC/USDT), live QR code (`api.qrserver.com`), copyable monospace address, "send exactly $X worth of {ccy}" instruction. Only shows currencies enabled in `Settings.crypto_addresses`.
- **Bank panel** — dynamic method chips from `Settings.manual_payment_methods`, whitespace-preserved instructions card, copy-instructions button. "Order goes on hold until admin confirms" note.
- **Pay button** upgraded to a 48px orange→red gradient pill with red glow shadow + hover-lift.
- `POST /orders` now sends `payment_method` alongside `share_ref` and `affiliate_code` for future backend routing.
- Verified on 1440×900 desktop and 390×844 mobile: all 4 panels render, animations engage, mobile touch targets stay at ≥44px.

### Feb 2026 — StorePage Contrast + Owner Publish CTA
- **Route alias** `/dashboard/list-product` → `Sell` page added in `App.js` so the requested CTA path works while still reusing the existing Sell workflow.
- **Owner Control Panel** — new high-contrast card rendered only when `isOwn`. Salmon → white → purple gradient background with soft orbs, orange gradient icon, "OWNER CONTROLS" chip, and 2 buttons:
  - **"Publish / List Products"** — vibrant orange→red gradient pill, 48px tall, glowing red shadow, hover `-translate-y-0.5` with `xl` shadow. Links to `/dashboard/list-product`.
  - **"Dashboard"** — outlined pill linking to `/store/analytics`.
- **Store listings section** wrapped in its own white card with shadow for clear section separation. Section header updated: filled gradient "STOREFRONT" pill (was tinted), bold "Store listings" title, tabular-nums counter "**N** of M items on offer".
- **Category chips** — hairline bottom border for separation, active state uses gradient background + red glow shadow, hover lifts by 0.5px, `active:scale-95` for touch feedback.
- **Product grid** — each card wrapped with `hover:-translate-y-0.5 hover:shadow-lg transition-all` for a subtle interactive feel.
- **Empty state** — for owners now includes a "Publish your first item" gradient CTA so a blank storefront always has a next step.
- Verified on 1440×900 desktop: owner sees control panel + Publish CTA, click navigates to `/dashboard/list-product` which renders the Sell page. Store listings card renders 65 items, category chips filter, hover states animate.

### Feb 2026 — Push Rewards Widget + Follower Notification Pagination
- **`GET /api/seller/push-stats`** — compact metrics for the Profile widget: `share_reach_followers`, `share_attributed_sales`, `share_attributed_gmv`, `share_attributed_earnings`, `last_share_sale_at`, `bonuses_count`, `bonuses_total`, `last_bonus_at`, `push_reward_amount` (from settings), and `eligible_for_next_bonus`. Two aggregates (orders + wallet_txs) + one settings read.
- **Profile widget** (`push-stats-widget`) — orange→red gradient icon, animated soft orbs, 3 color-coded stat tiles (Reach / Sales / Bonuses), emerald "+$X first-sale bonus available" CTA chip when eligible, "last on {date}" footer when there are attributed orders. Visible for any approved seller / admin so the incentive is always in view (not just after activity).
- **Cursor-based follower notifier** — `_notify_store_followers` now iterates `db.store_follows.find(...)` via `async for` instead of `to_list(1000)`. Stores with any follower count are notified without silent truncation. Verified end-to-end: admin follows Sophia's store → Sophia creates a listing → admin receives a `system` notification titled *"Sophy Style added something new"*.
- Lint clean · unauthenticated `GET /seller/push-stats` returns 401 · mobile screenshot confirms the widget renders with all three stat cards + eligibility chip.

### Feb 2026 — Store Follow Notifications + Phase 19 Regression Suite
- **`_notify_store_followers(store_id, title, listing_id, bulk=False)`** helper: fetches every follower of the store and pings a `system` notification with a deep link to the listing (or the storefront on bulk). Silent no-op when the store has no followers.
- Wired into all 3 publish paths: `POST /api/listings`, `POST /api/listings/import`, `POST /api/listings/import/bulk` (bulk sends one aggregated notification with the drop count).
- **Regression run** (`/app/test_reports/iteration_19.json`, `/app/backend/tests/test_phase19_regression.py`) — **15/15 pytest cases green**:
  1. Seller gate returns 403 with "Complete seller verification and approval…" on all 3 write endpoints for unapproved users; approved sellers succeed.
  2. Auto-store on both single approval (`PUT /admin/seller-applications/{id}`) and bulk (`POST /admin/seller-applications/bulk-review`) — user gets `store_id` + a unique username-derived slug.
  3. Wallet wholesale-debit — atomic `$gte` guard fires only when balance is sufficient; falls back to buyer-funded split otherwise; wallet_tx row + frozen credit both correct.
  4. Follow feed — 401 unauth, `[]` when following nobody, followed store's listings after `POST /stores/{slug}/follow`.
  5. Push reward — first `share_ref="push"` sale credits exactly one $2 bonus + stamps `push_reward_amount` on the order; second sale does NOT re-credit.
  6. Follower notifications — followers of the seller's store receive a system notification when the seller creates/imports/bulk-imports; sellers with 0 followers don't fail.
- **Non-blocking code quality notes** from the tester (deferred): extract `_require_approved_seller(user)` helper, replace description-regex idempotency check with a boolean flag or unique index, paginate `to_list(1000)` in `_notify_store_followers`, and consider `find_one_and_update` for the wallet debit balance-after read. server.py is at ~4443 lines — modular split still overdue.

### Feb 2026 — Seller Dashboard Redesign + Quick-Action Buttons
- **Vibrant hero redesign** (`StoreAnalytics.jsx`) — orange → pink → purple gradient with 3 soft glow orbs, matching the storefront hero for brand consistency. All stat pills upgraded with subtle borders + glassmorphism.
- **Quick-action buttons in the hero**:
  - **New listing** (white pill) → `/sell` — the primary path to publish an item.
  - **Bulk resell** (glass pill) → `/sell` — jumps to the resell workflow.
  - **View my store** (glass pill) → `/store/{mySlug}` — opens the seller's public storefront to visually verify auto-publish.
- **Mobile FAB**: a floating **+** button (bottom-right, gradient orange→red, `sm:hidden`) provides one-tap access to `/sell` on mobile.
- **"Recently published in your store" strip** — new section fetched from `/api/stores/{mySlug}/listings`, sorted by `created_at` desc. Shows 8 latest items in a horizontal snap-scroll with tagline "Every new listing lands here — and in your storefront — instantly." This proves the auto-attach behavior end-to-end for the seller.
- **Verified via screenshots** on 390×844 mobile and 1440×900 desktop — hero renders 3 CTAs + progress ring + stats, strip lists Sophia's newest items (Clear Backpack $15.59, The Sak Lumi $83.99, Clear Bag $32.38, …), and mobile FAB shows as a shadow-boosted gradient circle.

### Feb 2026 — Store Follow Feed + Storefront Push Rewards
- **`GET /api/feed/following?limit=20`** — returns fresh active listings from stores the current user follows, sorted newest first, excluding their own items. Auth-only.
- **Home page** — new **"New from stores you follow"** section (purple "YOUR FOLLOWS" pill + filled Heart icon) in a horizontal snap-scroll strip. Only renders when the logged-in user follows at least one store with active inventory.
- **Storefront Push Reward** — end-to-end conversion attribution:
  - `StorefrontShare` component now appends `?ref=push` to shared listing + store URLs.
  - `ListingDetail` captures `?ref=push` from the URL and stores it in `sessionStorage`.
  - `Checkout` passes `share_ref` in the `POST /orders` payload alongside the affiliate code, then clears it on success.
  - **Backend** — `OrderCreate.share_ref`, `Order.share_ref`, and `Order.push_reward_amount` fields added. On the seller's **first-ever** share-attributed sale, credit a `bonus` wallet tx of `settings.push_reward_amount` (default $2, admin-tunable via `PUT /admin/settings`), stamp the amount on the order, and send a "Storefront Push reward" wallet notification. Subsequent share-attributed sales are detected via prior `bonus` tx lookup and don't re-credit.
- **End-to-end verified**: Sophia follows Test Store → `/feed/following` returns 5 items · unauth = 401 · first buy w/ `share_ref=push` credits seller +$2.00 (balance 185.60 → 187.60) with the correct wallet tx description · second buy with same ref → no double-credit (still 1 bonus). Home strip renders with 12 products in a scrollable strip.

### Feb 2026 — Auto-Store Creation + Store Redesign + Follow System
- **Auto-store on approval**: added `ensure_store_for_user(user_id)` helper that generates a unique `{first_name}'s Store` with a slug based on the username (uniqueness-checked). Wired into all 3 approval paths: `POST /seller/apply` (auto-approve via trust score), `PUT /admin/seller-applications/{id}`, and `POST /admin/seller-applications/bulk-review`.
- **Safety net**: `POST /listings`, `POST /listings/import`, and `POST /listings/import/bulk` now call `ensure_store_for_user` when the seller lacks a `store_id`, guaranteeing every published item is instantly attached to a storefront.
- **New endpoints**: `POST /api/stores/{slug}/follow` (idempotent toggle, atomic `$inc` on `followers_count`, blocks self-follow) and `GET /api/stores/{slug}/follow-status`.
- **Historical backfill**: 80 existing listings across all users had their `store_id` populated from their owner's user record — every legacy seller's storefront now shows their inventory.
- **`StorePage.jsx` redesign** (fully mobile-first, 44×44 touch targets):
  - Vibrant animated gradient hero (orange → pink → purple with soft glow orbs).
  - Overlapping **profile card** with logo, tier badge, verification badges, tagline, bio, Follow + Share buttons.
  - Live **stat pills** in 4-up grid: Items · Followers · Sales · Since — color-coded per stat.
  - **Sticky mini-nav** appears on scroll with mini logo + name + Follow button.
  - **"New this week"** horizontal snap-scroll strip (last 7 days, emerald sparkles icon).
  - **"Hot picks"** strip (most-favorited, orange flame icon).
  - **Category filter chips** derived from the store's own listings with live counts; active chip uses the brand gradient. Combined with a sort dropdown.
- **Verified end-to-end via API**: single-review approval → user gets `seller_status: approved` + fresh `store_id: <uuid>` pointing to auto-created `"Auto's Store"`. Follow flow toggles cleanly (0→1→0). Sophia's 62-item store shows all strips, chips filter to "Women (21)" and updates counter.

### Feb 2026 — AI-Curated Suggested-For-Me Bulk Resell
- **New endpoint `GET /api/seller/resell-suggestions?limit=10`** — returns personalized picks scored by:
  1. **Category preference** from the seller's own active listings (+1.0 each) and completed orders (+2.5 each).
  2. **Popularity** (`likes_count × 1.0 + views_count × 0.05`).
  3. **Diversity** via round-robin weaving across the seller's top 3–4 categories.
  4. **Exclusions** — own listings, already-imported source ids, inactive items.
  New/empty sellers fall back to catalog-wide popular categories with a `fallback: true` flag. Each pick includes a human-readable `reason` (e.g. "Your top category · 89 favorites", "Hot in this category · 86 favorites"), `wholesale_cost` (tier-based), `score`, and category badge. The response also returns a natural-language `reason` summary ("Top-selling items in Women, Other, Men — your best categories so far.") and `top_categories`.
- **`ResellFromCatalog.jsx`** — added a third mode tab **"For me"** (wand icon). Selecting it fetches suggestions, auto-selects all 10 for one-tap publishing, and renders a gradient hero card (Smart picks + reason + category chips + Refresh) followed by a scrollable list with per-row emerald checkbox, image, price, category badge, and orange "why this" reason line. Reuses the existing sticky publish bar + `/listings/import/bulk` endpoint.
- **End-to-end verified**: Sophia (silver-tier) → 200, 10 picks weaved across Women/Other/Men/Electronics with real reasoning strings. Unapproved user → 403 "Complete seller verification and approval to see suggestions". Mobile screenshots (390×844) confirm the whole flow: mode toggle → hero card → 10 pre-selected picks → sticky publish bar.

### Feb 2026 — Admin Bulk Approve Seller Applications
- **New endpoint** `POST /api/admin/seller-applications/bulk-review` — approves or rejects up to 100 pending applications in a single call. Applies shared `admin_notes` to all, sets `seller_status` on each user, and fires the same per-user approval/rejection notifications as the single endpoint. Returns `{processed, skipped_count, skipped[]}` with per-item `reason` (`not_found`, `already_approved`, `already_rejected`).
- **`SellerApplicationsMgr` UI upgrade**:
  - Sticky top toolbar that appears whenever there is at least one pending application.
  - **"Select all pending (N)"** / **"Clear all"** toggle · live selected-count · shared bulk-notes input · **"Approve selected"** (emerald) + **"Reject"** buttons.
  - Each pending row now has a 44×44 checkbox; selected rows highlight with an emerald ring so admins see exactly what's about to change.
  - Row-level Approve/Reject buttons remain for one-off decisions.
- **End-to-end verified**: 3 seeded pending apps → bulk-approved → 200 `processed: 3, skipped_count: 0`. Re-run returned 200 `processed: 0` with 3 × `already_approved`. Empty ids returned 400 "Select at least one application"; invalid status returned 400 "Invalid status". Frontend screenshot on 1200-wide viewport confirms sticky bar, notes field, active/disabled button states.

### Feb 2026 — Seller Gating + Bulk Resell Publishing
- **Backend gate on `/api/listings/import`** — now returns 403 with "Complete seller verification and approval to resell listings" for any user whose `seller_status != "approved"` (admins bypass). Combined with the existing `/api/listings` (create) gate, all selling + reselling entrypoints are now consistent.
- **New `POST /api/listings/import/bulk`** — publishes up to 20 catalog items in one call. Same gate + tier-based markup cap enforcement. Returns `{published_count, skipped_count, published[], skipped[]}` with per-item skip reasons (`not_found_or_inactive`, `own_listing`, `already_imported`, `already_in_your_store`, `markup_exceeds_cap`). Supports a `default_markup_pct` fallback.
- **Frontend `Sell.jsx`** — replaced the silent `/verify` redirect with an inline `<SellerGate>` block that renders one of three states based on `user.seller_status`:
  - `none` → lock icon + "Selling is limited to verified sellers" + red "Apply to sell" CTA
  - `pending` → clock icon + "Application under review" + "View my application" CTA
  - `rejected` → red lock + reapply CTA
  All three list the same three benefit bullets and route to `/seller/apply`.
- **`ResellFromCatalog.jsx`** — added "Bulk publish" toggle inside the category product list. In bulk mode: each row shows a 44×44 checkbox; toolbar exposes "Pick top 10" (auto-selects the top-ranked 10) + "Clear" + live count with a red **max 20** warning past 20. A sticky bottom bar shows the count, a shared default-markup input (capped by tier), and an emerald **"Publish selected"** button that calls `/listings/import/bulk`. After success it shows a `bulk-result` summary card.
- **End-to-end verified via API and screenshots on 390×844 mobile**:
  - New user (`seller_status="none"`) hits `/api/listings/import`, `/import/bulk`, and `/listings` — all return 403 with the correct message.
  - Approved silver seller Sophia — bulk-published 3 Women's items @15% markup → 200, `published_count: 3, applied_cap: 80.0`.
  - Sell page renders the gate card for unapproved user; Sell → Resell → Kids → Bulk on → Pick top 10 renders the sticky publish bar with 10 checkboxes ticked.

### Feb 2026 — Wallet Wholesale Auto-Debit + Storefront Share Dialog
- **Order model** — added `reseller_wholesale_cost` and `reseller_paid_wholesale` fields.
- **`POST /api/orders`** — on imported (resell) listings, atomically debits the reseller's `wallet_balance` for their tier-based wholesale cost (`base_price × (1 − discount_pct)`) using a conditional `$gte` update to prevent oversell. On success, source seller earns wholesale cost (frozen), reseller earns `amount − platform_fee − affiliate` (keeps more since wholesale is pre-paid). Falls back to buyer-funded split when balance is insufficient — no sale is ever blocked.
- **Wallet history** — records an `adjustment −wholesale_cost` transaction (`"Wholesale cost auto-paid: <title>"`) and a wallet notification for the reseller.
- **`StorefrontShare.jsx`** — new reusable component (`StorefrontShareDialog` + `StorefrontShareButton`) with product preview, storefront URL, listing URL (both copy buttons), ready-to-post caption (auto-generated with title + price + hashtags), and one-tap share intents for Twitter/X, Facebook, WhatsApp, Telegram + native "More…" via `navigator.share`.
- **ListingDetail** — when viewing your own listing, shows a full-width **"Share to boost sales"** pill button that opens the share dialog. Fetches user's store slug from `/api/my/store`.
- **ResellFromCatalog** — after publish, the share dialog opens automatically with a "Published! Share it to boost your first sale" headline; closing navigates to the listing detail page.
- **End-to-end verified via curl:** silver reseller imports $8.99 base @ 30% markup → priced $11.69. Admin buys → order shows `reseller_wholesale_cost: $8.09`, `reseller_paid_wholesale: True`; reseller wallet debited 8.09 available + credited 11.69 frozen; wallet_txs shows both entries.
- **Screenshots verified** on 390×844 mobile: listing page own-view share button, share dialog with preview + copy + channel buttons, wallet after debit.
- Backend + frontend lint clean.

### Feb 2026 — Category-Based Reseller Workflow + Deposit Screenshots + Refunds View + Wholesale Discount Tiers
- **Backend `Settings`** — added `resell_wholesale_discounts` per tier (`new:0`, `bronze:5`, `silver:10`, `gold:15`). Whitelisted in `PUT /api/admin/settings`.
- **`GET /api/seller/resell-info`** — now returns `resell_wholesale_discounts` (full map) + `wholesale_discount_pct` (this user's live rate).
- **`ResellFromCatalog.jsx`** — added "By category / Search" mode toggle. Category mode shows a dropdown of all 22 admin categories → renders the top 40 popular products in a scrollable list, each with a compact **Select** button (44×44 touch target) that pins the item to the markup + earnings preview panel. Earnings preview now shows Retail / Wholesale cost (X% off) / Markup / Buyer pays / Platform fee / Paid to source seller / **You earn** — accurately deducts wholesale from margin.
- **`Wallet.jsx`** — added **Refunds** action button that opens a `RefundsDialog` showing total refunded + per-refund history + link to `/disputes`.
- **Deposit dialog** — new "Payment screenshot" upload zone (dashed dropzone), uses `/api/upload` (12 MB limit, jpg/png/webp/gif/pdf), stores `screenshot_url` on the deposit. Preview + remove button before submit.
- **`AdminPaymentMethods.jsx`** — pending deposits now show a 20×20 thumbnail of the uploaded screenshot (opens full size in new tab) to speed admin review.
- **All new UI** uses `min-h-[44px]` / `min-w-[44px]` touch targets, dialogs `max-h-[90vh] overflow-y-auto`, and adapts flawlessly to 390×844 (iPhone 12) and 1440×900 (desktop).
- End-to-end verified via curl: resell-info returns tier-aware discount ✅, `/listings?category_id=X` returns products ✅, `/upload` returns URL ✅, deposit accepts `screenshot_url` ✅.
- Screenshots captured for: wallet 3-button card, deposit dialog with upload zone, refunds dialog, category dropdown, product list with Select buttons, full earnings preview.

### Feb 2026 — Crypto & Manual Deposit System + Admin Payment Methods Panel
- **`Settings` model** extended with `crypto_addresses` (BTC/ETH/USDC/USDT — blank = hidden) and `manual_payment_methods` (list of `{id, name, instructions, icon, active}`).
- **`DepositRequest` model** — `{id, user_id, user_name, amount, method: crypto|manual, currency, reference, note, screenshot_url, status: pending|approved|rejected, admin_note, created_at, processed_at}`.
- **New endpoints:**
  - `GET /api/wallet/payment-methods` — user-facing: active crypto + active manual methods.
  - `POST /api/wallet/deposit` — user submits deposit claim (validates amount, currency, tx-hash for crypto).
  - `GET /api/wallet/deposits` — user's deposit history.
  - `GET /api/admin/settings/payment-methods` / `PUT` — admin CRUD (sanitizes list items).
  - `GET /api/admin/deposits/pending` — admin list (optional `status_filter`).
  - `POST /api/admin/deposits/{id}/approve` — credits wallet as an `adjustment` tx + notifies user.
  - `POST /api/admin/deposits/{id}/reject` — with reason, notifies user.
- **Frontend `Wallet.jsx`** (rewritten, fully responsive w/ 44×44 touch targets):
  - Header with Deposit / Withdraw / Payout dashboard buttons.
  - **Deposit dialog** — Crypto tab (currency select → live QR from `api.qrserver.com` + copy-address + amount + tx-hash) & Bank/Other tab (method select + rendered instructions + copy).
  - **Withdraw dialog** — Crypto tab (currency + external wallet address input) & Bank/Other tab (free-form payout details).
  - Deposit requests list (approved/pending/rejected badges), mobile card view for transactions, desktop table on ≥sm.
- **Admin panel** — new `/admin/payment-methods` route + sidebar link (Bitcoin icon). Two tabs: **Methods** (crypto addresses + Add/Toggle/Delete manual methods with textarea instructions) and **Pending** (approve/reject with reason). Live counter badge on Pending tab.
- **Backend verified via curl:** create → pending → approve → wallet +$50 ✅ · reject with reason ✅ · re-approve returns 400 ✅ · missing tx-hash returns 400 ✅.
- **Frontend verified via screenshots** on iPhone 390×844 (mobile) and 1440×900 (desktop) — deposit dialog with QR, admin panel Methods & Pending tabs.
- Testing status: self-tested end-to-end (curl + screenshots). No `testing_agent_v3_fork` run for this iteration.

### Feb 2026 — Admin Per-User Resell Cap + Badge Progress + Full Regression
- **Admin → Users** now has a "Resell cap %" column (`resell-cap-input-<userId>`). Entering a number 0–500 sets `resell_markup_override` on that user (hard-cap that bypasses tier logic); blanking it reverts to the badge-tier cap. Persists on blur with a success toast. `PUT /api/admin/users/{id}` accepts and validates the new field; non-admin returns 403; out-of-range/non-numeric returns 400.
- **Profile hero badge progress bar** (`BadgeProgress` in `Profile.jsx`) — fetches `/api/seller/resell-info`, shows tier chip + max % + a gradient progress bar with New/Bronze/Silver/Gold stops and % to next tier, plus a hint like "Unlock Gold with 4 more sales." Top-tier users see the celebratory copy.
- **Import error privacy fix** — when the cap is admin-imposed (`applied="override"`), the 400 message is now neutral ("Markup exceeds your allowed cap.") so the exact override value isn't leaked to the seller.
- Verified via `testing_agent_v3_fork` iteration_18: **10/10 backend pytest + all frontend E2E green** — zero action items. Test file: `/app/backend/tests/test_phase18_resell_markup_cap.py` (run serially with `-o addopts=''`).

### Feb 2026 — Sell-Page Resell Mode with Badge-Tiered Markup Caps
- **User model** — new `resell_markup_override` field (admin-set hard cap that bypasses tier logic).
- **Settings** — new `resell_markup_caps` dict per badge (`new: 25%`, `bronze: 50%`, `silver: 80%`, `gold: 120%`), tunable via `PUT /api/admin/settings`.
- **Backend helpers** — `compute_seller_badge()` auto-tiers on (sales_count, rating): New → Bronze (≥5 sales, ≥4.0) → Silver (≥20, ≥4.5) → Gold (≥50, ≥4.7). `resolve_max_markup()` returns override if set, else the tier cap.
- **New endpoint** `GET /api/seller/resell-info` — returns `{badge, applied, max_markup_pct, platform_fee_pct, resell_markup_caps, sales_count, rating, override_active}`.
- **`POST /api/listings/import` enforcement** — validates markup against `min(global dropship cap, seller tier cap)`.
- **Frontend `/sell`** — added a rounded segmented **"New listing" ⇄ "Resell existing item"** toggle at the top of the page.
- **`ResellFromCatalog.jsx`** — resell mode shows the seller's tier badge + max % + progression hint, a live catalog search (debounced against `/search/suggest`), a picked-source card with Change, a markup input with 5/10/20/35/50% presets, over-cap error, and a live earnings preview (base → markup → buyer pays → platform fee → source-seller cut → your earnings + margin %). Publish button posts to `/listings/import` and routes to the new reseller listing.

### Feb 2026 — Profile Hero Modernization + Payout Dashboard + Dropship Earnings Preview
- **Profile hero redesigned** (`Profile.jsx`) — replaced the flat neutral header with a full-bleed gradient card (orange→red) featuring decorative blur blobs, subtle grid pattern, a rounded-square avatar with ring, chips for verification/role/tenure, 4 glass-morphic stat cards (Available / Frozen / Lifetime sales / Listings), 4 quick-action CTAs (Sell / Payout dashboard / Wallet / Share), and a copyable referral-code strip. Fully dark-mode compatible; hero data auto-loads from `/api/wallet`.
- **Payout Dashboard** (`/seller/payouts`, `PayoutDashboard.jsx`, `GET /api/wallet/payout-dashboard?days=…`) — new standalone view that aggregates available balance, frozen amount, pending withdrawals, and lifetime total on gradient stat cards; a Recharts area chart plots frozen-in vs released vs withdrawn over a 7/30/90/180-day window; window totals row + Top-5 selling listings + Next-expected-release card + "Request withdrawal" CTA. Wallet page has a new "Open payout dashboard →" button.
- **Dropship earnings preview** (`ListingDetail.jsx` — `DropshipImportButton`) — the Import & resell dialog now fetches public settings to show: original seller price, your markup, buyer pays, minus platform fee %, minus paid-to-original-seller, and a highlighted "You earn per sale" with margin % and a "frozen until delivery" note. Quick presets 10/20/35/50 %, live max-markup cap validation, and negative-earning guard-rail that disables the Import button.

### Feb 2026 — Wallet Freeze/Release + Admin-Set Delivery ETA
- **User model**: added `wallet_frozen_balance` alongside `wallet_balance` (available).
- **Settings**: new `delivery_days_estimate` (default 7) and `delivery_auto_release_days` (default 14), both admin-controlled via `PUT /api/admin/settings`.
- **Order model**: new `estimated_delivery_at` (order.created_at + delivery_days_estimate), `delivery_confirmed_at`, `funds_released`.
- **credit_wallet(frozen=True)** routes sale + dropship earnings to `wallet_frozen_balance`. Affiliate + referral commissions release immediately (they're marketing rewards). New tx types: `sale_frozen`, `sale_released`, `dropship_frozen`, `dropship_released`.
- **`POST /api/orders/{id}/confirm-delivery`** (buyer or admin) — flips order to `delivered`, sets `funds_released=true`, and moves frozen amount into the seller's (and dropship source's) available balance. Idempotent.
- **`GET /api/settings/public`** — non-sensitive settings for buyer UI (delivery days + auto-release days).
- **Frontend**:
  - **Wallet page** — Frozen chip on the balance card, new tx-type labels (Sale (frozen), Sale released, Dropship (frozen), Dropship released, Refund).
  - **Profile → Purchases** — each order shows a live "Arrives in ~N days" chip + a green "Confirm delivery" button that releases funds.
  - **Profile → Sales** — each sale shows "Funds frozen · releases on delivery" until confirmed, then "Paid out".
  - **Checkout** — green ETA block "Arrives in ~7 days · by Aug 21" with note that seller earnings stay frozen until confirmation.
  - **Admin → Settings** — new "Delivery & fund release" section with two inputs (delivery days + auto-release days).
- Verified end-to-end via `testing_agent_v3_fork` iteration_17: 9/9 backend pytest + 5/5 frontend acceptance — zero action items.


- **Dictionary expansion**: `LanguageContext.jsx` grew from ~40 → 180+ keys across 4 locales (EN / ES / FR / JA) covering the entire buyer journey — greeting, hero CTAs, Flash Deals, Trending, Just Listed, For You, Trust strip, Request banner, Cart order summary, Checkout shipping + payment forms + success screen, ListingDetail CTAs (Buy/Add-to-cart/Save/Message seller), Description, Bundle strip, and SimilarItems.
- **Pages migrated**: `Home.jsx`, `Cart.jsx`, `Checkout.jsx`, `ListingDetail.jsx`, `SimilarItems.jsx` now consume `useLang().t()` for every visible string; data-driven content (product titles/prices/user names) stays as-is.
- **Persistence**: language stored in localStorage (`mercari_lang`) and applied to `<html lang>` for a11y.
- Verified via `testing_agent_v3_fork` iteration_16 — all 4 languages work across Home/Cart/Checkout/ListingDetail. Post-report fix applied to `SimilarItems.jsx` (kicker/title/subtitle now translated).

### Feb 2026 — Header Superpowers: Voice/Image Search + Command Palette + Multi-Currency + Multi-Language + Compact Sticky
- **Global 3-stroke nav** (`GlobalNavMenu.jsx`) — persistent top-left button opens a slide-out panel listing every main page (Home, Browse, Cart, Favorites, Sell, Messages, Wallet, Disputes, My Store, Analytics, Referrals, Affiliate, Verification, Profile, Admin).
- **Command Palette ⌘K** (`CommandPalette.jsx`) — global keyboard shortcut opens a full-screen search overlay with arrow-key navigable rows: main pages + live product suggestions from `/search/suggest`. Header has a dedicated ⌘K button too.
- **Voice + Image + Live counter + Vibe hint** (`SearchAutocomplete.jsx`) — mic uses `window.SpeechRecognition`, camera uploads a photo to `POST /api/search/image` (Emergent LLM vision → keywords + category → listings query with category-only fallback), a debounced "X matches" live counter appears while typing, and a rotating vibe hint chip cycles through 6 vibes when idle.
- **Mini-cart flyout** (`MiniCart.jsx`) — hover the cart icon for a preview panel with up to 6 items, remove, subtotal in the selected currency, View cart / Checkout CTAs.
- **Multi-currency** (`CurrencyContext.jsx`, `GET /api/currency/rates`) — USD/EUR/GBP/JPY/INR/CAD picker in the top strip; `format()` reformats prices site-wide via Intl.NumberFormat. Rates from mocked backend endpoint. Persisted in localStorage.
- **Multi-language** (`LanguageContext.jsx`) — EN / ES / FR / JA dictionary. Persisted in localStorage.
- **Compact sticky header** — scroll past ~200px collapses top strip + category ribbon, shrinks main bar `h-20 → h-14`, adds subtle shadow (40px hysteresis prevents flicker).
- **LiveSyncBadge countdown** — dynamic `Xh Ym Ns ago · next in Ns` that ticks every second.


- **Global 3-stroke nav** (`GlobalNavMenu.jsx`) — persistent top-left button opens a slide-out panel listing every main page (Home, Browse, Cart, Favorites, Sell, Messages, Wallet, Disputes, My Store, Analytics, Referrals, Affiliate, Verification, Profile, Admin).
- **Command Palette ⌘K** (`CommandPalette.jsx`) — global keyboard shortcut opens a full-screen search overlay with arrow-key navigable rows: main pages + live product suggestions from `/search/suggest`. Header has a dedicated ⌘K button (`header-cp-btn`) too.
- **Voice + Image + Live counter + Vibe hint** (`SearchAutocomplete.jsx`) — mic uses `window.SpeechRecognition`, camera uploads a photo to new `POST /api/search/image` (Emergent LLM key vision → keywords + category → listings query, with category-only fallback), a debounced "X matches" live counter appears while typing, and a rotating vibe hint chip cycles through 6 vibes when idle.
- **Mini-cart flyout** (`MiniCart.jsx`) — hovering the cart icon opens a preview panel with up to 6 items, remove buttons, running subtotal in the selected currency, and View cart / Checkout CTAs.
- **Multi-currency** (`CurrencyContext.jsx`, `CurrencyPicker.jsx`, `GET /api/currency/rates`) — USD/EUR/GBP/JPY/INR/CAD picker in the top strip; `format()` helper reformats prices site-wide via Intl.NumberFormat. Rates from mocked backend endpoint (documented; wire to ExchangeRate API for live rates). Preference persisted in localStorage.
- **Multi-language** (`LanguageContext.jsx`, `LanguagePicker.jsx`) — EN / ES / FR / JA dictionary covering header, nav, cart, and topstrip strings. Preference persisted in localStorage and applied to `<html lang>` (great for a11y). Full-app localization is a follow-up.
- **Compact sticky header** — scroll past ~200px collapses the top strip + category ribbon to zero height, shrinks the main bar from `h-20` to `h-14`, and adds subtle shadow. Restores on scroll-to-top with a 40px hysteresis gap so it doesn't flicker.
- **LiveSyncBadge countdown** — replaces the static "420m ago" text with a live-updating `Xh Ym Ns ago` + `next in Ns` countdown that resets after each sync.
- Verified via `testing_agent_v3_fork` iteration_15: **backend 3/3 pytest, frontend all assertions pass, zero action items**.

### Feb 2026 — You May Also Like + Vibe Search (AI)
- **You may also like** (`SimilarItems.jsx`, `GET /api/listings/{id}/similar`) — new horizontal scroll strip on every product detail page. Backend returns up to 12 active listings in the same category with prices in a ±40% band around the source (min $5 spread), sorted by views + likes; falls back to popular items in the same category when the tight band is thin. Left/right scroll controls, aspect-square cards, dark-mode compatible. Rendered above the existing "Complete the look" seller-bundle strip.
- **Vibe Search** (`VibeSearch.jsx`, `POST /api/search/vibe`) — LLM-powered natural-language search on the Search page behind a "Try Vibe search" toggle. Emergent LLM Key + GPT-5.4 translates a vibe into structured filters — keywords, category slugs (from the 21-cat taxonomy), brand hints, price range, and a plain-english explanation. Backend runs a 4-level graceful fallback (strict → drop price → drop keywords → category only) so results are non-empty even when the LLM suggests niche brands/terms outside our inventory. UI shows the vibe-read explanation, chip breakdown of matched categories/keywords/brands, a "broadened" badge when fallback triggers, and a grid of matching products. 6 example vibes as click-to-run chips. Tested end-to-end via `testing_agent_v3_fork` iteration_14 — 100% pass across backend (4/4 pytest) + frontend flows.

### Feb 2026 — Modern Mercari-Style Navigation + Advanced Search + Expanded Categories
- **New Header** (`Header.jsx`) faithful to mercari.com: slim top strip (marketplace, free returns, deals, Help/Login/Register), main bar with logo, Categories mega-menu button, prominent pill-shaped search bar (fills remaining space), and right-side action cluster (Sell gradient CTA, theme toggle, favorites, notifications, messages, cart, user avatar/sign-in). Category ribbon below shows all 21 categories horizontally scrollable.
- **CategoryMegaMenu** (`CategoryMegaMenu.jsx`) — hover/click dropdown with 4 quick-link chips (Trending, New arrivals, Under $25, Most loved) and a 5-column grid of all 21 categories with lucide icons + hover accents.
- **Advanced SearchAutocomplete** (`SearchAutocomplete.jsx`) — category scope selector (All / any of 21), debounced live suggestions (query tokens, brands with counts, categories from taxonomy, product items with images & prices), Recent searches persisted in localStorage (last 8), Trending queries from `/api/search/trending`, Escape/outside-click closes.
- **Category expansion (12 → 21)** — Added: Shoes, Bags & Accessories, Jewelry & Watches, Pet Supplies, Automotive, Garden & Outdoor, Musical Instruments, Office & Craft, Collectibles. Backfilled into live DB and the `/seed` defaults.
- **Backend endpoints**:
  - `/api/search/suggest` now returns `{items, queries, brands (with counts), categories (from taxonomy)}`.
  - `/api/search/facets` new — aggregated brand counts, condition counts, price bounds, total for current filter shape.
  - `/api/search/trending` new — top brand queries from most-viewed active listings.
  - `/api/listings` & `/api/listings/count` now accept optional `brand` filter.
- **MobileDrawer** revamped with a 2-column categories grid so all 21 are reachable on mobile.
- Verified via `testing_agent_v3_fork` (iteration_13.json) and playwright screenshots.


### Feb 2026 — Boost-my-score Hint + Product Detail Refresh
- **Boost my score hint** — New `BoostScoreHint` under the Trust meter (shown only when applicant is not yet fast-track eligible). Big "You're X points away from instant approval" headline, then a 2-column grid of tap-and-go actions sorted by biggest lift first — each row shows `+N` pts pill, action label, and CTA link (Verify email → `/verify`, Verify phone → `/verify`, Complete profile → `/profile`, Invite a friend → `/referrals`, Wait it out for account-age, Resolve disputes → `/disputes`). Wrapped in a soft warm-gradient panel so it feels like an offer, not a scold.
- **Product Detail refresh** — `/listing/:id` completely modernized: kicker chip category, tracking-tight extra-bold title, 4xl tabular-nums price + strikethrough + emerald "-N% off" chip, pill-shaped condition/brand/size/color badges, ship + protection info in tone-coded rounded-xl cards, Buy Now button now a warm gradient (`from-[#FF7A18] to-[#FF211F]`) with price and red-glow shadow, all secondary CTAs pill-shaped, gallery main image in rounded-2xl with subtle ring/shadow (thumbnails use ring-offset when active), gradient-avatar Seller card, "Complete the look" bundle section gets the same kicker + tracking-tight treatment. Full dark-mode support.
- **Lint**: clean across SellerApply + ListingDetail.

### Feb 2026 — Print Shipping Label + Seller Payout Preview
- **Printable Shipping Label** — New `GET /api/orders/{id}/label.svg` renders a 4×6-style SVG label with brand header band, carrier + tracking, ship-to + from blocks, deterministic barcode (from tracking hash), QR-code-style 16×16 block with corner finder patterns, and footer. Auth-gated via `Authorization: Bearer` OR `?auth=` query param so the same URL can render inline in a new tab. The existing `POST /api/orders/{id}/shipping-label` mock adapter now stamps `label_url = /api/orders/{id}/label.svg` so the "Print label" button opens a real printable page instead of a dead placeholder path. `ShippingTracker` shows a new `Print label` button (data-testid `view-label-<orderId>`) whenever a tracking number exists.
- **Seller Payout Preview** — New `PayoutPreviewCard` on `/seller/apply`, shown both in preview mode (before approval) and in the approved state. Displays weekly earnings range keyed to the applicant's trust tier (elite $800-$2,200 · trusted $400-$1,200 · new $150-$600), payout cadence (Every Monday · Direct to your bank), a two-tone fee-split bar (You keep 90% / Platform 10%), and a 3-column breakdown (midpoint sales · platform fee · your payout) using tabular-nums. Tier-specific tip line explains what unlocks the higher tier.
- **Fast-track auto-approval** (Phase 17): unchanged and verified — `POST /api/seller/apply` still auto-approves score ≥ 80 + no open disputes; low-trust flows continue to the admin queue.
- **Lint**: clean across backend + all touched frontend files.

### Feb 2026 — Seller Onboarding + Trust-Score Auto-Approval
- **Trust Score endpoint** — `GET /api/seller/trust-score` returns a 0-100 breakdown across 6 signals: email verified (25), phone verified (25), account age > 7 days (15), no open disputes (15), has referrals (10), profile complete — bio + avatar (10). Tiers: elite (≥80), trusted (≥60), new (<60). `auto_approve_eligible` requires score ≥ 80 AND no open disputes (dispute veto).
- **Fast-track auto-approval** — `POST /api/seller/apply` now checks the Trust Score first. Eligible applicants are approved on submit with `admin_notes = "Auto-approved via Trust Score (…)"`, `reviewed_by = "system:trust_score"`, user role updated to seller, and a 🎉 notification pushed. Everyone else falls into the existing admin review queue with the standard "application submitted" note.
- **Trust Score meter card** on `/seller/apply` — 4xl/5xl score, tier chip, gradient progress bar (emerald when eligible, warm brand when not), per-signal grid with earned/weight pips, "Instant approval on submit" badge when eligible, dynamic submit button copy.
- **Bug fixed by testing agent (HIGH)**: `_compute_trust_score` account-age computation was silently failing because Motor returns tz-naive datetimes while `datetime.now(timezone.utc)` is tz-aware — bare `except` hid the TypeError, capping fully-qualified users at 75/100. Fixed by normalising to UTC-aware inside the function and removing the broad except. Admin now correctly scores 55/100 with `age_earned=15`.
- **Regression preserved**: Existing email + phone verification gate, duplicate pending guard, and the admin manual approval PUT flow all unchanged. Shipping-provider adapter (mock EasyPost/Shippo) untouched.

### Feb 2026 — Cart, Checkout & Storefront Refresh
- **Cart page** — kicker chip + tracking-tight H1, item count subtitle, cart rows now rounded-2xl with warm hover-glow, tabular-nums prices, pill-shaped Checkout CTA with red glow shadow, empty state ringed with dashed border and centered CTA. Fully dark-mode ready.
- **Checkout page** — same header language, sections wrapped in rounded-2xl cards with soft shadows, payment section has emerald "Demo" pill and lock-icon tile, order summary sticky on desktop with clear divider rhythm, extra-bold total. Success screen redesigned: gradient emerald tick badge with blur-glow, warm CTA row (Share/View orders/Keep shopping), summary card with clean divider and tabular-nums amount.
- **Storefront (`/store/:slug`) rebuilt** — gradient hero (`from-[#FF7A18] via-[#FF5722] to-[#FF211F]`) with optional banner overlay and decorative blur blobs, logo circle in a rounded-2xl ringed avatar overlapping the hero, tier badge, stat pills (Sales / Followers / Since) with tone-coded icons, buyer-protection ribbon, kicker chip on the "Store listings" section, and a working sort dropdown (Newest / Price asc/desc / Most popular). Empty state polished with dashed border.
- **Lint**: clean across Cart, Checkout, StorePage.

### Feb 2026 — Modern Design Polish
- **ProductCard rebuilt**: rounded-2xl surfaces, soft-shadow → warm-glow hover lift, image zoom to 1.06 with ease-out, gradient SOLD overlay + white pill, favorite heart fades in on hover (stays red when active), extra-bold prices with tabular-nums, focus-visible ring for keyboard nav.
- **Home sections modernized**: Every major shelf/section now has a kicker chip ("CATALOG" / "WHY SHOP HERE" / "LIVE NOW" / "FRESH DROPS"), tracking-tight extra-bold H2 titles, animated "See all →" arrows that slide on hover, `mt-16 sm:mt-20` rhythm, and consistent `gap-3 sm:gap-4` grids across mobile/desktop.
- **TrustStrip redesigned**: warm-toned icon tiles with dark-mode variants (emerald/sky/orange/violet), rounded-2xl feature cards, hover-lift shadow.
- **RequestBanner redesigned**: rounded-3xl gradient panel with decorative blur blobs, glowing shadow, hover animation on primary CTA.
- **Search / All-products header**: kicker chip + tracking-tight H1, cleaner controls row.
- **Design guidelines committed**: `/app/design_guidelines.md` captures brand palette, surfaces, typography, spacing rhythm, interactions, and dark-mode rules so future work stays consistent.

### Feb 2026 — Paginated Category & Product Browsing
- **New paginated Search/Category page** — `/search` now shows all catalog products page-by-page. URL-driven state: `?category=<id>&size=24|48|96&page=N&sort=...`. Header displays "Showing X–Y of TOTAL items" and the selected category name.
- **Pagination controls** — First / Previous / smart-window page numbers (with ellipsis) / Next / Last, all with data-testids. Auto-scroll to top on page change. Any filter change resets to page 1.
- **Page-size selector** — 24 / 48 / 96 per page.
- **Backend** — `/api/listings` now clamps `limit` to `[1, 96]` and `skip` to `>=0`. New `/api/listings/count` endpoint returns the total for the same filter shape (`q`, `category_id`, price, condition, featured, seller_id, `status_filter`). Route ordered before `/listings/{listing_id}` so it doesn't collide. Filter logic extracted into `_build_listings_query` helper (single source of truth).
- **Verified**: 2,608 real Amazon products → 109 pages at 24/page. Category filter (Women) narrows to 564 items → 24 pages. Detail route still resolves correctly; page 1 vs page 2 return distinct items.
- **Bug fixed during rollout**: `parseInt(null)` returning NaN caused a 422 blank state — clamped the raw parse before checking membership.

### Feb 2026 — Real Amazon Catalog Replaces Mock Listings
- **Removed 100% of mock listings.** Deleted 1,748 seed/demo/TEST listings and replaced them with **2,611 real Amazon products** imported from the previously-completed Apify dataset (`4l18Zx7sRwgZJBbBy`, 2,694 raw items). All catalog data now originates from the connected Apify Amazon crawler — real titles (Brooks Adrenaline GTS 25, Marc Jacobs Tote Bag, Citizen watches, Lamicall accessories), real prices (up to $1,045), real breadcrumb-classified categories, real high-resolution images.
- **Disabled the seed mock-listings block.** `POST /api/seed` no longer inserts sample listings; it seeds categories, admin, and demo sellers only, and returns a note pointing to `/api/admin/sync/apify` for real product data.
- **New importer script** `/app/scripts/import_from_dataset.py <dataset_id>` — re-runs against any completed Apify dataset to re-populate the catalog without burning new Apify credits. Handles breadcrumb-to-category mapping, de-duplicates by ASIN, chunk-inserts, and updates `sync_state` for the admin dashboard.
- **Live per-category distribution**: Women 564 · Men 544 · Kids 429 · Other 360 · Electronics 211 · Beauty 208 · Toys 149 · Home 85 · Books 47 · Sports 14.

### Feb 2026 — Bug Fix: Preview showed 0 products (runaway live-simulator)
- **Root cause**: The `simulate_live_update` loop in `apify_sync.py` marked 3 random active listings as "sold" every 60s but had NO counterbalance — nothing brought sold items back to active. Over ~12 hours since the last real sync, the tick marked all 212 listings sold, so `/api/listings` returned `[]` and Home/Search rendered empty.
- **Fix**: (a) Revived all 212 sold listings back to active (one-off). (b) Rewrote `simulate_live_update` with guardrails: `ACTIVE_FLOOR=60` prevents dipping below the floor, `REVIVE_PER_TICK=5` resurrects sold items back to active on every tick BEFORE the sell pass, and the sell-3 pass only runs when active count is safely above the floor. Also cleaned 30 leftover TEST_ listings from testing agent runs.
- **Verified**: 5 consecutive ticks show a stable steady-state of `active=179`. Home page now renders the full catalog with flash deals, categories, and shelves.

### Feb 2026 — Phase 16: Apify Sync Insights (Per-Category Breakdown)
- **Live Per-Category Breakdown** — Backend `apify_sync.py` now persists `per_category` counts every 200 successful imports along with a mid-run message ("Classifying — N of M raw items imported"), so admins see live progress instead of waiting for end-of-run. Frontend replaces the old 4-column grid with a rich `CategoryBreakdownCard` featuring per-category icons, warm gradient bars sorted descending by count, percent + count on each row, a total-imported pill, dark-mode support, an empty state, and a live-refresh banner while a sync is running.
- **Bonus**: Cleared a stale `sync_running=true` flag left over from an earlier backend restart. New idle-state message shown when no sync is active.
- **Tests**: 6/6 backend pytest pass. All 4 UI states (empty+running, filled+running, filled+stopped, empty+stopped) verified by testing agent iteration_11. No P0/P1 issues.

### Feb 2026 — Phase 15: Apify Verification + Dispute Reason Exclusions
- **Apify Live Scraping Verified** — User's key `apify_api_SeSGRVh...` is wired via `APIFY_TOKEN` in `backend/.env`. Confirmed working end-to-end: SDK authenticates as user `coolish_fantail` (STARTER plan), `junglee/amazon-crawler` actor is actively running across 28 category URLs, target 5000 listings. Existing `POST /api/admin/sync/apify` and `GET /api/admin/sync/status` endpoints continue to serve real live data.
- **Dispute Reason Exclusions** — New `Settings.dispute_auto_refund_excluded_reasons: List[str]` (defaults to `["counterfeit"]`). PUT sanitizes: must be a list; unknown reasons stripped; strings/other types 400. `create_dispute` auto-refund block now checks BOTH the amount threshold AND `reason not in excluded` — excluded reasons always land in the manual queue regardless of amount. Admin UI: pill-toggle chips (`exclusion-toggle-<reason>`) inside the Disputes automation section with live count-helper text.
- **Tests**: 12/12 new backend pytest pass + 11/11 Phase 14 regression pass. Frontend flows verified by testing agent iteration_10. No P0/P1 issues.

### Feb 2026 — Phase 14: Auto-Refund Threshold + Branded PWA Icons
- **Auto-Refund Rule** — New `Settings.dispute_auto_refund_threshold` field ($). Any dispute filed on an order at-or-under the threshold auto-resolves at creation: buyer wallet credited, seller debited, order set to `cancelled`, both parties notified with "Refund issued automatically" / "Dispute auto-refunded". Threshold = 0 disables the rule. `get_settings()` now merges defaults so newly added fields never return None. New "Disputes automation" section in `/admin/settings` with numeric input + dynamic helper text.
- **Branded PWA Icons** — Generated 192×192, 512×512 PNG icons and a 32×32 favicon in `/app/frontend/public/`. Design mirrors the header logo: gradient #FF7A18 → #FF211F with a rounded-corner mask (maskable-safe), soft top-left highlight, and centered bold "M" mark with subtle drop shadow. Icons wired into `manifest.json` (`purpose: "any maskable"`) and `index.html` (`<link rel="icon">`, `apple-touch-icon` sizes). Regenerator script at `/app/scripts/generate_pwa_icons.py`.
- **Tests**: 11/11 backend pytest pass (`test_phase14_auto_refund_pwa.py`). Frontend flows verified by testing agent iteration_9. No P0/P1 issues.

### Feb 2026 — Phase 13: Warm Hero, Dispute Chat, PWA + Mobile Polish
- **Warm Hero Redesign** — New `HeroCarousel` on Home with time-of-day greeting ribbon (Good morning/afternoon/evening), ken-burns image zoom, per-slide gradient accents, decorative blur blobs, trust chips (Buyer protection / Fast delivery / Verified sellers / Loved by millions), animated Shop Now button with arrow slide, and slide dots. Auto-rotates every 5.5s and pauses on hover.
- **Dispute Chat** — New `DisputeMessage` model + endpoints `GET /api/disputes/{id}/messages` and `POST /api/disputes/{id}/messages`. Buyer, seller, and admin can all post text and up to 8 photo attachments. Auto-notifies the counterparty (or both parties for admin messages). Frontend inline `DisputeChat` on `/disputes` toggles per dispute card, polls every 6s while open. Admin has compact `AdminDisputeThread` inside `/admin/disputes`. Closed disputes disable the composer.
- **PWA + Mobile Polish** — New `manifest.json` (theme_color #FF211F, standalone display), `service-worker.js` (cache-first shell + stale-while-revalidate for cross-origin assets), viewport meta with `viewport-fit=cover`, apple-mobile-web-app tags, and SW registration in `index.html`. New responsive `MobileDrawer` in Header — slide-in from left with hamburger, cart shortcut, theme toggle, avatar, and all nav links with badge counts. Full responsive layout: header shrinks to h-16 on mobile, hero adopts 16/10 on small screens, category pills scroll horizontally.
- **Tests**: 12/12 backend pytest pass (`test_phase13_dispute_chat_pwa.py`). Frontend flows verified by testing agent iteration_8. Fixed the two flagged nits: `drawer-link-home` slug (was empty) and `hero-trust-chip-<i>` testids.

### Feb 2026 — Phase 12: Disputes Center, Featured Storefronts, Dark Mode
- **Disputes & Returns** — Buyers open disputes on paid/shipped/delivered orders with reason, description and up to 8 photo evidence uploads. Endpoints: `POST /api/disputes`, `GET /api/disputes/mine`, `GET /api/disputes/{id}`, admin `GET /api/admin/disputes?status=…` and `POST /api/admin/disputes/{id}/resolve` with actions refund/reject/review. Refund credits buyer wallet by order amount, debits seller by their earnings, cancels the order, and notifies both parties. New `/disputes` page for buyers (Filed by me / Against my sales tabs) and `/admin/disputes` queue for admins with resolution + notes fields.
- **Featured Storefronts Strip** — New public `GET /api/stores-featured` (defined in Phase 11 backend) is now surfaced on Home as a horizontal carousel of storefront cards with banner, tier badge (Gold/Silver/Bronze), sales count, and click-through to store page. Order controlled by admin drag-and-drop from Phase 11.
- **Light/Dark Theme Toggle** — New `ThemeContext` with class-based Tailwind dark mode. Sun/Moon toggle button in header (visible on both mobile and desktop) persists selection to `localStorage['mercari-theme']`, respects `prefers-color-scheme` on first load. Full dark variants across Header, category pills, App shell, Home hero backdrop, Featured Stores strip, Disputes page, and Admin Disputes queue. Mercari orange/red accents preserved in both themes.
- **Backend hardening**: `Notification.type` widened from Literal to `str` with a `NOTIFICATION_TYPES` allow-list constant so new notify() types don't 500. Refund seller-debit fix: handles `seller_earnings == 0.0` correctly (no longer falls back to full amount for legitimate zero-earning sellers).
- **Tests**: 18/18 backend pytest pass (`/app/backend/tests/test_phase12_disputes_featured.py`). Frontend flows verified by testing agent iteration_7.

### Feb 2026 — Phase 11: Sortable Storefronts + Weekly Recap Card
- **Sortable Storefronts (Admin)** — `Admin.jsx > StoresMgr` rewritten with `@hello-pangea/dnd`. Drag handle on each row, live optimistic reorder, "Save order" button gated by dirty state. Persists via new `POST /api/admin/stores/reorder` which writes `featured_rank` on every store. `GET /api/admin/stores` and the new public `GET /api/stores-featured` both sort by `featured_rank` ascending so top-of-list shows first everywhere.
- **Weekly Recap Card (Seller)** — new `WeeklyRecapCard` on `StoreAnalytics.jsx` (route `/store/analytics`) shows last week's earnings, orders count, top-selling product (linked), delta vs current week (+/- badge), and a personalized suggestion. Data comes from `weekly_recap` block already returned by `GET /api/seller/dashboard`. Empty state renders when no last-week sales.
- **Tests**: 13/13 backend pytest pass (`/app/backend/tests/test_phase11_sortable_stores_recap.py`). Frontend flows verified by testing agent (iteration_6).

### Feb 2026 — Phase 10: DnD Shelves, Digest Modal, Goal Milestones
- **Drag-and-Drop Shelves** — swapped arrow controls for full drag-and-drop via `@hello-pangea/dnd`. Rows highlight on drag, "Save order" button disables until dirty, then persists via `POST /api/admin/shelves/reorder`.
- **Digest Preview Modal + Opt-out** — new `GET /api/wishlist-digest/preview` returns the user's opt-in flag + up-to-20 recent price drops + delivery cadence. `PUT /api/wishlist-digest/opt` toggles subscription. Users see a `DigestCard` on their profile with a Switch (auto-saves) and a Preview button that opens a full email-style modal with product thumbnails + Unsubscribe button. `wishlist_digest_loop` now respects `user.weekly_digest_opt_in`.
- **Custom Goal Milestones** — dashboard fires escalating confetti bursts at 25/50/75/100% weekly progress, staggered by 400ms, with intensity scaled by milestone. ISO-week keyed localStorage tracks which milestones already celebrated so each fires exactly once per week.

### Feb 2026 — Phase 9: Typography, Shelf CMS UI, Digest, Celebrations
- **Geometric Sans-Serif Typography** — Poppins + DM Sans (Google Fonts) loaded via `public/index.html`; global `body` + `h1-h6` rules in `index.css` with `letter-spacing: -0.015em` on headings for a modern editorial feel.
- **Shelf Admin Screen** (`AdminShelves.jsx`) — new "Homepage shelves" tab under Admin. Editable title inline (blur to save), limit selector, toggle switch (auto-saves), up/down arrows for reorder, "Save order" button posts the final order to `POST /api/admin/shelves/reorder`.
- **Wishlist Digest Email (MOCKED Resend)** — new `wishlist_digest_loop` runs every `WISHLIST_DIGEST_INTERVAL_SEC` (default 6h in dev). For each user with favorites, gathers listings whose `price_drop_at` is within 7 days and logs a mock Resend email (`db.email_log`) + creates an in-app notification linking to `/favorites`.
- **Goal Celebrations** — When the seller dashboard sees `weekly.progress_pct >= 100`, it fires a `canvas-confetti` burst and shows a green "🎉 Goal hit!" banner above the hero. Uses ISO-week keyed localStorage so it only fires once per week.

### Feb 2026 — Phase 8: Wishlist toast, Shelf CMS, Seller goals
- **Wishlist Price Toast** — `Listing` model gains `price_drop_at` + `previous_price`. `PUT /api/listings/{id}` stamps both when the price drops 5%+ and notifies every favoriting user. `ProductCard.jsx` shows a pulsing green **-N%** badge (with strike-through of the old price) for 7 days after the drop.
- **Shelf A/B Ordering** (Admin CMS) — moved shelf definitions from hardcoded to `db.shelves` collection with `enabled`, `order`, `title`, `subtitle`, `category_slugs`, `price_lte`, `sort_by`, `limit`. New endpoints: `GET/PUT /api/admin/shelves/{id}`, `POST /api/admin/shelves/reorder`. Public `GET /api/shelves` now respects the enabled+order fields, with auto-seeding on first request.
- **Seller Weekly Goal + Progress Ring** — `User` model gains `weekly_earnings_goal`. New `PUT /api/seller/goal` sets it; `GET /api/seller/dashboard` now returns a `weekly: {goal, earned, progress_pct}` block. `StoreAnalytics.jsx` renders an SVG progress ring in the hero banner — click the amount to edit the goal inline.
- **Refactor step 3** — `routers/discovery.py` now hosts `/shelves`, `/seller/dashboard`, `/seller/goal`, and the admin shelf CRUD.

### Feb 2026 — Phase 7: Wishlist alerts, category shelves, seller dashboard redesign
- **Buyer Wishlist Alerts** — `PUT /api/listings/{id}` now compares old vs new price; if the drop is 5% or more, every user who favorited the listing receives a `notify()` record with the new/old price. The existing global `BuyerProgressToast` surfaces it in-app instantly.
- **Home Category Deep-Dive** — new `GET /api/shelves` endpoint (via `routers/discovery.py`) returns 5 curated shelves: Fashion of the day, Tech under $50, Home essentials, Beauty buzz, For the kids. Home renders a "Category Shelves" strip below Trust with 8 items per row and per-shelf "See all" deep links.
- **Seller Dashboard Redesign** — new `GET /api/seller/dashboard` endpoint returns a 30-day earnings series, today/30d totals, wallet + pending payout, listings breakdown (active/sold/flash), engagement (views/likes), and 5 most-recent orders. `StoreAnalytics.jsx` now shows a gradient orange-red hero banner with 4 in-banner metrics, a live SVG sparkline chart (net of platform fees, no chart library), 4 tinted stat cards, Latest orders panel with product thumbnails, plus a Pro tips + Cash out side rail.
- **Refactor step 2** — added `routers/discovery.py` (shelves + seller dashboard) alongside `routers/search.py`. `deps.py` gains lazy JWT secret loading (fix: prior tokens were rejected due to import-order race with `.env`).

### Feb 2026 — Phase 6: Discovery, Personalisation, Refactor step 1
- **Recently Viewed row** on Home for logged-in users. Backend: `POST /api/recently-viewed/{id}` (called from `ListingDetail.jsx` on every view, keeps most-recent 24 per user) and `GET /api/recently-viewed`. Home shows a "Pick up where you left off" strip above the hero.
- **Smart Bundles** — new `GET /api/listings/{id}/bundle` returns up to 6 other active listings from the same seller. `ListingDetail.jsx` renders a "Complete the look" row at the bottom.
- **Push On Deal Drop** — `rotate_flash_deals()` now creates a `notify()` record for every user who has favorited any listing newly promoted into the day's Flash Deals pool. The existing `BuyerProgressToast` provider surfaces the notification through the app-wide toast.
- **Verified Seller Storefront Boost** — `ProductCard.jsx` fetches the seller's `/users/{id}/public` snapshot (cached in `sessionStorage`) and, if approved, renders a small gold-gradient shield in front of the title on every card in Trending / Flash Deals / For You / Recently Viewed grids.
- **Refactor step 1** — created `/app/backend/routers/` package with `deps.py` (lazy `get_db`, `get_current_user`, `require_admin`, `now_utc`) and extracted the newest search+recommendations endpoints (`/search/suggest`, `/for-you`, `/recently-viewed`, `/listings/{id}/bundle`) into `routers/search.py`. Server.py shrank by ~120 lines. Pattern is established for the remaining router extractions (auth, listings, seller, verify, stripe, ai, shipping) — each future extraction just imports from `routers.deps`.

### Feb 2026 — Phase 5: Search, Personalization, Delight
- **Search Suggestions** — new `GET /api/search/suggest?q=` endpoint returns `{items, queries}`. `SearchAutocomplete.jsx` renders a debounced dropdown under the header search bar with product rows (image + title + brand + price) plus brand/category quick-chips and a "See all results →" footer.
- **Personal Flash Feed** — new `GET /api/for-you` endpoint returns listings scored against the user's favourites + purchase history (category + brand match) with a graceful trending fallback for cold-start users. Home page renders a "For You" row under Flash Deals with a Sparkles header.
- **Enhance Before Publish** — `Sell.jsx` detects raw (non-enhanced) photos on submit and shows a modal offering "Enhance all" (loops each photo through `POST /api/ai/photo-enhance` — Nano Banana). Users can also "Skip & publish" if they prefer originals.
- **Sold-Out Confetti + Share** — `Checkout.jsx` fires a two-cannon confetti burst using `canvas-confetti` on order success, plus a "Share your win" button that uses the Web Share API (with clipboard fallback).
- **Testing**: 19/19 Phase 5 backend tests pass (`/app/backend/tests/test_phase5_search_foryou.py`).

### Feb 2026 — Phase 4: Nano Banana + Flash Deals + Live buyer toast
- **AI Photo Cleanup** (`POST /api/ai/photo-enhance`) — one-click background removal & studio polish via Nano Banana (`gemini-3.1-flash-image-preview`) using Emergent LLM Key. Accepts `file_id | image_base64 | image_url` + optional `prompt`. Enhanced image is saved to Emergent object storage under a new file id. Sellers see a small orange wand button on every photo in `Sell.jsx`.
- **Live Flash Deals** — 10 random `status=active` listings become flash deals daily. `is_flash_deal`, `flash_deal_ends_at` (next midnight UTC), `flash_deal_discount_pct` (20-74%). Endpoints: `GET /api/flash-deals`, `POST /api/admin/flash-deals/rotate`. Background `flash_deals_rotation_loop()` refills the pool at boot and after each midnight UTC. Home `FlashDeals` component now uses this and shows a real ETA countdown.
- **Buyer Progress Toast** (`BuyerProgressToast.jsx`) — a global provider mounted at App root that polls `/api/notifications` every 30s for shipping-update notifications and fires a floating toast + "Track →" link when a NEW status change happens. Uses localStorage to avoid replaying on page reloads.
- **Bulk Import Ready** — new Home + Trending grid render Apify-imported items correctly. Apify actor still running in background (long-running scrape across 28 categories).
- **Testing**: 18/18 Phase 4 backend tests pass (`/app/backend/tests/test_phase4_photo_enhance_flash_deals.py`).

### Feb 2026 — Phase 3: Design refresh + live shipping + adapter pattern
- **Landing page redesign** matching Mercari Global mockups: dark top strip, gradient orange "M" logo + "Mercari Global · Smart Ecommerce Platform" wordmark, big rounded search bar with orange button, category pills strip, auto-rotating hero carousel, Flash Deals grid (FLASH -%, stock bar, ETA), "Why millions trust us" pastel card row, "Can't Find Your Product?" gradient CTA, feature cards, dark footer with Mercari Global branding.
- **Trending sort** (`GET /api/listings?sort=trending`) — views_count desc, likes_count desc, created_at desc.
- **Shipping provider adapter** (`/app/backend/shipping_providers.py`) — pluggable via `SHIPPING_PROVIDER=mock|easypost|shippo`. EasyPost/Shippo stubs raise NotImplementedError until keys are provided.
- **Persisted shipping events** on `orders.shipping_events` array. Backfill on read for legacy orders.
- **Auto-advance background loop** (`shipping_progress_loop`) runs every 30s, advances mock orders per `SHIPPING_MOCK_FAST` (default true → ~60s to picked_up, ~2m to in_transit, ~5m to out_for_delivery, ~8m to delivered), and notifies buyer on each transition.
- **Manual advance endpoint** `POST /api/orders/{id}/shipping-advance` (seller/admin) — either advance one stage or jump to `to_status`. Emits buyer notification.
- **Edit Listing page** at `/listing/:id/edit` (`EditListing.jsx`) — pick any existing photo, regenerate title/description/category/condition/price via the AI listing assistant (`/api/ai/listing-suggest` with `image_url`), or edit manually then `PUT /api/listings/{id}`.
- **ShippingTracker** now supports `canAdvance` prop → shows "Mark next stage →" button for sellers.
- **Header/Footer** rebuilt: sticky top strip, category pills row, user drop-down (Verification/Wallet/Referrals/Affiliate/Store analytics/Sell/Admin), notifications badge, cart, favorites.
- **Testing**: 15/15 Phase 3 backend tests pass (`/app/backend/tests/test_phase3_shipping_advance_trending.py`).

### Feb 2026 — Phase 2: Trust Badges, AI, Uploads, Shipping
- **Verification badges** (`VerificationBadges.jsx`) shown on Profile, Listing detail (seller block), Store page — pills for verified email / phone / approved seller. Public snapshot endpoint `GET /api/users/{id}/public` powers cross-user display without exposing sensitive fields.
- **AI Listing Assistant** — `POST /api/ai/listing-suggest` with `{image_base64|image_url, hints?}` calls GPT-5.4 vision via Emergent LLM Key and returns structured JSON (title, description, category_slug + category_id, condition, brand, color, size, suggested_price_usd). Wired into `Sell.jsx` — "AI-fill from photo" button auto-populates form fields.
- **File Upload / Object Storage** — `POST /api/upload` (multipart) + `GET /api/files/{id}?auth=…` for authenticated retrieval. Storage backed by Emergent object storage (`init_storage`, `put_object`, `get_object`). Files stored at `mercari-clone/uploads/{user_id}/{uuid}.{ext}`. Accepts JPG/PNG/WEBP/GIF/PDF up to 12MB. `db.files` collection tracks metadata + soft-delete flag.
- **ID Document Upload** replaces the textarea placeholder in `SellerApply.jsx`. Applications now persist `id_document_file_id` referencing the uploaded document.
- **Shipping Labels (MOCKED)** — `POST /api/orders/{id}/shipping-label` mints a MOCK tracking number + label URL + estimated delivery via random carrier (USPS/UPS/FedEx). `GET /api/orders/{id}/tracking` returns a progressive events timeline (label_created → picked_up → in_transit → out_for_delivery → delivered) computed from order age. `Order` model extended with `tracking_number`, `carrier`, `label_url`, `shipping_status`, `estimated_delivery`. `ShippingTracker.jsx` component wired into Profile → Purchases (buyer view) and Sales (seller view with "Buy label" CTA).
- **Apify sync**: Amazon 5000-item scrape re-triggered from admin API (runs in the background; actor progressing through 28 categories).
- **Testing**: 32/32 Phase 2 backend tests pass (`/app/backend/tests/test_phase2_verify_upload_ai_shipping.py`).

### Feb 2026 — Phase 1: Trust & Payments (Week-1, MOCKED)
- **User model extended**: `email_verified`, `phone`, `phone_verified`, `seller_status`, `stripe_account_id`, `stripe_status`.
- **Email verification** (`POST /api/verify/email/send`, `/confirm`) — magic-link token stored in DB; returned in response with `dev_mock:true`.
- **Phone OTP verification** (`POST /api/verify/phone/send`, `/confirm`) — 6-digit code, 10-min TTL, 5-attempt limit; returned in response with `dev_mock:true`.
- **Seller Application** (`POST /api/seller/apply`, `GET /api/seller/application`) — requires both verifications; tax ID stored as `****XXXX`; sets `user.seller_status=pending`.
- **Mock Stripe Connect** (`POST /api/stripe/connect/onboard`, `GET /api/stripe/connect/status`) — generates fake `acct_mock_*` ID; sets `stripe_status=active` immediately.
- **Admin queue** (`GET /api/admin/seller-applications`, `PUT /api/admin/seller-applications/{id}`) — approve/reject with `admin_notes`; notifies the user.
- **Listing gate**: `POST /api/listings` returns 403 unless `seller_status=approved` (admins bypass). Frontend Sell page redirects unapproved users to `/verify`.
- **Admin stats** now include `pending_seller_apps`.
- Frontend: `/verify` (Verification.jsx), `/seller/apply` (SellerApply.jsx), Admin → Seller applications tab.
- Mock tokens/codes auto-fill in frontend + shown in toast for dev visibility.
- **Testing**: 32/32 backend tests pass (`/app/backend/tests/test_phase1_trust_payments.py`). Frontend flows verified via Playwright.

### Earlier work (previous sessions)
- Full MVP: React + FastAPI + MongoDB, JWT auth, buyer/seller flows, cart, favorites, checkout.
- Admin Panel (users, listings, orders, categories, settings, withdrawals, stores, apify-sync).
- Storefronts with verified tiers.
- Affiliate marketing (5% commission tracking).
- 3-level Referral MLM system.
- Reviews & Ratings, In-app Chat, Notifications.
- Apify integration (`junglee/amazon-crawler`), weekly auto-sync.

---

## Roadmap (P0 → P2)

### P0 — Phase 1 Week 2 (Trust polish)
- **Verification badges** on user/store cards & listing pages (Verified email/phone/seller pills).
- **Resend cool-down** for verification codes (60s throttle).
- **Rate-limit** verification send endpoints (per user/IP).
- **ID document upload** UI (S3-like storage or Emergent object storage — replace `id_document_note`).

### P1 — Phase 2: Shipping Integrations
- EasyPost or Shippo API integration (real or mocked as needed).
- Multi-mode shipping (label purchase, tracking URL, delivery status webhooks).
- Live tracking on order detail page.

### P1 — Phase 3: AI Listing Assistant
- Photo upload → GPT-5.6 (via Emergent LLM Key) → auto-generate title, description, suggested category & price.
- Optional Nano Banana image cleanup / background removal.

### P2 — Phase 4: Drop-shipping enhancements
- Print-on-demand supplier connectors.
- Fulfilled-by-Platform (FBP) / warehouse pick-pack-ship simulation.

### P2 — Phase 5: Disputes & Returns
- Escrow-based dispute center, one-click returns, refund flow.

### P2 — Phase 6: Growth & Discovery
- Vector search (semantic).
- SEO-friendly URLs (`/item/{slug}` alongside `/listing/{id}`).
- Email marketing drip campaigns (via Resend when real key is ready).

### P2 — Phase 7: Mobile PWA
- Installable manifest, service worker, offline shell.

### Refactoring / Debt
- `server.py` is 1964 lines — split into routers: `auth`, `listings`, `orders`, `seller`, `verify`, `stripe`, `admin`, `sync`.
- Move `import secrets, random` to top of `server.py`.
- Replace raw `dict` bodies (admin update endpoints) with Pydantic models.
- Normalize `expires_at` on write (always tz-aware) so read-side branches disappear.

---

## Testing Data / Credentials
See `/app/memory/test_credentials.md`.

## Mocked Services (dev)
- **Resend** (email delivery) — MOCKED. Tokens returned in API response.
- **Twilio SMS** (OTP) — MOCKED. 6-digit codes returned in API response.
- **Stripe Connect** (payouts) — MOCKED. Fake `acct_mock_*` IDs, instant-active status.
- **EasyPost / Shippo** (shipping labels) — MOCKED. `MOCK...` tracking numbers, synthetic events timeline based on order age.

## Real Integrations
- **Emergent LLM Key** (`gpt-5.4` vision) — AI listing assistant.
- **Emergent Object Storage** — file uploads for seller ID documents and (future) listing images.
- **Apify** (`junglee/amazon-crawler`) — real Amazon scraping, weekly auto-sync.
