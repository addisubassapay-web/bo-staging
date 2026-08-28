import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { errorText } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Zap, ShieldCheck, Store as StoreIcon, Sparkles, Truck, ArrowRight, CheckCircle2 } from "lucide-react";

/**
 * SellerApplyQuick — a one-step, streamlined seller application.
 *
 * Trims the classic /seller/apply form from 12 fields down to 4 essentials
 * (legal name, city, postal code, country) and pre-configures every store
 * with the "Modern Storefront" layout. Client-side validation shows inline
 * errors immediately; the submit button stays disabled until every rule
 * passes.
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

const initialForm = { legal_name: "", city: "", postal_code: "", country: "US" };

const SellerApplyQuick = () => {
  const { user, refresh, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [errors, setErrors] = useState({});
  const [touched, setTouched] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [existing, setExisting] = useState(null);

  useEffect(() => {
    if (!user) return;
    api.get("/seller/application").then((r) => setExisting(r.data)).catch(() => {});
  }, [user]);

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
    for (const k of Object.keys(REQUIRED_RULES)) {
      next[k] = REQUIRED_RULES[k].validate(form[k]);
    }
    setErrors(next);
    setTouched(Object.fromEntries(Object.keys(REQUIRED_RULES).map((k) => [k, true])));
    return Object.values(next).every((e) => !e);
  };
  const isValid = Object.keys(REQUIRED_RULES).every((k) => !REQUIRED_RULES[k].validate(form[k]));
  const emailReady = !!user?.email_verified;

  const submit = async (e) => {
    e.preventDefault();
    if (!emailReady) {
      toast({ title: "Verify your email first", variant: "destructive" });
      return;
    }
    if (!runAll()) return;
    setSubmitting(true);
    try {
      const payload = {
        legal_name: form.legal_name.trim(),
        city: form.city.trim(),
        postal_code: form.postal_code.trim(),
        country: form.country.toUpperCase(),
        // Pre-configured Modern Storefront defaults so backend record is complete
        business_type: "individual",
        payout_method: "bank_transfer",
        address_line1: `${form.city.trim()} — quick apply`,
        storefront_theme: "Modern Storefront",
      };
      const { data } = await api.post("/seller/apply", payload);
      setExisting(data);
      toast({
        title: "Application submitted",
        description: data.status === "approved"
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

  if (authLoading) return <div className="max-w-2xl mx-auto px-4 py-12 text-neutral-500">Loading…</div>;
  if (!user) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-12">
        <p className="text-neutral-700">
          Please <Link to="/login" className="text-[#FF211F] underline">log in</Link> to apply.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-10 space-y-6" data-testid="seller-apply-quick-page">
      {/* Header */}
      <div>
        <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
          <Zap className="h-3 w-3" /> Quick apply · 60 seconds
        </span>
        <h1 className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">
          Open your store on Mercari-Smarthub
        </h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">
          Four fields, instant setup. We&apos;ll spin up your storefront on our best-selling <b>Modern Storefront</b> template.
        </p>
      </div>

      {/* Modern Storefront preview card */}
      <div
        className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-gradient-to-br from-white to-neutral-50 dark:from-neutral-900 dark:to-neutral-800/40 p-5 sm:p-6"
        data-testid="modern-storefront-preview"
      >
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
            { icon: Sparkles, label: "Instant setup", tone: "text-[#FF7A18]" },
            { icon: TruckIcon, label: "Weekly payouts", tone: "text-sky-600" },
            { icon: ShieldCheckIcon, label: "Escrow protected", tone: "text-emerald-600" },
          ].map((p, i) => (
            <div key={i} className="rounded-xl bg-white dark:bg-neutral-800/60 border border-neutral-100 dark:border-neutral-800 p-3">
              <p.icon className={`h-4 w-4 mx-auto ${p.tone}`} />
              <div className="text-[11px] font-semibold mt-1 text-neutral-700 dark:text-neutral-200">{p.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Email verification gate */}
      {!emailReady && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/30 p-4 text-sm text-amber-900 dark:text-amber-100">
          Verify your email first — <Link to="/verify" className="text-[#FF211F] underline font-medium">verify now</Link>.
        </div>
      )}

      {/* Existing application */}
      {existing && existing.status !== "rejected" && (
        <div
          className="rounded-xl border border-neutral-200 bg-neutral-50 dark:bg-neutral-800/40 p-5 flex items-start gap-3"
          data-testid="existing-application-quick"
        >
          <CheckCircle2 className={`h-5 w-5 shrink-0 mt-0.5 ${existing.status === "approved" ? "text-emerald-600" : "text-amber-600"}`} />
          <div className="flex-1">
            <div className="font-semibold capitalize">Application {existing.status}</div>
            <div className="text-sm text-neutral-500 mt-0.5">
              {existing.status === "approved"
                ? "Your storefront is live."
                : "Our team is reviewing — you'll be notified as soon as it's approved."}
            </div>
            {existing.status === "approved" && (
              <Button
                onClick={() => navigate("/dashboard/seller")}
                className="mt-3 bg-[#FF211F] hover:bg-[#e01d1b] rounded-full h-10"
                data-testid="quick-goto-dashboard"
              >
                Go to storefront <ArrowRight className="h-4 w-4 ml-1.5" />
              </Button>
            )}
          </div>
        </div>
      )}

      {/* The form itself */}
      {(!existing || existing.status === "rejected") && (
        <form
          onSubmit={submit}
          className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 sm:p-6 space-y-4"
          data-testid="seller-apply-quick-form"
          noValidate
        >
          {Object.entries(REQUIRED_RULES).map(([k, rule]) => (
            <div key={k}>
              <Label htmlFor={`sqf-${k}`} className="text-sm">
                {rule.label} <span className="text-[#FF211F]">*</span>
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
                aria-describedby={errors[k] ? `sqf-${k}-err` : undefined}
                autoComplete={k === "postal_code" ? "postal-code" : k === "country" ? "country" : k === "city" ? "address-level2" : "name"}
              />
              {errors[k] && (
                <div id={`sqf-${k}-err`} className="text-xs text-red-600 mt-1" data-testid={`sqf-${k}-err`}>
                  {errors[k]}
                </div>
              )}
            </div>
          ))}

          <Button
            type="submit"
            disabled={submitting || !emailReady || !isValid}
            className="w-full rounded-full h-12 bg-[#FF211F] hover:bg-[#e01d1b] shadow-lg shadow-[#FF211F]/25 disabled:opacity-50"
            data-testid="sqf-submit-btn"
          >
            {submitting ? "Submitting…" : "Launch my store"}
            {!submitting && <ArrowRight className="h-4 w-4 ml-1.5" />}
          </Button>
          <div className="text-[11px] text-neutral-500 text-center">
            Need more control? Use the{" "}
            <Link to="/seller/apply" className="text-[#FF211F] underline" data-testid="advanced-apply-link">
              advanced application
            </Link>
            .
          </div>
        </form>
      )}
    </div>
  );
};

// Local icon aliases so we can highlight them via `tone` props without extra imports
const TruckIcon = (props) => <Truck {...props} />;
const ShieldCheckIcon = (props) => <ShieldCheck {...props} />;

export default SellerApplyQuick;
