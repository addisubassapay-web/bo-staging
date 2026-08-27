import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Mail, ShoppingBag, TrendingUp, Wallet, CreditCard, AlertCircle, Bell } from "lucide-react";

const CATEGORIES = [
  { key: "order",   label: "Order updates",         desc: "Purchase confirmations, shipping updates, delivery.",           icon: ShoppingBag },
  { key: "sale",    label: "Sales & payouts",       desc: "New sales, funds frozen, funds released.",                      icon: TrendingUp },
  { key: "wallet",  label: "Wallet activity",       desc: "Deposits approved/declined, wallet credits, refunds.",          icon: Wallet },
  { key: "payout",  label: "Withdrawals & payouts", desc: "Withdrawal requests processed or on hold.",                     icon: CreditCard },
  { key: "dispute", label: "Disputes",              desc: "New dispute filings and resolution status.",                    icon: AlertCircle },
  { key: "system",  label: "Account & security",    desc: "Password resets, lockouts, account safety alerts.",             icon: Bell },
];

const EmailPreferences = () => {
  const { user, refresh } = useAuth();
  const { toast } = useToast();
  const [prefs, setPrefs] = useState(() => ({
    order: true, sale: true, wallet: true, payout: true, dispute: true, system: true,
  }));
  const [saving, setSaving] = useState(null); // holds key currently being toggled

  useEffect(() => {
    const initial = user?.email_prefs;
    if (initial && typeof initial === "object") {
      setPrefs((p) => ({ ...p, ...initial }));
    }
  }, [user]);

  const toggle = async (key, value) => {
    setSaving(key);
    // Optimistic update
    setPrefs((p) => ({ ...p, [key]: value }));
    try {
      const { data } = await api.put("/me/email-prefs", { [key]: value });
      if (data?.email_prefs) setPrefs((p) => ({ ...p, ...data.email_prefs }));
      toast({
        title: value ? "You'll get these emails" : "Opted out",
        description: CATEGORIES.find((c) => c.key === key)?.label,
      });
      // Refresh auth context so email_prefs stays in sync
      if (refresh) refresh().catch(() => {});
    } catch (e) {
      // Revert
      setPrefs((p) => ({ ...p, [key]: !value }));
      toast({
        title: "Couldn't update preference",
        description: e?.response?.data?.detail || "Try again",
        variant: "destructive",
      });
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-5 max-w-2xl" data-testid="email-preferences">
      <div className="rounded-2xl border border-neutral-200 bg-white p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-full bg-gradient-to-br from-[#FFE9E7] to-[#FFC9C4] text-[#FF211F] grid place-items-center shrink-0">
            <Mail className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold">Email preferences</h3>
            <p className="text-sm text-neutral-600 mt-1">
              Choose which transactional emails you want to receive from Mercari-Smarthub. You can change this any time. Account safety alerts always send even if disabled elsewhere.
            </p>
          </div>
        </div>

        <div className="mt-6 divide-y divide-neutral-100">
          {CATEGORIES.map(({ key, label, desc, icon: Icon }) => {
            const value = prefs[key] !== false;
            return (
              <div key={key} className="py-4 flex items-start gap-4">
                <div className="h-8 w-8 rounded-lg bg-neutral-100 text-neutral-700 grid place-items-center shrink-0">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{label}</div>
                  <div className="text-xs text-neutral-500 mt-0.5">{desc}</div>
                </div>
                <Switch
                  checked={value}
                  onCheckedChange={(v) => toggle(key, v)}
                  disabled={saving === key}
                  data-testid={`email-pref-${key}`}
                />
              </div>
            );
          })}
        </div>
      </div>
      <p className="text-xs text-neutral-500 px-1">
        We never send marketing spam. Preferences apply immediately across all your devices.
      </p>
    </div>
  );
};

export default EmailPreferences;
