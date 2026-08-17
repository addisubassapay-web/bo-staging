import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api, { formatPrice } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import {
  Wallet as WalletIcon, ArrowDownRight, ArrowUpRight, Clock, CheckCircle2, XCircle,
  Snowflake, Copy, Check, Bitcoin, Building2, Plus, Minus, RotateCcw, Upload, X as XIcon, Sparkles,
  ChevronDown, ChevronUp,
} from "lucide-react";

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
  adjustment: { label: "Deposit", color: "text-green-600" },
  refund: { label: "Refund", color: "text-blue-600" },
  withdrawal: { label: "Withdrawal", color: "text-red-600" },
};

const statusIcon = (s) => {
  if (s === "paid" || s === "approved") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
  if (s === "rejected") return <XCircle className="h-4 w-4 text-red-500" />;
  return <Clock className="h-4 w-4 text-amber-500" />;
};

const statusBadgeClass = (s) => {
  if (s === "paid" || s === "approved") return "bg-green-100 text-green-700";
  if (s === "rejected") return "bg-red-100 text-red-700";
  return "bg-amber-100 text-amber-700";
};

const QR_SIZE = 180;
const qrUrl = (data) => `https://api.qrserver.com/v1/create-qr-code/?size=${QR_SIZE}x${QR_SIZE}&margin=0&data=${encodeURIComponent(data || "")}`;

const CopyBtn = ({ text, testid }) => {
  const [copied, setCopied] = useState(false);
  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) { /* ignored */ }
  };
  return (
    <button
      type="button"
      onClick={doCopy}
      className="min-h-[44px] min-w-[44px] px-3 rounded-lg border border-neutral-200 bg-white hover:border-[#FF211F] hover:text-[#FF211F] active:scale-95 transition-all flex items-center gap-1.5 text-sm font-medium"
      data-testid={testid}
      aria-label="Copy"
    >
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
    </button>
  );
};

