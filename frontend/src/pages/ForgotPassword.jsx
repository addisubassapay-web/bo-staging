import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import BrandMark from "@/components/BrandMark";
import { Mail, ArrowRight, CheckCircle2, ShieldCheck } from "lucide-react";

const ForgotPassword = () => {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (e2) {
      setErr(e2.response?.data?.detail || "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] grid place-items-center px-4 py-10 bg-gradient-to-b from-[#FFFBF6] to-[#F8FAFC]" data-testid="forgot-page">
      <div className="w-full max-w-md">
        <div className="flex justify-center mb-6">
          <BrandMark size={64} showWordmark animated />
        </div>
        <div className="bg-white border border-neutral-200 rounded-2xl p-6 sm:p-8 shadow-xl shadow-neutral-200/50">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800">
            <ShieldCheck className="h-3 w-3" /> Account recovery
          </div>
          <h1 className="mt-3 text-2xl font-extrabold text-neutral-900">
            {sent ? "Check your email" : "Forgot your password?"}
          </h1>
          <p className="text-sm text-neutral-500 mt-1">
            {sent
              ? "If that email is registered, we've sent a one-time reset link. It expires in 60 minutes."
              : "Enter the email tied to your Ocean account and we'll send you a one-time reset link."}
          </p>

          {sent ? (
            <div className="mt-6 space-y-4">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
                <div className="text-sm text-emerald-900">
                  <div className="font-semibold">Reset link on its way</div>
                  <div className="text-xs mt-1 text-emerald-800/80">Didn&apos;t receive it? Check spam or try again in a few minutes.</div>
                </div>
              </div>
              <Link to="/login" className="block">
                <Button className="w-full h-11 bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white font-semibold" data-testid="forgot-back-to-login">
                  Back to sign-in
                </Button>
              </Link>
            </div>
          ) : (
            <form onSubmit={submit} className="mt-6 space-y-4" data-testid="forgot-form">
              <div>
                <Label htmlFor="fp-email" className="text-xs uppercase tracking-wider text-neutral-500">Email</Label>
                <div className="relative mt-1.5">
                  <Mail className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <Input
                    id="fp-email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-9 h-11 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB]"
                    data-testid="forgot-email"
                  />
                </div>
              </div>
              {err && <div className="text-xs text-red-600">{err}</div>}
              <Button
                type="submit"
                disabled={loading}
                className="w-full h-11 bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white font-semibold"
                data-testid="forgot-submit"
              >
                {loading ? "Sending…" : <>Send reset link <ArrowRight className="h-4 w-4 ml-1" /></>}
              </Button>
            </form>
          )}

          <p className="mt-6 text-sm text-center text-neutral-600">
            Remember it? <Link to="/login" className="text-[#2563EB] font-semibold hover:underline">Log in</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
