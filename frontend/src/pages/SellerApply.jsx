import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { ShieldCheck, CircleAlert } from "lucide-react";

const initialForm = {
  legal_name: "",
  business_name: "",
  business_type: "individual",
  tax_id: "",
  country: "US",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  postal_code: "",
  phone: "",
  payout_method: "stripe_connect",
  id_document_note: "",
};

const SellerApply = () => {
  const { user, refresh, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [existing, setExisting] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!user) return;
    setForm((f) => ({ ...f, phone: user.phone || "" }));
    api.get("/seller/application").then((r) => setExisting(r.data)).catch(() => {});
  }, [user]);

  if (authLoading) return <div className="max-w-3xl mx-auto px-4 py-12 text-neutral-500">Loading…</div>;
  if (!user) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12">
        <p className="text-neutral-700">Please <Link to="/login" className="text-[#FF211F] underline">log in</Link>.</p>
      </div>
    );
  }

  const readyChecks = [
    { ok: user.email_verified, label: "Email verified" },
    { ok: user.phone_verified, label: "Phone verified" },
  ];
  const allReady = readyChecks.every((c) => c.ok);

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: typeof v === "string" ? v : v.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!allReady) {
      toast({ title: "Verify email and phone first", variant: "destructive" });
      return;
    }
    if (!form.legal_name || !form.address_line1 || !form.city || !form.postal_code) {
      toast({ title: "Fill in the required fields", variant: "destructive" });
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/seller/apply", form);
      setExisting(data);
      toast({ title: "Application submitted", description: "Our team will review it shortly." });
      await refresh();
    } catch (err) {
      toast({ title: "Submission failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  const statusColor = {
    pending: "bg-amber-100 text-amber-800",
    approved: "bg-emerald-100 text-emerald-800",
    rejected: "bg-red-100 text-red-800",
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-6" data-testid="seller-apply-page">
      <div>
        <h1 className="text-3xl font-bold">Sell on Mercari</h1>
        <p className="text-neutral-600 mt-1">Tell us about your business so we can enable payouts and verified badges.</p>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        {readyChecks.map((c, i) => (
          <div key={i} className={`border rounded-lg p-3 flex items-center gap-2 ${c.ok ? "border-emerald-200 bg-emerald-50" : "border-neutral-200 bg-white"}`}>
            {c.ok ? <ShieldCheck className="h-4 w-4 text-emerald-600" /> : <CircleAlert className="h-4 w-4 text-neutral-400" />}
            <span className={c.ok ? "text-emerald-800 text-sm" : "text-neutral-700 text-sm"}>{c.label}</span>
          </div>
        ))}
      </div>
      {!allReady && (
        <div className="border border-amber-200 bg-amber-50 rounded-lg p-4 text-sm">
          Please complete <Link to="/verify" className="text-[#FF211F] underline font-medium">verification</Link> before applying.
        </div>
      )}

      {existing && (
        <div className="border border-neutral-200 bg-neutral-50 rounded-xl p-5" data-testid="existing-application">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-neutral-500">Your latest application</div>
              <div className="text-lg font-semibold mt-1">{existing.legal_name}</div>
              <div className="text-xs text-neutral-500 mt-1">Submitted {new Date(existing.created_at).toLocaleString()}</div>
            </div>
            <Badge className={`capitalize ${statusColor[existing.status] || "bg-neutral-200"}`}>{existing.status}</Badge>
          </div>
          {existing.admin_notes && (
            <div className="mt-3 text-sm text-neutral-700 border-t border-neutral-200 pt-3">
              <span className="text-neutral-500">Admin notes: </span>{existing.admin_notes}
            </div>
          )}
          {existing.status === "approved" && (
            <Button className="mt-4 bg-[#FF211F] hover:bg-[#e01d1b]" onClick={() => navigate("/sell")} data-testid="approved-start-selling">
              Start selling
            </Button>
          )}
        </div>
      )}

      {(!existing || existing.status === "rejected") && (
        <form onSubmit={submit} className="space-y-4 bg-white border border-neutral-200 rounded-xl p-6" data-testid="seller-apply-form">
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Legal name *</Label>
              <Input value={form.legal_name} onChange={set("legal_name")} required data-testid="apply-legal-name" className="mt-1" />
            </div>
            <div>
              <Label>Business name (optional)</Label>
              <Input value={form.business_name} onChange={set("business_name")} data-testid="apply-business-name" className="mt-1" />
            </div>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Business type</Label>
              <Select value={form.business_type} onValueChange={set("business_type")}>
                <SelectTrigger className="mt-1" data-testid="apply-business-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="individual">Individual</SelectItem>
                  <SelectItem value="sole_prop">Sole proprietor</SelectItem>
                  <SelectItem value="llc">LLC</SelectItem>
                  <SelectItem value="corp">Corporation</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Tax ID / EIN (last 4 stored)</Label>
              <Input value={form.tax_id} onChange={set("tax_id")} placeholder="123-45-6789" data-testid="apply-tax-id" className="mt-1 font-mono" />
            </div>
          </div>
          <div>
            <Label>Address line 1 *</Label>
            <Input value={form.address_line1} onChange={set("address_line1")} required data-testid="apply-address1" className="mt-1" />
          </div>
          <div>
            <Label>Address line 2</Label>
            <Input value={form.address_line2} onChange={set("address_line2")} data-testid="apply-address2" className="mt-1" />
          </div>
          <div className="grid sm:grid-cols-3 gap-4">
            <div>
              <Label>City *</Label>
              <Input value={form.city} onChange={set("city")} required data-testid="apply-city" className="mt-1" />
            </div>
            <div>
              <Label>State / Region</Label>
              <Input value={form.state} onChange={set("state")} data-testid="apply-state" className="mt-1" />
            </div>
            <div>
              <Label>Postal code *</Label>
              <Input value={form.postal_code} onChange={set("postal_code")} required data-testid="apply-postal" className="mt-1" />
            </div>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label>Country</Label>
              <Input value={form.country} onChange={set("country")} data-testid="apply-country" className="mt-1 uppercase" maxLength={2} />
            </div>
            <div>
              <Label>Phone (verified)</Label>
              <Input value={form.phone} onChange={set("phone")} data-testid="apply-phone" className="mt-1 font-mono" />
            </div>
          </div>
          <div>
            <Label>Payout method</Label>
            <Select value={form.payout_method} onValueChange={set("payout_method")}>
              <SelectTrigger className="mt-1" data-testid="apply-payout-method"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="stripe_connect">Stripe Connect (recommended)</SelectItem>
                <SelectItem value="bank_transfer">Bank transfer</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>ID document note (placeholder)</Label>
            <Textarea value={form.id_document_note} onChange={set("id_document_note")} placeholder="Describe your government-issued ID (upload UI coming soon)" data-testid="apply-id-note" className="mt-1" rows={3} />
          </div>
          <Button type="submit" disabled={submitting || !allReady} className="bg-[#FF211F] hover:bg-[#e01d1b] h-11 w-full" data-testid="apply-submit-btn">
            {submitting ? "Submitting…" : "Submit application"}
          </Button>
        </form>
      )}
    </div>
  );
};

export default SellerApply;