const DepositDialog = ({ open, onOpenChange, onSubmitted }) => {
  const { toast } = useToast();
  // Unified deposit methods — same admin-managed source used by the Checkout Payment page.
  // Endpoint shape: { crypto: [{id, currency, network, address, label}], manual: [{id, name, instructions, kind}] }
  const [methods, setMethods] = useState({ crypto: [], manual: [] });
  const cryptoList = methods.crypto || [];
  const manualList = methods.manual || [];
  const hasCrypto = cryptoList.length > 0;
  const hasManual = manualList.length > 0;
  const [tab, setTab] = useState("crypto");
  const [cryptoIdx, setCryptoIdx] = useState(0);          // index into cryptoList
  const [manualId, setManualId] = useState("");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [screenshotUrl, setScreenshotUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/wallet/deposit-methods").then((r) => {
      const data = r.data || { crypto: [], manual: [] };
      setMethods(data);
      const c = data.crypto || [];
      const m = data.manual || [];
      setTab(c.length > 0 ? "crypto" : (m.length > 0 ? "manual" : "crypto"));
      setCryptoIdx(0);
      setManualId(m[0]?.id || "");
    }).catch(() => setMethods({ crypto: [], manual: [] }));
    setAmount("");
    setReference("");
    setNote("");
    setScreenshotUrl("");
  }, [open]);

  const activeCrypto = cryptoList[cryptoIdx] || null;
  const selectedManual = manualList.find((m) => m.id === manualId);

  const uploadScreenshot = async (file) => {
    if (!file) return;
    if (file.size > 12 * 1024 * 1024) {
      toast({ title: "File too large", description: "Max 12MB", variant: "destructive" });
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setScreenshotUrl(data.url);
      toast({ title: "Screenshot attached" });
    } catch (e) {
      toast({ title: "Upload failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { toast({ title: "Enter a valid amount", variant: "destructive" }); return; }
    if (tab === "crypto") {
      if (!activeCrypto) { toast({ title: "Choose a cryptocurrency", variant: "destructive" }); return; }
      if (!reference.trim()) { toast({ title: "Transaction hash is required", variant: "destructive" }); return; }
    } else {
      if (!manualId) { toast({ title: "Choose a payment method", variant: "destructive" }); return; }
    }
    setSubmitting(true);
    try {
      const body = tab === "crypto"
        ? { amount: amt, method: "crypto", currency: activeCrypto.currency, reference: reference.trim(), note: note.trim(), screenshot_url: screenshotUrl || null }
        : { amount: amt, method: "manual", method_id: manualId, reference: reference.trim(), note: note.trim(), screenshot_url: screenshotUrl || null };
      await api.post("/wallet/deposit/pending", body);
      toast({ title: "Deposit submitted", description: "An admin will review and credit your wallet once confirmed." });
      onSubmitted?.();
      onOpenChange(false);
    } catch (e) {
      toast({ title: "Failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setSubmitting(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg sm:max-w-xl max-h-[90vh] overflow-y-auto" data-testid="deposit-dialog">
        <DialogHeader><DialogTitle>Deposit funds</DialogTitle></DialogHeader>

        {(!hasCrypto && !hasManual) ? (
          <div className="py-8 text-center text-sm text-neutral-500">
            No deposit methods are configured yet. Please contact support.
          </div>
        ) : (
          <div className="space-y-4">
            <div className="inline-flex bg-neutral-100 rounded-full p-1 w-full sm:w-auto">
              {hasCrypto && (
                <button
                  type="button"
                  onClick={() => setTab("crypto")}
                  className={`flex-1 sm:flex-none min-h-[44px] px-4 rounded-full text-sm font-medium transition-colors flex items-center justify-center gap-1.5 ${tab === "crypto" ? "bg-white text-[#FF211F] shadow-sm" : "text-neutral-700"}`}
                  data-testid="deposit-tab-crypto"
                >
                  <Bitcoin className="h-4 w-4" /> Crypto
                </button>
              )}
              {hasManual && (
                <button
                  type="button"
                  onClick={() => setTab("manual")}
                  className={`flex-1 sm:flex-none min-h-[44px] px-4 rounded-full text-sm font-medium transition-colors flex items-center justify-center gap-1.5 ${tab === "manual" ? "bg-white text-[#FF211F] shadow-sm" : "text-neutral-700"}`}
                  data-testid="deposit-tab-manual"
                >
                  <Building2 className="h-4 w-4" /> Bank / Other
                </button>
              )}
            </div>

            {tab === "crypto" && hasCrypto && (
              <div className="space-y-4">
                <div>
                  <Label className="text-sm">Cryptocurrency</Label>
                  <Select value={String(cryptoIdx)} onValueChange={(v) => setCryptoIdx(Number(v))}>
                    <SelectTrigger className="h-11 mt-1.5" data-testid="deposit-currency-select">
                      <SelectValue placeholder="Choose currency" />
                    </SelectTrigger>
                    <SelectContent>
                      {cryptoList.map((c, i) => (
                        <SelectItem key={c.id} value={String(i)}>{c.label || c.currency}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {activeCrypto && (
                  <div className="border border-neutral-200 rounded-xl p-4 bg-neutral-50 flex flex-col sm:flex-row gap-4 items-center sm:items-start">
                    <img
                      src={qrUrl(activeCrypto.address)}
                      alt={`${activeCrypto.currency} QR code`}
                      width={QR_SIZE}
                      height={QR_SIZE}
                      className="rounded-lg bg-white p-2 shrink-0"
                      data-testid="deposit-qr"
                    />
                    <div className="w-full min-w-0 flex-1 space-y-2">
                      <div className="text-xs uppercase tracking-wider text-neutral-500 font-semibold">
                        {activeCrypto.currency} address{activeCrypto.network ? ` · ${activeCrypto.network}` : ""}
                      </div>
                      <div className="font-mono text-xs break-all bg-white border border-neutral-200 rounded-lg p-2.5" data-testid="deposit-address">{activeCrypto.address}</div>
                      <div className="flex gap-2">
                        <CopyBtn text={activeCrypto.address} testid="deposit-copy-address" />
                      </div>
                      <p className="text-[11px] text-neutral-500 leading-relaxed">
                        Send only <b>{activeCrypto.currency}</b>{activeCrypto.network ? <> on the <b>{activeCrypto.network}</b> network</> : null} to this address. Sending any other asset may result in permanent loss.
                      </p>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <Label className="text-sm">Amount (USD)</Label>
                    <Input type="number" inputMode="decimal" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" className="h-11 mt-1.5 text-base" data-testid="deposit-amount" />
                  </div>
                  <div>
                    <Label className="text-sm">Transaction hash</Label>
                    <Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="0x..." className="h-11 mt-1.5 text-base font-mono text-xs" data-testid="deposit-reference" />
                  </div>
                </div>
                <div>
                  <Label className="text-sm">Note (optional)</Label>
                  <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Anything the admin should know" className="mt-1.5 text-base" data-testid="deposit-note" />
                </div>
              </div>
            )}

            {tab === "manual" && hasManual && (
              <div className="space-y-4">
                <div>
                  <Label className="text-sm">Payment method</Label>
                  <Select value={manualId} onValueChange={setManualId}>
                    <SelectTrigger className="h-11 mt-1.5" data-testid="deposit-manual-select">
                      <SelectValue placeholder="Choose method" />
                    </SelectTrigger>
                    <SelectContent>
                      {manualList.map((m) => (
                        <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {selectedManual && (
                  <div className="border border-neutral-200 rounded-xl p-4 bg-neutral-50" data-testid="deposit-manual-instructions">
                    <div className="text-xs uppercase tracking-wider text-neutral-500 font-semibold mb-2">Instructions</div>
                    <pre className="whitespace-pre-wrap font-sans text-sm text-neutral-800 leading-relaxed break-words">{selectedManual.instructions || "No instructions provided."}</pre>
                    {selectedManual.instructions && (
                      <div className="mt-3">
                        <CopyBtn text={selectedManual.instructions} testid="deposit-copy-instructions" />
                      </div>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <Label className="text-sm">Amount (USD)</Label>
                    <Input type="number" inputMode="decimal" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" className="h-11 mt-1.5 text-base" data-testid="deposit-amount-manual" />
                  </div>
                  <div>
                    <Label className="text-sm">Reference / payment id (optional)</Label>
                    <Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. bank ref, receipt #" className="h-11 mt-1.5 text-base" data-testid="deposit-reference-manual" />
                  </div>
                </div>
                <div>
                  <Label className="text-sm">Note (optional)</Label>
                  <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Anything the admin should know" className="mt-1.5 text-base" data-testid="deposit-note-manual" />
                </div>
              </div>
            )}

            <div className="border-t border-neutral-100 pt-3">
              <Label className="text-sm">Payment screenshot (optional)</Label>
              <p className="text-[11px] text-neutral-500 mt-0.5 mb-2">Attach proof of payment to speed up approval. JPG, PNG or PDF, up to 12MB.</p>
              {screenshotUrl ? (
                <div className="flex items-center gap-2 border border-neutral-200 rounded-lg p-2 bg-neutral-50">
                  {/\.pdf$/i.test(screenshotUrl) ? (
                    <div className="h-16 w-16 rounded bg-white border border-neutral-200 grid place-items-center text-xs text-neutral-500 shrink-0">PDF</div>
                  ) : (
                    <img src={screenshotUrl} alt="proof" className="h-16 w-16 rounded object-cover bg-white border border-neutral-200 shrink-0" data-testid="deposit-screenshot-preview" />
                  )}
                  <div className="flex-1 min-w-0 text-xs text-neutral-600 truncate">{screenshotUrl}</div>
                  <button
                    type="button"
                    onClick={() => setScreenshotUrl("")}
                    className="min-h-[44px] min-w-[44px] rounded-full border border-neutral-200 hover:border-red-400 hover:text-red-600 grid place-items-center transition"
                    aria-label="Remove screenshot"
                    data-testid="deposit-screenshot-remove"
                  ><XIcon className="h-4 w-4" /></button>
                </div>
              ) : (
                <label className="flex items-center justify-center gap-2 min-h-[52px] rounded-lg border-2 border-dashed border-neutral-300 hover:border-[#FF211F] hover:bg-[#FFF3F2] transition cursor-pointer text-sm text-neutral-600" data-testid="deposit-screenshot-upload">
                  <Upload className="h-4 w-4" />
                  <span>{uploading ? "Uploading…" : "Tap to upload payment proof"}</span>
                  <input
                    type="file"
                    accept="image/*,application/pdf"
                    className="hidden"
                    disabled={uploading}
                    onChange={(e) => uploadScreenshot(e.target.files?.[0])}
                  />
                </label>
              )}
            </div>

            <p className="text-[11px] text-neutral-500">
              Deposits are reviewed by an admin. Your wallet will be credited once payment is confirmed.
            </p>
          </div>
        )}

        <DialogFooter className="gap-2 flex-col sm:flex-row">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="min-h-[44px] w-full sm:w-auto">Cancel</Button>
          {(hasCrypto || hasManual) && (
            <Button onClick={submit} disabled={submitting} className="min-h-[44px] bg-[#FF211F] hover:bg-[#e01d1b] w-full sm:w-auto" data-testid="deposit-submit">
              {submitting ? "Submitting…" : "Submit deposit"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const WithdrawDialog = ({ open, onOpenChange, methods, onSubmitted }) => {
  const { toast } = useToast();
  const cryptoList = Object.keys(methods?.crypto_addresses || {});
  const hasCrypto = cryptoList.length > 0;
  const [tab, setTab] = useState(hasCrypto ? "crypto" : "manual");
  const [cryptoCcy, setCryptoCcy] = useState(cryptoList[0] || "USDT");
  const [walletAddress, setWalletAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [accountInfo, setAccountInfo] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTab(hasCrypto ? "crypto" : "manual");
    setCryptoCcy(cryptoList[0] || "USDT");
    setWalletAddress("");
    setAmount("");
    setAccountInfo("");
  }, [open]);

  const submit = async () => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { toast({ title: "Enter a valid amount", variant: "destructive" }); return; }
    let info = "";
    let method = "bank_transfer";
    if (tab === "crypto") {
      if (!walletAddress.trim()) { toast({ title: "Enter your wallet address", variant: "destructive" }); return; }
      info = `${cryptoCcy}: ${walletAddress.trim()}`;
      method = "crypto";
    } else {
      if (!accountInfo.trim()) { toast({ title: "Enter payout details", variant: "destructive" }); return; }
      info = accountInfo.trim();
      method = "bank_transfer";
    }
    setSubmitting(true);
    try {
      await api.post("/wallet/withdraw", { amount: amt, method, account_info: info });
      toast({ title: "Withdrawal requested", description: "An admin will review and process it." });
      onSubmitted?.();
      onOpenChange(false);
    } catch (e) {
      toast({ title: "Failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setSubmitting(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="withdraw-dialog">
        <DialogHeader><DialogTitle>Request withdrawal</DialogTitle></DialogHeader>

        <div className="space-y-4">
          <div className="inline-flex bg-neutral-100 rounded-full p-1 w-full sm:w-auto">
            {hasCrypto && (
              <button
                type="button"
                onClick={() => setTab("crypto")}
                className={`flex-1 sm:flex-none min-h-[44px] px-4 rounded-full text-sm font-medium transition-colors flex items-center justify-center gap-1.5 ${tab === "crypto" ? "bg-white text-[#FF211F] shadow-sm" : "text-neutral-700"}`}
                data-testid="withdraw-tab-crypto"
              ><Bitcoin className="h-4 w-4" /> Crypto</button>
            )}
            <button
              type="button"
              onClick={() => setTab("manual")}
              className={`flex-1 sm:flex-none min-h-[44px] px-4 rounded-full text-sm font-medium transition-colors flex items-center justify-center gap-1.5 ${tab === "manual" ? "bg-white text-[#FF211F] shadow-sm" : "text-neutral-700"}`}
              data-testid="withdraw-tab-manual"
            ><Building2 className="h-4 w-4" /> Bank / Other</button>
          </div>

          <div>
            <Label className="text-sm">Amount (USD)</Label>
            <Input type="number" inputMode="decimal" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" className="h-11 mt-1.5 text-base" data-testid="withdraw-amount" />
          </div>

          {tab === "crypto" ? (
            <>
              <div>
                <Label className="text-sm">Cryptocurrency</Label>
                <Select value={cryptoCcy} onValueChange={setCryptoCcy}>
                  <SelectTrigger className="h-11 mt-1.5" data-testid="withdraw-currency-select">
                    <SelectValue placeholder="Choose currency" />
                  </SelectTrigger>
                  <SelectContent>
                    {(hasCrypto ? cryptoList : ["USDT", "USDC", "BTC", "ETH"]).map((k) => (
                      <SelectItem key={k} value={k}>{k}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm">Your {cryptoCcy} wallet address</Label>
                <Input value={walletAddress} onChange={(e) => setWalletAddress(e.target.value)} placeholder={`Paste your ${cryptoCcy} address`} className="h-11 mt-1.5 text-base font-mono text-xs" data-testid="withdraw-wallet-address" />
                <p className="text-[11px] text-neutral-500 mt-1.5">Double-check the address — payouts to a wrong address cannot be recovered.</p>
              </div>
            </>
          ) : (
            <div>
              <Label className="text-sm">Payout details</Label>
              <Textarea value={accountInfo} onChange={(e) => setAccountInfo(e.target.value)} rows={4} placeholder="Bank name, account number, PayPal email, or any payout details" className="mt-1.5 text-base" data-testid="withdraw-account-info" />
            </div>
          )}

          <p className="text-[11px] text-neutral-500">Withdrawals are processed by admin. Mocked payout — no real money is transferred.</p>
        </div>

        <DialogFooter className="gap-2 flex-col sm:flex-row">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="min-h-[44px] w-full sm:w-auto">Cancel</Button>
          <Button onClick={submit} disabled={submitting} className="min-h-[44px] bg-[#FF211F] hover:bg-[#e01d1b] w-full sm:w-auto" data-testid="withdraw-submit">
            {submitting ? "Submitting…" : "Request payout"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const ReinvestDialog = ({ open, onOpenChange, frozenBalance, onSubmitted }) => {
  const { toast } = useToast();
  const [amount, setAmount] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [quote, setQuote] = useState({ frozen_balance: 0, pending_wholesale: 0, max_reinvest: 0, open_orders: 0 });
  const [loadingQuote, setLoadingQuote] = useState(false);
  useEffect(() => {
    if (!open) return;
    setAmount("");
    setLoadingQuote(true);
    api.get("/wallet/reinvest/quote")
      .then((r) => setQuote(r.data || { frozen_balance: frozenBalance, pending_wholesale: 0, max_reinvest: 0, open_orders: 0 }))
      .catch(() => setQuote({ frozen_balance: frozenBalance, pending_wholesale: 0, max_reinvest: 0, open_orders: 0 }))
      .finally(() => setLoadingQuote(false));
  }, [open, frozenBalance]);
  const cap = quote.max_reinvest || 0;
  const submit = async () => {
    const amt = parseFloat(amount);
    if (!amt || amt < 1) { toast({ title: "Enter a valid amount (≥ $1)", variant: "destructive" }); return; }
    if (amt > cap) { toast({ title: "Above reinvest cap", description: `Your open orders need $${cap.toFixed(2)} in wholesale funding.`, variant: "destructive" }); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post("/wallet/reinvest", { amount: amt });
      toast({
        title: "Reinvest unlocked",
        description: `$${amt.toFixed(2)} moved from frozen → available. New balance $${data.balance.toFixed(2)}.`,
      });
      onSubmitted?.();
      onOpenChange(false);
    } catch (e) {
      toast({ title: "Reinvest failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally { setSubmitting(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="reinvest-dialog">
        <DialogHeader><DialogTitle>Reinvest frozen funds</DialogTitle></DialogHeader>
        <div className="space-y-4 py-2">
          <div className="rounded-xl bg-gradient-to-br from-sky-50 to-blue-50 border border-blue-200 p-4">
            <div className="text-xs uppercase font-semibold text-blue-800 tracking-wider">Reinvest cap</div>
            <div className="mt-1 text-3xl font-bold tabular-nums text-blue-900" data-testid="reinvest-frozen-value">
              {loadingQuote ? "…" : `$${cap.toFixed(2)}`}
            </div>
            <p className="text-xs text-blue-900/70 mt-2 leading-relaxed">
              Unlocks the wholesale funding your open dropship orders need. Capped at the lower of your frozen escrow and the total wholesale cost of un-fulfilled incoming orders.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md bg-white/70 border border-blue-100 px-2 py-1.5" data-testid="reinvest-quote-frozen">
                <div className="text-blue-700/80 uppercase tracking-wider text-[10px] font-semibold">Frozen escrow</div>
                <div className="font-bold tabular-nums text-blue-900">${(quote.frozen_balance || 0).toFixed(2)}</div>
              </div>
              <div className="rounded-md bg-white/70 border border-blue-100 px-2 py-1.5" data-testid="reinvest-quote-pending">
                <div className="text-blue-700/80 uppercase tracking-wider text-[10px] font-semibold">Open wholesale demand</div>
                <div className="font-bold tabular-nums text-blue-900">${(quote.pending_wholesale || 0).toFixed(2)}</div>
                <div className="text-[10px] text-blue-700/80">{quote.open_orders || 0} order{quote.open_orders === 1 ? "" : "s"}</div>
              </div>
            </div>
          </div>
          {cap <= 0 && !loadingQuote && (
            <div className="rounded-lg bg-neutral-50 border border-neutral-200 text-neutral-600 text-xs p-3" data-testid="reinvest-empty-hint">
              You don&apos;t have any un-fulfilled dropship orders that need wholesale funding right now.
              {quote.frozen_balance > 0 && quote.pending_wholesale === 0 && (
                <span className="block mt-1">Your frozen escrow of ${quote.frozen_balance.toFixed(2)} will auto-release once your existing orders are delivered.</span>
              )}
            </div>
          )}
          <div>
            <Label className="text-sm">Amount to unlock (USD)</Label>
            <Input
              type="number"
              inputMode="decimal"
              step="0.01"
              min={1}
              max={cap}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              className="h-11 mt-1.5 text-base font-semibold tabular-nums"
              disabled={cap <= 0}
              data-testid="reinvest-amount"
            />
            <div className="mt-2 flex gap-2">
              {[25, 50, 100].map((p) => {
                const v = Math.floor(cap * (p / 100) * 100) / 100;
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setAmount(String(v))}
                    disabled={v < 1}
                    className="h-8 px-3 rounded-full border border-neutral-200 hover:border-[#2563EB] hover:text-[#2563EB] text-xs font-semibold disabled:opacity-40"
                    data-testid={`reinvest-preset-${p}`}
                  >{p}% (${v.toFixed(2)})</button>
                );
              })}
            </div>
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="reinvest-cancel">Cancel</Button>
          <Button
            onClick={submit}
            disabled={submitting || !amount || cap <= 0}
            className="bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] hover:brightness-110"
            data-testid="reinvest-submit"
          >{submitting ? "Unlocking…" : "Unlock funds"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const RefundsDialog = ({ open, onOpenChange, transactions }) => {
  const refunds = (transactions || []).filter((t) => t.type === "refund" || (t.type === "adjustment" && (t.description || "").toLowerCase().includes("refund")));
  const total = refunds.reduce((s, t) => s + Math.max(0, t.amount), 0);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="refunds-dialog">
        <DialogHeader><DialogTitle>Refund history</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="rounded-xl border border-neutral-200 bg-neutral-50 p-4">
            <div className="text-xs uppercase tracking-wider text-neutral-500 font-semibold">Total refunded to your wallet</div>
            <div className="text-2xl font-bold text-emerald-600 mt-1 tabular-nums" data-testid="refunds-total">{formatPrice(total)}</div>
            <p className="text-[11px] text-neutral-500 mt-2">Refunds happen automatically when a dispute is resolved in your favor.</p>
          </div>
          {refunds.length === 0 ? (
            <div className="py-8 text-center text-sm text-neutral-500">No refunds yet.</div>
          ) : (
            <div className="border border-neutral-200 rounded-lg divide-y divide-neutral-100 overflow-hidden">
              {refunds.map((t) => (
                <div key={t.id} className="p-3 flex items-center justify-between gap-2" data-testid={`refund-row-${t.id}`}>
                  <div className="min-w-0">
                    <div className="text-sm text-neutral-800 truncate">{t.description}</div>
                    <div className="text-[11px] text-neutral-500">{new Date(t.created_at).toLocaleString()}</div>
                  </div>
                  <div className="text-sm font-semibold text-emerald-600 tabular-nums shrink-0">+{formatPrice(Math.abs(t.amount))}</div>
                </div>
              ))}
            </div>
          )}
          <div className="text-xs text-neutral-500">
            Need a refund on a recent order? <Link to="/disputes" className="text-[#FF211F] font-medium hover:underline">Open a dispute →</Link>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} className="min-h-[44px] w-full sm:w-auto bg-[#FF211F] hover:bg-[#e01d1b]" data-testid="refunds-close">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const Wallet = () => {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [methods, setMethods] = useState({ crypto_addresses: {}, manual_payment_methods: [] });
  const [deposits, setDeposits] = useState([]);
  const [dpOpen, setDpOpen] = useState(false);
  const [wdOpen, setWdOpen] = useState(false);
  const [rfOpen, setRfOpen] = useState(false);
  const [riOpen, setRiOpen] = useState(false);
  const [expandedTx, setExpandedTx] = useState(null);

  const load = async () => {
    const [w, m, d] = await Promise.allSettled([
      api.get("/wallet"),
      api.get("/wallet/payment-methods"),
      api.get("/wallet/deposits"),
    ]);
    if (w.status === "fulfilled") setData(w.value.data);
    if (m.status === "fulfilled") setMethods(m.value.data || { crypto_addresses: {}, manual_payment_methods: [] });
    if (d.status === "fulfilled") setDeposits(d.value.data || []);
  };

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login"); return; }
    load();
  }, [user, loading, navigate]);

  const afterMutation = async () => {
    await refresh();
    await load();
  };

  if (!data) return <div className="max-w-4xl mx-auto px-4 py-8">Loading…</div>;

  const earnedByType = data.transactions.reduce((acc, t) => {
    if (t.amount > 0) acc[t.type] = (acc[t.type] || 0) + t.amount;
    return acc;
  }, {});

  const pendingDeposits = deposits.filter((d) => d.status === "pending");

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 sm:py-8">
      <div className="flex items-center gap-2 mb-6">
        <WalletIcon className="h-6 w-6 text-[#FF211F]" />
        <h1 className="text-2xl sm:text-3xl font-bold">Wallet</h1>
      </div>

      <div className="grid md:grid-cols-3 gap-4 mb-8">
        <div className="md:col-span-2 bg-gradient-to-br from-[#FF211F] to-[#c81816] text-white rounded-xl p-5 sm:p-6">
          <div className="text-sm opacity-90">Available balance</div>
          <div className="text-3xl sm:text-4xl font-bold mt-2" data-testid="wallet-available">{formatPrice(data.balance)}</div>
          {data.frozen_balance > 0 && (
            <div className="mt-3 inline-flex items-center gap-1.5 text-xs bg-white/15 backdrop-blur-sm rounded-full px-3 py-1" data-testid="wallet-frozen-chip">
              <Snowflake className="h-3.5 w-3.5" />
              <span>Frozen: <span className="font-semibold tabular-nums">{formatPrice(data.frozen_balance)}</span></span>
              <span className="opacity-80 hidden sm:inline">· released after delivery is confirmed</span>
            </div>
          )}
          <div className="mt-4 flex gap-2 flex-wrap">
            <Button
              onClick={() => setDpOpen(true)}
              className="min-h-[44px] bg-white text-[#FF211F] hover:bg-neutral-100 font-semibold"
              data-testid="wallet-deposit-btn"
            ><Plus className="h-4 w-4 mr-1" /> Deposit</Button>
            <Button
              onClick={() => setWdOpen(true)}
              className="min-h-[44px] bg-white/20 hover:bg-white/30 text-white border border-white/40"
              data-testid="wallet-withdraw-btn"
            ><Minus className="h-4 w-4 mr-1" /> Withdraw</Button>
            <Button
              onClick={() => setRfOpen(true)}
              className="min-h-[44px] bg-white/20 hover:bg-white/30 text-white border border-white/40"
              data-testid="wallet-refunds-btn"
            ><RotateCcw className="h-4 w-4 mr-1" /> Refunds</Button>
            <Button
              onClick={() => setRiOpen(true)}
              disabled={!(data.frozen_balance > 0)}
              title={data.frozen_balance > 0 ? "Unlock frozen funds to pay wholesale on incoming orders" : "No frozen funds available yet"}
              className="min-h-[44px] bg-white text-[#2563EB] hover:bg-blue-50 font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="wallet-reinvest-btn"
            ><Sparkles className="h-4 w-4 mr-1" /> Reinvest</Button>
            <Link to="/seller/payouts">
              <Button className="min-h-[44px] bg-white/20 hover:bg-white/30 text-white border border-white/40" data-testid="wallet-open-dashboard">
                Payout dashboard →
              </Button>
            </Link>
          </div>
        </div>

        <div className="bg-white border border-neutral-200 rounded-xl p-4 sm:p-5">
          <div className="text-xs uppercase text-neutral-500 mb-2 font-semibold tracking-wider">Earnings by source</div>
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

      {(deposits.length > 0) && (
        <div className="mb-8">
          <h2 className="font-semibold mb-3">Deposit requests</h2>
          <div className="space-y-2">
            {deposits.slice(0, 6).map((d) => (
              <div key={d.id} className="flex items-center justify-between border border-neutral-200 rounded-lg p-3 flex-wrap gap-2" data-testid={`deposit-row-${d.id}`}>
                <div className="flex items-center gap-3 min-w-0">
                  {statusIcon(d.status)}
                  <div className="min-w-0">
                    <div className="font-medium">{formatPrice(d.amount)} <span className="text-xs text-neutral-500 font-normal">· {d.method === "crypto" ? (d.currency || "crypto") : "manual"}</span></div>
                    <div className="text-xs text-neutral-500 truncate max-w-[60vw]">{new Date(d.created_at).toLocaleDateString()} {d.reference && `· ${d.reference.slice(0, 20)}${d.reference.length > 20 ? "…" : ""}`}</div>
                  </div>
                </div>
                <Badge variant="secondary" className={`capitalize ${statusBadgeClass(d.status)}`}>{d.status}</Badge>
              </div>
            ))}
          </div>
          {pendingDeposits.length > 0 && (
            <p className="text-xs text-neutral-500 mt-2">{pendingDeposits.length} pending review by admin.</p>
          )}
        </div>
      )}

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
          <>
            {/* Desktop table */}
            <div className="hidden sm:block border border-neutral-200 rounded-lg overflow-hidden">
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
                  {data.transactions.map((t) => {
                    const funded = t.funded_orders || [];
                    const isExpandable = funded.length > 0;
                    const expanded = expandedTx === t.id;
                    return (
                      <React.Fragment key={t.id}>
                        <tr
                          className={`border-t border-neutral-100 ${isExpandable ? "cursor-pointer hover:bg-blue-50/40" : ""}`}
                          onClick={() => isExpandable && setExpandedTx(expanded ? null : t.id)}
                          data-testid={isExpandable ? `reinvest-tx-row-${t.id}` : undefined}
                        >
                          <td className="p-3">
                            <Badge variant="secondary" className={typeMeta[t.type]?.color || ""}>{typeMeta[t.type]?.label || t.type}</Badge>
                          </td>
                          <td className="p-3 text-neutral-700">
                            <div className="flex items-center gap-2">
                              <span>{t.description}</span>
                              {isExpandable && (
                                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-800 bg-gradient-to-r from-sky-100 to-blue-100 border border-blue-200 rounded-full px-2 py-0.5">
                                  <Sparkles className="h-3 w-3" /> {funded.length} order{funded.length === 1 ? "" : "s"} funded
                                  {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className={`p-3 text-right font-medium ${t.amount >= 0 ? "text-green-600" : "text-red-600"}`}>
                            {t.amount >= 0 ? <ArrowDownRight className="h-3 w-3 inline mr-0.5" /> : <ArrowUpRight className="h-3 w-3 inline mr-0.5" />}
                            {formatPrice(Math.abs(t.amount))}
                          </td>
                          <td className="p-3 text-right text-neutral-600">{formatPrice(t.balance_after)}</td>
                          <td className="p-3 text-right text-neutral-500 text-xs">{new Date(t.created_at).toLocaleDateString()}</td>
                        </tr>
                        {isExpandable && expanded && (
                          <tr className="bg-gradient-to-br from-sky-50/40 to-blue-50/30" data-testid={`reinvest-tx-detail-${t.id}`}>
                            <td colSpan={5} className="p-3">
                              <div className="text-[11px] uppercase font-semibold text-blue-800 tracking-wider mb-2">
                                Funded orders ({funded.length})
                              </div>
                              <div className="space-y-2">
                                {funded.map((oid) => {
                                  const o = (data.orders_by_id || {})[oid];
                                  if (!o) return (
                                    <div key={oid} className="text-xs text-neutral-500 font-mono">#{oid.slice(0,8)} · (deleted)</div>
                                  );
                                  return (
                                    <Link
                                      key={oid}
                                      to={`/profile?tab=sales`}
                                      className="flex items-center gap-3 rounded-lg bg-white border border-blue-100 p-2 hover:border-[#2563EB] transition"
                                      data-testid={`reinvest-funded-order-${oid}`}
                                    >
                                      {o.listing_image && (
                                        <img src={o.listing_image} alt="" className="h-10 w-10 rounded object-cover shrink-0" />
                                      )}
                                      <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium text-neutral-900 line-clamp-1">{o.listing_title}</div>
                                        <div className="text-[11px] text-neutral-500">
                                          #{o.id.slice(0,8)} · qty {o.quantity} · {o.status}
                                        </div>
                                      </div>
                                      <div className="text-right shrink-0">
                                        <div className="text-sm font-bold tabular-nums text-blue-800">{formatPrice(o.reinvest_funded_amount)}</div>
                                        <div className="text-[10px] text-neutral-400">reinvested</div>
                                      </div>
                                    </Link>
                                  );
                                })}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* Mobile cards */}
            <div className="sm:hidden space-y-2">
              {data.transactions.map((t) => {
                const funded = t.funded_orders || [];
                const expanded = expandedTx === t.id;
                return (
                  <div key={t.id} className="border border-neutral-200 rounded-lg p-3">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <Badge variant="secondary" className={typeMeta[t.type]?.color || ""}>{typeMeta[t.type]?.label || t.type}</Badge>
                      <span className={`font-semibold ${t.amount >= 0 ? "text-green-600" : "text-red-600"}`}>
                        {t.amount >= 0 ? "+" : "-"}{formatPrice(Math.abs(t.amount))}
                      </span>
                    </div>
                    <div className="text-sm text-neutral-700">{t.description}</div>
                    <div className="flex justify-between mt-1 text-xs text-neutral-500">
                      <span>Balance: {formatPrice(t.balance_after)}</span>
                      <span>{new Date(t.created_at).toLocaleDateString()}</span>
                    </div>
                    {funded.length > 0 && (
                      <>
                        <button
                          type="button"
                          onClick={() => setExpandedTx(expanded ? null : t.id)}
                          className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-blue-800 bg-gradient-to-r from-sky-100 to-blue-100 border border-blue-200 rounded-full px-2 py-0.5"
                          data-testid={`reinvest-tx-toggle-${t.id}`}
                        >
                          <Sparkles className="h-3 w-3" /> {funded.length} order{funded.length === 1 ? "" : "s"} funded
                          {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                        </button>
                        {expanded && (
                          <div className="mt-2 space-y-1.5" data-testid={`reinvest-tx-detail-${t.id}`}>
                            {funded.map((oid) => {
                              const o = (data.orders_by_id || {})[oid];
                              if (!o) return <div key={oid} className="text-xs font-mono text-neutral-500">#{oid.slice(0,8)}</div>;
                              return (
                                <Link key={oid} to="/profile?tab=sales" className="flex items-center gap-2 bg-white border border-blue-100 rounded-md p-1.5">
                                  {o.listing_image && <img src={o.listing_image} alt="" className="h-8 w-8 rounded object-cover shrink-0" />}
                                  <div className="flex-1 min-w-0 text-xs">
                                    <div className="font-medium line-clamp-1">{o.listing_title}</div>
                                    <div className="text-neutral-500">qty {o.quantity} · {o.status}</div>
                                  </div>
                                  <div className="text-xs font-bold text-blue-800 tabular-nums">{formatPrice(o.reinvest_funded_amount)}</div>
                                </Link>
                              );
                            })}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      <DepositDialog open={dpOpen} onOpenChange={setDpOpen} onSubmitted={afterMutation} />
      <WithdrawDialog open={wdOpen} onOpenChange={setWdOpen} methods={methods} onSubmitted={afterMutation} />
      <RefundsDialog open={rfOpen} onOpenChange={setRfOpen} transactions={data.transactions} />
      <ReinvestDialog open={riOpen} onOpenChange={setRiOpen} frozenBalance={data.frozen_balance || 0} onSubmitted={afterMutation} />
    </div>
  );
};

export default Wallet;
