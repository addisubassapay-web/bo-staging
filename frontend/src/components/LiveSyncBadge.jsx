import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Radio } from "lucide-react";

const LiveSyncBadge = () => {
  const [status, setStatus] = useState(null);

  const load = () => {
    api.get("/sync/status").then((r) => setStatus(r.data)).catch(() => {});
  };

  useEffect(() => {
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, []);

  if (!status) return null;

  const lastTick = status.last_live_tick ? new Date(status.last_live_tick) : null;
  const ago = lastTick ? Math.max(0, Math.round((Date.now() - lastTick.getTime()) / 1000)) : null;

  return (
    <div className="flex items-center gap-1.5 text-xs text-neutral-600" title={`Source: ${status.source}\nLast sync: ${status.last_sync_at}\nActive: ${status.active_listings}`}>
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
      </span>
      <Radio className="h-3 w-3" />
      <span className="font-medium">Live</span>
      {ago !== null && <span className="text-neutral-400 hidden sm:inline">· {ago < 60 ? `${ago}s ago` : `${Math.round(ago/60)}m ago`}</span>}
      <span className="text-neutral-400 hidden md:inline">· {status.active_listings?.toLocaleString()} live items</span>
    </div>
  );
};

export default LiveSyncBadge;
