import React, { useRef, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { RefreshCw, ImagePlus, AlertCircle } from "lucide-react";

/**
 * One-tap resubmit for a rejected deposit. Uploads a new screenshot (or a
 * corrected reference) and flips the deposit back to `pending` via
 * `POST /api/wallet/deposits/{id}/resubmit`.
 *
 * The original amount / method / currency are read-only — accounting stays
 * traceable to the first submission. Backend requires at least one changed
 * field before it'll accept the resubmit.
 */
const DepositResubmit = ({ deposit, onSuccess }) => {
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [screenshotUrl, setScreenshotUrl] = useState("");
  const [reference, setReference] = useState(deposit.reference || "");
  const fileRef = useRef(null);
  const { toast } = useToast();

  const openDialog = () => {
    setScreenshotUrl("");
    setReference(deposit.reference || "");
    setOpen(true);
  };

  const uploadFile = async (file) => {
    if (!file) return;
    if (!/^image\//.test(file.type)) {
      toast({ title: "Only image uploads are allowed", variant: "destructive" });
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast({ title: "Image is larger than 10 MB", variant: "destructive" });
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", "deposit-proof");
      const r = await api.post("/upload/public-image", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setScreenshotUrl(r.data?.url || "");
      toast({ title: "Screenshot uploaded" });
    } catch (err) {
      toast({ title: "Upload failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    const referenceChanged = reference.trim() && reference.trim() !== (deposit.reference || "");
    if (!screenshotUrl && !referenceChanged) {
      toast({ title: "Attach a new screenshot or update the reference before resubmitting.", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {};
      if (screenshotUrl) payload.screenshot_url = screenshotUrl;
      if (referenceChanged) payload.reference = reference.trim();
      const r = await api.post(`/wallet/deposits/${deposit.id}/resubmit`, payload);
      toast({ title: "Deposit resubmitted", description: "Admins will review your new proof shortly." });
      setOpen(false);
      onSuccess?.(r.data);
    } catch (err) {
      toast({ title: "Resubmit failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={openDialog}
        className="h-8 rounded-full border-rose-300 text-rose-700 hover:bg-rose-50"
        data-testid={`deposit-resubmit-btn-${deposit.id}`}
      >
        <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
        Resubmit
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md" data-testid={`deposit-resubmit-dialog-${deposit.id}`}>
          <DialogHeader>
            <DialogTitle>Resubmit deposit</DialogTitle>
          </DialogHeader>

          {deposit.admin_note && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 flex items-start gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold">Why it was rejected</div>
                <div>{deposit.admin_note}</div>
              </div>
            </div>
          )}

          <div className="text-sm text-neutral-600 dark:text-neutral-300">
            <div className="grid grid-cols-2 gap-3 mb-4 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 p-3">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">Amount</div>
                <div className="text-lg font-bold tabular-nums">${Number(deposit.amount).toFixed(2)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">Method</div>
                <div className="text-sm font-semibold capitalize">{deposit.method === "crypto" ? `Crypto · ${deposit.currency || ""}` : (deposit.currency || "Manual")}</div>
              </div>
            </div>

            <Label className="text-xs">New screenshot</Label>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => uploadFile(e.target.files?.[0])}
              data-testid={`deposit-resubmit-file-${deposit.id}`}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="mt-1 w-full min-h-[44px] rounded-lg border-2 border-dashed border-neutral-300 dark:border-neutral-700 hover:border-[#FF211F] hover:bg-neutral-50 dark:hover:bg-neutral-900 transition inline-flex items-center justify-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 disabled:opacity-60"
              data-testid={`deposit-resubmit-upload-${deposit.id}`}
            >
              <ImagePlus className="h-4 w-4" />
              {uploading ? "Uploading…" : screenshotUrl ? "Replace uploaded screenshot" : "Upload new screenshot"}
            </button>
            {screenshotUrl && (
              <img
                src={screenshotUrl}
                alt="New proof"
                className="mt-2 w-full max-h-48 object-contain rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900"
              />
            )}

            <div className="mt-4">
              <Label className="text-xs">Reference / TX hash</Label>
              <Input
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                placeholder="Update if the original was wrong"
                className="mt-1"
                data-testid={`deposit-resubmit-reference-${deposit.id}`}
              />
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={submitting}>Cancel</Button>
            <Button
              onClick={submit}
              disabled={submitting || uploading || (!screenshotUrl && reference.trim() === (deposit.reference || ""))}
              className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:brightness-110"
              data-testid={`deposit-resubmit-submit-${deposit.id}`}
            >
              {submitting ? "Resubmitting…" : "Resubmit for review"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default DepositResubmit;
