import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Mail, Phone, ShieldCheck, CircleAlert, ExternalLink } from "lucide-react";

const StatusPill = ({ ok, label }) => (
  <Badge className={ok ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-100" : "bg-neutral-200 text-neutral-600 hover:bg-neutral-200"}>
    {ok ? <ShieldCheck className="h-3 w-3 mr-1" /> : <CircleAlert className="h-3 w-3 mr-1" />}
    {label}
  </Badge>
);

const Verification = () => {
  const { user, refresh, loading: authLoading } = useAuth();
  const { toast } = useToast();
  const [params] = useSearchParams();

  const [emailToken, setEmailToken] = useState("");
  const [emailSending, setEmailSending] = useState(false);
  const [emailConfirming, setEmailConfirming] = useState(false);

  const [phone, setPhone] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [phoneSending, setPhoneSending] = useState(false);
  const [phoneConfirming, setPhoneConfirming] = useState(false);

  const [stripeStatus, setStripeStatus] = useState(null);
  const [stripeLoading, setStripeLoading] = useState(false);

  useEffect(() => {
    // Auto-fill token if magic link is followed: /verify?token=xxx
    const t = params.get("token");
    if (t) setEmailToken(t);
  }, [params]);

  useEffect(() => {
    if (!user) return;
    setPhone(user.phone || "");
    api.get("/stripe/connect/status").then((r) => setStripeStatus(r.data)).catch(() => {});
  }, [user]);

  if (authLoading) return <div className="max-w-3xl mx-auto px-4 py-12 text-neutral-500">Loading…</div>;
  if (!user) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12">
        <p className="text-neutral-700">Please <Link to="/login" className="text-[#FF211F] underline">log in</Link> to access verification.</p>
      </div>
    );
  }

  const sendEmail = async () => {
    setEmailSending(true);
    try {
      const { data } = await api.post("/verify/email/send", {});
      if (data.already_verified) {
        toast({ title: "Email already verified" });
        return;
      }
      if (data.dev_mock && data.token) {
        setEmailToken(data.token);
        toast({
          title: "Mock magic link sent",
          description: `Token: ${data.token} (auto-filled below)`,
        });
      } else {
        toast({ title: "Verification email sent" });
      }
    } catch (err) {
      toast({ title: "Failed to send", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setEmailSending(false);
    }
  };

  const confirmEmail = async () => {
    if (!emailToken.trim()) {
      toast({ title: "Enter or paste the token", variant: "destructive" });
      return;
    }
    setEmailConfirming(true);
    try {
      await api.post("/verify/email/confirm", { token: emailToken.trim() });
      toast({ title: "Email verified", description: "You can now proceed to phone verification." });
      await refresh();
      setEmailToken("");
    } catch (err) {
      toast({ title: "Verification failed", description: err.response?.data?.detail || "Invalid or expired token", variant: "destructive" });
    } finally {
      setEmailConfirming(false);
    }
  };

  const sendPhone = async () => {
    if (!phone.trim() || phone.trim().length < 6) {
      toast({ title: "Enter a valid phone number", variant: "destructive" });
      return;
    }
    setPhoneSending(true);
    try {
      const { data } = await api.post("/verify/phone/send", { phone: phone.trim() });
      if (data.dev_mock && data.code) {
        setPhoneCode(data.code);
        toast({
          title: "Mock OTP sent",
          description: `Code: ${data.code} (auto-filled below)`,
        });
      } else {
        toast({ title: "OTP sent" });
      }
    } catch (err) {
      toast({ title: "Failed to send", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setPhoneSending(false);
    }
  };

  const confirmPhone = async () => {
    if (!phoneCode.trim() || phoneCode.trim().length !== 6) {
      toast({ title: "Enter the 6-digit code", variant: "destructive" });
      return;
    }
    setPhoneConfirming(true);
    try {
      await api.post("/verify/phone/confirm", { phone: phone.trim(), code: phoneCode.trim() });
      toast({ title: "Phone verified" });
      await refresh();
      setPhoneCode("");
    } catch (err) {
      toast({ title: "Verification failed", description: err.response?.data?.detail || "Invalid code", variant: "destructive" });
    } finally {
      setPhoneConfirming(false);
    }
  };

  const startStripe = async () => {
    setStripeLoading(true);
    try {
      const { data } = await api.post("/stripe/connect/onboard");
      setStripeStatus({ stripe_account_id: data.stripe_account_id, stripe_status: data.stripe_status });
      toast({
        title: data.already_active ? "Stripe already connected" : "Mock Stripe Connect activated",
        description: `Account: ${data.stripe_account_id}`,
      });
      await refresh();
    } catch (err) {
      toast({ title: "Stripe onboarding failed", description: err.response?.data?.detail || "Try again", variant: "destructive" });
    } finally {
      setStripeLoading(false);
    }
  };

  const canApply = user.email_verified && user.phone_verified && user.seller_status !== "approved" && user.seller_status !== "pending";

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-6" data-testid="verification-page">
      <div>
        <h1 className="text-3xl font-bold">Trust & payouts</h1>
        <p className="text-neutral-600 mt-1">Verify your account to unlock selling, payouts, and higher trust badges. External services are mocked in dev — codes auto-fill below.</p>
      </div>

      {/* Email */}
      <section className="border border-neutral-200 rounded-xl p-6 bg-white" data-testid="verify-email-section">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-[#FFF3F2] grid place-items-center">
              <Mail className="h-5 w-5 text-[#FF211F]" />
            </div>
            <div>
              <h2 className="font-semibold text-lg">Email verification</h2>
              <p className="text-sm text-neutral-500">We&apos;ll send a magic link to <span className="font-mono">{user.email}</span></p>
            </div>
          </div>
          <StatusPill ok={user.email_verified} label={user.email_verified ? "Verified" : "Unverified"} />
        </div>
        {!user.email_verified && (
          <div className="mt-4 space-y-3">
            <Button onClick={sendEmail} disabled={emailSending} className="bg-[#FF211F] hover:bg-[#e01d1b]" data-testid="verify-email-send-btn">
              {emailSending ? "Sending…" : "Send magic link"}
            </Button>
            <div>
              <Label>Paste token (or use the magic link)</Label>
              <div className="flex gap-2 mt-1">
                <Input value={emailToken} onChange={(e) => setEmailToken(e.target.value)} placeholder="magic-token" className="font-mono" data-testid="verify-email-token-input" />
                <Button variant="outline" onClick={confirmEmail} disabled={emailConfirming} data-testid="verify-email-confirm-btn">
                  {emailConfirming ? "Verifying…" : "Confirm"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Phone */}
      <section className="border border-neutral-200 rounded-xl p-6 bg-white" data-testid="verify-phone-section">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-[#FFF3F2] grid place-items-center">
              <Phone className="h-5 w-5 text-[#FF211F]" />
            </div>
            <div>
              <h2 className="font-semibold text-lg">Phone verification</h2>
              <p className="text-sm text-neutral-500">
                {user.phone_verified ? <>Verified: <span className="font-mono">{user.phone}</span></> : <>We&apos;ll send you a 6-digit code via SMS.</>}
              </p>
            </div>
          </div>
          <StatusPill ok={user.phone_verified} label={user.phone_verified ? "Verified" : "Unverified"} />
        </div>
        {!user.phone_verified && (
          <div className="mt-4 space-y-3">
            <div>
              <Label>Phone number (E.164 format)</Label>
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+15551234567" className="mt-1 font-mono" data-testid="verify-phone-input" />
            </div>
            <Button onClick={sendPhone} disabled={phoneSending || !phone.trim()} className="bg-[#FF211F] hover:bg-[#e01d1b]" data-testid="verify-phone-send-btn">
              {phoneSending ? "Sending…" : "Send code"}
            </Button>
            <div>
              <Label>6-digit code</Label>
              <div className="flex gap-2 mt-1">
                <Input value={phoneCode} onChange={(e) => setPhoneCode(e.target.value.replace(/\D/g, ""))} maxLength={6} placeholder="123456" className="font-mono tracking-widest" data-testid="verify-phone-code-input" />
                <Button variant="outline" onClick={confirmPhone} disabled={phoneConfirming} data-testid="verify-phone-confirm-btn">
                  {phoneConfirming ? "Verifying…" : "Confirm"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Stripe Connect (mocked) */}
      <section className="border border-neutral-200 rounded-xl p-6 bg-white" data-testid="stripe-connect-section">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-[#FFF3F2] grid place-items-center">
              <ExternalLink className="h-5 w-5 text-[#FF211F]" />
            </div>
            <div>
              <h2 className="font-semibold text-lg">Payouts (Stripe Connect)</h2>
              <p className="text-sm text-neutral-500">
                {stripeStatus?.stripe_account_id ? <>Account: <span className="font-mono">{stripeStatus.stripe_account_id}</span></> : "Connect your payout method — mocked in dev."}
              </p>
            </div>
          </div>
          <StatusPill ok={(stripeStatus?.stripe_status || user.stripe_status) === "active"} label={(stripeStatus?.stripe_status || user.stripe_status || "none")} />
        </div>
        {(stripeStatus?.stripe_status || user.stripe_status) !== "active" && (
          <Button className="mt-4 bg-[#FF211F] hover:bg-[#e01d1b]" onClick={startStripe} disabled={stripeLoading} data-testid="stripe-connect-btn">
            {stripeLoading ? "Connecting…" : "Start onboarding (mocked)"}
          </Button>
        )}
      </section>

      {/* Seller status */}
      <section className="border border-neutral-200 rounded-xl p-6 bg-white" data-testid="seller-status-section">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-semibold text-lg">Seller status</h2>
            <p className="text-sm text-neutral-500">
              {user.seller_status === "approved" && "You're an approved seller — start listing!"}
              {user.seller_status === "pending" && "Your application is under review by our team."}
              {user.seller_status === "rejected" && "Your last application was declined. You may re-apply."}
              {(!user.seller_status || user.seller_status === "none") && "Complete verification, then submit a seller application."}
            </p>
          </div>
          <Badge className="capitalize bg-neutral-100 text-neutral-700 hover:bg-neutral-100">{user.seller_status || "none"}</Badge>
        </div>
        {canApply && (
          <Link to="/seller/apply">
            <Button className="mt-4 bg-[#FF211F] hover:bg-[#e01d1b]" data-testid="seller-apply-cta">
              Apply to sell
            </Button>
          </Link>
        )}
        {user.seller_status === "pending" && (
          <Link to="/seller/apply">
            <Button variant="outline" className="mt-4" data-testid="seller-view-application">View application</Button>
          </Link>
        )}
      </section>
    </div>
  );
};

export default Verification;
