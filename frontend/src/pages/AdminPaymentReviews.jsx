import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { RefreshCw, ImageIcon, CheckCircle2, XCircle, Bell, ArrowUpRight, Coins, RotateCcw, Snowflake } from "lucide-react";

const SLA_STYLES = {
  fresh:     "bg-emerald-50 text-emerald-700 border-emerald-200",
  attention: "bg-amber-50   text-amber-700   border-amber-200",
  urgent:    "bg-orange-50  text-orange-700  border-orange-200",
  overdue:   "bg-rose-50    text-rose-700    border-rose-200",
};

const fmtAge = (min) => {
  const m = Math.max(0, Number(min) || 0);
  if (m < 60) return `${Math.round(m)}m`;
  const h = m / 60;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
};

const SlaBadge = ({ sla }) => {
  if (!sla) return null;
  const cls = SLA_STYLES[sla.tier] || "bg-neutral-100 text-neutral-700 border-neutral-200";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border text-[10px] font-bold px-2 py-0.5 ${cls}`} data-testid={`sla-${sla.tier}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {sla.label} · {fmtAge(sla.age_min)}
    </span>
  );
};

const SectionHeader = ({ icon: Icon, title, count, hint }) => (
  <div className="flex items-baseline gap-3 mb-3 mt-6">
    <div className="flex items-center gap-2">
      <Icon className="h-4 w-4 text-neutral-500" />
      <h2 className="text-sm font-bold uppercase tracking-wider text-neutral-800 dark:text-neutral-200">{title}</h2>
    </div>
    <Badge variant="secondary" className="rounded-full">{count}</Badge>
    {hint && <span className="text-xs text-neutral-500">{hint}</span>}
  </div>
);

