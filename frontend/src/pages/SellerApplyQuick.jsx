import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { errorText } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import {
  Zap,
  ShieldCheck,
  Store as StoreIcon,
  Sparkles,
  Truck,
  ArrowRight,
  CheckCircle2,
  Bitcoin,
  Banknote,
  CreditCard,
  Wallet as WalletIcon,
  Coins,
  Mail,
  RefreshCw,
} from "lucide-react";
import CryptoIcon from "@/components/ui/CryptoIcon";

/**
 * SellerApplyQuick — a one-step, streamlined seller application with
 * inline email-OTP verification and 5 payout methods.
 */
const REQUIRED_RULES = {
  legal_name: {
    label: "Legal name",
    validate: (v) => (v.trim().length >= 2 ? null : "Enter your full legal name"),
  },
  city: {
    label: "City",
    validate: (v) => (v.trim().length >= 2 ? null : "Enter your city"),
  },
  postal_code: {
    label: "Postal / ZIP",
    validate: (v) => (v.trim().length >= 3 ? null : "Enter a valid postal code"),
  },
  country: {
    label: "Country",
    validate: (v) => (/^[A-Za-z]{2}$/.test(v.trim()) ? null : "Two-letter code (US, GB, IN…)"),
  },
};

const PAYOUT_METHODS = [
  {
    key: "crypto",
    label: "Crypto",
    tagline: "Recommended · fast & secure",
    icon: Bitcoin,
    tone: "text-amber-500",
    coins: ["BTC", "ETH", "USDT"],
    recommended: true,
    hint: "Instant settlement in BTC.",
  },
  {
    key: "bank_transfer",
    label: "Bank transfer",
    tagline: "Traditional account",
    icon: Banknote,
    tone: "text-sky-600",
    hint: "1–3 business days.",
  },
  {
    key: "card",
    label: "Credit / Debit",
    tagline: "Direct-to-card",
    icon: CreditCard,
    tone: "text-emerald-600",
    hint: "Same-day, most regions.",
  },
  {
    key: "paypal",
    label: "PayPal",
    tagline: "Instant to your PayPal",
    icon: WalletIcon,
    tone: "text-indigo-600",
    hint: "Available in 200+ countries.",
  },
  {
    key: "crypto_alt",
    label: "SOL / ETH / USDT",
    tagline: "Alt-networks",
    icon: Coins,
    tone: "text-fuchsia-600",
    coins: ["SOL", "ETH", "USDT", "USDC"],
    hint: "Solana · Ethereum · Tether.",
  },
];

const initialForm = { legal_name: "", city: "", postal_code: "", country: "US" };

