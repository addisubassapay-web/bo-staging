import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Settings2, Bell, Loader2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";

/**
 * PickupTimingTuner — admin-only card to tune the pickup window and
 * reminder cadence. Backed by `/api/admin/settings` (allowed keys:
 * pickup_deadline_hours, pickup_reminder_hours).
 */
const PickupTimingTuner = () => {
  const [deadline, setDeadline] = useState("48");
  const [reminders, setReminders] = useState("6,1");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/settings");
      setDeadline(String(data?.pickup_deadline_hours ?? 48));
      const rh = Array.isArray(data?.pickup_reminder_hours) ? data.pickup_reminder_hours : [6, 1];
      setReminders(rh.join(","));
    } catch (e) {
      // silent — non-admin gets 403
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (saving) return;
    // Parse
    const deadlineN = parseInt(deadline, 10);
    if (isNaN(deadlineN) || deadlineN < 1 || deadlineN > 168) {
      toast({ title: "Pickup window must be 1–168 hours", variant: "destructive" });
      return;
    }
    const remindersArr = reminders
      .split(",")
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n) && n >= 1 && n <= 72);
    if (remindersArr.length === 0) {
      toast({ title: "Enter at least one reminder hour (1–72)", variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      await api.put("/admin/settings", {
        pickup_deadline_hours: deadlineN,
        pickup_reminder_hours: remindersArr,
      });
      toast({
        title: "Pickup timing updated",
        description: `Deadline: ${deadlineN}h · Reminders at ${remindersArr.join("h, ")}h before`,
      });
      load();
    } catch (e) {
      toast({
        title: "Save failed",
        description: e?.response?.data?.detail || "Try again in a moment",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-white p-4 flex items-center gap-2 text-sm text-neutral-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading pickup settings…
      </div>
    );
  }

  return (
    <div
      data-testid="pickup-timing-tuner"
      className="rounded-xl border border-neutral-200 bg-white p-4 sm:p-5 space-y-4"
    >
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
          <Settings2 className="w-4 h-4 text-blue-600" />
        </div>
        <div className="flex-1">
          <div className="font-semibold text-neutral-900">Pickup timing</div>
          <div className="text-xs text-neutral-500">
            Tune how long sellers have to accept an order and when we send reminders before auto-cancel.
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block text-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-1 block">
            Pickup window (hours)
          </span>
          <Input
            type="number"
            min="1"
            max="168"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
            data-testid="pickup-tuner-deadline"
            className="h-10"
          />
          <div className="text-[11px] text-neutral-500 mt-1">
            Sellers must Pick &amp; Deliver within this many hours or the buyer is auto-refunded.
          </div>
        </label>
        <label className="block text-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-1 flex items-center gap-1.5">
            <Bell className="w-3 h-3" /> Reminder cadence (hours before deadline)
          </span>
          <Input
            type="text"
            value={reminders}
            onChange={(e) => setReminders(e.target.value)}
            placeholder="e.g. 6, 1"
            data-testid="pickup-tuner-reminders"
            className="h-10 font-mono"
          />
          <div className="text-[11px] text-neutral-500 mt-1">
            Comma-separated. Each entry (1–72) sends an email + notify when the deadline is that far away.
          </div>
        </label>
      </div>

      <div className="flex justify-end">
        <Button
          onClick={save}
          disabled={saving}
          data-testid="pickup-tuner-save"
          className="bg-[#DC2626] hover:bg-[#e01a19] text-white"
        >
          {saving ? (
            <>
              <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Saving
            </>
          ) : (
            <>
              <Check className="w-4 h-4 mr-1.5" /> Save timing
            </>
          )}
        </Button>
      </div>
    </div>
  );
};

export default PickupTimingTuner;
