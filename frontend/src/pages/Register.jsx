import React, { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import api from "@/lib/api";
import BrandMark from "@/components/BrandMark";
import GoogleLoginButton from "@/components/GoogleLoginButton";
import PasswordInput from "@/components/PasswordInput";
import { ShieldCheck, Mail, User, Lock, Gift, ArrowRight, Check, Sparkles, Lock as LockIcon, AlertCircle } from "lucide-react";

const strengthOf = (pw) => {
  let s = 0;
  if (pw.length >= 6) s++;
  if (pw.length >= 10) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return Math.min(4, s);
};

const Register = () => {
  const [searchParams] = useSearchParams();
  const { toast } = useToast();
  const [form, setForm] = useState({
    email: "",
    username: "",
    password: "",
    confirm_password: "",
    referral_code: "",
    accept: false,
  });
  const [loading, setLoading] = useState(false);
  const [inviteOnly, setInviteOnly] = useState(false);
  const [inviteLoading, setInviteLoading] = useState(true);

  useEffect(() => {
    const ref = searchParams.get("ref");
    if (ref) {
      setForm((f) => ({ ...f, referral_code: ref.toUpperCase() }));
      try { localStorage.setItem("mercari-global_pending_referral", ref.toUpperCase()); } catch { /* ignore */ }
    } else {
      try {
        const pending = localStorage.getItem("mercari-global_pending_referral");
        if (pending) setForm((f) => ({ ...f, referral_code: pending }));
      } catch { /* ignore */ }
    }
  }, [searchParams]);

  useEffect(() => {
    api.get("/settings/public")
      .then((r) => setInviteOnly(!!r.data?.invite_only_signup))
      .catch(() => {})
      .finally(() => setInviteLoading(false));
  }, []);

  const strength = strengthOf(form.password);
  const strengthLabel = ["Too short", "Weak", "Fair", "Good", "Strong"][strength];
  const strengthColor = ["bg-red-400", "bg-red-400", "bg-amber-400", "bg-emerald-400", "bg-emerald-600"][strength];
  const passwordsMatch = form.password && form.confirm_password && form.password === form.confirm_password;
  const passwordsMismatch = form.confirm_password && form.password !== form.confirm_password;

  const submit = async (e) => {
    e.preventDefault();
    if (form.password.length < 6) {
      toast({ title: "Password too short", description: "At least 6 characters.", variant: "destructive" });
      return;
    }
    if (form.password !== form.confirm_password) {
      toast({ title: "Passwords don't match", description: "Please retype your password.", variant: "destructive" });
      return;
    }
    if (inviteOnly && !form.referral_code.trim()) {
      toast({ title: "Invitation code required", description: "Signup is currently invite-only.", variant: "destructive" });
      return;
    }
    if (!form.accept) {
      toast({ title: "Please accept the terms to continue", variant: "destructive" });
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/register", {
        email: form.email,
        username: form.username,
        password: form.password,
        referral_code: form.referral_code || null,
      });
      localStorage.setItem("mercari-global_token", data.token);
      try { localStorage.removeItem("mercari-global_pending_referral"); } catch { /* ignore */ }
      toast({ title: `Welcome, ${data.user.username}!`, description: "Your account is ready." });
      window.location.href = "/";
    } catch (err) {
      toast({
        title: "Sign up failed",
        description: err.response?.data?.detail || "Try a different email or username",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] relative overflow-hidden" data-testid="register-page">
      <div className="grid lg:grid-cols-2 min-h-[calc(100vh-4rem)]">
        {/* Left — brand pane */}
        <div
          className="relative hidden lg:flex flex-col justify-between p-12 text-white overflow-hidden"
          style={{
            background:
              "radial-gradient(circle at 25% 25%, rgba(84,89,232,0.55) 0%, transparent 45%), radial-gradient(circle at 80% 75%, rgba(255,5,21,0.5) 0%, transparent 45%), linear-gradient(160deg, #0F172A 0%, #1E293B 100%)",
          }}
        >
          <div className="pointer-events-none absolute -top-24 -right-24 h-96 w-96 rounded-full bg-[#818CF8] opacity-25 blur-3xl animate-pulse" />
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-96 w-96 rounded-full bg-[#5459E8] opacity-20 blur-3xl" />

          <BrandMark size={64} showWordmark animated wordmarkClassName="text-white" />

          <div className="max-w-md">
            <h2 className="text-4xl font-extrabold leading-tight">Start selling in minutes.</h2>
            <p className="mt-4 text-white/80 leading-relaxed">
              Your storefront is auto-provisioned the moment you register. List real Amazon-sourced inventory, earn instant escrow releases, and keep 90%+ of every sale.
            </p>
            <ul className="mt-8 space-y-3 text-sm text-white/90">
              <li className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-300" /> Auto-provisioned storefront + subdomain</li>
              <li className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-300" /> Reinvest frozen escrow into new orders</li>
              <li className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-300" /> 3-tier bulk discounts drive bigger baskets</li>
              <li className="flex items-center gap-2"><Check className="h-4 w-4 text-emerald-300" /> Real-time analytics for every category filter</li>
            </ul>
          </div>

          <div className="text-xs text-white/60">© {new Date().getFullYear()} BlueOcean · All rights reserved.</div>
        </div>

        {/* Right — form pane */}
        <div className="relative flex items-center justify-center p-6 sm:p-10">
          <div className="absolute inset-0 -z-10 lg:hidden" style={{
            background: "radial-gradient(circle at 20% 20%, #FFF7ED 0%, transparent 55%), radial-gradient(circle at 80% 80%, #DBEAFE 0%, transparent 55%), linear-gradient(180deg, #FFFBF6 0%, #F8FAFC 100%)",
          }} />
          <div className="w-full max-w-md">
            <div className="flex justify-center mb-6 lg:hidden">
              <BrandMark size={64} showWordmark animated wordmarkClassName="dark:text-neutral-100" />
            </div>

            <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl p-6 sm:p-8 shadow-xl shadow-neutral-200/50 dark:shadow-black/40">
              <div className="flex items-center gap-2 flex-wrap">
                <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800 dark:text-emerald-300">
                  <ShieldCheck className="h-3 w-3" /> Secure registration
                </div>
                {inviteOnly && (
                  <div
                    className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 px-2.5 py-0.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300"
                    data-testid="register-invite-badge"
                  >
                    <LockIcon className="h-3 w-3" /> Invite only
                  </div>
                )}
              </div>
              <h1 className="mt-3 text-2xl sm:text-3xl font-extrabold text-neutral-900 dark:text-neutral-100">Create your account</h1>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
                {inviteOnly
                  ? "Enter the invitation code shared by an existing member to join."
                  : "Join BlueOcean and get your storefront in seconds."}
              </p>

              <form onSubmit={submit} className="mt-6 space-y-4" data-testid="register-form">
                <div>
                  <Label htmlFor="reg-email" className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Email</Label>
                  <div className="relative mt-1.5">
                    <Mail className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <Input
                      id="reg-email"
                      type="email"
                      autoComplete="email"
                      value={form.email}
                      onChange={(e) => setForm({ ...form, email: e.target.value })}
                      required
                      className="pl-9 h-11 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB]"
                      data-testid="register-email"
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="reg-username" className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Username</Label>
                  <div className="relative mt-1.5">
                    <User className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <Input
                      id="reg-username"
                      value={form.username}
                      onChange={(e) => setForm({ ...form, username: e.target.value })}
                      required
                      minLength={3}
                      maxLength={20}
                      autoComplete="username"
                      className="pl-9 h-11 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB]"
                      data-testid="register-username"
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="reg-password" className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Password</Label>
                  <div className="relative mt-1.5">
                    <Lock className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2 z-10" />
                    <PasswordInput
                      id="reg-password"
                      autoComplete="new-password"
                      value={form.password}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                      required
                      minLength={6}
                      className="pl-9 h-11 focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB]"
                      testIdSuffix="register-password"
                      data-testid="register-password"
                    />
                  </div>
                  {form.password && (
                    <div className="mt-2" data-testid="password-strength">
                      <div className="grid grid-cols-4 gap-1">
                        {[1,2,3,4].map((b) => (
                          <div key={b} className={`h-1 rounded-full transition-colors ${b <= strength ? strengthColor : "bg-neutral-100 dark:bg-neutral-800"}`} />
                        ))}
                      </div>
                      <div className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">{strengthLabel}</div>
                    </div>
                  )}
                </div>

                <div>
                  <Label htmlFor="reg-confirm" className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Confirm password</Label>
                  <div className="relative mt-1.5">
                    <Lock className="h-4 w-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2 z-10" />
                    <PasswordInput
                      id="reg-confirm"
                      autoComplete="new-password"
                      value={form.confirm_password}
                      onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
                      required
                      minLength={6}
                      className={`pl-9 h-11 focus-visible:ring-2 ${
                        passwordsMismatch
                          ? "border-red-400 focus-visible:ring-red-400/30 focus-visible:border-red-500"
                          : passwordsMatch
                            ? "border-emerald-400 focus-visible:ring-emerald-400/30 focus-visible:border-emerald-500"
                            : "focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB]"
                      }`}
                      testIdSuffix="register-confirm"
                      data-testid="register-confirm-password"
                    />
                    {passwordsMatch && (
                      <Check className="h-4 w-4 text-emerald-500 absolute right-11 top-1/2 -translate-y-1/2 z-10" data-testid="password-match-check" />
                    )}
                  </div>
                  {passwordsMismatch && (
                    <div className="mt-1 text-[11px] text-red-600 flex items-center gap-1" data-testid="password-mismatch-error">
                      <AlertCircle className="h-3 w-3" /> Passwords don&apos;t match
                    </div>
                  )}
                </div>

                <div>
                  <Label htmlFor="reg-ref" className="text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                    Invitation code {inviteOnly ? <span className="text-amber-600 dark:text-amber-400 font-semibold">(required)</span> : <span className="text-neutral-400">(optional)</span>}
                  </Label>
                  <div className="relative mt-1.5">
                    <Gift className={`h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 ${inviteOnly ? "text-amber-500" : "text-neutral-400"}`} />
                    <Input
                      id="reg-ref"
                      value={form.referral_code}
                      onChange={(e) => setForm({ ...form, referral_code: e.target.value.toUpperCase() })}
                      placeholder={inviteOnly ? "Enter code from your inviter" : "Have a friend's code?"}
                      required={inviteOnly}
                      className={`pl-9 h-11 font-mono uppercase focus-visible:ring-2 focus-visible:ring-[#2563EB]/30 focus-visible:border-[#2563EB] ${
                        inviteOnly ? "bg-amber-50/50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900" : ""
                      }`}
                      maxLength={12}
                      data-testid="register-referral"
                    />
                  </div>
                  {inviteOnly && !inviteLoading && (
                    <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400 inline-flex items-center gap-1">
                      <Sparkles className="h-3 w-3 text-amber-500" /> New signups need a valid invitation from a BlueOcean member.
                    </p>
                  )}
                </div>

                <label className="flex items-start gap-2 text-xs text-neutral-600 dark:text-neutral-400 select-none cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.accept}
                    onChange={(e) => setForm({ ...form, accept: e.target.checked })}
                    className="mt-0.5 h-4 w-4 rounded border-neutral-300 accent-[#2563EB]"
                    data-testid="register-accept"
                  />
                  <span>
                    I agree to BlueOcean&apos;s{" "}
                    <a href="/terms" className="text-[#2563EB] dark:text-[#7DD3FC] hover:underline">Terms</a> and{" "}
                    <a href="/privacy" className="text-[#2563EB] dark:text-[#7DD3FC] hover:underline">Privacy Policy</a>.
                  </span>
                </label>

                <Button
                  type="submit"
                  disabled={loading || passwordsMismatch}
                  className="w-full bg-gradient-to-r from-[#5459E8] to-[#818CF8] hover:brightness-110 text-white h-11 shadow-md shadow-[#5459E8]/25 hover:shadow-lg transition-all font-semibold disabled:opacity-60"
                  data-testid="register-submit"
                >
                  {loading ? "Creating your account…" : <>Create account <ArrowRight className="h-4 w-4 ml-1" /></>}
                </Button>
              </form>

              <div className="my-6 flex items-center gap-3">
                <div className="flex-1 h-px bg-neutral-200 dark:bg-neutral-700" />
                <span className="text-[11px] uppercase tracking-widest text-neutral-400 dark:text-neutral-500">or</span>
                <div className="flex-1 h-px bg-neutral-200 dark:bg-neutral-700" />
              </div>

              <GoogleLoginButton label="Sign up with Google" testId="register-google-btn" />

              <p className="mt-6 text-sm text-center text-neutral-600 dark:text-neutral-400">
                Already have an account? <Link to="/login" className="text-[#2563EB] dark:text-[#7DD3FC] font-semibold hover:underline">Log in</Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Register;
