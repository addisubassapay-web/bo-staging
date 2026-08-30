import React, { useEffect, useState } from "react";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/context/AuthContext";
import { Trash2, Plus, CheckCircle2, XCircle, Clock, Bitcoin, Building2 } from "lucide-react";
import CryptoIcon from "@/components/ui/CryptoIcon";

const emptyManual = () => ({
  id: Math.random().toString(36).slice(2, 10),
  name: "",
  instructions: "",
  icon: "",
  active: true,
});

const AdminPaymentMethods = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [crypto, setCrypto] = useState({ BTC: "", ETH: "", USDC: "", USDT: "" });
  const [assets, setAssets] = useState([]);
  const [manual, setManual] = useState([]);
  const [pending, setPending] = useState([]);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState("methods");

  const load = async () => {
    try {
      const { data } = await api.get("/admin/settings/payment-methods");
      setCrypto({ BTC: "", ETH: "", USDC: "", USDT: "", ...(data.crypto_addresses || {}) });
      setAssets(data.crypto_assets || []);
      setManual(data.manual_payment_methods || []);
    } catch (e) { /* ignored */ }
    try {
      const { data } = await api.get("/admin/deposits/pending");
      setPending(data || []);
    } catch (e) { /* ignored */ }
  };

  useEffect(() => { if (user?.role === "admin") load(); }, [user]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/settings/payment-methods", {
        crypto_addresses: crypto,
        crypto_assets: assets,
        manual_payment_methods: manual,
      });
      toast({ title: "Payment methods saved" });
    } catch (e) {
      toast({ title: "Save failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setSaving(false); }
  };

  const addAsset = () => setAssets([...assets, {
    id: Math.random().toString(36).slice(2, 10), symbol: "", network: "", address: "", active: true,
  }]);

  const approve = async (id) => {
    try { await api.post(`/admin/deposits/${id}/approve`); toast({ title: "Approved — wallet credited" }); load(); }
    catch (e) { toast({ title: "Failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" }); }
  };
  const reject = async (id) => {
    const reason = window.prompt("Reason for rejection?") || "";
    try { await api.post(`/admin/deposits/${id}/reject`, { reason }); toast({ title: "Rejected" }); load(); }
    catch (e) { toast({ title: "Failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" }); }
  };

  if (user && user.role !== "admin") {
    return <div className="p-8 text-neutral-500">Admins only.</div>;
  }

  const pendingCount = pending.filter((p) => p.status === "pending").length;

  return (
    <div className="space-y-6" data-testid="admin-payments-page">
      <div>
        <h2 className="text-2xl font-bold">Payment methods &amp; deposits</h2>
        <p className="text-sm text-neutral-500 mt-1">Configure how users deposit funds. Review and approve pending deposits.</p>
      </div>

      <div className="inline-flex bg-neutral-100 rounded-full p-1">
        <button
          onClick={() => setTab("methods")}
          className={`min-h-[44px] px-4 rounded-full text-sm font-medium transition-colors ${tab === "methods" ? "bg-white text-[#DC2626] shadow-sm" : "text-neutral-700"}`}
          data-testid="admin-pay-tab-methods"
        >Methods</button>
        <button
          onClick={() => setTab("pending")}
          className={`min-h-[44px] px-4 rounded-full text-sm font-medium transition-colors relative ${tab === "pending" ? "bg-white text-[#DC2626] shadow-sm" : "text-neutral-700"}`}
          data-testid="admin-pay-tab-pending"
        >
          Pending
          {pendingCount > 0 && (
            <span className="ml-2 inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full bg-[#DC2626] text-white text-[10px] font-bold tabular-nums">{pendingCount}</span>
          )}
        </button>
      </div>

      {tab === "methods" && (
        <div className="space-y-6">
          <section className="border border-neutral-200 rounded-2xl bg-white p-5 mesh-gradient-warm">
            <div className="flex items-center gap-2 mb-4">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-[#5459E8] to-[#FF0515] grid place-items-center shadow-md shadow-[#5459E8]/25"><Bitcoin className="h-5 w-5 text-white" /></div>
              <div>
                <h3 className="font-bold text-lg text-neutral-900">Crypto assets &amp; networks</h3>
                <p className="text-xs text-neutral-600">Configure the coins you accept</p>
              </div>
            </div>
            <p className="text-xs text-neutral-500 mb-4">Each row is one (asset · network · address) deposit slot. Toggle Active to hide from checkout. Blank addresses are auto-hidden.</p>
            <div className="space-y-3">
              {assets.map((a, i) => (
                <div key={a.id} className="grid grid-cols-1 sm:grid-cols-[44px_110px_140px_1fr_auto] gap-2 sm:items-center border border-neutral-200 rounded-xl p-2.5 bg-white/80 backdrop-blur-sm">
                  <div className="grid place-items-center bg-neutral-50 rounded-lg h-11 w-11" data-testid={`asset-preview-${i}`}>
                    <CryptoIcon symbol={a.symbol || "BTC"} size={30} />
                  </div>
                  <Input value={a.symbol} onChange={(e) => { const cp = [...assets]; cp[i].symbol = e.target.value.toUpperCase(); setAssets(cp); }} placeholder="ETH" className="h-11 text-base font-mono uppercase" data-testid={`asset-symbol-${i}`} />
                  <Input value={a.network} onChange={(e) => { const cp = [...assets]; cp[i].network = e.target.value; setAssets(cp); }} placeholder="Ethereum" className="h-11 text-base" data-testid={`asset-network-${i}`} />
                  <Input value={a.address} onChange={(e) => { const cp = [...assets]; cp[i].address = e.target.value; setAssets(cp); }} placeholder="Deposit address" className="h-11 text-base font-mono text-xs" data-testid={`asset-address-${i}`} />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { const cp = [...assets]; cp[i].active = !cp[i].active; setAssets(cp); }} className={`min-h-[44px] px-3 rounded-full text-xs font-semibold border transition ${a.active ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-neutral-100 text-neutral-500 border-neutral-200"}`} data-testid={`asset-toggle-${i}`}>
                      {a.active ? "Active" : "Off"}
                    </button>
                    <button type="button" onClick={() => setAssets(assets.filter((_, j) => j !== i))} className="min-h-[44px] min-w-[44px] rounded-full border border-neutral-200 hover:border-[#FF0515] hover:text-[#FF0515] grid place-items-center transition" aria-label="Delete" data-testid={`asset-delete-${i}`}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
              <Button type="button" variant="outline" onClick={addAsset} className="min-h-[44px] w-full sm:w-auto rounded-full gap-1.5 border-[#5459E8] text-[#5459E8] hover:bg-[#5459E8] hover:text-white transition" data-testid="asset-add"><Plus className="h-4 w-4" /> Add asset / network</Button>
            </div>
          </section>

          <section className="border border-neutral-200 rounded-xl bg-white p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="h-9 w-9 rounded-lg bg-blue-50 grid place-items-center"><Building2 className="h-4 w-4 text-blue-600" /></div>
              <h3 className="font-semibold text-lg">Manual payment methods</h3>
            </div>
            <p className="text-xs text-neutral-500 mb-4">e.g. bank transfer, mobile money, PayPal link — instructions shown to users during deposit.</p>
            <div className="space-y-4">
              {manual.map((m, i) => (
                <div key={m.id} className="border border-neutral-200 rounded-lg p-3 bg-neutral-50 space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2">
                    <Input
                      value={m.name}
                      onChange={(e) => { const cp = [...manual]; cp[i].name = e.target.value; setManual(cp); }}
                      placeholder="Method name (e.g. Bank Transfer — USA)"
                      className="h-11 text-base"
                      data-testid={`admin-manual-name-${i}`}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => { const cp = [...manual]; cp[i].active = !cp[i].active; setManual(cp); }}
                        className={`min-h-[44px] px-4 rounded-full text-sm font-medium border transition-colors ${m.active ? "bg-green-50 text-green-700 border-green-200" : "bg-neutral-100 text-neutral-500 border-neutral-200"}`}
                        data-testid={`admin-manual-toggle-${i}`}
                      >{m.active ? "Active" : "Inactive"}</button>
                      <button
                        type="button"
                        onClick={() => setManual(manual.filter((_, j) => j !== i))}
                        className="min-h-[44px] min-w-[44px] rounded-full border border-neutral-200 hover:border-[#DC2626] hover:text-[#DC2626] grid place-items-center transition-colors"
                        aria-label="Delete method"
                        data-testid={`admin-manual-delete-${i}`}
                      ><Trash2 className="h-4 w-4" /></button>
                    </div>
                  </div>
                  <Textarea
                    value={m.instructions}
                    onChange={(e) => { const cp = [...manual]; cp[i].instructions = e.target.value; setManual(cp); }}
                    placeholder="Instructions for the user (bank details, account #, payment link, notes)"
                    rows={4}
                    className="text-base"
                    data-testid={`admin-manual-instructions-${i}`}
                  />
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                onClick={() => setManual([...manual, emptyManual()])}
                className="min-h-[44px] w-full sm:w-auto rounded-full gap-1.5"
                data-testid="admin-manual-add"
              ><Plus className="h-4 w-4" /> Add method</Button>
            </div>
          </section>

          <div className="flex justify-end">
            <Button
              onClick={save}
              disabled={saving}
              className="min-h-[44px] h-11 px-8 rounded-full bg-[#DC2626] hover:bg-[#e01d1b] text-white font-semibold"
              data-testid="admin-payments-save"
            >{saving ? "Saving…" : "Save changes"}</Button>
          </div>
        </div>
      )}

      {tab === "pending" && (
        <section className="border border-neutral-200 rounded-xl bg-white overflow-hidden">
          {pending.length === 0 ? (
            <div className="p-10 text-center text-neutral-500 text-sm">No deposit requests yet.</div>
          ) : (
            <ul className="divide-y divide-neutral-100">
              {pending.map((p) => (
                <li key={p.id} className="p-4 flex flex-col sm:flex-row gap-3 sm:items-center" data-testid={`pending-deposit-${p.id}`}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-neutral-900">{formatPrice(Number(p.amount))}</span>
                      <span className="text-xs text-neutral-500">· {p.user_name || p.user_id.slice(0, 8)}</span>
                      <Badge variant="secondary" className={
                        p.status === "pending" ? "bg-amber-100 text-amber-700"
                        : p.status === "approved" ? "bg-green-100 text-green-700"
                        : "bg-neutral-100 text-neutral-500"
                      }>{p.status}</Badge>
                    </div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {p.method === "crypto" ? `${p.currency} — ` : "Manual — "}
                      <span className="font-mono break-all">{p.reference}</span>
                    </div>
                    {p.note && <div className="mt-1 text-xs text-neutral-700">{p.note}</div>}
                    {p.screenshot_url && (
                      <a
                        href={p.screenshot_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-block"
                        data-testid={`screenshot-${p.id}`}
                      >
                        <img
                          src={p.screenshot_url}
                          alt="proof"
                          className="h-20 w-20 rounded-lg object-cover border border-neutral-200 hover:opacity-90 transition"
                        />
                      </a>
                    )}
                    <div className="mt-1 text-[11px] text-neutral-400">{new Date(p.created_at).toLocaleString()}</div>
                  </div>
                  {p.status === "pending" && (
                    <div className="flex gap-2 shrink-0">
                      <Button
                        onClick={() => approve(p.id)}
                        className="min-h-[44px] rounded-full bg-green-600 hover:bg-green-700 text-white gap-1"
                        data-testid={`approve-${p.id}`}
                      ><CheckCircle2 className="h-4 w-4" /> Approve</Button>
                      <Button
                        onClick={() => reject(p.id)}
                        variant="outline"
                        className="min-h-[44px] rounded-full gap-1"
                        data-testid={`reject-${p.id}`}
                      ><XCircle className="h-4 w-4" /> Reject</Button>
                    </div>
                  )}
                  {p.status !== "pending" && <Clock className="h-4 w-4 text-neutral-400 shrink-0" />}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
};

export default AdminPaymentMethods;
