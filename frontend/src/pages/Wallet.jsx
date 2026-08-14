import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Wallet as WalletIcon, ArrowDownRight, ArrowUpRight, Clock, CheckCircle2, XCircle, Snowflake } from "lucide-react";

const typeMeta = {
  sale: { label: "Sale", color: "text-green-600" },
  sale_frozen: { label: "Sale (frozen)", color: "text-amber-600" },
  sale_released: { label: "Sale released", color: "text-emerald-600" },
  affiliate: { label: "Affiliate", color: "text-blue-600" },
  referral: { label: "Referral", color: "text-purple-600" },
  dropship: { label: "Dropship", color: "text-teal-600" },
  dropship_frozen: { label: "Dropship (frozen)", color: "text-amber-600" },
  dropship_released: { label: "Dropship released", color: "text-emerald-600" },
  bonus: { label: "Bonus", color: "text-amber-600" },
  adjustment: { label: "Adjustment", color: "text-neutral-600" },
  refund: { label: "Refund", color: "text-blue-600" },
  withdrawal: { label: "Withdrawal", color: "text-red-600" },
};

const statusIcon = (s) => {
  if (s === "paid") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
  if (s === "rejected") return <XCircle className="h-4 w-4 text-red-500" />;
  return <Clock className="h-4 w-4 text-amber-500" />;
};

const Wallet = () => {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [wdOpen, setWdOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [accountInfo, setAccountInfo] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => api.get("/wallet").then((r) => setData(r.data));

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login"); return; }
    load();
  }, [user, loading, navigate]);

  const requestWithdrawal = async () => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { toast({ title: "Enter a valid amount", variant: "destructive" }); return; }
    setSubmitting(true);
    try {
      await api.post("/wallet/withdraw", { amount: amt, account_info: accountInfo });
      toast({ title: "Withdrawal requested", description: "An admin will review and process it." });
      setWdOpen(false);
      setAmount("");
      setAccountInfo("");
      await refresh();
      await load();
    } catch (err) {
      toast({ title: "Failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  if (!data) return <div className="max-w-4xl mx-auto px-4 py-8">Loading…</div>;

  const earnedByType = data.transactions.reduce((acc, t) => {
    if (t.amount > 0) acc[t.type] = (acc[t.type] || 0) + t.amount;
    return acc;
  }, {});

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center gap-2 mb-6">
        <WalletIcon className="h-6 w-6 text-[#FF211F]" />
        <h1 className="text-3xl font-bold">Wallet</h1>
      </div>

      <div className="grid md:grid-cols-3 gap-4 mb-8">
        <div className="md:col-span-2 bg-gradient-to-br from-[#FF211F] to-[#c81816] text-white rounded-xl p-6">
          <div className="text-sm opacity-90">Available balance</div>
          <div className="text-4xl font-bold mt-2" data-testid="wallet-available">{formatPrice(data.balance)}</div>
          {data.frozen_balance > 0 && (
            <div className="mt-3 inline-flex items-center gap-1.5 text-xs bg-white/15 backdrop-blur-sm rounded-full px-3 py-1" data-testid="wallet-frozen-chip">
              <Snowflake className="h-3.5 w-3.5" />
              <span>Frozen: <span className="font-semibold tabular-nums">{formatPrice(data.frozen_balance)}</span></span>
              <span className="opacity-80">· released after delivery is confirmed</span>
            </div>
          )}
          <div className="mt-4 flex gap-2">
            <Dialog open={wdOpen} onOpenChange={setWdOpen}>
              <DialogTrigger asChild>
                <Button variant="secondary" className="bg-white text-[#FF211F] hover:bg-neutral-100">Withdraw</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Request withdrawal</DialogTitle></DialogHeader>
                <div className="space-y-3">
                  <div><Label>Amount</Label><Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" /></div>
                  <div><Label>Account info (bank, PayPal, etc.)</Label><Input value={accountInfo} onChange={(e) => setAccountInfo(e.target.value)} placeholder="Optional — admin will see this" /></div>
                  <p className="text-xs text-neutral-500">Withdrawals are processed by admin. Mocked payout — no real money is transferred.</p>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setWdOpen(false)}>Cancel</Button>
                  <Button className="bg-[#FF211F] hover:bg-[#e01d1b]" onClick={requestWithdrawal} disabled={submitting}>
                    {submitting ? "Submitting…" : "Request"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        <div className="bg-white border border-neutral-200 rounded-xl p-5">
          <div className="text-xs uppercase text-neutral-500 mb-2">Earnings by source</div>
          {Object.keys(earnedByType).length === 0 ? (
            <div className="text-sm text-neutral-500">No earnings yet.</div>
          ) : (
            <div className="space-y-2">
              {Object.entries(earnedByType).map(([k, v]) => (
                <div key={k} className="flex justify-between text-sm">
                  <span className={typeMeta[k]?.color || ""}>{typeMeta[k]?.label || k}</span>
                  <span className="font-medium">{formatPrice(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {data.pending_withdrawals?.length > 0 && (
        <div className="mb-8">
          <h2 className="font-semibold mb-3">Pending withdrawals</h2>
          <div className="space-y-2">
            {data.pending_withdrawals.map((w) => (
              <div key={w.id} className="flex items-center justify-between border border-neutral-200 rounded-lg p-3">
                <div className="flex items-center gap-3">
                  {statusIcon(w.status)}
                  <div>
                    <div className="font-medium">{formatPrice(w.amount)}</div>
                    <div className="text-xs text-neutral-500">Requested {new Date(w.created_at).toLocaleDateString()}</div>
                  </div>
                </div>
                <Badge variant="secondary" className="capitalize">{w.status}</Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="font-semibold mb-3">Transactions</h2>
        {data.transactions.length === 0 ? (
          <div className="text-center py-10 border border-dashed rounded-xl text-neutral-500">No transactions yet.</div>
        ) : (
          <div className="border border-neutral-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-left">
                <tr>
                  <th className="p-3">Type</th>
                  <th className="p-3">Description</th>
                  <th className="p-3 text-right">Amount</th>
                  <th className="p-3 text-right">Balance</th>
                  <th className="p-3 text-right">Date</th>
                </tr>
              </thead>
              <tbody>
                {data.transactions.map((t) => (
                  <tr key={t.id} className="border-t border-neutral-100">
                    <td className="p-3">
                      <Badge variant="secondary" className={typeMeta[t.type]?.color || ""}>{typeMeta[t.type]?.label || t.type}</Badge>
                    </td>
                    <td className="p-3 text-neutral-700">{t.description}</td>
                    <td className={`p-3 text-right font-medium ${t.amount >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {t.amount >= 0 ? <ArrowDownRight className="h-3 w-3 inline mr-0.5" /> : <ArrowUpRight className="h-3 w-3 inline mr-0.5" />}
                      {formatPrice(Math.abs(t.amount))}
                    </td>
                    <td className="p-3 text-right text-neutral-600">{formatPrice(t.balance_after)}</td>
                    <td className="p-3 text-right text-neutral-500 text-xs">{new Date(t.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default Wallet;
