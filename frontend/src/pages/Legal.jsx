import React from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, ArrowLeft } from "lucide-react";

/**
 * Legal — a single component that renders either Terms of Service or
 * Privacy Policy based on the `mode` prop. Copy is deliberately concise,
 * plain-English, and references the new production domain
 * `blueocean.com` + support mailbox `support@blueocean.com`.
 * Nothing here is legal advice; the operator should still have a lawyer
 * review before launch.
 */
const CONTACT = {
  brand: "BlueOcean",
  domain: "blueocean.com",
  email: "support@blueocean.com",
};

const TERMS_SECTIONS = [
  { h: "1. Acceptance", p: `By accessing ${CONTACT.brand} at ${CONTACT.domain} you agree to these Terms. If you don't agree, please stop using the service.` },
  { h: "2. Accounts", p: "You must provide accurate information and keep your credentials secure. You're responsible for everything that happens under your account." },
  { h: "3. Selling", p: `Sellers must only list items they legally own or are authorised to resell. Listings that infringe intellectual property, safety regulations, or ${CONTACT.brand}'s prohibited-items policy will be removed and the seller may be suspended.` },
  { h: "4. Escrow & payouts", p: `${CONTACT.brand} holds buyer payments in escrow until delivery is confirmed (or auto-confirmed on the platform's release schedule). Payout methods and cadence are shown at the point of sale. A platform fee applies to every completed sale — the current rate is shown in your seller dashboard.` },
  { h: "5. Prohibited conduct", p: "No fraud, no counterfeit goods, no illegal items, no harassment. We reserve the right to suspend or terminate accounts that abuse the service or endanger buyers." },
  { h: "6. Disputes", p: `Buyers and sellers should attempt to resolve issues directly first. If that fails, open a dispute through the /disputes page and our team will mediate. Chargebacks bypass this flow and may result in account restrictions.` },
  { h: "7. Termination", p: "You may close your account at any time. We may suspend or terminate accounts that breach these Terms, defraud buyers, or violate applicable law." },
  { h: "8. Liability", p: `${CONTACT.brand} is a marketplace, not the seller of record for most items. To the maximum extent permitted by law, our aggregate liability is limited to the fees you've paid us in the 12 months preceding the claim.` },
  { h: "9. Changes", p: "We may update these Terms. Material changes will be announced at least 14 days before they take effect. Continued use after the effective date means acceptance." },
  { h: "10. Contact", p: `Questions? Email us at ${CONTACT.email}.` },
];

const PRIVACY_SECTIONS = [
  { h: "1. What we collect", p: "Account data (email, username, hashed password), verification data (email/phone OTPs, seller application details), transactional data (orders, payments, escrow events), and technical data (IP, device, cookies) used to keep the service secure." },
  { h: "2. How we use it", p: "To operate the marketplace, verify identities, process payments, prevent fraud, send transactional email (order updates, OTPs, password resets), and — with your opt-in — send occasional product news." },
  { h: "3. Who we share it with", p: `Payment processors, shipping carriers (only what the label needs), our email provider (Hostinger — for messages from ${CONTACT.email}), and law enforcement when legally compelled. We do not sell personal data.` },
  { h: "4. Storage & retention", p: "Data is stored on MongoDB Atlas (cloud). Uploaded images are hosted on Cloudflare R2. Account data is retained for as long as your account is active plus a short compliance window; anonymised transaction records may be kept longer for tax/audit purposes." },
  { h: "5. Security", p: "Passwords are hashed with bcrypt. OTPs are SHA-256 hashed with a 10-minute TTL. Sensitive endpoints require a fresh OTP token. We use TLS on every request and rotate database credentials on suspicion of exposure." },
  { h: "6. Your rights", p: "You can access, correct, or delete your account data at any time from /profile, or email us. EU/UK users have full GDPR rights (access, rectification, erasure, portability, objection); California users have CCPA rights. We honour every valid request within 30 days." },
  { h: "7. Cookies & localStorage", p: "We use localStorage to keep you signed in (JWT), remember your preferred currency/language/theme, and cache exchange rates. We do not use third-party ad-tracking cookies." },
  { h: "8. Children", p: "The service is intended for users 18+. We do not knowingly collect data from anyone under 13." },
  { h: "9. Changes", p: "Material changes will be announced at least 14 days ahead. The 'last updated' date at the bottom of this page always reflects the current version." },
  { h: "10. Contact", p: `Privacy questions? Email ${CONTACT.email} with subject "Privacy request".` },
];

const Legal = ({ mode = "terms" }) => {
  const isTerms = mode === "terms";
  const title = isTerms ? "Terms of Service" : "Privacy Policy";
  const sections = isTerms ? TERMS_SECTIONS : PRIVACY_SECTIONS;
  const lastUpdated = "February 27, 2026";

  return (
    <div className="max-w-3xl mx-auto px-4 py-10" data-testid={`legal-${mode}-page`}>
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-[#DC2626] mb-6">
        <ArrowLeft className="h-4 w-4" /> Back to marketplace
      </Link>
      <div className="flex items-center gap-3">
        <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-[#5459E8] to-[#818CF8] text-white grid place-items-center">
          <ShieldCheck className="h-6 w-6" />
        </div>
        <div>
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-[#5459E8]">Legal</div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">
            {title}
          </h1>
        </div>
      </div>
      <p className="mt-4 text-sm text-neutral-500 dark:text-neutral-400">
        {CONTACT.brand} · Last updated {lastUpdated}
      </p>
      <div className="mt-8 space-y-6 text-neutral-800 dark:text-neutral-200 leading-relaxed">
        {sections.map((s) => (
          <section key={s.h} data-testid={`legal-section-${s.h.split(".")[0]}`}>
            <h2 className="text-lg font-bold text-neutral-900 dark:text-neutral-100">{s.h}</h2>
            <p className="mt-1 text-sm sm:text-base">{s.p}</p>
          </section>
        ))}
      </div>
      <div className="mt-10 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-5 text-sm text-neutral-600 dark:text-neutral-300">
        Need to reach us? Email{" "}
        <a href={`mailto:${CONTACT.email}`} className="text-[#DC2626] font-semibold underline" data-testid="legal-contact-email">
          {CONTACT.email}
        </a>.
      </div>
    </div>
  );
};

export const Terms = () => <Legal mode="terms" />;
export const Privacy = () => <Legal mode="privacy" />;
export default Legal;
