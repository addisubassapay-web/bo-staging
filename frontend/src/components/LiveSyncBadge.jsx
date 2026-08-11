import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Radio } from "lucide-react";

const REFRESH_MS = 30000;

const fmtDuration = (secs) => {
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
  return `${Math.floor(secs / 86400)}d`;
};

const LiveSyncBadge = () => {
  const [status, setStatus] = useState(null);
  const [nowTick, setNowTick] = useState(Date.now());
  const [nextIn, setNextIn] = useState(Math.round(REFRESH_MS / 1000));

  const load = () => api.get("/sync/status").then((r) => { setStatus(r.data); setNextIn(Math.round(REFRESH_MS / 1000)); }).catch(() => {});

  useEffect(() => {
    load();
    const iv = setInterval(load, REFRESH_MS);
    const tick = setInterval(() => {
      setNowTick(Date.now());
      setNextIn((n) => (n <= 1 ? Math.round(REFRESH_MS / 1000) : n - 1));
    }, 1000);
    return () => { clearInterval(iv); clearInterval(tick); };
  }, []);

  if (!status) return null;

  const lastTick = status.last_live_tick ? new Date(status.last_live_tick) : null;
  const agoSecs = lastTick ? Math.max(0, Math.round((nowTick - lastTick.getTime()) / 1000)) : null;

  return (
    <div
      className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-300"
      title={`Source: ${status.source}\nLast sync: ${status.last_sync_at}\nActive: ${status.active_listings}\nNext refresh in ${nextIn}s`}
      data-testid="live-sync-badge"
    >
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
      </span>
      <Radio className="h-3 w-3" />
      <span className="font-medium">Live</span>
      {agoSecs !== null && (
        <span className="text-neutral-400 hidden sm:inline tabular-nums" data-testid="live-sync-ago">· {fmtDuration(agoSecs)} ago</span>
      )}
      <span className="text-neutral-400 hidden lg:inline tabular-nums" data-testid="live-sync-next">· next in {nextIn}s</span>
      <span className="text-neutral-400 hidden xl:inline tabular-nums">· {status.active_listings?.toLocaleString()} live items</span>
    </div>
  );
};

export default LiveSyncBadge;
