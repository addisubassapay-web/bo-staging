import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { ShieldCheck, CircleAlert, Upload as UploadIcon, FileText, X as XIcon, Zap, Sparkles, Check, Circle } from "lucide-react";

const initialForm = {
  legal_name: "",
  business_name: "",
  business_type: "individual",
  tax_id: "",
  country: "US",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  postal_code: "",
  phone: "",
  payout_method: "bank_transfer",
  id_document_note: "",
  id_document_file_id: null,
};

const SellerApply = () => {
  const { user, refresh, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [existing, setExisting] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [idFile, setIdFile] = useState(null); // {id, url, size, content_type, filename}
  const [uploading, setUploading] = useState(false);
  const [trust, setTrust] = useState(null);

  useEffect(() => {
    if (!user) return;
    api.get("/seller/trust-score").then((r) => setTrust(r.data)).catch(() => {});
  }, [user]);

  const uploadIdDoc = async (file) => {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setIdFile({ ...data, filename: file.name });
      setForm((f) => ({ ...f, id_document_file_id: data.id }));
      toast({ title: "ID document uploaded", description: file.name });
    } catch (err) {
      toast({ title: "Upload failed", description: err.response?.data?.detail || "Try a smaller file", variant: "destructive" });
    } finally {
      setUploading(false);
    }
  };

  const removeIdDoc = () => {
    setIdFile(null);
    setForm((f) => ({ ...f, id_document_file_id: null }));
  };

  useEffect(() => {
    if (!user) return;
    setForm((f) => ({ ...f, phone: user.phone || "" }));
    api.get("/seller/application").then((r) => setExisting(r.data)).catch(() => {});
  }, [user]);

  if (authLoading) return <div className="max-w-3xl mx-auto px-4 py-12 text-neutral-500">Loading…</div>;
  if (!user) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12">
        <p className="text-neutral-700">Please <Link to="/login" className="text-[#FF211F] underline">log in</Link>.</p>
      </div>
    );
  }

  const readyChecks = [
    { ok: user.email_verified, label: "Email verified" },
  ];
  const allReady = readyChecks.every((c) => c.ok);

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: typeof v === "string" ? v : v.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!allReady) {
      toast({ title: "Verify your email first", variant: "destructive" });
      return;
    }
    if (!form.legal_name || !form.address_line1 || !form.city || !form.postal_code) {
      toast({ title: "Fill in the required fields", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/seller/apply", form);
      setExisting(data);
      toast({ title: "Application submitted", description: "Our team will review it shortly." });
      await refresh();
    } catch (err) {
      toast({ title: "Submission failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  const statusColor = {
    pending: "bg-amber-100 text-amber-800",
    approved: "bg-emerald-100 text-emerald-800",
    rejected: "bg-red-100 text-red-800",
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-6" data-testid="seller-apply-page">
      <div>
        <span className="inline-block text-[10px] uppercase tracking-[0.2em] font-semibold text-[#FF7A18] bg-[#FF7A18]/10 border border-[#FF7A18]/20 rounded-full px-3 py-1">
          Become a seller
        </span>
        <h1 className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">Sell on Mercari-Global</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">List items, set your prices, ship worldwide, and get paid. High-trust accounts are approved instantly.</p>
      </div>

      {trust && (
        <>
          <TrustScoreCard trust={trust} />
          {!trust.auto_approve_eligible && <BoostScoreHint trust={trust} />}
        </>
      )}

      <div className="grid sm:grid-cols-2 gap-3">
        {readyChecks.map((c, i) => (
          <div key={i} className={`border rounded-lg p-3 flex items-center gap-2 ${c.ok ? "border-emerald-200 bg-emerald-50 dark:bg-emerald-500/15 dark:border-emerald-500/30" : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900"}`}>
            {c.ok ? <ShieldCheck className="h-4 w-4 text-emerald-600" /> : <CircleAlert className="h-4 w-4 text-neutral-400" />}
            <span className={c.ok ? "text-emerald-800 dark:text-emerald-200 text-sm" : "text-neutral-700 dark:text-neutral-300 text-sm"}>{c.label}</span>
          </div>
        ))}
      </div>
      {!allReady && (
        <div className="border border-amber-200 bg-amber-50 rounded-lg p-4 text-sm">
          Please <Link to="/verify" className="text-[#FF211F] underline font-medium">verify your email</Link> before applying. All other details are trusted by default.
        </div>
      )}

      {existing && (
        <div className="border border-neutral-200 bg-neutral-50 rounded-xl p-5" data-testid="existing-application">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-neutral-500">Your latest application</div>
              <div className="text-lg font-semibold mt-1">{existing.legal_name}</div>
              <div className="text-xs text-neutral-500 mt-1">Submitted {new Date(existing.created_at).toLocaleString()}</div>
            </div>
            <Badge className={`capitalize ${statusColor[existing.status] || "bg-neutral-200"}`}>{existing.status}</Badge>
          </div>
          {existing.admin_notes && (
            <div className="mt-3 text-sm text-neutral-700 border-t border-neutral-200 pt-3">
              <span className="text-neutral-500">Admin notes: </span>{existing.admin_notes}
            </div>
          )}
          {existing.status === "approved" && (
            <>
              <Button className="mt-4 bg-[#FF211F] hover:bg-[#e01d1b] rounded-full h-11 shadow-lg shadow-[#FF211F]/20" onClick={() => navigate("/sell")} data-testid="approved-start-selling">
                Start selling
              </Button>
              <PayoutPreviewCard tier={trust?.tier} />
            </>
          )}
        </div>
      )}

      {(!existing || existing.status === "rejected") && (
        <>
        <PayoutPreviewCard tier={trust?.tier} previewOnly />
        <form onSubmit={submit} className="space-y-4 bg-white border border-neutral-200 rounded-xl p-6" data-testid="seller-apply-form">
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Legal name *</Label>
              <Input value={form.legal_name} onChange={set("legal_name")} required data-testid="apply-legal-name" className="mt-1" />
            </div>
            <div>
              <Label>Business name (optional)</Label>
              <Input value={form.business_name} onChange={set("business_name")} data-testid="apply-business-name" className="mt-1" />
            </div>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Business type</Label>
              <Select value={form.business_type} onValueChange={set("business_type")}>
                <SelectTrigger className="mt-1" data-testid="apply-business-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="individual">Individual</SelectItem>
                  <SelectItem value="sole_prop">Sole proprietor</SelectItem>
                  <SelectItem value="llc">LLC</SelectItem>
                  <SelectItem value="corp">Corporation</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Tax ID / EIN (last 4 stored)</Label>
              <Input value={form.tax_id} onChange={set("tax_id")} placeholder="123-45-6789" data-testid="apply-tax-id" className="mt-1 font-mono" />
            </div>
          </div>
          <div>
            <Label>Address line 1 *</Label>
            <Input value={form.address_line1} onChange={set("address_line1")} required data-testid="apply-address1" className="mt-1" />
          </div>
          <div>
            <Label>Address line 2</Label>
            <Input value={form.address_line2} onChange={set("address_line2")} data-testid="apply-address2" className="mt-1" />
          </div>
          <div className="grid sm:grid-cols-3 gap-4">
            <div>
              <Label>City *</Label>
              <Input value={form.city} onChange={set("city")} required data-testid="apply-city" className="mt-1" />
            </div>
            <div>
              <Label>State / Region</Label>
              <Input value={form.state} onChange={set("state")} data-testid="apply-state" className="mt-1" />
            </div>
            <div>
              <Label>Postal code *</Label>
              <Input value={form.postal_code} onChange={set("postal_code")} required data-testid="apply-postal" className="mt-1" />
            </div>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Country</Label>
              <Input value={form.country} onChange={set("country")} data-testid="apply-country" className="mt-1 uppercase" maxLength={2} />
            </div>
            <div>
              <Label>Phone (verified)</Label>
              <Input value={form.phone} onChange={set("phone")} data-testid="apply-phone" className="mt-1 font-mono" />
            </div>
          </div>
          <div>
            <Label>Payout method</Label>
            <Select value={form.payout_method} onValueChange={set("payout_method")}>
              <SelectTrigger className="mt-1" data-testid="apply-payout-method"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="bank_transfer">Bank transfer (recommended)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Government-issued ID</Label>
            <p className="text-xs text-neutral-500 mt-0.5">Passport, driver&apos;s license, or national ID. Only the admin and you can view this. PDF/JPG/PNG, max 12MB.</p>
            {!idFile ? (
              <label className="mt-2 flex items-center gap-3 border border-dashed border-neutral-300 hover:border-[#FF211F] hover:bg-[#FFF3F2] rounded-lg p-4 cursor-pointer transition" data-testid="id-doc-upload">
                <UploadIcon className="h-5 w-5 text-neutral-500" />
                <div>
                  <div className="text-sm font-medium">{uploading ? "Uploading…" : "Click to upload"}</div>
                  <div className="text-xs text-neutral-500">PDF, JPG, PNG</div>
                </div>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,application/pdf"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadIdDoc(f); }}
                  disabled={uploading}
                />
              </label>
            ) : (
              <div className="mt-2 flex items-center gap-3 border border-emerald-200 bg-emerald-50 rounded-lg p-3" data-testid="id-doc-uploaded">
                <FileText className="h-5 w-5 text-emerald-700" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{idFile.filename}</div>
                  <div className="text-xs text-neutral-500">{Math.round(idFile.size / 1024)} KB · Encrypted storage</div>
                </div>
                <Button type="button" variant="ghost" size="sm" onClick={removeIdDoc} data-testid="id-doc-remove">
                  <XIcon className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
          <div>
            <Label>Additional notes (optional)</Label>
            <Textarea value={form.id_document_note} onChange={set("id_document_note")} placeholder="Anything else our reviewers should know" data-testid="apply-id-note" className="mt-1" rows={2} />
          </div>
          <Button type="submit" disabled={submitting || !allReady} className="bg-[#FF211F] hover:bg-[#e01d1b] rounded-full h-11 w-full shadow-lg shadow-[#FF211F]/20" data-testid="apply-submit-btn">
            {submitting ? "Submitting…" : trust?.auto_approve_eligible ? "Submit — you'll be instantly approved" : "Submit application"}
          </Button>
        </form>
        </>
      )}
    </div>
  );
};

const PayoutPreviewCard = ({ tier, previewOnly = false }) => {
  // Simple, transparent projection based on tier — pure frontend estimate.
  const t = tier || "new";
  const scenarios = {
    elite:   { lo: 800,  hi: 2200, note: "Elite trust unlocks Featured Storefront spots." },
    trusted: { lo: 400,  hi: 1200, note: "Trusted sellers see 1.6x average conversion." },
    new:     { lo: 150,  hi: 600,  note: "Complete verification steps to lift these numbers." },
  }[t];
  const feePct = 10; // platform fee %
  const midpoint = Math.round((scenarios.lo + scenarios.hi) / 2);
  const platformFee = Math.round(midpoint * (feePct / 100));
  const payout = midpoint - platformFee;

  return (
    <div
      className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 sm:p-6 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
      data-testid="payout-preview-card"
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-medium flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5 text-[#FF7A18]" /> Weekly earnings preview
          </div>
          <div className="mt-1 text-3xl sm:text-4xl font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums" data-testid="payout-preview-range">
            ${scenarios.lo.toLocaleString()} – ${scenarios.hi.toLocaleString()}
          </div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            {previewOnly ? "Estimate after you're approved · " : ""}Based on the {t} tier and category average.
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-medium">Payout cadence</div>
          <div className="mt-1 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Every Monday</div>
          <div className="text-[11px] text-neutral-400">Direct to your bank</div>
        </div>
      </div>

      {/* Fee breakdown bar */}
      <div className="mt-4">
        <div className="h-2.5 rounded-full overflow-hidden bg-neutral-100 dark:bg-neutral-800 flex">
          <div className="h-full bg-gradient-to-r from-emerald-400 to-emerald-500" style={{ width: `${100 - feePct}%` }} />
          <div className="h-full bg-gradient-to-r from-[#FF7A18] to-[#FF211F]" style={{ width: `${feePct}%` }} />
        </div>
        <div className="mt-2 flex justify-between text-[11px] uppercase tracking-wider">
          <span className="text-emerald-700 dark:text-emerald-300 font-semibold">You keep {100 - feePct}%</span>
          <span className="text-[#FF211F] font-semibold">Platform fee {feePct}%</span>
        </div>
      </div>

      {/* Example row */}
      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div className="rounded-xl bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-100 dark:border-neutral-800 p-3">
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Midpoint sales</div>
          <div className="mt-0.5 font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums">${midpoint.toLocaleString()}</div>
        </div>
        <div className="rounded-xl bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-100 dark:border-neutral-800 p-3">
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Platform fee</div>
          <div className="mt-0.5 font-extrabold text-[#FF211F] tabular-nums">-${platformFee.toLocaleString()}</div>
        </div>
        <div className="rounded-xl bg-emerald-50 dark:bg-emerald-500/15 border border-emerald-100 dark:border-emerald-500/30 p-3">
          <div className="text-[10px] uppercase tracking-wider text-emerald-700 dark:text-emerald-300">Your payout</div>
          <div className="mt-0.5 font-extrabold text-emerald-700 dark:text-emerald-300 tabular-nums">${payout.toLocaleString()}</div>
        </div>
      </div>

      <div className="mt-3 text-[11px] text-neutral-500 dark:text-neutral-400">💡 {scenarios.note}</div>
    </div>
  );
};

const BoostScoreHint = ({ trust }) => {
  const remaining = Math.max(0, trust.auto_approve_threshold - trust.score);
  // Sorted actions by max earnable points (largest lift first)
  const actions = trust.signals
    .filter((s) => s.earned < s.weight)
    .map((s) => {
      const meta = {
        email_verified:   { label: "Verify email",       to: "/verify", cta: "Verify now" },
        phone_verified:   { label: "Verify phone",       to: "/verify", cta: "Verify now" },
        profile_complete: { label: "Complete profile",   to: "/profile", cta: "Update" },
        has_referrals:    { label: "Invite a friend",    to: "/referrals", cta: "Get link" },
        account_age:      { label: "Keep your account active", to: "/profile", cta: "Wait it out", passive: true },
        no_open_disputes: { label: "Resolve open disputes", to: "/disputes", cta: "Review" },
      }[s.key] || { label: s.label, to: "/profile", cta: "Go" };
      return { ...meta, gap: s.weight - s.earned, key: s.key };
    })
    .sort((a, b) => b.gap - a.gap);

  if (actions.length === 0) return null;

  return (
    <div
      className="rounded-2xl border border-[#FF7A18]/25 bg-gradient-to-br from-[#FFF7EF] to-white dark:from-[#FF7A18]/10 dark:to-neutral-900 p-5 sm:p-6 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
      data-testid="boost-score-hint"
    >
      <div className="flex items-start gap-3 flex-wrap">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-[#FF7A18] to-[#FF211F] text-white grid place-items-center shadow-lg shadow-[#FF211F]/20 shrink-0">
          <Zap className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs uppercase tracking-wider font-semibold text-[#FF211F]">Boost your score</div>
          <div className="mt-0.5 text-lg sm:text-xl font-extrabold text-neutral-900 dark:text-neutral-100 tracking-tight">
            You&apos;re <span className="text-[#FF211F] tabular-nums" data-testid="boost-points-remaining">{remaining}</span> point{remaining === 1 ? "" : "s"} away from instant approval
          </div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Tap the fastest lifts below — each one instantly bumps your score.
          </p>
        </div>
      </div>
      <div className="mt-4 grid sm:grid-cols-2 gap-2.5">
        {actions.map((a) => (
          <Link
            key={a.key}
            to={a.to}
            className="group flex items-center gap-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-3 hover:border-[#FF7A18] hover:shadow-[0_10px_24px_-16px_rgba(255,33,31,0.28)] hover:-translate-y-0.5 transition-all duration-200"
            data-testid={`boost-action-${a.key}`}
          >
            <span className="inline-flex h-8 w-8 rounded-lg bg-[#FF7A18]/10 text-[#FF211F] items-center justify-center font-extrabold text-sm tabular-nums shrink-0">
              +{a.gap}
            </span>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-neutral-900 dark:text-neutral-100 truncate">{a.label}</div>
              <div className="text-[11px] text-neutral-500 dark:text-neutral-400">Worth up to +{a.gap} pts</div>
            </div>
            <span className="text-xs font-semibold text-[#FF7A18] group-hover:text-[#FF211F] whitespace-nowrap">{a.cta} →</span>
          </Link>
        ))}
      </div>
    </div>
  );
};

const TrustScoreCard = ({ trust }) => {
  const pct = trust.max > 0 ? Math.min(100, (trust.score / trust.max) * 100) : 0;
  const eligible = trust.auto_approve_eligible;
  const tierMeta = {
    elite:   { label: "Elite trust",   cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30" },
    trusted: { label: "Trusted",       cls: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30" },
    new:     { label: "Getting started", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30" },
  }[trust.tier] || { label: "New", cls: "bg-neutral-200 text-neutral-700" };

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 sm:p-6 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
      data-testid="trust-score-card"
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-medium flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-[#FF7A18]" /> Trust score
          </div>
          <div className="flex items-baseline gap-3 mt-1">
            <div className="text-4xl sm:text-5xl font-extrabold text-neutral-900 dark:text-neutral-100 tabular-nums" data-testid="trust-score-value">
              {trust.score}
              <span className="text-lg text-neutral-400 dark:text-neutral-500 font-medium">/{trust.max}</span>
            </div>
            <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full border ${tierMeta.cls}`}>
              {tierMeta.label}
            </span>
          </div>
        </div>
        <div className="text-right">
          {eligible ? (
            <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500 text-white text-xs font-bold px-3 py-1 shadow shadow-emerald-500/30" data-testid="trust-fast-track-badge">
              <Zap className="h-3.5 w-3.5" /> Instant approval on submit
            </div>
          ) : (
            <div className="text-xs text-neutral-500 dark:text-neutral-400 max-w-[180px]">
              Reach <b>{trust.auto_approve_threshold}</b> for instant approval — otherwise our team reviews within 24h.
            </div>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-4 h-2 rounded-full bg-neutral-100 dark:bg-neutral-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${
            eligible
              ? "bg-gradient-to-r from-emerald-400 to-emerald-500"
              : "bg-gradient-to-r from-[#FF7A18] to-[#FF211F]"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Signal breakdown */}
      <ul className="mt-4 grid sm:grid-cols-2 gap-x-4 gap-y-2">
        {trust.signals.map((s) => (
          <li
            key={s.key}
            className="flex items-center gap-2 text-sm"
            data-testid={`trust-signal-${s.key}`}
          >
            {s.earned > 0 ? (
              <span className="inline-flex h-5 w-5 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 items-center justify-center shrink-0">
                <Check className="h-3 w-3" />
              </span>
            ) : (
              <span className="inline-flex h-5 w-5 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-400 dark:text-neutral-500 items-center justify-center shrink-0">
                <Circle className="h-2.5 w-2.5" />
              </span>
            )}
            <span className={`flex-1 min-w-0 ${s.earned > 0 ? "text-neutral-800 dark:text-neutral-200" : "text-neutral-500 dark:text-neutral-400"}`}>
              {s.label}
              {s.earned === 0 && s.hint && <span className="text-[11px] text-neutral-400 dark:text-neutral-500 block truncate">{s.hint}</span>}
            </span>
            <span className={`text-xs tabular-nums shrink-0 ${s.earned > 0 ? "text-emerald-600 dark:text-emerald-300 font-semibold" : "text-neutral-400"}`}>
              +{s.earned}/{s.weight}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default SellerApply;
