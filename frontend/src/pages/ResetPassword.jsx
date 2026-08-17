import React, { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import api from "@/lib/api";
import BrandMark from "@/components/BrandMark";
import PasswordInput from "@/components/PasswordInput";
import { Lock, ArrowRight, ShieldCheck } from "lucide-react";

const ResetPassword = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const token = params.get("token") || "";
  const [pw, setPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pw.length < 6) { toast({ title: "Password too short", description: "At least 6 characters.", variant: "destructive" }); return; }
    if (pw !== confirmPw) { toast({ title: "Passwords don't match", variant: "destructive" }); return; }
    if (!token) { toast({ title: "Missing reset token", variant: "destructive" }); return; }
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: pw });
      toast({ title: "Password updated", description: "You can now sign in with your new password." });
      navigate("/login");
    } catch (e2) {
      toast({ title: "Reset failed", description: e2.response?.data?.detail || "Invalid or expired link", variant: "destructive" });
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] grid place-items-center px-4 py-10 bg-gradient-to-b from-[#FFFBF6] to-[#F8FAFC]" data-testid="reset-page">
      <div className="w-full max-w-md">
        <div className="flex justify-center mb-6"><BrandMark size={64} showWordmark animated /></div>
        <div className="bg-white border border-neutral-200 rounded-2xl p-6 sm:p-8 shadow-xl shadow-neutral-200/50">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800">
            <ShieldCheck className="h-3 w-3" /> New password
          </div>
          <h1 className="mt-3 text-2xl font-extrabold text-neutral-900">Set a new password</h1>
          <p className="text-sm text-neutral-500 mt-1">Choose something strong — at least 6 characters.</p>

          <form onSubmit={submit} className="mt-6 space-y-4" data-testid="reset-form">
            <div>
              <Label htmlFor="rp-pw" className="text-xs uppercase tracking-wider text-neutral-500">New password</Label>
              <div className="relative mt-1.5">
                <Lock className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2 z-10" />
                <PasswordInput
                  id="rp-pw"
                  autoComplete="new-password"
                  value={pw}
                  onChange={(e) => setPw(e.target.value)}
                  required
                  minLength={6}
                  className="pl-9 h-11"
                  testIdSuffix="reset-new"
                  data-testid="reset-new"
                />
              </div>
            </div>
            <div>
              <Label htmlFor="rp-pw2" className="text-xs uppercase tracking-wider text-neutral-500">Confirm password</Label>
              <div className="relative mt-1.5">
                <Lock className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2 z-10" />
                <PasswordInput
                  id="rp-pw2"
                  autoComplete="new-password"
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  required
                  minLength={6}
                  className="pl-9 h-11"
                  testIdSuffix="reset-confirm"
                  data-testid="reset-confirm"
                />
              </div>
            </div>
            <Button
              type="submit"
              disabled={loading || !token}
              className="w-full h-11 bg-gradient-to-r from-[#7DD3FC] to-[#2563EB] text-white font-semibold"
              data-testid="reset-submit"
            >
              {loading ? "Updating…" : <>Update password <ArrowRight className="h-4 w-4 ml-1" /></>}
            </Button>
          </form>

          <p className="mt-6 text-sm text-center text-neutral-600">
            <Link to="/login" className="text-[#2563EB] font-semibold hover:underline">Back to sign-in</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default ResetPassword;
