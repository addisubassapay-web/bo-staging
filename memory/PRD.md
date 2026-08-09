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
