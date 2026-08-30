import React, { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import { Bitcoin, Copy, Check, Building2, Info, Send } from "lucide-react";

/**
 * Deposit dialog with two methods:
 *   1. Crypto — pick currency (BTC/ETH/USDC/…), see designated address + QR + copy button,
 *      paste the tx hash, submit a pending deposit for admin approval.
 *   2. Manual — pick an admin-configured method (bank transfer, local, payment link),
 *      follow the instructions, submit a reference.
 *
 * Touch-target rule: every button/input is min 44×44 on mobile (`h-11` = 44px, `h-12` = 48px).
 */
export const DepositDialog = ({ open, onOpenChange, onDeposited }) => {
  const { toast } = useToast();
  const [methods, setMethods] = useState({ crypto: [], manual: [] });
  const [tab, setTab] = useState("crypto");
  const [cryptoIdx, setCryptoIdx] = useState(0);
  const [manualIdx, setManualIdx] = useState(0);
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/wallet/deposit-methods").then((r) => {
      setMethods(r.data || { crypto: [], manual: [] });
      const hasCrypto = (r.data?.crypto || []).length > 0;
      setTab(hasCrypto ? "crypto" : "manual");
    }).catch(() => {});
  }, [open]);

  const activeCrypto = methods.crypto[cryptoIdx] || null;
  const activeManual = methods.manual[manualIdx] || null;

  const copyAddress = async () => {
    if (!activeCrypto?.address) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(activeCrypto.address);
      } else {
        // Fallback for insecure contexts / older browsers
        const ta = document.createElement("textarea");
        ta.value = activeCrypto.address;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
    } catch {
      // Clipboard permission denied — user can still select the address text manually.
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const submit = async () => {
    const amt = Number(amount);
    if (!amt || amt < 1) { toast({ title: "Enter a valid amount", variant: "destructive" }); return; }
    if (!reference.trim()) { toast({ title: "Enter a transaction reference", description: "Paste the tx hash or your bank reference so admin can verify.", variant: "destructive" }); return; }
    setSubmitting(true);
    try {
      const body = tab === "crypto"
        ? { amount: amt, method: "crypto", currency: activeCrypto?.currency, reference: reference.trim(), note }
        : { amount: amt, method: "manual", method_id: activeManual?.id, reference: reference.trim(), note };
      await api.post("/wallet/deposit/pending", body);
      toast({
        title: "Deposit submitted",
        description: `$${amt.toFixed(2)} is pending admin approval — you'll be notified once credited.`,
      });
      setAmount(""); setReference(""); setNote("");
      onOpenChange(false);
      onDeposited?.();
    } catch (e) {
      toast({ title: "Failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  const cryptoEmpty = methods.crypto.length === 0;
  const manualEmpty = methods.manual.length === 0;
  const allEmpty = cryptoEmpty && manualEmpty;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg w-[calc(100vw-2rem)] sm:w-full max-h-[90vh] overflow-y-auto p-5 sm:p-6" data-testid="wallet-deposit-dialog">
        <DialogHeader>
          <DialogTitle className="section-heading-lower text-2xl">add funds</DialogTitle>
          <DialogDescription>Deposit via crypto or a manual method. Admin approves once verified.</DialogDescription>
        </DialogHeader>

        {allEmpty ? (
          <div className="p-8 text-center rounded-xl bg-canvas-2 text-ink-muted text-sm">
            No deposit methods are configured yet. Please contact support.
          </div>
        ) : (
          <Tabs value={tab} onValueChange={setTab} className="w-full">
            <TabsList className="w-full grid grid-cols-2 h-auto p-1 bg-canvas-2">
              <TabsTrigger value="crypto" disabled={cryptoEmpty} className="h-11 gap-1.5" data-testid="deposit-tab-crypto">
                <Bitcoin className="h-4 w-4" /> Crypto
              </TabsTrigger>
              <TabsTrigger value="manual" disabled={manualEmpty} className="h-11 gap-1.5" data-testid="deposit-tab-manual">
                <Building2 className="h-4 w-4" /> Manual
              </TabsTrigger>
            </TabsList>

            {/* CRYPTO */}
            <TabsContent value="crypto" className="mt-5 space-y-4">
              <div className="flex gap-2 flex-wrap" role="tablist" aria-label="Cryptocurrency">
                {methods.crypto.map((c, i) => (
                  <button
                    key={c.currency}
                    type="button"
                    onClick={() => setCryptoIdx(i)}
                    className={`min-h-[44px] px-4 rounded-full text-sm font-semibold transition-colors duration-200 border ${
                      i === cryptoIdx
                        ? "bg-ocean-red text-canvas-0 border-ocean-red shadow-brand-sm"
                        : "bg-canvas-0 text-ink-body border-hairline hover:border-ink"
                    }`}
                    data-testid={`deposit-crypto-${c.currency}`}
                  >
                    {c.currency}
                  </button>
                ))}
              </div>

              {activeCrypto && (
                <div className="rounded-xl bg-canvas-0 ring-1 ring-hairline p-4 flex flex-col sm:flex-row gap-4 items-center sm:items-start">
                  <div className="bg-canvas-0 rounded-lg p-2 ring-1 ring-hairline shrink-0">
                    <QRCodeSVG
                      value={activeCrypto.address}
                      size={144}
                      level="M"
                      includeMargin={false}
                      fgColor="#0A0A0A"
                    />
                  </div>
                  <div className="flex-1 min-w-0 w-full">
                    <div className="text-[10px] uppercase tracking-widest text-ink-muted font-semibold">{activeCrypto.currency} address</div>
                    <div className="mt-2 font-mono text-xs sm:text-sm text-ink break-all bg-canvas-2 rounded-lg p-2.5 select-all" data-testid="deposit-crypto-address">
                      {activeCrypto.address}
                    </div>
                    <button
                      type="button"
                      onClick={copyAddress}
                      className={`mt-2 min-h-[44px] w-full sm:w-auto px-4 rounded-full text-sm font-semibold inline-flex items-center justify-center gap-1.5 transition-colors duration-200 ${
                        copied
                          ? "bg-success text-canvas-0"
                          : "bg-ink text-canvas-0 hover:bg-ink-body"
                      }`}
                      data-testid="deposit-copy-address"
                    >
                      {copied ? <><Check className="h-4 w-4" /> Copied</> : <><Copy className="h-4 w-4" /> Copy address</>}
                    </button>
                    <div className="mt-2 text-[11px] text-ink-muted flex items-start gap-1">
                      <Info className="h-3 w-3 mt-0.5 shrink-0" />
                      <span>Send only {activeCrypto.currency} to this address. Other coins will be lost.</span>
                    </div>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* MANUAL */}
            <TabsContent value="manual" className="mt-5 space-y-4">
              <div className="flex gap-2 flex-wrap" role="tablist" aria-label="Manual method">
                {methods.manual.map((m, i) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setManualIdx(i)}
                    className={`min-h-[44px] px-4 rounded-full text-sm font-semibold transition-colors duration-200 border ${
                      i === manualIdx
                        ? "bg-ocean-red text-canvas-0 border-ocean-red shadow-brand-sm"
                        : "bg-canvas-0 text-ink-body border-hairline hover:border-ink"
                    }`}
                    data-testid={`deposit-manual-${m.id}`}
                  >
                    {m.name}
                  </button>
                ))}
              </div>
              {activeManual && (
                <div className="rounded-xl bg-canvas-0 ring-1 ring-hairline p-4" data-testid="deposit-manual-instructions">
                  <div className="text-[10px] uppercase tracking-widest text-ink-muted font-semibold">instructions</div>
                  <div className="mt-2 text-sm text-ink-body whitespace-pre-line leading-relaxed">
                    {activeManual.instructions}
                  </div>
                </div>
              )}
            </TabsContent>
          </Tabs>
        )}

        {/* Common form */}
        {!allEmpty && (
          <div className="space-y-3 mt-4">
            <div>
              <Label htmlFor="dep-amount">Amount (USD)</Label>
              <Input
                id="dep-amount" type="number" inputMode="decimal" min="1" step="0.01"
                value={amount} onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                className="h-12 text-base mt-1 tabular-nums"
                data-testid="deposit-amount-input"
              />
            </div>
            <div>
              <Label htmlFor="dep-ref">Transaction reference</Label>
              <Input
                id="dep-ref" value={reference} onChange={(e) => setReference(e.target.value)}
                placeholder={tab === "crypto" ? "e.g. 0xabc123… (tx hash)" : "e.g. Bank ref / receipt no."}
                className="h-12 text-base mt-1 font-mono text-xs"
                data-testid="deposit-reference-input"
              />
            </div>
            <div>
              <Label htmlFor="dep-note">Note (optional)</Label>
              <Textarea
                id="dep-note" value={note} onChange={(e) => setNote(e.target.value)}
                placeholder="Anything the admin should know…"
                rows={2}
                className="text-base mt-1"
              />
            </div>
          </div>
        )}

        <DialogFooter className="mt-4 gap-2 flex-col sm:flex-row">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="h-12 w-full sm:w-auto rounded-full border-hairline">
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={submitting || allEmpty}
            className="h-12 w-full sm:w-auto rounded-full bg-ocean-red hover:bg-ocean-red-hover text-canvas-0 font-semibold shadow-brand-md gap-1.5"
            data-testid="deposit-submit"
          >
            <Send className="h-4 w-4" />
            {submitting ? "Submitting…" : "Submit for approval"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

/**
 * Withdraw dialog — supports bank/PayPal-style manual info (existing behavior)
 * PLUS a new "crypto" method where the user pastes their external wallet address.
 */
export const WithdrawDialog = ({ open, onOpenChange, onSubmitted }) => {
  const { toast } = useToast();
  const [method, setMethod] = useState("crypto");
  const [amount, setAmount] = useState("");
  const [accountInfo, setAccountInfo] = useState("");
  const [cryptoCurrency, setCryptoCurrency] = useState("BTC");
  const [cryptoAddress, setCryptoAddress] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [supportedCryptos, setSupportedCryptos] = useState([]);

  useEffect(() => {
    if (!open) return;
    // Pull supported cryptos from admin-configured deposit methods (mirror what's set)
    api.get("/wallet/deposit-methods").then((r) => {
      const cs = (r.data?.crypto || []).map((c) => c.currency);
      setSupportedCryptos(cs.length ? cs : ["BTC", "ETH", "USDC"]);
      if (cs.length) setCryptoCurrency(cs[0]);
    }).catch(() => setSupportedCryptos(["BTC", "ETH", "USDC"]));
  }, [open]);

  const submit = async () => {
    const amt = Number(amount);
    if (!amt || amt < 1) { toast({ title: "Enter a valid amount", variant: "destructive" }); return; }
    let info = "";
    if (method === "crypto") {
      if (!cryptoAddress.trim()) {
        toast({ title: "Paste your wallet address", variant: "destructive" });
        return;
      }
      info = `${cryptoCurrency}: ${cryptoAddress.trim()}`;
    } else {
      info = accountInfo.trim();
    }
    setSubmitting(true);
    try {
      await api.post("/wallet/withdraw", { amount: amt, account_info: info });
      toast({ title: "Withdrawal requested", description: "Admin will process this shortly." });
      onOpenChange(false);
      setAmount(""); setAccountInfo(""); setCryptoAddress("");
      onSubmitted?.();
    } catch (e) {
      toast({ title: "Failed", description: e?.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md w-[calc(100vw-2rem)] sm:w-full p-5 sm:p-6" data-testid="wallet-withdraw-dialog">
        <DialogHeader>
          <DialogTitle className="section-heading-lower text-2xl">request withdrawal</DialogTitle>
          <DialogDescription>Choose how you&apos;d like to receive your funds. Admin processes withdrawals within 24h.</DialogDescription>
        </DialogHeader>

        <Tabs value={method} onValueChange={setMethod} className="w-full mt-2">
          <TabsList className="w-full grid grid-cols-2 h-auto p-1 bg-canvas-2">
            <TabsTrigger value="crypto" className="h-11 gap-1.5" data-testid="withdraw-tab-crypto">
              <Bitcoin className="h-4 w-4" /> Crypto
            </TabsTrigger>
            <TabsTrigger value="manual" className="h-11 gap-1.5" data-testid="withdraw-tab-manual">
              <Building2 className="h-4 w-4" /> Bank / other
            </TabsTrigger>
          </TabsList>

          <TabsContent value="crypto" className="mt-5 space-y-3">
            <div>
              <Label>Currency</Label>
              <div className="flex gap-2 flex-wrap mt-1.5">
                {supportedCryptos.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setCryptoCurrency(c)}
                    className={`min-h-[44px] px-4 rounded-full text-sm font-semibold transition-colors duration-200 border ${
                      c === cryptoCurrency
                        ? "bg-ocean-red text-canvas-0 border-ocean-red shadow-brand-sm"
                        : "bg-canvas-0 text-ink-body border-hairline hover:border-ink"
                    }`}
                    data-testid={`withdraw-currency-${c}`}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <Label htmlFor="wd-crypto-addr">Your {cryptoCurrency} wallet address</Label>
              <Input
                id="wd-crypto-addr" value={cryptoAddress} onChange={(e) => setCryptoAddress(e.target.value)}
                placeholder={`Paste your ${cryptoCurrency} address…`}
                className="h-12 text-base mt-1 font-mono text-xs"
                data-testid="withdraw-crypto-address"
              />
              <div className="mt-1.5 text-[11px] text-ink-muted flex items-start gap-1">
                <Info className="h-3 w-3 mt-0.5 shrink-0" />
                <span>Double-check the address. Crypto withdrawals to a wrong address cannot be reversed.</span>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="manual" className="mt-5">
            <Label htmlFor="wd-account">Account info (bank, PayPal, etc.)</Label>
            <Textarea
              id="wd-account" value={accountInfo} onChange={(e) => setAccountInfo(e.target.value)}
              placeholder="Bank name, account #, IBAN, or PayPal email — admin uses this to send the funds."
              rows={4}
              className="text-base mt-1"
              data-testid="withdraw-account-info"
            />
          </TabsContent>
        </Tabs>

        <div className="mt-4">
          <Label htmlFor="wd-amount">Amount (USD)</Label>
          <Input
            id="wd-amount" type="number" inputMode="decimal" min="1" step="0.01"
            value={amount} onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            className="h-12 text-base mt-1 tabular-nums"
            data-testid="withdraw-amount"
          />
        </div>

        <DialogFooter className="mt-4 gap-2 flex-col sm:flex-row">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="h-12 w-full sm:w-auto rounded-full border-hairline">Cancel</Button>
          <Button
            onClick={submit}
            disabled={submitting}
            className="h-12 w-full sm:w-auto rounded-full bg-ocean-red hover:bg-ocean-red-hover text-canvas-0 font-semibold shadow-brand-md gap-1.5"
            data-testid="withdraw-submit"
          >
            <Send className="h-4 w-4" />
            {submitting ? "Submitting…" : "Request"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
