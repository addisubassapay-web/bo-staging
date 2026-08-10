import React from "react";
import { Badge } from "@/components/ui/badge";
import { ShieldCheck, Mail, Phone, Store as StoreIcon } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

// A tiny pill with an icon; used to show verified email/phone/seller status.
const Pill = ({ icon: Icon, label, tone = "emerald", tip }) => {
  const tones = {
    emerald: "bg-emerald-100 text-emerald-800 border-emerald-200",
    slate: "bg-neutral-100 text-neutral-600 border-neutral-200",
    amber: "bg-amber-100 text-amber-800 border-amber-200",
  };
  const content = (
    <Badge variant="outline" className={`gap-1 border ${tones[tone] || tones.emerald} font-medium`}>
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
  if (!tip) return content;
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild><span>{content}</span></TooltipTrigger>
        <TooltipContent>{tip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

// Props: `user` (with email_verified, phone_verified, seller_status) — omits unverified pills.
export const VerificationBadges = ({ user, size = "sm", showLabels = true, className = "" }) => {
  if (!user) return null;
  const pills = [];
  if (user.email_verified) pills.push({ key: "e", icon: Mail, label: showLabels ? "Email" : "", tip: "Email verified" });
  if (user.phone_verified) pills.push({ key: "p", icon: Phone, label: showLabels ? "Phone" : "", tip: "Phone verified" });
  if (user.seller_status === "approved") pills.push({ key: "s", icon: ShieldCheck, label: showLabels ? "Seller" : "", tip: "Approved seller" });
  if (pills.length === 0) return null;
  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`} data-testid="verification-badges">
      {pills.map((p) => (
        <Pill key={p.key} icon={p.icon} label={p.label} tip={p.tip} />
      ))}
    </div>
  );
};

// A single seller-tier / store-verified pill for store cards
export const StoreTierBadge = ({ tier }) => {
  if (!tier || tier === "none") return null;
  const map = {
    bronze: { bg: "bg-amber-50 text-amber-700 border-amber-200", label: "Bronze verified" },
    silver: { bg: "bg-slate-100 text-slate-700 border-slate-200", label: "Silver verified" },
    gold: { bg: "bg-yellow-50 text-yellow-800 border-yellow-200", label: "Gold verified" },
  };
  const t = map[tier] || map.bronze;
  return (
    <Badge variant="outline" className={`gap-1 border ${t.bg}`}>
      <StoreIcon className="h-3 w-3" />
      {t.label}
    </Badge>
  );
};

export default VerificationBadges;
