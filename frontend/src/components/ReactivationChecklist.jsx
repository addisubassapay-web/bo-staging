import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { ShieldCheck, Loader2, ListChecks } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

/**
 * ReactivationChecklist — mandatory post-unlock modal for sellers. Fires
 * on Profile mount if the seller has been reactivated but hasn't acked yet.
 * The Dialog cannot be dismissed until every item is checked (self-attestation
 * that they've read all guidance), preventing "click through it in a second".
 */
const ReactivationChecklist = () => {
  const [state, setState] = useState(null);
  const [checked, setChecked] = useState({});
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const { toast } = useToast();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/seller/reactivation-checklist");
      setState(data);
      setOpen(!!data.required);
    } catch (e) {
      // Non-seller users get 401/403 — silent.
      setState(null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const allChecked =
    !!state?.items?.length && state.items.every((i) => checked[i.id]);

  const ack = async () => {
    if (busy || !allChecked) return;
    setBusy(true);
    try {
      await api.post("/seller/reactivation-checklist/ack");
      toast({ title: "Thanks — you're all set", description: "Watch your health score daily this week." });
      setOpen(false);
    } catch (e) {
      toast({
        title: "Couldn't save acknowledgement",
        description: e?.response?.data?.detail || "Try again in a moment",
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  };

  if (!state?.required) return null;

  return (
    <Dialog open={open} onOpenChange={() => { /* mandatory — no external close */ }}>
      <DialogContent
        data-testid="reactivation-checklist-dialog"
        className="max-w-lg"
        // Block esc/backdrop dismissal — this is mandatory.
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-600" />
            Welcome back — a quick 60-second recap
          </DialogTitle>
          <DialogDescription>
            Your listings are live again. To keep them that way, please read and check off each item below.
            The tag <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-neutral-600"><ListChecks className="w-3 h-3" /> mandatory</span> just means we log that you saw it.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          {state.items.map((item) => (
            <label
              key={item.id}
              className="flex items-start gap-3 p-3 rounded-lg border border-neutral-200 hover:border-emerald-300 hover:bg-emerald-50/40 transition-colors cursor-pointer"
              data-testid={`reactivation-item-${item.id}`}
            >
              <Checkbox
                checked={!!checked[item.id]}
                onCheckedChange={(v) => setChecked((c) => ({ ...c, [item.id]: !!v }))}
                data-testid={`reactivation-check-${item.id}`}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="font-semibold text-sm text-neutral-900">{item.title}</div>
                <div className="text-xs text-neutral-600 mt-0.5">{item.body}</div>
              </div>
            </label>
          ))}
        </div>

        <DialogFooter>
          <div className="w-full flex items-center justify-between gap-3">
            <div className="text-xs text-neutral-500">
              {Object.values(checked).filter(Boolean).length} / {state.items.length} read
            </div>
            <Button
              onClick={ack}
              disabled={busy || !allChecked}
              data-testid="reactivation-ack-btn"
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              {busy ? (
                <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Saving</>
              ) : allChecked ? (
                <>I understand — get me back to selling</>
              ) : (
                <>Check every item to continue</>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ReactivationChecklist;