const SellerApplyQuick = () => {
  const { user, refresh, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [payout, setPayout] = useState("crypto");
  const [errors, setErrors] = useState({});
  const [touched, setTouched] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [existing, setExisting] = useState(null);

  // OTP state — the fix for "Missing OTP token" crash
  const [otpStage, setOtpStage] = useState("idle"); // idle | requesting | awaiting | verifying | verified
  const [otpCode, setOtpCode] = useState("");
  const [otpToken, setOtpToken] = useState(null);
  const [otpExpiresAt, setOtpExpiresAt] = useState(null);
  const [otpCountdown, setOtpCountdown] = useState(0);
  const otpInputRef = useRef(null);

  useEffect(() => {
    if (!user) return;
    // If the applicant's email was verified in another tab / an admin
    // flipped the flag, pick that up before we render — the OTP flow
    // still runs, but a stale user.email_verified won't confuse the UI.
    refresh?.().catch(() => {});
    api.get("/seller/application").then((r) => setExisting(r.data)).catch(() => {});
  }, [user, refresh]);

  // Live countdown for OTP expiry
  useEffect(() => {
    if (!otpExpiresAt) { setOtpCountdown(0); return; }
    const tick = () => {
      const left = Math.max(0, Math.floor((otpExpiresAt - Date.now()) / 1000));
      setOtpCountdown(left);
      if (left === 0 && otpStage === "awaiting") setOtpStage("idle");
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [otpExpiresAt, otpStage]);

  const setField = (k) => (e) => {
    const val = typeof e === "string" ? e : e.target.value;
    const upper = k === "country" ? val.toUpperCase().slice(0, 2) : val;
    setForm((f) => ({ ...f, [k]: upper }));
    if (touched[k]) {
      const err = REQUIRED_RULES[k]?.validate(upper) ?? null;
      setErrors((prev) => ({ ...prev, [k]: err }));
    }
  };
  const blur = (k) => () => {
    setTouched((t) => ({ ...t, [k]: true }));
    setErrors((prev) => ({ ...prev, [k]: REQUIRED_RULES[k]?.validate(form[k]) ?? null }));
  };
  const runAll = () => {
    const next = {};
    for (const k of Object.keys(REQUIRED_RULES)) next[k] = REQUIRED_RULES[k].validate(form[k]);
    setErrors(next);
    setTouched(Object.fromEntries(Object.keys(REQUIRED_RULES).map((k) => [k, true])));
    return Object.values(next).every((e) => !e);
  };
  const isValid = Object.keys(REQUIRED_RULES).every((k) => !REQUIRED_RULES[k].validate(form[k]));

  // === OTP flow ===
  const requestOtp = async () => {
    if (!runAll()) return;
    setOtpStage("requesting");
    try {
      const { data } = await api.post("/otp/request", { purpose: "seller_apply" });
      const secs = data.expires_in_seconds || 600;
      setOtpExpiresAt(Date.now() + secs * 1000);
      setOtpStage("awaiting");
      setOtpCode("");
      setTimeout(() => otpInputRef.current?.focus(), 50);
      toast({
        title: "Code sent",
        description: `Check ${data.sent_to_email || user.email} for a 6-digit code.`,
      });
    } catch (err) {
      setOtpStage("idle");
      toast({ title: "Couldn't send code", description: errorText(err, "Try again in a moment"), variant: "destructive" });
    }
  };

  const verifyOtp = async () => {
    if (otpCode.length !== 6 || !/^\d{6}$/.test(otpCode)) {
      toast({ title: "Enter the 6-digit code", variant: "destructive" });
      return;
    }
    setOtpStage("verifying");
    try {
      const { data } = await api.post("/otp/verify", { purpose: "seller_apply", code: otpCode });
      setOtpToken(data.otp_token);
      setOtpStage("verified");
      toast({ title: "Email verified", description: "Submitting your application…" });
      // auto-submit right away
      await submitApplication(data.otp_token);
    } catch (err) {
      setOtpStage("awaiting");
      toast({ title: "Verification failed", description: errorText(err, "Try again"), variant: "destructive" });
    }
  };

  const submitApplication = async (token) => {
    setSubmitting(true);
    try {
      const payload = {
        legal_name: form.legal_name.trim(),
        city: form.city.trim(),
        postal_code: form.postal_code.trim(),
        country: form.country.toUpperCase(),
        business_type: "individual",
        payout_method: payout,
        address_line1: `${form.city.trim()} — quick apply`,
        storefront_theme: "Modern Storefront",
      };
      const { data } = await api.post("/seller/apply", payload, {
        headers: { "x-otp-token": token || otpToken || "" },
      });
      setExisting(data);
      toast({
        title: "Application submitted",
        description:
          data.status === "approved"
            ? "You're approved! Redirecting to your storefront…"
            : "Our team will review it shortly.",
      });
      await refresh();
      if (data.status === "approved") {
        setTimeout(() => navigate("/dashboard/seller"), 900);
      }
    } catch (err) {
      toast({
        title: "Submission failed",
        description: errorText(err, "Try again"),
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const onSubmit = (e) => {
    e.preventDefault();
    // If already have a valid OTP token, submit directly; else start OTP flow.
    if (otpStage === "verified" && otpToken) {
      submitApplication(otpToken);
    } else {
      requestOtp();
    }
  };

  if (authLoading) return <div className="max-w-2xl mx-auto px-4 py-12 text-neutral-500">Loading…</div>;
  if (!user) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-12">
        <p className="text-neutral-700">Please <Link to="/login" className="text-[#DC2626] underline">log in</Link> to apply.</p>
      </div>
    );
  }

  const fmtMMSS = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="max-w-2xl mx-auto px-4 py-10 space-y-6" data-testid="seller-apply-quick-page">
      {/* Header */}
      <div>
        <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-[0.2em] font-semibold text-[#5459E8] bg-[#5459E8]/10 border border-[#5459E8]/20 rounded-full px-3 py-1">
          <Zap className="h-3 w-3" /> Quick apply · 60 seconds
        </span>
        <h1 className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">
          Open your store on BlueOcean
        </h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">
          Four fields, instant setup. We&apos;ll spin up your storefront on our best-selling <b>Modern Storefront</b> template.
        </p>
      </div>

      {/* Modern Storefront preview */}
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-gradient-to-br from-white to-neutral-50 dark:from-neutral-900 dark:to-neutral-800/40 p-5 sm:p-6" data-testid="modern-storefront-preview">
        <div className="flex items-start gap-3 flex-wrap">
          <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-neutral-900 to-neutral-700 text-white grid place-items-center shrink-0">
            <StoreIcon className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs uppercase tracking-wider text-neutral-500 font-medium">Pre-configured</div>
            <div className="text-lg font-extrabold text-neutral-900 dark:text-neutral-100 mt-0.5">Modern Storefront</div>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1 max-w-md">
              Editorial hero, category ribbon, best-sellers rotator, and mobile-first product grid. Fully customizable after launch.
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          {[
            { icon: Sparkles, label: "Instant setup", tone: "text-[#5459E8]" },
            { icon: Truck, label: "Weekly payouts", tone: "text-sky-600" },
            { icon: ShieldCheck, label: "Escrow protected", tone: "text-emerald-600" },
          ].map((p, i) => (
            <div key={i} className="rounded-xl bg-white dark:bg-neutral-800/60 border border-neutral-100 dark:border-neutral-800 p-3">
              <p.icon className={`h-4 w-4 mx-auto ${p.tone}`} />
              <div className="text-[11px] font-semibold mt-1 text-neutral-700 dark:text-neutral-200">{p.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Existing application */}
      {existing && existing.status !== "rejected" && (
        <div className="rounded-xl border border-neutral-200 bg-neutral-50 dark:bg-neutral-800/40 p-5 flex items-start gap-3" data-testid="existing-application-quick">
          <CheckCircle2 className={`h-5 w-5 shrink-0 mt-0.5 ${existing.status === "approved" ? "text-emerald-600" : "text-amber-600"}`} />
          <div className="flex-1">
            <div className="font-semibold capitalize">Application {existing.status}</div>
            <div className="text-sm text-neutral-500 mt-0.5">
              {existing.status === "approved" ? "Your storefront is live." : "Our team is reviewing — you'll be notified as soon as it's approved."}
            </div>
            {existing.status === "approved" && (
              <Button onClick={() => navigate("/dashboard/seller")} className="mt-3 bg-[#DC2626] hover:bg-[#e01d1b] rounded-full h-10" data-testid="quick-goto-dashboard">
                Go to storefront <ArrowRight className="h-4 w-4 ml-1.5" />
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Form */}
      {(!existing || existing.status === "rejected") && (
        <form onSubmit={onSubmit} className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 sm:p-6 space-y-5" data-testid="seller-apply-quick-form" noValidate>
          {/* 4 fields */}
          {Object.entries(REQUIRED_RULES).map(([k, rule]) => (
            <div key={k}>
              <Label htmlFor={`sqf-${k}`} className="text-sm">
                {rule.label} <span className="text-[#DC2626]">*</span>
              </Label>
              <Input
                id={`sqf-${k}`}
                value={form[k]}
                onChange={setField(k)}
                onBlur={blur(k)}
                className={`mt-1 min-h-[44px] ${errors[k] ? "border-red-400 focus-visible:ring-red-300" : ""}`}
                placeholder={rule.label}
                data-testid={`sqf-${k}-input`}
                aria-invalid={!!errors[k]}
                autoComplete={k === "postal_code" ? "postal-code" : k === "country" ? "country" : k === "city" ? "address-level2" : "name"}
              />
              {errors[k] && (<div className="text-xs text-red-600 mt-1" data-testid={`sqf-${k}-err`}>{errors[k]}</div>)}
            </div>
          ))}

          {/* Payout method picker */}
          <div>
            <Label className="text-sm">Payout method <span className="text-[#DC2626]">*</span></Label>
            <div className="mt-2 grid sm:grid-cols-2 gap-2" data-testid="payout-picker">
              {PAYOUT_METHODS.map((m) => {
                const active = payout === m.key;
                return (
                  <button
                    type="button"
                    key={m.key}
                    onClick={() => setPayout(m.key)}
                    className={`relative flex items-start gap-3 rounded-2xl border p-3.5 text-left transition-all min-h-[76px] ${
                      active
                        ? "border-[#5459E8] bg-gradient-to-br from-[#E0E7FF]/60 to-[#FEE2E2]/40 dark:from-[#5459E8]/15 dark:to-[#FF0515]/10 shadow-[0_6px_24px_-10px_rgba(84,89,232,0.45)] scale-[1.02]"
                        : "border-neutral-200 dark:border-neutral-700 hover:border-[#5459E8]/60 dark:hover:border-[#818CF8]/60 hover:shadow-sm bg-white dark:bg-neutral-900"
                    }`}
                    data-testid={`payout-${m.key}`}
                    aria-pressed={active}
                  >
                    <div className={`h-10 w-10 rounded-xl grid place-items-center shrink-0 ${active ? "bg-gradient-to-br from-[#5459E8] to-[#818CF8] text-white shadow-md" : `bg-neutral-100 dark:bg-neutral-800 ${m.tone}`}`}>
                      <m.icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-neutral-900 dark:text-neutral-100 truncate">{m.label}</span>
                        {m.recommended && (
                          <span className="inline-flex items-center rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5">
                            Recommended
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5">{m.tagline}</div>
                      <div className="text-[10px] text-neutral-400 dark:text-neutral-500 mt-1">{m.hint}</div>
                      {m.coins && (
                        <div className="flex items-center gap-1 mt-2" data-testid={`payout-coins-${m.key}`}>
                          {m.coins.map((c) => (
                            <CryptoIcon key={c} symbol={c} size={18} />
                          ))}
                        </div>
                      )}
                    </div>
                    {active && (
                      <CheckCircle2 className="absolute top-2 right-2 h-4 w-4 text-[#5459E8]" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* OTP verification block */}
          <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50/60 dark:bg-neutral-800/30 p-4" data-testid="otp-block">
            <div className="flex items-start gap-3">
              <Mail className="h-5 w-5 text-neutral-500 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-neutral-800 dark:text-neutral-100">Verify your email</div>
                <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                  We&apos;ll send a 6-digit code to <b className="break-all">{user.email}</b>.
                </div>
              </div>
              {otpStage === "verified" && (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
                  <CheckCircle2 className="h-3 w-3" /> Verified
                </span>
              )}
            </div>

            {otpStage === "awaiting" && (
              <div className="mt-4 space-y-2" data-testid="otp-awaiting">
                <Label htmlFor="otp-input" className="text-xs">6-digit code</Label>
                <div className="flex gap-2 flex-wrap">
                  <Input
                    id="otp-input"
                    ref={otpInputRef}
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    inputMode="numeric"
                    pattern="\d{6}"
                    className="flex-1 min-w-[160px] text-lg tracking-widest font-mono tabular-nums text-center"
                    placeholder="••••••"
                    data-testid="otp-input"
                  />
                  <Button
                    type="button"
                    onClick={verifyOtp}
                    disabled={otpCode.length !== 6 || otpStage === "verifying"}
                    className="bg-[#DC2626] hover:bg-[#e01d1b] min-h-[44px]"
                    data-testid="otp-verify-btn"
                  >
                    {otpStage === "verifying" ? "Verifying…" : "Verify code"}
                  </Button>
                </div>
                <div className="flex items-center justify-between text-[11px] text-neutral-500">
                  <span data-testid="otp-countdown">
                    {otpCountdown > 0 ? `Code expires in ${fmtMMSS(otpCountdown)}` : "Code expired"}
                  </span>
                  <button
                    type="button"
                    onClick={requestOtp}
                    disabled={otpStage === "requesting"}
                    className="text-[#DC2626] hover:underline inline-flex items-center gap-1"
                    data-testid="otp-resend"
                  >
                    <RefreshCw className="h-3 w-3" /> Resend
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Submit */}
          <Button
            type="submit"
            disabled={submitting || !isValid || otpStage === "requesting" || otpStage === "verifying"}
            className="w-full rounded-full h-12 bg-[#DC2626] hover:bg-[#e01d1b] shadow-lg shadow-[#DC2626]/25 disabled:opacity-50"
            data-testid="sqf-submit-btn"
          >
            {submitting
              ? "Submitting…"
              : otpStage === "requesting"
              ? "Sending code…"
              : otpStage === "verified"
              ? "Submit application"
              : otpStage === "awaiting"
              ? "Enter the code above ↑"
              : "Send verification code"}
            {!submitting && otpStage !== "awaiting" && <ArrowRight className="h-4 w-4 ml-1.5" />}
          </Button>

          <div className="text-[11px] text-neutral-500 text-center">
            Need more control? Use the{" "}
            <Link to="/seller/apply" className="text-[#DC2626] underline" data-testid="advanced-apply-link">
              advanced application
            </Link>.
          </div>
        </form>
      )}
    </div>
  );
};

export default SellerApplyQuick;
