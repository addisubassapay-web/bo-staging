import React, { useEffect, useState } from "react";
import { Clock } from "lucide-react";

const AUTO_CONFIRM_HOURS = 72; // matches backend AUTO_CONFIRM_AFTER_HOURS default

const fmtRemaining = (ms) => {
  if (ms <= 0) return null;
  const totalMin = Math.floor(ms / 60000);
  const days = Math.floor(totalMin / (60 * 24));
  const hours = Math.floor((totalMin - days * 60 * 24) / 60);
  const mins = totalMin - days * 60 * 24 - hours * 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
};

/**
 * Small pill shown on a seller's in-transit order the moment tracking
 * reports "delivered". Counts down to the auto-release timestamp (delivered_at
 * + 72h) so the seller knows exactly when their money will unlock without any
 * buyer action. Renders nothing outside that window.
 */
const AutoConfirmCountdown = ({ order }) => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  if (!order || order.funds_released) return null;
  const status = order.shipping_status || order.status;
  const deliveredRaw = order.shipping_delivered_at;
  if (!deliveredRaw || status !== "delivered") return null;

  const deliveredAt = new Date(deliveredRaw).getTime();
  if (Number.isNaN(deliveredAt)) return null;
  const releaseAt = deliveredAt + AUTO_CONFIRM_HOURS * 3600 * 1000;
  const remaining = releaseAt - now;
  const label = fmtRemaining(remaining);
  const soon = remaining < 6 * 3600 * 1000; // <6h left → highlight

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium rounded-full px-2 py-0.5 border ${
        remaining <= 0
          ? "bg-emerald-50 text-emerald-800 border-emerald-200"
          : soon
            ? "bg-orange-50 text-orange-800 border-orange-200"
            : "bg-sky-50 text-sky-800 border-sky-200"
      }`}
      title={
        remaining <= 0
          ? "Escrow release is due — the auto-confirm sweep will unlock funds on its next hourly tick."
          : `Auto-releases at ${new Date(releaseAt).toLocaleString()} if the buyer doesn't confirm.`
      }
      data-testid={`auto-confirm-countdown-${order.id}`}
    >
      <Clock className="h-3 w-3" />
      {remaining <= 0 ? "Auto-releasing…" : `Auto-releases in ${label}`}
    </span>
  );
};

export default AutoConfirmCountdown;
