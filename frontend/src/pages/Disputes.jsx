import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import {
  AlertCircle, Upload, ImagePlus, X, Package, Clock, CheckCircle2, XCircle,
  ShieldAlert, MessageSquareWarning,
} from "lucide-react";

const money = (n) => `$${Number(n || 0).toFixed(2)}`;

const REASONS = [
  { value: "not_as_described", label: "Item not as described" },
  { value: "damaged",          label: "Arrived damaged" },
  { value: "not_received",     label: "Never received" },
  { value: "counterfeit",      label: "Counterfeit / fake" },
  { value: "other",            label: "Other issue" },
];
const REASON_LABEL = Object.fromEntries(REASONS.map((r) => [r.value, r.label]));

const STATUS_META = {
  open:      { label: "Open",      icon: Clock,        cls: "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30" },
  reviewing: { label: "Reviewing", icon: ShieldAlert,  cls: "bg-sky-100 text-sky-800 border-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-500/30" },
  refunded:  { label: "Refunded",  icon: CheckCircle2, cls: "bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30" },
  rejected:  { label: "Rejected",  icon: XCircle,      cls: "bg-rose-100 text-rose-800 border-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30" },
};

const StatusBadge = ({ status }) => {
  const m = STATUS_META[status] || STATUS_META.open;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${m.cls}`}>
      <Icon className="h-3 w-3" /> {m.label}
    </span>
  );
};

const NewDisputeDialog = ({ open, onOpenChange, orders, onCreated }) => {
  const { toast } = useToast();
  const [orderId, setOrderId] = useState("");
  const [reason, setReason] = useState("not_as_described");
  const [description, setDescription] = useState("");
  const [photos, setPhotos] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setOrderId(orders?.[0]?.id || "");
      setReason("not_as_described");
      setDescription("");
      setPhotos([]);
    }
  }, [open, orders]);

  const onFiles = useCallback(async (fileList) => {
    const files = Array.from(fileList || []).slice(0, 8 - photos.length);
    if (!files.length) return;
    setUploading(true);
    try {
      const uploaded = [];
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        const r = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
        if (r.data?.url) uploaded.push(r.data.url);
      }
      setPhotos((p) => [...p, ...uploaded].slice(0, 8));
    } catch (e) {
      toast({ title: "Upload failed", description: e?.response?.data?.detail || "Try again.", variant: "destructive" });
    } finally { setUploading(false); }
  }, [photos.length, toast]);

  const submit = async () => {
    if (!orderId) return toast({ title: "Pick an order", variant: "destructive" });
    if (!description.trim()) return toast({ title: "Describe the issue", variant: "destructive" });
    setSubmitting(true);
    try {
      await api.post("/disputes", { order_id: orderId, reason, description: description.trim(), photos });
      toast({ title: "Dispute submitted", description: "Our team will review shortly." });
      onOpenChange(false);
      onCreated?.();
    } catch (e) {
      toast({ title: "Could not submit dispute", description: e?.response?.data?.detail || "Try again.", variant: "destructive" });
    } finally { setSubmitting(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="new-dispute-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquareWarning className="h-5 w-5 text-[#FF211F]" /> Open a dispute
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-neutral-500">Order</Label>
            {orders.length === 0 ? (
              <p className="mt-2 text-sm text-neutral-500">You have no eligible orders to dispute.</p>
            ) : (
              <Select value={orderId} onValueChange={setOrderId}>
                <SelectTrigger data-testid="dispute-order-select"><SelectValue placeholder="Choose order" /></SelectTrigger>
                <SelectContent>
                  {orders.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.listing_title} · {money(o.amount)} · #{o.id.slice(0, 6)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-neutral-500">What went wrong?</Label>
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger data-testid="dispute-reason-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {REASONS.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-neutral-500">Describe the issue</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Tell us what happened. Include dates, condition, packaging, and any seller messages…"
              className="min-h-[100px] mt-1"
              data-testid="dispute-description"
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-neutral-500 flex items-center justify-between">
              <span>Photo evidence <span className="text-neutral-400">(optional, up to 8)</span></span>
              <label className="text-[#FF7A18] hover:underline cursor-pointer inline-flex items-center gap-1">
                <ImagePlus className="h-4 w-4" /> Add photos
                <input
                  type="file" accept="image/*" multiple hidden
                  onChange={(e) => onFiles(e.target.files)}
                  data-testid="dispute-photo-input"
                />
              </label>
            </Label>
            {photos.length > 0 && (
              <div className="mt-2 grid grid-cols-4 gap-2">
                {photos.map((url, i) => (
                  <div key={i} className="relative aspect-square rounded-lg overflow-hidden bg-neutral-100 dark:bg-neutral-800 group">
                    <img src={url.startsWith("http") ? url : `${process.env.REACT_APP_BACKEND_URL}${url}?auth=${localStorage.getItem("mercari_token") || ""}`} alt="" className="h-full w-full object-cover" />
                    <button
                      onClick={() => setPhotos((p) => p.filter((_, idx) => idx !== i))}
                      className="absolute top-1 right-1 h-6 w-6 rounded-full bg-black/60 text-white grid place-items-center opacity-0 group-hover:opacity-100 transition"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {uploading && <div className="text-xs text-neutral-500 mt-1 flex items-center gap-1"><Upload className="h-3 w-3 animate-pulse" /> Uploading…</div>}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            onClick={submit}
            disabled={submitting || uploading || !orderId || !description.trim()}
            className="bg-[#FF211F] hover:bg-[#e01d1b]"
            data-testid="dispute-submit"
          >
            {submitting ? "Submitting…" : "Submit dispute"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const DisputeCard = ({ d, currentUserId }) => {
  const iAmBuyer = d.buyer_id === currentUserId;
  return (
    <div
      className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 sm:p-5"
      data-testid={`dispute-card-${d.id}`}
    >
      <div className="flex flex-wrap items-start gap-4">
        <img
          src={d.listing_image}
          alt=""
          className="h-16 w-16 rounded-xl object-cover bg-neutral-100 dark:bg-neutral-800"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={d.status} />
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {new Date(d.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
            </span>
            <span className="text-xs text-neutral-400 dark:text-neutral-500 font-mono">#{d.id.slice(0, 6)}</span>
          </div>
          <div className="mt-1 font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-1">
            {d.listing_title}
          </div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400">
            {iAmBuyer ? "Filed by you" : `Filed by ${d.buyer_name}`} · {REASON_LABEL[d.reason] || d.reason} · <span className="font-medium text-neutral-700 dark:text-neutral-300">{money(d.amount)}</span>
          </div>
        </div>
      </div>

      <p className="mt-3 text-sm text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap">
        {d.description}
      </p>

      {d.photos?.length > 0 && (
        <div className="mt-3 grid grid-cols-4 sm:grid-cols-6 gap-2">
          {d.photos.map((url, i) => (
            <a
              key={i}
              href={url.startsWith("http") ? url : `${process.env.REACT_APP_BACKEND_URL}${url}?auth=${localStorage.getItem("mercari_token") || ""}`}
              target="_blank" rel="noreferrer"
              className="block aspect-square rounded-lg overflow-hidden bg-neutral-100 dark:bg-neutral-800 hover:ring-2 hover:ring-[#FF7A18]"
              data-testid={`dispute-photo-${d.id}-${i}`}
            >
              <img
                src={url.startsWith("http") ? url : `${process.env.REACT_APP_BACKEND_URL}${url}?auth=${localStorage.getItem("mercari_token") || ""}`}
                alt="evidence" className="h-full w-full object-cover"
              />
            </a>
          ))}
        </div>
      )}

      {d.resolution && (
        <div className="mt-3 rounded-lg bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-700 p-3 text-sm">
          <div className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400 font-medium mb-1">Resolution</div>
          <div className="text-neutral-800 dark:text-neutral-200">{d.resolution}</div>
        </div>
      )}
    </div>
  );
};

const Disputes = () => {
  const { user, loading } = useAuth();
  const [disputes, setDisputes] = useState([]);
  const [eligibleOrders, setEligibleOrders] = useState([]);
  const [tab, setTab] = useState("mine");
  const [dialogOpen, setDialogOpen] = useState(false);

  const load = useCallback(() => {
    if (!user) return;
    api.get("/disputes/mine").then((r) => setDisputes(r.data)).catch(() => {});
    // Eligible orders = orders the user bought that aren't already open-disputed
    api.get("/orders", { params: { role: "buyer" } }).then((r) => {
      const eligible = (r.data || []).filter((o) => ["paid", "shipped", "delivered"].includes(o.status));
      setEligibleOrders(eligible);
    }).catch(() => {});
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const mineAsBuyer = useMemo(() => disputes.filter((d) => d.buyer_id === user?.id), [disputes, user]);
  const mineAsSeller = useMemo(() => disputes.filter((d) => d.seller_id === user?.id), [disputes, user]);
  const shown = tab === "mine" ? mineAsBuyer : mineAsSeller;
  const eligibleForNew = eligibleOrders.filter((o) =>
    !mineAsBuyer.some((d) => d.order_id === o.id && ["open", "reviewing"].includes(d.status))
  );

  if (loading) return <div className="max-w-5xl mx-auto px-4 py-16 text-neutral-500">Loading…</div>;
  if (!user) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <p className="text-neutral-700 dark:text-neutral-300">
          Please <Link to="/login" className="text-[#FF7A18] underline">log in</Link> to view your disputes.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8" data-testid="disputes-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <AlertCircle className="h-7 w-7 text-[#FF211F]" /> Disputes &amp; Returns
          </h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Not what you expected? Open a case, share evidence, and our team will step in.
          </p>
        </div>
        <Button
          onClick={() => setDialogOpen(true)}
          className="bg-[#FF211F] hover:bg-[#e01d1b] gap-1.5"
          data-testid="open-new-dispute-btn"
          disabled={eligibleForNew.length === 0}
          title={eligibleForNew.length === 0 ? "No eligible orders" : "Open a new dispute"}
        >
          <MessageSquareWarning className="h-4 w-4" /> Open new dispute
        </Button>
      </div>

      <div className="mt-6 inline-flex rounded-full border border-neutral-200 dark:border-neutral-800 p-1 bg-white dark:bg-neutral-900">
        <button
          onClick={() => setTab("mine")}
          className={`px-4 h-9 rounded-full text-sm font-medium transition ${
            tab === "mine"
              ? "bg-[#FF211F] text-white shadow"
              : "text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"
          }`}
          data-testid="tab-mine"
        >
          Filed by me ({mineAsBuyer.length})
        </button>
        <button
          onClick={() => setTab("against")}
          className={`px-4 h-9 rounded-full text-sm font-medium transition ${
            tab === "against"
              ? "bg-[#FF211F] text-white shadow"
              : "text-neutral-600 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100"
          }`}
          data-testid="tab-against"
        >
          Against my sales ({mineAsSeller.length})
        </button>
      </div>

      <div className="mt-6 space-y-3">
        {shown.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-10 text-center" data-testid="disputes-empty">
            <Package className="h-10 w-10 text-neutral-300 dark:text-neutral-600 mx-auto" />
            <div className="mt-3 font-semibold text-neutral-800 dark:text-neutral-200">
              {tab === "mine" ? "No disputes filed" : "No disputes against your sales"}
            </div>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
              {tab === "mine"
                ? "If an item arrives damaged, isn't as described, or never shows up, come back here."
                : "Great news — buyers are happy with your orders."}
            </p>
          </div>
        ) : (
          shown.map((d) => <DisputeCard key={d.id} d={d} currentUserId={user.id} />)
        )}
      </div>

      <NewDisputeDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        orders={eligibleForNew}
        onCreated={load}
      />
    </div>
  );
};

export default Disputes;
