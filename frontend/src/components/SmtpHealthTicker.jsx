import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { Mail, RefreshCw, CheckCircle2, AlertTriangle, XCircle, ExternalLink } from "lucide-react";

/**
 * SmtpHealthTicker — polls /admin/smtp/health every 60s (backend caches
 * for 60s too, so total probe rate against Hostinger is ~1/min) and
 * renders a red/amber/green dot with an actionable hint. Sits in the
 * Admin dashboard header so outages surface before real users hit them.
 *
 * States:
 *   healthy      → green    "SMTP OK (host · latency)"
 *   blocked      → red      "Hostinger outbound disabled" (5.7.1)
 *   auth_failed  → red      "SMTP auth failed"
 *   unreachable  → amber    "SMTP unreachable"
 *   unconfigured → amber    "SMTP env vars missing"
 */
const STATE_TONE = {
  healthy: { dot: "bg-emerald-500", ring: "ring-emerald-500/30", text: "text-emerald-700", label: "Healthy" },
  blocked: { dot: "bg-red-500", ring: "ring-red-500/30", text: "text-red-700", label: "Blocked" },
  auth_failed: { dot: "bg-red-500", ring: "ring-red-500/30", text: "text-red-700", label: "Auth failed" },
  unreachable: { dot: "bg-amber-500", ring: "ring-amber-500/30", text: "text-amber-700", label: "Unreachable" },
  unconfigured: { dot: "bg-neutral-400", ring: "ring-neutral-400/30", text: "text-neutral-700", label: "Not configured" },
};

const HINT = {
  healthy: "Verification codes, password resets, and order emails are sending normally.",
  blocked:
    "Hostinger has disabled outbound sending on this mailbox. Log into Hostinger hPanel → Emails and re-enable SMTP.",
  auth_failed:
    "SMTP login is rejected. Check SMTP_USER / SMTP_PASS in backend/.env — Hostinger may have rotated the password.",
  unreachable:
    "The mailer can't reach smtp.hostinger.com. Could be a transient network blip or DNS issue.",
  unconfigured:
    "Backend .env is missing SMTP_HOST / SMTP_USER / SMTP_PASS / EMAIL_FROM_ADDRESS / EMAIL_PROVIDER.",
};

const SmtpHealthTicker = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/smtp/health", { params: force ? { force: 1 } : {} });
      setData(data);
    } catch {
      setData({ ok: false, state: "unreachable", error: "Health endpoint failed" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(() => load(), 60_000); // once a minute
    return () => clearInterval(t);
  }, [load]);

  if (!data) {
    return (
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-3 flex items-center gap-2 text-sm text-neutral-500" data-testid="smtp-health-ticker">
        <Mail className="h-4 w-4" /> Checking SMTP…
      </div>
    );
  }

  const tone = STATE_TONE[data.state] || STATE_TONE.unreachable;
  const Icon = data.state === "healthy" ? CheckCircle2 : data.state === "blocked" || data.state === "auth_failed" ? XCircle : AlertTriangle;

  return (
    <div
      className={`rounded-xl border p-3 md:p-4 flex flex-col md:flex-row md:items-center gap-3 ${
        data.state === "healthy"
          ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-900/40 dark:bg-emerald-950/20"
          : data.state === "blocked" || data.state === "auth_failed"
          ? "border-red-200 bg-red-50/60 dark:border-red-900/40 dark:bg-red-950/20"
          : "border-amber-200 bg-amber-50/60 dark:border-amber-900/40 dark:bg-amber-950/20"
      }`}
      data-testid="smtp-health-ticker"
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className={`relative flex h-2.5 w-2.5 shrink-0`}>
          <span className={`absolute inline-flex h-full w-full rounded-full ${tone.dot} opacity-75 ${data.state === "healthy" ? "animate-ping" : ""}`}></span>
          <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${tone.dot}`}></span>
        </span>
        <Icon className={`h-4 w-4 ${tone.text}`} />
        <div className="min-w-0">
          <div className="text-sm font-semibold flex items-center gap-2 flex-wrap">
            <span data-testid="smtp-health-state">SMTP · {tone.label}</span>
            {data.state === "healthy" && data.latency_ms != null && (
              <span className="text-xs font-normal text-emerald-700/70 tabular-nums">{data.latency_ms}ms</span>
            )}
            {data.host && (
              <span className="text-xs font-mono font-normal text-neutral-500 truncate max-w-[220px]">{data.host}</span>
            )}
          </div>
          <div className={`text-xs mt-0.5 ${tone.text} max-w-2xl`} data-testid="smtp-health-hint">
            {HINT[data.state] || data.error || "Unknown state"}
          </div>
        </div>
      </div>
      <div className="flex-1" />
      <div className="flex items-center gap-2 flex-wrap">
        {data.checked_at && (
          <span className="text-[11px] text-neutral-500 tabular-nums">
            checked {new Date(data.checked_at).toLocaleTimeString()}
            {data.cached && data.cache_age_seconds > 0 ? ` · cached ${data.cache_age_seconds}s ago` : ""}
          </span>
        )}
        {data.state !== "healthy" && data.error && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[11px] px-2 py-1 rounded border border-neutral-300 text-neutral-700 hover:bg-white/50"
            data-testid="smtp-health-detail-toggle"
          >
            {expanded ? "Hide" : "Details"}
          </button>
        )}
        <button
          type="button"
          onClick={() => load(true)}
          disabled={loading}
          className="text-[11px] px-2 py-1 rounded border border-neutral-300 text-neutral-700 hover:bg-white/50 inline-flex items-center gap-1"
          data-testid="smtp-health-refresh"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Retest
        </button>
        {data.state === "blocked" && (
          <a
            href="https://hpanel.hostinger.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] px-2 py-1 rounded border border-red-300 text-red-700 hover:bg-red-50 inline-flex items-center gap-1 font-semibold"
            data-testid="smtp-health-hpanel"
          >
            Open hPanel <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
      {expanded && data.error && (
        <pre
          className="w-full mt-2 text-[11px] font-mono bg-white/70 dark:bg-neutral-900/60 border border-neutral-200 dark:border-neutral-800 rounded p-2 overflow-x-auto text-neutral-700"
          data-testid="smtp-health-error-detail"
        >
          {data.error}
        </pre>
      )}
    </div>
  );
};

export default SmtpHealthTicker;
