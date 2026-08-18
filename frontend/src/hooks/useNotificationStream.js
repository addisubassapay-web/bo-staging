import { useEffect, useRef } from "react";
import api from "@/lib/api";

/**
 * Poll the notifications endpoint on an interval and fire a callback for
 * every new row. Used by the Wallet page to surface live "Funds released"
 * toasts the instant escrow unlocks — no page refresh needed.
 *
 * Simple long-poll is used instead of SSE/WebSocket because it survives the
 * Kubernetes ingress' idle-connection timeouts and needs zero extra infra.
 *
 * @param onNew        (Notification[]) => void — called with new rows
 * @param types        CSV of Notification.type values to filter server-side
 * @param intervalMs   poll frequency, default 15s
 * @param enabled      pause/resume the stream
 */
export const useNotificationStream = (
  onNew,
  types = "wallet,payout",
  intervalMs = 15000,
  enabled = true,
) => {
  const sinceRef = useRef(new Date().toISOString());
  const cbRef = useRef(onNew);
  cbRef.current = onNew;

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let timer = null;

    const tick = async () => {
      try {
        const { data } = await api.get("/notifications", {
          params: { since: sinceRef.current, types, limit: 20 },
        });
        if (cancelled) return;
        if (Array.isArray(data) && data.length > 0) {
          // Server returns newest-first; advance the cursor to the newest
          // seen so the next poll only grabs strictly-newer rows.
          const newest = data[0]?.created_at;
          if (newest) sinceRef.current = newest;
          // Fire callback with rows in chronological order (oldest first)
          // so multiple toasts stack in the correct sequence.
          cbRef.current?.([...data].reverse());
        }
      } catch { /* transient network errors are non-fatal */ }
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    };

    timer = setTimeout(tick, intervalMs);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [types, intervalMs, enabled]);
};
