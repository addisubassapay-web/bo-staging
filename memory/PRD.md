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
