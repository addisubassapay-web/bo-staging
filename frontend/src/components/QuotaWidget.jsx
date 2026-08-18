import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Progress } from "@/components/ui/progress";
import { Zap, TrendingUp } from "lucide-react";

const QuotaWidget = () => {
  const [q, setQ] = useState(null);

  const load = () => {
    api.get("/scraper/quota").then((r) => setQ(r.data)).catch(() => setQ(null));
  };
  useEffect(() => {
    load();
    const i = setInterval(load, 15000);
    return () => clearInterval(i);
  }, []);

  if (!q) return null;
  const pct = q.cap ? Math.min(100, Math.round((q.used / q.cap) * 100)) : 0;
  const isLow = q.remaining < Math.max(20, q.cap * 0.1);

  return (
    <div className="rounded-xl border border-neutral-200 bg-white px-4 py-3" data-testid="quota-widget">
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 font-semibold">
          <Zap className={`h-4 w-4 ${isLow ? "text-red-500" : "text-emerald-600"}`} />
          Zyte credits — {q.month}
        </div>
        <div className={`tabular-nums font-bold ${isLow ? "text-red-600" : "text-neutral-900"}`}>
          <span>{q.remaining}</span>
          <span className="text-neutral-400"> / {q.cap}</span>
        </div>
      </div>
      <Progress value={pct} className={`h-1.5 mt-2 ${isLow ? "[&>div]:bg-red-500" : "[&>div]:bg-emerald-500"}`} />
      <div className="flex items-center justify-between text-xs mt-1.5 text-neutral-500">
        <span>{q.used} used this month</span>
        {isLow && <span className="text-red-600 font-medium flex items-center gap-1"><TrendingUp className="h-3 w-3" /> Running low</span>}
      </div>
    </div>
  );
};

export default QuotaWidget;