const AdminPaymentReviews = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [preview, setPreview] = useState("");
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/admin/payment-reviews");
      setData(r.data);
    } catch (err) {
      toast({ title: "Couldn't load reviews", description: err.response?.data?.detail || "", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);  // auto-refresh
    return () => clearInterval(t);
  }, [load]);

  const approve = async (dep) => {
    setBusyId(dep.id);
    try {
      await api.post(`/admin/deposits/${dep.id}/approve`);
      toast({ title: `Approved $${dep.amount.toFixed(2)} deposit`, description: `${dep.user_name || dep.user_id.slice(0,8)}` });
      load();
    } catch (err) {
      toast({ title: "Approve failed", description: err.response?.data?.detail || "", variant: "destructive" });
    } finally {
      setBusyId("");
    }
  };

  const reject = async (dep) => {
    const reason = window.prompt("Reason for rejection (buyer sees this):", "Screenshot is unclear — please retake");
    if (!reason) return;
    setBusyId(dep.id);
    try {
      await api.post(`/admin/deposits/${dep.id}/reject`, { reason });
      toast({ title: `Rejected $${dep.amount.toFixed(2)} deposit`, description: reason });
      load();
    } catch (err) {
      toast({ title: "Reject failed", description: err.response?.data?.detail || "", variant: "destructive" });
    } finally {
      setBusyId("");
    }
  };

  const nudgeBuyer = async (o) => {
    setBusyId(o.id);
    try {
      await api.post(`/orders/${o.id}/nudge-buyer`);
      toast({ title: "Nudge sent", description: `Reminded buyer about ${o.listing_title || "order"}` });
      load();
    } catch (err) {
      toast({ title: "Nudge failed", description: err.response?.data?.detail || "", variant: "destructive" });
    } finally {
      setBusyId("");
    }
  };

  const renderDeposit = (d, resubmit = false) => (
    <div
      key={d.id}
      className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 flex flex-col sm:flex-row sm:items-center gap-4"
      data-testid={`review-deposit-${d.id}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="text-lg font-extrabold tabular-nums">{formatPrice(d.amount)}</div>
          <Badge variant="outline" className="capitalize">{d.method === "crypto" ? `Crypto · ${d.currency || ""}` : (d.currency || "Manual")}</Badge>
          <SlaBadge sla={d.sla} />
          {resubmit && <Badge className="bg-fuchsia-100 text-fuchsia-700 border-fuchsia-200 border">Resubmitted × {d.resubmit_count}</Badge>}
        </div>
        <div className="text-xs text-neutral-500 mt-1">
          <span className="font-medium text-neutral-700 dark:text-neutral-300">{d.user_name || d.user_id?.slice(0,8)}</span>
          {d.reference && <> · ref <code className="font-mono text-[11px]">{d.reference.slice(0, 24)}{d.reference.length > 24 ? "…" : ""}</code></>}
        </div>
        {d.note && <div className="text-xs text-neutral-500 mt-0.5 line-clamp-1">{d.note}</div>}
        {resubmit && d.admin_note && (
          <div className="text-[11px] text-amber-700 mt-1 line-clamp-2">Previous reject: {d.admin_note}</div>
        )}
      </div>
      <div className="flex items-center gap-2">
        {d.screenshot_url && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setPreview(d.screenshot_url)}
            className="h-9"
            data-testid={`review-screenshot-btn-${d.id}`}
          >
            <ImageIcon className="h-3.5 w-3.5 mr-1.5" /> Proof
          </Button>
        )}
        <Button
          size="sm"
          onClick={() => approve(d)}
          disabled={busyId === d.id}
          className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white"
          data-testid={`review-approve-${d.id}`}
        >
          <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> Approve
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => reject(d)}
          disabled={busyId === d.id}
          className="h-9 border-rose-300 text-rose-700 hover:bg-rose-50"
          data-testid={`review-reject-${d.id}`}
        >
          <XCircle className="h-3.5 w-3.5 mr-1.5" /> Reject
        </Button>
      </div>
    </div>
  );

  const renderStuck = (o) => (
    <div
      key={o.id}
      className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 flex flex-col sm:flex-row sm:items-center gap-4"
      data-testid={`review-stuck-${o.id}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="text-lg font-extrabold tabular-nums">{formatPrice(o.amount)}</div>
          <Badge variant="outline" className="capitalize">{o.fulfillment_status?.replace("_"," ")}</Badge>
          <SlaBadge sla={o.sla} />
        </div>
        <div className="text-sm font-medium mt-1 line-clamp-1">{o.listing_title || "(untitled listing)"}</div>
        <div className="text-xs text-neutral-500 mt-0.5">{o.stuck_reason} · escrow {formatPrice(o.seller_earnings)}</div>
      </div>
      <div className="flex items-center gap-2">
        {o.fulfillment_status !== "pending_pickup" && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => nudgeBuyer(o)}
            disabled={busyId === o.id}
            className="h-9 border-amber-300 text-amber-800 hover:bg-amber-50"
            data-testid={`review-nudge-${o.id}`}
          >
            <Bell className="h-3.5 w-3.5 mr-1.5" /> Nudge buyer
          </Button>
        )}
        <Link
          to={`/admin/orders`}
          state={{ focusOrder: o.id }}
          className="inline-flex items-center gap-1 text-xs font-semibold text-[#FF211F] hover:underline"
          data-testid={`review-order-link-${o.id}`}
        >
          Open order <ArrowUpRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );

  const counts = data?.counts || { total: 0, pending_deposits: 0, resubmitted_deposits: 0, stuck_escrow: 0 };

  return (
    <div data-testid="admin-payment-reviews">
      <div className="flex items-baseline gap-3 flex-wrap">
        <h1 className="text-2xl font-bold">Payment Reviews</h1>
        <Badge variant="secondary" className="rounded-full">{counts.total} open</Badge>
        <Button size="sm" variant="outline" onClick={load} disabled={loading} className="ml-auto" data-testid="reviews-refresh">
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>
      <p className="text-sm text-neutral-500 mt-1">Everything waiting on a human decision — top-ups awaiting proof review and orders where escrowed money is trapped.</p>

      {/* Summary chips */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
        {[
          { key: "pending_deposits",     label: "Pending top-ups",   icon: Coins,     tint: "from-emerald-50 to-emerald-100 text-emerald-800 border-emerald-200" },
          { key: "resubmitted_deposits", label: "Resubmitted",       icon: RotateCcw, tint: "from-fuchsia-50 to-fuchsia-100 text-fuchsia-800 border-fuchsia-200" },
          { key: "stuck_escrow",         label: "Stuck escrow",      icon: Snowflake, tint: "from-sky-50 to-sky-100 text-sky-800 border-sky-200" },
          { key: "total",                label: "Total open",        icon: RefreshCw, tint: "from-neutral-50 to-neutral-100 text-neutral-800 border-neutral-200" },
        ].map((k) => {
          const Icon = k.icon;
          return (
            <div key={k.key} className={`rounded-xl border bg-gradient-to-br p-3 ${k.tint}`} data-testid={`reviews-count-${k.key}`}>
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                <div className="text-[11px] uppercase tracking-wider font-semibold">{k.label}</div>
              </div>
              <div className="text-2xl font-extrabold tabular-nums mt-1">{counts[k.key]}</div>
            </div>
          );
        })}
      </div>

      {loading && !data && <div className="mt-8 text-sm text-neutral-500">Loading…</div>}

      {data && (
        <>
          {/* Priority: resubmitted (user already waited once). */}
          {counts.resubmitted_deposits > 0 && (
            <>
              <SectionHeader icon={RotateCcw} title="Resubmitted top-ups" count={counts.resubmitted_deposits} hint="Priority — buyer already waited once" />
              <div className="space-y-2">{data.resubmitted_deposits.map((d) => renderDeposit(d, true))}</div>
            </>
          )}

          {counts.pending_deposits > 0 && (
            <>
              <SectionHeader icon={Coins} title="Pending top-ups" count={counts.pending_deposits} hint="Awaiting first review" />
              <div className="space-y-2">{data.pending_deposits.map((d) => renderDeposit(d, false))}</div>
            </>
          )}

          {counts.stuck_escrow > 0 && (
            <>
              <SectionHeader icon={Snowflake} title="Stuck escrow orders" count={counts.stuck_escrow} hint="Funds trapped past the auto-release window" />
              <div className="space-y-2">{data.stuck_escrow.map(renderStuck)}</div>
            </>
          )}

          {counts.total === 0 && (
            <div className="mt-10 rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700 p-10 text-center" data-testid="reviews-empty">
              <CheckCircle2 className="h-10 w-10 text-emerald-500 mx-auto mb-3" />
              <div className="text-lg font-bold">Inbox zero</div>
              <div className="text-sm text-neutral-500 mt-1">Every top-up has been reviewed and no escrow orders are stuck. Nice work.</div>
            </div>
          )}
        </>
      )}

      {/* Proof lightbox */}
      {preview && (
        <div
          onClick={() => setPreview("")}
          className="fixed inset-0 bg-black/80 z-50 grid place-items-center p-6 cursor-zoom-out"
          data-testid="review-proof-lightbox"
        >
          <img src={preview} alt="Payment proof" className="max-h-full max-w-full rounded-lg" />
        </div>
      )}
    </div>
  );
};

export default AdminPaymentReviews;
